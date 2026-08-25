"""FG-02 — certificates of authenticity: TC-LBL-001..007.

Rendering-dependent halves end in ctx.blocked() per the suite policy
(see tests/fg02/common.py docstring). The chooser methods asserted by
TC-LBL-002..005 are underscore-private (not callable over external RPC);
their offline-checkable *inputs* (variant x_date / description_sale state)
and the report records/template paths are asserted instead, then the case
blocks for the rendering/byte-level verification.

Expected v15 outcome for every test in this file: **BLOCKED** — the offline
half (report records, chooser inputs, ORM helpers) is expected to pass and is
asserted in full first; the blocked verdict covers only the py3o/LibreOffice
rendering the QA host cannot produce. No expectation in this file describes a
v19-only behaviour, so none of them is a documented v15 FAIL.

Shape rules this file follows (tests/fg02/common.py):
* invariant 1 — every fixture is created INSIDE the try and teardown goes
  through cleanup_fg02(), which reports its own problems through ctx.log
  instead of raising: a cleanup error must never replace the BLOCKED verdict
  with ERROR / AUTOMATION_ERROR;
* invariant 3 — every fixture name, SKU, artist, medium name, provenance
  text and partner name is namespaced with fx();
* invariant 4 — fixture products pin invoice_policy='order', and TC-LBL-007
  snapshots/clears the company auto-invoice flag while it confirms orders;
* collected assertions — related field comparisons are gathered into one
  mismatch dict and asserted once, so the first difference cannot abort the
  comparison and destroy the evidence for the rest.
"""
from framework.registry import test_case
from tests.fg02.common import (CERT_TEMPLATE_XMLID, CERT_VARIANT_XMLID,
                               FULL_TEMPLATE_PATH, MARK, NO_DATE_PATH,
                               NO_DATE_NO_PROVENANCE_PATH, NO_PROVENANCE_PATH,
                               PNG_1PX, cleanup_fg02, collect_report_record,
                               ensure_medium, fx, m2o_id, make_product,
                               note_mismatch, prepare_fg02, render_blocked,
                               suspend_auto_invoice, trace)


@test_case(
    id="TEST-FG02-LBL-001", name="Certificate of authenticity prints for a variant",
    workflow="FG-02", workflow_name="Certificates & Labels",
    module="mmg_report", priority="P0", kind="API", order=200,
    description="Variant certificate report record (py3o/odt, "
                "report/certificate.odt) plus every data field feeding the "
                "certificate readable on a full fixture; rendering blocked.",
    traceability=trace("TC-LBL-001"))
def test_lbl_001(ctx):
    """Expected v15 outcome: BLOCKED.

    The offline half must pass on v15: mmg_report.product_certificate is a
    py3o/odt report on product.product with py3o_template_fallback
    report/certificate.odt, and every field the ODT prints reads back on the
    fixture. Only _render_py3o (private, server-side) and the visual
    comparison against the v15 baseline document are blocked.
    """
    rpc = ctx.adapter.rpc
    prepare_fg02(ctx, rpc)
    try:
        with ctx.step("Create the x.medium record and a full-data product"):
            medium_name = fx(f"{MARK} Oil on canvas")
            medium = ensure_medium(rpc, medium_name)
            artist = fx("Maynard Dixon")
            provenance = fx("Estate of the artist")
            product, product_name = make_product(
                rpc, "Certificate Item",
                x_artist=artist, x_medium=medium,
                x_height=30.0, x_width=40.0, x_date="1948",
                description_sale=provenance, image_1920=PNG_1PX)
            ctx.log(f"fixture product.product id {product} ('{product_name}')")
        with ctx.step("Assert the variant certificate report record "
                      "(report_type, filetype, template path)"):
            mismatches = {}
            collect_report_record(ctx, CERT_VARIANT_XMLID, {
                "report_type": "py3o",
                "py3o_filetype": "odt",
                "py3o_template_fallback": "report/certificate.odt",
                "model": "product.product",
            }, mismatches)
            ctx.check("variant certificate report record mismatches",
                      {}, mismatches)
        with ctx.step("Assert every data field feeding the certificate reads "
                      "back on the fixture"):
            data = rpc.read("product.product", [product],
                            ["x_artist", "x_medium", "x_height", "x_width",
                             "x_date", "description_sale", "image_1024"])[0]
            mismatches = {}
            note_mismatch(mismatches, "x_artist", artist, data["x_artist"])
            note_mismatch(mismatches, "x_medium", medium,
                          m2o_id(data["x_medium"]))
            note_mismatch(mismatches, "x_height", 30.0, data["x_height"])
            note_mismatch(mismatches, "x_width", 40.0, data["x_width"])
            note_mismatch(mismatches, "x_date", "1948", data["x_date"])
            note_mismatch(mismatches, "description_sale (provenance)",
                          provenance, data["description_sale"])
            note_mismatch(mismatches, "image_1024 derived from image_1920",
                          True, bool(data["image_1024"]))
            ctx.check("certificate data-field mismatches", {}, mismatches)
        with ctx.step("Assert the company block source "
                      "(company.partner_id.x_main_phone readable)"):
            company = rpc.search_read("res.company", [], ["partner_id"],
                                      limit=1)[0]
            phone = rpc.read("res.partner", [m2o_id(company["partner_id"])],
                             ["x_main_phone"])[0]
            ctx.log(f"company partner x_main_phone = {phone['x_main_phone']!r}")
        with ctx.step("Render the certificate (_render_py3o) and compare "
                      "against the v15 baseline"):
            ctx.blocked(render_blocked(
                f"print the certificate of product.product id {product} "
                f"('{product_name}') from the variant form and check the "
                f"rendered ODT prints the artist ({artist}), the medium "
                f"('{medium_name}'), the 30.0 x 40.0 dimensions, the date "
                f"1948, the provenance line '{provenance}', the product image "
                "and the company block, then compare it block-by-block with "
                "the same certificate rendered on the v15 clone"))
    finally:
        cleanup_fg02(ctx, rpc)


def _fallback_case(ctx, label, x_date, provenance, expected_path, path_label):
    """Shared body of TC-LBL-002..005: fixture with the given chooser-input
    combination, template-report record assertions, then blocked for the
    private chooser / byte-level / rendering verification.

    `label` keeps each case's fixture name distinct inside one execution, so
    the blocked instructions point at exactly one record.
    """
    rpc = ctx.adapter.rpc
    prepare_fg02(ctx, rpc)
    provenance = fx(provenance) if provenance else ""
    extra = {}
    if x_date:
        extra["x_date"] = x_date
    if provenance:
        extra["description_sale"] = provenance
    try:
        with ctx.step("Create the product with the chooser-input combination"):
            product, product_name = make_product(rpc, label, **extra)
            ctx.log(f"fixture product.product id {product} "
                    f"('{product_name}'), x_date={x_date or 'empty'}, "
                    f"provenance={provenance or 'empty'}")
        with ctx.step("Assert the chooser inputs on the variant "
                      "(template.product_variant_id reads this data)"):
            data = rpc.read("product.product", [product],
                            ["x_date", "description_sale",
                             "product_tmpl_id"])[0]
            mismatches = {}
            note_mismatch(mismatches, "variant.x_date", x_date or False,
                          data["x_date"])
            note_mismatch(mismatches, "variant.description_sale (provenance)",
                          provenance or False, data["description_sale"])
            ctx.check("chooser-input mismatches", {}, mismatches)
            tmpl = m2o_id(data["product_tmpl_id"])
        with ctx.step("Assert the template-level report record and its XML "
                      "py3o_template_fallback (the full template)"):
            mismatches = {}
            collect_report_record(ctx, CERT_TEMPLATE_XMLID, {
                "report_type": "py3o",
                "py3o_filetype": "odt",
                "py3o_template_fallback": FULL_TEMPLATE_PATH,
                "model": "product.template",
            }, mismatches)
            ctx.check("template certificate report record mismatches",
                      {}, mismatches)
        with ctx.step(f"Chooser must select {path_label} — render and "
                      "verify the printed blocks"):
            chooser_return = expected_path or (
                "None, so the XML py3o_template_fallback stays in force")
            ctx.blocked(render_blocked(
                f"print the certificate of product.template id {tmpl} "
                f"(variant '{product_name}', x_date={x_date or 'empty'}, "
                f"provenance={provenance or 'empty'}) and confirm "
                "_get_product_template_certificate_report_path returns "
                f"{chooser_return} — i.e. that {path_label} is the layout "
                "py3o.report._get_template_fallback loads, that the shipped "
                "ODT it names is the file actually rendered (byte comparison) "
                "and that the printed document omits exactly the empty "
                "blocks"))
    finally:
        cleanup_fg02(ctx, rpc)


@test_case(
    id="TEST-FG02-LBL-002", name="Certificate template fallback — full provenance and date",
    workflow="FG-02", workflow_name="Certificates & Labels",
    module="mmg_report", priority="P0", kind="API", order=201,
    description="Full-data fixture (x_date + description_sale set); template "
                "report XML fallback is the full template; chooser/render "
                "verification blocked (private methods + py3o rendering).",
    traceability=trace("TC-LBL-002"))
def test_lbl_002(ctx):
    """Expected v15 outcome: BLOCKED — the chooser inputs (both x_date and
    provenance set) and the template report record are asserted and expected
    to pass on v15; only the private chooser call, the ODT byte comparison
    and the rendered document are blocked."""
    _fallback_case(ctx, "Fallback Date+Provenance", "1948",
                   "Estate of the artist",
                   None, "no override (the full template via XML fallback)")


@test_case(
    id="TEST-FG02-LBL-003", name="Certificate template fallback — no date",
    workflow="FG-02", workflow_name="Certificates & Labels",
    module="mmg_report", priority="P0", kind="API", order=202,
    description="Provenance-only fixture (x_date empty); expected chooser "
                "path report/template_certificate_no_date.odt; chooser/render "
                "verification blocked.",
    traceability=trace("TC-LBL-003"))
def test_lbl_003(ctx):
    """Expected v15 outcome: BLOCKED — same shape as TC-LBL-002 for the
    no-date input state; the offline half is expected to pass on v15."""
    _fallback_case(ctx, "Fallback No Date", "", "Estate of the artist",
                   NO_DATE_PATH, "the no-date template")


@test_case(
    id="TEST-FG02-LBL-004", name="Certificate template fallback — no provenance",
    workflow="FG-02", workflow_name="Certificates & Labels",
    module="mmg_report", priority="P0", kind="API", order=203,
    description="Date-only fixture (description_sale empty); expected chooser "
                "path report/template_certificate_no_provenance.odt; "
                "chooser/render verification blocked.",
    traceability=trace("TC-LBL-004"))
def test_lbl_004(ctx):
    """Expected v15 outcome: BLOCKED — same shape as TC-LBL-002 for the
    no-provenance input state; the offline half is expected to pass on v15."""
    _fallback_case(ctx, "Fallback No Provenance", "1948", "",
                   NO_PROVENANCE_PATH, "the no-provenance template")


@test_case(
    id="TEST-FG02-LBL-005", name="Certificate template fallback — neither date nor provenance",
    workflow="FG-02", workflow_name="Certificates & Labels",
    module="mmg_report", priority="P0", kind="API", order=204,
    description="Bare fixture (neither x_date nor description_sale); expected "
                "chooser path the fourth template "
                "(no_date_no_provenance); chooser/render blocked.",
    traceability=trace("TC-LBL-005"))
def test_lbl_005(ctx):
    """Expected v15 outcome: BLOCKED — same shape as TC-LBL-002 for the
    neither-date-nor-provenance input state; the offline half is expected to
    pass on v15."""
    _fallback_case(ctx, "Fallback Bare", "", "",
                   NO_DATE_NO_PROVENANCE_PATH,
                   "the no-date-no-provenance template")


@test_case(
    id="TEST-FG02-LBL-006", name="Certificate prints from the template (not just the variant)",
    workflow="FG-02", workflow_name="Certificates & Labels",
    module="mmg_report", priority="P1", kind="API", order=205,
    description="Template-level report record: model/report_name/report_type "
                "and the Print-menu binding on product.template; rendering "
                "blocked.",
    traceability=trace("TC-LBL-006"))
def test_lbl_006(ctx):
    """Expected v15 outcome: BLOCKED.

    The template report record (model product.template, report_name
    product.template.certificate, py3o/odt, Print-menu binding on
    product.model_product_template) is asserted offline and expected to pass
    on v15; the _render_py3o run and the template-form download are blocked.
    """
    rpc = ctx.adapter.rpc
    prepare_fg02(ctx, rpc)
    try:
        with ctx.step("Create a full-data product (x_date + "
                      "description_sale)"):
            product, product_name = make_product(
                rpc, "Template Cert Item",
                x_date="1948", description_sale=fx("Estate of the artist"))
            ctx.log(f"fixture product.product id {product} ('{product_name}')")
        with ctx.step("Assert the template report record and its Print-menu "
                      "binding (binding_model_id = product.template)"):
            tmpl_model_id = rpc.ref("product.model_product_template")
            mismatches = {}
            collect_report_record(ctx, CERT_TEMPLATE_XMLID, {
                "model": "product.template",
                "report_name": "product.template.certificate",
                "report_type": "py3o",
                "py3o_filetype": "odt",
                "binding_model_id": tmpl_model_id,
            }, mismatches)
            ctx.check("template certificate report record mismatches",
                      {}, mismatches)
        with ctx.step("Resolve the fixture's template for the render step"):
            tmpl = m2o_id(rpc.read("product.product", [product],
                                   ["product_tmpl_id"])[0]["product_tmpl_id"])
            ctx.log(f"product.template id {tmpl}")
        with ctx.step("Render via _render_py3o and download from the "
                      "template form"):
            ctx.blocked(render_blocked(
                f"open product.template id {tmpl} ('{product_name}'), use "
                "Print → Certificate on the template form and confirm the ODT "
                "downloads and shows the same certificate content as the "
                "variant-level print (the workbook's template-vs-variant "
                "parity check)"))
    finally:
        cleanup_fg02(ctx, rpc)


@test_case(
    id="TEST-FG02-LBL-007", name="Certificate cites the most recent confirmed sale",
    workflow="FG-02", workflow_name="Certificates & Labels",
    module="mmg_report", priority="P1", kind="API", order=206,
    description="get_purchase_info_based_on_sol returns the most recent "
                "confirmed sale (not the first, not the cancelled decoy); "
                "never-sold returns ('', '', 0.0); printed-block check "
                "blocked.",
    traceability=trace("TC-LBL-007"))
def test_lbl_007(ctx):
    """Expected v15 outcome: BLOCKED.

    The ORM essence is asserted in full and expected to pass on v15:
    mmg_report's get_purchase_info_based_on_sol searches sale.order.line with
    order_id.state in ('sale', 'done') ordered by id desc, so the newest
    *confirmed* line wins over the cancelled decoy that carries the newest id,
    and a never-sold product returns ('', '', 0.0). Only the printed
    last-sale block is blocked.

    Fixture notes (invariant 4, tests/fg02/common.py):
    * the fixture products are services with invoice_policy='order' — a
      service creates no picking on confirm (exact cleanup) and is skipped by
      mmg_magento2_ept_inherit's confirm-time export_stock_to_magento(),
      which only touches type='product' lines;
    * the company's auto-invoice-on-confirm flag is snapshotted and cleared
      for this test and restored in the finally step. With it on and the
      clone's default 'delivery' policy, action_confirm raised sale's
      nothing-to-invoice UserError (RUN-5C016D16 AUTOMATION_ERROR); with the
      policy pinned it would instead create a draft invoice whose validity
      depends on the clone's chart of accounts — neither is part of this TC's
      expected result.
    """
    rpc = ctx.adapter.rpc
    prepare_fg02(ctx, rpc)
    # set by the first step; stays None if that step never ran, so the
    # finally always has something valid to hand cleanup_fg02
    restore_config = None

    def make_order(partner, date_order, price):
        return rpc.create("sale.order", {
            "partner_id": partner,
            "date_order": date_order,
            "order_line": [(0, 0, {
                "product_id": product,
                "product_uom_qty": 1,
                "price_unit": price,
                "tax_id" if ctx.env.version == "15" else "tax_ids":
                    [(6, 0, [])],
            })],
        })

    try:
        with ctx.step("Suspend the company auto-invoice-on-confirm option "
                      "(snapshot restored in the cleanup step)"):
            restore_config = suspend_auto_invoice(ctx, rpc)
        with ctx.step("Create the product and the three buyers"):
            # service product: no pickings on confirm, keeps cleanup exact
            product, product_name = make_product(rpc, "Last Sale Item",
                                                 type="service")
            first_name = fx(f"{MARK} First Buyer")
            latest_name = fx(f"{MARK} Latest Buyer")
            cancelled_name = fx(f"{MARK} Cancelled Buyer")
            first, latest, cancelled = rpc.create(
                "res.partner", [{"name": first_name}, {"name": latest_name},
                                {"name": cancelled_name}])
            ctx.log(f"fixture product.product id {product} ('{product_name}')")
        with ctx.step("Create the three sale orders (old / latest / "
                      "cancelled decoy with the newest id)"):
            so_old = make_order(first, "2024-01-15 10:00:00", 900.0)
            so_new = make_order(latest, "2025-06-30 10:00:00", 1500.0)
            so_cancel = make_order(cancelled, "2026-01-05 10:00:00", 9999.0)
            ctx.log(f"sale orders: old={so_old}, latest={so_new}, "
                    f"decoy={so_cancel}")
        with ctx.step("Confirm old and latest; confirm then cancel the decoy"):
            rpc.call("sale.order", "action_confirm", [so_old, so_new])
            rpc.call("sale.order", "action_confirm", [so_cancel])
            # v15 sale.order.action_cancel returns the sale.order.cancel
            # confirmation wizard — leaving the order in state 'sale' — when
            # _show_cancel_wizard() finds a draft invoice (sale/models/
            # sale_order.py) or a done picking (sale_stock override), unless
            # the 'disable_cancel_warning' context flag is set. The guard is
            # kept even with auto-invoicing suspended: any other module that
            # invoices on confirm would otherwise leave the decoy confirmed.
            # ctx.adapter.cancel_order cannot be used: the v15 adapter does
            # not override it, so it would call action_cancel with no context.
            rpc.call("sale.order", "action_cancel", [so_cancel],
                     context={"disable_cancel_warning": True})
            # confirmation resets date_order to now — restore the workbook
            # dates so the expected ('2025-06-30', …) tuple stays exact
            rpc.write("sale.order", [so_old],
                      {"date_order": "2024-01-15 10:00:00"})
            rpc.write("sale.order", [so_new],
                      {"date_order": "2025-06-30 10:00:00"})
        with ctx.step("Assert the order states: two confirmed, the decoy "
                      "cancelled"):
            states = {row["id"]: row["state"] for row in rpc.read(
                "sale.order", [so_old, so_new, so_cancel], ["state"])}
            ctx.log(f"sale.order states = {states}")
            # 'confirmed' is state in ('sale', 'done') — exactly the domain
            # get_purchase_info_based_on_sol filters on, so a clone with
            # "Lock Confirmed Sales" enabled (state 'done') is still correct.
            ctx.check("order states (decoy cancelled, the other two "
                      "confirmed)",
                      {"old order confirmed": True,
                       "latest order confirmed": True,
                       "decoy state": "cancel"},
                      {"old order confirmed":
                          states[so_old] in ("sale", "done"),
                       "latest order confirmed":
                          states[so_new] in ("sale", "done"),
                       "decoy state": states[so_cancel]})
        with ctx.step("Call get_purchase_info_based_on_sol — most recent "
                      "confirmed sale wins"):
            result = rpc.call("product.product",
                              "get_purchase_info_based_on_sol", [product])
            ctx.check("last-sale tuple (date, customer, amount)",
                      ["2025-06-30", latest_name, 1500.0], list(result))
        with ctx.step("Never-sold product returns ('', '', 0.0)"):
            never, never_name = make_product(rpc, "Never Sold Item",
                                             type="service")
            ctx.log(f"never-sold fixture id {never} ('{never_name}')")
            result = rpc.call("product.product",
                              "get_purchase_info_based_on_sol", [never])
            ctx.check("never-sold tuple", ["", "", 0.0], list(result))
        with ctx.step("Print the certificate and verify the last-sale block"):
            ctx.blocked(render_blocked(
                f"print the certificate of product.product id {product} "
                f"('{product_name}') and confirm its last-sale block prints "
                f"2025-06-30 / {latest_name} / 1500.0 — the values the ORM "
                "half just asserted — and not the cancelled decoy's "
                "2026-01-05 / 9999.0"))
    finally:
        cleanup_fg02(ctx, rpc,
                     restore=[fn for fn in (restore_config,) if fn])
