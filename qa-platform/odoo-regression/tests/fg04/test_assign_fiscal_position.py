"""FG-04 — Assign Fiscal Position wizard: TC-BLK-005..007.

TC-BLK-005 carries a sequencing note from the workbook: on v19 it must not
be signed off before TC-DAT-019 (company-dependent property storage
migration) has passed — recorded as a log line, the ORM behaviour itself is
asserted here on both versions.

TC-BLK-007 creates (or reuses) a dedicated FG04 second company; company
creation on a stock-enabled database also creates that company's warehouse
data, so the company fixture is reused across runs instead of deleted, and
the acting user's company access is snapshotted and restored in finally.
"""
from adapters.base import OdooRPCError
from framework.registry import test_case
from tests.fg04.common import (fixture_token, fx,  # noqa: F401
                               FP_WIZARD, MARK, ensure_fiscal_position,
                               expect_user_error, m2o_id, make_partners,
                               sweep_fg04, trace)


@test_case(
    id="TEST-FG04-BLK-005", name="Assign Fiscal Position to selected partners",
    workflow="FG-04", workflow_name="Bulk Wizards",
    module="mmg_sale_assign_fiscal_position", priority="P0", kind="API",
    order=404,
    description="property_account_position_id set to the chosen position on "
                "all 10 selected partners (single batched write); baseline "
                "diff proves exactly the selection changed.",
    traceability=trace("TC-BLK-005"))
def test_blk_005(ctx):
    rpc = ctx.adapter.rpc
    with ctx.step("Sweep previous FG-04 fixtures"):
        sweep_fg04(rpc)
    ctx.log("workbook gate: on v19 do not sign off before TC-DAT-019 "
            "(ir.property → JSONB property migration) has passed")
    with ctx.step("Create the Avatax-treatment position and 10 partners "
                  "with mixed existing positions + 1 control"):
        avatax_fp = ensure_fiscal_position(rpc, f"{MARK} Avatax Position")
        old_fp = ensure_fiscal_position(rpc, f"{MARK} Old Position")
        with_old = make_partners(rpc, 5, "FP Preset",
                                 {"property_account_position_id": old_fp})
        without = make_partners(rpc, 5, "FP Empty")
        selected = with_old + without
        control = make_partners(rpc, 1, "FP Ctrl",
                                {"property_account_position_id": old_fp})[0]
    try:
        with ctx.step("Export the per-partner baseline before the run"):
            baseline = {r["id"]: m2o_id(r["property_account_position_id"])
                        for r in rpc.read("res.partner", selected,
                                          ["property_account_position_id"])}
            mixed = sorted(set(baseline.values()), key=str)
            ctx.check_true("starting positions are mixed", len(mixed) == 2,
                           actual_desc=f"distinct starting values: {mixed}")
        with ctx.step("Create the wizard over the 10 partners and assign()"):
            wiz = rpc.create(FP_WIZARD,
                             {"partner_ids": [(6, 0, selected)],
                              "fiscal_position_id": avatax_fp})
            rpc.call(FP_WIZARD, "assign", [wiz])
        with ctx.step("Each selected partner reads the Avatax position in "
                      "the acting company (the value the partner form "
                      "displays)"):
            for row in rpc.read("res.partner", selected,
                                ["property_account_position_id"]):
                ctx.check(f"partner {row['id']} fiscal position",
                          avatax_fp,
                          m2o_id(row["property_account_position_id"]))
        with ctx.step("Diff against the baseline: exactly the 10 selected "
                      "partners changed"):
            ctrl = rpc.read("res.partner", [control],
                            ["property_account_position_id"])[0]
            ctx.check("control partner keeps its previous position",
                      old_fp, m2o_id(ctrl["property_account_position_id"]))
            count = rpc.call("res.partner", "search_count",
                             [("property_account_position_id", "=",
                               avatax_fp)])
            ctx.check("partners carrying the new position", 10, count)
    finally:
        with ctx.step("Cleanup fixtures"):
            sweep_fg04(rpc)


@test_case(
    id="TEST-FG04-BLK-006", name="Assign Fiscal Position blocks an empty selection",
    workflow="FG-04", workflow_name="Bulk Wizards",
    module="mmg_sale_assign_fiscal_position", priority="P1", kind="API",
    order=405,
    description="assign() with no fiscal position raises UserError 'Missing "
                "Fiscal Position.' and writes nothing — customer tax "
                "treatment is never cleared by accident.",
    traceability=trace("TC-BLK-006"))
def test_blk_006(ctx):
    rpc = ctx.adapter.rpc
    with ctx.step("Sweep previous FG-04 fixtures"):
        sweep_fg04(rpc)
    with ctx.step("Create partners with a known existing fiscal position"):
        old_fp = ensure_fiscal_position(rpc, f"{MARK} Old Position")
        partners = make_partners(rpc, 3, "FP Guard",
                                 {"property_account_position_id": old_fp})
    try:
        with ctx.step("Create the wizard with partners but NO fiscal "
                      "position"):
            wiz = rpc.create(FP_WIZARD, {"partner_ids": [(6, 0, partners)]})
            fp = rpc.read(FP_WIZARD, [wiz], ["fiscal_position_id"])[0]
            ctx.check("wizard.fiscal_position_id empty", None,
                      m2o_id(fp["fiscal_position_id"]))
        with ctx.step("assign() raises UserError 'Missing Fiscal "
                      "Position.'"):
            raised, message = expect_user_error(
                rpc.call, FP_WIZARD, "assign", [wiz])
            ctx.check_true("guard raised",
                           raised and "Missing Fiscal Position." in message,
                           actual_desc=message)
        with ctx.step("No write happened — every partner keeps its previous "
                      "position"):
            for row in rpc.read("res.partner", partners,
                                ["property_account_position_id"]):
                ctx.check(f"partner {row['id']} position unchanged",
                          old_fp,
                          m2o_id(row["property_account_position_id"]))
    finally:
        with ctx.step("Cleanup fixtures"):
            sweep_fg04(rpc)


@test_case(
    id="TEST-FG04-BLK-007", name="Assign Fiscal Position in a multi-company context",
    workflow="FG-04", workflow_name="Bulk Wizards",
    module="mmg_sale_assign_fiscal_position", priority="P2", kind="API",
    order=406,
    description="The wizard writes the company-dependent property for the "
                "acting company only: company A reads the new position, "
                "company B keeps its preset one.",
    traceability=trace("TC-BLK-007"))
def test_blk_007(ctx):
    rpc = ctx.adapter.rpc
    with ctx.step("Sweep previous FG-04 fixtures"):
        sweep_fg04(rpc)
    with ctx.step("Resolve company A (acting) and ensure the FG04 test "
                  "company B"):
        user = rpc.read("res.users", [rpc.uid],
                        ["company_id", "company_ids"])[0]
        company_a = m2o_id(user["company_id"])
        original_companies = list(user["company_ids"])
        found = rpc.search("res.company",
                           [("name", "=", f"{MARK} Test Company B")], limit=1)
        if found:
            company_b = found[0]
            ctx.log(f"reusing fixture company B id={company_b}")
        else:
            try:
                company_b = rpc.create("res.company",
                                       {"name": f"{MARK} Test Company B"})
                ctx.log(f"created fixture company B id={company_b} (reused on "
                        "later runs — company deletion is not safe on a "
                        "stock-enabled clone)")
            except OdooRPCError as exc:
                # multi-company rights are an environment property, not a
                # product defect — report BLOCKED, never a misleading FAIL
                ctx.blocked(
                    f"The runner user cannot create the second company this "
                    f"multi-company case needs ({exc}). Grant it "
                    f"base.group_multi_company / Settings rights on the QA "
                    f"clone, or pre-create a company named "
                    f"'{MARK} Test Company B' — the test reuses it.")
    partner = None
    try:
        with ctx.step("Grant the acting user access to company B "
                      "(snapshot + restore)"):
            if company_b not in original_companies:
                rpc.write("res.users", [rpc.uid],
                          {"company_ids": [(4, company_b)]})
        with ctx.step("Create the shared partner and the per-company "
                      "positions FP-A / FP-B"):
            partner = rpc.create("res.partner",
                                 {"name": fx(f"{MARK} MC Partner"),
                                  "company_id": False})
            fp_a = ensure_fiscal_position(rpc, f"{MARK} FP-A", company_a)
            fp_b = ensure_fiscal_position(rpc, f"{MARK} FP-B", company_b)
        with ctx.step("Preset the partner's company-B mapping to FP-B"):
            rpc.call("res.partner", "write", [partner],
                     {"property_account_position_id": fp_b},
                     context={"allowed_company_ids": [company_b]})
            preset = rpc.call("res.partner", "read", [partner],
                              ["property_account_position_id"],
                              context={"allowed_company_ids": [company_b]})
            ctx.check("company-B preset in place", fp_b,
                      m2o_id(preset[0]["property_account_position_id"]))
        with ctx.step("Acting in company A, run the wizard with FP-A"):
            wiz = rpc.call(FP_WIZARD, "create",
                           {"partner_ids": [(6, 0, [partner])],
                            "fiscal_position_id": fp_a},
                           context={"allowed_company_ids": [company_a]})
            rpc.call(FP_WIZARD, "assign", [wiz],
                     context={"allowed_company_ids": [company_a]})
        with ctx.step("Company A reads the newly assigned FP-A"):
            val_a = rpc.call("res.partner", "read", [partner],
                             ["property_account_position_id"],
                             context={"allowed_company_ids": [company_a]})
            ctx.check("company-A value", fp_a,
                      m2o_id(val_a[0]["property_account_position_id"]))
        with ctx.step("Company B still reads its preset FP-B — no leak "
                      "between companies"):
            val_b = rpc.call("res.partner", "read", [partner],
                             ["property_account_position_id"],
                             context={"allowed_company_ids": [company_b]})
            ctx.check("company-B value untouched", fp_b,
                      m2o_id(val_b[0]["property_account_position_id"]))
        ctx.log("UI half (top-bar company switch shows the per-company "
                "value) follows from the same company-dependent read")
    finally:
        with ctx.step("Restore user company access and cleanup"):
            try:
                rpc.write("res.users", [rpc.uid],
                          {"company_ids": [(6, 0, original_companies)]})
            except Exception:
                pass
            sweep_fg04(rpc)
