"""FG-04 — cross-wizard behaviour: TC-BLK-013, -015, -016, -017, -018.

TC-BLK-013 (workbook type UI/tour) is implemented at the binding-record
level: the Action-menu entries are rendered from the act_window binding
records (binding_model_id / binding_view_types), so asserting those records
asserts menu presence deterministically without a browser (documented
adaptation).

TC-BLK-017 asserts the confirmed FG-04 ACL matrix (v19 target state): on the
v15 baseline the wizards are open to base.group_user, so the denial
assertions FAIL — the immutable workbook expectation, classified FIXED when
v19 passes. The RPC denial probe uses the platform's JSON-RPC call_kw
transport (the /web/dataset/call_kw equivalent).
"""
from framework.qa_fixtures import ensure_qa_user, rpc_as_qa_user
from framework.registry import test_case
from tests.fg04.common import (fixture_token, fx,  # noqa: F401
                               CATEG_WIZARD, FG04_MANAGER_LOGIN,
                               FG04_MANAGER_PASSWORD, FP_WIZARD, MARK,
                               TAX_WIZARD, TYPE_WIZARD, WEB_CATEG_WIZARD,
                               ensure_category, ensure_fg04_manager,
                               ensure_fiscal_position, ensure_sale_tax,
                               expect_user_error, m2o_id, make_partners,
                               make_templates, customer_type_method,
                               rpc_session, run_assign_product_categ,
                               sweep_fg04, trace)

ALL_WIZARDS = [TAX_WIZARD, FP_WIZARD, CATEG_WIZARD, WEB_CATEG_WIZARD,
               TYPE_WIZARD]


@test_case(
    id="TEST-FG04-BLK-013", name="Each wizard's menu/Action entry appears on the right list view",
    workflow="FG-04", workflow_name="Bulk Wizards",
    module="all mmg bulk wizards", priority="P1", kind="API", order=411,
    description="The five modules bind exactly 6 act_windows on the correct "
                "list models (customer taxes x2, fiscal position, product "
                "category, website extra category, customer type); the "
                "seventh menu entry is attributed to the mmg_stock print "
                "server actions; no entry on a wrong model.",
    traceability=trace("TC-BLK-013"))
def test_blk_013(ctx):
    rpc = ctx.adapter.rpc
    tmpl_model = rpc.ref("product.model_product_template")
    var_model = rpc.ref("product.model_product_product")
    partner_model = rpc.ref("base.model_res_partner")

    def bindings(res_model):
        rows = rpc.search_read(
            "ir.actions.act_window",
            [("res_model", "=", res_model),
             ("binding_model_id", "!=", False)],
            ["name", "binding_model_id", "binding_view_types"])
        return rows

    expected = {
        TAX_WIZARD: sorted([tmpl_model, var_model]),
        FP_WIZARD: [partner_model],
        CATEG_WIZARD: [var_model],
        WEB_CATEG_WIZARD: [var_model],
        TYPE_WIZARD: [partner_model],
    }
    total = 0
    with ctx.step("Each wizard binds its Action-menu entry to the right "
                  "list model (binding_view_types 'list')"):
        for wizard_model, exp_models in expected.items():
            rows = bindings(wizard_model)
            total += len(rows)
            actual_models = sorted(m2o_id(r["binding_model_id"])
                                   for r in rows)
            ctx.check(f"{wizard_model} binding models", exp_models,
                      actual_models)
            for row in rows:
                ctx.check_true(
                    f"{wizard_model} binding '{row['name']}' targets list "
                    "views",
                    "list" in (row["binding_view_types"] or ""),
                    actual_desc=f"binding_view_types="
                                f"{row['binding_view_types']!r}")
    with ctx.step("The five FG-04 modules bind exactly 6 act_windows"):
        ctx.check("FG-04 act_window binding count", 6, total)
    with ctx.step("Reconcile the workbook's '7 actions': the seventh entry "
                  "is the mmg_stock product-list print server action "
                  "(FG-01/FG-02 scope)"):
        print_actions = rpc.search_read(
            "ir.actions.server",
            [("binding_model_id", "in", [var_model, tmpl_model]),
             ("name", "in", ["Print Avery Label", "Print Backtag"])],
            ["name", "binding_model_id"])
        ctx.check_true("the non-FG-04 seventh entry is attributed "
                       "(mmg_stock print actions present)",
                       len(print_actions) >= 1,
                       actual_desc=f"{len(print_actions)} mmg_stock print "
                                   f"server actions bound to product lists")
        for row in print_actions:
            ctx.log(f"attributed: {row['name']} on "
                    f"{row['binding_model_id']}")
    with ctx.step("Negative check: no wizard entry on a wrong model's list"):
        for wizard_model in (FP_WIZARD, TYPE_WIZARD):
            models = [m2o_id(r["binding_model_id"])
                      for r in bindings(wizard_model)]
            ctx.check_true(f"{wizard_model} not bound to product lists",
                           tmpl_model not in models
                           and var_model not in models,
                           actual_desc=f"bound ir.model ids: {models}")
        for wizard_model in (TAX_WIZARD, CATEG_WIZARD, WEB_CATEG_WIZARD):
            models = [m2o_id(r["binding_model_id"])
                      for r in bindings(wizard_model)]
            ctx.check_true(f"{wizard_model} not bound to Contacts",
                           partner_model not in models,
                           actual_desc=f"bound ir.model ids: {models}")


@test_case(
    id="TEST-FG04-BLK-015", name="Bulk wizard respects the current selection only",
    workflow="FG-04", workflow_name="Bulk Wizards",
    module="all mmg bulk wizards", priority="P0", kind="API", order=412,
    description="For all five wizards: every selected record carries the "
                "new value, the identical-valued control record outside the "
                "selection is unchanged, and the count of records carrying "
                "the new value equals exactly the selection size.",
    traceability=trace("TC-BLK-015"))
def test_blk_015(ctx):
    rpc = ctx.adapter.rpc
    with ctx.step("Sweep previous FG-04 fixtures"):
        sweep_fg04(rpc)
    with ctx.step("Create the per-wizard fixture sets (3 selected + 1 "
                  "identical control each)"):
        old_tax = ensure_sale_tax(rpc, f"{MARK} Old Sale Tax", 5.0)
        new_tax = ensure_sale_tax(rpc, f"{MARK} Sel Sale Tax", 8.25)
        tax_sel = make_templates(rpc, 3, "SelTax", old_tax)
        tax_ctrl = make_templates(rpc, 1, "SelTaxCtrl", old_tax)[0]

        old_fp = ensure_fiscal_position(rpc, f"{MARK} Old Position")
        new_fp = ensure_fiscal_position(rpc, f"{MARK} Sel Position")
        fp_sel = make_partners(rpc, 3, "SelFP",
                               {"property_account_position_id": old_fp})
        fp_ctrl = make_partners(rpc, 1, "SelFPCtrl",
                                {"property_account_position_id": old_fp})[0]

        old_categ = ensure_category(rpc, f"{MARK} Old Category")
        new_categ = ensure_category(rpc, f"{MARK} Sel Category")
        cat_sel = rpc.create("product.product",
                             [{"name": f"{MARK} SelCat {i:03d}",
                               "categ_id": old_categ} for i in (1, 2, 3)])
        cat_ctrl = rpc.create("product.product",
                              {"name": f"{MARK} SelCatCtrl 001",
                               "categ_id": old_categ})

        web_existing = ensure_category(rpc, f"{MARK} SelWebExisting")
        web_new = ensure_category(rpc, f"{MARK} SelWebNew")
        web_sel = rpc.create("product.product",
                             [{"name": f"{MARK} SelWeb {i:03d}",
                               "x_categ_ids": [(6, 0, [web_existing])]}
                              for i in (1, 2, 3)])
        web_ctrl = rpc.create("product.product",
                              {"name": f"{MARK} SelWebCtrl 001",
                               "x_categ_ids": [(6, 0, [web_existing])]})

        type_sel = make_partners(rpc, 3, "SelType",
                                 {"x_type": fx(f"{MARK}-SEL-OLD")})
        type_ctrl = make_partners(rpc, 1, "SelTypeCtrl",
                                  {"x_type": fx(f"{MARK}-SEL-OLD")})[0]
    try:
        with ctx.step("Assign Customer Taxes over the selection only"):
            wiz = rpc.create(TAX_WIZARD,
                             {"product_tmpl_ids": [(6, 0, tax_sel)],
                              "taxes_id": [(6, 0, [new_tax])]})
            rpc.call(TAX_WIZARD, "assign", [wiz])
            for row in rpc.read("product.template", tax_sel, ["taxes_id"]):
                ctx.check(f"selected template {row['id']} carries the new "
                          "tax", [new_tax], row["taxes_id"])
            ctrl = rpc.read("product.template", [tax_ctrl], ["taxes_id"])[0]
            ctx.check("tax control unchanged", [old_tax], ctrl["taxes_id"])
            ctx.check("count carrying the new tax", 3,
                      rpc.call("product.template", "search_count",
                               [("taxes_id", "in", [new_tax])]))
        with ctx.step("Assign Fiscal Position over the selection only"):
            wiz = rpc.create(FP_WIZARD,
                             {"partner_ids": [(6, 0, fp_sel)],
                              "fiscal_position_id": new_fp})
            rpc.call(FP_WIZARD, "assign", [wiz])
            for row in rpc.read("res.partner", fp_sel,
                                ["property_account_position_id"]):
                ctx.check(f"selected partner {row['id']} carries the new "
                          "position", new_fp,
                          m2o_id(row["property_account_position_id"]))
            ctrl = rpc.read("res.partner", [fp_ctrl],
                            ["property_account_position_id"])[0]
            ctx.check("fiscal-position control unchanged", old_fp,
                      m2o_id(ctrl["property_account_position_id"]))
            ctx.check("count carrying the new position", 3,
                      rpc.call("res.partner", "search_count",
                               [("property_account_position_id", "=",
                                 new_fp)]))
        with ctx.step("Assign Product Category over the selection only "
                      "(via the confirmation step where the version has "
                      "one)"):
            sel_ctx = {"active_model": "product.product",
                       "active_ids": cat_sel}
            wiz = rpc.call(CATEG_WIZARD, "create",
                           {"product_categ_id": new_categ}, context=sel_ctx)
            run_assign_product_categ(ctx, rpc, wiz, sel_ctx)
            for row in rpc.read("product.product", cat_sel, ["categ_id"]):
                ctx.check(f"selected product {row['id']} carries the new "
                          "category", new_categ, m2o_id(row["categ_id"]))
            ctrl = rpc.read("product.product", [cat_ctrl], ["categ_id"])[0]
            ctx.check("category control unchanged", old_categ,
                      m2o_id(ctrl["categ_id"]))
            ctx.check("count carrying the new category", 3,
                      rpc.call("product.product", "search_count",
                               [("categ_id", "=", new_categ)]))
        with ctx.step("Assign Website Extra Category over the selection "
                      "only"):
            sel_ctx = {"active_model": "product.product",
                       "active_ids": web_sel}
            wiz = rpc.call(WEB_CATEG_WIZARD, "create",
                           {"product_categ_ids": [(6, 0, [web_new])]},
                           context=sel_ctx)
            rpc.call(WEB_CATEG_WIZARD, "action_assign_website_extra_categ",
                     [wiz], context=sel_ctx)
            for row in rpc.read("product.product", web_sel, ["x_categ_ids"]):
                ctx.check(f"selected product {row['id']} x_categ_ids",
                          sorted([web_existing, web_new]),
                          sorted(row["x_categ_ids"]))
            ctrl = rpc.read("product.product", [web_ctrl],
                            ["x_categ_ids"])[0]
            ctx.check("website-category control unchanged", [web_existing],
                      ctrl["x_categ_ids"])
            ctx.check("count carrying the new website category", 3,
                      rpc.call("product.product", "search_count",
                               [("x_categ_ids", "in", [web_new])]))
        with ctx.step("Update Customer Type over the selection only"):
            wiz = rpc.create(TYPE_WIZARD,
                             {"partner_ids": [(6, 0, type_sel)],
                              "new_customer_type": fx(f"{MARK}-SEL-TYPE")})
            rpc.call(TYPE_WIZARD, customer_type_method(ctx), [wiz])
            for row in rpc.read("res.partner", type_sel, ["x_type"]):
                ctx.check(f"selected partner {row['id']} x_type",
                          fx(f"{MARK}-SEL-TYPE"), row["x_type"])
            ctrl = rpc.read("res.partner", [type_ctrl], ["x_type"])[0]
            ctx.check("customer-type control unchanged", fx(f"{MARK}-SEL-OLD"),
                      ctrl["x_type"])
            ctx.check("count carrying the new customer type", 3,
                      rpc.call("res.partner", "search_count",
                               [("x_type", "=", fx(f"{MARK}-SEL-TYPE"))]))
    finally:
        with ctx.step("Cleanup fixtures"):
            sweep_fg04(rpc)


@test_case(
    id="TEST-FG04-BLK-016", name='Bulk wizard with "select all" across a filtered domain',
    workflow="FG-04", workflow_name="Bulk Wizards",
    module="all mmg bulk wizards", priority="P1", kind="API", order=413,
    description="The wizard write covers the whole 120-record filtered "
                "domain (past the 80-row first list page), records outside "
                "the filter untouched.",
    traceability=trace("TC-BLK-016"))
def test_blk_016(ctx):
    rpc = ctx.adapter.rpc
    with ctx.step("Sweep previous FG-04 fixtures"):
        sweep_fg04(rpc)
    with ctx.step("Create 120 BLKFILTER-marked templates (more than one "
                  "80-row list page) and 2 non-matching controls"):
        old_tax = ensure_sale_tax(rpc, f"{MARK} Old Sale Tax", 5.0)
        new_tax = ensure_sale_tax(rpc, f"{MARK} New Sale Tax", 8.25)
        rpc.create("product.template",
                   [{"name": fx(f"{MARK} BLKFILTER {i:03d}"),
                     "taxes_id": [(6, 0, [old_tax])]}
                    for i in range(1, 121)])
        controls = make_templates(rpc, 2, "TaxFilterCtrl", old_tax)
    try:
        with ctx.step("The filtered domain resolves all 120 records (what "
                      "the 'Select all 120' banner feeds into active_ids)"):
            filtered = rpc.search("product.template",
                                  [("name", "like", f"{MARK} BLKFILTER%[{fixture_token()}]")])
            ctx.check("filtered selection size", 120, len(filtered))
        with ctx.step("Run Assign Customer Taxes over the whole filtered "
                      "selection"):
            wiz = rpc.create(TAX_WIZARD,
                             {"product_tmpl_ids": [(6, 0, filtered)],
                              "taxes_id": [(6, 0, [new_tax])]})
            rpc.call(TAX_WIZARD, "assign", [wiz])
        with ctx.step("All 120 filtered templates carry the tax — "
                      "explicitly including rows 80..119 beyond the first "
                      "list page"):
            count = rpc.call("product.template", "search_count",
                             [("name", "like", f"{MARK} BLKFILTER%[{fixture_token()}]"),
                              ("taxes_id", "in", [new_tax])])
            ctx.check("filtered templates carrying the new tax", 120, count)
            beyond_page = filtered[80:120]
            for row in rpc.read("product.template", beyond_page,
                                ["taxes_id"]):
                ctx.check(f"template {row['id']} (beyond page 1) carries "
                          "the new tax", [new_tax], row["taxes_id"])
        with ctx.step("Templates outside the filter are unchanged"):
            for row in rpc.read("product.template", controls, ["taxes_id"]):
                ctx.check(f"control template {row['id']} keeps the old tax",
                          [old_tax], row["taxes_id"])
            total = rpc.call("product.template", "search_count",
                             [("taxes_id", "in", [new_tax])])
            ctx.check("nothing outside the filtered set was written",
                      120, total)
    finally:
        with ctx.step("Cleanup fixtures"):
            sweep_fg04(rpc)


@test_case(
    id="TEST-FG04-BLK-017", name="ACL: a non-privileged user cannot run the tax/fiscal wizards",
    workflow="FG-04", workflow_name="Bulk Wizards",
    module="all mmg bulk wizards", priority="P1", kind="API", order=414,
    description="v19 target ACL matrix: a base.group_user-only user is "
                "denied the tax/fiscal wizards (RPC call_kw), the binding "
                "act_windows carry manager groups_id, the five modules' ACL "
                "rows match the matrix; a manager user passes. Expected "
                "v15 baseline FAIL (wizards open to base.group_user on "
                "v15).",
    traceability=trace("TC-BLK-017"))
def test_blk_017(ctx):
    rpc = ctx.adapter.rpc
    with ctx.step("Sweep previous FG-04 fixtures"):
        sweep_fg04(rpc)
    with ctx.step("Ensure the plain internal user (base.group_user only)"):
        ensure_qa_user(rpc)
        plain = rpc_as_qa_user(ctx.env)
    with ctx.step("Plain user is denied create on the customer-taxes wizard "
                  "(call_kw over the JSON-RPC endpoint — the "
                  "/web/dataset/call_kw equivalent)"):
        raised, message = expect_user_error(plain.create, TAX_WIZARD, {})
        ctx.check_true("assign.customer.taxes.wizard create denied "
                       "(AccessError)",
                       raised and ("access" in message.lower()
                                   or "not allowed" in message.lower()),
                       actual_desc=message
                       if raised else "created — no access error")
    with ctx.step("Plain user is denied create on the fiscal-position "
                  "wizard"):
        raised, message = expect_user_error(plain.create, FP_WIZARD, {})
        ctx.check_true("assign.fiscal.position.wizard create denied "
                       "(AccessError)",
                       raised and ("access" in message.lower()
                                   or "not allowed" in message.lower()),
                       actual_desc=message
                       if raised else "created — no access error")
    ctx.log("ORM double-check (workbook step 3) is the same call_kw path — "
            "covered by the two denials above")
    with ctx.step("The binding act_windows carry the manager groups_id "
                  "(hides the Action-menu entries)"):
        group_expect = {
            TAX_WIZARD: rpc.ref("account.group_account_manager"),
            FP_WIZARD: rpc.ref("account.group_account_manager"),
            CATEG_WIZARD: rpc.ref("stock.group_stock_manager"),
            WEB_CATEG_WIZARD: None,  # e-commerce/system manager — xmlid not
                                     # pinned by the matrix; assert non-empty
            TYPE_WIZARD: rpc.ref("sales_team.group_sale_manager"),
        }
        for wizard_model, expected_group in group_expect.items():
            rows = rpc.search_read(
                "ir.actions.act_window",
                [("res_model", "=", wizard_model),
                 ("binding_model_id", "!=", False)], ["name", "groups_id"])
            for row in rows:
                if expected_group:
                    ctx.check_true(
                        f"{wizard_model} binding '{row['name']}' restricted "
                        "to the matrix group",
                        expected_group in row["groups_id"],
                        actual_desc=f"groups_id={row['groups_id']}")
                else:
                    ctx.check_true(
                        f"{wizard_model} binding '{row['name']}' carries a "
                        "non-empty groups_id",
                        bool(row["groups_id"]),
                        actual_desc=f"groups_id={row['groups_id']}")
    with ctx.step("The five modules' ACL rows match the manager matrix (no "
                  "wizard on base.group_user full CRUD, no empty-group "
                  "row)"):
        base_user_gid = rpc.ref("base.group_user")
        rows = rpc.search_read("ir.model.access",
                               [("model_id.model", "in", ALL_WIZARDS)],
                               ["name", "model_id", "group_id",
                                "perm_write", "perm_create", "perm_unlink"])
        offenders = []
        for row in rows:
            gid = m2o_id(row["group_id"])
            full_crud = (row["perm_write"] and row["perm_create"]
                         and row["perm_unlink"])
            if not gid:
                offenders.append(f"{row['name']}: empty group")
            elif gid == base_user_gid and full_crud:
                offenders.append(f"{row['name']}: base.group_user full CRUD")
        ctx.check("ACL offenders (empty group / base.group_user full CRUD)",
                  [], offenders)
    with ctx.step("Positive control: a manager-group user runs both wizards "
                  "successfully"):
        ensure_fg04_manager(rpc)
        manager = rpc_session(ctx.env, FG04_MANAGER_LOGIN,
                              FG04_MANAGER_PASSWORD)
        new_tax = ensure_sale_tax(rpc, f"{MARK} New Sale Tax", 8.25)
        tmpl = make_templates(rpc, 1, "AclTmpl", new_tax)[0]
        partner = make_partners(rpc, 1, "AclPartner")[0]
        fp = ensure_fiscal_position(rpc, f"{MARK} Acl Position")
        try:
            wiz = manager.create(TAX_WIZARD,
                                 {"product_tmpl_ids": [(6, 0, [tmpl])],
                                  "taxes_id": [(6, 0, [new_tax])]})
            manager.call(TAX_WIZARD, "assign", [wiz])
            ctx.check("manager ran the tax wizard",
                      [new_tax],
                      rpc.read("product.template", [tmpl],
                               ["taxes_id"])[0]["taxes_id"])
            wiz = manager.create(FP_WIZARD,
                                 {"partner_ids": [(6, 0, [partner])],
                                  "fiscal_position_id": fp})
            manager.call(FP_WIZARD, "assign", [wiz])
            ctx.check("manager ran the fiscal-position wizard", fp,
                      m2o_id(rpc.read("res.partner", [partner],
                                      ["property_account_position_id"])[0]
                             ["property_account_position_id"]))
        finally:
            sweep_fg04(rpc)


@test_case(
    id="TEST-FG04-BLK-018", name="Wizard writes are attributable",
    workflow="FG-04", workflow_name="Bulk Wizards",
    module="all mmg bulk wizards", priority="P2", kind="API", order=415,
    description="write_uid is the acting manager user and write_date is "
                "refreshed on every record a wizard writes (tax wizard + "
                "customer-type spot-check); the no-audit-trail gap is "
                "recorded, not asserted.",
    traceability=trace("TC-BLK-018"))
def test_blk_018(ctx):
    rpc = ctx.adapter.rpc
    with ctx.step("Sweep previous FG-04 fixtures"):
        sweep_fg04(rpc)
    with ctx.step("Ensure the dedicated manager user (id differs from the "
                  "setup user) and authenticate a session"):
        manager_uid = ensure_fg04_manager(rpc)
        ctx.check_true("manager differs from the setup user",
                       manager_uid != rpc.uid,
                       actual_desc=f"manager={manager_uid}, setup={rpc.uid}")
        manager = rpc_session(ctx.env, FG04_MANAGER_LOGIN,
                              FG04_MANAGER_PASSWORD)
    with ctx.step("Create fixtures as the setup user and capture pre-run "
                  "write metadata"):
        old_tax = ensure_sale_tax(rpc, f"{MARK} Old Sale Tax", 5.0)
        new_tax = ensure_sale_tax(rpc, f"{MARK} New Sale Tax", 8.25)
        templates = make_templates(rpc, 3, "AttribTax", old_tax)
        partners = make_partners(rpc, 2, "AttribType")
        pre = {r["id"]: (m2o_id(r["write_uid"]), r["write_date"])
               for r in rpc.read("product.template", templates,
                                 ["write_uid", "write_date"])}
        for tid, (uid, date) in pre.items():
            ctx.log(f"pre-run template {tid}: write_uid={uid}, "
                    f"write_date={date}")
    try:
        with ctx.step("Run Assign Customer Taxes as the manager (the "
                      "wizard's server-side create_date is the 'before' "
                      "timestamp)"):
            wiz = manager.create(TAX_WIZARD,
                                 {"product_tmpl_ids": [(6, 0, templates)],
                                  "taxes_id": [(6, 0, [new_tax])]})
            before = manager.read(TAX_WIZARD, [wiz],
                                  ["create_date"])[0]["create_date"]
            manager.call(TAX_WIZARD, "assign", [wiz])
        with ctx.step("Every written template carries write_uid == manager "
                      "and a refreshed write_date"):
            for row in rpc.read("product.template", templates,
                                ["write_uid", "write_date", "taxes_id"]):
                ctx.check(f"template {row['id']} write_uid", manager_uid,
                          m2o_id(row["write_uid"]))
                ctx.check_true(
                    f"template {row['id']} write_date refreshed (>= before)",
                    row["write_date"] >= before,
                    actual_desc=f"write_date={row['write_date']}, "
                                f"before={before}")
                ctx.check(f"template {row['id']} carries the new tax",
                          [new_tax], row["taxes_id"])
        with ctx.step("Spot-check a second wizard: Update Customer Type as "
                      "the manager"):
            wiz = manager.create(TYPE_WIZARD,
                                 {"partner_ids": [(6, 0, partners)],
                                  "new_customer_type": fx(f"{MARK}-ATTRIB")})
            before2 = manager.read(TYPE_WIZARD, [wiz],
                                   ["create_date"])[0]["create_date"]
            manager.call(TYPE_WIZARD, customer_type_method(ctx), [wiz])
            for row in rpc.read("res.partner", partners,
                                ["write_uid", "write_date", "x_type"]):
                ctx.check(f"partner {row['id']} write_uid", manager_uid,
                          m2o_id(row["write_uid"]))
                ctx.check_true(
                    f"partner {row['id']} write_date refreshed (>= before)",
                    row["write_date"] >= before2,
                    actual_desc=f"write_date={row['write_date']}, "
                                f"before={before2}")
                ctx.check(f"partner {row['id']} x_type written",
                          fx(f"{MARK}-ATTRIB"), row["x_type"])
        ctx.log("known gap (recorded, unchanged from v15): only the LAST "
                "writer is captured — previous field values are not "
                "retained anywhere (no audit trail / chatter of old "
                "values), so a bulk mistake is attributable but not "
                "reversible from data")
    finally:
        with ctx.step("Cleanup fixtures"):
            sweep_fg04(rpc)
