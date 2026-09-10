"""TEST-SALES-004 — MMG dollar discount converts on write (API).

Excel traceability: TC-SAL-007 "Dollar discount converts on write (not just
onchange)" — P0 / FUNC, feature #8 "dollar-to-percentage discount conversion",
module mmg_automated_action, user story: "As a Sales Representative, I can
enter a discount as a dollar amount on an order line, so that I can negotiate
in the currency the customer is thinking in and let Odoo derive the
percentage."

MMG-specific: requires the Studio field ``x_discount`` on sale.order.line.
On a database that doesn't carry the MMG customization yet (e.g. a vanilla
v19 test DB before migration), the test SKIPS deterministically with a real,
recorded reason — it does not fake a pass or fail.
"""
from framework.registry import test_case
from framework.testdata import PRODUCT_PRICE, ensure_master_data

QTY = 2
DISCOUNT_DOLLARS = 30.0  # on a 2 × $150 line → expected 10% discount


@test_case(
    id="TEST-SALES-004",
    name="MMG dollar discount converts on write (API)",
    workflow="WF-O2C-GALLERY",
    workflow_name="Gallery Direct Sale — Order to Cash",
    module="Sales (MMG custom)",
    priority="P0",
    kind="API",
    order=50,
    description="Writes x_discount (dollar amount) on an order line via API — "
                "bypassing UI onchange — and asserts the percentage discount "
                "is derived. Auto-skips when the MMG field is absent.",
    traceability={
        "tc_ids": ["TC-SAL-007"],
        "feature": "#8 dollar-to-percentage discount conversion",
        "user_story": "As a Sales Representative, I can enter a discount as a "
                      "dollar amount on an order line, so that I can negotiate "
                      "in the currency the customer is thinking in and let "
                      "Odoo derive the percentage.",
        "source": "MMG_v19_Test_Cases_Grouped_by_Feature_v2.0.xlsx / Test Execution",
    },
)
def test_mmg_dollar_discount_api(ctx):
    with ctx.step("Check MMG customization is present on this database"):
        if not ctx.adapter.rpc.field_exists("sale.order.line", "x_discount"):
            ctx.skip("Field sale.order.line.x_discount does not exist on "
                     f"database '{ctx.env.db}' — MMG discount customization "
                     "not installed/migrated here yet (TC-SAL-007 not applicable).")

    with ctx.step("Prepare deterministic master data"):
        customer_id, product_id = ensure_master_data(ctx)

    with ctx.step(f"Create quotation via API (qty {QTY} × ${PRODUCT_PRICE})"):
        order_id = ctx.adapter.create_quotation(
            customer_id, [(product_id, QTY)],
            origin=f"QA-AUTO {ctx.test_def.id}")
        line = ctx.adapter.order_data(order_id)["lines"][0]

    with ctx.step(f"Write x_discount = ${DISCOUNT_DOLLARS} on the line "
                  "(write path, bypasses onchange)"):
        ctx.adapter.rpc.write("sale.order.line", [line["id"]],
                              {"x_discount": DISCOUNT_DOLLARS})

    with ctx.step("Verify the percentage was derived"):
        after = ctx.adapter.order_data(order_id)["lines"][0]
        expected_pct = round(
            DISCOUNT_DOLLARS / (PRODUCT_PRICE * QTY) * 100, 2)
        ctx.check("Discount % derived from dollar amount",
                  expected=expected_pct,
                  actual=round(after["discount"], 2))
        ctx.check("Line subtotal reflects the discount",
                  expected=round(PRODUCT_PRICE * QTY - DISCOUNT_DOLLARS, 2),
                  actual=round(after["price_subtotal"], 2))
