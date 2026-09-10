"""TEST-SALES-003 — Cancel quotation before confirmation (API).

Excel traceability: fills the "cancel before confirmation" scenario gap found
in the Phase-1 discovery of workflow WF-O2C-GALLERY (related workbook test:
TC-SAL-021, which covers cancel AFTER confirmation with an auto-created
invoice — the pre-confirmation path had no test at all).
"""
from framework.registry import test_case
from framework.testdata import ensure_master_data


@test_case(
    id="TEST-SALES-003",
    name="Cancel quotation before confirmation (API)",
    workflow="WF-O2C-GALLERY",
    workflow_name="Gallery Direct Sale — Order to Cash",
    module="Sales",
    priority="P1",
    kind="API",
    order=40,
    description="Create a draft quotation, cancel it, assert state=cancel and "
                "that no invoice or delivery was spawned.",
    traceability={
        "tc_ids": ["TC-SAL-021 (related)", "WF-O2C-GALLERY gap: cancel-before-confirmation"],
        "feature": "invoice creation on confirm, redirect to invoice (feature #29 — related)",
        "user_story": "As a Gallery Salesperson, I can abandon a quotation "
                      "cleanly before confirming it, so that dead quotes never "
                      "produce documents.",
        "source": "Phase-1 discovery report §5 (WF-O2C-GALLERY scenario grid)",
    },
)
def test_cancel_quotation_api(ctx):
    with ctx.step("Prepare deterministic master data"):
        customer_id, product_id = ensure_master_data(ctx)

    with ctx.step("Create quotation via API"):
        order_id = ctx.adapter.create_quotation(
            customer_id, [(product_id, 1)],
            origin=f"QA-AUTO {ctx.test_def.id}")
        ctx.check("State before cancel", expected="draft",
                  actual=ctx.adapter.order_data(order_id)["state"])

    with ctx.step("Cancel the quotation"):
        ctx.adapter.cancel_order(order_id)

    with ctx.step("Verify business outcome"):
        data = ctx.adapter.order_data(order_id)
        ctx.check("Order state after cancel", expected="cancel",
                  actual=data["state"])
        ctx.check("No invoices were created", expected=0,
                  actual=len(data.get("invoice_ids") or []))
        if data["has_picking_field"]:
            ctx.check("No delivery was created", expected=0,
                      actual=len(data.get("picking_ids") or []))
