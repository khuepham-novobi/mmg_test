"""FG-03 — auto-create invoice on confirm (mmg_sale_auto_create_invoice):
TC-SAL-013, TC-SAL-014, TC-SAL-015, TC-SAL-021.

The company-scoped `auto_create_invoice_after_confirming_so` flag is
snapshotted before the first write and restored in a `finally` step by every
test here.

Verified v15 implementation (`mmg_sale_auto_create_invoice/models/
sale_order.py`):

    def action_confirm(self):
        res = super().action_confirm()
        need_open_invoice = False
        for rec in self:
            if rec.company_id.auto_create_invoice_after_confirming_so:
                need_open_invoice = True
                self._create_invoices()          # <- the whole recordset
        if need_open_invoice:
            return self.action_view_invoice()
        return res

so for a single order the flow is correct (one invoice, redirect action),
while a batch confirm calls `self._create_invoices()` once per enabled order.
The expected v15 outcome of TC-SAL-014 is therefore a REFUSED batch confirm,
not the "N invoices per order" the workbook's source note hypothesised — but
the exact mechanism is [UNVERIFIED] and deliberately not asserted, because two
independent v15 overrides can refuse first and only the run can say which one
does:

* this module's second loop pass calls `self._create_invoices()` again on the
  whole recordset, where every line is already invoiced, and
  `sale._create_invoices()` raises `_nothing_to_invoice_error()`;
* `account_avatax_sale_oca.sale.order.action_confirm()` reads
  `self.company_id` (a singleton field read) on the multi-record recordset,
  which raises "Expected singleton" before any invoice is created.

Either way the batch confirm fails and the orders stay draft, which is a FAIL
against the workbook's (v19) expectation — exactly what BC-001 fixes. The
server's own message is recorded as the actual value so triage sees the real
mechanism instead of this docstring's guess.

TC-SAL-021 likewise records v15 core behaviour: `sale.order.action_cancel`
returns the `sale.order.cancel` wizard when a draft invoice exists, and the
wizard's confirmation routes into `_action_cancel()`, which *cancels* the
draft invoices (`inv.button_cancel()`) before setting the order to cancel.
The workbook requires the auto-created invoice to stay 'draft', so that
assertion is an expected v15 FAIL. The multi-order variant additionally hits
`{'default_order_id': self.id}` on a multi-record recordset — `fields.Id`
raises "Expected singleton" — which is exactly the "no traceback"
expectation the workbook states.
"""
from framework.registry import test_case
from tests.fg03.common import (AUTO_FLAG, Checks, QA_PARTNER_SQL, attempt,
                               avatax_confirm_probe, cancel_order_flow,
                               company_id, get_auto_invoice_flag, make_order,
                               make_partner, make_product, require_field,
                               restore_auto_invoice_flag,
                               set_auto_invoice_flag, sql_rows_optional,
                               sweep_fg03, trace)


@test_case(
    id="TEST-FG03-SAL-013",
    name="Auto-create invoice on confirm, single order",
    workflow="FG-03", workflow_name="Sales & Pricing",
    module="mmg_sale_auto_create_invoice", priority="P0", kind="API",
    order=311,
    description="With the setting on, confirming one order creates exactly "
                "one draft invoice and action_confirm returns the "
                "account.move window action the UI navigates to.",
    traceability=trace("TC-SAL-013"))
def test_sal_013(ctx):
    """Expected v15 outcome: PASS.

    The single-order path of `mmg_sale_auto_create_invoice` is correct on v15:
    the loop runs once, `_create_invoices()` produces exactly one draft invoice
    and `action_view_invoice()` returns an `account.move` window action. The
    company flag is snapshotted before it is switched on and restored in the
    `finally` step, so the clone's configuration is unchanged afterwards.
    """
    rpc = ctx.adapter.rpc
    checks = Checks(ctx)
    with ctx.step("Sweep previous FG-03 fixtures (fresh namespace)"):
        sweep_fg03(rpc, ctx.log)
    with ctx.step("Preconditions: the company flag exists + AvaTax does not "
                  "hijack action_confirm"):
        require_field(ctx, rpc, "res.company", AUTO_FLAG,
                      "mmg_sale_auto_create_invoice",
                      "the auto-invoice-on-confirm behaviour of this TC")
        avatax_confirm_probe(ctx, rpc)
    with ctx.step("Fixture: setting ON, one draft invoiceable order"):
        cid = company_id(rpc)
        flag = get_auto_invoice_flag(rpc, cid)
        partner = make_partner(rpc, "AutoInv Customer")
        product = make_product(rpc, "Artwork 500", 500.0)
    try:
        set_auto_invoice_flag(rpc, cid, True)
        order = make_order(rpc, partner, [(product, 1.0, 500.0)])
        with ctx.step("Confirm the order"):
            ok, action = attempt(rpc.call, "sale.order", "action_confirm",
                                 [order])
            ctx.log(f"action_confirm returned: {action!r}")
        with ctx.step("The order is confirmed"):
            got = rpc.read("sale.order", [order],
                           ["state", "invoice_ids"])[0]
            checks.record("order state", "sale", got["state"])
        with ctx.step("Exactly one automatically created draft invoice"):
            checks.record("number of invoices on the order", 1,
                          len(got["invoice_ids"]))
            states = [r["state"] for r in rpc.read(
                "account.move", got["invoice_ids"], ["state"])] \
                if got["invoice_ids"] else []
            checks.record("invoice states", ["draft"], states)
        with ctx.step("action_confirm returns the invoice redirect "
                      "(res_model account.move)"):
            checks.record("confirm returns a window action", True,
                          isinstance(action, dict))
            checks.record("redirect res_model", "account.move",
                          (action or {}).get("res_model")
                          if isinstance(action, dict) else repr(action))
        with ctx.step("Assert the workbook's expected results"):
            checks.assert_all()
    finally:
        with ctx.step("Cleanup fixtures and restore the setting"):
            restore_auto_invoice_flag(ctx, rpc, cid, flag)
            sweep_fg03(rpc, ctx.log)


@test_case(
    id="TEST-FG03-SAL-014",
    name="Auto-create invoice on a MULTI-order confirm - suspected defect",
    workflow="FG-03", workflow_name="Sales & Pricing",
    module="mmg_sale_auto_create_invoice", priority="P0", kind="HYBRID",
    order=312,
    description="Batch confirm of 3 orders for 3 different customers must "
                "create exactly one invoice per order, and 3 orders for one "
                "customer exactly one merged invoice. On v15 the batch confirm "
                "is refused (the module calls _create_invoices() on the whole "
                "recordset once per enabled order; the server's own message is "
                "recorded, the mechanism is not asserted) - expected FAIL. "
                "Includes the read-only historical duplicate hunt.",
    traceability=trace("TC-SAL-014"))
def test_sal_014(ctx):
    """Expected v15 outcome: FAIL — this is the suspected defect, confirmed.

    The workbook expects one invoice per order on a batch confirm (3 distinct
    customers -> 3 invoices; 3 orders for one customer -> 1 merged invoice).
    v15's `action_confirm` calls `self._create_invoices()` on the WHOLE
    recordset once per enabled order, so the batch confirm is refused and the
    orders stay draft; the module docstring lists the two candidate mechanisms
    ([UNVERIFIED] which one fires first) and the server's own message is
    recorded as the actual value. FG-03 BC-001 is the v19 fix, so this FAIL
    classifies as FIXED when v19 passes.

    The read-only historical duplicate hunt on live data runs first and only
    logs (no verdict), so a missing PostgreSQL configuration degrades to a log
    line instead of blocking the functional half.
    """
    rpc = ctx.adapter.rpc
    checks = Checks(ctx)
    with ctx.step("Sweep previous FG-03 fixtures (fresh namespace)"):
        sweep_fg03(rpc, ctx.log)
    with ctx.step("Preconditions: the company flag exists + AvaTax does not "
                  "hijack action_confirm"):
        require_field(ctx, rpc, "res.company", AUTO_FLAG,
                      "mmg_sale_auto_create_invoice",
                      "the batch-confirm behaviour of this TC")
        avatax_confirm_probe(ctx, rpc)
    with ctx.step("Historical duplicate hunt on live data (read-only "
                  "baseline for the pre-go-live reconciliation)"):
        rows = sql_rows_optional(
            ctx,
            "SELECT o.id, o.name, count(DISTINCT ml.move_id) AS invoices "
            "FROM sale_order o "
            "JOIN sale_order_line l ON l.order_id = o.id "
            "JOIN sale_order_line_invoice_rel r ON r.order_line_id = l.id "
            "JOIN account_move_line ml ON ml.id = r.invoice_line_id "
            "JOIN account_move m ON m.id = ml.move_id "
            "WHERE m.move_type = 'out_invoice' AND m.state <> 'cancel' "
            f"AND o.partner_id NOT IN {QA_PARTNER_SQL} "
            "GROUP BY o.id, o.name HAVING count(DISTINCT ml.move_id) > 1 "
            "ORDER BY 3 DESC, 1 LIMIT 50",
            "historical duplicate hunt")
        if rows is not None:
            ctx.log(f"orders carrying more than one non-cancelled customer "
                    f"invoice: {len(rows)} found (top 50 listed) -> {rows}")
    with ctx.step("Fixture: setting ON, 3 draft orders for 3 DIFFERENT "
                  "customers (distinct partners prevent invoice grouping)"):
        cid = company_id(rpc)
        flag = get_auto_invoice_flag(rpc, cid)
        product = make_product(rpc, "Artwork 500", 500.0)
        partners = [make_partner(rpc, f"Multi Customer {suffix}")
                    for suffix in ("A", "B", "C")]
    try:
        set_auto_invoice_flag(rpc, cid, True)
        orders = [make_order(rpc, p, [(product, 1.0, 500.0)])
                  for p in partners]
        with ctx.step("Batch confirm (list view Action > Confirm "
                      "equivalent)"):
            ok, res = attempt(rpc.call, "sale.order", "action_confirm",
                              orders)
            ctx.log(f"batch action_confirm ok={ok} result={res!r}")
            checks.record("batch confirm completes without error", None,
                          None if ok else res)
        with ctx.step("Every order confirmed, exactly one invoice each, "
                      "three in total"):
            rows = rpc.read("sale.order", orders, ["state", "invoice_ids"])
            by_id = {r["id"]: r for r in rows}
            checks.record("order states", ["sale"] * 3,
                          [by_id[o]["state"] for o in orders])
            checks.record("invoices per order", [1, 1, 1],
                          [len(by_id[o]["invoice_ids"]) for o in orders])
            distinct = {i for r in rows for i in r["invoice_ids"]}
            checks.record("distinct invoices in total", 3, len(distinct))
        with ctx.step("Same-partner variant: 3 orders for ONE customer "
                      "batch-confirm into exactly 1 merged invoice"):
            same = [make_order(rpc, partners[0], [(product, 1.0, 500.0)])
                    for _ in range(3)]
            ok, res = attempt(rpc.call, "sale.order", "action_confirm", same)
            ctx.log(f"same-partner batch confirm ok={ok} result={res!r}")
            rows = rpc.read("sale.order", same, ["invoice_ids"])
            merged = sorted({i for r in rows for i in r["invoice_ids"]})
            checks.record("merged invoices for one customer", 1, len(merged))
            checks.record("every same-partner order shares that invoice",
                          [merged] * 3,
                          [sorted(r["invoice_ids"]) for r in rows])
        with ctx.step("Assert the workbook's expected results"):
            checks.assert_all()
    finally:
        with ctx.step("Cleanup fixtures and restore the setting"):
            restore_auto_invoice_flag(ctx, rpc, cid, flag)
            sweep_fg03(rpc, ctx.log)


@test_case(
    id="TEST-FG03-SAL-015",
    name="Auto-create invoice disabled - no invoice on confirm",
    workflow="FG-03", workflow_name="Sales & Pricing",
    module="mmg_sale_auto_create_invoice", priority="P1", kind="API",
    order=313,
    description="With the setting off: standard confirmation, no invoice, "
                "invoice_status 'to invoice', and no account.move redirect "
                "(the plain super() result).",
    traceability=trace("TC-SAL-015"))
def test_sal_015(ctx):
    """Expected v15 outcome: PASS.

    With the flag off, `need_open_invoice` stays False and the override returns
    the plain `super()` result: standard confirmation, no invoice,
    invoice_status 'to invoice', no `account.move` redirect. The flag is
    snapshotted and restored even though the test only switches it off, because
    the clone's own value may be on.
    """
    rpc = ctx.adapter.rpc
    checks = Checks(ctx)
    with ctx.step("Sweep previous FG-03 fixtures (fresh namespace)"):
        sweep_fg03(rpc, ctx.log)
    with ctx.step("Preconditions: the company flag exists + AvaTax does not "
                  "hijack action_confirm"):
        require_field(ctx, rpc, "res.company", AUTO_FLAG,
                      "mmg_sale_auto_create_invoice",
                      "the setting-off half of this TC")
        avatax_confirm_probe(ctx, rpc)
    with ctx.step("Fixture: setting OFF, one draft invoiceable order"):
        cid = company_id(rpc)
        flag = get_auto_invoice_flag(rpc, cid)
        partner = make_partner(rpc, "NoAutoInv Customer")
        product = make_product(rpc, "Artwork 500", 500.0)
    try:
        set_auto_invoice_flag(rpc, cid, False)
        order = make_order(rpc, partner, [(product, 1.0, 500.0)])
        with ctx.step("Confirm the order"):
            ok, res = attempt(rpc.call, "sale.order", "action_confirm",
                              [order])
            ctx.log(f"action_confirm returned: {res!r}")
        with ctx.step("Standard flow: confirmed, no invoice, to invoice"):
            got = rpc.read("sale.order", [order],
                           ["state", "invoice_ids", "invoice_status"])[0]
            checks.record("order state", "sale", got["state"])
            checks.record("invoices created on confirm", [],
                          got["invoice_ids"])
            checks.record("invoice_status", "to invoice",
                          got["invoice_status"])
        with ctx.step("No account.move redirect is returned"):
            redirected = isinstance(res, dict) and \
                res.get("res_model") == "account.move"
            checks.record("confirm returns an invoice redirect", False,
                          redirected)
        with ctx.step("Assert the workbook's expected results"):
            checks.assert_all()
    finally:
        with ctx.step("Cleanup fixtures and restore the setting"):
            restore_auto_invoice_flag(ctx, rpc, cid, flag)
            sweep_fg03(rpc, ctx.log)


@test_case(
    id="TEST-FG03-SAL-021",
    name="Cancel a confirmed order that has an auto-created invoice",
    workflow="FG-03", workflow_name="Sales & Pricing",
    module="mmg_sale_auto_create_invoice", priority="P1", kind="API",
    order=314,
    description="Cancel through the sale.order.cancel confirmation wizard: "
                "the order reaches 'cancel' and the auto-created invoice "
                "must still exist in state 'draft' (v15 _action_cancel "
                "button-cancels it - expected FAIL, recorded verbatim). The "
                "multi-order cancel must complete without traceback.",
    traceability=trace("TC-SAL-021"))
def test_sal_021(ctx):
    """Expected v15 outcome: FAIL — twice, both v19-target expectations.

    (a) The workbook requires the auto-created invoice to survive the order
    cancellation in state 'draft'. v15 `sale.order._action_cancel()` calls
    `inv.button_cancel()` on the draft invoices first, so the invoice ends
    'cancel'. The invoice does still exist, and the order does reach 'cancel'
    through the `sale.order.cancel` confirmation wizard, so those assertions
    pass and the FAIL is precisely scoped to the invoice state.
    (b) The multi-order variant must complete "without traceback"; v15 builds
    the wizard action with `{'default_order_id': self.id}`, and `self.id` on a
    multi-record recordset raises "Expected singleton", which is recorded
    verbatim as the actual value.

    The whole point of the TC is to record the v15 baseline behaviour as the
    contract, so both observations are evidence, not automation defects.
    """
    rpc = ctx.adapter.rpc
    checks = Checks(ctx)
    with ctx.step("Sweep previous FG-03 fixtures (fresh namespace)"):
        sweep_fg03(rpc, ctx.log)
    with ctx.step("Preconditions: the company flag exists + AvaTax does not "
                  "hijack action_confirm"):
        require_field(ctx, rpc, "res.company", AUTO_FLAG,
                      "mmg_sale_auto_create_invoice",
                      "the auto-created invoice this TC cancels around")
        avatax_confirm_probe(ctx, rpc)
    with ctx.step("Fixture: setting ON, confirmed order with its "
                  "auto-created draft invoice (the TC-SAL-013 flow)"):
        cid = company_id(rpc)
        flag = get_auto_invoice_flag(rpc, cid)
        partner = make_partner(rpc, "CancelInv Customer")
        product = make_product(rpc, "Artwork 500", 500.0)
    try:
        set_auto_invoice_flag(rpc, cid, True)
        order = make_order(rpc, partner, [(product, 1.0, 500.0)])
        ok, res = attempt(rpc.call, "sale.order", "action_confirm", [order])
        ctx.log(f"fixture confirm ok={ok} result={res!r}")
        invoices = rpc.read("sale.order", [order],
                            ["invoice_ids"])[0]["invoice_ids"]
        if len(invoices) != 1:
            # the fixture this TC needs is TC-SAL-013's output; without it
            # there is nothing to observe, and a FAIL here would be reported
            # against the wrong test case
            ctx.blocked(
                "the fixture of this TC (one confirmed order carrying exactly "
                f"one auto-created invoice) could not be built: confirm "
                f"returned {res!r} and the order carries {len(invoices)} "
                "invoice(s). Run TEST-FG03-SAL-013 first — it isolates the "
                "auto-invoice-on-confirm behaviour this TC depends on.")
        invoice = invoices[0]
        with ctx.step("Cancel the order, completing the confirmation wizard "
                      "when one is raised"):
            raised, detail, wizard = cancel_order_flow(rpc, [order])
            ctx.log(f"cancel flow: wizard_raised={wizard} "
                    f"error={detail or 'none'}")
            state = rpc.read("sale.order", [order], ["state"])[0]["state"]
            checks.record("order state after cancel", "cancel", state)
        with ctx.step("The auto-created invoice still exists and stays "
                      "draft - never deleted, never posted"):
            rows = rpc.search_read("account.move", [("id", "=", invoice)],
                                   ["state"])
            observed = rows[0]["state"] if rows else "deleted"
            ctx.log(f"v{ctx.env.version} recorded invoice state after the "
                    f"order cancel: {observed}")
            checks.record("invoice still exists", 1, len(rows))
            checks.record("invoice state after the order cancel", "draft",
                          observed)
        with ctx.step("Multi-order variant: cancel 2 auto-invoice orders in "
                      "one call without traceback"):
            more = [make_order(rpc, partner, [(product, 1.0, 500.0)])
                    for _ in range(2)]
            ok, res = attempt(rpc.call, "sale.order", "action_confirm", more)
            ctx.log(f"multi fixture confirm ok={ok} result={res!r}")
            raised, detail, wizard = cancel_order_flow(rpc, more)
            ctx.log(f"multi-order cancel: wizard_raised={wizard} "
                    f"error={detail or 'none'}")
            checks.record("multi-order cancel completes without traceback",
                          None, detail or None)
            states = [r["state"] for r in
                      rpc.read("sale.order", more, ["state"])]
            ctx.log(f"multi-order cancel end states: {states}")
        with ctx.step("Assert the workbook's expected results"):
            checks.assert_all()
    finally:
        with ctx.step("Cleanup fixtures and restore the setting"):
            restore_auto_invoice_flag(ctx, rpc, cid, flag)
            sweep_fg03(rpc, ctx.log)
