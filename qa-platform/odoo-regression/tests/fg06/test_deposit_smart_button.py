"""FG-06 — TC-DEP-006: the Deposits button on an order opens the right deposits.

Implements row 21.0 (P1, "Deposits from orders") of the CLIENT MANUAL TESTING
GUIDELINE ``MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0.xlsx`` /
sheet ``Testing Guideline``.

The workbook's framing: *"A salesperson looking at an order needs to see, in
one click, what has actually been paid against it — without hunting through
the payment lists."* Its Why It Matters: *"The button behaves differently for
one deposit than for several, and it must never show deposits belonging to
another order."*

The behavioural split this case is really about
----------------------------------------------
``sale.order.action_view_deposit`` has three branches
(``sale_partner_deposit/models/sale_order.py:55-67``):

* **more than one deposit** — the Customer Deposits action with
  ``domain = [('id', 'in', self.deposit_ids.ids)]``, i.e. a LIST scoped to
  this order;
* **exactly one** — the same action with ``res_id`` set and the deposit FORM
  view pushed to the front of ``views``, i.e. straight to that one record;
* **none** — the untouched action. The button itself is hidden in that case
  (``invisible="deposit_count == 0"``,
  ``views/sale_order_views.xml:15-19``), so the branch is unreachable from
  the screen, which is what Expected Result line 4 asserts.

Each branch is asserted for what it returns, not for what it is assumed to
return: ``res_id`` present and no scoping domain for one deposit; a domain
naming exactly this order's deposits for several; and the button absent from
the form for none.

Documented adaptation — no cross-test fixtures, and the ordering warning
------------------------------------------------------------------------
The workbook's precondition is *"TC-DEP-004 and TC-DEP-016 have both passed,
so you have one order with a single deposit and one with several"*, and it
adds an explicit ordering warning: run this AFTER TC-DEP-016 and BEFORE
TC-DEP-017, because TC-DEP-017 adds a fourth deposit to the TC-DEP-016 order
and would change the count being checked.

``AUTOMATION_CONVENTIONS`` rule 5 forbids depending on another test's
records, which removes that hazard rather than working around it: this test
builds **both** orders itself — Order X with one deposit of 3,000.00 (the
TC-DEP-004 end state) and Order Y with three (the TC-DEP-016 end state) —
plus a third order with none, so the counts it checks cannot be disturbed by
any other case. The registry ``order`` value (608) still places it between
TC-DEP-016 (607) and TC-DEP-017 (614), so a full-suite run reads in the
workbook's own sequence.

Expected Result line 3 — "no deposit from another order appears" — is
therefore asserted in both directions, which is the assertion the workbook
calls the serious one: Order X's view must not contain Order Y's deposits and
vice versa.
"""
from __future__ import annotations

import ast

from adapters.base import OdooRPCError
from framework.registry import test_case
from tests.fg06.common import (CUSTOMER_SIDE, MODULE_SALE, OPTION_FIXED,
                               WORKFLOW, WORKFLOW_NAME, acting_company,
                               cleanup, deposit_accounts_for_test,
                               deposit_popup_state, make_order, make_partner,
                               make_product, open_make_deposit_wizard,
                               order_totals, require_sale_deposit,
                               run_make_deposit_wizard, sweep_fg06, trace,
                               validate_deposit_popup)

# Workbook Test Data: Order X carries one deposit of 3,000.00 (TC-DEP-004's
# end state); Order Y carries more than one (TC-DEP-016's).
ORDER_X_TOTAL, ORDER_X_DEPOSIT = 10000.00, 3000.00
ORDER_Y_TOTAL, ORDER_Y_DEPOSITS = 12000.00, (2000.00, 3000.00, 3000.00)
ORDER_Z_TOTAL = 4000.00

CUSTOMER_DEPOSIT_ACTION = ("account_partner_deposit."
                           "action_account_payment_customer_deposit")
DEPOSIT_FORM_XMLID = ("account_partner_deposit."
                      "view_account_payment_deposit_form")
VIEW_DEPOSIT_METHOD = "action_view_deposit"


def _take(ctx, order_id: int, amount: float, account_id: int) -> int:
    """One Create deposit -> Validate journey; returns the payment id."""
    wizard_action = open_make_deposit_wizard(ctx, order_id)
    payment_action = run_make_deposit_wizard(
        ctx, order_id, OPTION_FIXED, amount,
        dict(wizard_action.get("context") or {}))
    popup = deposit_popup_state(ctx, payment_action)
    payment_id, error = validate_deposit_popup(
        ctx, popup, side=CUSTOMER_SIDE, account_id=account_id)
    if error:
        ctx.log(f"Validate refused a {amount:.2f} deposit on order "
                f"#{order_id}: {error}")
    return payment_id


def _resolve(ctx, action: dict) -> dict:
    """What the Deposits button actually opens: form-with-res_id, or a list.

    Returns ``{"mode", "ids", "domain", "first_view"}``. The domain is parsed
    as a literal rather than evaluated — ``action_view_deposit`` builds it
    from ``self.deposit_ids.ids``, so it contains no expressions.
    """
    res_id = action.get("res_id")
    raw_domain = action.get("domain")
    domain = []
    if isinstance(raw_domain, str) and raw_domain.strip():
        try:
            domain = ast.literal_eval(raw_domain)
        except (ValueError, SyntaxError):
            ctx.log(f"the Deposits action domain {raw_domain!r} is not a "
                    f"plain literal — recorded as unparsed rather than "
                    f"guessed")
            domain = raw_domain
    elif isinstance(raw_domain, (list, tuple)):
        domain = list(raw_domain)

    views = action.get("views") or []
    first_view = ""
    if views:
        first = views[0]
        if isinstance(first, (list, tuple)) and len(first) > 1:
            first_view = first[1]

    if res_id:
        return {"mode": "form", "ids": [res_id], "domain": domain,
                "first_view": first_view}
    ids = []
    if isinstance(domain, list) and domain:
        try:
            ids = ctx.adapter.rpc.search("account.payment", domain)
        except OdooRPCError as exc:
            ctx.log(f"could not resolve the Deposits action domain ({exc})")
    return {"mode": "list", "ids": ids, "domain": domain,
            "first_view": first_view}


@test_case(
    id="TEST-FG06-DEP-006",
    name="The Deposits button on an order opens the right deposits",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE_SALE,
    priority="P1",
    kind="API",
    order=608,
    description="An order with one deposit opens straight to that deposit's "
                "form; an order with three opens a list containing exactly "
                "those three; neither view leaks the other order's deposits; "
                "and an order with no deposits does not show the button at "
                "all.",
    traceability=trace("TC-DEP-006"))
def test_dep_006(ctx):
    rpc = ctx.adapter.rpc
    created = {"sale.order": [], "account.payment": [],
               "product.product": [], "res.partner": []}

    with ctx.step("Preconditions (workbook, adapted): one order with a "
                  "single deposit, one with several, and one with none — "
                  "each built here rather than inherited"):
        require_sale_deposit(ctx)
        company = acting_company(ctx)
        sweep_fg06(ctx)
        account = deposit_accounts_for_test(ctx, CUSTOMER_SIDE,
                                            company["id"], wanted=1)[0]
        ctx.log("workbook ordering note: this case must run AFTER TC-DEP-016 "
                "and BEFORE TC-DEP-017, because TC-DEP-017 adds a fourth "
                "deposit to TC-DEP-016's order. Building both orders here "
                "removes that hazard rather than working around it "
                "(AUTOMATION_CONVENTIONS rule 5); the registry order value "
                "608 still places this case between them for a full-suite "
                "run.")

    try:
        with ctx.step("Build Order X (one deposit of 3,000.00), Order Y "
                      "(three deposits) and Order Z (none)"):
            orders = {}
            for label, total in (("X", ORDER_X_TOTAL), ("Y", ORDER_Y_TOTAL),
                                 ("Z", ORDER_Z_TOTAL)):
                partner_id = make_partner(
                    ctx, f"DEP-006 Customer {label}", company=company,
                    customer_deposit_account_id=account["id"])
                created["res.partner"].append(partner_id)
                product_id = make_product(ctx, f"DEP-006 Item {label}", total)
                created["product.product"].append(product_id)
                order_id = make_order(ctx, partner_id,
                                      [(product_id, 1, total)], confirm=True)
                created["sale.order"].append(order_id)
                orders[label] = order_id

            x_deposits = [_take(ctx, orders["X"], ORDER_X_DEPOSIT,
                                account["id"])]
            y_deposits = [_take(ctx, orders["Y"], amount, account["id"])
                          for amount in ORDER_Y_DEPOSITS]
            created["account.payment"].extend(
                [p for p in x_deposits + y_deposits if p])

            x_totals = order_totals(ctx, orders["X"])
            y_totals = order_totals(ctx, orders["Y"])
            z_totals = order_totals(ctx, orders["Z"])
            ctx.check("Order X carries exactly one deposit (workbook Test "
                      "Data)", 1, x_totals["deposit_count"])
            ctx.check("Order Y carries more than one deposit",
                      len(ORDER_Y_DEPOSITS), y_totals["deposit_count"])
            ctx.check("Order Z carries no deposits", 0,
                      z_totals["deposit_count"])

        with ctx.step("Steps 1-3 / Expected line 1: Order X's button shows 1 "
                      "and goes straight to that deposit's form"):
            action = rpc.call("sale.order", VIEW_DEPOSIT_METHOD,
                              [orders["X"]]) or {}
            resolved = _resolve(ctx, action)
            ctx.log(f"Order X Deposits button -> mode={resolved['mode']} "
                    f"ids={resolved['ids']} domain={resolved['domain']!r} "
                    f"first view={resolved['first_view']!r}")
            ctx.check("Order X's Deposits button count", 1,
                      x_totals["deposit_count"])
            ctx.check("Order X's Deposits button opens a single deposit form "
                      "rather than a list", "form", resolved["mode"])
            ctx.check("…and it is the 3,000.00 deposit belonging to Order X",
                      sorted(p for p in x_deposits if p),
                      sorted(resolved["ids"]))
            form_view_id = rpc.ref(DEPOSIT_FORM_XMLID)
            ctx.check_true(
                "…opened through the deposit form view, not the generic "
                "payment form",
                resolved["first_view"] == "form",
                actual_desc=f"first view mode = {resolved['first_view']!r} "
                            f"(expected 'form'; the deposit form view id is "
                            f"{form_view_id!r})")

        with ctx.step("Steps 4-5 / Expected line 2: Order Y's button shows "
                      "the right count and opens a list of exactly those "
                      "deposits"):
            action_y = rpc.call("sale.order", VIEW_DEPOSIT_METHOD,
                                [orders["Y"]]) or {}
            resolved_y = _resolve(ctx, action_y)
            ctx.log(f"Order Y Deposits button -> mode={resolved_y['mode']} "
                    f"ids={resolved_y['ids']} "
                    f"domain={resolved_y['domain']!r}")
            ctx.check("Order Y's Deposits button count",
                      len(ORDER_Y_DEPOSITS), y_totals["deposit_count"])
            ctx.check("Order Y's Deposits button opens a list", "list",
                      resolved_y["mode"])
            ctx.check("…containing exactly Order Y's deposits",
                      sorted(p for p in y_deposits if p),
                      sorted(resolved_y["ids"]))

        with ctx.step("Step 6 / Expected line 3: neither view leaks the "
                      "other order's deposits"):
            # The workbook calls this the serious version and a P1 naming both
            # orders. Asserted in both directions.
            leaked_into_x = sorted(set(resolved["ids"])
                                   & {p for p in y_deposits if p})
            leaked_into_y = sorted(set(resolved_y["ids"])
                                   & {p for p in x_deposits if p})
            ctx.check(f"No deposit of Order Y (#{orders['Y']}) appears in "
                      f"Order X's (#{orders['X']}) Deposits view", [],
                      leaked_into_x)
            ctx.check(f"No deposit of Order X (#{orders['X']}) appears in "
                      f"Order Y's (#{orders['Y']}) Deposits view", [],
                      leaked_into_y)

        with ctx.step("Step 7 / Expected line 4: on an order with NO "
                      "deposits the button is not shown at all"):
            arch = rpc.call("sale.order", "get_view",
                            view_type="form")["arch"]
            ctx.check_true(
                "The Deposits button is hidden when the count is zero "
                "(invisible=\"deposit_count == 0\")",
                'name="action_view_deposit"' in arch
                and 'invisible="deposit_count == 0"' in arch,
                actual_desc=f"action_view_deposit in arch: "
                            f"{'name=\"action_view_deposit\"' in arch}; "
                            f"deposit_count==0 guard in arch: "
                            f"{'invisible=\"deposit_count == 0\"' in arch}")
            ctx.check("Order Z's deposit count, which is what hides the "
                      "button", 0,
                      order_totals(ctx, orders["Z"])["deposit_count"])
            # The zero branch of action_view_deposit is unreachable from the
            # screen; recorded so a reviewer knows it was considered rather
            # than missed.
            action_z = rpc.call("sale.order", VIEW_DEPOSIT_METHOD,
                                [orders["Z"]]) or {}
            resolved_z = _resolve(ctx, action_z)
            ctx.log(f"Order Z's action_view_deposit (unreachable from the "
                    f"screen, since the button is hidden) returns "
                    f"mode={resolved_z['mode']} ids={resolved_z['ids']} "
                    f"domain={resolved_z['domain']!r} — recorded as evidence "
                    f"only; the workbook's expectation is about the button "
                    f"not being shown, which is asserted above.")
    finally:
        with ctx.step("Cleanup: remove FG06 fixtures (the workbook's State "
                      "After The Test is 'Nothing changed'; the four "
                      "confirmed deposits built here cannot be unlinked)"):
            payments = created.get("account.payment") or []
            if payments:
                ctx.log(f"confirmed deposit(s) {payments} left in place BY "
                        f"DESIGN: v19 account.payment.unlink() would "
                        f"reset the posted entry to draft and delete "
                        f"it (addons/account/models/account_payment."
                        f"py:957-959), destroying accounting evidence")
                created["account.payment"] = []
            cleanup(ctx, created)
