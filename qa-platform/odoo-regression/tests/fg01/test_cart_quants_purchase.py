"""FG-01 — cart-exclusion actions, quants, purchase context:
TC-ART-008, TC-ART-006, TC-ART-012.

Expected v15 outcomes: TC-ART-008 and TC-ART-012 PASS; TC-ART-006 FAILs on
its last step — stock.quant.x_vendor is declared as a plain related field
(``fields.Char(related='product_id.x_vendor')``,
mmg_stock/models/stock_quant.py:9) with no ``store=True``, so read_group
refuses it on v15. The workbook expects it groupable (the v19 target), so the
FAIL is the documented baseline and classifies as FIXED when v19 passes.

TC-ART-006 creates its own consigned product + quant (workbook steps 1-2)
instead of sampling live consigned stock: sampling made step 3 tautological
(product.x_vendor compared with the quant's related read of the same value)
and skipped the case whenever the clone held no consigned stock. The vendor
value is namespaced with fx() because steps 4-5 count/filter by it.

TC-ART-012 writes the consignment fields on the variant it puts on the PO
line as well as on the template. They are independent stored fields on both
models; the purchase-context assertion must not depend on the template→
variant precommit mirror, which TC-ART-001/-003 own.

All three tests clean up through ``unlink_quiet`` / ``cleanup_fg01`` and the
defensive ``_remove_quant``, none of which can raise — a raising cleanup
would replace TC-ART-006's documented FAIL with an ERROR.
"""
from adapters.base import OdooRPCError
from framework.registry import test_case
from tests.fg01.common import (MARK, cleanup_fg01, form_arch, fx, m2o_id,
                               sweep_fg01, trace, unlink_quiet)

CART_ACTIONS = ("mmg_stock.activate_exclude_cart_server_action",
                "mmg_stock.deactivate_exclude_cart_server_action")


@test_case(
    id="TEST-FG01-ART-008", name="Exclude-from-cart bulk activate / deactivate",
    workflow="FG-01", workflow_name="Art Catalogue", module="mmg_stock",
    priority="P1", kind="API", order=140,
    description="mmg_stock server-action pair toggles x_exclude_cart on "
                "exactly the selection; bindings exist; no side effects.",
    traceability=trace("TC-ART-008"))
def test_art_008(ctx):
    """EXPECTED v15 OUTCOME: PASS. Both server actions and their list-view
    bindings ship in v15 mmg_stock, and x_exclude_cart is a stored Boolean,
    so the selection-scoped toggle and the untouched control record are v15
    behaviour.

    The three binding facts per action (XML id resolves, bound model, bound
    view type) are collected into one mapping and asserted once, so a wrong
    binding on the first action cannot hide the second.
    """
    rpc = ctx.adapter.rpc
    with ctx.step("Sweep previous FG-01 fixtures"):
        sweep_fg01(rpc)
    with ctx.step("Create 3 selected + 1 control product"):
        selected = [rpc.create("product.product",
                               {"name": fx(f"{MARK} Cart {i}")})
                    for i in range(3)]
        untouched = rpc.create("product.product",
                               {"name": fx(f"{MARK} Cart untouched")})
        before = rpc.read("product.product", [untouched],
                          ["x_exclude_cart", "write_date"])[0]
    try:
        with ctx.step("Activate exclude-from-cart on the selection"):
            rpc.call("product.product", "activate_exclude_from_cart", selected)
            flags = [r["x_exclude_cart"] for r in rpc.read(
                "product.product", selected, ["x_exclude_cart"])]
            ctx.check("all selected flagged", [True, True, True], flags)
            ctx.check("control record not flagged", False, rpc.read(
                "product.product", [untouched],
                ["x_exclude_cart"])[0]["x_exclude_cart"])
        with ctx.step("Deactivate a subset"):
            rpc.call("product.product", "deactivate_exclude_from_cart",
                     selected[:2])
            flags = [r["x_exclude_cart"] for r in rpc.read(
                "product.product", selected, ["x_exclude_cart"])]
            ctx.check("subset deactivated", [False, False, True], flags)
        with ctx.step("Assert the list-view server-action bindings exist"):
            expected, actual = {}, {}
            for xmlid in CART_ACTIONS:
                expected[xmlid] = {"resolves": True,
                                   "binding_model": "product.product",
                                   "binding_view_types": "list"}
                act_id = rpc.ref(xmlid)
                entry = {"resolves": bool(act_id)}
                if act_id:
                    act = rpc.read("ir.actions.server", [act_id],
                                   ["binding_model_id",
                                    "binding_view_types"])[0]
                    model_id = m2o_id(act["binding_model_id"])
                    entry["binding_model"] = (
                        rpc.read("ir.model", [model_id],
                                 ["model"])[0]["model"] if model_id
                        else "no binding model set")
                    entry["binding_view_types"] = act["binding_view_types"]
                actual[xmlid] = entry
            ctx.check("exclude-from-cart server-action bindings",
                      expected, actual)
        with ctx.step("No side effects on the control record"):
            after = rpc.read("product.product", [untouched],
                             ["x_exclude_cart", "write_date"])[0]
            ctx.check("control write_date unchanged", before["write_date"],
                      after["write_date"])
    finally:
        with ctx.step("Cleanup fixtures"):
            cleanup_fg01(ctx, rpc)


@test_case(
    id="TEST-FG01-ART-006", name="Vendor visible on stock quants",
    workflow="FG-01", workflow_name="Art Catalogue", module="mmg_stock",
    priority="P1", kind="API", order=141,
    description="stock.quant.x_vendor related field resolves, is searchable, "
                "groupable and rendered in the quant search view for a "
                "consigned fixture product.",
    traceability=trace("TC-ART-006"))
def test_art_006(ctx):
    """EXPECTED v15 OUTCOME: FAIL on the last step — documented baseline.
    stock.quant.x_vendor is a NON-STORED related Char on v15
    (mmg_stock/models/stock_quant.py:9), and Odoo's read_group accepts stored
    fields only, so the workbook's groupable expectation describes the v19
    target.

    The resolve / search / search-view steps are v15 behaviour and run first,
    so the group-by failure cannot destroy their evidence.
    """
    rpc = ctx.adapter.rpc
    with ctx.step("Sweep previous fixtures"):
        sweep_fg01(rpc)
    vendor = fx("Consignor A")
    quant = None
    with ctx.step("Create a consigned product (template + variant)"):
        values = {"name": fx(f"{MARK} Consigned Quant"), "x_vendor": vendor}
        values.update(ctx.adapter.storable_product_values())
        tmpl = rpc.create("product.template", values)
        variant = rpc.search("product.product",
                             [("product_tmpl_id", "=", tmpl)], limit=1)[0]
        mirrored = rpc.read("product.product", [variant],
                            ["x_vendor"])[0]["x_vendor"]
        ctx.log(f"variant {variant} x_vendor after template create: "
                f"{mirrored!r}")
        # the quant reads product_id.x_vendor, so the value must sit on the
        # variant: set it there explicitly instead of relying on the
        # template→variant precommit mirror (owned by TC-ART-001/-003)
        rpc.write("product.product", [variant], {"x_vendor": vendor})
    try:
        with ctx.step("Create a quant at the internal stock location"):
            location = rpc.ref("stock.stock_location_stock")
            ctx.check_true("stock.stock_location_stock resolves",
                           bool(location),
                           actual_desc=f"id={location}" if location
                           else "xml id not found")
            quant = rpc.create("stock.quant", {"product_id": variant,
                                               "location_id": location,
                                               "quantity": 1.0})
            ctx.log(f"quant id {quant}")
        with ctx.step("Related field resolves on the quant"):
            data = rpc.read("stock.quant", [quant],
                            ["x_vendor", "product_id", "quantity"])[0]
            ctx.log(f"quant quantity {data['quantity']}")
            ctx.check("quant read-back",
                      {"product_id": variant, "x_vendor": vendor},
                      {"product_id": m2o_id(data["product_id"]),
                       "x_vendor": data["x_vendor"]})
        with ctx.step("Searchable by vendor"):
            try:
                found = rpc.search("stock.quant", [("x_vendor", "=", vendor)])
            except OdooRPCError as exc:
                ctx.check("quants searchable by x_vendor (domain)", True,
                          f"not searchable: {exc}")
            else:
                ctx.check("search returns exactly the fixture quant", [quant],
                          found)
        # the search-view check runs before the group-by one: read_group is
        # the documented v15 FAIL, and a failing assertion ends the test, so
        # the view evidence would otherwise never be recorded on v15
        with ctx.step("Quant search view renders the Vendor field"):
            arch = form_arch(ctx, "stock.quant", "search")
            ctx.check_true("x_vendor present in the quant search view",
                           "x_vendor" in arch,
                           actual_desc=f"{len(arch)} chars, x_vendor "
                                       f"{'present' if 'x_vendor' in arch else 'absent'}")
        with ctx.step("Groupable by vendor"):
            try:
                groups = rpc.read_group("stock.quant",
                                        [("x_vendor", "=", vendor)],
                                        ["x_vendor"], ["x_vendor"])
            except OdooRPCError as exc:
                # v15: x_vendor is a non-stored related field → not groupable;
                # the workbook expects groupable (v19 target) — honest FAIL
                ctx.check("quants groupable by x_vendor (read_group)", True,
                          f"not groupable: {exc}")
            else:
                ctx.check("one group for the vendor", 1, len(groups))
                count = groups[0].get("__count",
                                      groups[0].get("x_vendor_count", 0))
                ctx.check_true("group count >= 1", count >= 1,
                               actual_desc=str(count))
    finally:
        with ctx.step("Cleanup fixtures"):
            if quant:
                _remove_quant(ctx, rpc, quant)
            cleanup_fg01(ctx, rpc)


def _remove_quant(ctx, rpc, quant_id):
    """Delete the fixture quant without ever raising.

    stock gates quant unlink, so the inventory-mode contexts are tried first;
    if every attempt is refused the quantity is zeroed so no stock is left
    behind, and the outcome is logged either way (this runs in a finally step,
    where a raise would replace the test's verdict).
    """
    for context in ({"inventory_mode": True}, {"force_unlink": True},
                    {"inventory_mode": True, "force_unlink": True}, {}):
        try:
            rpc.call("stock.quant", "unlink", [quant_id], context=context)
            ctx.log(f"quant {quant_id} deleted (context {context})")
            return
        except Exception as exc:  # noqa: BLE001 — cleanup must not raise
            ctx.log(f"quant {quant_id} unlink refused with context "
                    f"{context}: {exc}")
    try:
        rpc.write("stock.quant", [quant_id], {"quantity": 0.0})
        ctx.log(f"quant {quant_id} could not be deleted — quantity zeroed")
    except Exception as exc:  # noqa: BLE001 — cleanup must not raise
        ctx.log(f"cleanup incomplete: quant {quant_id} left in place "
                f"(write refused): {exc}")


@test_case(
    id="TEST-FG01-ART-012", name="Purchase views retain the art/consignment context",
    workflow="FG-01", workflow_name="Art Catalogue", module="mmg_stock",
    priority="P2", kind="API", order=142,
    description="Purchase variant menu deactivated; PO form view parses; "
                "consignment fields readable from the PO line product.",
    traceability=trace("TC-ART-012"))
def test_art_012(ctx):
    """EXPECTED v15 OUTCOME: PASS. mmg_stock deactivates
    purchase.product_product_menu and extends the PO views in v15, and the
    three consignment fields are stored on product.product, so every asserted
    fact is current behaviour.

    The three consignment read-backs are collected into one assertion so a
    single wrong value cannot hide the others.
    """
    rpc = ctx.adapter.rpc
    with ctx.step("Sweep previous fixtures"):
        sweep_fg01(rpc)
    with ctx.step("Assert purchase.product_product_menu is deactivated"):
        menu_id = rpc.ref("purchase.product_product_menu")
        ctx.check_true("purchase.product_product_menu resolves", bool(menu_id),
                       actual_desc=f"id={menu_id}" if menu_id
                       else "xml id not found")
        active = rpc.call("ir.ui.menu", "read", [menu_id],
                          fields=["active"],
                          context={"active_test": False})[0]["active"]
        ctx.check("variant menu inactive", False, active)
    po = None
    try:
        with ctx.step("Create vendor + consigned product + purchase order"):
            partner = rpc.create("res.partner",
                                 {"name": fx(f"{MARK} Vendor"),
                                  "supplier_rank": 1})
            consignment = {"x_vendor": fx("Consignor A"),
                           "x_consignment_percentage": 40.0,
                           "x_gallery_cost": 5000.0}
            tmpl_values = {"name": fx(f"{MARK} Consigned Piece"),
                           "purchase_ok": True}
            tmpl_values.update(consignment)
            tmpl = rpc.create("product.template", tmpl_values)
            variant = rpc.search("product.product",
                                 [("product_tmpl_id", "=", tmpl)], limit=1)[0]
            # the three fields are independent stored fields on the variant
            # (kept in step by the precommit mirror, which TC-ART-001/-003
            # own): set them on the variant under test so this case proves the
            # purchase context rather than re-testing the mirror
            rpc.write("product.product", [variant], consignment)
            po = rpc.create("purchase.order", {
                "partner_id": partner,
                "order_line": [(0, 0, {"product_id": variant,
                                       "product_qty": 1})]})
            ctx.log(f"PO id {po}")
        with ctx.step("PO form view parses with mmg_stock installed"):
            arch = form_arch(ctx, "purchase.order", "form")
            ctx.check_true("form arch non-empty", len(arch) > 100,
                           actual_desc=f"{len(arch)} chars")
        with ctx.step("Consignment context readable from the PO line product"):
            line = rpc.search_read("purchase.order.line",
                                   [("order_id", "=", po)],
                                   ["product_id"], limit=1)[0]
            ctx.check("PO line carries the fixture variant", variant,
                      m2o_id(line["product_id"]))
            prod = rpc.read("product.product", [m2o_id(line["product_id"])],
                            list(consignment))[0]
            ctx.check("consignment field mismatches on the PO line product",
                      {}, {field: {"expected": want, "actual": prod[field]}
                           for field, want in consignment.items()
                           if prod[field] != want})
    finally:
        with ctx.step("Cleanup fixtures"):
            unlink_quiet(ctx, rpc, "purchase.order", [po] if po else [],
                         cancel_method="button_cancel")
            cleanup_fg01(ctx, rpc)
