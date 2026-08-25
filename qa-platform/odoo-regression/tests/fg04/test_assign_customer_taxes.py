"""FG-04 — Assign Customer Taxes wizard: TC-BLK-001..004.

The "nothing outside the selection changed" workbook baseline-diff is
implemented marker-scoped: the new tax is created fresh per run, so the
global set of records carrying it after the run is exactly what the wizard
wrote (plus the explicit untouched control record).
"""
from framework.registry import test_case
from tests.fg04.common import (MARK, TAX_WIZARD, ensure_sale_tax,
                               expect_user_error, m2o_id, make_templates,
                               sweep_fg04, trace)


@test_case(
    id="TEST-FG04-BLK-001", name="Assign Customer Taxes to selected templates",
    workflow="FG-04", workflow_name="Bulk Wizards",
    module="mmg_sale_assign_customer_taxes", priority="P0", kind="API",
    order=400,
    description="10 selected templates end with exactly the new sale tax "
                "(replace, not append); the picker domain restricts to sale "
                "taxes; the control template and the global count prove "
                "nothing else changed.",
    traceability=trace("TC-BLK-001"))
def test_blk_001(ctx):
    rpc = ctx.adapter.rpc
    with ctx.step("Sweep previous FG-04 fixtures"):
        sweep_fg04(rpc)
    with ctx.step("Create the old/new sale taxes and 10 templates + 1 "
                  "control on the old tax"):
        old_tax = ensure_sale_tax(rpc, f"{MARK} Old Sale Tax", 5.0)
        new_tax = ensure_sale_tax(rpc, f"{MARK} New Sale Tax", 8.25)
        selected = make_templates(rpc, 10, "TaxTmpl", old_tax)
        control = make_templates(rpc, 1, "TaxCtrl", old_tax)[0]
    try:
        with ctx.step("Export the pre-run baseline (id, taxes_id) of the "
                      "selection"):
            baseline = {r["id"]: r["taxes_id"] for r in rpc.read(
                "product.template", selected, ["id", "taxes_id"])}
            for tid, taxes in sorted(baseline.items()):
                ctx.check(f"baseline template {tid} carries the old tax",
                          [old_tax], taxes)
            pre_count = rpc.call("product.template", "search_count",
                                 [("taxes_id", "in", [new_tax])])
            ctx.check("no template carries the new tax pre-run", 0, pre_count)
        with ctx.step("The tax picker only offers sale taxes "
                      "(field domain type_tax_use = 'sale')"):
            info = rpc.call(TAX_WIZARD, "fields_get", ["taxes_id"],
                            attributes=["domain"])
            domain = str(info["taxes_id"].get("domain"))
            ctx.check_true("taxes_id domain restricts to type_tax_use='sale'",
                           "type_tax_use" in domain and "sale" in domain,
                           actual_desc=f"domain: {domain}")
        with ctx.step("Create the wizard over the 10 templates and assign()"):
            wiz = rpc.create(TAX_WIZARD,
                             {"product_tmpl_ids": [(6, 0, selected)],
                              "taxes_id": [(6, 0, [new_tax])]})
            rpc.call(TAX_WIZARD, "assign", [wiz])
        with ctx.step("Every selected template carries exactly the new tax "
                      "(clear-then-link replace semantics)"):
            for row in rpc.read("product.template", selected, ["taxes_id"]):
                ctx.check(f"template {row['id']} taxes replaced",
                          [new_tax], row["taxes_id"])
        with ctx.step("The unselected control template still carries the "
                      "old tax"):
            ctrl = rpc.read("product.template", [control], ["taxes_id"])[0]
            ctx.check("control taxes unchanged", [old_tax], ctrl["taxes_id"])
        with ctx.step("Diff against the baseline: exactly the 10 selected "
                      "rows changed, nothing else"):
            post_count = rpc.call("product.template", "search_count",
                                  [("taxes_id", "in", [new_tax])])
            ctx.check("templates carrying the new tax after the run",
                      10, post_count)
    finally:
        with ctx.step("Cleanup fixtures"):
            sweep_fg04(rpc)


@test_case(
    id="TEST-FG04-BLK-002", name="Assign Customer Taxes defaults to the company sale tax",
    workflow="FG-04", workflow_name="Bulk Wizards",
    module="mmg_sale_assign_customer_taxes", priority="P1", kind="API",
    order=401,
    description="A freshly created wizard pre-fills taxes_id with "
                "env.company.account_sale_tax_id; company config is "
                "snapshotted and restored.",
    traceability=trace("TC-BLK-002"))
def test_blk_002(ctx):
    rpc = ctx.adapter.rpc
    with ctx.step("Sweep previous FG-04 fixtures"):
        sweep_fg04(rpc)
    with ctx.step("Snapshot the acting company's default sale tax"):
        company_id = m2o_id(rpc.read("res.users", [rpc.uid],
                                     ["company_id"])[0]["company_id"])
        original = m2o_id(rpc.read("res.company", [company_id],
                                   ["account_sale_tax_id"])[0]
                          ["account_sale_tax_id"])
        ctx.log(f"company {company_id} account_sale_tax_id = {original}")
    wrote_company = False
    try:
        with ctx.step("Ensure a known company default sale tax"):
            if original:
                known_tax = original
                ctx.log("company already carries a default sale tax — "
                        "used as the known tax without writing config")
            else:
                known_tax = ensure_sale_tax(rpc, f"{MARK} Default Sale Tax",
                                            8.25)
                rpc.write("res.company", [company_id],
                          {"account_sale_tax_id": known_tax})
                wrote_company = True
        with ctx.step("A wizard created with no values pre-fills taxes_id "
                      "with the company default"):
            wiz = rpc.create(TAX_WIZARD, {})
            taxes = rpc.read(TAX_WIZARD, [wiz], ["taxes_id"])[0]["taxes_id"]
            ctx.check("wizard.taxes_id defaults to the company sale tax",
                      [known_tax], taxes)
        ctx.log("UI half (field pre-filled on the Action-menu form) follows "
                "from the same default lambda — asserted at ORM level")
    finally:
        with ctx.step("Restore company config and cleanup"):
            if wrote_company:
                rpc.write("res.company", [company_id],
                          {"account_sale_tax_id": original})
            sweep_fg04(rpc)


@test_case(
    id="TEST-FG04-BLK-003", name="Assign Customer Taxes blocks an empty selection",
    workflow="FG-04", workflow_name="Bulk Wizards",
    module="mmg_sale_assign_customer_taxes", priority="P1", kind="API",
    order=402,
    description="assign() with an empty taxes_id raises UserError 'Missing "
                "Customer Taxes.' and writes nothing — no product is left "
                "untaxed.",
    traceability=trace("TC-BLK-003"))
def test_blk_003(ctx):
    rpc = ctx.adapter.rpc
    with ctx.step("Sweep previous FG-04 fixtures"):
        sweep_fg04(rpc)
    with ctx.step("Create templates carrying a known existing tax"):
        old_tax = ensure_sale_tax(rpc, f"{MARK} Old Sale Tax", 5.0)
        selected = make_templates(rpc, 3, "TaxGuard", old_tax)
    try:
        with ctx.step("Create the wizard and clear the tax field"):
            wiz = rpc.create(TAX_WIZARD,
                             {"product_tmpl_ids": [(6, 0, selected)]})
            rpc.write(TAX_WIZARD, [wiz], {"taxes_id": [(5, 0, 0)]})
            taxes = rpc.read(TAX_WIZARD, [wiz], ["taxes_id"])[0]["taxes_id"]
            ctx.check("wizard.taxes_id cleared", [], taxes)
        with ctx.step("assign() raises UserError 'Missing Customer Taxes.'"):
            raised, message = expect_user_error(
                rpc.call, TAX_WIZARD, "assign", [wiz])
            ctx.check_true("guard raised",
                           raised and "Missing Customer Taxes." in message,
                           actual_desc=message)
        with ctx.step("No write happened — every template keeps its "
                      "previous taxes"):
            for row in rpc.read("product.template", selected, ["taxes_id"]):
                ctx.check(f"template {row['id']} keeps the old tax",
                          [old_tax], row["taxes_id"])
    finally:
        with ctx.step("Cleanup fixtures"):
            sweep_fg04(rpc)


@test_case(
    id="TEST-FG04-BLK-004", name="Assign Customer Taxes works from the variant list too",
    workflow="FG-04", workflow_name="Bulk Wizards",
    module="mmg_sale_assign_customer_taxes", priority="P2", kind="API",
    order=403,
    description="The product_ids branch of assign() replaces taxes on the "
                "selected variants with the same clear-then-link semantics; "
                "variants outside the selection unchanged.",
    traceability=trace("TC-BLK-004"))
def test_blk_004(ctx):
    rpc = ctx.adapter.rpc
    with ctx.step("Sweep previous FG-04 fixtures"):
        sweep_fg04(rpc)
    with ctx.step("Create taxes and templates; resolve their variants"):
        old_tax = ensure_sale_tax(rpc, f"{MARK} Old Sale Tax", 5.0)
        new_tax = ensure_sale_tax(rpc, f"{MARK} New Sale Tax", 8.25)
        tmpl_selected = make_templates(rpc, 5, "TaxVar", old_tax)
        tmpl_control = make_templates(rpc, 1, "TaxVarCtrl", old_tax)[0]
        variants = rpc.search("product.product",
                              [("product_tmpl_id", "in", tmpl_selected)])
        control_variant = rpc.search("product.product",
                                     [("product_tmpl_id", "=",
                                       tmpl_control)])[0]
        ctx.check("five variants selected", 5, len(variants))
    try:
        with ctx.step("Create the wizard over the variants "
                      "(default_product_ids branch) and assign()"):
            wiz = rpc.create(TAX_WIZARD,
                             {"product_ids": [(6, 0, variants)],
                              "taxes_id": [(6, 0, [new_tax])]})
            rpc.call(TAX_WIZARD, "assign", [wiz])
        with ctx.step("Each selected variant carries exactly the new tax"):
            for row in rpc.read("product.product", variants, ["taxes_id"]):
                ctx.check(f"variant {row['id']} taxes replaced",
                          [new_tax], row["taxes_id"])
        with ctx.step("Variants outside the selection are unchanged"):
            ctrl = rpc.read("product.product", [control_variant],
                            ["taxes_id"])[0]
            ctx.check("control variant keeps the old tax",
                      [old_tax], ctrl["taxes_id"])
            count = rpc.call("product.product", "search_count",
                             [("taxes_id", "in", [new_tax])])
            ctx.check("variants carrying the new tax", 5, count)
    finally:
        with ctx.step("Cleanup fixtures"):
            sweep_fg04(rpc)
