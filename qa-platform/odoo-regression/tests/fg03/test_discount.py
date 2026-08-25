"""FG-03 — dollar-to-percentage discount conversion:
TC-SAL-006 (blocked stub), TC-SAL-007, TC-SAL-008 (blocked stub),
TC-SAL-019, TC-SAL-020, TC-STU-004.

The workbook's expected values encode the v19 formula fixed by FG-03
decision #4b: `discount = x_discount * 100 / (price_unit * qty)`, clamped at
100, applied from create() as well as write(). They are immutable.

The v15 implementation this suite runs against is
`mmg_automated_action/models/sale_order_line.py`:

    def update_discount_from_x_discount(self):
        for rec in self:
            if rec.x_discount:
                rec.discount = rec.x_discount * 100 / rec.price_unit \\
                    if rec.price_unit else 0

    @api.onchange('x_discount', 'product_uom_qty', 'price_unit') -> calls it
    def write(self, values): super().write(values); if x_discount /
        product_uom_qty / price_unit in values -> calls it

so on v15: the denominator is the UNIT PRICE ONLY (quantity ignored), there
is no create() hook, there is no 100 % clamp, and a zero price_unit
short-circuits to 0. Every assertion below that depends on one of those four
differences is therefore an EXPECTED v15 FAIL describing the v19 target — it
stays failing and classifies as FIXED when v19 passes. (The base_automation
records "[PZE] Calc Dollar Discount" / "[PZE] Inv Value" are INACTIVE in
production precisely because this module replaced them with the code above;
that is the correct configuration and is not "fixed" here.)

Second v15-only consideration, and the reason every write goes through
`attempt()`: `x_discount` is a Studio field on v15, and the MMG code base
declares the *product-level* `x_discount` as `fields.Char`
(`mmg_stock/models/product.py`). If the sale.order.line Studio field is a
Char too, `rec.x_discount * 100 / rec.price_unit` performs string
arithmetic and the server raises instead of storing a percentage. Each test
therefore logs the declared field type up front and records the server's
refusal *as the actual value* of the workbook assertion, so the run produces
evidence of the real v15 baseline instead of an unrecorded traceback.
"""
from framework.registry import test_case
from tests.fg03.common import (Checks, QA_PARTNER_SQL, add_line,
                               attempt, avatax_confirm_probe, company_id,
                               get_auto_invoice_flag, line_state, make_order,
                               make_partner, make_product, order_lines,
                               reconcile, restore_auto_invoice_flag, rounded,
                               set_auto_invoice_flag, sweep_fg03, trace,
                               x_discount_type)


@test_case(
    id="TEST-FG03-SAL-006",
    name="Dollar discount converts to percentage (onchange)",
    workflow="FG-03", workflow_name="Sales & Pricing",
    module="mmg_automated_action", priority="P0", kind="API", order=300,
    description="Onchange path (sale.order.line.new() + "
                "_onchange_x_discount() on an unsaved virtual record) cannot "
                "be driven over RPC — blocked stub after the field-presence "
                "probe. The create/write path is TEST-FG03-SAL-007.",
    traceability=trace("TC-SAL-006"))
def test_sal_006(ctx):
    """Expected v15 outcome: BLOCKED — and it would be BLOCKED on v19 too.

    The TC's essence is an unsaved virtual record: `sale.order.line.new({...})`
    followed by `_onchange_x_discount()`, asserted on that virtual record.
    `/web/dataset/call_kw` has no representation for it — the web client's own
    onchange RPC returns a value dict, not a record, and cannot host `new()` —
    so the case runs as an Odoo TransactionCase only. The stub still probes and
    logs what the target database declares for `sale.order.line.x_discount`,
    which is the part that carries information for the v19 comparison. Had the
    onchange been reachable on v15 it would have produced discount 20.00 (unit
    price only) against the workbook's 10.00; that difference is covered
    through the create/write path by TEST-FG03-SAL-007.
    """
    rpc = ctx.adapter.rpc
    with ctx.step("Precondition probe: sale.order.line.x_discount exists"):
        declared = x_discount_type(rpc)
        ctx.log(f"sale.order.line.x_discount declared type: {declared} "
                "(v19 target: float, coded in mmg_sale)")
        ctx.check("sale.order.line.x_discount exists", True,
                  declared != "absent")
    with ctx.step("Onchange path requires an in-process ORM"):
        ctx.blocked(
            "onchange/new() requires in-process ORM — the TC's essence is "
            "sale.order.line.new({...}) followed by _onchange_x_discount() "
            "on an UNSAVED virtual record, which has no representation over "
            "/web/dataset/call_kw (the web client's own onchange RPC returns "
            "a value dict, not the virtual record the workbook asserts on, "
            "and cannot host new()). Runs as an Odoo TransactionCase only; "
            "the same shared conversion helper is covered through the "
            f"create/write path by TEST-FG03-SAL-007. Declared field type on "
            f"this database: {declared}.")


@test_case(
    id="TEST-FG03-SAL-007",
    name="Dollar discount converts on write (not just onchange)",
    workflow="FG-03", workflow_name="Sales & Pricing",
    module="mmg_automated_action", priority="P0", kind="API", order=301,
    description="create/write conversion per the v19 per-line-total formula: "
                "10.00 on create, 5.00 after qty 4, 10.00 after price 250, "
                "and a line without x_discount keeps its manual discount. "
                "v15 has no create hook and divides by price_unit only — "
                "expected v15 FAILs.",
    traceability=trace("TC-SAL-007"))
def test_sal_007(ctx):
    """Expected v15 outcome: FAIL — the documented v15 discount baseline.

    Confirmed by run RUN-937DC32E, which recorded exactly this:
    `{'discount after create': expected 10.0 actual 0.0, 'discount after
    qty -> 4': ...}`. Three of the workbook's expectations describe the v19
    formula and each fails for its own verified reason:
      * after create -> expected 10.00, v15 gives 0.00: there is NO create hook
        at all in v15 (the conversion runs from write() and the onchange only);
      * after qty -> 4 -> expected 5.00, v15 gives 20.00: quantity is not in
        the v15 denominator (`x_discount * 100 / price_unit`);
      * after price -> 250 -> expected 10.00, v15 gives 40.00: same reason.
    What passes on v15: the guard line without x_discount keeps its manual
    7.00 discount, x_discount itself is preserved by the conversion, and the
    identical rewrite is stable (no nested-write recursion). All observations
    are collected and asserted once, so the FAIL carries the whole picture
    rather than the first mismatch.
    """
    rpc = ctx.adapter.rpc
    checks = Checks(ctx)
    with ctx.step("Sweep previous FG-03 fixtures (fresh namespace)"):
        sweep_fg03(rpc, ctx.log)
        ctx.log(f"sale.order.line.x_discount declared type: "
                f"{x_discount_type(rpc)}")
    with ctx.step("Fixture: customer, product at 500.00, empty draft order"):
        partner = make_partner(rpc, "Discount Customer")
        product = make_product(rpc, "Artwork 500", 500.0)
        order = make_order(rpc, partner)
    try:
        with ctx.step("Create a saved line qty 2 x 500.00 with "
                      "x_discount = 100 (import/API path, no onchange)"):
            ok, res = attempt(add_line, rpc, order, product, qty=2.0,
                              price=500.0, x_discount=100.0)
            if not ok:
                # a Char-typed Studio x_discount makes the conversion raise;
                # the refusal is the finding and must not abort the test
                checks.record("discount after create (100 / (2 x 500) x 100)",
                              10.0, f"line create refused: {res}")
                ctx.blocked(
                    "sale.order.line could not be created with x_discount on "
                    f"this database ({res}) — every later step of this TC "
                    "writes to that same line, so there is nothing left to "
                    "observe. Check the declared type of "
                    "sale.order.line.x_discount (logged above): the v19 target "
                    "is a coded Float in mmg_sale.")
            line = res
            got = line_state(rpc, line)
            ctx.log(f"line {line} after create: {got}")
            checks.record("discount after create (100 / (2 x 500) x 100)",
                          10.0, rounded(got["discount"]))
        with ctx.step("Change quantity to 4 — discount reconverts to 5.00"):
            ok, err = attempt(rpc.write, "sale.order.line", [line],
                              {"product_uom_qty": 4.0})
            actual = rounded(line_state(rpc, line)["discount"]) if ok else err
            checks.record("discount after qty -> 4 (100 / (4 x 500) x 100)",
                          5.0, actual)
        with ctx.step("Change unit price to 250 — discount reconverts to "
                      "10.00"):
            ok, err = attempt(rpc.write, "sale.order.line", [line],
                              {"price_unit": 250.0})
            actual = rounded(line_state(rpc, line)["discount"]) if ok else err
            checks.record("discount after price -> 250 "
                          "(100 / (4 x 250) x 100)", 10.0, actual)
        with ctx.step("Guard: a line WITHOUT x_discount keeps its manual "
                      "discount across a price write"):
            control = add_line(rpc, order, product, qty=1.0, price=500.0,
                               discount=7.0)
            ok, err = attempt(rpc.write, "sale.order.line", [control],
                              {"price_unit": 300.0})
            got = line_state(rpc, control)
            checks.record("control line x_discount stays falsy", False,
                          bool(got["x_discount"]))
            checks.record("manual discount untouched by the hook", 7.0,
                          rounded(got["discount"]) if ok else err)
        with ctx.step("Idempotence: rewriting the same price changes nothing "
                      "(no nested-write recursion)"):
            ok, err = attempt(rpc.write, "sale.order.line", [line],
                              {"price_unit": 250.0})
            got = line_state(rpc, line)
            checks.record("discount stable on an identical rewrite", 10.0,
                          rounded(got["discount"]) if ok else err)
            checks.record("x_discount preserved by the conversion", 100.0,
                          got["x_discount"])
        with ctx.step("Assert the workbook's expected results"):
            checks.assert_all()
    finally:
        with ctx.step("Cleanup fixtures"):
            sweep_fg03(rpc, ctx.log)


@test_case(
    id="TEST-FG03-SAL-008",
    name="Dollar discount on a bulk line update does not recurse",
    workflow="FG-03", workflow_name="Sales & Pricing",
    module="mmg_automated_action", priority="P1", kind="API", order=302,
    description="500-line timed bulk write compared with a v15 wall-clock "
                "baseline, with a server-log watch for RecursionError and "
                "nested UPDATE cascades — performance harness, blocked stub.",
    traceability=trace("TC-SAL-008"))
def test_sal_008(ctx):
    """Expected v15 outcome: BLOCKED — a performance harness, per the workbook.

    The workbook classifies TC-SAL-008 MANUAL / MANUAL_ONLY: its verdict is a
    wall-clock comparison (v19 <= v15 x 1.2) around one timed 500-line bulk
    write plus a live server-log watch for RecursionError / MemoryError /
    nested `UPDATE sale_order_line` cascades. This runner has neither a timing
    threshold nor log access, and a 500-line fixture write burst on the shared
    production clone is not a safe automated step. The correctness half of the
    same code path (idempotent rewrite, no recursion) is covered at line level
    by TEST-FG03-SAL-007's final step.
    """
    rpc = ctx.adapter.rpc
    with ctx.step("Precondition probe: sale.order.line.x_discount exists"):
        declared = x_discount_type(rpc)
        ctx.log(f"sale.order.line.x_discount declared type: {declared}")
        ctx.check("sale.order.line.x_discount exists", True,
                  declared != "absent")
    with ctx.step("Timed 500-line baseline requires the manual harness"):
        ctx.blocked(
            "performance harness — manual baseline: the TC's verdict is a "
            "wall-clock comparison (v19 <= v15 x 1.2) around one 500-line "
            "bulk write, plus a live server-log watch for RecursionError / "
            "MemoryError / nested UPDATE sale_order_line cascades. Neither "
            "the timing threshold nor the log watch is available to this "
            "runner, and a 500-line fixture write on the shared production "
            "clone is not a safe automated step.")


@test_case(
    id="TEST-FG03-SAL-019",
    name="Order with a 100%-discounted line",
    workflow="FG-03", workflow_name="Sales & Pricing",
    module="mmg_automated_action", priority="P2", kind="API", order=303,
    description="Line total exactly discounted -> 100.00 with subtotal 0.00; "
                "over-discount clamps at 100.00; zero price short-circuits "
                "to 0.0 without ZeroDivisionError; the order still confirms. "
                "The lines are created with x_discount as the workbook writes "
                "them and v15 has no create hook (nor a clamp, nor qty in the "
                "denominator) — expected v15 FAILs.",
    traceability=trace("TC-SAL-019"))
def test_sal_019(ctx):
    """Expected v15 outcome: FAIL — on the clamp/percentage assertions.

    All three lines are created with `x_discount` in the create vals, exactly
    as the workbook writes them, and v15 has no create hook, so `discount`
    stays 0.00 on each: expected 100.00 (exactly-discounted line), 0.00
    price_subtotal and the 100.00 clamp are all recorded as mismatches — the
    v19 target formula plus its `min(..., 100.0)` guard, which v15 does not
    have either. What passes on v15: the zero-price line yields 0.0 with no
    ZeroDivisionError, and the order still confirms with these edge-case lines
    present.

    The company's auto-invoice flag is snapshotted and switched OFF for the
    confirm step (so this TC cannot depend on
    mmg_sale_auto_create_invoice's behaviour) and restored in the `finally`
    step. Run RUN-937DC32E lost this test to "web session authentication
    failed: connection refused" after the server was killed mid-run; that is an
    ENVIRONMENT result by construction now — `attempt()` re-raises transport
    failures instead of recording them as assertion values.
    """
    rpc = ctx.adapter.rpc
    checks = Checks(ctx)
    with ctx.step("Sweep previous FG-03 fixtures (fresh namespace)"):
        sweep_fg03(rpc, ctx.log)
        ctx.log(f"sale.order.line.x_discount declared type: "
                f"{x_discount_type(rpc)}")
    with ctx.step("Precondition: AvaTax does not hijack action_confirm"):
        avatax_confirm_probe(ctx, rpc)
    with ctx.step("Fixture: customer, product at 500.00, draft order; "
                  "auto-invoice flag off for the confirm step"):
        cid = company_id(rpc)
        flag = get_auto_invoice_flag(rpc, cid)
        partner = make_partner(rpc, "Clamp Customer")
        product = make_product(rpc, "Artwork 500", 500.0)
        order = make_order(rpc, partner)
    try:
        set_auto_invoice_flag(rpc, cid, False)
        with ctx.step("Line qty 2 x 500 with x_discount = 1000 (exactly the "
                      "line total) -> discount 100.00, subtotal 0.00"):
            line1 = add_line(rpc, order, product, qty=2.0, price=500.0,
                             x_discount=1000.0)
            got = line_state(rpc, line1, ["discount", "price_subtotal",
                                          "x_discount"])
            ctx.log(f"line {line1}: {got}")
            checks.record("100%-line discount", 100.0,
                          rounded(got["discount"]))
            checks.record("100%-line price_subtotal", 0.0,
                          rounded(got["price_subtotal"]))
        with ctx.step("Over-discount: x_discount = 5000 on the same line "
                      "total clamps at exactly 100.00"):
            line2 = add_line(rpc, order, product, qty=2.0, price=500.0,
                             x_discount=5000.0)
            got = line_state(rpc, line2)
            ctx.log(f"line {line2}: {got}")
            checks.record("over-discount clamped at 100.00", 100.0,
                          rounded(got["discount"]))
        with ctx.step("Zero-price line with x_discount = 50 -> no "
                      "ZeroDivisionError, discount 0.0"):
            ok, res = attempt(add_line, rpc, order, product, qty=1.0,
                              price=0.0, x_discount=50.0)
            if ok:
                got = line_state(rpc, res)
                ctx.log(f"line {res}: {got}")
                checks.record("zero-price line discount", 0.0,
                              rounded(got["discount"]))
            else:
                checks.record("zero-price line discount", 0.0,
                              f"line create refused: {res}")
        with ctx.step("The order confirms normally with the edge-case lines "
                      "present"):
            ok, res = attempt(rpc.call, "sale.order", "action_confirm",
                              [order])
            state = rpc.read("sale.order", [order], ["state"])[0]["state"]
            if not ok:
                ctx.log(f"action_confirm refused: {res}")
            checks.record("state after confirm", "sale", state)
        with ctx.step("Assert the workbook's expected results"):
            checks.assert_all()
    finally:
        with ctx.step("Cleanup fixtures and restore the auto-invoice flag"):
            restore_auto_invoice_flag(ctx, rpc, cid, flag)
            sweep_fg03(rpc, ctx.log)


@test_case(
    id="TEST-FG03-SAL-020",
    name="Order line with qty 0",
    workflow="FG-03", workflow_name="Sales & Pricing",
    module="mmg_automated_action", priority="P2", kind="API", order=304,
    description="qty 0 gives discount 0.0 (zero line total, no division by "
                "zero) and the conversion resumes at 5.00 once qty becomes "
                "2. v15 ignores qty in the denominator — expected v15 FAIL "
                "on the second half.",
    traceability=trace("TC-SAL-020"))
def test_sal_020(ctx):
    """Expected v15 outcome: FAIL — on the second half only.

    Step 1 (create at qty 0, price 500, x_discount 50) gives discount 0.0 as
    the workbook expects, though on v15 that PASS is incidental: there is no
    create hook, so nothing ran. Step 2 writes qty 2, the write hook fires and
    v15 computes 50 * 100 / 500 = 10.00 where the workbook expects 5.00,
    because quantity is not in the v15 denominator. No order is confirmed here,
    so no company flag is touched.

    Like TEST-FG03-SAL-019 this test was lost to the server being killed
    mid-run in RUN-937DC32E; a transport failure now raises ServerUnreachable
    (-> ENVIRONMENT) instead of being recorded as an assertion value.
    """
    rpc = ctx.adapter.rpc
    checks = Checks(ctx)
    with ctx.step("Sweep previous FG-03 fixtures (fresh namespace)"):
        sweep_fg03(rpc, ctx.log)
        ctx.log(f"sale.order.line.x_discount declared type: "
                f"{x_discount_type(rpc)}")
    with ctx.step("Fixture: customer, product at 500.00, draft order"):
        partner = make_partner(rpc, "Qty0 Customer")
        product = make_product(rpc, "Artwork 500", 500.0)
        order = make_order(rpc, partner)
    try:
        with ctx.step("Create a line qty 0, price 500, x_discount 50 — no "
                      "exception, discount 0.0"):
            ok, res = attempt(add_line, rpc, order, product, qty=0.0,
                              price=500.0, x_discount=50.0)
            line = res if ok else None
            if ok:
                got = line_state(rpc, line)
                ctx.log(f"line {line}: {got}")
                checks.record("discount on a zero line total", 0.0,
                              rounded(got["discount"]))
            else:
                checks.record("discount on a zero line total", 0.0,
                              f"line create refused: {res}")
        with ctx.step("Write qty 2 — the conversion resumes: "
                      "50 / (2 x 500) x 100 = 5.00"):
            if line is None:
                checks.record("discount after qty -> 2", 5.0,
                              "line was never created")
            else:
                ok, err = attempt(rpc.write, "sale.order.line", [line],
                                  {"product_uom_qty": 2.0})
                actual = (rounded(line_state(rpc, line)["discount"])
                          if ok else err)
                checks.record("discount after qty -> 2", 5.0, actual)
        with ctx.step("Assert the workbook's expected results"):
            checks.assert_all()
    finally:
        with ctx.step("Cleanup fixtures"):
            sweep_fg03(rpc, ctx.log)


@test_case(
    id="TEST-FG03-STU-004",
    name="sale.order.line.x_discount (Discount $) preserved and still "
         "drives discount",
    workflow="FG-03", workflow_name="Sales & Pricing",
    module="(Odoo Studio layer)", priority="P0", kind="HYBRID", order=305,
    description="v15 data baseline (populated x_discount rows + 20 ordered "
                "samples) persisted for the v19 diff, then the v19 target "
                "state: coded Float field, exactly one ir.model.fields row "
                "with state 'base', and the write path yielding 10.00 on a "
                "qty 2 x 500 line. On v15 the field is a Studio (manual) "
                "field and the formula ignores qty — expected FAILs.",
    traceability=trace("TC-STU-004"))
def test_stu_004(ctx):
    """Expected v15 outcome: FAIL — on the v19-target halves; the data baseline
    is captured first so it survives the failure.

    The workbook asserts the migrated end state: `x_discount` a CODED Float
    (mmg_sale, FG-03 decision #3), exactly one `ir.model.fields` row in state
    'base' after the post-migrate script deletes the Studio shadow, and
    discount 10.00 from a write on a qty 2 x 500 line. On the v15 clone the
    field is a Studio (manual) field, so the state assertion records 'manual',
    and the write path yields 20.00 (unit price only) — both are the documented
    baseline and classify as FIXED when v19 passes. The declared *type* may well
    be 'float' on v15 too; that assertion is expected to pass and is kept
    because the v19 requirement is about the type AND the ownership.

    Ordering is deliberate: `reconcile()` runs BEFORE the failing assertions,
    because the v15 -> v19 data comparison this TC exists for would otherwise
    never get its baseline. BLOCKED instead when the environment has no
    read-only PostgreSQL configuration (the workbook's step 3 is SQL).
    """
    rpc = ctx.adapter.rpc
    checks = Checks(ctx)

    def capture(inner_ctx):
        if not inner_ctx.sql.column_exists("sale_order_line", "x_discount"):
            # recorded, not raised: the absence of the column IS the finding
            # the v19 comparison needs (the Upgrade Service must preserve it)
            return {"populated_x_discount_rows":
                    "sale_order_line.x_discount column absent"}
        # QA fixture lines are excluded so reruns cannot drift the baseline.
        # "populated" is expressed as a text regex rather than a numeric
        # comparison because the column is a Studio field: it is varchar on
        # the v15 clone and a Float column in the v19 port, and '0'/'0.00'
        # must count as empty on both.
        populated = ("l.x_discount IS NOT NULL AND l.x_discount::text ~ "
                     "'[1-9]'")
        out = {"populated_x_discount_rows": inner_ctx.sql.one(
            "SELECT count(*) FROM sale_order_line l "
            "JOIN sale_order o ON o.id = l.order_id "
            f"WHERE {populated} "
            f"AND o.partner_id NOT IN {QA_PARTNER_SQL}")}
        rows = inner_ctx.sql.rows(
            "SELECT l.id, l.x_discount, l.discount, l.price_unit, "
            "l.product_uom_qty FROM sale_order_line l "
            "JOIN sale_order o ON o.id = l.order_id "
            f"WHERE {populated} "
            f"AND o.partner_id NOT IN {QA_PARTNER_SQL} "
            "ORDER BY l.id LIMIT 20")
        for row in rows:
            out[f"sample_line_{row[0]}"] = (
                f"x_discount={row[1]}|discount={row[2]}|"
                f"price_unit={row[3]}|qty={row[4]}")
        return out

    with ctx.step("Sweep previous FG-03 fixtures (fresh namespace)"):
        sweep_fg03(rpc, ctx.log)
    # The data baseline is captured and persisted FIRST: the registry
    # assertions below encode the v19 target state and fail on v15, and a
    # failing assertion ends the test, which would leave the v15 -> v19
    # comparison this TC exists for without its baseline.
    reconcile(ctx, "TC-STU-004", capture)

    with ctx.step("Registry check: x_discount is a coded Float field"):
        info = rpc.call("sale.order.line", "fields_get", ["x_discount"],
                        attributes=["type", "string", "store"])
        ctx.log(f"fields_get(x_discount) = {info}")
        # recorded, never raised: the absence of the field IS the finding this
        # TC exists to catch (the Upgrade Service must preserve the column),
        # and raising here would drop every later observation
        checks.record("x_discount is declared on sale.order.line", True,
                      "x_discount" in info)
        checks.record("x_discount field type", "float",
                      (info.get("x_discount") or {}).get("type", "absent"))
    with ctx.step("ir.model.fields: exactly one declaration, state 'base' "
                  "(no leftover Studio 'manual' shadow row)"):
        rows = rpc.search_read("ir.model.fields",
                               [("model", "=", "sale.order.line"),
                                ("name", "=", "x_discount")],
                               ["state", "ttype"])
        ctx.log(f"ir.model.fields rows: {rows}")
        checks.record("ir.model.fields declarations", 1, len(rows))
        checks.record("ir.model.fields state",
                      "base", rows[0]["state"] if rows else "no row")
    try:
        with ctx.step("Behaviour: write x_discount = 100 on a qty 2 x 500 "
                      "line -> discount 10.00"):
            partner = make_partner(rpc, "Studio Customer")
            product = make_product(rpc, "Artwork 500", 500.0)
            order = make_order(rpc, partner, [(product, 2.0, 500.0)])
            line = order_lines(rpc, order, ["id"])[0]["id"]
            ok, err = attempt(rpc.write, "sale.order.line", [line],
                              {"x_discount": 100.0})
            got = line_state(rpc, line)
            ctx.log(f"line {line} after write: {got}")
            checks.record("discount driven by the write path", 10.0,
                          rounded(got["discount"]) if ok else err)
        with ctx.step("Persistence: both halves survive a re-read"):
            got = line_state(rpc, line)
            checks.record("x_discount persisted", 100.0, got["x_discount"])
            checks.record("discount persisted", 10.0,
                          rounded(got["discount"]))
        with ctx.step("Assert the workbook's expected results"):
            checks.assert_all()
    finally:
        with ctx.step("Cleanup fixtures"):
            sweep_fg03(rpc, ctx.log)
