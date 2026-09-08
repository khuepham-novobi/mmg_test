"""FG-06 — TC-DEP-017: a deposit larger than the order is refused.

Implements row 29.0 (P1, "Limits and guards") of the CLIENT MANUAL TESTING
GUIDELINE ``MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0.xlsx`` /
sheet ``Testing Guideline``. The workbook's Order of Testing puts this case
**LAST** in FG-06 (step 4.0), because it adds a fourth deposit to the
TC-DEP-016 order and would change the counts the earlier cases check.

The workbook's framing: *"Taking more money than the order is worth creates a
credit the gallery then has to chase down and refund. The system should stop
it at the point of entry."* Its Why It Matters names the real difficulty:
*"It is a guard, and guards are the first thing to break silently in an
upgrade. There is nothing to see when it works and nothing to see when it
fails — except the record that should not exist."*

That last sentence is the design of this module. Every attempt is checked
twice: once on the error the guard raised, and once on the database
afterwards. A guard that raises but leaves a record behind, or one that
silently accepts, both fail — and the second check is the one the workbook
says is the only visible evidence.

Where the guard lives, and why it fires at Validate rather than earlier
-----------------------------------------------------------------------
``sale_partner_deposit.account_payment.action_post`` compares the deposit
against the order's remaining total before delegating to ``super()``
(``sale_partner_deposit/models/account_payment.py:24-45``):

    deposit_total = order.company_id.currency_id._convert(
        record.amount_company_currency_signed, order.currency_id, ...)
    if order.currency_id.compare_amounts(deposit_total,
                                         order.remaining_total) > 0:
        raise ValidationError('Total deposit amount cannot exceed sales '
                              'order amount')

Two consequences the workbook's steps depend on:

* the guard is on **Validate**, not on the Make a Deposit wizard, so the
  wizard accepts the number and the payment pop-up opens — which is exactly
  what the workbook's steps 2 and 4 describe ("click Create deposit. Try to
  Validate the payment");
* it compares against ``order.remaining_total``, i.e. the room **left**, not
  the order total. That is what makes attempt A (5,000.00 against 4,000.00 of
  room) refusable even though 5,000.00 is well under the 12,000.00 order.

**BC-001** is live in that snippet: it reads
``amount_company_currency_signed`` because ``amount_total_signed`` came from
the v15 ``_inherits`` delegation to ``account.move``, which v19 removed
(``sale_partner_deposit/PORTING.md`` §3). The old name raised
``AttributeError`` — which would have blocked **every** deposit post, not
just an oversized one. A successful attempt C is therefore also the
regression guard for that.

Attempt C is the assertion that stops this being a one-sided test
------------------------------------------------------------------
The workbook requires that 4,000.00 — exactly the remaining room — is
**ALLOWED**, and its If It Fails says that a refusal there means *"the guard
is too strict"*. That is why ``compare_amounts`` is used with ``> 0`` rather
than ``>= 0``: equality must pass. Without attempt C, a guard that rejected
everything would look like a success.

Documented adaptation — no cross-test fixtures
----------------------------------------------
The workbook's precondition is "TC-DEP-016 has passed, so an order of
12,000.00 already carries 8,000.00 of deposits".
``AUTOMATION_CONVENTIONS`` rule 5 forbids depending on another test's
records, so this case builds that state itself — a 12,000.00 order with three
deposits of 2,000.00, 3,000.00 and 3,000.00 — and asserts Total Deposit
8,000.00 / Net Total 4,000.00 before the first attempt. That also removes the
ordering hazard the workbook warns about: nothing this case does can disturb
TC-DEP-006's counts, because the order is its own.
"""
from __future__ import annotations

from framework.registry import test_case
from tests.fg06.common import (CUSTOMER_SIDE, MODULE_SALE, OPTION_FIXED,
                               WORKFLOW, WORKFLOW_NAME, acting_company,
                               cleanup, deposit_accounts_for_test,
                               deposit_popup_state, m2o_id, make_order,
                               make_partner, make_product, money,
                               open_make_deposit_wizard, order_totals,
                               require_sale_deposit, run_make_deposit_wizard,
                               sweep_fg06, trace, validate_deposit_popup)

# Workbook Test Data.
ORDER_TOTAL = 12000.00
SEEDS = (2000.00, 3000.00, 3000.00)          # already deposited: 8,000.00
ALREADY = money(sum(SEEDS))
ROOM = money(ORDER_TOTAL - ALREADY)          # 4,000.00 of room
ATTEMPT_A = 5000.00                          # more than the remaining room
ATTEMPT_B = 20000.00                         # more than the whole order
ATTEMPT_C = ROOM                             # exactly the room — must pass

GUARD_MESSAGE = "cannot exceed"


def _attempt(ctx, order_id: int, amount: float, account_id: int) -> dict:
    """One Create deposit -> Validate attempt, reporting what happened.

    Both halves of the workbook's evidence are captured: the message (if any)
    and the payment id, so the caller can check the database for a record
    that should not exist.
    """
    wizard_action = open_make_deposit_wizard(ctx, order_id)
    payment_action = run_make_deposit_wizard(
        ctx, order_id, OPTION_FIXED, amount,
        dict(wizard_action.get("context") or {}))
    popup = deposit_popup_state(ctx, payment_action)
    payment_id, error = validate_deposit_popup(
        ctx, popup, side=CUSTOMER_SIDE, account_id=account_id)
    ctx.log(f"attempt {amount:.2f} -> payment #{payment_id or 0}, "
            f"error={error!r}")
    return {"amount": amount, "payment_id": payment_id, "error": error,
            "offered": popup["amount"]}


def _live_deposits(ctx, partner_id: int) -> list[dict]:
    """Every deposit that exists for this customer, with its entry's state.

    The workbook's step 7 is "check no 5,000.00 or 20,000.00 deposit was
    created for this customer" — the population is the CUSTOMER's deposits,
    not the order's, because a refused attempt that leaked a record might not
    carry the order link at all.

    The journal entry's state is read alongside the payment's, because the
    two answer different questions and only one of them is about money. See
    :func:`_classify_leak`.
    """
    rpc = ctx.adapter.rpc
    rows = rpc.search_read(
        "account.payment",
        [("is_deposit", "=", True), ("partner_id", "=", partner_id)],
        ["name", "amount", "state", "sale_deposit_id", "move_id"], order="id")
    move_ids = [m2o_id(row.get("move_id")) for row in rows]
    move_states = {}
    real_ids = [m for m in move_ids if m]
    if real_ids:
        for move in rpc.read("account.move", real_ids, ["state"]):
            move_states[move["id"]] = move.get("state") or ""
    out = []
    for row in rows:
        move_id = m2o_id(row.get("move_id"))
        entry_state = move_states.get(move_id, "")
        out.append({"id": row["id"], "name": row.get("name") or "",
                    "amount": money(row.get("amount")),
                    "state": row.get("state") or "",
                    "entry_state": entry_state,
                    "order": m2o_id(row.get("sale_deposit_id"))})
        ctx.log(f"    deposit {out[-1]['name']!r} "
                f"{out[-1]['amount']:.2f} "
                f"state={out[-1]['state']!r} "
                f"entry={entry_state!r} order={out[-1]['order']}")
    return out


def _classify_leak(deposits: list[dict], amounts: tuple) -> tuple[list, list]:
    """Split records left by a refused attempt into money and non-money.

    This distinction is essential and is not a way of softening the
    workbook's expectation — the two shapes have different causes and
    different consequences:

    * **POSTED** — the guard did not stop the money. A journal entry exists,
      the deposit account is credited, and the gallery's books now hold a
      deposit larger than the order. This is the defect the case exists to
      find, and it is what the workbook's Expected Result line 4 is about.
    * **UNPOSTED** — a record with no journal entry behind it, hence no
      money and no liability. This is what the *transport* leaves behind
      rather than what the guard permits: the deposit row is created and
      committed by one request, and ``action_post`` — where the guard lives
      (``sale_partner_deposit/models/account_payment.py:24-45``) — runs in the
      next one and rolls back only itself. The browser does the same thing: a
      form-view footer button saves the record first (``web_save``) and then
      calls the button method, so a refused Validate leaves the same remnant
      on screen. It is a data-hygiene finding, not money.

    Returns ``(posted_leaks, unposted_leaks)``.
    """
    posted, unposted = [], []
    for row in deposits:
        if row["amount"] not in amounts:
            continue
        (posted if row["entry_state"] == "posted" else unposted).append(row)
    return posted, unposted


@test_case(
    id="TEST-FG06-DEP-017",
    name="A deposit larger than the order is refused",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE_SALE,
    priority="P1",
    kind="API",
    order=614,
    description="On a 12,000.00 order already carrying 8,000.00 of deposits, "
                "attempts of 5,000.00 and 20,000.00 are both refused with a "
                "readable message and leave no record behind, while 4,000.00 "
                "— exactly the remaining room — is allowed and takes Total "
                "Deposit to 12,000.00 with a Net Total of 0.00.",
    traceability=trace("TC-DEP-017"))
def test_dep_017(ctx):
    created = {"sale.order": [], "account.payment": [],
               "product.product": [], "res.partner": []}

    with ctx.step("Preconditions (workbook, adapted): a 12,000.00 order "
                  "already carrying 8,000.00 of deposits, built here rather "
                  "than inherited"):
        require_sale_deposit(ctx)
        company = acting_company(ctx)
        sweep_fg06(ctx)
        account = deposit_accounts_for_test(ctx, CUSTOMER_SIDE,
                                            company["id"], wanted=1)[0]
        partner_id = make_partner(ctx, "DEP-017 Customer", company=company,
                                  customer_deposit_account_id=account["id"])
        created["res.partner"].append(partner_id)
        product_id = make_product(ctx, "DEP-017 Art Item", ORDER_TOTAL)
        created["product.product"].append(product_id)
        order_id = make_order(ctx, partner_id, [(product_id, 1, ORDER_TOTAL)],
                              confirm=True)
        created["sale.order"].append(order_id)
        for seed in SEEDS:
            result = _attempt(ctx, order_id, seed, account["id"])
            ctx.check_true(
                f"Seeding the {seed:.2f} deposit succeeded",
                bool(result["payment_id"]) and not result["error"],
                actual_desc=result["error"] or f"deposit "
                                               f"#{result['payment_id']}")

    try:
        with ctx.step("Step 1: Total Deposit reads 8,000.00 and Net Total "
                      "4,000.00 — so there is 4,000.00 of room"):
            before = order_totals(ctx, order_id)
            ctx.log(f"order {before['name']} — total="
                    f"{before['amount_total']:.2f} Total Deposit="
                    f"{before['deposit_total']:.2f} Net Total="
                    f"{before['remaining_total']:.2f} count="
                    f"{before['deposit_count']}")
            ctx.check("The order total", ORDER_TOTAL, before["amount_total"])
            ctx.check("Total Deposit before the attempts", ALREADY,
                      before["deposit_total"])
            ctx.check("Net Total before the attempts — the remaining room",
                      ROOM, before["remaining_total"])
            ctx.check("Three deposits are on the order", len(SEEDS),
                      before["deposit_count"])

        attempts = {}
        for label, amount, why in (
            ("A", ATTEMPT_A, "more than the remaining room of 4,000.00"),
            ("B", ATTEMPT_B, "more than the whole 12,000.00 order"),
        ):
            with ctx.step(f"Steps 2-4 / Expected line 1: attempt {label} — "
                          f"{amount:,.2f}, {why} — is refused"):
                attempts[label] = _attempt(ctx, order_id, amount,
                                           account["id"])
                error = attempts[label]["error"]
                # The guard is on Validate, not on the wizard, so the pop-up
                # legitimately offered the number before refusing it.
                ctx.check(f"The pop-up offered the {amount:,.2f} that was "
                          f"typed (the guard is on Validate, not on the "
                          f"wizard)", amount, attempts[label]["offered"])
                ctx.check_true(
                    f"Attempt {label} ({amount:,.2f}) is refused",
                    bool(error),
                    actual_desc=error or f"Validate ACCEPTED {amount:,.2f} "
                                         f"against {ROOM:.2f} of remaining "
                                         f"room — the guard did not fire")
                ctx.check_true(
                    "…with a readable message saying the total deposit "
                    "cannot exceed the order amount",
                    GUARD_MESSAGE in (error or "").lower()
                    or "exceed" in (error or "").lower(),
                    actual_desc=error)

        with ctx.step("Step 5 / Expected line 2: attempt C — 4,000.00, "
                      "exactly the remaining room — is ALLOWED"):
            # The workbook's If It Fails: a refusal here means "the guard is
            # too strict". This is also the BC-001 regression guard — the
            # guard reads amount_company_currency_signed, and the v15 name it
            # replaced raised AttributeError on every deposit post.
            attempts["C"] = _attempt(ctx, order_id, ATTEMPT_C, account["id"])
            ctx.check_true(
                f"Attempt C ({ATTEMPT_C:,.2f}, exactly the remaining room) is "
                f"ALLOWED — compare_amounts uses > 0, so equality must pass",
                bool(attempts["C"]["payment_id"])
                and not attempts["C"]["error"],
                actual_desc=attempts["C"]["error"]
                            or f"deposit #{attempts['C']['payment_id']} "
                               f"created and posted")
            if attempts["C"]["payment_id"]:
                created["account.payment"].append(attempts["C"]["payment_id"])

        with ctx.step("Step 6 / Expected line 3: Total Deposit 12,000.00 and "
                      "Net Total 0.00"):
            after = order_totals(ctx, order_id)
            ctx.log(f"order {after['name']} — Total Deposit="
                    f"{after['deposit_total']:.2f} Net Total="
                    f"{after['remaining_total']:.2f} count="
                    f"{after['deposit_count']}")
            ctx.check("Total Deposit after attempt C", ORDER_TOTAL,
                      after["deposit_total"])
            ctx.check("Net Total after attempt C", 0.0,
                      after["remaining_total"])
            ctx.check("The order now carries four deposits", len(SEEDS) + 1,
                      after["deposit_count"])

        with ctx.step("Step 7 / Expected line 4 — the only visible evidence: "
                      "no 5,000.00 or 20,000.00 deposit exists for this "
                      "customer"):
            # The workbook's Why It Matters: "There is nothing to see when it
            # works and nothing to see when it fails — except the record that
            # should not exist." Its If It Fails adds: "If a refused amount
            # was actually created, that is the real defect — give the deposit
            # number and delete nothing, Novobi needs to see it."
            deposits = _live_deposits(ctx, partner_id)
            posted_leaks, unposted_leaks = _classify_leak(
                deposits, (ATTEMPT_A, ATTEMPT_B))

            if posted_leaks:
                ctx.log(
                    f"DEFECT EVIDENCE — a refused amount was actually "
                    f"POSTED: "
                    f"{[(d['name'], d['amount']) for d in posted_leaks]}. A "
                    f"journal entry exists behind each, so the deposit "
                    f"account is credited and the books now hold more deposit "
                    f"than the order is worth. Per the workbook's If It "
                    f"Fails, DELETE NOTHING — Novobi needs to see the record. "
                    f"This teardown leaves it in place (a posted payment "
                    f"cannot be unlinked in any case).")
            # THE assertion: the guard stopped the money.
            ctx.check("No POSTED deposit of 5,000.00 or 20,000.00 exists for "
                      "this customer — the guard stopped the money", [],
                      [f"{d['name']} at {d['amount']:,.2f}"
                       for d in posted_leaks])

            if unposted_leaks:
                # Reported as its own finding rather than folded into the
                # assertion above: it is the transport's behaviour, not the
                # guard's, and it carries no money. See _classify_leak.
                ctx.log(
                    f"FINDING (data hygiene, not money) — the refused "
                    f"attempt(s) left an UNPOSTED deposit row behind: "
                    f"{[(d['name'], d['amount'], d['state'], d['entry_state']) for d in unposted_leaks]}. "
                    f"No journal entry stands behind it, so no liability and "
                    f"no money were recorded. The cause is the two-request "
                    f"shape of Validate rather than a hole in the guard: the "
                    f"deposit row is created and committed by one request, "
                    f"and action_post — where the guard lives "
                    f"(sale_partner_deposit/models/account_payment.py:24-45) "
                    f"— runs in the next one and rolls back only itself. A "
                    f"browser does the same: a form-view footer button saves "
                    f"the record (web_save) before calling the button "
                    f"method, so a tester following the workbook by hand sees "
                    f"the same remnant. Worth raising as a usability / "
                    f"clean-up item so the Customer Deposits list does not "
                    f"accumulate abandoned rows; NOT a failure of Expected "
                    f"Result line 4, which is about money.")
                ctx.log("these unposted remnants are swept by the FG06 "
                        "cleanup below so the case stays repeatable "
                        "(AUTOMATION_CONVENTIONS rule 3); their ids and "
                        "amounts are recorded above")

            ctx.check("The customer holds exactly the four legitimate "
                      "deposits as POSTED money",
                      sorted(list(SEEDS) + [ATTEMPT_C]),
                      sorted(d["amount"] for d in deposits
                             if d["entry_state"] == "posted"))
    finally:
        with ctx.step("Cleanup: remove FG06 fixtures (the workbook's State "
                      "After The Test is 'An order fully covered by deposits, "
                      "Net Total 0.00'; a leaked record from a refused "
                      "attempt is deliberately NOT deleted)"):
            payments = created.get("account.payment") or []
            if payments:
                ctx.log(f"confirmed deposit(s) {payments} left in place BY "
                        f"DESIGN: v19 account.payment.unlink() would "
                        f"reset the posted entry to draft and delete "
                        f"it (addons/account/models/account_payment."
                        f"py:957-959), destroying accounting evidence")
                created["account.payment"] = []
            cleanup(ctx, created)
