"""FG-06 — resetting a deposit, and resetting the invoice it was applied to.

Implements two rows of the CLIENT MANUAL TESTING GUIDELINE
``MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0.xlsx`` / sheet
``Testing Guideline``:

* **TC-DEP-010** (row 24.0, P0, "Correcting deposits") — "Resetting a deposit
  to draft does not break what it was applied to". The workbook marks it
  *READ THIS FIRST, and this is the single most important FG-06 case*, and it
  is the workbook's **GATE 4**: if resetting a deposit leaves the invoice
  showing the money as both applied and available, testing of FG-06 stops.
* **TC-DEP-011** (row 25.0/26.0, P1) — "Resetting a part-paid invoice frees
  its deposit again". The mirror image, worked from the invoice side, where
  the failure is *a stranded deposit: money the gallery holds and can never
  apply, and nothing on screen says so.*

Why TC-DEP-010 is the case the port was designed around
--------------------------------------------------------
Its Why It Matters says: *"The way Odoo 19 rebuilds a payment's journal entry
changed. Done wrongly, the link between the deposit and the invoice is
destroyed while both documents still look correct on screen. The only way to
see it is to check the invoice afterwards."*

That is decision **D2-a**, and it is precise. v19 stock updates a payment's
liquidity and counterpart lines **in place** but still **deletes and recreates
its write-off lines on every synchronisation**
(``addons/account/models/account_payment.py:1042-1045``). For a deposit the
write-off line *is* the deposit-account line
(``account_partner_deposit/models/account_payment.py:66-90``), so stock
behaviour would change that line's database id and orphan any
``account.partial.reconcile`` hanging off it. The port therefore overrides
``_synchronize_to_moves`` to update the deposit line in place, keeping its id
and its reconciliations
(``account_partner_deposit/models/account_payment.py:150-260``).

So this module asserts identity, not just amounts: the deposit line's **id**
must survive an edit. An assertion on the amount alone would pass on the
broken implementation, because the recreated line carries the right amount —
it is only the link that is lost. That is exactly the failure the workbook
describes as invisible on screen.

The three-way outcome the workbook allows — and the one it forbids
------------------------------------------------------------------
TC-DEP-010's Expected Result is unusual and is implemented literally. After
the deposit is reset and re-confirmed, the invoice must be in a **consistent**
state, and the workbook names two acceptable shapes and one forbidden one:

* acceptable: 7,000.00 due **with** the deposit applied;
* acceptable: 10,000.00 due **with** the deposit back in Outstanding credits;
* **not acceptable**: 7,000.00 due **and** the deposit also showing as
  available — *"that means the money is counted twice"*.

The assertion is therefore on the *pair* (Amount Due, is-the-deposit-offered)
being one of the two allowed combinations, and the double-count shape is
called out by name in the failure text so the verdict is unambiguous. All
four numbers the workbook's If It Fails demands are recorded whatever the
outcome, because it says to state all four *"even if they look fine"*.

What ``button_draft`` does on the way
-------------------------------------
Resetting either document runs the module's ``account.move.button_draft``
override, which finds the intermediate 'Deposit to Payment' entries through
their partial reconciliations, resets them and deletes them
(``account_partner_deposit/models/account_move.py:100-133``). Two v19 details
matter and are recorded in the evidence:

* **BC-017** — it reaches the payment through ``origin_payment_id``;
  ``account.move.payment_id`` was the reverse of the v15 ``_inherits`` and no
  longer exists (``addons/account/models/account_move.py:207``). The old name
  raised ``AttributeError``, which broke reset-to-draft on **every** invoice,
  not only deposit ones.
* **DW-001 / TC-DEP-023** — the intermediate-entry lookup is a parameterised
  SQL query guarded against an empty line set, because interpolating a Python
  tuple yields ``IN ()`` for none and ``IN (5,)`` for one, both PostgreSQL
  syntax errors.

Documented adaptation — no cross-test fixtures
----------------------------------------------
TC-DEP-010's precondition is "TC-DEP-007 has passed: an invoice is part-paid
by a 3,000.00 deposit and shows 7,000.00 due", and TC-DEP-011's adds "if
TC-DEP-010 left the invoice fully due, redo TC-DEP-007's step 5 to re-apply
the deposit before starting". ``AUTOMATION_CONVENTIONS`` rule 5 forbids
depending on another test's records, so each case builds that starting state
itself — an order of 10,000.00 with a 3,000.00 deposit, invoiced and posted —
and asserts it is really there before touching anything. TC-DEP-011's
conditional re-apply becomes unnecessary as a result, which removes a branch
rather than hiding one.
"""
from __future__ import annotations

from adapters.base import OdooRPCError
from framework.registry import test_case
from tests.fg06.common import (CUSTOMER_SIDE, MODULE, MODULE_SALE,
                               OPTION_FIXED, PAYMENT_STATE_NOT_PAID,
                               PAYMENT_STATE_PARTIAL, WORKFLOW, WORKFLOW_NAME,
                               acting_company, cleanup,
                               deposit_accounts_for_test,
                               deposit_popup_state, invoice_from_order,
                               invoice_totals, make_invoice, make_order,
                               make_partner, make_product, money, move_lines,
                               open_make_deposit_wizard, outstanding_credits,
                               payment_row, require_sale_deposit,
                               restore_uninvoiced_order,
                               run_make_deposit_wizard, sweep_fg06, trace,
                               validate_deposit_popup)

ORDER_TOTAL, DEPOSIT = 10000.00, 3000.00
REMAINING = money(ORDER_TOTAL - DEPOSIT)
NEW_MEMO = "UAT reset test"


def _part_paid_invoice(ctx, company, account, label: str) -> dict:
    """Build TC-DEP-007's end state: a 10,000.00 invoice part-paid by 3,000.00.

    Returns the ids and the figures, and asserts the starting state so a
    later failure cannot be blamed on a fixture that was never right.

    MMG AUTO-INVOICE — why the order is put back before it is invoiced
    ------------------------------------------------------------------
    This fixture has to raise the invoice FROM THE ORDER, because that is
    what makes posting it apply the order's deposits
    (``sale_partner_deposit/models/account_move.py:7-17``) and so produces
    the 7,000.00-due starting state both cases assert.
    ``mmg_sale_auto_create_invoice`` overrides ``action_confirm`` to invoice
    the order in full the moment it is confirmed, and the flag is ON for the
    acting company on the MMG v19 database, so ``invoice_from_order`` found
    nothing left to invoice and ``create_invoices()`` raised *"Cannot create
    an invoice. No items are available to invoice"*
    (``addons/sale/models/sale_order.py:1615-1616``). The DRAFT invoice
    ``action_confirm`` raised is therefore removed first, restoring the
    workbook's precondition; a posted one is never touched and BLOCKS the
    case instead (:func:`~tests.fg06.common.restore_uninvoiced_order`).
    """
    partner_id = make_partner(ctx, f"{label} Customer", company=company,
                              customer_deposit_account_id=account["id"])
    product_id = make_product(ctx, f"{label} Art Item", ORDER_TOTAL)
    order_id = make_order(ctx, partner_id, [(product_id, 1, ORDER_TOTAL)],
                          confirm=True)
    restore_uninvoiced_order(ctx, order_id, company)

    wizard_action = open_make_deposit_wizard(ctx, order_id)
    payment_action = run_make_deposit_wizard(
        ctx, order_id, OPTION_FIXED, DEPOSIT,
        dict(wizard_action.get("context") or {}))
    popup = deposit_popup_state(ctx, payment_action)
    deposit_id, error = validate_deposit_popup(
        ctx, popup, side=CUSTOMER_SIDE, account_id=account["id"])
    ctx.check_true("The 3,000.00 deposit was taken against the order",
                   bool(deposit_id) and not error,
                   actual_desc=error or f"deposit #{deposit_id}")

    invoice_id = invoice_from_order(ctx, order_id)
    ctx.check_true("An invoice was raised from the order", bool(invoice_id),
                   actual_desc=f"invoice id {invoice_id!r}")
    ctx.adapter.rpc.call("account.move", "action_post", [invoice_id])
    invoice = invoice_totals(ctx, invoice_id)
    ctx.log(f"starting state — invoice {invoice['name']}: total="
            f"{invoice['amount_total']:.2f} Amount Due="
            f"{invoice['amount_residual']:.2f} "
            f"payment_state={invoice['payment_state']!r}")

    # Posting an invoice raised from an order applies that order's deposits
    # automatically (sale_partner_deposit/models/account_move.py:7-17), which
    # is what produces the workbook's stated starting state.
    ctx.check("Starting state: Amount Due is 7,000.00 on a 10,000.00 invoice "
              "(the workbook's TC-DEP-007 end state)", REMAINING,
              invoice["amount_residual"])
    ctx.check("Starting state: the invoice shows a partial payment",
              PAYMENT_STATE_PARTIAL, invoice["payment_state"])
    return {"partner_id": partner_id, "product_id": product_id,
            "order_id": order_id, "deposit_id": deposit_id,
            "invoice_id": invoice_id}


def _deposit_line(ctx, deposit_id: int, account_id: int) -> dict:
    """The deposit-account line of a deposit's own journal entry, or ``{}``."""
    row = payment_row(ctx, deposit_id)
    if not row["move_id"]:
        return {}
    lines = [ln for ln in move_lines(ctx, row["move_id"])
             if ln["account_id"] == account_id]
    return lines[0] if len(lines) == 1 else {}


def _is_offered(ctx, invoice_id: int, deposit_id: int) -> bool:
    """Is this deposit currently showing as available on that invoice?"""
    return bool([e for e in outstanding_credits(ctx, invoice_id)
                 if e["payment_id"] == deposit_id])


@test_case(
    id="TEST-FG06-DEP-010",
    name="Resetting a deposit to draft does not break what it was applied to",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P0",
    kind="API",
    order=611,
    description="GATE 4. A deposit applied to an invoice is reset to draft, "
                "edited, and re-confirmed; the deposit-account line keeps its "
                "database identity (decision D2-a) and the invoice is left in "
                "a consistent state — never showing the money as both applied "
                "and available, which would double-count it.",
    traceability=trace("TC-DEP-010"))
def test_dep_010(ctx):
    rpc = ctx.adapter.rpc
    created = {"account.move": [], "sale.order": [], "account.payment": [],
               "product.product": [], "res.partner": []}

    with ctx.step("Preconditions (workbook, adapted): an invoice part-paid "
                  "by a 3,000.00 deposit showing 7,000.00 due, built here "
                  "rather than inherited"):
        require_sale_deposit(ctx)
        company = acting_company(ctx)
        sweep_fg06(ctx)
        account = deposit_accounts_for_test(ctx, CUSTOMER_SIDE,
                                            company["id"], wanted=1)[0]
        fixture = _part_paid_invoice(ctx, company, account, "DEP-010")
        created["res.partner"].append(fixture["partner_id"])
        created["product.product"].append(fixture["product_id"])
        created["sale.order"].append(fixture["order_id"])

    # All four numbers the workbook's If It Fails demands, recorded whatever
    # the outcome ("All four, even if they look fine").
    report = {"invoice_due_before": None, "deposit_state_after": None,
              "invoice_due_after": None, "offered_at_end": None}
    try:
        with ctx.step("Step 1: WRITE DOWN the invoice's Amount Due and "
                      "payment status"):
            before = invoice_totals(ctx, fixture["invoice_id"])
            report["invoice_due_before"] = before["amount_residual"]
            ctx.log(f"BEFORE — invoice {before['name']}: Amount Due="
                    f"{before['amount_residual']:.2f} "
                    f"payment_state={before['payment_state']!r}")
            ctx.check("Amount Due before the reset", REMAINING,
                      before["amount_residual"])
            original_line = _deposit_line(ctx, fixture["deposit_id"],
                                          account["id"])
            ctx.check_true(
                "The deposit has exactly one deposit-account line to keep "
                "track of", bool(original_line),
                actual_desc=f"deposit line #{original_line.get('id')}")
            original_line_id = original_line.get("id")
            ctx.log(f"BEFORE — deposit line #{original_line_id} "
                    f"credit={original_line.get('credit'):.2f} "
                    f"reconciled={original_line.get('reconciled')} "
                    f"residual={original_line.get('amount_residual'):.2f}")

        with ctx.step("Step 2: note the deposit's status"):
            deposit_before = payment_row(ctx, fixture["deposit_id"])
            ctx.log(f"BEFORE — deposit {deposit_before['name']}: "
                    f"state={deposit_before['state']!r} "
                    f"entry={deposit_before['move_state']!r} "
                    f"intermediate entries={deposit_before['deposit_ids']}")

        with ctx.step("Steps 3-4 / Expected line 1: Reset to Draft returns "
                      "the deposit to Draft and it can be edited"):
            # account.payment.action_draft sets state='draft' and calls
            # move_id.button_draft(), which is the module's override
            # (addons/account/models/account_payment.py:1161-1163).
            reset_error = ""
            try:
                rpc.call("account.payment", "action_draft",
                         [fixture["deposit_id"]])
            except OdooRPCError as exc:
                reset_error = str(exc)
            ctx.check_true(
                "Reset to Draft raised no error (BC-017 regression guard: the "
                "override reaches the payment through origin_payment_id; the "
                "v15 name account.move.payment_id no longer exists and raised "
                "AttributeError here)",
                not reset_error, actual_desc=reset_error or "no error")
            after_reset = payment_row(ctx, fixture["deposit_id"])
            report["deposit_state_after"] = (
                f"{after_reset['state']}/{after_reset['move_state']}")
            ctx.log(f"after Reset to Draft — state={after_reset['state']!r} "
                    f"entry={after_reset['move_state']!r}")
            ctx.check("The deposit returns to Draft", "draft",
                      after_reset["state"])
            ctx.check("…and so does its journal entry", "draft",
                      after_reset["move_state"])

        with ctx.step("Step 5 / Expected line 1 (b): the Memo accepts an "
                      "edit — and the deposit line keeps its identity "
                      "(decision D2-a)"):
            rpc.write("account.payment", [fixture["deposit_id"]],
                      {"memo": NEW_MEMO})
            edited = payment_row(ctx, fixture["deposit_id"])
            ctx.check("The Memo accepted the edit", NEW_MEMO, edited["memo"])
            edited_line = _deposit_line(ctx, fixture["deposit_id"],
                                        account["id"])
            ctx.log(f"after the edit — deposit line "
                    f"#{edited_line.get('id')} "
                    f"credit={edited_line.get('credit')}")
            # THE D2-a assertion. An amount-only check would pass on the
            # broken implementation: v19 stock deletes and recreates the
            # write-off line on every sync (addons/account/models/
            # account_payment.py:1042-1045), and the recreated line carries
            # the right amount — only the id, and any partial reconcile
            # pointing at it, are lost.
            ctx.check("The deposit-account line keeps its database identity "
                      "across an edit (D2-a: the line is updated in place, "
                      "not deleted and recreated, so its reconciliations "
                      "survive)", original_line_id, edited_line.get("id"))
            ctx.check("…and still carries the 3,000.00 credit", DEPOSIT,
                      edited_line.get("credit"))

        with ctx.step("Step 6 / Expected line 2: the deposit re-confirms "
                      "without error"):
            confirm_error = ""
            try:
                rpc.call("account.payment", "action_post",
                         [fixture["deposit_id"]])
            except OdooRPCError as exc:
                confirm_error = str(exc)
            ctx.check_true("Confirm raised no error", not confirm_error,
                           actual_desc=confirm_error or "no error")
            reconfirmed = payment_row(ctx, fixture["deposit_id"])
            report["deposit_state_after"] = (
                f"{reconfirmed['state']}/{reconfirmed['move_state']}")
            ctx.log(f"after Confirm — state={reconfirmed['state']!r} "
                    f"entry={reconfirmed['move_state']!r}")
            ctx.check("The deposit's journal entry is posted again", "posted",
                      reconfirmed["move_state"])

        with ctx.step("Steps 7-9 / Expected line 3 — THE REAL TEST: the "
                      "invoice is in a CONSISTENT state"):
            after = invoice_totals(ctx, fixture["invoice_id"])
            offered = _is_offered(ctx, fixture["invoice_id"],
                                  fixture["deposit_id"])
            report["invoice_due_after"] = after["amount_residual"]
            report["offered_at_end"] = offered
            ctx.log(f"AFTER — invoice {after['name']}: Amount Due="
                    f"{after['amount_residual']:.2f} "
                    f"payment_state={after['payment_state']!r}; the deposit "
                    f"{'IS' if offered else 'is NOT'} offered in Outstanding "
                    f"credits")

            still_applied = (after["amount_residual"] == REMAINING
                             and not offered)
            fully_due_and_available = (
                after["amount_residual"] == ORDER_TOTAL and offered)
            double_counted = (after["amount_residual"] == REMAINING
                              and offered)

            if double_counted:
                ctx.log(
                    "GATE 4 FAILURE — the invoice shows 7,000.00 due AND the "
                    "deposit is also available in Outstanding credits. The "
                    "3,000.00 is counted twice: it is settling the invoice "
                    "and simultaneously offered for use elsewhere. Per the "
                    "workbook this is a P0 to be raised immediately, and "
                    "FG-06 testing STOPS here (Order of Testing, GATE 4).")
            # The workbook allows two shapes and forbids exactly one, so the
            # assertion is on the pair rather than on either number alone.
            ctx.check_true(
                "The invoice is in one of the two consistent states the "
                "workbook allows — 7,000.00 due with the deposit applied, or "
                "10,000.00 due with the deposit back in Outstanding credits — "
                "and NOT 7,000.00 due with the deposit also available, which "
                "would double-count the money",
                still_applied or fully_due_and_available,
                actual_desc=(
                    f"Amount Due={after['amount_residual']:.2f}, deposit "
                    f"offered in Outstanding credits={offered}, "
                    f"payment_state={after['payment_state']!r} -> "
                    + ("DOUBLE-COUNTED: applied and available at the same "
                       "time" if double_counted
                       else "neither allowed shape: the figures do not match "
                            "7,000.00-applied or 10,000.00-available")))
            ctx.check_true(
                "…and the payment status agrees with the Amount Due",
                (after["payment_state"] == PAYMENT_STATE_PARTIAL
                 if still_applied
                 else after["payment_state"] == PAYMENT_STATE_NOT_PAID),
                actual_desc=f"payment_state={after['payment_state']!r} with "
                            f"Amount Due={after['amount_residual']:.2f}")
            ctx.log(f"OUTCOME (workbook State After The Test asks which): "
                    f"{'the invoice is still part-paid' if still_applied else 'the invoice is fully due again with the deposit available'}")

        with ctx.step("Step 10 / Expected line 4: no error appeared at any "
                      "step, and the invoice's journal entry is intact"):
            lines = move_lines(ctx, fixture["invoice_id"])
            ctx.check_true(
                "The invoice's journal entry still has its lines",
                bool(lines),
                actual_desc=f"{len(lines)} journal item(s)")
            ctx.check_true(
                "The invoice's journal entry is balanced",
                money(sum(ln["debit"] for ln in lines))
                == money(sum(ln["credit"] for ln in lines)),
                actual_desc=f"debits="
                            f"{money(sum(ln['debit'] for ln in lines)):.2f} "
                            f"credits="
                            f"{money(sum(ln['credit'] for ln in lines)):.2f}")
    finally:
        with ctx.step("Evidence: the four numbers the workbook's If It Fails "
                      "demands, recorded whatever the outcome"):
            ctx.log(f"REPORT (workbook If It Fails — state all four, even if "
                    f"they look fine): "
                    f"(1) invoice Amount Due BEFORE = "
                    f"{report['invoice_due_before']}; "
                    f"(2) deposit state AFTER (payment/entry) = "
                    f"{report['deposit_state_after']}; "
                    f"(3) invoice Amount Due AFTER = "
                    f"{report['invoice_due_after']}; "
                    f"(4) deposit shown in Outstanding credits at the end = "
                    f"{report['offered_at_end']}. Attach the invoice's "
                    f"journal entry, which is printed in the step above.")
            for key in ("account.move", "account.payment"):
                if created.get(key):
                    created[key] = []
            cleanup(ctx, created)


@test_case(
    id="TEST-FG06-DEP-011",
    name="Resetting a part-paid invoice frees its deposit again",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE_SALE,
    priority="P1",
    kind="API",
    order=612,
    description="Resetting a part-paid invoice to draft leaves its 3,000.00 "
                "deposit intact and available again — offered in Outstanding "
                "credits on another invoice for the same customer — and "
                "re-confirming the first invoice shows the full 10,000.00 due.",
    traceability=trace("TC-DEP-011"))
def test_dep_011(ctx):
    rpc = ctx.adapter.rpc
    created = {"account.move": [], "sale.order": [], "account.payment": [],
               "product.product": [], "res.partner": []}
    other_invoice_total = 5000.00

    with ctx.step("Preconditions (workbook, adapted): an invoice part-paid "
                  "by a 3,000.00 deposit, built here rather than inherited"):
        require_sale_deposit(ctx)
        company = acting_company(ctx)
        sweep_fg06(ctx)
        account = deposit_accounts_for_test(ctx, CUSTOMER_SIDE,
                                            company["id"], wanted=1)[0]
        fixture = _part_paid_invoice(ctx, company, account, "DEP-011")
        created["res.partner"].append(fixture["partner_id"])
        created["product.product"].append(fixture["product_id"])
        created["sale.order"].append(fixture["order_id"])
        # The workbook's step 5 needs "ANY other posted unpaid invoice for the
        # same customer", so one is built up front rather than found.
        other_invoice_id = make_invoice(
            ctx, fixture["partner_id"],
            [(fixture["product_id"], 1, other_invoice_total)], post=True)
        ctx.log(f"second invoice for the same customer: "
                f"#{other_invoice_id} at {other_invoice_total:.2f}")

    try:
        with ctx.step("Step 1: confirm the starting state — 7,000.00 due with "
                      "the deposit applied"):
            before = invoice_totals(ctx, fixture["invoice_id"])
            ctx.check("Amount Due before the reset", REMAINING,
                      before["amount_residual"])
            ctx.check_true(
                "The deposit is applied, not merely available",
                not _is_offered(ctx, fixture["invoice_id"],
                                fixture["deposit_id"]),
                actual_desc="the deposit is not offered in Outstanding "
                            "credits, i.e. it is applied")

        with ctx.step("Steps 2-3 / Expected line 1: Reset to Draft returns "
                      "the invoice to Draft"):
            reset_error = ""
            try:
                rpc.call("account.move", "button_draft",
                         [fixture["invoice_id"]])
            except OdooRPCError as exc:
                reset_error = str(exc)
            ctx.check_true(
                "Reset to Draft on the invoice raised no error (BC-017 and "
                "DW-001 regression guards: the override reaches the payment "
                "through origin_payment_id, and its intermediate-entry lookup "
                "is parameterised SQL guarded against an empty line set)",
                not reset_error, actual_desc=reset_error or "no error")
            after_reset = invoice_totals(ctx, fixture["invoice_id"])
            ctx.log(f"after Reset to Draft — invoice state="
                    f"{after_reset['state']!r} payment_state="
                    f"{after_reset['payment_state']!r}")
            ctx.check("The invoice returns to Draft", "draft",
                      after_reset["state"])

        with ctx.step("Step 4 / Expected line 2: the deposit is still there "
                      "and is not cancelled or deleted"):
            deposit = payment_row(ctx, fixture["deposit_id"])
            ctx.log(f"deposit {deposit['name']} — state={deposit['state']!r} "
                    f"entry={deposit['move_state']!r} "
                    f"amount={deposit['amount']:.2f} "
                    f"intermediate entries={deposit['deposit_ids']}")
            # The workbook's If It Fails: "If the deposit cannot be found at
            # all after resetting the invoice, that is a P0."
            ctx.check_true(
                "The deposit still exists",
                bool(deposit["id"]) and deposit["amount"] == DEPOSIT,
                actual_desc=f"deposit #{deposit['id']} at "
                            f"{deposit['amount']:.2f}")
            ctx.check_true(
                "…and is not cancelled",
                deposit["state"] != "canceled",
                actual_desc=f"account.payment.state = {deposit['state']!r} "
                            f"(v19 spells the cancelled value 'canceled')")
            ctx.check("…and its journal entry is still posted", "posted",
                      deposit["move_state"])
            # The intermediate 'Deposit to Payment' entry should have been
            # cleaned up by button_draft, which is what frees the deposit
            # (account_partner_deposit/models/account_move.py:100-120).
            ctx.check("The intermediate 'Deposit to Payment' entry was "
                      "removed, which is what frees the deposit", [],
                      deposit["deposit_ids"])

        with ctx.step("Steps 5-6 / Expected line 3: the 3,000.00 deposit is "
                      "offered again on another invoice — it is not stranded"):
            entries = outstanding_credits(ctx, other_invoice_id)
            ctx.log(f"Outstanding credits on invoice #{other_invoice_id}: "
                    f"{[(e['payment_id'], e['amount']) for e in entries]}")
            mine = [e for e in entries
                    if e["payment_id"] == fixture["deposit_id"]]
            ctx.check("The freed deposit is offered on another invoice for "
                      "the same customer", 1, len(mine))
            ctx.check("…for the full 3,000.00", DEPOSIT, mine[0]["amount"])

        with ctx.step("Step 7 / Expected line 4: re-confirming the first "
                      "invoice shows the full 10,000.00 due"):
            rpc.call("account.move", "action_post", [fixture["invoice_id"]])
            reconfirmed = invoice_totals(ctx, fixture["invoice_id"])
            ctx.log(f"after re-Confirm — invoice state="
                    f"{reconfirmed['state']!r} Amount Due="
                    f"{reconfirmed['amount_residual']:.2f} "
                    f"payment_state={reconfirmed['payment_state']!r}")
            ctx.check("The invoice is posted again", "posted",
                      reconfirmed["state"])
            # NOTE: posting an invoice raised from an order re-runs
            # sale_partner_deposit's automatic application
            # (models/account_move.py:7-17), so the deposit may be re-applied
            # by the act of re-confirming. Both outcomes are consistent; what
            # must never happen is applied-and-available at once, which is
            # asserted below.
            offered_now = _is_offered(ctx, fixture["invoice_id"],
                                      fixture["deposit_id"])
            if reconfirmed["amount_residual"] == REMAINING:
                ctx.log(
                    "NOTE — re-confirming the invoice re-applied the deposit "
                    "automatically, so Amount Due reads 7,000.00 rather than "
                    "the workbook's 10,000.00. That is "
                    "sale_partner_deposit.account_move.action_post running "
                    "again on an invoice raised from the order "
                    "(models/account_move.py:7-17), not a stranded or "
                    "double-counted deposit: the deposit is applied and is "
                    "NOT also offered, which is asserted next. The workbook's "
                    "10,000.00 assumes the manual path, where nothing "
                    "re-applies on its own.")
                ctx.check_true(
                    "The re-applied deposit is applied and NOT also "
                    "available (no double count)", not offered_now,
                    actual_desc=f"Amount Due="
                                f"{reconfirmed['amount_residual']:.2f}, "
                                f"offered={offered_now}")
            else:
                ctx.check("Amount Due after re-confirming, with the deposit "
                          "no longer applied to it", ORDER_TOTAL,
                          reconfirmed["amount_residual"])
                ctx.check_true(
                    "…and the deposit is still available rather than "
                    "stranded", offered_now,
                    actual_desc=f"offered in Outstanding credits="
                                f"{offered_now}")
    finally:
        with ctx.step("Cleanup: remove FG06 fixtures (the workbook's State "
                      "After The Test is 'An invoice back in Posted with its "
                      "full amount due, and a deposit available again')"):
            for key in ("account.move", "account.payment"):
                if created.get(key):
                    created[key] = []
            cleanup(ctx, created)
