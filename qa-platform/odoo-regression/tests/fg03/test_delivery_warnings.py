"""FG-03 — delivery status and sales warnings:
TC-SAL-004, TC-SAL-005, TC-SAL-009, TC-SAL-010, TC-SAL-012, TC-SAL-011.

Version mapping taken from the modules themselves:

* `delivery_status` — same field name on both target versions, different
  owner. v15 = the `mmg_sale_delivery_status` stored compute over picking
  states only (pending / partial / full / False when everything is
  cancelled); v19 = the native `sale_stock` field, which adds `started` and
  additionally requires `qty_delivered` on a line for `partial`. The module
  is retired in the v19 port (FG-03 decision #1), so the workbook re-points
  this TC at the native field and its `started` state — a state the v15
  selection does not even contain, hence an expected v15 FAIL.

* warnings — `mmg_sale_warning_extend` never declared an order-level warning
  *text*: it adds `is_show_warning_msg_box` (a compute with no
  `@api.depends`, the v15 refresh bug) plus
  `action_open_order_lines_warning_message`, a popup listing the warned
  products. FG-03 decision #2 retires the module in favour of the native
  `sale.order.sale_warning_text` banner, and the workbook asserts that
  banner. These tests therefore assert the workbook's v19 expectation and
  record the v15 observables (banner flag, popup product ids, per-product
  messages) as evidence in the run log. The v15 FAIL is the point: it
  classifies as FIXED when the v19 banner passes. Asserting the v15 popup
  *instead* would make both versions pass and hide the replacement.

* Confirmation blocking (`sale_line_warn = 'block'`) is asserted on both
  versions per the workbook: v15 core only warns through an onchange, so
  `action_confirm` succeeds — expected v15 FAIL, fixed by the new
  `mmg_sale_warning_block` module in v19.

Live-clone adaptations (documented, not assertion-weakening):

* every delivery fixture is a CONSUMABLE (`make_deliverable`, `type='consu'`),
  never a storable. `sale_stock` launches the stock rule and computes
  `qty_delivered` from stock moves for `consu` lines exactly as for `product`
  lines, so pending/partial/full is reproduced faithfully — while the product
  stays out of `mmg_magento2_ept_inherit`'s two `type == 'product'` code paths:
  `_check_positive_quantity()` (which refused every later order create for a
  fixture product whose `virtual_available` had gone negative — the failure the
  retired legacy suite hit) and `_export_order_line_stock_to_magento()`, whose
  `update_magento_product()` raises "Internal reference is required for magento
  synchronization" for a product without `default_code` and can otherwise reach
  an outbound Magento API call. See `tests/fg03/common.py`;
* module-owned preconditions (`delivery_status`, `sale_line_warn`) and AvaTax's
  forced address validation are probed and reported as BLOCKED with a precise
  reason, never as a FAIL.
"""
from framework.registry import test_case
from tests.fg03.common import (Checks, attempt, avatax_confirm_probe,
                               banner_text, company_id, fx,
                               get_auto_invoice_flag, label, m2o_id, make_order,
                               make_deliverable, make_partner, make_product,
                               multi_step_warehouse, order_lines,
                               picking_codes, pickings_of, require_field,
                               restore_auto_invoice_flag,
                               set_auto_invoice_flag, sweep_fg03, trace,
                               validate_picking, variants_of,
                               warned_products_v15)


def _delivery_status(rpc, order_id):
    return rpc.read("sale.order", [order_id],
                    ["delivery_status"])[0]["delivery_status"]


def _confirm(ctx, rpc, order_id):
    """Confirm and log the outcome. A refused confirmation is recorded as
    evidence and the delivery_status assertion that follows reports what the
    order actually shows — an unrecorded traceback would turn a product
    refusal into an AUTOMATION_ERROR."""
    ok, res = attempt(rpc.call, "sale.order", "action_confirm", [order_id])
    if not ok:
        ctx.log(f"action_confirm({order_id}) refused: {res}")
    return ok


def _deliver(ctx, rpc, picking_ids, done_by_product=None):
    """Validate the given transfers (skipping done/cancelled ones), logging any
    refusal instead of raising: the delivery_status assertion is the verdict."""
    for pick in picking_ids or []:
        state = rpc.read("stock.picking", [pick], ["state"])[0]["state"]
        if state in ("done", "cancel"):
            continue
        ok, res = attempt(validate_picking, rpc, pick, done_by_product)
        if not ok:
            ctx.log(f"validating transfer {pick} refused: {res}")


def _delivery_selection(rpc):
    info = rpc.call("sale.order", "fields_get", ["delivery_status"],
                    attributes=["selection"])
    return [value for value, _label in
            (info.get("delivery_status") or {}).get("selection") or []]


def _warning_evidence(ctx, rpc, order_id):
    """Log the v15 observables of the retired module next to the v19
    expectation. Returns the native banner text (None when absent)."""
    if rpc.field_exists("sale.order", "is_show_warning_msg_box"):
        flag = rpc.read("sale.order", [order_id],
                        ["is_show_warning_msg_box"])[0][
                            "is_show_warning_msg_box"]
        _action, ids = warned_products_v15(rpc, order_id)
        ctx.log(f"v15 observables on order {order_id}: "
                f"is_show_warning_msg_box={flag}, popup product ids={ids}")
    return banner_text(rpc, order_id)


def _record_banner(checks, text, exists, expectations):
    """Record 'the banner contains X' for each expectation, or the field's
    absence as the actual value once."""
    for name, needle in expectations:
        if not exists:
            checks.record(name, True,
                          "sale.order.sale_warning_text absent on this "
                          "version (v15: mmg_sale_warning_extend declares no "
                          "order-level banner text)")
        else:
            checks.record(name, True, needle in (text or ""))


@test_case(
    id="TEST-FG03-SAL-004",
    name="Delivery status derives from transfers",
    workflow="FG-03", workflow_name="Sales & Pricing",
    module="mmg_sale_delivery_status", priority="P1", kind="API", order=315,
    description="pending -> partial -> full as the transfers progress, and "
                "no status at all when every transfer is cancelled. The "
                "native-only 'started' state (pick step done, nothing "
                "delivered) is asserted too and recorded for the TC-NEW-001 "
                "mapping table - v15 has no such value, expected FAIL.",
    traceability=trace("TC-SAL-004"))
def test_sal_004(ctx):
    """Expected v15 outcome: FAIL — on the last step only.

    The v15 owner is `mmg_sale_delivery_status`, a stored compute over picking
    states with the selection pending/partial/full (plus False when every
    transfer is cancelled), so steps 1-4 PASS and record the v15 half of the
    TC-NEW-001 mapping table. The workbook's final step asserts the NATIVE v19
    'started' state (a pick step done, nothing delivered) — a value the v15
    selection does not contain at all, so that assertion fails. It is the
    immutable v19 target expectation and classifies as FIXED when v19 passes.
    """
    rpc = ctx.adapter.rpc
    checks = Checks(ctx)
    with ctx.step("Sweep previous FG-03 fixtures (fresh namespace)"):
        sweep_fg03(rpc, ctx.log)
    with ctx.step("Preconditions: delivery_status field + AvaTax does not "
                  "hijack action_confirm"):
        require_field(ctx, rpc, "sale.order", "delivery_status",
                      "mmg_sale_delivery_status (v15) / sale_stock (v19)",
                      "the delivery-status transitions of this TC")
        avatax_confirm_probe(ctx, rpc)
    with ctx.step("Fixture: 2 consumable products (real transfers, no stock "
                  "reservation), auto-invoice off"):
        cid = company_id(rpc)
        flag = get_auto_invoice_flag(rpc, cid)
        selection = _delivery_selection(rpc)
        ctx.log(f"delivery_status selection on v{ctx.env.version}: "
                f"{selection}")
        partner = make_partner(rpc, "Delivery Customer")
        prod_a = make_deliverable(rpc, "Deliverable A", 100.0)
        prod_b = make_deliverable(rpc, "Deliverable B", 100.0)
    try:
        set_auto_invoice_flag(rpc, cid, False)
        with ctx.step("Confirm a 2-line order - nothing delivered yet"):
            order = make_order(rpc, partner,
                               [(prod_a, 1.0, 100.0), (prod_b, 1.0, 100.0)])
            _confirm(ctx, rpc, order)
            picks = pickings_of(rpc, order)
            ctx.log(f"order {order} pickings: {picks}")
            checks.record("a delivery transfer exists", True, bool(picks))
            checks.record("delivery_status after confirm", "pending",
                          _delivery_status(rpc, order))
        with ctx.step("Deliver line 1 only, creating a backorder"):
            _deliver(ctx, rpc, picks[:1], {prod_a: 1.0, prod_b: 0.0})
            checks.record("delivery_status after a partial delivery",
                          "partial", _delivery_status(rpc, order))
        with ctx.step("Validate the backorder in full"):
            _deliver(ctx, rpc, pickings_of(rpc, order))
            checks.record("delivery_status after the full delivery", "full",
                          _delivery_status(rpc, order))
        with ctx.step("Fresh order with ALL transfers cancelled - no status "
                      "at all, not 'pending'"):
            order2 = make_order(rpc, partner, [(prod_a, 1.0, 100.0)])
            _confirm(ctx, rpc, order2)
            picks2 = pickings_of(rpc, order2)
            ok, res = attempt(rpc.call, "stock.picking", "action_cancel",
                              picks2)
            if not ok:
                ctx.log(f"cancelling transfers {picks2} refused: {res}")
            checks.record("delivery_status with every transfer cancelled",
                          False, _delivery_status(rpc, order2))
        with ctx.step("Native-only state: a two-step delivery whose pick step "
                      "is done but nothing delivered reports 'started'"):
            warehouse = multi_step_warehouse(rpc, cid)
            if not warehouse:
                # the workbook lists a two-step route as a precondition; the
                # clone has none, and re-configuring a live warehouse's
                # delivery_steps is out of scope for a QA fixture
                checks.record("delivery_status after the pick step of a "
                              "two-step delivery", "started",
                              f"no multi-step warehouse configured in "
                              f"company {cid}; delivery_status selection = "
                              f"{selection}")
            else:
                ctx.log(f"using warehouse {warehouse['name']!r} "
                        f"(delivery_steps={warehouse['delivery_steps']})")
                order3 = make_order(rpc, partner, [(prod_a, 1.0, 100.0)],
                                    warehouse_id=warehouse["id"])
                _confirm(ctx, rpc, order3)
                picks3 = pickings_of(rpc, order3)
                codes = picking_codes(rpc, picks3)
                internal = [pid for pid, code in codes.items()
                            if code == "internal"]
                ctx.log(f"two-step pickings {codes}; pick step={internal}")
                _deliver(ctx, rpc, internal[:1])
                observed = _delivery_status(rpc, order3)
                ctx.log(f"TC-NEW-001 mapping row: pick step done, "
                        f"qty_delivered 0 -> delivery_status={observed!r}")
                checks.record("delivery_status after the pick step of a "
                              "two-step delivery", "started", observed)
        with ctx.step("Assert the workbook's expected results"):
            checks.assert_all()
    finally:
        with ctx.step("Cleanup fixtures and restore the auto-invoice flag"):
            restore_auto_invoice_flag(ctx, rpc, cid, flag)
            sweep_fg03(rpc, ctx.log)


@test_case(
    id="TEST-FG03-SAL-005",
    name="Delivery status is groupable and filterable in the list",
    workflow="FG-03", workflow_name="Sales & Pricing",
    module="mmg_sale_delivery_status", priority="P2", kind="API", order=316,
    description="search() and read_group() on the stored delivery_status "
                "return the right records and counts. Adaptation: both are "
                "scoped to this execution's fixture orders, since the clone "
                "holds ~43k live orders; the column/filter/group-by UI check "
                "stays manual (logged).",
    traceability=trace("TC-SAL-005"))
def test_sal_005(ctx):
    """Expected v15 outcome: PASS.

    The v15 `delivery_status` is a STORED compute, so it is searchable and
    groupable exactly like the native v19 field the workbook re-points this TC
    at; the four fixture orders reach pending / partial / full / no-status on
    v15 as well. Only the native-only 'started' bucket cannot exist here, and
    this TC does not assert it (TEST-FG03-SAL-004 does). The list-view
    column/filter/group-by walkthrough stays a manual check and is logged.
    """
    rpc = ctx.adapter.rpc
    checks = Checks(ctx)
    with ctx.step("Sweep previous FG-03 fixtures (fresh namespace)"):
        sweep_fg03(rpc, ctx.log)
    with ctx.step("Preconditions: delivery_status field + AvaTax does not "
                  "hijack action_confirm"):
        require_field(ctx, rpc, "sale.order", "delivery_status",
                      "mmg_sale_delivery_status (v15) / sale_stock (v19)",
                      "the searchable/groupable stored field of this TC")
        avatax_confirm_probe(ctx, rpc)
    with ctx.step("Fixture orders in every reachable state: pending, "
                  "partial, full and all-cancelled (auto-invoice off)"):
        cid = company_id(rpc)
        flag = get_auto_invoice_flag(rpc, cid)
        partner = make_partner(rpc, "GroupBy Customer")
        prod_a = make_deliverable(rpc, "Deliverable A", 100.0)
        prod_b = make_deliverable(rpc, "Deliverable B", 100.0)
    try:
        set_auto_invoice_flag(rpc, cid, False)
        fixture = {}
        with ctx.step("Drive one fixture order into each reachable state"):
            fixture["pending"] = make_order(rpc, partner,
                                            [(prod_a, 1.0, 100.0)])
            _confirm(ctx, rpc, fixture["pending"])

            fixture["partial"] = make_order(
                rpc, partner, [(prod_a, 1.0, 100.0), (prod_b, 1.0, 100.0)])
            _confirm(ctx, rpc, fixture["partial"])
            _deliver(ctx, rpc, pickings_of(rpc, fixture["partial"])[:1],
                     {prod_a: 1.0, prod_b: 0.0})

            fixture["full"] = make_order(rpc, partner, [(prod_a, 1.0, 100.0)])
            _confirm(ctx, rpc, fixture["full"])
            _deliver(ctx, rpc, pickings_of(rpc, fixture["full"]))

            fixture[False] = make_order(rpc, partner, [(prod_a, 1.0, 100.0)])
            _confirm(ctx, rpc, fixture[False])
            cancel_me = pickings_of(rpc, fixture[False])
            ok, res = attempt(rpc.call, "stock.picking", "action_cancel",
                              cancel_me)
            if not ok:
                ctx.log(f"cancelling transfers {cancel_me} refused: {res}")

            fixture_ids = sorted(fixture.values())
            observed = {key: _delivery_status(rpc, oid)
                        for key, oid in fixture.items()}
            ctx.log(f"fixture orders by expected state: {fixture}; "
                    f"delivery_status actually reached: {observed}")
        with ctx.step("ORM filter: delivery_status = 'full' returns exactly "
                      "the fully delivered fixture order"):
            found = rpc.search("sale.order",
                               [("id", "in", fixture_ids),
                                ("delivery_status", "=", "full")])
            checks.record("search(delivery_status = 'full')",
                          [fixture["full"]], sorted(found))
        with ctx.step("ORM group: one bucket per populated state with the "
                      "right counts"):
            groups = rpc.read_group("sale.order",
                                    [("id", "in", fixture_ids)], ["id"],
                                    ["delivery_status"])
            counts = {}
            for group in groups:
                key = group.get("delivery_status")
                counts[key] = group.get("__count",
                                        group.get("delivery_status_count", 0))
            checks.record("read_group buckets and counts",
                          {"pending": 1, "partial": 1, "full": 1, False: 1},
                          counts)
        with ctx.step("Column / filter / group-by in the list view (manual)"):
            ctx.log("Manual UI check: Sales > Orders - the Delivery Status "
                    "column (always visible on v15, native v19 ships "
                    "optional='hide' as a badge), a custom filter on it and "
                    "Group By > Delivery Status. The v15-look styling "
                    "decision is recorded in TC-NEW-001.")
        with ctx.step("Assert the workbook's expected results"):
            checks.assert_all()
    finally:
        with ctx.step("Cleanup fixtures and restore the auto-invoice flag"):
            restore_auto_invoice_flag(ctx, rpc, cid, flag)
            sweep_fg03(rpc, ctx.log)


@test_case(
    id="TEST-FG03-SAL-009",
    name="Order warning banner appears when a line has a warned product",
    workflow="FG-03", workflow_name="Sales & Pricing",
    module="mmg_sale_warning_extend", priority="P1", kind="API", order=317,
    description="Adding a warned line makes sale_warning_text carry the "
                "product name and its message immediately; an order with "
                "only unwarned products shows no banner. v15 has no "
                "order-level banner field (the retired module used a popup, "
                "logged as evidence) - expected FAIL.",
    traceability=trace("TC-SAL-009"))
def test_sal_009(ctx):
    """Expected v15 outcome: FAIL — on the banner assertions.

    The workbook asserts the v19 target: the native
    `sale.order.sale_warning_text` banner (FG-03 decision #2 retires
    `mmg_sale_warning_extend`). v15 never had an order-level warning TEXT — the
    retired module only adds `is_show_warning_msg_box` plus the warned-product
    popup action — so `sale_warning_text` does not exist and its absence is
    recorded as the actual value, with the v15 observables logged next to it as
    mapping evidence. The negative half (no banner without warned products)
    passes on both versions. Asserting the v15 popup INSTEAD would make both
    versions green and hide the replacement, so it is deliberately not done.
    """
    rpc = ctx.adapter.rpc
    checks = Checks(ctx)
    message = fx("Fragile artwork - white-glove shipping only")
    with ctx.step("Sweep previous FG-03 fixtures (fresh namespace)"):
        sweep_fg03(rpc, ctx.log)
    with ctx.step("Precondition: the sales-warning field exists on the "
                  "product template"):
        require_field(ctx, rpc, "product.template", "sale_line_warn",
                      "sale_warning + mmg_sale_warning_extend (v15) / "
                      "mmg_sale_warning_block (v19)",
                      "a product carrying a sales warning")
    with ctx.step("Fixture: a product.template with sale_line_warn "
                  "'warning' and its message"):
        partner = make_partner(rpc, "Warning Customer")
        warned = make_product(rpc, "Fragile Artwork", 500.0,
                              sale_line_warn="warning",
                              sale_line_warn_msg=message)
        plain = make_product(rpc, "Plain Artwork", 100.0)
        warned_name = rpc.read("product.product", [warned],
                               ["display_name"])[0]["display_name"]
        exists = rpc.field_exists("sale.order", "sale_warning_text")
        checks.record("sale.order.sale_warning_text exists (native banner)",
                      True, exists)
    try:
        with ctx.step("An order with the warned line shows the banner "
                      "immediately (in-memory recompute, no form reload)"):
            order = make_order(rpc, partner, [(warned, 1.0, 500.0)])
            text = _warning_evidence(ctx, rpc, order)
            ctx.log(f"sale_warning_text = {text!r}")
            _record_banner(checks, text, exists, [
                ("banner mentions the warned product", warned_name),
                ("banner carries the product's warning message", message)])
        with ctx.step("Banner visibility on the form (manual/tour check)"):
            ctx.log("Manual UI check: the alert-warning banner div is visible "
                    "at the top of the order form as soon as the warned line "
                    "is added.")
        with ctx.step("Negative: an order with only unwarned products shows "
                      "no banner"):
            order2 = make_order(rpc, partner, [(plain, 1.0, 100.0)])
            text2 = _warning_evidence(ctx, rpc, order2)
            checks.record("no banner on an order without warned products",
                          True, not (text2 or ""))
        with ctx.step("Assert the workbook's expected results"):
            checks.assert_all()
    finally:
        with ctx.step("Cleanup fixtures"):
            sweep_fg03(rpc, ctx.log)


@test_case(
    id="TEST-FG03-SAL-010",
    name="Warned-product list shows every warned product with its message",
    workflow="FG-03", workflow_name="Sales & Pricing",
    module="mmg_sale_warning_extend", priority="P1", kind="API", order=318,
    description="On a 3-line order the banner lists exactly the two warned "
                "products, each paired with its own message, and never "
                "mentions the unwarned one. v15 exposes this through the "
                "retired popup action instead of a banner (logged as "
                "evidence) - expected FAIL.",
    traceability=trace("TC-SAL-010"))
def test_sal_010(ctx):
    """Expected v15 outcome: FAIL — same cause as TEST-FG03-SAL-009.

    The workbook re-points this TC from the v15 modal
    (`action_open_order_lines_warning_message`, view_mode 'tree' — invalid in
    v19 anyway) to the native inline banner, so the four
    "banner mentions Pn / carries Pn's message" assertions record
    'sale_warning_text absent on this version' on v15 and the retired popup's
    product ids are logged as mapping evidence. The negative half ("P3 not
    mentioned") passes on both versions. Both messages are namespaced with the
    per-execution token so a leftover order from an earlier run can never
    satisfy a containment assertion.
    """
    rpc = ctx.adapter.rpc
    checks = Checks(ctx)
    msg_one, msg_two = fx("Message one"), fx("Message two")
    with ctx.step("Sweep previous FG-03 fixtures (fresh namespace)"):
        sweep_fg03(rpc, ctx.log)
    with ctx.step("Precondition: the sales-warning field exists on the "
                  "product template"):
        require_field(ctx, rpc, "product.template", "sale_line_warn",
                      "sale_warning + mmg_sale_warning_extend (v15) / "
                      "mmg_sale_warning_block (v19)",
                      "products carrying sales warnings")
    with ctx.step("Fixture: P1/P2 warned with distinct messages, P3 "
                  "unwarned"):
        partner = make_partner(rpc, "Warning List Customer")
        prod1 = make_product(rpc, "Warned One", 100.0,
                             sale_line_warn="warning",
                             sale_line_warn_msg=msg_one)
        prod2 = make_product(rpc, "Warned Two", 100.0,
                             sale_line_warn="warning",
                             sale_line_warn_msg=msg_two)
        prod3 = make_product(rpc, "Unwarned Three", 100.0)
        names = {row["id"]: row["display_name"] for row in rpc.read(
            "product.product", [prod1, prod2, prod3], ["display_name"])}
        exists = rpc.field_exists("sale.order", "sale_warning_text")
        checks.record("sale.order.sale_warning_text exists (native banner)",
                      True, exists)
    try:
        with ctx.step("Order with the three lines"):
            order = make_order(rpc, partner, [(prod1, 1.0, 100.0),
                                              (prod2, 1.0, 100.0),
                                              (prod3, 1.0, 100.0)])
        with ctx.step("Exactly the two warned products, each with its own "
                      "message; the unwarned product is absent"):
            text = _warning_evidence(ctx, rpc, order)
            ctx.log(f"sale_warning_text = {text!r}")
            _record_banner(checks, text, exists, [
                ("banner mentions P1", names[prod1]),
                ("banner carries P1's message", msg_one),
                ("banner mentions P2", names[prod2]),
                ("banner carries P2's message", msg_two)])
            checks.record("banner does not mention the unwarned P3", False,
                          names[prod3] in (text or ""))
            # v15 evidence for the mapping table: the retired popup action
            _action, popup_ids = warned_products_v15(rpc, order)
            if popup_ids:
                ctx.log(f"v15 popup product ids={popup_ids} "
                        f"(P1={prod1} P2={prod2} P3={prod3})")
        with ctx.step("The list is read-only and needs no click on v19"):
            ctx.log("v15 shows the list through the read-only popup action "
                    "(action_open_order_lines_warning_message, view_mode "
                    "'tree'); v19 shows it inline in the native banner - the "
                    "modal is retired (FG-03 decision #2).")
        with ctx.step("Assert the workbook's expected results"):
            checks.assert_all()
    finally:
        with ctx.step("Cleanup fixtures"):
            sweep_fg03(rpc, ctx.log)


@test_case(
    id="TEST-FG03-SAL-012",
    name="Banner clears when the warned line is removed",
    workflow="FG-03", workflow_name="Sales & Pricing",
    module="mmg_sale_warning_extend", priority="P2", kind="API", order=319,
    description="Removing the warned line empties sale_warning_text and "
                "re-adding it brings the banner back (proper @api.depends on "
                "order_line). v15 has no banner field at all; note that its "
                "missing-@api.depends refresh bug is only observable in a "
                "live form, since every RPC call recomputes.",
    traceability=trace("TC-SAL-012"))
def test_sal_012(ctx):
    """Expected v15 outcome: FAIL — on the two precondition/return assertions.

    `sale.order.sale_warning_text` does not exist on v15, so "banner mentions
    the warned product" (before) and "banner mentions it again" (after
    re-adding) record the field's absence, while the middle assertion (banner
    empty after removing the line) passes trivially. Documented limitation: the
    v15 refresh bug this TC targets — `_compute_is_show_warning_msg_box` has no
    `@api.depends` — is only observable in a live form, because every RPC call
    runs in its own transaction and recomputes the non-stored field anyway; that
    half belongs to a UI tour, not to this API test.
    """
    rpc = ctx.adapter.rpc
    checks = Checks(ctx)
    message = fx("Handle with care")
    with ctx.step("Sweep previous FG-03 fixtures (fresh namespace)"):
        sweep_fg03(rpc, ctx.log)
    with ctx.step("Precondition: the sales-warning field exists on the "
                  "product template"):
        require_field(ctx, rpc, "product.template", "sale_line_warn",
                      "sale_warning + mmg_sale_warning_extend (v15) / "
                      "mmg_sale_warning_block (v19)",
                      "the warned line this TC adds and removes")
    with ctx.step("Fixture: order with exactly one warned line"):
        partner = make_partner(rpc, "Banner Clear Customer")
        warned = make_product(rpc, "Fragile Artwork", 500.0,
                              sale_line_warn="warning",
                              sale_line_warn_msg=message)
        warned_name = rpc.read("product.product", [warned],
                               ["display_name"])[0]["display_name"]
        exists = rpc.field_exists("sale.order", "sale_warning_text")
        checks.record("sale.order.sale_warning_text exists (native banner)",
                      True, exists)
        order = make_order(rpc, partner, [(warned, 1.0, 500.0)])
        text = _warning_evidence(ctx, rpc, order)
        _record_banner(checks, text, exists, [
            ("precondition: banner mentions the warned product",
             warned_name)])
    try:
        with ctx.step("Remove the warned line - the banner disappears "
                      "without a form reload"):
            line = order_lines(rpc, order, ["id"])[0]["id"]
            rpc.write("sale.order", [order], {"order_line": [(2, line, 0)]})
            text = _warning_evidence(ctx, rpc, order)
            ctx.log(f"sale_warning_text after removal = {text!r}")
            checks.record("banner empty after removing the warned line",
                          True, not (text or ""))
        with ctx.step("Re-add the warned line - the banner returns "
                      "(the dependency triggers in both directions)"):
            rpc.write("sale.order", [order], {"order_line": [(0, 0, {
                "product_id": warned, "name": warned_name,
                "product_uom_qty": 1.0, "price_unit": 500.0})]})
            text = _warning_evidence(ctx, rpc, order)
            ctx.log(f"sale_warning_text after re-adding = {text!r}")
            _record_banner(checks, text, exists, [
                ("banner mentions the warned product again", warned_name)])
        with ctx.step("Assert the workbook's expected results"):
            checks.assert_all()
    finally:
        with ctx.step("Cleanup fixtures"):
            sweep_fg03(rpc, ctx.log)


@test_case(
    id="TEST-FG03-SAL-011",
    name="Warning fields settable at template level",
    workflow="FG-03", workflow_name="Sales & Pricing",
    module="mmg_sale_warning_extend", priority="P1", kind="API", order=320,
    description="A template-level warning flows to every variant with no "
                "per-variant entry; 'block' must raise a UserError on "
                "confirm and leave the order draft (v19 "
                "mmg_sale_warning_block - v15 core only warns through an "
                "onchange, expected FAIL); a fresh template defaults to "
                "'no-message'.",
    traceability=trace("TC-SAL-011"))
def test_sal_011(ctx):
    """Expected v15 outcome: FAIL — on the banner halves and on the block gate.

    Two independent v19-target expectations fail here and both are immutable:
    (a) the banner assertions need `sale.order.sale_warning_text`, which v15
    does not have (see TEST-FG03-SAL-009); (b) v15 core `sale_warning` only
    warns through `sale.order.line`'s onchange, so `action_confirm()` on a
    'block' product SUCCEEDS where the workbook requires a UserError naming the
    product and the order left in 'draft' — the gate arrives with the new
    mmg_sale_warning_block module in v19. What does pass on v15: the two
    variants are generated from the attribute, and a fresh template defaults to
    'no-message'.
    """
    rpc = ctx.adapter.rpc
    checks = Checks(ctx)
    message = fx("Template-level warning")
    with ctx.step("Sweep previous FG-03 fixtures (fresh namespace)"):
        sweep_fg03(rpc, ctx.log)
    with ctx.step("Preconditions: the sales-warning field + AvaTax does not "
                  "hijack action_confirm"):
        require_field(ctx, rpc, "product.template", "sale_line_warn",
                      "sale_warning + mmg_sale_warning_extend (v15) / "
                      "mmg_sale_warning_block (v19)",
                      "the template-level warning and the 'block' gate")
        avatax_confirm_probe(ctx, rpc)
    with ctx.step("Fixture: a template with 2 variants, auto-invoice off"):
        cid = company_id(rpc)
        flag = get_auto_invoice_flag(rpc, cid)
        partner = make_partner(rpc, "Template Warning Customer")
        attribute = rpc.create("product.attribute",
                               {"name": label("Size"),
                                "create_variant": "always"})
        value_ids = [rpc.create("product.attribute.value",
                                {"name": label(size),
                                 "attribute_id": attribute})
                     for size in ("Small", "Large")]
        # make_product returns a variant; here the template itself is needed
        variant = make_product(
            rpc, "Variant Artwork", 200.0,
            attribute_line_ids=[(0, 0, {"attribute_id": attribute,
                                        "value_ids": [(6, 0, value_ids)]})])
        template = m2o_id(rpc.read("product.product", [variant],
                                   ["product_tmpl_id"])[0]["product_tmpl_id"])
        variants = variants_of(rpc, template)
        ctx.check("two variants generated", 2, len(variants))
        exists = rpc.field_exists("sale.order", "sale_warning_text")
        checks.record("sale.order.sale_warning_text exists (native banner)",
                      True, exists)
    try:
        set_auto_invoice_flag(rpc, cid, False)
        with ctx.step("Set the warning and its message on the template"):
            rpc.write("product.template", [template],
                      {"sale_line_warn": "warning",
                       "sale_line_warn_msg": message})
        with ctx.step("An order on variant #1 carries the template warning"):
            order1 = make_order(rpc, partner, [(variants[0], 1.0, 200.0)])
            text = _warning_evidence(ctx, rpc, order1)
            _record_banner(checks, text, exists, [
                ("variant #1 banner carries the template message", message)])
        with ctx.step("An order on variant #2 carries it too - no "
                      "per-variant entry needed"):
            order2 = make_order(rpc, partner, [(variants[1], 1.0, 200.0)])
            text = _warning_evidence(ctx, rpc, order2)
            _record_banner(checks, text, exists, [
                ("variant #2 banner carries the template message", message)])
        with ctx.step("Switch the template to 'block': confirmation raises "
                      "and the order stays draft"):
            rpc.write("product.template", [template],
                      {"sale_line_warn": "block",
                       "sale_line_warn_msg": message})
            order3 = make_order(rpc, partner, [(variants[0], 1.0, 200.0)])
            ok, res = attempt(rpc.call, "sale.order", "action_confirm",
                              [order3])
            ctx.log(f"confirm of a blocked product: ok={ok} result={res!r}")
            checks.record("confirmation refused for a 'block' product", True,
                          not ok)
            checks.record("blocking message names the product", True,
                          (not ok) and names_product(res, variants, rpc))
            state = rpc.read("sale.order", [order3], ["state"])[0]["state"]
            checks.record("order state after the blocked confirm", "draft",
                          state)
        with ctx.step("A fresh template defaults to 'no-message'"):
            fresh = rpc.create("product.template",
                               {"name": label("Fresh product")})
            got = rpc.read("product.template", [fresh],
                           ["sale_line_warn"])[0]["sale_line_warn"]
            checks.record("default sale_line_warn on a new template",
                          "no-message", got)
        with ctx.step("Assert the workbook's expected results"):
            checks.assert_all()
    finally:
        with ctx.step("Cleanup fixtures and restore the auto-invoice flag"):
            restore_auto_invoice_flag(ctx, rpc, cid, flag)
            sweep_fg03(rpc, ctx.log)


def names_product(error_message, variant_ids, rpc) -> bool:
    """True when the blocking error names one of the blocked variants — the
    workbook requires _confirmation_error_message() to list the product."""
    if not isinstance(error_message, str):
        return False
    labels = [row["display_name"] for row in
              rpc.read("product.product", list(variant_ids),
                       ["display_name"])]
    return any(label and label in error_message for label in labels)
