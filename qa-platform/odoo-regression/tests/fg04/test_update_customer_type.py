"""FG-04 — Update Customer Type wizard: TC-BLK-010, TC-BLK-012.

The wizard writes the Studio manual field x_type on res.partner. On the QA
clone the field exists (TC-STU-003 precondition) and is asserted before use.
The v15 button method update() vs the v19 rename
action_update_customer_type() (DW-006) is absorbed by
common.customer_type_method() — the workbook step documents both names.

TC-BLK-011 (field-missing guard) is NOT implemented here: it requires a
database where res.partner has no x_type field, and removing the
data-bearing Studio field from the shared production clone would destroy
live data (see reports/data/fg04_feasibility.json).
"""
from framework.registry import test_case
from tests.fg04.common import (fixture_token, fx,  # noqa: F401
                               MARK, TYPE_WIZARD, customer_type_method,
                               expect_user_error, make_partners, sweep_fg04,
                               trace)


@test_case(
    id="TEST-FG04-BLK-010", name="Update Customer Type writes x_type",
    workflow="FG-04", workflow_name="Bulk Wizards",
    module="mmg_sale_update_customer_type", priority="P1", kind="API",
    order=409,
    description="x_type set to the typed value on all 5 selected partners "
                "in one batched write; the unselected control partner is "
                "untouched.",
    traceability=trace("TC-BLK-010"))
def test_blk_010(ctx):
    rpc = ctx.adapter.rpc
    with ctx.step("Sweep previous FG-04 fixtures"):
        sweep_fg04(rpc)
    with ctx.step("Assert the TC-STU-003 precondition: the Studio field "
                  "x_type exists on res.partner"):
        ctx.check_true("res.partner has x_type",
                       rpc.field_exists("res.partner", "x_type"),
                       actual_desc="x_type present in fields_get")
    with ctx.step("Create 5 contacts + 1 unselected control contact"):
        selected = make_partners(rpc, 5, "CustType")
        control = make_partners(rpc, 1, "CustTypeCtrl")[0]
        control_before = rpc.read("res.partner", [control],
                                  ["x_type"])[0]["x_type"]
    try:
        with ctx.step("Create the wizard over the 5 contacts and run the "
                      "update action"):
            wiz = rpc.create(TYPE_WIZARD,
                             {"partner_ids": [(6, 0, selected)],
                              "new_customer_type": "Wholesale"})
            rpc.call(TYPE_WIZARD, customer_type_method(ctx), [wiz])
        with ctx.step("Each of the 5 partners has x_type == 'Wholesale'"):
            for row in rpc.read("res.partner", selected, ["x_type"]):
                ctx.check(f"partner {row['id']} x_type", "Wholesale",
                          row["x_type"])
            count = rpc.call("res.partner", "search_count",
                             [("x_type", "=", "Wholesale"),
                              ("name", "like", f"{MARK} %")])
            ctx.check("marker-scoped count of updated partners", 5, count)
        with ctx.step("The unselected control partner's x_type is "
                      "unchanged"):
            after = rpc.read("res.partner", [control],
                             ["x_type"])[0]["x_type"]
            ctx.check("control x_type unchanged", control_before, after)
    finally:
        with ctx.step("Cleanup fixtures"):
            sweep_fg04(rpc)


@test_case(
    id="TEST-FG04-BLK-012", name="Update Customer Type requires a value",
    workflow="FG-04", workflow_name="Bulk Wizards",
    module="mmg_sale_update_customer_type", priority="P3", kind="API",
    order=410,
    description="Creating the wizard without a Customer Type value fails "
                "(required field, NOT NULL at flush); the field is declared "
                "required (the UI form's blocking indicator derives from "
                "it); no partner is written.",
    traceability=trace("TC-BLK-012"))
def test_blk_012(ctx):
    rpc = ctx.adapter.rpc
    with ctx.step("Sweep previous FG-04 fixtures"):
        sweep_fg04(rpc)
    with ctx.step("Create partners with a known x_type"):
        partners = make_partners(rpc, 2, "TypeReq",
                                 {"x_type": fx(f"{MARK}-Orig")})
    try:
        with ctx.step("Creating the wizard without a Customer Type value "
                      "fails (required field violation at flush)"):
            raised, message = expect_user_error(
                rpc.create, TYPE_WIZARD,
                {"partner_ids": [(6, 0, partners)]})
            ctx.check_true("wizard create without a value rejected",
                           raised, actual_desc=message)
        with ctx.step("UI half: new_customer_type is declared required, "
                      "which drives the form's blocking indicator"):
            info = rpc.call(TYPE_WIZARD, "fields_get", ["new_customer_type"],
                            attributes=["required"])
            ctx.check("new_customer_type required", True,
                      info["new_customer_type"]["required"])
        with ctx.step("No partner's x_type changed"):
            for row in rpc.read("res.partner", partners, ["x_type"]):
                ctx.check(f"partner {row['id']} x_type unchanged",
                          fx(f"{MARK}-Orig"), row["x_type"])
    finally:
        with ctx.step("Cleanup fixtures"):
            sweep_fg04(rpc)
