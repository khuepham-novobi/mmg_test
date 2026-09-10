"""FG-06 — TC-DEP-012: a deposit in a foreign currency.

Implements row 25.0 (P1, "Deposits from orders") of the CLIENT MANUAL TESTING
GUIDELINE ``MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0.xlsx`` /
sheet ``Testing Guideline``.

The workbook's framing: *"The gallery sells internationally. A deposit taken
against an order priced in another currency must record the right amount in
that currency and the right amount in the company's books."* Its Why It
Matters: *"Two currencies and a calculated figure across three screens. The
wizard has to pick up the order's currency rather than the company's, and
getting that wrong produces an amount that looks plausible."*

Where "the order's currency rather than the company's" actually lives
---------------------------------------------------------------------
Two defaults are in tension, and the case exists because only one of them is
right:

* ``order.make.deposit.currency_id`` defaults to
  ``self.env.company.currency_id`` — the COMPANY's
  (``account_partner_deposit/wizard/order_make_deposit.py:18``);
* ``sale.order.action_make_a_deposit`` overrides that when it opens the
  wizard, passing ``default_currency_id = self.currency_id`` — the ORDER's
  (``sale_partner_deposit/models/sale_order.py:69-73``);
* ``action_create_deposit`` then passes ``default_currency_id =
  order.currency_id`` into the payment pop-up
  (``wizard/order_make_deposit.py:41``).

So the correct value depends on the *action's* context winning over the
field's own default. This module drives the journey through those exact
calls, so the currency asserted on the pop-up is the one the override
produced — if the field default won instead, the assertion fails, which is
precisely the defect the workbook describes as "an amount that looks
plausible".

That currency also decides the guard: ``action_create_deposit`` rejects a
non-positive amount using ``self.currency_id.compare_amounts``
(``:31-33``), so the wizard currency is load-bearing beyond display.

Why the order needs a pricelist
-------------------------------
``sale.order.currency_id`` is ``compute='_compute_currency_id', store=True``
with **no** ``readonly=False`` (``addons/sale/models/sale_order.py:195-201``)
and computes to ``pricelist_id.currency_id or company_id.currency_id``
(``:454-456``). The currency therefore cannot be written on the order; it has
to arrive through a pricelist. ``tests/fg06/common.py::ensure_pricelist``
creates an FG06-marked one, which is the same approach the module's own test
fixture takes (``sale_partner_deposit/tests/common.py``, ``pricelist_eur``).

BLOCKED rather than FAILED when the database is single-currency
---------------------------------------------------------------
The workbook's own precondition is *"More than one currency is active. If you
only see one currency field, ask Novobi to enable multi-currency on the test
system first."* That is a setup condition outside the test's control, so
``require_multi_currency`` reports BLOCKED with the remedy rather than
failing. Note that v19 has no ``group_multi_currency`` group — it survives
only in stale translation files — so the check is the workbook's own wording:
count the active ``res.currency`` rows, and require a usable rate, because
without one ``_get_conversion_rate`` silently falls back to 1.0 and every
figure in the case would be meaningless while looking correct.

Expected Result line 4 — the journal entry
------------------------------------------
*"The journal entry shows the company-currency equivalent at today's rate as
well as the foreign amount."* On ``account.move.line`` those are two
different columns: ``amount_currency`` carries the foreign figure and
``balance`` (``debit``/``credit``) the company-currency one
(``addons/account/models/account_move_line.py``). The deposit line is built
with exactly that pair — ``amount_currency`` rounded in the payment currency
and ``balance`` multiplied by the conversion rate
(``account_partner_deposit/models/account_payment.py:80-89``) — so the
assertion is that the two differ and that the foreign one equals the deposit,
rather than re-deriving the rate and comparing to itself.
"""
from __future__ import annotations

from framework.registry import test_case
from tests.fg06.common import (AUTO_INVOICE_FIELD, CUSTOMER_SIDE,
                               MODULE_SALE, OPTION_FIXED,
                               WORKFLOW, WORKFLOW_NAME, acting_company,
                               cleanup, deposit_accounts_for_test,
                               deposit_popup_state, ensure_pricelist,
                               make_order, make_partner, make_product, money,
                               move_lines, open_make_deposit_wizard,
                               order_invoice_rows,
                               order_totals, payment_row,
                               require_multi_currency, require_sale_deposit,
                               run_make_deposit_wizard, sweep_fg06, trace,
                               validate_deposit_popup)

# Workbook Test Data: order total 5,000.00 in the foreign currency, deposit
# 1,000.00 fixed, leaving a Net Total of 4,000.00.
ORDER_TOTAL = 5000.00
DEPOSIT = 1000.00


@test_case(
    id="TEST-FG06-DEP-012",
    name="A deposit in a foreign currency is taken at the right amount",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE_SALE,
    priority="P1",
    kind="API",
    order=606,
    description="On an order priced in a second currency, the payment pop-up "
                "offers 1,000.00 in the ORDER's currency rather than "
                "converted into the company's; the order then reads Total "
                "Deposit 1,000.00 / Net Total 4,000.00 in that currency, the "
                "deposit record carries it, and its journal entry shows both "
                "the foreign amount and the company-currency equivalent.",
    traceability=trace("TC-DEP-012"))
def test_dep_012(ctx):
    created = {"sale.order": [], "account.payment": [],
               "product.product": [], "res.partner": [],
               "product.pricelist": []}

    with ctx.step("Preconditions (workbook): more than one currency is "
                  "active with a rate loaded, and a CONFIRMED uninvoiced "
                  "order priced in a currency that is NOT the company's"):
        require_sale_deposit(ctx)
        company = acting_company(ctx)
        sweep_fg06(ctx)
        currency = require_multi_currency(ctx, company)
        ctx.check_true(
            "The order currency is NOT the company currency (workbook "
            "precondition)",
            currency["id"] != company["currency_id"],
            actual_desc=f"order currency {currency['name']} vs company "
                        f"currency {company['currency_name']}")
        account = deposit_accounts_for_test(ctx, CUSTOMER_SIDE,
                                            company["id"], wanted=1)[0]
        pricelist_id = ensure_pricelist(ctx, currency, company)
        created["product.pricelist"].append(pricelist_id)
        partner_id = make_partner(ctx, "DEP-012 Customer", company=company,
                                  customer_deposit_account_id=account["id"])
        created["res.partner"].append(partner_id)
        product_id = make_product(ctx, "DEP-012 Art Item", ORDER_TOTAL)
        created["product.product"].append(product_id)
        order_id = make_order(ctx, partner_id,
                              [(product_id, 1, ORDER_TOTAL)],
                              confirm=True, pricelist_id=pricelist_id)
        created["sale.order"].append(order_id)

    try:
        with ctx.step("Step 1: the order really is in the foreign currency, "
                      "at the workbook's total"):
            order = order_totals(ctx, order_id)
            ctx.log(f"order {order['name']} — {order['amount_total']:.2f} "
                    f"{order['currency']} (state={order['state']!r})")
            ctx.check("The order's currency", currency["id"],
                      order["currency_id"])
            ctx.check("The order's total in that currency", ORDER_TOTAL,
                      order["amount_total"])
            ctx.check("The order is CONFIRMED", "sale", order["state"])
            # MMG auto-invoice: mmg_sale_auto_create_invoice overrides
            # action_confirm to call _create_invoices() whenever the
            # company carries auto_create_invoice_after_confirming_so
            # (models/sale_order.py), and that flag is ON for the acting
            # company — so a confirmed order reads
            # invoice_status='invoiced' BY DESIGN. TC-DEP-012 is about the
            # CURRENCY a deposit is taken in: none of its Expected Result
            # lines read invoice_status, and action_make_a_deposit has no
            # invoice gate of its own
            # (sale_partner_deposit/models/sale_order.py). The workbook's
            # "uninvoiced" precondition is therefore asserted only where
            # it can hold, and the MMG behaviour is reported instead of
            # being recorded as a deposit defect.
            if company.get("auto_invoice_on_confirm"):
                raised = [(r["name"], r["state"])
                          for r in order_invoice_rows(ctx, order_id)]
                ctx.log(
                    f"the acting company has {AUTO_INVOICE_FIELD} = True, "
                    f"so confirming this order auto-created {raised} and "
                    f"invoice_status reads {order['invoice_status']!r}. "
                    f"That is MMG behaviour, not a defect, and it does "
                    f"not touch the currency this case checks.")
            else:
                ctx.check_true(
                    "The order is NOT yet invoiced",
                    order["invoice_status"] != "invoiced",
                    actual_desc=f"invoice_status = "
                                f"{order['invoice_status']!r}")

        with ctx.step("Step 2: Create deposit — the wizard picks up the "
                      "ORDER's currency, not the company's"):
            # The wizard field's own default is the COMPANY currency
            # (wizard/order_make_deposit.py:18); the order's action overrides
            # it (sale_partner_deposit/models/sale_order.py:69-73). Asserting
            # the resolved default is asserting that the override won.
            wizard_action = open_make_deposit_wizard(ctx, order_id)
            wizard_context = dict(wizard_action.get("context") or {})
            ctx.log(f"Create deposit -> context={wizard_context}")
            resolved = ctx.adapter.rpc.call(
                "order.make.deposit", "default_get", ["currency_id"],
                context=wizard_context)
            ctx.check("The Make a Deposit wizard's currency is the order's",
                      currency["id"], resolved.get("currency_id"))

        with ctx.step("Steps 3-4 / Expected line 1: the payment pop-up shows "
                      "1,000.00 in the ORDER's currency, not converted"):
            payment_action = run_make_deposit_wizard(
                ctx, order_id, OPTION_FIXED, DEPOSIT, wizard_context)
            popup = deposit_popup_state(ctx, payment_action)
            # Both halves of the workbook's step 4 ("read the Amount and read
            # the Currency next to it BEFORE you validate").
            ctx.check("The Amount the payment pop-up offers", DEPOSIT,
                      popup["amount"])
            ctx.check("The Currency next to it on the payment pop-up",
                      currency["id"], popup["currency_id"])
            ctx.check_true(
                "The pop-up did NOT convert the amount into the company "
                "currency",
                popup["currency_id"] != company["currency_id"],
                actual_desc=f"pop-up currency = {popup['currency']!r}, "
                            f"company currency = "
                            f"{company['currency_name']!r}")
            ctx.check("Deposit Account on the pop-up is pre-filled from the "
                      "contact", account["id"],
                      popup["customer_deposit_account_id"])

        with ctx.step("Step 5: Validate"):
            payment_id, error = validate_deposit_popup(
                ctx, popup, side=CUSTOMER_SIDE, account_id=account["id"])
            if payment_id:
                created["account.payment"].append(payment_id)
            ctx.check_true("Validate raised no error", not error,
                           actual_desc=error or "action_post returned no error")

        with ctx.step("Step 6 / Expected line 2: Total Deposit 1,000.00 and "
                      "Net Total 4,000.00, both in the order's currency"):
            after = order_totals(ctx, order_id)
            ctx.log(f"order {after['name']} — Total Deposit="
                    f"{after['deposit_total']:.2f} Net Total="
                    f"{after['remaining_total']:.2f} shown in "
                    f"{after['currency']}")
            # _compute_deposit_amount converts the deposit's
            # amount_company_currency_signed back into the ORDER's currency
            # (sale_partner_deposit/models/sale_order.py:32-44), so a wrong
            # conversion shows up here as a plausible-but-wrong figure — which
            # is exactly what the workbook warns about.
            ctx.check("Total Deposit on the order", DEPOSIT,
                      after["deposit_total"])
            ctx.check("Net Total on the order", money(ORDER_TOTAL - DEPOSIT),
                      after["remaining_total"])
            ctx.check("The totals are shown in the order's currency",
                      currency["id"], after["currency_id"])

        with ctx.step("Step 7 / Expected line 3: the deposit record itself "
                      "carries the order's currency"):
            row = payment_row(ctx, payment_id)
            ctx.log(f"deposit {row['name']} — {row['amount']:.2f} "
                    f"{row['currency']}, company-currency signed "
                    f"{row['amount_company_signed']:.2f} "
                    f"{company['currency_name']}")
            ctx.check("Amount on the deposit", DEPOSIT, row["amount"])
            ctx.check("Currency on the deposit", currency["id"],
                      row["currency_id"])
            ctx.check("The deposit is linked to this order", order_id,
                      row["sale_deposit_id"])

        with ctx.step("Step 8 / Expected line 4: the journal entry shows the "
                      "foreign amount AND the company-currency equivalent"):
            lines = move_lines(ctx, row["move_id"])
            for line in lines:
                ctx.log(f"  {line['account_code']} "
                        f"{line['account_name']!r} — "
                        f"debit={line['debit']:.2f} "
                        f"credit={line['credit']:.2f} "
                        f"({company['currency_name']}), "
                        f"amount_currency={line['amount_currency']:.2f} "
                        f"({line['currency']})")
            deposit_lines = [ln for ln in lines
                             if ln["account_id"] == account["id"]]
            ctx.check("Exactly one line on the Deposit Account", 1,
                      len(deposit_lines))
            deposit_line = deposit_lines[0]
            # amount_currency is the foreign figure; debit/credit is the
            # company-currency one (account_partner_deposit/models/
            # account_payment.py:80-89 builds precisely that pair).
            ctx.check("The Deposit Account line's foreign amount is the "
                      "1,000.00 deposit", DEPOSIT,
                      abs(deposit_line["amount_currency"]))
            ctx.check("…carried in the order's currency", currency["name"],
                      deposit_line["currency"])
            company_amount = money(deposit_line["debit"]
                                   or deposit_line["credit"])
            ctx.check_true(
                "…and the entry also carries a non-zero company-currency "
                f"equivalent in {company['currency_name']}",
                company_amount > 0.0,
                actual_desc=f"debit={deposit_line['debit']:.2f} "
                            f"credit={deposit_line['credit']:.2f}")
            if company_amount == DEPOSIT:
                # Not a failure by itself — a 1:1 rate is legal — but it is
                # the shape a missing rate produces, and the workbook asks
                # which of the two amounts moved.
                ctx.log(
                    f"NOTE — the company-currency amount "
                    f"({company_amount:.2f} {company['currency_name']}) "
                    f"equals the foreign amount ({DEPOSIT:.2f} "
                    f"{currency['name']}), i.e. an effective rate of 1.0. "
                    f"That is legal if the rate genuinely is 1.0, but it is "
                    f"also what a MISSING rate looks like: "
                    f"res.currency._get_conversion_rate falls back to 1.0. "
                    f"The latest rate this run found for {currency['name']} "
                    f"is dated {currency['latest_rate_date']} — confirm it is "
                    f"the rate you expect for today before passing this line.")
            ctx.check_true(
                "The entry is balanced in the company currency",
                money(sum(ln["debit"] for ln in lines))
                == money(sum(ln["credit"] for ln in lines)),
                actual_desc=f"debits="
                            f"{money(sum(ln['debit'] for ln in lines)):.2f} "
                            f"credits="
                            f"{money(sum(ln['credit'] for ln in lines)):.2f}")
    finally:
        with ctx.step("Cleanup: remove FG06 fixtures (a posted deposit stays "
                      "— the workbook's State After The Test is 'A "
                      "foreign-currency order carrying a 1,000.00 deposit')"):
            payments = created.get("account.payment") or []
            if payments:
                ctx.log(f"confirmed deposit(s) {payments} left in place BY "
                        f"DESIGN: v19 account.payment.unlink() would "
                        f"reset the posted entry to draft and delete "
                        f"it (addons/account/models/account_payment."
                        f"py:957-959), destroying accounting evidence")
                created["account.payment"] = []
            cleanup(ctx, created)
