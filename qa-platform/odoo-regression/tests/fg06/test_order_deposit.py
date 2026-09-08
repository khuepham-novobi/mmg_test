"""FG-06 — taking deposits against a sales order.

Implements three rows of the CLIENT MANUAL TESTING GUIDELINE
``MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0.xlsx`` / sheet
``Testing Guideline``:

* **TC-DEP-004** (row 19.0, P0, "Deposits from orders") — "Take a
  fixed-amount deposit against a sales order". The everyday gallery
  transaction, done from the order rather than from the accounting screens.
* **TC-DEP-005** (row 20.0, P0) — "Take a deposit as a percentage of the
  order", including the zero-amount guard.
* **TC-DEP-016** (row 27.0, P1) — "Several deposits on one order add up
  correctly", including the question of what a percentage is taken *on*.

How the four screens of the workbook's journey are driven
---------------------------------------------------------
The workbook's steps cross the sales order, a wizard, a payment pop-up and
back to the order. Each is driven through the same call the button makes, so
that what is asserted is what a tester sees:

1. **Create deposit** on the order -> ``sale.order.action_make_a_deposit``,
   which returns the ``order.make.deposit`` act_window with
   ``default_currency_id`` set to the ORDER's currency
   (``sale_partner_deposit/models/sale_order.py:69-73``).
2. The **Make a Deposit** pop-up -> ``order.make.deposit`` created with
   ``deposit_option`` and ``amount``, then ``action_create_deposit``
   (``account_partner_deposit/wizard/order_make_deposit.py:22-63``).
   ``percentage`` is ``related='amount'`` and the view shows one input or the
   other, so writing ``amount`` is what typing in either box does
   (``wizard/order_make_deposit.py:15-16``,
   ``wizard/order_make_deposit_views.xml:12-17``).
3. The **payment pop-up** -> the act_window that call returns. Its context
   carries the pop-up's initial values, and
   ``tests/fg06/common.py::deposit_popup_state`` runs ``onchange``'s
   first call over that context, which is exactly how the form fills itself
   in. **This is what makes "read the Amount before you validate" a real
   assertion** rather than a re-derivation: the figure asserted is the one
   the pop-up would display.
4. **Validate** -> ``action_post``, which is the footer button's own method
   (``views/account_payment_deposit_view.xml:134-136``).

Where the workbook's expectation meets a v19 behaviour worth naming
-------------------------------------------------------------------
**TC-DEP-005's caption.** The workbook says explicitly that the caption above
the input still reads "Deposit amount" even when *By percentage* is chosen,
that this is cosmetic, and that it must NOT be raised. That is DW-005: the
two fields shared one label, which raises an ``ir_model`` warning at install,
so the port relabelled ``percentage`` to "Deposit percentage" while leaving
it a ``related='amount'`` alias — "splitting it into two real fields is a
wizard redesign, not a port" (``account_partner_deposit/PORTING.md`` §3). The
label is therefore recorded as evidence and deliberately not asserted either
way, exactly as instructed.

**TC-DEP-016's percentage base.** The workbook does not assert which base is
correct — it says the percentage is taken on the ORDER total, then adds "Note
which you see; Novobi needs to know", and its If It Fails says to report both
figures and "let Novobi decide which is intended — do not assume it is a
defect". The code takes it on ``order.amount_total``
(``wizard/order_make_deposit.py:44``), i.e. the full order, not the remaining
balance. This module asserts the workbook's stated expectation (the order
total) and, when the observed figure matches the remaining balance instead,
logs both numbers and the source line so the report Novobi asked for is in
the evidence either way.

Documented adaptation — no cross-test fixtures
----------------------------------------------
The workbook chains these cases onto one another (TC-DEP-005's precondition
is "TC-DEP-004 has passed"; TC-DEP-016's is the same). ``AUTOMATION_CONVENTIONS``
rule 5 forbids depending on another test's records, so each test builds its
own order at the total the workbook's Test Data names — 10,000.00 for
TC-DEP-004, 8,000.00 for TC-DEP-005, 12,000.00 for TC-DEP-016 — and the
comparisons are the workbook's unchanged.
"""
from __future__ import annotations

from adapters.base import OdooRPCError
from framework.registry import test_case
from tests.fg06.common import (CUSTOMER_SIDE, MODULE_SALE, OPTION_FIXED,
                               OPTION_PERCENTAGE, WORKFLOW, WORKFLOW_NAME,
                               acting_company, cleanup, deposit_popup_state,
                               deposit_accounts_for_test, make_order,
                               make_partner, make_product, money,
                               open_make_deposit_wizard, order_totals,
                               payment_row, require_sale_deposit,
                               run_make_deposit_wizard, sweep_fg06, trace,
                               validate_deposit_popup)

# The Create deposit button and the Deposits smart button, from
# sale_partner_deposit/views/sale_order_views.xml:9-20.
CREATE_DEPOSIT_METHOD = "action_make_a_deposit"
VIEW_DEPOSIT_METHOD = "action_view_deposit"


def _build_order(ctx, company, account, label: str, total: float) -> tuple:
    """A confirmed, uninvoiced FG06 order at exactly ``total``."""
    partner_id = make_partner(ctx, f"{label} Customer", company=company,
                              customer_deposit_account_id=account["id"])
    product_id = make_product(ctx, f"{label} Art Item", total)
    order_id = make_order(ctx, partner_id, [(product_id, 1, total)],
                          confirm=True)
    return partner_id, product_id, order_id


def _require_confirmed_uninvoiced(ctx, order_id: int, total: float) -> dict:
    """Assert the workbook's own precondition on the order it will use.

    All three of these hide the Create deposit button by design
    (``invisible="invoice_status == 'invoiced' or state != 'sale'"`` plus
    ``groups="account.group_account_invoice"``,
    ``sale_partner_deposit/views/sale_order_views.xml:9-13``), and the
    workbook's If It Fails names all three as the first things to check.
    """
    order = order_totals(ctx, order_id)
    ctx.check("The order is CONFIRMED (state 'sale'), as the workbook "
              "precondition requires", "sale", order["state"])
    ctx.check_true(
        "The order is NOT yet invoiced (invoice_status != 'invoiced')",
        order["invoice_status"] != "invoiced",
        actual_desc=f"invoice_status = {order['invoice_status']!r}")
    ctx.check("The order total matches the workbook's Test Data", total,
              order["amount_total"])
    return order


def _take_deposit(ctx, order_id: int, option: str, amount: float,
                  *, account_id=None) -> dict:
    """One full Create deposit -> Validate journey, as a tester performs it.

    Returns the pop-up's initial state, the created payment id and any error
    the guard raised, so the caller asserts on the figure the pop-up OFFERED
    as well as on the outcome.
    """
    wizard_action = open_make_deposit_wizard(ctx, order_id)
    ctx.log(f"Create deposit -> {wizard_action.get('res_model')!r} "
            f"context={wizard_action.get('context')}")
    payment_action = run_make_deposit_wizard(
        ctx, order_id, option, amount,
        dict(wizard_action.get("context") or {}))
    ctx.log(f"Create deposit (wizard) -> {payment_action.get('res_model')!r} "
            f"name={payment_action.get('name')!r}")
    state = deposit_popup_state(ctx, payment_action)
    payment_id, error = validate_deposit_popup(
        ctx, state, side=CUSTOMER_SIDE, account_id=account_id)
    return {"wizard_action": wizard_action, "payment_action": payment_action,
            "popup": state, "payment_id": payment_id, "error": error}


@test_case(
    id="TEST-FG06-DEP-004",
    name="Take a fixed-amount deposit against a sales order",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE_SALE,
    priority="P0",
    kind="API",
    order=604,
    description="Create deposit is available on a confirmed uninvoiced "
                "order, the wizard offers both fixed and percentage, the "
                "payment pop-up opens with a read-only Customer and a "
                "pre-filled Deposit Account, and after Validate the order "
                "reads Total Deposit 3,000.00 / Net Total 7,000.00 with a "
                "Deposits button showing 1.",
    traceability=trace("TC-DEP-004"))
def test_dep_004(ctx):
    rpc = ctx.adapter.rpc
    created = {"sale.order": [], "account.payment": [],
               "product.product": [], "res.partner": []}
    order_total, deposit = 10000.00, 3000.00

    with ctx.step("Preconditions (workbook): TC-DEP-003 has passed; a "
                  "CONFIRMED, uninvoiced order for a customer with a Customer "
                  "Deposit Account; the Invoicing group"):
        require_sale_deposit(ctx)
        company = acting_company(ctx)
        sweep_fg06(ctx)
        account = deposit_accounts_for_test(ctx, CUSTOMER_SIDE,
                                            company["id"], wanted=1)[0]
        partner_id, product_id, order_id = _build_order(
            ctx, company, account, "DEP-004", order_total)
        created["res.partner"].append(partner_id)
        created["product.product"].append(product_id)
        created["sale.order"].append(order_id)
        _require_confirmed_uninvoiced(ctx, order_id, order_total)

    try:
        with ctx.step("Step 2 / Expected line 1: Create deposit is present "
                      "on a confirmed, uninvoiced order"):
            # The button's method existing and returning the wizard IS the
            # button being present; its visibility expression is asserted
            # from the arch as well, because a method that works behind a
            # hidden button is still a failure for the tester.
            arch = rpc.call("sale.order", "get_view",
                            view_type="form")["arch"]
            ctx.check_true(
                "The order form carries a Create deposit button "
                f"(name=\"{CREATE_DEPOSIT_METHOD}\")",
                f'name="{CREATE_DEPOSIT_METHOD}"' in arch
                and "Create deposit" in arch,
                actual_desc=f"{CREATE_DEPOSIT_METHOD} in arch: "
                            f"{f'name=\"{CREATE_DEPOSIT_METHOD}\"' in arch}")
            action = open_make_deposit_wizard(ctx, order_id)
            ctx.check("Create deposit opens the Make a Deposit wizard",
                      "order.make.deposit", action.get("res_model"))

        with ctx.step("Step 3 / Expected line 2: the pop-up offers By fixed "
                      "amount and By percentage, and opens on fixed"):
            options = rpc.call("order.make.deposit", "fields_get",
                               ["deposit_option"],
                               attributes=["selection"])["deposit_option"]
            ctx.check("The Make a Deposit options",
                      [(OPTION_FIXED, "By fixed amount"),
                       (OPTION_PERCENTAGE, "By percentage")],
                      [tuple(item) for item in options["selection"]])
            default = rpc.call("order.make.deposit", "default_get",
                               ["deposit_option"],
                               context=dict(action.get("context") or {}))
            ctx.check("The pop-up opens with the choice on By fixed amount "
                      "(the workbook says 'leave the choice on')",
                      OPTION_FIXED, default.get("deposit_option"))

        with ctx.step("Steps 4-7 / Expected line 3: the payment pop-up shows "
                      "a read-only Customer and a pre-filled Deposit Account"):
            result = _take_deposit(ctx, order_id, OPTION_FIXED, deposit,
                                   account_id=account["id"])
            popup = result["popup"]
            if result["payment_id"]:
                created["account.payment"].append(result["payment_id"])
            ctx.check_true(
                "Validate raised no error",
                not result["error"],
                actual_desc=result["error"] or "action_post returned no error")
            ctx.check("The payment pop-up is filled in with the order's "
                      "customer", partner_id, popup["partner_id"])
            ctx.check("Deposit Account on the pop-up is pre-filled from the "
                      "contact", account["id"],
                      popup["customer_deposit_account_id"])
            ctx.check("The pop-up's Amount is the 3,000.00 that was typed",
                      deposit, popup["amount"])
            # "the Customer is filled in and cannot be changed" — the
            # from-order form forces partner_id readonly
            # (views/account_payment_deposit_view.xml:143-148).
            popup_view_id = rpc.ref("account_partner_deposit."
                                    "account_payment_deposit_from_order_form_view")
            ctx.check_true(
                "The from-order payment pop-up exists as its own view",
                bool(popup_view_id),
                actual_desc=f"view id {popup_view_id!r}")
            popup_arch = rpc.call("account.payment", "get_view",
                                  view_id=popup_view_id,
                                  view_type="form")["arch"]
            ctx.check_true(
                "Customer is read-only on the payment pop-up",
                'name="partner_id"' in popup_arch
                and 'readonly="1"' in popup_arch,
                actual_desc="partner_id readonly=\"1\" present in the "
                            "from-order arch: "
                            f"{'readonly=\"1\"' in popup_arch}")

        with ctx.step("Steps 8-9 / Expected line 4: Total Deposit 3,000.00 "
                      "and Net Total 7,000.00 on the order"):
            after = order_totals(ctx, order_id)
            ctx.log(f"order {after['name']} — total="
                    f"{after['amount_total']:.2f} "
                    f"Total Deposit={after['deposit_total']:.2f} "
                    f"Net Total={after['remaining_total']:.2f} "
                    f"Deposits button={after['deposit_count']}")
            ctx.check("Total Deposit on the order", deposit,
                      after["deposit_total"])
            ctx.check("Net Total on the order", money(order_total - deposit),
                      after["remaining_total"])

        with ctx.step("Step 10 / Expected line 5: the Deposits button appears "
                      "showing 1"):
            ctx.check("Deposits button count", 1, after["deposit_count"])
            # deposit_ids is gated on BOTH the payment state and the entry
            # state (BC-002 + BC-016,
            # sale_partner_deposit/models/sale_order.py:20-24), so a count of
            # 1 here also proves the deposit's entry actually posted.
            row = payment_row(ctx, result["payment_id"])
            ctx.check("The counted deposit's journal entry is posted (so the "
                      "count is money received, not money merely recorded)",
                      "posted", row["move_state"])
            ctx.check("The deposit is linked to this order", order_id,
                      row["sale_deposit_id"])
    finally:
        with ctx.step("Cleanup: remove FG06 fixtures"):
            _release_posted(ctx, created)
            cleanup(ctx, created)


@test_case(
    id="TEST-FG06-DEP-005",
    name="Take a deposit as a percentage of the order",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE_SALE,
    priority="P0",
    kind="API",
    order=605,
    description="25 per cent of an 8,000.00 order is offered as 2,000.00 on "
                "the payment pop-up, the order then reads Total Deposit "
                "2,000.00 / Net Total 6,000.00, and a 0 per cent attempt is "
                "refused with 'Deposit amount must be greater than 0'.",
    traceability=trace("TC-DEP-005"))
def test_dep_005(ctx):
    created = {"sale.order": [], "account.payment": [],
               "product.product": [], "res.partner": []}
    order_total, percentage, expected = 8000.00, 25.0, 2000.00

    with ctx.step("Preconditions (workbook): TC-DEP-004 has passed; a second "
                  "CONFIRMED, uninvoiced order whose total makes the "
                  "percentage easy to check"):
        require_sale_deposit(ctx)
        company = acting_company(ctx)
        sweep_fg06(ctx)
        account = deposit_accounts_for_test(ctx, CUSTOMER_SIDE,
                                            company["id"], wanted=1)[0]
        partner_id, product_id, order_id = _build_order(
            ctx, company, account, "DEP-005", order_total)
        created["res.partner"].append(partner_id)
        created["product.product"].append(product_id)
        created["sale.order"].append(order_id)
        _require_confirmed_uninvoiced(ctx, order_id, order_total)

    try:
        with ctx.step("Steps 1-5 / Expected line 1: 25 per cent of 8,000.00 "
                      "is offered as 2,000.00, calculated for you"):
            result = _take_deposit(ctx, order_id, OPTION_PERCENTAGE,
                                   percentage, account_id=account["id"])
            popup = result["popup"]
            if result["payment_id"]:
                created["account.payment"].append(result["payment_id"])
            # This is the figure the workbook asks the tester to read BEFORE
            # validating, and it is read from the pop-up's own initial state.
            ctx.check("The Amount the payment pop-up offers for 25 per cent "
                      "of 8,000.00", expected, popup["amount"])
            ctx.check_true(
                "Validate raised no error",
                not result["error"],
                actual_desc=result["error"] or "action_post returned no error")

        with ctx.step("Steps 6-7 / Expected line 2: Total Deposit 2,000.00 "
                      "and Net Total 6,000.00"):
            after = order_totals(ctx, order_id)
            ctx.log(f"order {after['name']} — Total Deposit="
                    f"{after['deposit_total']:.2f} Net Total="
                    f"{after['remaining_total']:.2f}")
            ctx.check("Total Deposit on the order", expected,
                      after["deposit_total"])
            ctx.check("Net Total on the order", money(order_total - expected),
                      after["remaining_total"])

        with ctx.step("Step 8 / Expected line 3: 0 per cent is refused, with "
                      "a message that the amount must be greater than zero"):
            # wizard/order_make_deposit.py:31-33 raises before it converts the
            # percentage, so the guard is on the number typed.
            error = ""
            try:
                _take_deposit(ctx, order_id, OPTION_PERCENTAGE, 0.0,
                              account_id=account["id"])
            except OdooRPCError as exc:
                error = str(exc)
            ctx.log(f"0 per cent attempt -> {error!r}")
            ctx.check_true(
                "A zero deposit is refused",
                bool(error),
                actual_desc=error or "the wizard accepted a zero deposit and "
                                     "created a payment")
            ctx.check_true(
                "…with a readable message saying the amount must be greater "
                "than zero",
                "greater than 0" in error or "greater than zero" in error,
                actual_desc=error)

        with ctx.step("Expected line 4 (workbook: NOT a defect): the caption "
                      "above the percentage input"):
            # The workbook says the caption still reading "Deposit amount" is
            # cosmetic and must NOT be raised. DW-005 relabelled `percentage`
            # while keeping it a related='amount' alias
            # (account_partner_deposit/PORTING.md §3), so the label is
            # recorded as evidence and deliberately not asserted either way.
            labels = ctx.adapter.rpc.call(
                "order.make.deposit", "fields_get", ["amount", "percentage"],
                attributes=["string", "related"])
            ctx.log(f"wizard field labels — amount: "
                    f"{labels.get('amount', {}).get('string')!r}, "
                    f"percentage: "
                    f"{labels.get('percentage', {}).get('string')!r} "
                    f"(percentage is still an alias of amount). The workbook "
                    f"says a caption reading 'Deposit amount' over the "
                    f"percentage input is COSMETIC and must NOT be raised as "
                    f"a defect — recorded here as an observation, not "
                    f"asserted.")
            ctx.check("The order still shows the 2,000.00 deposit after the "
                      "refused attempt (nothing was created by it)",
                      expected, order_totals(ctx, order_id)["deposit_total"])
    finally:
        with ctx.step("Cleanup: remove FG06 fixtures"):
            _release_posted(ctx, created)
            cleanup(ctx, created)


@test_case(
    id="TEST-FG06-DEP-016",
    name="Several deposits on one order add up correctly",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE_SALE,
    priority="P1",
    kind="API",
    order=607,
    description="Three deposits on a 12,000.00 order — 2,000.00 fixed, "
                "3,000.00 fixed, then 25 per cent — produce a running Total "
                "Deposit of 2,000 / 5,000 / 8,000 and a Net Total of 10,000 / "
                "7,000 / 4,000, with the percentage taken on the order total "
                "and the Deposits button showing 3.",
    traceability=trace("TC-DEP-016"))
def test_dep_016(ctx):
    created = {"sale.order": [], "account.payment": [],
               "product.product": [], "res.partner": []}
    order_total = 12000.00
    first, second, percentage = 2000.00, 3000.00, 25.0
    # Expected line 3: 25 per cent of the ORDER total, not of the remaining
    # 7,000.00 (wizard/order_make_deposit.py:44 reads order.amount_total).
    on_order_total = money(order_total * percentage / 100)      # 3,000.00
    on_remaining = money((order_total - first - second)
                         * percentage / 100)                    # 1,750.00

    with ctx.step("Preconditions (workbook): TC-DEP-004 has passed; a "
                  "CONFIRMED, uninvoiced order with a total of 12,000.00"):
        require_sale_deposit(ctx)
        company = acting_company(ctx)
        sweep_fg06(ctx)
        account = deposit_accounts_for_test(ctx, CUSTOMER_SIDE,
                                            company["id"], wanted=1)[0]
        partner_id, product_id, order_id = _build_order(
            ctx, company, account, "DEP-016", order_total)
        created["res.partner"].append(partner_id)
        created["product.product"].append(product_id)
        created["sale.order"].append(order_id)
        _require_confirmed_uninvoiced(ctx, order_id, order_total)

    try:
        running = 0.0
        for index, (option, typed, label) in enumerate(
                ((OPTION_FIXED, first, "2,000.00 by fixed amount"),
                 (OPTION_FIXED, second, "3,000.00 by fixed amount")), start=1):
            with ctx.step(f"Steps {index * 2 - 1}-{index * 2} / Expected "
                          f"lines 1-2: deposit {index} — {label}"):
                result = _take_deposit(ctx, order_id, option, typed,
                                       account_id=account["id"])
                if result["payment_id"]:
                    created["account.payment"].append(result["payment_id"])
                ctx.check_true(
                    f"Validate raised no error on deposit {index}",
                    not result["error"],
                    actual_desc=result["error"] or "no error")
                running = money(running + typed)
                after = order_totals(ctx, order_id)
                ctx.log(f"after deposit {index} — Total Deposit="
                        f"{after['deposit_total']:.2f} Net Total="
                        f"{after['remaining_total']:.2f} "
                        f"count={after['deposit_count']}")
                ctx.check(f"Total Deposit after deposit {index}", running,
                          after["deposit_total"])
                ctx.check(f"Net Total after deposit {index}",
                          money(order_total - running),
                          after["remaining_total"])

        with ctx.step("Step 5 / Expected line 3: the third deposit's 25 per "
                      "cent is taken on the ORDER total of 12,000.00"):
            wizard_action = open_make_deposit_wizard(ctx, order_id)
            payment_action = run_make_deposit_wizard(
                ctx, order_id, OPTION_PERCENTAGE, percentage,
                dict(wizard_action.get("context") or {}))
            popup = deposit_popup_state(ctx, payment_action)
            offered = popup["amount"]
            # The workbook asks for BOTH figures to be reported, whichever is
            # seen, and says not to assume a difference is a defect.
            ctx.log(f"25 per cent offered as {offered:.2f}. On the ORDER "
                    f"total of {order_total:.2f} that is "
                    f"{on_order_total:.2f}; on the remaining balance of "
                    f"{money(order_total - running):.2f} it would be "
                    f"{on_remaining:.2f}. The code reads order.amount_total "
                    f"(account_partner_deposit/wizard/order_make_deposit.py:"
                    f"44), so the order total is the intended base.")
            if offered == on_remaining and offered != on_order_total:
                ctx.log(
                    f"FINDING for Novobi (workbook Step 5 note and If It "
                    f"Fails): the percentage was taken on the REMAINING "
                    f"balance, offering {offered:.2f}, not on the order total, "
                    f"which would be {on_order_total:.2f}. The workbook says "
                    f"to report both figures and let Novobi decide which is "
                    f"intended rather than assuming a defect.")
            ctx.check("The Amount offered for 25 per cent, taken on the order "
                      "total", on_order_total, offered)
            payment_id, error = validate_deposit_popup(
                ctx, popup, side=CUSTOMER_SIDE, account_id=account["id"])
            if payment_id:
                created["account.payment"].append(payment_id)
            ctx.check_true("Validate raised no error on deposit 3",
                           not error, actual_desc=error or "no error")

        with ctx.step("Step 6 / Expected line 4: Total Deposit 8,000.00 and "
                      "Net Total 4,000.00"):
            running = money(running + on_order_total)
            after = order_totals(ctx, order_id)
            ctx.check("Total Deposit after deposit 3", running,
                      after["deposit_total"])
            ctx.check("Net Total after deposit 3",
                      money(order_total - running), after["remaining_total"])

        with ctx.step("Step 7 / Expected line 5: the Deposits button shows 3 "
                      "and lists all three"):
            ctx.check("Deposits button count", 3,
                      order_totals(ctx, order_id)["deposit_count"])
            action = ctx.adapter.rpc.call("sale.order", VIEW_DEPOSIT_METHOD,
                                          [order_id]) or {}
            listed = _deposits_in_action(ctx, action, order_id)
            ctx.check("The Deposits button lists exactly this order's three "
                      "deposits",
                      sorted(created["account.payment"]), sorted(listed))
    finally:
        with ctx.step("Cleanup: remove FG06 fixtures"):
            _release_posted(ctx, created)
            cleanup(ctx, created)


# ------------------------------------------------------------------ helpers
def _deposits_in_action(ctx, action: dict, order_id: int) -> list:
    """The deposits the Deposits smart button actually opens.

    ``action_view_deposit`` returns a LIST filtered to the order's deposits
    when there is more than one, and a single FORM with ``res_id`` when there
    is exactly one (``sale_partner_deposit/models/sale_order.py:55-67``) —
    which is the behavioural split TC-DEP-006 checks and this case relies on.
    """
    if action.get("res_id"):
        return [action["res_id"]]
    domain = action.get("domain") or []
    if isinstance(domain, str):
        try:
            import ast
            domain = ast.literal_eval(domain)
        except (ValueError, SyntaxError):
            ctx.log(f"the Deposits action domain {domain!r} is not a plain "
                    f"literal — falling back to the order's deposit_ids")
            return order_totals(ctx, order_id)["deposit_ids"]
    return ctx.adapter.rpc.search("account.payment", list(domain))


def _release_posted(ctx, created: dict):
    """Drop ids that cannot be unlinked, so cleanup logs stay meaningful.

    A posted payment and its entry cannot be deleted, and a confirmed sales
    order cannot be unlinked either — ``sweep_fg06`` cancels FG06 orders
    first for exactly that reason. Handing a posted id to ``cleanup()`` only
    produces a logged refusal, so the ids are filtered here and named in the
    log instead.
    """
    rpc = ctx.adapter.rpc
    payments = created.get("account.payment") or []
    if not payments:
        return
    try:
        posted = rpc.search("account.payment",
                            [("id", "in", payments),
                             ("move_id.state", "=", "posted")])
    except OdooRPCError as exc:
        ctx.log(f"[cleanup] could not classify deposits {payments} ({exc}) — "
                f"handing them to cleanup as-is")
        return
    if posted:
        ctx.log(f"confirmed deposit(s) {posted} left in place: a posted "
                f"payment cannot be unlinked, and the workbook's State After "
                f"The Test expects the order to keep carrying them")
        created["account.payment"] = [p for p in payments
                                      if p not in set(posted)]
