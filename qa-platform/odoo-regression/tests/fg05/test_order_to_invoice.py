"""FG-05 — order → invoice tax continuity and Avalara registration.

Implements two rows of the CLIENT MANUAL TESTING GUIDELINE
``MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0.xlsx`` / sheet
``Testing Guideline``:

* **TC-TAX-010** (row 8.0, P0) — "Tax carries from the order through to the
  invoice unchanged". A quotation carrying a computed Avalara tax figure is
  confirmed and invoiced through *Create Invoice > Regular invoice*; the
  invoice's Untaxed / Taxes / Total must equal the order's to the cent, the
  invoice must carry its own Avalara Code, and it must post without error.
* **TC-TAX-011** (row 9.0, P0) — "A posted invoice is registered at Avalara".
  A posted invoice must be committed at Avalara and a draft one must not.

Why the agreement in TC-TAX-010 is a real result, in v19 terms
--------------------------------------------------------------
The workbook's "Why It Matters" says the invoice *recalculates* tax rather
than copying it. In Odoo 19 that happens in two stages, and both were read
from source before writing this module:

1. ``sale.order.line._prepare_invoice_line`` (addons/sale/models/
   sale_order_line.py:1544-1547) copies ``tax_ids`` **and**
   ``extra_tax_data`` onto the invoice line, and
   ``account.external.tax.mixin._set_external_taxes`` stored Avalara's
   per-jurisdiction amounts in ``extra_tax_data['manual_tax_amounts']``.
   So the *draft* invoice shows the order's figures the moment it is
   created — which is exactly what workbook step 5 reads, straight after
   creation. ``account_external_tax/models/account_move.py`` only calls
   ``_get_and_set_external_taxes_on_eligible_records()`` from ``_post()``
   and from the *Compute Taxes* button, never from ``create()``, so this
   module asserts on the creation-time totals and does **not** press
   Compute Taxes first (pressing it would have replaced the very figures
   the workbook wants compared).
2. Posting then genuinely re-queries Avalara: ``_post()`` recomputes, MMG's
   ``account.move._check_avatax_tax_total`` refuses the move when the tax
   lines do not add up to Avalara's ``totalTax``, and
   ``account_avatax``'s own ``_post`` re-creates the transaction under the
   invoice name and commits it. "The invoice posts with no error" is
   therefore the point at which recalculation is proven — not a formality.

Documented adaptations (business assertions unchanged)
------------------------------------------------------
1. **No cross-test fixtures.** The workbook chains TC-TAX-010 onto
   TC-TAX-009's quotation and TC-TAX-011 onto TC-TAX-001's posted invoice.
   The platform forbids depending on another test's records, so each test
   builds its own equivalent starting state in-test — *equivalent* meaning
   the state the chain actually hands over, not a convenient one:

   * TC-TAX-010 says "use the quotation from TC-TAX-009 as-is; do not
     change its address or lines". TC-TAX-009 ends "the quotation now
     carries Address B and Montana tax", Address B being 100 N Higgins
     Ave, Missoula, MT 59802 — the deliberately no-state-sales-tax
     address — and that quotation is TC-TAX-008's, whose Test Data is
     "price 2,000.00, quantity 1". This test therefore builds **Missoula
     MT, one line, 2,000.00**. Montana legitimately computes to 0.00 tax,
     which is the point: the case is "whatever the order carries reaches
     the invoice unchanged", and a 0.00 that turns into a re-derived Odoo
     figure on the invoice is exactly the defect the chain is aimed at.
     The precondition that the figure is a *computed* one is asserted
     through the AvaTax routing flags instead of through "non-zero" (see
     step 2), because non-zero would fail the workbook's own scenario.
   * TC-TAX-011 continues from TC-TAX-001, whose Test Data is "any
     sandbox-safe US customer with a full address, sale price 1,000.00,
     quantity 1" — built here as Phoenix AZ, one line, 1,000.00.

   The comparisons themselves are identical to the workbook's.
2. **The Avalara ``commit`` flag is not observable from inside Odoo.**
   Nothing in this module asserts it, because there is nothing to assert
   against. ``_get_avatax_service_params()``, which builds that flag, is a
   private method and both of the platform's transports refuse those
   (``odoo/service/model.py::get_public_method`` — "Private methods (such
   as '%s.%s') cannot be called remotely"), so it can never be read over
   RPC. Nor is the outcome written back to the record: ``_change_avatax_
   state`` (account_avatax/models/account_external_tax_mixin.py:240-274)
   calls ``client.commit_transaction()`` / ``void_transaction()`` and
   stores no field on the move. Re-deriving the source expression
   ``self.state == 'posted' and avatax_company.avalara_commit``
   (account_avatax/models/account_move.py:53) from values this test has
   *already* asserted — the move's ``state`` and the company's
   ``avalara_commit`` — would be a tautology dressed as a check, not
   evidence. It is therefore recorded with ``ctx.log`` as the reason the
   portal lookup is required, and the Avalara portal is stated plainly as
   the only proof of commit state.
3. **TC-TAX-011's portal half is not reachable.** All three of its
   Expected Results are ultimately proven in the Avalara sandbox portal,
   which this platform has no access to. Everything provable in Odoo is
   asserted for real — the posted move reached ``posted`` state, both
   moves carry their own Avalara Code, the posted one carries a non-zero
   Taxes figure that MMG's ``_check_avatax_tax_total`` already reconciled
   against Avalara's ``totalTax`` before the post was allowed, and the
   second invoice is still draft. The residual is logged as a precise
   manual step with both Avalara Codes and both Taxes figures printed, so
   the human step is a lookup and never a re-run. The test is not
   BLOCKED — much of it is provable.
4. **Teardown vs. "leave both".** Both workbook rows say to leave the
   documents in place, and a move this module posts is therefore **never**
   handed to ``cleanup()``. That is not merely to honour the workbook's end
   state: a failed unlink of a posted AvaTax move is *not* a no-op. The
   outermost ``unlink`` override on ``account.move`` is
   ``account_external_tax/models/account_move.py:14-16``, which runs
   ``self._filtered_external_tax_moves()._void_external_taxes()`` **before**
   ``super().unlink()``. ``_filtered_external_tax_moves()`` (line 23-25)
   filters on ``is_tax_computed_externally and not _is_downpayment()`` with
   no state test, and ``account_avatax``'s
   ``_change_avatax_state('void')``
   (``account_avatax/models/account_external_tax_mixin.py:240-274``) has no
   state test either — it calls ``client.void_transaction()`` for every
   ``is_avatax`` record. ``super().unlink()`` then reaches
   ``account.move.line._unlink_except_posted``
   (``addons/account/models/account_move_line.py:1953-1960``) and raises,
   rolling back Odoo — but not the outbound HTTP void. The posted invoice
   would survive in Odoo with its Avalara transaction VOIDED, which would
   make TC-TAX-011's own printed manual step ("confirm it is PRESENT and
   COMMITTED") report a false P0. Posted ids are kept out of ``created``;
   ``sweep_fg05`` already scopes itself to draft/cancelled moves, and every
   other fixture is still cleaned up in ``finally``.
5. **TC-TAX-010's warehouse shipFrom is gated, not asserted.** The case starts
   on a quotation, and ``account_avatax_stock`` gives a sale order line a
   *line-level* ``shipFrom`` built from that line's warehouse address
   (``account_avatax_stock/models/sale_order.py:11`` ->
   ``…/account_external_tax_mixin.py:32-35``). A warehouse with no address does
   not fall back to the document-level address: the empty recordset satisfies
   the ``!= company.partner_id`` test, and
   ``account_avatax/models/account_external_tax_mixin.py:108-121`` then emits
   ``'country': False`` because its ``all(partner._fields[f] …)`` guard tests
   field descriptors instead of values. Avalara rejects the whole
   ``CreateTransaction`` and the order never receives the tax figure steps 5-6
   compare against, so :func:`~tests.fg05.common.require_warehouse_shipfrom`
   reports BLOCKED naming the warehouse, what is missing and the remedy,
   instead of the case ERRORing on Avalara's text. TC-TAX-011 does **not**
   call it: it builds stand-alone customer invoices, whose lines have no
   delivery moves, so ``account_avatax_stock/models/account_move.py:10-15``
   leaves their warehouse ``None`` and no line-level address is sent — which
   is why the invoice cases in this suite compute tax correctly today and must
   keep doing so.
"""
from __future__ import annotations

from adapters.base import OdooRPCError
from framework.registry import test_case
from tests.fg05.common import (ADDRESS_MISSOULA_MT, ADDRESS_PHOENIX_AZ, MODULE,
                               WORKFLOW, WORKFLOW_NAME, cleanup, compute_taxes,
                               doc_totals, make_invoice, make_partner,
                               make_product, make_quotation,
                               require_avatax_fiscal_position,
                               require_sandbox, require_warehouse_shipfrom,
                               sweep_fg05, trace)

# The wizard behind the sale order's "Create Invoice" button
# (addons/sale/views/sale_order_views.xml:272-279 opens
# sale.action_view_sale_advance_payment_inv). 'delivered' is the selection
# labelled "Regular invoice" — the workbook's step 4 choice — and
# SaleAdvancePaymentInv._create_invoices() delegates it straight to
# sale.order._create_invoices(). Driving the wizard rather than
# _create_invoices() directly keeps the test on the path the UI button
# actually runs, including its deduct_down_payments / consolidated_billing
# defaults.
ADVANCE_PAYMENT_WIZARD = "sale.advance.payment.inv"
REGULAR_INVOICE = "delivered"




def _avatax_commit_flag(state, company_commit):
    """The value ``_get_avatax_service_params()['commit']`` would carry.

    Source: account_avatax/models/account_move.py:53 —
    ``'commit': self.state == 'posted' and avatax_company and
    avatax_company.avalara_commit``. ``avatax_company`` is the company that
    holds the credentials (``_find_avatax_credentials_company``); on a
    single-company database that is the acting company, whose
    ``avalara_commit`` ``require_sandbox`` already read.
    """
    return bool(state == "posted" and company_commit)


def _probe_service_params_commit(ctx, move_id):
    """Try the real method first; return its ``commit`` or None.

    Kept as an honest probe rather than an assumption: if a future
    transport does expose it, the test uses the real value.
    """
    try:
        params = ctx.adapter.rpc.call(
            "account.move", "_get_avatax_service_params", [move_id])
    except OdooRPCError as exc:
        ctx.log(f"_get_avatax_service_params() is not reachable over the "
                f"platform's transport ({exc}) — private methods are refused "
                f"remotely (odoo/service/model.py:53). Falling back to the "
                f"source expression it evaluates.")
        return None
    if isinstance(params, dict) and "commit" in params:
        ctx.log(f"_get_avatax_service_params() returned commit="
                f"{params['commit']!r} over RPC")
        return bool(params["commit"])
    ctx.log(f"_get_avatax_service_params() returned {type(params).__name__} "
            f"without a usable 'commit' key — falling back to the source "
            f"expression it evaluates")
    return None


@test_case(
    id="TEST-FG05-TAX-010",
    name="Tax carries from the order through to the invoice unchanged",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P0",
    kind="API",
    order=507,
    description="Untaxed / Taxes / Total on the invoice created from a "
                "confirmed AvaTax order equal the order's to the cent; the "
                "invoice carries its own Avalara Code and posts with no error.",
    traceability=trace("TC-TAX-010"))
def test_tax_010(ctx):
    rpc = ctx.adapter.rpc
    created = {"account.move": [], "sale.order": [],
               "product.product": [], "res.partner": []}
    with ctx.step("Precondition: Odoo 19 with a usable Avalara SANDBOX and "
                  "an AvaTax fiscal position"):
        require_sandbox(ctx, "computing tax on a quotation and on the "
                             "invoice created from it")
        fp_id, fp = require_avatax_fiscal_position(ctx)
        ctx.log(f"AvaTax fiscal position #{fp_id} {fp.get('name')!r}")
        sweep_fg05(ctx)
    try:
        with ctx.step("Step 1 (workbook, adapted): build the quotation "
                      "TC-TAX-009 hands over — Missoula MT (Address B), one "
                      "line at 2,000.00 — and compute its tax"):
            # Adaptation 1: the workbook reuses TC-TAX-009's quotation ("use
            # it as-is, do not change its address or lines"); the platform
            # forbids depending on another test's fixtures, so the state the
            # chain leaves is rebuilt here: TC-TAX-009 ends on Address B =
            # 100 N Higgins Ave, Missoula, MT 59802, and the quotation is
            # TC-TAX-008's, whose Test Data is price 2,000.00 quantity 1.
            partner_id = make_partner(ctx, "TAX-010 Customer",
                                      ADDRESS_MISSOULA_MT,
                                      fiscal_position_id=fp_id)
            created["res.partner"].append(partner_id)
            product_id = make_product(ctx, "TAX-010 Item", 2000.00)
            created["product.product"].append(product_id)
            order_id = make_quotation(ctx, partner_id,
                                      [(product_id, 1, 2000.00)],
                                      fiscal_position_id=fp_id)
            created["sale.order"].append(order_id)
            # This case starts on a QUOTATION, so it carries the line-level
            # shipFrom that account_avatax_stock builds from the line's
            # warehouse. When that warehouse has no address, Avalara refuses
            # the whole document ("Unknown country name or code (FALSE)") and
            # the order never gets the tax figure steps 5-6 compare the
            # invoice against — so the case is BLOCKED with the warehouse
            # named, not left to ERROR on Avalara's text. See
            # tests/fg05/common.py::require_warehouse_shipfrom and
            # ODOO_SHIPFROM_DEFECT. The invoice half of this case inherits the
            # same warehouse through its delivery moves
            # (account_avatax_stock/models/account_move.py:10-15), so the gate
            # covers both halves.
            require_warehouse_shipfrom(
                ctx, order_id,
                "workbook steps 1-2 — computing the quotation's tax, which is "
                "the figure steps 5-6 compare the invoice against")
            compute_taxes(ctx, "sale.order", order_id)

        with ctx.step("Step 2 (workbook): write down the quotation's Untaxed "
                      "Amount, Taxes and Total"):
            order_totals = doc_totals(ctx, "sale.order", order_id)
            ctx.log(f"ORDER totals — Untaxed={order_totals['untaxed']:.2f} "
                    f"Taxes={order_totals['tax']:.2f} "
                    f"Total={order_totals['total']:.2f} "
                    f"Avalara Code={order_totals['avalara_code']!r}")
            # Workbook precondition: "TC-TAX-009 has passed. Its quotation
            # carries a computed tax figure." Under the chain that figure is
            # the MONTANA one, and Montana charges no state sales tax
            # (TC-TAX-009 Test Data says so in as many words), so 0.00 is the
            # correct value here — asserting non-zero would fail the
            # workbook's own scenario rather than test it. What must hold
            # instead is that the figure was computed EXTERNALLY at all:
            # is_tax_computed_externally (account_external_tax/models/
            # account_external_tax_mixin.py:18-19) is what routes a document
            # to Avalara, and account_avatax's
            # _compute_is_tax_computed_externally sets it from is_avatax,
            # which is fiscal_position_id.is_avatax. With either flag off the
            # document never reaches Avalara and the three comparisons below
            # WOULD be vacuous — this is the guard against that.
            flags = rpc.read("sale.order", [order_id],
                             ["is_avatax", "is_tax_computed_externally"])[0]
            ctx.check_true(
                "the quotation's tax figure is a computed Avalara one (it is "
                "on the AvaTax path)",
                bool(flags["is_avatax"])
                and bool(flags["is_tax_computed_externally"]),
                actual_desc=f"is_avatax={flags['is_avatax']!r} "
                            f"is_tax_computed_externally="
                            f"{flags['is_tax_computed_externally']!r}; order "
                            f"Taxes = {order_totals['tax']:.2f} on a Missoula "
                            f"MT address, which has no state sales tax")
            # TC-TAX-008/009 Expected Result: "Total equals Untaxed Amount
            # plus Taxes." The quotation the chain hands over must satisfy it
            # before TC-TAX-010 compares anything against it.
            ctx.check("quotation Total equals Untaxed Amount plus Taxes",
                      round(order_totals["untaxed"] + order_totals["tax"], 2),
                      order_totals["total"])

        with ctx.step("Step 3 (workbook): Confirm — the quotation becomes a "
                      "sales order"):
            rpc.call("sale.order", "action_confirm", [order_id])
            confirmed = doc_totals(ctx, "sale.order", order_id)
            ctx.check("quotation state after Confirm", "sale",
                      confirmed["state"])
            # sale_external_tax.action_confirm() recomputes external taxes
            # before confirming, so log what the order reads afterwards: the
            # workbook compares the invoice against the step-2 figures, and
            # this line makes any drift at confirmation visible in evidence.
            ctx.log(f"CONFIRMED ORDER totals — "
                    f"Untaxed={confirmed['untaxed']:.2f} "
                    f"Taxes={confirmed['tax']:.2f} "
                    f"Total={confirmed['total']:.2f}")

        with ctx.step("Step 4 (workbook): Create Invoice > Regular invoice"):
            wizard_id = rpc.create(ADVANCE_PAYMENT_WIZARD, {
                "sale_order_ids": [(6, 0, [order_id])],
                "advance_payment_method": REGULAR_INVOICE,
            })
            rpc.call(ADVANCE_PAYMENT_WIZARD, "create_invoices", [wizard_id])
            invoice_ids = rpc.read("sale.order", [order_id],
                                   ["invoice_ids"])[0]["invoice_ids"]
            ctx.check("invoices created by Create Invoice > Regular invoice",
                      1, len(invoice_ids))
            invoice_id = invoice_ids[0]
            created["account.move"].append(invoice_id)
            ctx.log(f"draft invoice #{invoice_id} from order #{order_id}")

        with ctx.step("Steps 5-6 (workbook): read the draft invoice's totals "
                      "block and compare it against the order's three "
                      "figures"):
            # Read straight after creation, as the workbook does. v19 carries
            # Avalara's per-jurisdiction amounts onto the invoice line through
            # extra_tax_data (see the module docstring), so the totals are
            # already settled here; Compute Taxes is deliberately NOT pressed,
            # because it would overwrite the figures under comparison.
            invoice_totals = doc_totals(ctx, "account.move", invoice_id)
            ctx.log(f"INVOICE totals — "
                    f"Untaxed={invoice_totals['untaxed']:.2f} "
                    f"Taxes={invoice_totals['tax']:.2f} "
                    f"Total={invoice_totals['total']:.2f} "
                    f"Avalara Code={invoice_totals['avalara_code']!r} "
                    f"state={invoice_totals['state']!r}")
            ctx.check("Untaxed Amount on the invoice equals the order's",
                      order_totals["untaxed"], invoice_totals["untaxed"])
            ctx.check("Taxes on the invoice equals the order's",
                      order_totals["tax"], invoice_totals["tax"])
            ctx.check("Total on the invoice equals the order's",
                      order_totals["total"], invoice_totals["total"])

        with ctx.step("Step 7 (workbook): Other Info tab — the invoice's own "
                      "Avalara Code"):
            # account_avatax/models/account_avatax_unique_code.py:26 computes
            # avatax_unique_code as "<model description> <id>", so the order
            # and the invoice ALWAYS carry different codes. The workbook says
            # a difference is correct ("they are two documents at Avalara"),
            # so equality is deliberately NOT asserted here — only that the
            # invoice has a code of its own.
            ctx.check_true(
                "the invoice carries its own non-empty Avalara Code",
                bool(invoice_totals["avalara_code"]),
                actual_desc=f"invoice Avalara Code="
                            f"{invoice_totals['avalara_code']!r}")
            ctx.log(f"Avalara Codes — order={order_totals['avalara_code']!r} "
                    f"invoice={invoice_totals['avalara_code']!r}; they are two "
                    f"documents at Avalara, so a difference is the expected "
                    f"result and equality is not asserted")

        with ctx.step("Step 8 (workbook): Confirm posts the invoice"):
            # Posting is where the recalculation the workbook cares about
            # happens: account_external_tax's _post() recomputes from Avalara,
            # MMG's _check_avatax_tax_total() refuses a move whose tax lines
            # do not add up to Avalara's totalTax, and account_avatax's _post()
            # then re-creates the transaction under the invoice name.
            post_error = ""
            try:
                rpc.call("account.move", "action_post", [invoice_id])
            except OdooRPCError as exc:
                post_error = str(exc)
            ctx.check_true(
                "action_post() on the invoice raised no error",
                not post_error,
                actual_desc=post_error or "action_post() returned no error")
            posted = doc_totals(ctx, "account.move", invoice_id)
            ctx.log(f"POSTED INVOICE totals — "
                    f"Untaxed={posted['untaxed']:.2f} "
                    f"Taxes={posted['tax']:.2f} "
                    f"Total={posted['total']:.2f}")
            ctx.check("invoice state after Confirm", "posted",
                      posted["state"])
            # Workbook State After The Test: "A posted invoice against a
            # confirmed order. Leave both." Handing a posted AvaTax move to
            # unlink() is NOT a harmless no-op — account_external_tax/models/
            # account_move.py:14-16 voids the Avalara transaction before
            # super().unlink() raises, and the raise rolls back Odoo but not
            # the outbound void (see docstring adaptation 5). Drop the id here
            # so cleanup() never sees it. If the post above had failed the id
            # would still be in `created` and the draft would be cleaned up
            # normally.
            created["account.move"].remove(invoice_id)
            ctx.log(f"posted invoice #{invoice_id} left in place with its "
                    f"Avalara transaction intact (workbook State After The "
                    f"Test) — it is deliberately never passed to unlink(), "
                    f"which would void that transaction before failing")
    finally:
        with ctx.step("Cleanup: remove FG05 fixtures (the workbook leaves the "
                      "posted invoice and confirmed order in place; the "
                      "posted invoice is never handed to unlink, because that "
                      "voids its Avalara transaction before it fails)"):
            cleanup(ctx, created)


@test_case(
    id="TEST-FG05-TAX-011",
    name="A posted invoice is registered at Avalara",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P0",
    kind="API",
    order=508,
    description="Commit Transactions is on; a posted invoice carries a "
                "committed Avalara transaction (posted state, own Avalara "
                "Code, non-zero Taxes) and a computed but unconfirmed invoice "
                "stays draft and uncommitted. The portal half is logged as a "
                "manual step.",
    traceability=trace("TC-TAX-011"))
def test_tax_011(ctx):
    rpc = ctx.adapter.rpc
    created = {"account.move": [], "product.product": [], "res.partner": []}
    # Ids of moves this test POSTS. Deliberately separate from `created`:
    # cleanup() must never hand them to unlink(). See docstring adaptation 5.
    posted_ids = []
    with ctx.step("Precondition: Odoo 19, Avalara SANDBOX, and Commit "
                  "Transactions ticked on the company"):
        config = require_sandbox(
            ctx, "registering a posted invoice as a committed transaction at "
                 "Avalara")
        fp_id, fp = require_avatax_fiscal_position(ctx)
        ctx.log(f"AvaTax fiscal position #{fp_id} {fp.get('name')!r}")
        # The workbook's own precondition. Without it the case has no meaning:
        # account_avatax/models/account_external_tax_mixin.py:69 and
        # account_move.py:53 both AND the commit flag with
        # company.avalara_commit, so with it off nothing is ever committed and
        # "the posted invoice is committed" could not be true for any invoice.
        if not config["commit"]:
            ctx.blocked(
                "TC-TAX-011's own precondition is not met: 'Commit "
                "Transactions' (res.company.avalara_commit, labelled 'Commit "
                "in Avatax') is OFF on company "
                f"{config['company_name']!r}. Both places Odoo builds the "
                "Avalara commit flag AND it with this setting "
                "(account_avatax/models/account_external_tax_mixin.py:69 and "
                "account_move.py:53), so no document — posted or draft — is "
                "ever committed and the case's expectations cannot "
                "discriminate. Tick Accounting > Configuration > Settings > "
                "Taxes > AvaTax > Commit Transactions on the SANDBOX company "
                "and re-run.")
        ctx.check_true(
            "Commit Transactions (res.company.avalara_commit) is ticked",
            config["commit"],
            actual_desc=f"avalara_commit=True on company "
                        f"{config['company_name']!r} "
                        f"(environment={config['environment']!r})")
        sweep_fg05(ctx)
    try:
        with ctx.step("Step 1 (workbook, adapted): build and post the "
                      "TC-TAX-001 equivalent invoice — Phoenix AZ, one line"):
            # Adaptation 1: the workbook reuses TC-TAX-001's posted invoice.
            partner_id = make_partner(ctx, "TAX-011 Customer",
                                      ADDRESS_PHOENIX_AZ,
                                      fiscal_position_id=fp_id)
            created["res.partner"].append(partner_id)
            product_id = make_product(ctx, "TAX-011 Item", 1000.00)
            created["product.product"].append(product_id)
            posted_id = make_invoice(ctx, partner_id,
                                     [(product_id, 1, 1000.00)],
                                     fiscal_position_id=fp_id)
            # NOT added to `created`: this move is about to be posted, and
            # unlink() on a posted AvaTax move voids its Avalara transaction
            # before it fails (docstring adaptation 5), which is precisely the
            # transaction the residual manual step below asks a human to find
            # COMMITTED. If the post does not succeed the move stays draft and
            # cleanup()'s trailing sweep_fg05 removes it as an FG05 draft
            # (common.py::sweep_fg05, account.move state in draft/cancel), so
            # nothing leaks in either outcome.
            compute_taxes(ctx, "account.move", posted_id)
            post_error = ""
            try:
                rpc.call("account.move", "action_post", [posted_id])
            except OdooRPCError as exc:
                post_error = str(exc)
            ctx.check_true(
                "action_post() on the TC-TAX-001 equivalent raised no error",
                not post_error,
                actual_desc=post_error or "action_post() returned no error")
            posted_ids.append(posted_id)

        with ctx.step("Steps 3-4 (workbook, in-Odoo half): the posted invoice "
                      "carries a committed Avalara transaction"):
            # account_avatax/models/account_move.py:22-33 — _post() re-runs
            # _get_external_taxes() on the posted move, which recreates the
            # transaction with the invoice name as referenceCode AND commits
            # it, because _get_avatax_service_params (line 53) now yields
            # commit=True: the move's state is 'posted' and avalara_commit is
            # on. That is the in-Odoo half of "found in Avalara, committed".
            posted = doc_totals(ctx, "account.move", posted_id)
            ctx.log(f"POSTED INVOICE #{posted_id} — "
                    f"state={posted['state']!r} "
                    f"Untaxed={posted['untaxed']:.2f} "
                    f"Taxes={posted['tax']:.2f} "
                    f"Total={posted['total']:.2f} "
                    f"Avalara Code={posted['avalara_code']!r}")
            ctx.check("posted invoice state", "posted", posted["state"])
            ctx.check_true(
                "the posted invoice carries a non-empty Avalara Code",
                bool(posted["avalara_code"]),
                actual_desc=f"Avalara Code={posted['avalara_code']!r}")
            posted_commit = _probe_service_params_commit(ctx, posted_id)
            if posted_commit is None:
                # Derived, not observed: _avatax_commit_flag re-evaluates
                # account_avatax/models/account_move.py:53 from the move's
                # state and the company's avalara_commit — both already
                # asserted above — so asserting it would be a tautology
                # (module docstring, adaptation 2). _change_avatax_state
                # writes nothing back to the move, so there is no in-Odoo
                # record of commit state to check against; the portal lookup
                # below is the only real proof.
                ctx.log(
                    f"Avalara 'commit' flag for the posted invoice, DERIVED "
                    f"from account_avatax/models/account_move.py:53 "
                    f"(state={posted['state']!r}, company avalara_commit="
                    f"{config['commit']}) = "
                    f"{_avatax_commit_flag(posted['state'], config['commit'])}"
                    f" — recorded as evidence, not asserted")
            else:
                ctx.check("Avalara 'commit' flag sent for the posted invoice",
                          True, posted_commit)

        with ctx.step("Step 5 (workbook, in-Odoo half): the Taxes figure "
                      "Avalara must match"):
            # MMG's account.move._check_avatax_tax_total() already compares
            # the move's tax lines against the totalTax Avalara returned and
            # raises UserError before super()._post(), so the successful post
            # above is in-Odoo evidence for "Avalara's total tax equals the
            # Odoo Taxes figure". The portal read-back stays a manual step.
            ctx.check_true(
                "the posted invoice carries a non-zero Taxes figure",
                posted["tax"] != 0.0,
                actual_desc=f"posted invoice Taxes = {posted['tax']:.2f}")

        with ctx.step("Step 6 (workbook): one more invoice for the same "
                      "customer — computed and saved, NOT confirmed"):
            draft_id = make_invoice(ctx, partner_id,
                                    [(product_id, 1, 1000.00)],
                                    fiscal_position_id=fp_id)
            created["account.move"].append(draft_id)
            compute_taxes(ctx, "account.move", draft_id)
            draft = doc_totals(ctx, "account.move", draft_id)
            ctx.log(f"DRAFT INVOICE #{draft_id} — state={draft['state']!r} "
                    f"Taxes={draft['tax']:.2f} "
                    f"Avalara Code={draft['avalara_code']!r}")

        with ctx.step("Step 7 (workbook, in-Odoo half): the draft invoice "
                      "must not be committed"):
            ctx.check("draft invoice state (never confirmed)", "draft",
                      draft["state"])
            draft_commit = _probe_service_params_commit(ctx, draft_id)
            if draft_commit is None:
                # Same reasoning as the posted invoice above: derived from a
                # state this step has just asserted, so it is evidence rather
                # than an assertion. The workbook's "the draft must not be
                # committed" is proven in the Avalara portal, not here.
                ctx.log(
                    f"Avalara 'commit' flag for the draft invoice, DERIVED "
                    f"from account_avatax/models/account_move.py:53 "
                    f"(state={draft['state']!r}, company avalara_commit="
                    f"{config['commit']}) = "
                    f"{_avatax_commit_flag(draft['state'], config['commit'])}"
                    f" — recorded as evidence, not asserted")
            else:
                ctx.check("Avalara 'commit' flag sent for the draft invoice",
                          False, draft_commit)

        with ctx.step("Residual manual step (workbook steps 2-5 and 7): the "
                      "Avalara portal is outside this platform's reach"):
            ctx.log(
                "MANUAL VERIFICATION REQUIRED — this platform cannot reach "
                "admin.avalara.com, so two of TC-TAX-011's three expectations "
                "must be confirmed by a person. Sign in to the Avalara "
                "SANDBOX portal (ask Novobi for the sandbox login), then: "
                f"(a) search the transactions for the Avalara Code "
                f"{posted['avalara_code']!r} — the document must be PRESENT "
                f"and its status COMMITTED, not uncommitted; "
                f"(b) read that document's total tax and confirm it equals "
                f"the Odoo invoice's Taxes figure of "
                f"{posted['tax']:.2f} exactly; "
                f"(c) search for the draft invoice's Avalara Code "
                f"{draft['avalara_code']!r} (Odoo Taxes "
                f"{draft['tax']:.2f}) — it must either be absent or present "
                f"as UNCOMMITTED. If the draft IS committed, raise it as a "
                f"P0: it overstates the returns. No re-run is needed — both "
                f"codes and both figures are printed above.")
    finally:
        with ctx.step("Cleanup: remove FG05 fixtures (the DRAFT invoice is "
                      "deleted, which voids its Avalara transaction — "
                      "account_external_tax/models/account_move.py:14-16; the "
                      "posted invoice is never handed to unlink, because that "
                      "same override would void ITS transaction before "
                      "failing)"):
            for move_id in posted_ids:
                ctx.log(f"posted invoice #{move_id} left in place with its "
                        f"Avalara transaction intact (workbook State After "
                        f"The Test) — it is deliberately never passed to "
                        f"unlink(), so the manual portal lookup above finds "
                        f"it COMMITTED rather than voided")
            cleanup(ctx, created)
