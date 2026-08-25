"""FG-04 — Assign Product Category & Assign Website Extra Category wizards:
TC-BLK-008, TC-BLK-009.

Both wizards read the selection from context active_ids; over RPC the
context is passed on the create AND on every method call (the
TransactionCase with_context equivalent).

Expected v15 baseline FAILs (immutable workbook expectations describing the
v19 port — they classify as FIXED when v19 passes):
* TC-BLK-008 asserts the v19 two-state confirmation gate (state 'select',
  UserError on direct apply, action_show_confirmation, confirm_message) —
  the v15 wizard has no gate;
* TC-BLK-009's final guard step asserts UserError 'Missing Website Extra
  Category.' on an empty pick — the v15 wizard is a silent no-op there.
"""
from framework.registry import test_case
from tests.fg04.common import (CATEG_WIZARD, MARK, WEB_CATEG_WIZARD,
                               ensure_category, expect_user_error, m2o_id,
                               sweep_fg04, trace)


@test_case(
    id="TEST-FG04-BLK-008", name="Assign Product Category replaces categ_id",
    workflow="FG-04", workflow_name="Bulk Wizards",
    module="mmg_assign_product_category", priority="P1", kind="API",
    order=407,
    description="Two-state confirmation gates the categ_id write (v19 "
                "target — expected v15 baseline FAIL at the gate); the "
                "apply replaces categ_id on exactly the selection.",
    traceability=trace("TC-BLK-008"))
def test_blk_008(ctx):
    rpc = ctx.adapter.rpc
    with ctx.step("Sweep previous FG-04 fixtures"):
        sweep_fg04(rpc)
    with ctx.step("Create the old/new categories and 5 products + 1 control "
                  "on the old category"):
        old_categ = ensure_category(rpc, f"{MARK} Old Category")
        new_categ = ensure_category(rpc, f"{MARK} New Category")
        selected = rpc.create("product.product",
                              [{"name": f"{MARK} Categ {i:03d}",
                                "categ_id": old_categ}
                               for i in range(1, 6)])
        control = rpc.create("product.product",
                             {"name": f"{MARK} CategCtrl 001",
                              "categ_id": old_categ})
    sel_ctx = {"active_model": "product.product", "active_ids": selected}
    try:
        with ctx.step("Create the wizard with the list-selection context"):
            wiz = rpc.call(CATEG_WIZARD, "create",
                           {"product_categ_id": new_categ}, context=sel_ctx)
        with ctx.step("Wizard opens on the picker state 'select' (two-state "
                      "confirmation flow)"):
            if rpc.field_exists(CATEG_WIZARD, "state"):
                state = rpc.read(CATEG_WIZARD, [wiz], ["state"])[0]["state"]
            else:
                state = ("field 'state' missing — this wizard has no "
                         "confirmation flow (v15 behaviour)")
            ctx.check("wizard.state", "select", state)
        with ctx.step("Direct apply from state 'select' raises UserError "
                      "and writes nothing"):
            raised, message = expect_user_error(
                rpc.call, CATEG_WIZARD, "action_assign_product_categ",
                [wiz], context=sel_ctx)
            ctx.check_true("apply from 'select' rejected (UserError)",
                           raised, actual_desc=message)
            for row in rpc.read("product.product", selected, ["categ_id"]):
                ctx.check(f"product {row['id']} categ_id untouched by the "
                          "rejected apply", old_categ, m2o_id(row["categ_id"]))
        with ctx.step("action_show_confirmation moves to 'confirm' and the "
                      "message names the category and the count"):
            rpc.call(CATEG_WIZARD, "action_show_confirmation", [wiz],
                     context=sel_ctx)
            data = rpc.read(CATEG_WIZARD, [wiz],
                            ["state", "confirm_message"])[0]
            ctx.check("wizard.state after confirmation step", "confirm",
                      data["state"])
            new_name = rpc.read("product.category", [new_categ],
                                ["display_name"])[0]["display_name"]
            message = data["confirm_message"] or ""
            ctx.check_true("confirm_message names the category and the "
                           "count '5'",
                           new_name in message and "5" in message,
                           actual_desc=message)
        with ctx.step("Apply from 'confirm' — the gated write runs"):
            rpc.call(CATEG_WIZARD, "action_assign_product_categ", [wiz],
                     context=sel_ctx)
        with ctx.step("All 5 selected products carry the new category "
                      "(previous category replaced)"):
            for row in rpc.read("product.product", selected, ["categ_id"]):
                ctx.check(f"product {row['id']} categ_id replaced",
                          new_categ, m2o_id(row["categ_id"]))
            count = rpc.call("product.product", "search_count",
                             [("categ_id", "=", new_categ)])
            ctx.check("products carrying the new category", 5, count)
        with ctx.step("The unselected control product still has the old "
                      "category"):
            ctrl = rpc.read("product.product", [control], ["categ_id"])[0]
            ctx.check("control categ_id unchanged", old_categ,
                      m2o_id(ctrl["categ_id"]))
    finally:
        with ctx.step("Cleanup fixtures"):
            sweep_fg04(rpc)


@test_case(
    id="TEST-FG04-BLK-009", name="Assign Website Extra Category adds to the set and recomputes",
    workflow="FG-04", workflow_name="Bulk Wizards",
    module="mmg_assign_website_extra_category", priority="P1", kind="API",
    order=408,
    description="Two categories ADDED on top of the existing x_categ_ids "
                "set; the stored website_extra_categories compute refreshes; "
                "control untouched; empty-pick guard (v19 target — expected "
                "v15 baseline FAIL on the final step).",
    traceability=trace("TC-BLK-009"))
def test_blk_009(ctx):
    rpc = ctx.adapter.rpc
    with ctx.step("Sweep previous FG-04 fixtures"):
        sweep_fg04(rpc)
    with ctx.step("Create three categories and 5 products + 1 control with "
                  "the existing web category"):
        existing = ensure_category(rpc, f"{MARK} WebExisting")
        new_1 = ensure_category(rpc, f"{MARK} WebNew1")
        new_2 = ensure_category(rpc, f"{MARK} WebNew2")
        selected = rpc.create("product.product",
                              [{"name": f"{MARK} WebCat {i:03d}",
                                "x_categ_ids": [(6, 0, [existing])]}
                               for i in range(1, 6)])
        control = rpc.create("product.product",
                             {"name": f"{MARK} WebCatCtrl 001",
                              "x_categ_ids": [(6, 0, [existing])]})
        control_text = rpc.read("product.product", [control],
                                ["website_extra_categories"])[0][
                                    "website_extra_categories"]

    def joined_display_names(categ_ids):
        rows = rpc.read("product.category", categ_ids, ["display_name"])
        return ", ".join(r["display_name"] for r in rows)

    sel_ctx = {"active_model": "product.product", "active_ids": selected}
    try:
        with ctx.step("Create the wizard with the selection context and the "
                      "two new categories, then run the assign action"):
            wiz = rpc.call(WEB_CATEG_WIZARD, "create",
                           {"product_categ_ids": [(6, 0, [new_1, new_2])]},
                           context=sel_ctx)
            rpc.call(WEB_CATEG_WIZARD, "action_assign_website_extra_categ",
                     [wiz], context=sel_ctx)
        with ctx.step("The two categories were ADDED on top of the existing "
                      "set on all 5 products"):
            for row in rpc.read("product.product", selected, ["x_categ_ids"]):
                ctx.check(f"product {row['id']} x_categ_ids",
                          sorted([existing, new_1, new_2]),
                          sorted(row["x_categ_ids"]))
        with ctx.step("The stored website_extra_categories compute refreshed "
                      "on all 5 (comma-joined display names of the full "
                      "set)"):
            for row in rpc.read("product.product", selected,
                                ["x_categ_ids", "website_extra_categories"]):
                expected_text = joined_display_names(row["x_categ_ids"])
                ctx.check(f"product {row['id']} website_extra_categories",
                          expected_text, row["website_extra_categories"])
        with ctx.step("The unselected control product is untouched"):
            ctrl = rpc.read("product.product", [control],
                            ["x_categ_ids", "website_extra_categories"])[0]
            ctx.check("control x_categ_ids", [existing], ctrl["x_categ_ids"])
            ctx.check("control website_extra_categories unchanged",
                      control_text, ctrl["website_extra_categories"])
        with ctx.step("Guard: an empty category pick raises UserError "
                      "'Missing Website Extra Category.' and writes nothing"):
            before = {r["id"]: sorted(r["x_categ_ids"]) for r in rpc.read(
                "product.product", selected, ["x_categ_ids"])}
            empty_wiz = rpc.call(WEB_CATEG_WIZARD, "create", {},
                                 context=sel_ctx)
            raised, message = expect_user_error(
                rpc.call, WEB_CATEG_WIZARD,
                "action_assign_website_extra_categ", [empty_wiz],
                context=sel_ctx)
            ctx.check_true(
                "empty pick raised UserError 'Missing Website Extra "
                "Category.'",
                raised and "Missing Website Extra Category." in message,
                actual_desc=message)
            after = {r["id"]: sorted(r["x_categ_ids"]) for r in rpc.read(
                "product.product", selected, ["x_categ_ids"])}
            ctx.check("empty pick wrote nothing", before, after)
    finally:
        with ctx.step("Cleanup fixtures"):
            sweep_fg04(rpc)
