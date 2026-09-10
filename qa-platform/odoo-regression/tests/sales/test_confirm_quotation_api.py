"""TEST-SALES-002 — Confirm quotation → sales order (API).

Excel traceability: second leg of TC-SAL-017 (P0 / REGR, Order-to-Cash):
"End-to-end completes; totals correct at each step". Runs at the API level —
business behavior, not pixels — and asserts the cross-module outcome
(delivery picking) when the sale_stock bridge is installed.
"""
from framework.registry import test_case
from framework.testdata import PRODUCT_PRICE, ensure_master_data

QTY = 3


@test_case(
    id="TEST-SALES-002",
    name="Confirm quotation → sales order (API)",
    workflow="WF-O2C-GALLERY",
    workflow_name="Gallery Direct Sale — Order to Cash",
    module="Sales",
    priority="P0",
    kind="API",
    order=30,
    description="Create a quotation via XML-RPC, confirm it, assert state=sale, "
                "totals unchanged, and a delivery is spawned (when sale_stock "
                "is installed).",
    traceability={
        "tc_ids": ["TC-SAL-017"],
        "feature": "Sales order core (workbook suite SAL)",
        "user_story": "Confirming a quotation produces a sales order whose "
                      "totals are unchanged and whose delivery chain starts.",
        "source": "MMG_v19_Test_Cases_Grouped_by_Feature_v2.0.xlsx / Test Execution",
    },
)
def test_confirm_quotation_api(ctx):
    with ctx.step("Prepare deterministic master data"):
        customer_id, product_id = ensure_master_data(ctx)

    with ctx.step(f"Create quotation via API (qty {QTY})"):
        order_id = ctx.adapter.create_quotation(
            customer_id, [(product_id, QTY)],
            origin=f"QA-AUTO {ctx.test_def.id}")
        before = ctx.adapter.order_data(order_id)
        ctx.log(f"Created {before['name']} (id {order_id})")
        ctx.check("State before confirm", expected="draft",
                  actual=before["state"])

    with ctx.step("Confirm the order"):
        ctx.adapter.confirm_order(order_id)

    with ctx.step("Verify business outcome"):
        after = ctx.adapter.order_data(order_id)
        ctx.check("Order state after confirm", expected="sale",
                  actual=after["state"])
        ctx.check("Untaxed total unchanged by confirmation",
                  expected=round(before["amount_untaxed"], 2),
                  actual=round(after["amount_untaxed"], 2))
        ctx.check("Untaxed total equals qty × price",
                  expected=round(PRODUCT_PRICE * QTY, 2),
                  actual=round(after["amount_untaxed"], 2))
        if after["has_picking_field"]:
            ctx.check_true(
                "Delivery picking created (sale_stock installed)",
                len(after.get("picking_ids") or []) >= 1,
                actual_desc=f"picking_ids={after.get('picking_ids')}")
        else:
            ctx.log("sale_stock not installed on this database — "
                    "delivery assertion not applicable, skipped explicitly.")
