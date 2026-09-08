"""FG-05 — TC-TAX-013: an exempt customer is charged no tax.

Workbook row 10.0 (``MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0
.xlsx`` / ``Testing Guideline``), P0, business area "Tax exemption".

What this proves
----------------
Two customer invoices are computed through Avalara in the SAME jurisdiction
(Phoenix AZ), same product, same 1,000.00 line, differing in exactly one
attribute: Customer A carries an ``avatax.exemption`` on
``res.partner.avalara_exemption_id`` and Customer B does not.

* Customer A's Taxes must read exactly 0.00.
* Customer B's Taxes must be NON-ZERO. **This control is an assertion, not a
  note**: the workbook says a zero on BOTH figures means AvaTax is not
  calculating at all, "which is a different and worse problem". Implemented
  as ``ctx.check_true`` so that failure mode cannot pass as a green run.
* Neither invoice may raise an error.

The field the exemption rides on
--------------------------------
``account_avatax/models/res_partner.py`` declares
``avalara_exemption_id = fields.Many2one('avatax.exemption',
company_dependent=True)`` and
``account_external_tax_mixin._prepare_avatax_document_service_call`` sends it
as ``entityUseCode`` from
``self.partner_id.commercial_partner_id.with_company(self.company_id)``.
Because the value is stored **per company**, the workbook's If-It-Fails column
warns it "may look filled on one company and be empty on another". Every
exemption read and write below therefore happens in one company, and that
company (name and id) is logged up front so a failure can be read against the
right property row. The fixture partners have no ``parent_id``, so each is its
own ``commercial_partner_id`` and the value the test writes is the value
Avalara receives.

Documented adaptations
----------------------
1. **Cross-test dependency broken.** The workbook's Test Data column says
   "Customer A: the exempt customer identified in TC-DAT-017". The platform
   forbids depending on another test's fixtures, and modifying a pre-existing
   business customer is forbidden outright. This test instead builds its own
   equivalent starting state: two FG05 fixture partners, and it puts an
   *existing, unmodified* ``avatax.exemption`` record on one of them. The
   business assertion is identical to the workbook's.
2. **The workbook's remedy is reported, never executed.** The Preconditions
   column says that if no exempt customer survived, "use Sync Parameters in
   the AvaTax settings block first to pull the exemption list". That is
   ``res.config.settings.avatax_sync_company_params()``, which creates
   ``avatax.exemption`` records and calls Avalara — outside what a regression
   test may do. When the company has no usable exemption the test reports
   BLOCKED and names that remedy verbatim.
3. **A missing Avalara Tax Code is BLOCKED, not FAILED.**
   ``_prepare_avatax_document_line_service_call`` raises
   ``UserError('The Avalara Tax Code is required for ... See
   https://taxcode.avatax.avalara.com/')`` when the fixture product's category
   chain resolves no ``product.avatax.category``. That is a fixture/setup gap
   in the target database, not the exemption behaviour under test, so it is
   reported as BLOCKED with the remedy. It is recognised by the
   ``taxcode.avatax.avalara.com`` marker, because the RPC layer keeps only the
   LAST line of a multi-line server message. **Every other** error is recorded
   and fails the workbook's "Neither invoice shows an error" expectation.

State after the test: the workbook says "Two draft invoices. Delete them or
leave them in draft." Both stay draft, so both are deletable and both are in
the cleanup dict.
"""
from __future__ import annotations

from adapters.base import OdooRPCError
from framework.registry import test_case
from tests.fg05.common import (ADDRESS_PHOENIX_AZ, MODULE, WORKFLOW,
                               WORKFLOW_NAME, cleanup, compute_taxes,
                               doc_totals, make_invoice, make_partner,
                               make_product, require_avatax_fiscal_position,
                               require_sandbox, sweep_fg05, trace)

# account_avatax raises "The Avalara Tax Code is required for <product>\n
# See https://taxcode.avatax.avalara.com/" when a line's product resolves no
# product.avatax.category. adapters.base.OdooRPC keeps only the last line of a
# server message, so the URL — not the first line — is the reliable marker.
TAX_CODE_MARKERS = ("taxcode.avatax.avalara.com",
                    "Avalara Tax Code is required")

LINE_PRICE = 1000.00


def _m2o(value):
    """``[id, display_name]`` -> id; ``False`` / ``None`` / ``[]`` -> ``None``."""
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    return value or None


def _m2o_label(value):
    """Human-readable value of a many2one, for evidence lines."""
    if isinstance(value, (list, tuple)) and len(value) > 1:
        return value[1]
    return "empty"


@test_case(
    id="TEST-FG05-TAX-013",
    name="An exempt customer is charged no tax",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P0",
    kind="API",
    order=509,
    description="Customer A carrying an Avalara Exemption computes 0.00 tax "
                "while Customer B — same state, same city, same 1,000.00 "
                "line, no exemption — computes a non-zero tax; the control "
                "figure proves AvaTax is calculating at all.",
    traceability=trace("TC-TAX-013"))
def test_tax_013(ctx):
    rpc = ctx.adapter.rpc
    created = {"account.move": [], "product.product": [], "res.partner": []}

    with ctx.step("Precondition: Odoo 19 with a usable Avalara SANDBOX"):
        config = require_sandbox(
            ctx, "computing tax for an exempt customer and for a taxable "
                 "control customer in the same state")
        company_id = config["company_id"]
        fp_id, fp = require_avatax_fiscal_position(ctx)
        ctx.log(f"AvaTax fiscal position #{fp_id} {fp['name']!r}")
        ctx.log(
            f"res.partner.avalara_exemption_id is company_dependent "
            f"(account_avatax/models/res_partner.py) — this run reads and "
            f"writes it for company {config['company_name']!r} "
            f"(id={company_id}) ONLY. The workbook's If-It-Fails column warns "
            f"the same customer can show a filled exemption in one company "
            f"and an empty one in another; a failure below must be re-read "
            f"against this company")
        ctx.log(
            "avalara_exemption_id / entityUseCode is Odoo Enterprise "
            "account_avatax behaviour; mmg_account_avatax_enhancement only "
            "renames the jurisdiction taxes and adds the tax-total "
            "post-condition. Route a defect here accordingly")
        sweep_fg05(ctx)

    try:
        with ctx.step("Step 1 (workbook): resolve an Avalara Exemption for "
                      "this company and create Customer A with it"):
            us_ids = rpc.search("res.country", [("code", "=", "US")], limit=1)
            us_id = us_ids[0] if us_ids else None
            company_domain = [("company_id", "=", company_id)]
            domain = list(company_domain)
            if us_id:
                # mirror the field's own domain: an exemption restricted to
                # other countries cannot legally be put on a US customer
                domain = company_domain + [
                    "|", ("valid_country_ids", "=", False),
                    ("valid_country_ids", "in", [us_id])]
            usable = rpc.search_read(
                "avatax.exemption", domain, ["name", "code"],
                limit=1, order="id")
            if not usable:
                on_company = rpc.call("avatax.exemption", "search_count",
                                      company_domain)
                if on_company:
                    ctx.blocked(
                        f"company {config['company_name']!r} (id={company_id}) "
                        f"has {on_company} avatax.exemption record(s), but "
                        f"none of them is valid for the United States "
                        f"(valid_country_ids), so none can be put on the US "
                        f"customer TC-TAX-013 needs. Re-run Sync Parameters "
                        f"in the AvaTax settings block (Accounting > "
                        f"Configuration > Settings > Taxes > AvaTax) to pull "
                        f"the full exemption list, then re-run this test")
                ctx.blocked(
                    f"no avatax.exemption record exists for company "
                    f"{config['company_name']!r} (id={company_id}), so there "
                    f"is no Avalara Exemption to put on Customer A and the "
                    f"exempt-vs-taxable comparison cannot be evaluated. "
                    f"Workbook remedy (TC-TAX-013 Preconditions): use Sync "
                    f"Parameters in the AvaTax settings block to pull the "
                    f"exemption list first, then set one on a test customer. "
                    f"This test deliberately does NOT call "
                    f"res.config.settings.avatax_sync_company_params() "
                    f"itself — it creates avatax.exemption records and "
                    f"reaches Avalara, which is outside what a regression "
                    f"test may do")
            exemption = usable[0]
            ctx.log(f"using avatax.exemption #{exemption['id']} "
                    f"[{exemption['code']}] {exemption['name']} "
                    f"(read-only reference record — never modified)")

            partner_a = make_partner(ctx, "Exempt Customer A",
                                     ADDRESS_PHOENIX_AZ,
                                     fiscal_position_id=fp_id,
                                     exemption_id=exemption["id"])
            created["res.partner"].append(partner_a)
            row_a = rpc.read("res.partner", [partner_a],
                             ["avalara_exemption_id", "state_id", "city"])[0]
            ctx.log(f"Customer A #{partner_a} Avalara Exemption = "
                    f"{_m2o_label(row_a['avalara_exemption_id'])}")
            ctx.check(
                f"Customer A's Avalara Exemption is filled in "
                f"(company {company_id})",
                exemption["id"], _m2o(row_a["avalara_exemption_id"]))

        with ctx.step("Step 4 setup (workbook): Customer B — the taxable "
                      "control customer in the SAME state and city, with no "
                      "exemption"):
            partner_b = make_partner(ctx, "Taxable Control Customer B",
                                     ADDRESS_PHOENIX_AZ,
                                     fiscal_position_id=fp_id)
            created["res.partner"].append(partner_b)
            row_b = rpc.read("res.partner", [partner_b],
                             ["avalara_exemption_id", "state_id", "city"])[0]
            ctx.log(f"Customer B #{partner_b} Avalara Exemption = "
                    f"{_m2o_label(row_b['avalara_exemption_id'])}")
            ctx.check(
                "Customer B (the control) carries NO Avalara Exemption",
                None, _m2o(row_b["avalara_exemption_id"]))
            ctx.check(
                "control customer sits in the same state and city as the "
                "exempt customer",
                (_m2o(row_a["state_id"]), row_a["city"]),
                (_m2o(row_b["state_id"]), row_b["city"]))

        with ctx.step("Step 2 (workbook): the same art item at 1,000.00 for "
                      "both invoices"):
            product_id = make_product(ctx, "Art Item Exemption", LINE_PRICE)
            created["product.product"].append(product_id)

        errors = []

        def _invoice_and_compute(label, partner_id):
            """New invoice, one 1,000.00 line, save, Compute Taxes, read.

            Returns ``(move_id, totals)``. A Compute Taxes failure is recorded
            in ``errors`` instead of raising, so the other customer's figure is
            still collected — the workbook's whole point is the comparison.
            """
            move_id = make_invoice(ctx, partner_id,
                                   [(product_id, 1, LINE_PRICE)],
                                   fiscal_position_id=fp_id)
            created["account.move"].append(move_id)
            try:
                compute_taxes(ctx, "account.move", move_id)
            except OdooRPCError as exc:
                message = str(exc)
                if any(marker in message for marker in TAX_CODE_MARKERS):
                    ctx.blocked(
                        f"the fixture product resolves no Avalara Tax Code, "
                        f"so account_avatax refused the document before any "
                        f"tax was computed ({message}). This is a data-setup "
                        f"gap in the target database, not the exemption "
                        f"behaviour TC-TAX-013 covers: set an Avatax Category "
                        f"(product.avatax.category) on the default product "
                        f"category, the product template, or the product, "
                        f"then re-run")
                errors.append(f"{label} invoice #{move_id}: {message}")
            totals = doc_totals(ctx, "account.move", move_id)
            ctx.log(f"{label} invoice #{move_id} — Untaxed "
                    f"{totals['untaxed']:.2f} / Taxes {totals['tax']:.2f} / "
                    f"Total {totals['total']:.2f} / state {totals['state']} / "
                    f"Avalara Code {totals['avalara_code']!r}")
            return move_id, totals

        with ctx.step("Steps 2-3 (workbook): Customer A's invoice — one line "
                      "at 1,000.00, Compute Taxes, read the Taxes figure"):
            move_a, totals_a = _invoice_and_compute("Customer A", partner_a)
            ctx.check("Customer A's Untaxed Amount", LINE_PRICE,
                      totals_a["untaxed"])

        with ctx.step("Step 4 (workbook): repeat steps 2-3 for Customer B, "
                      "the taxable control customer"):
            move_b, totals_b = _invoice_and_compute("Customer B", partner_b)
            ctx.check("Customer B's Untaxed Amount", LINE_PRICE,
                      totals_b["untaxed"])

        with ctx.step("Step 5 (workbook): compare the two Taxes figures"):
            # asserted first: an invoice whose Compute Taxes failed also shows
            # 0.00 tax, which would let the exempt expectation pass for the
            # wrong reason
            ctx.check_true(
                "neither invoice showed an error",
                not errors,
                actual_desc="; ".join(errors) if errors
                else (f"Compute Taxes returned cleanly on invoice #{move_a} "
                      f"(Customer A) and invoice #{move_b} (Customer B)"))
            ctx.check("Customer A's invoice shows Taxes of 0.00",
                      0.00, totals_a["tax"])
            ctx.check_true(
                "Customer B's invoice — same state, same city, same amount — "
                "shows a NON-ZERO Taxes figure (a zero on BOTH would mean "
                "AvaTax is not calculating at all)",
                totals_b["tax"] != 0.00,
                actual_desc=(
                    f"Customer B Taxes = {totals_b['tax']:.2f} "
                    f"(total {totals_b['total']:.2f}); Customer A Taxes = "
                    f"{totals_a['tax']:.2f} (total {totals_a['total']:.2f}); "
                    f"both on an untaxed 1,000.00 in "
                    f"{row_b['city']}, exemption on A = "
                    f"{_m2o_label(row_a['avalara_exemption_id'])}, exemption "
                    f"on B = {_m2o_label(row_b['avalara_exemption_id'])}, "
                    f"company {config['company_name']!r} "
                    f"(id={company_id})"))
            ctx.check_true(
                "both invoices are still DRAFT — the workbook's state after "
                "the test",
                totals_a["state"] == "draft" and totals_b["state"] == "draft",
                actual_desc=f"invoice #{move_a} state="
                            f"{totals_a['state']}, invoice #{move_b} state="
                            f"{totals_b['state']}")
    finally:
        with ctx.step("Cleanup: remove FG05 fixtures (both invoices are "
                      "draft, so both are deletable)"):
            cleanup(ctx, created)
