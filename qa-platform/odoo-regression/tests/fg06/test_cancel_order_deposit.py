"""FG-06 — TC-DEP-013: cancelling an order leaves the deposit as customer money.

Implements row 26.0 (P1, "Cancelling") of the CLIENT MANUAL TESTING GUIDELINE
``MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0.xlsx`` / sheet
``Testing Guideline``.

The workbook's framing: *"Sales fall through. When an order is cancelled the
deposit does not vanish — the gallery is still holding the customer's money
and must be able to apply it elsewhere or refund it."*

READ THIS FIRST — the workbook has already been corrected once here
-------------------------------------------------------------------
This case's Why It Matters says: *"The old test for this said the deposit
liability would be reversed. It never did that, in the old system or the new
one. What actually happens is that the deposit detaches from the order and
stays on the customer's account. Test the real behaviour described below, not
the old expectation."*

The port's own record goes one step further, and this module implements what
the code does rather than either earlier expectation. From
``sale_partner_deposit/PORTING.md`` §4:

* **v15** overrode ``sale_order.action_cancel`` to run
  ``order.deposit_ids = [(5, 0, 0)]``, detaching the deposits. That is where
  the workbook's "detaches from the order" wording comes from, and it is the
  basis of decision **D5-a**.
* **The 18.0 branch this port came from removed that override entirely**, and
  ships a test asserting the opposite — ``test_cancel_so_having_deposits``,
  docstringed *"Test cancel so having deposits will not remove links to
  deposits on SO"*. So v19 inherits: **cancelling a sales order leaves its
  deposits attached.**
* PORTING.md therefore flags D5-a as *"⚠ Premise no longer holds — needs
  re-taking"* and states that TC-DEP-013 *"needs rewriting again"*.

The workbook is consistent with this. Its own Expected Result closes with:
*"Note: the deposit may still show as attached to the cancelled order. That
is the agreed behaviour and is NOT a defect"*, and its If It Fails says *"If
it merely stayed linked to the cancelled order, that is expected: pass the
case and note it."* Read Me change item 9 says the same. So the attachment is
recorded as an observation and deliberately **not** asserted in either
direction — asserting "still attached" would pin behaviour the client has not
yet decided on, and asserting "detached" would fail working code.

What IS asserted is the whole substance of the case, which is unaffected by
that open decision:

1. the order cancels;
2. the deposit still **exists** and is still **confirmed** — not cancelled,
   not reversed, not deleted. The workbook's If It Fails calls a reversed or
   removed deposit "the gallery losing track of customer money";
3. the deposit is offered in Outstanding credits on a **new** invoice for the
   same customer and applies normally;
4. a 1,500.00 invoice is left fully paid with 500.00 of the 2,000.00 deposit
   still unused.

Point 2 is also the closure of the **CB-001** data-loss question. The
instruction was to verify what ``(5, 0, 0)`` does on v19 and report it as a
defect if it unlinks rather than detaches. It does neither, because nothing
calls it any more — so the risk is verified away here rather than merely
documented (``sale_partner_deposit/PORTING.md`` §4, point 1).

Documented adaptation — no cross-test fixtures
----------------------------------------------
The workbook's precondition is "TC-DEP-005 has passed, so an order exists
with a 2,000.00 deposit and no invoice yet".
``AUTOMATION_CONVENTIONS`` rule 5 forbids depending on another test's
records, so this case builds the same starting state itself: an 8,000.00
order carrying a 2,000.00 deposit, taken as 25 per cent exactly as TC-DEP-005
does, with no invoice raised.
"""
from __future__ import annotations

from adapters.base import OdooRPCError
from framework.registry import test_case
from tests.fg06.common import (CUSTOMER_SIDE, MODULE_SALE, OPTION_PERCENTAGE,
                               PAYMENT_LIVE_STATES, PAYMENT_STATE_PAID,
                               WORKFLOW, WORKFLOW_NAME, acting_company,
                               apply_outstanding_credit, cleanup,
                               deposit_accounts_for_test, deposit_popup_state,
                               invoice_totals, make_invoice, make_order,
                               make_partner, make_product, money,
                               open_make_deposit_wizard, order_totals,
                               outstanding_credits, payment_row,
                               require_sale_deposit, run_make_deposit_wizard,
                               sweep_fg06, trace, validate_deposit_popup)

# Workbook Test Data: the TC-DEP-005 order — total 8,000.00, deposit 2,000.00
# taken as 25 per cent. Then a new invoice of 1,500.00, leaving 500.00 of the
# deposit unused.
ORDER_TOTAL, PERCENTAGE, DEPOSIT = 8000.00, 25.0, 2000.00
NEW_INVOICE = 1500.00
UNUSED = money(DEPOSIT - NEW_INVOICE)


@test_case(
    id="TEST-FG06-DEP-013",
    name="Cancelling an order leaves the deposit as money on the customer's "
         "account",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE_SALE,
    priority="P1",
    kind="API",
    order=613,
    description="After an order carrying a 2,000.00 deposit is cancelled, the "
                "deposit still exists and is still confirmed — not reversed, "
                "cancelled or deleted — and it is offered on a new 1,500.00 "
                "invoice for the same customer, applying normally and leaving "
                "that invoice fully paid with 500.00 unused. Whether the "
                "deposit stays attached to the cancelled order is recorded as "
                "an observation, per the workbook.",
    traceability=trace("TC-DEP-013"))
def test_dep_013(ctx):
    rpc = ctx.adapter.rpc
    created = {"account.move": [], "sale.order": [], "account.payment": [],
               "product.product": [], "res.partner": []}

    with ctx.step("Preconditions (workbook, adapted): an 8,000.00 order "
                  "carrying a 2,000.00 deposit and no invoice yet, built "
                  "here rather than inherited"):
        require_sale_deposit(ctx)
        company = acting_company(ctx)
        sweep_fg06(ctx)
        account = deposit_accounts_for_test(ctx, CUSTOMER_SIDE,
                                            company["id"], wanted=1)[0]
        partner_id = make_partner(ctx, "DEP-013 Customer", company=company,
                                  customer_deposit_account_id=account["id"])
        created["res.partner"].append(partner_id)
        product_id = make_product(ctx, "DEP-013 Art Item", ORDER_TOTAL)
        created["product.product"].append(product_id)
        order_id = make_order(ctx, partner_id, [(product_id, 1, ORDER_TOTAL)],
                              confirm=True)
        created["sale.order"].append(order_id)

        wizard_action = open_make_deposit_wizard(ctx, order_id)
        payment_action = run_make_deposit_wizard(
            ctx, order_id, OPTION_PERCENTAGE, PERCENTAGE,
            dict(wizard_action.get("context") or {}))
        popup = deposit_popup_state(ctx, payment_action)
        ctx.check("The deposit taken is 25 per cent of 8,000.00", DEPOSIT,
                  popup["amount"])
        deposit_id, error = validate_deposit_popup(
            ctx, popup, side=CUSTOMER_SIDE, account_id=account["id"])
        ctx.check_true("The 2,000.00 deposit was taken against the order",
                       bool(deposit_id) and not error,
                       actual_desc=error or f"deposit #{deposit_id}")
        starting = order_totals(ctx, order_id)
        ctx.check("The order has no invoice yet (workbook precondition)", [],
                  starting["invoice_ids"])

    try:
        with ctx.step("Step 1: Total Deposit reads 2,000.00 and the Deposits "
                      "button count is noted"):
            before = order_totals(ctx, order_id)
            ctx.log(f"BEFORE cancel — order {before['name']}: "
                    f"state={before['state']!r} Total Deposit="
                    f"{before['deposit_total']:.2f} Net Total="
                    f"{before['remaining_total']:.2f} Deposits button="
                    f"{before['deposit_count']}")
            ctx.check("Total Deposit before the cancellation", DEPOSIT,
                      before["deposit_total"])
            ctx.check("Deposits button count before the cancellation", 1,
                      before["deposit_count"])

        with ctx.step("Steps 2-3 / Expected line 1: the order cancels"):
            cancel_error = ""
            try:
                ctx.adapter.cancel_order([order_id])
            except OdooRPCError as exc:
                cancel_error = str(exc)
            ctx.check_true("Cancelling the order raised no error",
                           not cancel_error,
                           actual_desc=cancel_error or "no error")
            cancelled = order_totals(ctx, order_id)
            ctx.check("The order is cancelled", "cancel", cancelled["state"])

        with ctx.step("Step 4 / Expected note (workbook: NOT a defect): what "
                      "the order's totals block shows now"):
            # Deliberately recorded, not asserted — see the module docstring.
            # D5-a's premise no longer holds and the decision needs re-taking,
            # so pinning either shape here would be wrong.
            ctx.log(
                f"OBSERVATION — after cancellation the order shows Total "
                f"Deposit={cancelled['deposit_total']:.2f}, Net "
                f"Total={cancelled['remaining_total']:.2f}, Deposits button "
                f"count={cancelled['deposit_count']}. The workbook says the "
                f"deposit MAY still show as attached to the cancelled order "
                f"and that this is the agreed behaviour and NOT a defect "
                f"(Expected Result note, If It Fails, and Read Me change "
                f"item 9). The v15 module detached them with "
                f"order.deposit_ids = [(5, 0, 0)]; the 18.0 branch this port "
                f"came from REMOVED that override and ships a test asserting "
                f"they stay linked, so v19 keeps the link "
                f"(sale_partner_deposit/PORTING.md §4). Decision D5-a is "
                f"flagged there as needing to be re-taken, so this line is an "
                f"observation for that decision and is deliberately not "
                f"asserted in either direction.")

        with ctx.step("Step 5 / Expected line 2: the deposit still EXISTS and "
                      "is still confirmed — not cancelled, reversed or "
                      "deleted"):
            # This is the CB-001 data-loss question, closed by observation
            # rather than by documentation.
            surviving = rpc.search("account.payment",
                                   [("id", "=", deposit_id)])
            ctx.check("The deposit payment record survives the cancellation",
                      [deposit_id], surviving)
            deposit = payment_row(ctx, deposit_id)
            ctx.log(f"deposit {deposit['name']} — state={deposit['state']!r} "
                    f"entry={deposit['move_state']!r} "
                    f"amount={deposit['amount']:.2f} "
                    f"sale_deposit_id={deposit['sale_deposit_id']}")
            ctx.check("…for the full 2,000.00", DEPOSIT, deposit["amount"])
            # The workbook's If It Fails: a reversed or removed deposit is
            # "the gallery losing track of customer money".
            ctx.check_true(
                "The deposit is still confirmed, not cancelled (v19 spells "
                "the cancelled value 'canceled')",
                deposit["state"] in PAYMENT_LIVE_STATES,
                actual_desc=f"account.payment.state = "
                            f"{deposit['state']!r}")
            ctx.check("…and its journal entry is still posted, so the "
                      "liability was not reversed", "posted",
                      deposit["move_state"])
            lines = ctx.adapter.rpc.search(
                "account.move.line",
                [("move_id", "=", deposit["move_id"]),
                 ("account_id", "=", account["id"])])
            ctx.check("…and its deposit-account line still exists", 1,
                      len(lines))

        with ctx.step("Steps 6-7 / Expected line 3: the deposit is offered on "
                      "a new invoice for the same customer and applies "
                      "normally"):
            new_invoice_id = make_invoice(
                ctx, partner_id, [(product_id, 1, NEW_INVOICE)], post=True)
            entries = outstanding_credits(ctx, new_invoice_id)
            ctx.log(f"Outstanding credits on the new 1,500.00 invoice: "
                    f"{[(e['payment_id'], e['amount']) for e in entries]}")
            mine = [e for e in entries if e["payment_id"] == deposit_id]
            ctx.check("The deposit from the cancelled order is offered on the "
                      "new invoice — it is not stranded", 1, len(mine))
            ctx.check("…for the full 2,000.00, none of it used yet", DEPOSIT,
                      mine[0]["amount"])
            apply_outstanding_credit(ctx, new_invoice_id, mine[0]["line_id"])

        with ctx.step("Step 8 / Expected line 3 (b): the new invoice is fully "
                      "paid, with 500.00 of the deposit still unused"):
            after = invoice_totals(ctx, new_invoice_id)
            ctx.log(f"new invoice {after['name']} — total="
                    f"{after['amount_total']:.2f} Amount Due="
                    f"{after['amount_residual']:.2f} "
                    f"payment_state={after['payment_state']!r}")
            ctx.check("Amount Due on the new 1,500.00 invoice after applying "
                      "the deposit", 0.0, after["amount_residual"])
            ctx.check("…and its payment status is fully paid",
                      PAYMENT_STATE_PAID, after["payment_state"])
            # "leaving that invoice fully paid with 500.00 of the deposit
            # still unused" — read off the deposit line's residual, which is
            # what makes the remainder usable again.
            deposit_line = ctx.adapter.rpc.search_read(
                "account.move.line",
                [("move_id", "=", payment_row(ctx, deposit_id)["move_id"]),
                 ("account_id", "=", account["id"])],
                ["amount_residual", "reconciled"])
            residual = money(abs(deposit_line[0]["amount_residual"])) \
                if deposit_line else 0.0
            ctx.log(f"deposit line residual after the partial application: "
                    f"{residual:.2f} (reconciled="
                    f"{deposit_line[0]['reconciled'] if deposit_line else '?'})")
            ctx.check("500.00 of the 2,000.00 deposit is still unused",
                      UNUSED, residual)
    finally:
        with ctx.step("Cleanup: remove FG06 fixtures (the workbook's State "
                      "After The Test is 'A cancelled order, and a deposit of "
                      "which 1,500.00 has been applied to another invoice')"):
            for key in ("account.move", "account.payment"):
                if created.get(key):
                    created[key] = []
            cleanup(ctx, created)
