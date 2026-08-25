"""FG-03 — pick-up-at-store handling and the Display Invoices field:
TC-SAL-001, TC-SAL-002, TC-SAL-022, TC-SAL-003, TC-DAT-010.

Verified v15 implementation (`mmg_sale/models/sale_order.py`): both the
`create` and the `write` override rewrite `partner_shipping_id` to
`env.company.partner_id` when `is_pickup_at_store` is set truthy, and
`display_invoice_ids` is a compute on `_get_invoiced` filtering
`order_line.invoice_lines.move_id` to non-cancelled out_invoice/out_refund
moves — the same expression the v19 port keeps.

Note on the batch-create step of TC-SAL-001 (FG-03 BC-001): the v15 override
is written `@api.model def create(self, vals)`, and what a *list* of vals does
to that signature is [UNVERIFIED] here — the Odoo 15 core tree is not part of
this workspace, so the claim cannot be grounded in source. Two outcomes are
possible and the test records whichever happens instead of asserting a
mechanism:

* if core wraps a method named `create` per record, the rewrite applies to the
  flagged record only and the workbook's step 3 PASSES;
* if the override receives the list itself, `'is_pickup_at_store' in vals` is
  False for a list (no rewrite), and — more decisively —
  `mmg_magento2_ept_inherit.sale.order.create()`, also `@api.model`, calls
  `res._check_positive_quantity()`, which starts with `ensure_one()` and
  therefore raises "Expected singleton" on the 2-record result, i.e. the batch
  create is refused outright.

The second outcome is the more likely one and is what the plan records as the
expected v15 baseline; either way the workbook expectation itself is asserted
unchanged, and the v19 `@api.model_create_multi` port makes the contract
explicit.
"""
from framework.registry import test_case
from tests.fg03.common import (Checks, MARK, QA_PARTNER_SQL, add_line,
                               attempt, avatax_confirm_probe, company_id,
                               company_partner, get_auto_invoice_flag,
                               invoice_or_block, line_state, m2o_id,
                               make_order, make_partner, make_product,
                               order_lines, order_origin, reconcile,
                               require_field, restore_auto_invoice_flag,
                               reverse_invoice, rounded,
                               set_auto_invoice_flag, sweep_fg03, trace)


@test_case(
    id="TEST-FG03-SAL-001",
    name="Pick up at Store rewrites the delivery address",
    workflow="FG-03", workflow_name="Sales & Pricing", module="mmg_sale",
    priority="P0", kind="API", order=306,
    description="Write, create and import/API batch-create paths all rewrite "
                "partner_shipping_id to the company partner for flagged "
                "orders only. The write and create paths pass on v15; the "
                "batch create is expected to be refused there (single-vals "
                "overrides throughout) and its outcome is recorded verbatim - "
                "BC-001 is the v19 fix. The AvaTax jurisdiction step belongs "
                "to TC-TAX-009 (AvaTax sandbox) and is logged here.",
    traceability=trace("TC-SAL-001"))
def test_sal_001(ctx):
    """Expected v15 outcome: FAIL — on the import/API batch-create step only.

    Steps 1 and 2 (write path, create path) exercise `mmg_sale`'s two
    single-vals overrides and PASS on v15: `partner_shipping_id` becomes the
    company partner on both paths. Step 3 creates TWO orders in one call, and
    the v15 stack is written for a single vals dict throughout — see the module
    docstring for the two candidate mechanisms ([UNVERIFIED] which fires) —
    so the batch outcome is recorded verbatim as the actual value. FG-03 BC-001
    (`@api.model_create_multi`) is the v19 fix, so this classifies as FIXED
    when v19 passes; if v15 turns out to loop per record after all, step 3
    passes and the test is simply green.

    The AvaTax jurisdiction step of the workbook belongs to TC-TAX-009 (AvaTax
    sandbox) and is logged as evidence, never asserted, here.
    """
    rpc = ctx.adapter.rpc
    checks = Checks(ctx)
    with ctx.step("Sweep previous FG-03 fixtures (fresh namespace)"):
        sweep_fg03(rpc, ctx.log)
    with ctx.step("Precondition: the pick-up flag exists on sale.order"):
        require_field(ctx, rpc, "sale.order", "is_pickup_at_store", "mmg_sale",
                      "the pick-up address rewrite of this TC")
    with ctx.step("Fixture: customer with its own address; company partner"):
        cid = company_id(rpc)
        gallery = company_partner(rpc, cid)
        partner = make_partner(rpc, "Pickup Customer")
        product = make_product(rpc, "Artwork 500", 500.0)
        ctx.check("customer differs from the company partner", True,
                  partner != gallery)
    try:
        with ctx.step("Write path: a plain order ships to the customer, then "
                      "is_pickup_at_store = True rewrites it to the gallery"):
            order = make_order(rpc, partner, [(product, 1.0, 500.0)])
            before = rpc.read("sale.order", [order],
                              ["partner_shipping_id"])[0]
            checks.record("shipping address before the flag", partner,
                          m2o_id(before["partner_shipping_id"]))
            rpc.write("sale.order", [order], {"is_pickup_at_store": True})
            after = rpc.read("sale.order", [order],
                             ["partner_shipping_id"])[0]
            checks.record("shipping address after write(flag=True)", gallery,
                          m2o_id(after["partner_shipping_id"]))
        with ctx.step("Create path: an order created with the flag set ships "
                      "to the gallery"):
            order2 = rpc.create("sale.order", {
                "partner_id": partner, "origin": order_origin(),
                "is_pickup_at_store": True})
            got = rpc.read("sale.order", [order2],
                           ["partner_shipping_id"])[0]
            checks.record("shipping address on create(flag=True)", gallery,
                          m2o_id(got["partner_shipping_id"]))
        with ctx.step("Import/API batch create: only the flagged record is "
                      "rewritten, the unflagged one keeps the customer "
                      "address"):
            ok, res = attempt(rpc.create, "sale.order", [
                {"partner_id": partner, "origin": order_origin(),
                 "is_pickup_at_store": True},
                {"partner_id": partner, "origin": order_origin()},
            ])
            if not ok or not isinstance(res, list) or len(res) != 2:
                checks.record("batch create returns two order ids", True,
                              f"batch create outcome: {res!r}")
            else:
                picked, normal = res
                rows = {r["id"]: r for r in rpc.read(
                    "sale.order", [picked, normal],
                    ["partner_shipping_id", "is_pickup_at_store"])}
                checks.record("flagged batch order ships to the gallery",
                              gallery,
                              m2o_id(rows[picked]["partner_shipping_id"]))
                checks.record("unflagged batch order keeps the customer "
                              "address", partner,
                              m2o_id(rows[normal]["partner_shipping_id"]))
        with ctx.step("AvaTax jurisdiction on pick-up orders "
                      "(cross-referenced)"):
            ctx.log("Tax jurisdiction of a pick-up order must follow the "
                    "gallery address: owned by TC-TAX-009 on the "
                    "AvaTax-configured staging DB. The QA clone is "
                    "neutralized (no AvaTax credentials, connector instances "
                    "inactive), so this step is evidence-only here.")
        with ctx.step("Assert the workbook's expected results"):
            checks.assert_all()
    finally:
        with ctx.step("Cleanup fixtures"):
            sweep_fg03(rpc, ctx.log)


@test_case(
    id="TEST-FG03-SAL-002",
    name="Un-ticking Pick up at Store",
    workflow="FG-03", workflow_name="Sales & Pricing", module="mmg_sale",
    priority="P1", kind="API", order=307,
    description="Un-ticking the flag does NOT restore the customer address "
                "(documented one-way behaviour, identical on v15 and v19); a "
                "manual correction afterwards persists.",
    traceability=trace("TC-SAL-002"))
def test_sal_002(ctx):
    """Expected v15 outcome: PASS.

    The workbook's expectation IS the v15 behaviour: the override only rewrites
    on a truthy write, so un-ticking is a one-way operation and nothing
    restores the customer address; a manual correction afterwards persists.
    This test therefore records the documented baseline that v19 must match —
    a PASS here is the evidence, not the absence of a finding.
    """
    rpc = ctx.adapter.rpc
    checks = Checks(ctx)
    with ctx.step("Sweep previous FG-03 fixtures (fresh namespace)"):
        sweep_fg03(rpc, ctx.log)
    with ctx.step("Precondition: the pick-up flag exists on sale.order"):
        require_field(ctx, rpc, "sale.order", "is_pickup_at_store", "mmg_sale",
                      "the un-tick behaviour of this TC")
    with ctx.step("Fixture: a pick-up order (shipping already the gallery)"):
        gallery = company_partner(rpc)
        partner = make_partner(rpc, "Untick Customer")
        order = rpc.create("sale.order", {
            "partner_id": partner, "origin": order_origin(),
            "is_pickup_at_store": True})
        got = rpc.read("sale.order", [order], ["partner_shipping_id"])[0]
        ctx.check("precondition: shipping is the gallery partner", gallery,
                  m2o_id(got["partner_shipping_id"]))
    try:
        with ctx.step("Un-tick the flag — the gallery address stays "
                      "(one-way operation, nothing restores the customer)"):
            rpc.write("sale.order", [order], {"is_pickup_at_store": False})
            got = rpc.read("sale.order", [order],
                           ["partner_shipping_id", "is_pickup_at_store"])[0]
            checks.record("flag is off", False, got["is_pickup_at_store"])
            checks.record("shipping address after un-ticking", gallery,
                          m2o_id(got["partner_shipping_id"]))
            ctx.log(f"v{ctx.env.version} baseline recorded: un-ticking Pick "
                    "up at Store keeps the gallery address")
        with ctx.step("Manual correction of the shipping address persists "
                      "while the flag is off"):
            rpc.write("sale.order", [order],
                      {"partner_shipping_id": partner})
            got = rpc.read("sale.order", [order],
                           ["partner_shipping_id"])[0]
            checks.record("manually restored customer address sticks",
                          partner, m2o_id(got["partner_shipping_id"]))
        with ctx.step("Assert the workbook's expected results"):
            checks.assert_all()
    finally:
        with ctx.step("Cleanup fixtures"):
            sweep_fg03(rpc, ctx.log)


@test_case(
    id="TEST-FG03-SAL-022",
    name="Duplicate a sales order",
    workflow="FG-03", workflow_name="Sales & Pricing", module="mmg_sale",
    priority="P2", kind="API", order=308,
    description="copy() of a confirmed pick-up order yields a draft carrying "
                "x_discount 100 with the converted discount 10.00 (v19 "
                "formula — v15 stores 20.00, expected FAIL), a consistent "
                "flag/address pair, and a confirmed total equal to the "
                "original.",
    traceability=trace("TC-SAL-022"))
def test_sal_022(ctx):
    """Expected v15 outcome: FAIL — on the copied discount only.

    The fixture's dollar discount is applied with a `write()` (the path a
    salesperson's save takes on v15, since `create()` has no hook there — that
    gap is TEST-FG03-SAL-007's subject, not this TC's), so v15 stores 20.00 and
    the copy faithfully carries 20.00 where the workbook expects the v19
    per-line-total 10.00. Everything else passes on v15: the copy is 'draft',
    x_discount 100.0 is preserved, the pick-up flag and the gallery address
    agree on the copy, a manual address correction persists after clearing the
    flag, and the confirmed copy's total equals the original's.
    """
    rpc = ctx.adapter.rpc
    checks = Checks(ctx)
    with ctx.step("Sweep previous FG-03 fixtures (fresh namespace)"):
        sweep_fg03(rpc, ctx.log)
    with ctx.step("Preconditions: the pick-up flag + AvaTax does not hijack "
                  "action_confirm"):
        require_field(ctx, rpc, "sale.order", "is_pickup_at_store", "mmg_sale",
                      "the pick-up flag carried by the duplicate")
        avatax_confirm_probe(ctx, rpc)
    with ctx.step("Fixture: confirmed pick-up order, qty 2 x 500 with "
                  "x_discount = 100 (auto-invoice off)"):
        cid = company_id(rpc)
        flag = get_auto_invoice_flag(rpc, cid)
        gallery = company_partner(rpc, cid)
        partner = make_partner(rpc, "Copy Customer")
        product = make_product(rpc, "Artwork 500", 500.0)
    try:
        set_auto_invoice_flag(rpc, cid, False)
        order = make_order(rpc, partner, [(product, 2.0, 500.0)],
                           is_pickup_at_store=True)
        line = order_lines(rpc, order, ["id"])[0]["id"]
        # write (not create) so the v15 conversion hook fires — the missing
        # create hook is TEST-FG03-SAL-007's subject, not this TC's
        attempt(rpc.write, "sale.order.line", [line], {"x_discount": 100.0})
        ctx.log(f"fixture line state: {line_state(rpc, line)}")
        ok, res = attempt(rpc.call, "sale.order", "action_confirm", [order])
        ctx.log(f"fixture confirm ok={ok} result={res!r}")
        with ctx.step("Duplicate the order"):
            ok, copy_id = attempt(rpc.call, "sale.order", "copy", [order])
            if not ok:
                checks.record("copy() succeeds", True, f"refused: {copy_id}")
                copy_id = None
            else:
                got = rpc.read("sale.order", [copy_id],
                               ["state", "is_pickup_at_store",
                                "partner_shipping_id", "amount_total"])[0]
                checks.record("copy state", "draft", got["state"])
        with ctx.step("The copied line carries x_discount 100 with its "
                      "converted discount 10.00 (not doubled, not dropped)"):
            if copy_id:
                copied = order_lines(rpc, copy_id,
                                     ["x_discount", "discount"])[0]
                checks.record("copied line x_discount", 100.0,
                              copied["x_discount"])
                checks.record("copied line discount", 10.0,
                              rounded(copied["discount"]))
        with ctx.step("Pick-up flag and shipping address agree on the copy"):
            if copy_id:
                checks.record("copy is_pickup_at_store", True,
                              got["is_pickup_at_store"])
                checks.record("copy ships to the gallery", gallery,
                              m2o_id(got["partner_shipping_id"]))
        with ctx.step("Clear the flag on the copy and write the customer "
                      "address back — it persists"):
            if copy_id:
                rpc.write("sale.order", [copy_id],
                          {"is_pickup_at_store": False,
                           "partner_shipping_id": partner})
                now = rpc.read("sale.order", [copy_id],
                               ["partner_shipping_id"])[0]
                checks.record("customer address persists on the copy",
                              partner, m2o_id(now["partner_shipping_id"]))
        with ctx.step("Confirm the copy — its total equals the original"):
            if copy_id:
                ok, res = attempt(rpc.call, "sale.order", "action_confirm",
                                  [copy_id])
                totals = {r["id"]: rounded(r["amount_total"]) for r in
                          rpc.read("sale.order", [order, copy_id],
                                   ["amount_total"])}
                ctx.log(f"totals: original={totals[order]} "
                        f"copy={totals[copy_id]} (confirm ok={ok})")
                checks.record("confirmed copy amount_total",
                              totals[order], totals[copy_id])
        with ctx.step("Assert the workbook's expected results"):
            checks.assert_all()
    finally:
        with ctx.step("Cleanup fixtures and restore the auto-invoice flag"):
            restore_auto_invoice_flag(ctx, rpc, cid, flag)
            sweep_fg03(rpc, ctx.log)


@test_case(
    id="TEST-FG03-SAL-003",
    name="Display Invoices on the order excludes cancelled",
    workflow="FG-03", workflow_name="Sales & Pricing", module="mmg_sale",
    priority="P1", kind="API", order=309,
    description="display_invoice_ids holds exactly the posted invoice, the "
                "draft invoice and the posted credit note; the cancelled "
                "invoice is excluded but still present in native "
                "invoice_ids. The many2many_tags click-through stays a "
                "manual UI check (logged).",
    traceability=trace("TC-SAL-003"))
def test_sal_003(ctx):
    """Expected v15 outcome: PASS.

    `display_invoice_ids` is the same compute in the v19 port
    (`order_line.invoice_lines.move_id` filtered to non-cancelled
    out_invoice/out_refund), and sale's `_copy_data_extend_business_fields`
    keeps `sale_line_ids` on the reversal, so the credit note is included and
    the cancelled invoice is excluded while remaining in native `invoice_ids`.
    This test therefore records the v15 baseline the v19 run is compared
    against. Accounting preconditions (invoice creation, posting) BLOCK with the
    server's own message instead of reporting a false defect in the field under
    test. The many2many_tags click-through stays a manual UI check and is
    logged.
    """
    rpc = ctx.adapter.rpc
    checks = Checks(ctx)
    with ctx.step("Sweep previous FG-03 fixtures (fresh namespace)"):
        sweep_fg03(rpc, ctx.log)
    with ctx.step("Preconditions: display_invoice_ids exists + AvaTax does "
                  "not hijack action_confirm"):
        require_field(ctx, rpc, "sale.order", "display_invoice_ids",
                      "mmg_sale", "the Display Invoices field under test")
        avatax_confirm_probe(ctx, rpc)
    with ctx.step("Fixture: confirmed order with an invoiceable line "
                  "(invoice_policy 'order', auto-invoice off)"):
        cid = company_id(rpc)
        flag = get_auto_invoice_flag(rpc, cid)
        partner = make_partner(rpc, "Invoice Customer")
        product = make_product(rpc, "Artwork 500", 500.0)
    try:
        set_auto_invoice_flag(rpc, cid, False)
        order = make_order(rpc, partner, [(product, 1.0, 500.0)])
        rpc.call("sale.order", "action_confirm", [order])
        inv_a = inv_b = inv_c = inv_r = None
        with ctx.step("Invoice A: create it from the order and post it"):
            inv_a = invoice_or_block(ctx, rpc, order, "invoice A")
            ok, res = attempt(rpc.call, "account.move", "action_post",
                              [inv_a])
            if not ok:
                ctx.blocked(
                    "posting a customer invoice is refused on this database "
                    f"({res}) — an accounting precondition of this TC "
                    "(open period / posted-entry rights), not a defect in "
                    "the field under test")
        with ctx.step("Invoice B: add a line, invoice again, leave it draft"):
            add_line(rpc, order, product, qty=1.0, price=500.0)
            inv_b = invoice_or_block(ctx, rpc, order, "invoice B")
        with ctx.step("Invoice C: add a line, invoice again, cancel it"):
            add_line(rpc, order, product, qty=1.0, price=500.0)
            inv_c = invoice_or_block(ctx, rpc, order, "invoice C")
            ok, res = attempt(rpc.call, "account.move", "button_cancel",
                              [inv_c])
            if not ok:
                ctx.log(f"cancelling invoice C refused: {res}")
        with ctx.step("Credit note R: reverse invoice A and post it"):
            ok, new_moves = attempt(reverse_invoice, rpc, inv_a,
                                    "FG-03 QA reversal")
            if not ok:
                ctx.log(f"account.move.reversal refused: {new_moves}")
                new_moves = []
            checks.record("one credit note created by the reversal", 1,
                          len(new_moves))
            if new_moves:
                inv_r = new_moves[0]
                ok, res = attempt(rpc.call, "account.move", "action_post",
                                  [inv_r])
                got = rpc.read("account.move", [inv_r],
                               ["state", "move_type"])[0]
                checks.record("credit note move_type", "out_refund",
                              got["move_type"])
                checks.record("credit note state", "posted",
                              got["state"] if ok else res)
        with ctx.step("display_invoice_ids == {A, B, R}: the cancelled "
                      "invoice C is excluded"):
            got = rpc.read("sale.order", [order],
                           ["display_invoice_ids", "invoice_ids"])[0]
            ctx.log(f"invoice_ids={sorted(got['invoice_ids'])} "
                    f"display_invoice_ids="
                    f"{sorted(got['display_invoice_ids'])} "
                    f"(A={inv_a} B={inv_b} C={inv_c} R={inv_r})")
            expected = sorted(i for i in (inv_a, inv_b, inv_r) if i)
            checks.record("display_invoice_ids", expected,
                          sorted(got["display_invoice_ids"]))
        with ctx.step("Native invoice_ids still includes the cancelled "
                      "invoice — the custom field is still needed"):
            checks.record("cancelled invoice C in native invoice_ids", True,
                          inv_c in got["invoice_ids"])
        with ctx.step("Invoice tag click-through (manual UI check)"):
            ctx.log("Manual UI check: every tag of the Invoices "
                    "many2many_tags widget on the order form (mmg_sale view, "
                    "after payment_term_id) opens the corresponding move "
                    "form on click.")
        with ctx.step("Assert the workbook's expected results"):
            checks.assert_all()
    finally:
        with ctx.step("Cleanup fixtures and restore the auto-invoice flag"):
            restore_auto_invoice_flag(ctx, rpc, cid, flag)
            sweep_fg03(rpc, ctx.log)


@test_case(
    id="TEST-FG03-DAT-010",
    name="Sale-order to invoice linkage intact",
    workflow="FG-03", workflow_name="Sales & Pricing", module="mmg_sale",
    priority="P1", kind="DATA", order=310,
    description="Read-only reconciliation: sale_order_line_invoice_rel row "
                "count and the per-order invoice_status distribution "
                "(QA fixtures excluded) are persisted on v15 and diffed on "
                "v19, plus the relation-name verification and an ORM spot "
                "check that display_invoice_ids equals "
                "order_line.invoice_lines.move_id minus cancelled moves.",
    traceability=trace("TC-DAT-010"))
def test_dat_010(ctx):
    """Expected v15 outcome: PASS — it captures and persists the baseline.

    Read-only. The workbook's step 2 (verify the relation before querying it)
    is honoured literally: `fields_get` on `sale.order.line.invoice_lines` plus
    an information_schema check that `sale_order_line_invoice_rel` really has
    `order_line_id` / `invoice_line_id`, and the captured query uses the
    verified table name. The link-row count and the invoice_status distribution
    exclude this platform's fixture partners so reruns cannot drift the
    baseline; the ORM spot check compares `display_invoice_ids` against the
    recomputed set on the 20 lowest-id invoiced orders and asserts the diff
    dict once (collected assertions), so one drifting order does not hide the
    other 19. BLOCKED when the environment has no read-only PostgreSQL
    configuration, which the workbook lists as a precondition.
    """
    rpc = ctx.adapter.rpc
    checks = Checks(ctx)
    probe = {}

    with ctx.step("Verify the link relation before querying it "
                  "(sale.order.line.invoice_lines)"):
        info = rpc.call("sale.order.line", "fields_get", ["invoice_lines"],
                        attributes=["type", "relation"])
        meta = info.get("invoice_lines") or {}
        ctx.log(f"fields_get(invoice_lines) = {meta}")
        probe["table"] = ("sale_order_line_invoice_rel"
                          if ctx.sql.column_exists(
                              "sale_order_line_invoice_rel", "order_line_id")
                          else None)
        checks.record("invoice_lines relation model", "account.move.line",
                      meta.get("relation"))
        checks.record("invoice_lines field type", "many2many",
                      meta.get("type"))
        checks.record("link table sale_order_line_invoice_rel "
                      "(order_line_id / invoice_line_id)", True,
                      bool(probe["table"]) and ctx.sql.column_exists(
                          "sale_order_line_invoice_rel", "invoice_line_id"))

    def capture(inner_ctx):
        out = {}
        if probe["table"]:
            out["sale_order_line_invoice_rel rows"] = inner_ctx.sql.one(
                f"SELECT count(*) FROM {probe['table']} r "
                "JOIN sale_order_line l ON l.id = r.order_line_id "
                "JOIN sale_order o ON o.id = l.order_id "
                f"WHERE o.partner_id NOT IN {QA_PARTNER_SQL}")
        else:
            out["sale_order_line_invoice_rel rows"] = "link table absent"
        for status, count in inner_ctx.sql.rows(
                "SELECT coalesce(invoice_status, 'none'), count(*) "
                "FROM sale_order "
                f"WHERE partner_id NOT IN {QA_PARTNER_SQL} "
                "GROUP BY 1 ORDER BY 1"):
            out[f"invoice_status:{status}"] = count
        return out

    reconcile(ctx, "TC-DAT-010", capture)

    with ctx.step("ORM spot check: display_invoice_ids equals "
                  "order_line.invoice_lines.move_id without cancelled moves "
                  "(20 lowest-id invoiced orders, QA fixtures excluded)"):
        if not rpc.field_exists("sale.order", "display_invoice_ids"):
            checks.record("display_invoice_ids exists on sale.order", True,
                          "field absent — mmg_sale not installed here")
        else:
            groups = rpc.read_group(
                "sale.order.line",
                [("invoice_lines", "!=", False),
                 ("order_id.partner_id.name", "not like", MARK)],
                ["order_id"], ["order_id"], limit=20, orderby="order_id")
            order_ids = [m2o_id(g["order_id"]) for g in groups
                         if g.get("order_id")]
            ctx.log(f"spot-check orders: {order_ids}")
            lines = rpc.search_read("sale.order.line",
                                    [("order_id", "in", order_ids)],
                                    ["order_id", "invoice_lines"])
            ml_ids = sorted({i for row in lines for i in row["invoice_lines"]})
            move_of = {}
            if ml_ids:
                for row in rpc.search_read("account.move.line",
                                           [("id", "in", ml_ids)],
                                           ["move_id"]):
                    move_of[row["id"]] = m2o_id(row["move_id"])
            keep = set()
            move_ids = sorted(set(move_of.values()))
            if move_ids:
                for row in rpc.search_read("account.move",
                                           [("id", "in", move_ids)],
                                           ["move_type", "state"]):
                    if row["move_type"] in ("out_invoice", "out_refund") \
                            and row["state"] != "cancel":
                        keep.add(row["id"])
            expected = {oid: set() for oid in order_ids}
            for row in lines:
                oid = m2o_id(row["order_id"])
                for ml in row["invoice_lines"]:
                    move = move_of.get(ml)
                    if move in keep:
                        expected[oid].add(move)
            actual = {row["id"]: set(row["display_invoice_ids"]) for row in
                      rpc.read("sale.order", order_ids,
                               ["display_invoice_ids"])}
            diffs = {oid: {"computed": sorted(expected[oid]),
                           "display_invoice_ids": sorted(actual.get(oid, []))}
                     for oid in order_ids
                     if expected[oid] != actual.get(oid, set())}
            checks.record(f"orders whose display_invoice_ids differs from the "
                          f"computed set ({len(order_ids)} checked)", {},
                          diffs)

    with ctx.step("Assert the workbook's expected results"):
        checks.assert_all()
