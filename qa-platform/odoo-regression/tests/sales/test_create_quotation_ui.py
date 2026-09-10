"""TEST-SALES-001 — Create quotation through the real UI (Playwright).

Excel traceability: first leg of TC-SAL-017 "Quotation → confirm → deliver →
invoice → pay, happy path" (P0 / REGR / suite SAL, workflow Order-to-Cash),
with master data conventions from TC-ART-001.

Business steps run through the browser exactly as a Gallery Salesperson would;
the final verification cross-checks the database through XML-RPC so the
assertion is on business state, not on pixels.
"""
from framework.registry import test_case
from framework.testdata import (CUSTOMER_NAME, PRODUCT_NAME, PRODUCT_PRICE,
                                ensure_master_data)
from pages import LoginPage, QuotationPage, SalesPage

QTY = 2


@test_case(
    id="TEST-SALES-001",
    name="Create quotation (UI)",
    workflow="WF-O2C-GALLERY",
    workflow_name="Gallery Direct Sale — Order to Cash",
    module="Sales",
    priority="P0",
    kind="UI",
    order=20,
    description="Login → Sales → New quotation → select customer → add "
                "product ×2 → save → verify record via RPC (state, lines, "
                "untaxed total).",
    traceability={
        "tc_ids": ["TC-SAL-017", "TC-ART-001"],
        "feature": "Sales order core (workbook suite SAL)",
        "user_story": "A salesperson completes the first leg of Order-to-Cash: "
                      "a saved quotation for a customer with a priced product.",
        "source": "MMG_v19_Test_Cases_Grouped_by_Feature_v2.0.xlsx / Test Execution",
    },
)
def test_create_quotation_ui(ctx):
    env = ctx.env

    with ctx.step("Prepare deterministic master data (find-or-create via API)"):
        customer_id, product_id = ensure_master_data(ctx)

    with ctx.step("Login"):
        page = ctx.browser_page()
        login = LoginPage(page, ctx.adapter).open()
        login.login(env.username, env.password)
        ctx.check("Login succeeded", expected=True, actual=login.is_logged_in())

    with ctx.step("Open Sales app"):
        sales = SalesPage(page, ctx.adapter).open()
        ctx.check("Sales list view rendered", expected=True,
                  actual=sales.is_loaded())

    with ctx.step("Start a new quotation"):
        sales.click_new()
        quote = QuotationPage(page, ctx.adapter)

    with ctx.step(f"Select customer '{CUSTOMER_NAME}'"):
        quote.set_customer(CUSTOMER_NAME)

    with ctx.step(f"Add product '{PRODUCT_NAME}' × {QTY}"):
        quote.add_product_line(PRODUCT_NAME, QTY)

    with ctx.step("Save quotation"):
        quote.save()
        ctx.screenshot("quotation-saved")

    with ctx.step("Verify quotation in the database (XML-RPC)"):
        order_id = quote.record_id()
        if not order_id:  # defensive fallback, still fully deterministic
            order_id = ctx.adapter.latest_order_for_customer(customer_id)
        ctx.check_true("Quotation record exists", bool(order_id),
                       actual_desc=f"order_id={order_id}")
        data = ctx.adapter.order_data(order_id)
        ctx.log(f"Order {data['name']}: state={data['state']}, "
                f"untaxed={data['amount_untaxed']}")
        ctx.check("Quotation state", expected="draft", actual=data["state"])
        ctx.check("Customer on order", expected=customer_id,
                  actual=data["partner_id"][0])
        ctx.check("Number of order lines", expected=1,
                  actual=len(data["lines"]))
        ctx.check("Line quantity", expected=QTY,
                  actual=data["lines"][0]["product_uom_qty"])
        ctx.check("Untaxed total", expected=round(PRODUCT_PRICE * QTY, 2),
                  actual=round(data["amount_untaxed"], 2))
