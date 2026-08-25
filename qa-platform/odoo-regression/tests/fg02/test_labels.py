"""FG-02 — Avery labels, backtag, print entry points and the rendering
smoke: TC-LBL-008..011, TC-SMK-011.

The wizard routing (count-driven format selection), slot helpers
(check_list_data / check_label_description / get_page_groups /
check_list_data_6) and the print server actions are public ORM methods and
are asserted here in full. The rendered DOCX itself (pagination, slot
geometry, LibreOffice ODT→DOCX conversion, v15 page-by-page baseline
comparison) cannot be verified offline — those halves end in ctx.blocked().

Expected v15 outcome for every test in this file: **BLOCKED** — the offline
half is expected to pass on v15 and is asserted first; the blocked verdict
covers only the rendered document (and, for TC-SMK-011, the missing
LibreOffice runtime, which the workbook lists as a precondition). No
expectation here describes a v19-only behaviour, so none of them is a
documented v15 FAIL.

Shape rules this file follows (tests/fg02/common.py):
* invariant 1 — fixtures are created INSIDE the try and teardown goes through
  cleanup_fg02(), which logs its own problems instead of raising: a cleanup
  error must never replace the BLOCKED verdict with ERROR/AUTOMATION_ERROR.
  cleanup_fg02 also unlinks the wizards each test created;
* invariant 2 — every call that reaches ir.actions.report.report_action (the
  two wizard action methods and the four print entry points) passes
  REPORT_CTX, so the "Configure your document layout" diversion cannot
  replace the report action this clone's unset external_report_layout_id
  would otherwise trigger;
* invariant 3 — fixture names, SKUs, artist strings and the x.medium name
  carry this execution's fx() token; the workbook's literal label data
  (x_date 1950, 10.5 x 8.0) stays literal;
* invariant 4 — label fixtures carry a real non-zero price written to BOTH
  list_price and lst_price, because multichannel_manage_price makes
  lst_price (the field the label formats) read the stored variant_price;
* the wizard a print entry point creates internally is identified by an id
  watermark taken immediately before the call (newest_wizard_id), never as
  "the globally newest wizard" — the transient table is shared;
* collected assertions — slot samples, routing results and report-record
  fields are gathered into one dict and asserted once, so the first
  difference cannot abort the comparison and destroy the rest of the
  evidence.
"""
from framework.registry import test_case
from tests.fg02.common import (LABEL_WIZARD, MARK, REPORT_CTX, cleanup_fg02,
                               collect_report_record, ensure_medium,
                               fixture_token, fx, label_artist,
                               label_description, label_wizard,
                               libreoffice_blocked, m2o_id,
                               make_label_products, make_product,
                               newest_wizard_id, note_mismatch, prepare_fg02,
                               price_label, render_blocked, trace)


@test_case(
    id="TEST-FG02-LBL-008", name="Avery 30-per-page labels",
    workflow="FG-02", workflow_name="Certificates & Labels",
    module="mmg_stock", priority="P0", kind="API", order=210,
    description="35 selected variants auto-select avery.label.60; slot "
                "helpers return the right per-label data in selection order "
                "and '' past the selection; DOCX render blocked.",
    traceability=trace("TC-LBL-008"))
def test_lbl_008(ctx):
    """Expected v15 outcome: BLOCKED.

    Everything offline is expected to pass on v15: the 31..90 threshold
    selects avery.label.60, check_list_data follows the wizard's product_ids
    order and returns '' past the selection, and each slot carries its own
    product's artist, formatted price and description line. Only the rendered
    DOCX (30 + 5 pagination, slot geometry, v15 baseline comparison) is
    blocked.

    Price note: the formatted-price assertion compares the wizard slot value
    against the fixture's own lst_price rendered the way
    digest.digest._format_currency_amount renders it (currency symbol + the
    float's str()). RUN-5C016D16 failed here with '$0.0' because the fixture
    had no price at all — see invariant 4 in tests/fg02/common.py.
    """
    rpc = ctx.adapter.rpc
    prepare_fg02(ctx, rpc)
    wizards = []
    try:
        with ctx.step("Assert the digest dependency of the price formatter is "
                      "installed (workbook precondition)"):
            digest = rpc.search_read("ir.module.module",
                                     [("name", "=", "digest")], ["state"],
                                     limit=1)
            ctx.check("digest module state", "installed",
                      digest[0]["state"] if digest else "absent")
        with ctx.step("Create 35 variants with distinct label data"):
            medium_name = fx(f"{MARK} Watercolor")
            medium = ensure_medium(rpc, medium_name)
            ids_35 = make_label_products(rpc, 35, "LBL08", medium)
            ctx.check("35 fixtures created", 35, len(ids_35))
        with ctx.step("Wizard over the 35 variants auto-selects the "
                      "avery.label.60 format (31..90 threshold)"):
            wiz = label_wizard(rpc, ids_35)
            wizards.append(wiz)
            action = rpc.call(LABEL_WIZARD, "action_export_avery_label",
                              [wiz], context=REPORT_CTX)
            ctx.check("label action (report_name, report_type)",
                      {"report_name": "avery.label.60", "report_type": "py3o"},
                      {key: action.get(key)
                       for key in ("report_name", "report_type")})
        with ctx.step("Slot order follows the wizard's product_ids order "
                      "(flat index 0..34, no gaps, no reordering)"):
            wizard_order = rpc.read(LABEL_WIZARD, [wiz],
                                    ["product_ids"])[0]["product_ids"]
            codes = rpc.read("product.product", wizard_order,
                             ["default_code"])
            code_by_pos = [row["default_code"] for row in codes]
            mismatches = {}
            for idx in (0, 17, 34):
                slot = rpc.call(LABEL_WIZARD, "check_list_data",
                                [wiz], idx, "default_code")
                note_mismatch(mismatches, f"slot {idx} default_code",
                              code_by_pos[idx], slot)
            ctx.check("sampled slot-order mismatches", {}, mismatches)
        with ctx.step("Slots past the selection are empty "
                      "(check_list_data returns '')"):
            mismatches = {}
            for idx in (35, 59):
                past = rpc.call(LABEL_WIZARD, "check_list_data",
                                [wiz], idx, "default_code")
                note_mismatch(mismatches, f"slot {idx} past selection",
                              "", past)
            ctx.check("past-selection slot mismatches", {}, mismatches)
        with ctx.step("Per-label data on slot 0: artist, price rendered as a "
                      "formatted currency amount, description line"):
            # the fixture index behind slot 0, so the expectation never
            # assumes the m2m read order equals the creation order
            slot0_product = wizard_order[0]
            slot0_index = ids_35.index(slot0_product) + 1
            amount, formatted = price_label(rpc, slot0_product)
            ctx.check_true("fixture precondition: slot-0 product has a "
                           "non-zero list price (TC-LBL-008 asks for distinct "
                           "lst_price values)", bool(amount),
                           actual_desc=f"lst_price={amount!r}")
            mismatches = {}
            note_mismatch(mismatches, "slot 0 x_artist",
                          label_artist("LBL08", slot0_index),
                          rpc.call(LABEL_WIZARD, "check_list_data",
                                   [wiz], 0, "x_artist"))
            note_mismatch(mismatches,
                          "slot 0 lst_price as a formatted currency amount "
                          "(digest.digest._format_currency_amount)",
                          formatted,
                          rpc.call(LABEL_WIZARD, "check_list_data",
                                   [wiz], 0, "lst_price"))
            note_mismatch(mismatches, "slot 0 description line",
                          label_description(medium_name),
                          rpc.call(LABEL_WIZARD, "check_label_description",
                                   [wiz], 0))
            ctx.check("per-label data mismatches", {}, mismatches)
        with ctx.step("Render the DOCX through LibreOffice: pagination "
                      "(30 + 5), slot geometry, v15 baseline comparison"):
            ctx.blocked(render_blocked(
                f"print the labels of access.avery.label.wizard id {wiz} (the "
                "35 FG02 LBL08 variants of fixture namespace "
                f"[{fixture_token()}]) and check the DOCX carries 30 "
                "labels on sheet 1 and 5 on sheet 2, that each label sits in "
                "its Avery slot with the artist / price / description line of "
                "the matching variant, that the 55 unused slots are blank, "
                "and compare the sheets page-by-page with the v15 baseline "
                "output for the same 35 products"))
    finally:
        cleanup_fg02(ctx, rpc, wizards)


@test_case(
    id="TEST-FG02-LBL-009", name="Avery 60 / 90 / 120-per-page labels",
    workflow="FG-02", workflow_name="Certificates & Labels",
    module="mmg_stock", priority="P1", kind="API", order=211,
    description="65/95/125 selections auto-select avery.label.60/90/120 "
                "(and 120 as the empty-selection default); ODT layout paths "
                "on the report records; DOCX renders blocked.",
    traceability=trace("TC-LBL-009"))
def test_lbl_009(ctx):
    """Expected v15 outcome: BLOCKED.

    The three count thresholds, the empty-selection default and the three
    ODT layout paths are asserted offline and expected to pass on v15; the
    rendered pagination/layout and the v15 page-by-page baseline comparison
    are blocked. The three routing probes are collected and asserted once, so
    a wrong threshold on one selection size still leaves the evidence for the
    other two.
    """
    rpc = ctx.adapter.rpc
    prepare_fg02(ctx, rpc)
    wizards = []
    by_count = {}
    cases = ((65, "avery.label.60"), (95, "avery.label.90"),
             (125, "avery.label.120"))
    try:
        with ctx.step("Create a pool of 125 variants with distinct label "
                      "data"):
            medium_name = fx(f"{MARK} Watercolor")
            medium = ensure_medium(rpc, medium_name)
            pool = make_label_products(rpc, 125, "LBL09", medium)
            ctx.check("125 fixtures created", 125, len(pool))
        routing = {}
        for count, expected_report in cases:
            with ctx.step(f"{count} selected variants auto-select "
                          f"{expected_report}"):
                wiz = label_wizard(rpc, pool[:count])
                wizards.append(wiz)
                by_count[count] = wiz
                action = rpc.call(LABEL_WIZARD, "action_export_avery_label",
                                  [wiz], context=REPORT_CTX)
                routing[count] = {
                    "report_name": action.get("report_name"),
                    "report_type": action.get("report_type"),
                    "first slot past the selection": rpc.call(
                        LABEL_WIZARD, "check_list_data", [wiz], count,
                        "default_code"),
                }
                ctx.log(f"{count} products → wizard {wiz} → {routing[count]}")
        with ctx.step("Assert the collected count-driven format routing"):
            ctx.check("count → format routing",
                      {count: {"report_name": report, "report_type": "py3o",
                               "first slot past the selection": ""}
                       for count, report in cases},
                      routing)
        with ctx.step("Empty selection falls back to avery.label.120 "
                      "(the wizard default)"):
            empty_wiz = rpc.create(LABEL_WIZARD, {})
            wizards.append(empty_wiz)
            action = rpc.call(LABEL_WIZARD, "action_export_avery_label",
                              [empty_wiz], context=REPORT_CTX)
            ctx.check("empty-selection report_name", "avery.label.120",
                      action.get("report_name"))
        with ctx.step("The three formats point at their own ODT layouts "
                      "(py3o_template_fallback)"):
            mismatches = {}
            for xmlid, path in (
                    ("mmg_stock.avery_label_60_report", "report/60.odt"),
                    ("mmg_stock.avery_label_90_report", "report/90.odt"),
                    ("mmg_stock.avery_label_120_report", "report/120.odt")):
                collect_report_record(ctx, xmlid, {
                    "report_type": "py3o",
                    "py3o_filetype": "docx",
                    "py3o_template_fallback": path,
                }, mismatches)
            ctx.check("Avery report record mismatches", {}, mismatches)
        with ctx.step("Render each DOCX: per-page slot counts, page breaks, "
                      "fill order, v15 page-by-page baseline comparison"):
            ctx.blocked(render_blocked(
                "print the three selections of FG02 LBL09 variants "
                f"(65 → access.avery.label.wizard id {by_count.get(65)}, "
                f"95 → id {by_count.get(95)}, 125 → id {by_count.get(125)}) "
                "and check each DOCX uses its own Avery layout — 60, 90 and "
                "120 slots per sheet — with the right per-page slot count, "
                "page breaks and left-to-right fill order, then compare each "
                "sheet with the v15 baseline output for the same products"))
    finally:
        cleanup_fg02(ctx, rpc, wizards)


@test_case(
    id="TEST-FG02-LBL-010", name="6-up Backtag prints",
    workflow="FG-02", workflow_name="Certificates & Labels",
    module="mmg_stock", priority="P1", kind="API", order=212,
    description="Backtag action always returns avery.label.6; "
                "get_page_groups()==[0,1] for 8 products; page-slot mapping "
                "and description line correct; DOCX render blocked.",
    traceability=trace("TC-LBL-010"))
def test_lbl_010(ctx):
    """Expected v15 outcome: BLOCKED.

    action_export_avery_label_6 returning avery.label.6 regardless of the
    selection size, get_page_groups() == [0, 1] for 8 products, the
    page/slot mapping of check_list_data_6 and the description line are all
    asserted offline and expected to pass on v15; only the rendered 2-page
    DOCX is blocked.
    """
    rpc = ctx.adapter.rpc
    prepare_fg02(ctx, rpc)
    wizards = []
    try:
        with ctx.step("Create 8 variants with display_name and "
                      "description-line data"):
            medium_name = fx(f"{MARK} Watercolor")
            medium = ensure_medium(rpc, medium_name)
            ids_8 = make_label_products(rpc, 8, "BTAG", medium)
            ctx.check("8 fixtures created", 8, len(ids_8))
        with ctx.step("action_export_avery_label_6 returns the 6-per-page "
                      "report"):
            wiz = label_wizard(rpc, ids_8)
            wizards.append(wiz)
            action = rpc.call(LABEL_WIZARD, "action_export_avery_label_6",
                              [wiz], context=REPORT_CTX)
            ctx.check("backtag action (report_name, report_type)",
                      {"report_name": "avery.label.6", "report_type": "py3o"},
                      {key: action.get(key)
                       for key in ("report_name", "report_type")})
        with ctx.step("get_page_groups() == [0, 1] (ceil(8/6) = 2 pages)"):
            pages = rpc.call(LABEL_WIZARD, "get_page_groups", [wiz])
            ctx.check("page groups", [0, 1], pages)
        with ctx.step("Page-slot mapping: (1,1) is the 8th product, (1,2) is "
                      "past the selection"):
            order = rpc.read(LABEL_WIZARD, [wiz],
                             ["product_ids"])[0]["product_ids"]
            eighth_name = rpc.read("product.product", [order[7]],
                                   ["name"])[0]["name"]
            mismatches = {}
            note_mismatch(mismatches, "check_list_data_6(1, 1, 'name')",
                          eighth_name,
                          rpc.call(LABEL_WIZARD, "check_list_data_6",
                                   [wiz], 1, 1, "name"))
            note_mismatch(mismatches, "check_list_data_6(1, 2, 'name')", "",
                          rpc.call(LABEL_WIZARD, "check_list_data_6",
                                   [wiz], 1, 2, "name"))
            ctx.check("page-slot mapping mismatches", {}, mismatches)
        with ctx.step("Description line via check_label_description_6"):
            desc = rpc.call(LABEL_WIZARD, "check_label_description_6",
                            [wiz], 0, 0)
            ctx.check("tag (0,0) description line",
                      label_description(medium_name), desc)
        with ctx.step("Render the DOCX: 6 tags page 1, 2 tags page 2, "
                      "4 empty slots"):
            ctx.blocked(render_blocked(
                f"print the backtags of access.avery.label.wizard id {wiz} "
                "(the 8 FG02 BTAG variants) and check the DOCX carries 6 tags "
                "on page 1 and 2 tags on page 2 with the remaining 4 slots "
                "blank, each tag showing the variant name and the "
                f"'{label_description(medium_name)}' description line"))
    finally:
        cleanup_fg02(ctx, rpc, wizards)


@test_case(
    id="TEST-FG02-LBL-011", name="Label printing works from both template and variant lists",
    workflow="FG-02", workflow_name="Certificates & Labels",
    module="mmg_stock", priority="P1", kind="API", order=213,
    description="All four print server actions exist with the right "
                "bindings; each entry-point method builds a wizard over the "
                "right product set and returns a py3o action; UI download "
                "blocked.",
    traceability=trace("TC-LBL-011"))
def test_lbl_011(ctx):
    """Expected v15 outcome: BLOCKED.

    The four server-action records with their bindings, and each entry-point
    method building an access.avery.label.wizard over the right product set
    and returning the right py3o action, are asserted offline and expected to
    pass on v15. Only the Action-menu download of the rendered document is
    blocked. Both halves are collected: all four server actions and all four
    entry points are compared in one assertion each, so a single wrong
    binding still leaves the rest of the evidence recorded.
    """
    rpc = ctx.adapter.rpc
    prepare_fg02(ctx, rpc)
    wizards = []

    def wizard_products(entry_label, watermark):
        """product_ids of the wizard the entry point just created.

        Identified by the id watermark captured immediately before the call —
        never as "the globally newest access.avery.label.wizard", which is
        unsafe on a shared clone whose transient table other sessions also
        write to. Returns [] when no wizard appeared (recorded as a mismatch
        by the caller instead of aborting the step).
        """
        ids = rpc.search(LABEL_WIZARD, [("id", ">", watermark)],
                         order="id desc")
        wizards.extend(ids)
        ctx.log(f"{entry_label}: wizard id(s) created above watermark "
                f"{watermark}: {ids}")
        if not ids:
            return []
        return rpc.read(LABEL_WIZARD, ids[:1],
                        ["product_ids"])[0]["product_ids"]

    def probe(entry_label, model, method, record_ids, expected_report,
              expected_products):
        """Call one print entry point and return the observed/expected pair
        for the collected assertion."""
        watermark = newest_wizard_id(rpc)
        action = rpc.call(model, method, record_ids, context=REPORT_CTX)
        observed = {"report_name": action.get("report_name"),
                    "report_type": action.get("report_type"),
                    "wizard product_ids": sorted(
                        wizard_products(entry_label, watermark))}
        expected = {"report_name": expected_report, "report_type": "py3o",
                    "wizard product_ids": sorted(expected_products)}
        ctx.log(f"{entry_label}: {observed}")
        return observed, expected

    try:
        with ctx.step("Assert the four server-action records and their "
                      "bindings"):
            variant_model = rpc.ref("product.model_product_product")
            template_model = rpc.ref("product.model_product_template")
            expected = {
                "mmg_stock.action_print_avery_label_from_variant":
                    (variant_model, "action_print_avery_label_from_variant"),
                "mmg_stock.action_print_avery_label_from_template":
                    (template_model, "action_print_avery_label_from_template"),
                "mmg_stock.action_print_avery_label_6_from_variant":
                    (variant_model, "action_print_avery_label_6_from_variant"),
                "mmg_stock.action_print_avery_label_6_from_template":
                    (template_model,
                     "action_print_avery_label_6_from_template"),
            }
            mismatches = {}
            for xmlid, (model_id, method) in expected.items():
                rid = rpc.ref(xmlid)
                if not rid:
                    mismatches[f"{xmlid} (record)"] = {
                        "expected": "resolves to a record", "actual": None}
                    continue
                data = rpc.read("ir.actions.server", [rid],
                                ["state", "binding_model_id",
                                 "binding_view_types", "code"])[0]
                note_mismatch(mismatches, f"{xmlid}.state", "code",
                              data["state"])
                note_mismatch(mismatches, f"{xmlid}.binding_model_id",
                              model_id, m2o_id(data["binding_model_id"]))
                note_mismatch(mismatches, f"{xmlid}.binding_view_types",
                              "list,form", data["binding_view_types"])
                note_mismatch(mismatches, f"{xmlid} code calls {method}()",
                              True, method in (data["code"] or ""))
            ctx.check("server-action mismatches", {}, mismatches)
        with ctx.step("Create a template with one variant plus two standalone "
                      "variants"):
            base_variant, tmpl_name = make_product(rpc, "EntryPoint T")
            tmpl_id = m2o_id(rpc.read("product.product", [base_variant],
                                      ["product_tmpl_id"])[0]
                             ["product_tmpl_id"])
            tmpl_variants = rpc.search("product.product",
                                       [("product_tmpl_id", "=", tmpl_id)])
            std = [make_product(rpc, "EntryPoint V1")[0],
                   make_product(rpc, "EntryPoint V2")[0]]
            ctx.log(f"template {tmpl_id} ('{tmpl_name}') variants "
                    f"{tmpl_variants}; standalone variants {std}")
        results = {}
        with ctx.step("Template-list entry points build wizards on the "
                      "template's variants"):
            results["template label"] = probe(
                "template label entry point", "product.template",
                "action_print_avery_label_from_template", [tmpl_id],
                "avery.label.30", tmpl_variants)
            results["template backtag"] = probe(
                "template backtag entry point", "product.template",
                "action_print_avery_label_6_from_template", [tmpl_id],
                "avery.label.6", tmpl_variants)
        with ctx.step("Variant-list entry points build wizards on the "
                      "selected variants"):
            results["variant label"] = probe(
                "variant label entry point", "product.product",
                "action_print_avery_label_from_variant", std,
                "avery.label.30", std)
            results["variant backtag"] = probe(
                "variant backtag entry point", "product.product",
                "action_print_avery_label_6_from_variant", std,
                "avery.label.6", std)
        with ctx.step("Assert the collected results of all four print entry "
                      "points"):
            ctx.check("print entry-point results",
                      {name: pair[1] for name, pair in results.items()},
                      {name: pair[0] for name, pair in results.items()})
        with ctx.step("UI spot-check: both Action-menu entries download a "
                      "document"):
            ctx.blocked(render_blocked(
                "as Art Cataloguer, open the product.template list and the "
                f"product.product list, select the {MARK} EntryPoint records "
                f"of fixture namespace [{fixture_token()}], and confirm "
                "the Action menu of BOTH lists offers Print Avery Label and "
                "Print Backtag and that each one downloads a document that "
                "opens (the download is served from the rendered py3o output, "
                "which this host cannot produce)"))
    finally:
        cleanup_fg02(ctx, rpc, wizards)


@test_case(
    id="TEST-FG02-SMK-011", name="Certificate / label rendering pipeline alive",
    workflow="FG-02", workflow_name="Certificates & Labels",
    module="mmg_report", priority="P0", kind="API", order=214,
    description="mmg_stock/mmg_report/report_py3o installed; the Avery 30 "
                "report record resolves (py3o/docx) and the wizard action "
                "routes to avery.label.30; the LibreOffice-dependent half "
                "(lo_bin_path, boot-log scan, real DOCX render) is BLOCKED — "
                "the runtime is absent on this host.",
    traceability=trace("TC-SMK-011"))
def test_smk_011(ctx):
    """Expected v15 outcome: BLOCKED.

    The three module states, the Avery 30 report record and the wizard action
    routing are asserted offline and expected to pass on v15. The remaining
    workbook steps (boot-log scan, lo_bin_path non-empty, the real ODT→DOCX
    render) depend on LibreOffice being installed on the Odoo host — a stated
    *precondition* of TC-SMK-011 that this host does not meet, so the verdict
    is BLOCKED with the observed engine state, not FAILED.
    """
    rpc = ctx.adapter.rpc
    prepare_fg02(ctx, rpc)
    wizards = []
    try:
        with ctx.step("Assert module states: mmg_stock, mmg_report, "
                      "report_py3o all installed"):
            rows = rpc.search_read(
                "ir.module.module",
                [("name", "in", ["mmg_stock", "mmg_report", "report_py3o"])],
                ["name", "state"])
            states = {r["name"]: r["state"] for r in rows}
            ctx.check("module states",
                      {"mmg_stock": "installed", "mmg_report": "installed",
                       "report_py3o": "installed"}, states)
        with ctx.step("Assert the Avery 30 report record (report_name, "
                      "report_type, py3o_filetype)"):
            mismatches = {}
            rid = collect_report_record(ctx, "mmg_stock.avery_label_30_report",
                                        {"report_name": "avery.label.30",
                                         "report_type": "py3o",
                                         "py3o_filetype": "docx"}, mismatches)
            ctx.check("Avery 30 report record mismatches", {}, mismatches)
        with ctx.step("Probe the rendering engine on the host (report_py3o "
                      "lo_bin_path / is_py3o_report_not_available)"):
            # Host tooling, not MMG behaviour: report_py3o computes these two
            # from whether a 'libreoffice' binary is on the Odoo host's PATH.
            # The workbook lists the installed runtime as a PRECONDITION of
            # TC-SMK-011, so an absent binary is a BLOCKED precondition, not a
            # product defect — recorded below with the observed values.
            data = rpc.read("ir.actions.report", [rid],
                            ["lo_bin_path",
                             "is_py3o_report_not_available"])[0]
            ctx.log(f"lo_bin_path = {data['lo_bin_path']!r}")
            ctx.log("is_py3o_report_not_available = "
                    f"{data['is_py3o_report_not_available']!r}")
            engine_ready = bool(data["lo_bin_path"]) and not data[
                "is_py3o_report_not_available"]
            ctx.log(f"LibreOffice engine available on this host: "
                    f"{engine_ready}")
        with ctx.step("Print one Avery 30 label: the wizard action routes to "
                      "avery.label.30 / py3o"):
            product, product_name = make_product(rpc, "Smoke Item")
            wiz = label_wizard(rpc, [product])
            wizards.append(wiz)
            action = rpc.call(LABEL_WIZARD, "action_export_avery_label",
                              [wiz], context=REPORT_CTX)
            ctx.log(f"fixture product.product id {product} "
                    f"('{product_name}'), wizard {wiz}")
            ctx.check("label action (report_name, report_type)",
                      {"report_name": "avery.label.30", "report_type": "py3o"},
                      {key: action.get(key)
                       for key in ("report_name", "report_type")})
        with ctx.step("Boot-log scan and the real ODT→DOCX render through "
                      "LibreOffice"):
            if engine_ready:
                # runtime present: only the server-side render itself and the
                # boot-log scan remain outside this transport's reach
                ctx.blocked(render_blocked(
                    f"run odoo-bin -d {ctx.env.db} -u mmg_stock,mmg_report "
                    "--stop-after-init --log-level=info and confirm the log "
                    "holds no traceback, no 'Failed to load' and no "
                    "report_py3o 'libreoffice runtime is required' warning "
                    "for any of the 7 MMG py3o reports, then render "
                    "mmg_stock.avery_label_30_report for "
                    f"access.avery.label.wizard id {wiz} with no "
                    "skip-conversion context and confirm the payload is a "
                    "valid DOCX (zip container starting b'PK') that opens — "
                    "_render_py3o is underscore-private and not callable "
                    "over RPC"))
            else:
                ctx.blocked(libreoffice_blocked(data))
    finally:
        cleanup_fg02(ctx, rpc, wizards)
