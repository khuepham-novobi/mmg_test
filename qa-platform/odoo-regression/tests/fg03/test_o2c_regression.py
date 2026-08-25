"""FG-03 — order-to-cash regression and data reconciliation:
TC-SAL-017, TC-SAL-018, TC-SAL-023, TC-DAT-009.

TC-SAL-017 walks the whole chain the gallery actually runs (quotation ->
confirm -> deliver -> invoice -> pay) and its totals encode the v19 discount
formula: a $100 dollar discount on a qty 2 x $500 line is 10 % of the line
total, so amount_untaxed is 900.00. The v15 code divides by the unit price
only (20 %), so the totals differ by design — an expected v15 FAIL that
classifies as FIXED when v19 passes. The dollar discount is applied with a
`write()` (the path a salesperson's save takes on v15, where `create()` has
no hook); the missing create hook itself is TEST-FG03-SAL-007's subject, so
this chain fails on the formula, not on a second cause.

Everything after the discount assertion still runs and is recorded, because
the observations are collected and asserted once at the end — otherwise the
first mismatch would hide whether delivery, invoicing and payment work at
all on the baseline.

The delivery leg uses a CONSUMABLE fixture product (`make_deliverable`), not a
storable one: `sale_stock` computes `qty_delivered` from stock moves for
`consu` lines exactly as for `product` lines, while the product stays outside
mmg_magento2_ept_inherit's `type == 'product'` paths — the availability check
and the Magento stock export (which can reach an outbound API call). See
`tests/fg03/common.py`.

TC-SAL-023 drives the report through the web client's own endpoints
(`/report/pdf/...` and `/report/html/...`) over an authenticated session,
because `_render_qweb_pdf` returns bytes that cannot cross the JSON-RPC
boundary. wkhtmltopdf is a documented precondition and is probed first
(BLOCKED, not FAILED, when it is missing).

TC-DAT-009 applies the workbook's own state-mapping rule *inside* the
capture: v19 has no separate 'done' state (locked orders are state 'sale'
with locked = TRUE), so the v15 'sale' and 'done' buckets are merged per year
before the snapshot is stored. Without that the diff would report a false
mismatch on every year that contains locked orders.
"""
import re

from framework.registry import test_case
from tests.fg03.common import (Checks, MARK, QA_PARTNER_SQL, attempt,
                               avatax_confirm_probe, company_id,
                               get_auto_invoice_flag, invoice_or_block,
                               line_state, m2o_id, make_deliverable,
                               make_order, make_partner, make_product,
                               order_lines, payment_journal, pickings_of,
                               reconcile, register_payment,
                               report_response, restore_auto_invoice_flag,
                               reverse_invoice, rounded,
                               set_auto_invoice_flag, sweep_fg03, trace,
                               validate_picking)

QUOTATION_REPORT = "sale.report_saleorder"


def _plain_text(payload: bytes) -> str:
    """HTML -> searchable text (tags dropped, whitespace normalised)."""
    text = payload.decode("utf-8", "replace")
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text,
                  flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    return re.sub(r"\s+", " ", text)


def _amount_forms(value) -> list:
    """The renderings a monetary amount can take in a QWeb report."""
    plain = f"{value:,.2f}"
    return [plain, plain.replace(",", "")]


@test_case(
    id="TEST-FG03-SAL-017",
    name="Quotation, confirm, deliver, invoice, pay - happy path",
    workflow="FG-03", workflow_name="Sales & Pricing",
    module="sale, all mmg_sale*", priority="P0", kind="API", order=321,
    description="The full order-to-cash chain with a converted dollar "
                "discount: discount 10.00 and untaxed 900.00, one "
                "auto-created invoice, delivery to 'full', invoice posted and "
                "paid, and the posted invoice visible in display_invoice_ids. "
                "The v15 formula yields 20.00 / 800.00 - expected FAIL.",
    traceability=trace("TC-SAL-017"))
def test_sal_017(ctx):
    """Expected v15 outcome: FAIL — on the money, and only on the money.

    The workbook's totals encode the v19 per-line-total discount formula: $100
    off a qty 2 x $500 line is 10 % and amount_untaxed 900.00. The verified v15
    code (`mmg_automated_action`) divides by the UNIT PRICE only, so it stores
    discount 20.00 / untaxed 800.00 and the invoice total follows — an
    intentional formula change (FG-03 decision #4b), so this FAIL is the
    documented baseline and classifies as FIXED when v19 passes. Everything
    else is expected to PASS and is asserted after the discount observation
    (collected assertions): state 'sale', exactly one auto-created draft
    invoice, delivery_status pending then full, qty_delivered 2.0, the posted
    invoice, invoice_status 'invoiced', payment_state paid/in_payment and the
    display_invoice_ids cross-check.

    BLOCKED (not FAILED) when a precondition of the chain is missing: no bank
    or cash journal for the payment leg, or AvaTax forcing address validation
    on confirm.
    """
    rpc = ctx.adapter.rpc
    checks = Checks(ctx)
    with ctx.step("Sweep previous FG-03 fixtures (fresh namespace)"):
        sweep_fg03(rpc, ctx.log)
    with ctx.step("Preconditions: a payment journal + AvaTax does not hijack "
                  "action_confirm"):
        cid = company_id(rpc)
        journal = payment_journal(rpc, cid)
        if not journal:
            ctx.blocked(
                f"no bank or cash journal in company {cid} — the payment leg "
                "of this chain (account.payment.register) is a documented "
                "precondition of the TC and cannot be driven on this "
                "database")
        avatax_confirm_probe(ctx, rpc)
    with ctx.step("Fixture: deliverable (consumable) product at 500.00, "
                  "auto-invoice ON, a customer"):
        flag = get_auto_invoice_flag(rpc, cid)
        partner = make_partner(rpc, "O2C Customer")
        product = make_deliverable(rpc, "O2C Artwork 500", 500.0)
    try:
        set_auto_invoice_flag(rpc, cid, True)
        order = invoice = None
        picks = []
        with ctx.step("Quotation: one line qty 2 x 500.00 with "
                      "x_discount = 100 -> discount 10.00, untaxed 900.00"):
            order = make_order(rpc, partner, [(product, 2.0, 500.0)])
            line = order_lines(rpc, order, ["id"])[0]["id"]
            ok, err = attempt(rpc.write, "sale.order.line", [line],
                              {"x_discount": 100.0})
            got = line_state(rpc, line)
            ctx.log(f"line after the dollar discount write: {got} (ok={ok})")
            checks.record("line discount", 10.0,
                          rounded(got["discount"]) if ok else err)
            checks.record("order amount_untaxed", 900.0,
                          rounded(rpc.read("sale.order", [order],
                                           ["amount_untaxed"])[0]
                                  ["amount_untaxed"]))
        with ctx.step("Confirm: state 'sale', one auto-created draft "
                      "invoice, a delivery transfer, nothing delivered yet"):
            ok, res = attempt(rpc.call, "sale.order", "action_confirm",
                              [order])
            ctx.log(f"action_confirm ok={ok} result={res!r}")
            got = rpc.read("sale.order", [order],
                           ["state", "invoice_ids", "delivery_status"])[0]
            checks.record("order state after confirm", "sale", got["state"])
            checks.record("auto-created invoices", 1,
                          len(got["invoice_ids"]))
            picks = pickings_of(rpc, order)
            checks.record("a delivery transfer exists", True, bool(picks))
            checks.record("delivery_status after confirm", "pending",
                          got["delivery_status"])
            invoice = got["invoice_ids"][0] if got["invoice_ids"] else None
        with ctx.step("Deliver: set the done quantities and validate the "
                      "transfer"):
            for pick in picks:
                state = rpc.read("stock.picking", [pick],
                                 ["state"])[0]["state"]
                if state in ("done", "cancel"):
                    continue
                ok, res = attempt(validate_picking, rpc, pick)
                if not ok:
                    # a refused validation is evidence; the qty_delivered and
                    # delivery_status assertions below are the verdict
                    ctx.log(f"validating transfer {pick} refused: {res}")
            got = rpc.read("sale.order", [order], ["delivery_status"])[0]
            checks.record("line qty_delivered", 2.0,
                          rounded(line_state(rpc, line, ["qty_delivered"])
                                  ["qty_delivered"]))
            checks.record("delivery_status after the delivery", "full",
                          got["delivery_status"])
        with ctx.step("Invoice: post the auto-created invoice"):
            if not invoice:
                checks.record("invoice posted", "posted",
                              "no invoice was created on confirm")
            else:
                ok, res = attempt(rpc.call, "account.move", "action_post",
                                  [invoice])
                data = rpc.read("account.move", [invoice],
                                ["state", "amount_untaxed", "amount_total",
                                 "payment_state"])[0]
                ctx.log(f"invoice {invoice}: {data} (post ok={ok})")
                checks.record("invoice state", "posted",
                              data["state"] if ok else res)
                checks.record("invoice amount_untaxed", 900.0,
                              rounded(data["amount_untaxed"]))
                checks.record("order invoice_status", "invoiced",
                              rpc.read("sale.order", [order],
                                       ["invoice_status"])[0]
                              ["invoice_status"])
        with ctx.step("Pay: register the full payment on the posted invoice"):
            if invoice:
                ok, res = attempt(register_payment, rpc, invoice)
                data = rpc.read("account.move", [invoice],
                                ["payment_state", "amount_residual"])[0]
                ctx.log(f"after payment registration (ok={ok}, {res!r}): "
                        f"payment_state={data['payment_state']!r} "
                        f"residual={data['amount_residual']}")
                checks.record("invoice payment_state is paid or in_payment",
                              True,
                              data["payment_state"] in ("paid", "in_payment"))
        with ctx.step("Final cross-checks: the posted invoice shows on the "
                      "order and the totals agree"):
            if invoice:
                got = rpc.read("sale.order", [order],
                               ["display_invoice_ids", "amount_total"])[0]
                checks.record("posted invoice in display_invoice_ids", True,
                              invoice in got["display_invoice_ids"])
                inv_total = rounded(rpc.read("account.move", [invoice],
                                             ["amount_total"])[0]
                                    ["amount_total"])
                checks.record("order amount_total equals the invoice total",
                              inv_total, rounded(got["amount_total"]))
        with ctx.step("Assert the workbook's expected results"):
            checks.assert_all()
    finally:
        with ctx.step("Cleanup fixtures and restore the auto-invoice flag"):
            restore_auto_invoice_flag(ctx, rpc, cid, flag)
            sweep_fg03(rpc, ctx.log)


@test_case(
    id="TEST-FG03-SAL-018",
    name="Credit note from a posted invoice",
    workflow="FG-03", workflow_name="Sales & Pricing", module="account",
    priority="P1", kind="API", order=322,
    description="The reversal wizard produces a posted out_refund linked "
                "through reversed_entry_id, the order's invoice_status falls "
                "back to 'to invoice' after a full refund, and both the "
                "invoice and the credit note appear in display_invoice_ids.",
    traceability=trace("TC-SAL-018"))
def test_sal_018(ctx):
    """Expected v15 outcome: PASS.

    Pure standard-Odoo behaviour (`account.move.reversal` plus mmg_sale's
    display_invoice_ids compute, which keeps out_refund moves), so this test
    records the v15 baseline the v19 run is compared against rather than a
    v19-target expectation. It BLOCKS instead of failing when an accounting
    precondition is missing (invoice cannot be created or posted on this
    database: closed period, journal/rights), and records a refused reversal as
    the actual value instead of aborting.
    """
    rpc = ctx.adapter.rpc
    checks = Checks(ctx)
    with ctx.step("Sweep previous FG-03 fixtures (fresh namespace)"):
        sweep_fg03(rpc, ctx.log)
    with ctx.step("Precondition: AvaTax does not hijack action_confirm"):
        avatax_confirm_probe(ctx, rpc)
    with ctx.step("Fixture: confirmed, fully invoiced order with a POSTED "
                  "invoice (auto-invoice off)"):
        cid = company_id(rpc)
        flag = get_auto_invoice_flag(rpc, cid)
        partner = make_partner(rpc, "Credit Note Customer")
        product = make_product(rpc, "Artwork 500", 500.0)
    try:
        set_auto_invoice_flag(rpc, cid, False)
        order = make_order(rpc, partner, [(product, 1.0, 500.0)])
        rpc.call("sale.order", "action_confirm", [order])
        invoice = invoice_or_block(ctx, rpc, order, "the fixture invoice")
        ok, res = attempt(rpc.call, "account.move", "action_post", [invoice])
        if not ok:
            ctx.blocked(
                f"posting a customer invoice is refused on this database "
                f"({res}) — an accounting precondition of this TC, not a "
                "defect in the reversal flow")
        with ctx.step("Create the credit note through the reversal wizard "
                      "and post it"):
            ok, new_moves = attempt(reverse_invoice, rpc, invoice,
                                    "FG-03 UAT reversal")
            if not ok:
                ctx.log(f"account.move.reversal refused: {new_moves}")
                new_moves = []
            checks.record("one credit note created", 1, len(new_moves))
            credit = new_moves[0] if new_moves else None
            if credit:
                ok, res = attempt(rpc.call, "account.move", "action_post",
                                  [credit])
                data = rpc.read("account.move", [credit],
                                ["move_type", "state",
                                 "reversed_entry_id"])[0]
                ctx.log(f"credit note {credit}: {data} (post ok={ok})")
                checks.record("credit note move_type", "out_refund",
                              data["move_type"])
                checks.record("credit note state", "posted",
                              data["state"] if ok else res)
                checks.record("credit note reversed_entry_id", invoice,
                              m2o_id(data["reversed_entry_id"]))
        with ctx.step("The order's invoice_status recomputes after the full "
                      "refund"):
            status = rpc.read("sale.order", [order],
                              ["invoice_status"])[0]["invoice_status"]
            ctx.log(f"v{ctx.env.version} recorded invoice_status after a full "
                    f"refund: {status!r}")
            checks.record("invoice_status after a full refund", "to invoice",
                          status)
        with ctx.step("Display Invoices lists both the invoice and the "
                      "credit note"):
            shown = rpc.read("sale.order", [order],
                             ["display_invoice_ids"])[0]["display_invoice_ids"]
            ctx.log(f"display_invoice_ids={sorted(shown)} "
                    f"(invoice={invoice} credit={credit})")
            checks.record("invoice and credit note both in "
                          "display_invoice_ids",
                          sorted(i for i in (invoice, credit) if i),
                          sorted(shown))
        with ctx.step("Assert the workbook's expected results"):
            checks.assert_all()
    finally:
        with ctx.step("Cleanup fixtures and restore the auto-invoice flag"):
            restore_auto_invoice_flag(ctx, rpc, cid, flag)
            sweep_fg03(rpc, ctx.log)


@test_case(
    id="TEST-FG03-SAL-023",
    name="Sales order print (quotation PDF)",
    workflow="FG-03", workflow_name="Sales & Pricing", module="sale",
    priority="P2", kind="HYBRID", order=323,
    description="The quotation report renders through the web endpoints "
                "(PDF bytes plus the HTML rendering) and shows the order "
                "name, the product, the converted 10.00 discount and the "
                "order total. v15 renders 20.00 in the Disc.% column - "
                "expected FAIL.",
    traceability=trace("TC-SAL-023"))
def test_sal_023(ctx):
    """Expected v15 outcome: FAIL — on exactly one assertion.

    The Disc.% column of the rendered quotation shows the stored discount, and
    the v15 formula stores 20.00 for the fixture line (qty 2 x 500 with
    x_discount 100), so the workbook's "report shows the converted discount
    10.00" is absent from the document. Everything else passes: the PDF
    endpoint returns 200 with a %PDF- payload and the HTML rendering carries
    the order name, the product and the order's own total.

    BLOCKED (not FAILED) when wkhtmltopdf is unavailable — the workbook lists
    it as an environment precondition. Documented adaptations: the report is
    fetched through the web client's own endpoints (`_render_qweb_pdf` returns
    bytes that cannot cross the JSON-RPC boundary), and the text assertions run
    against `/report/html` of the same report because no PDF-to-text tool is
    available in this runner.
    """
    rpc = ctx.adapter.rpc
    checks = Checks(ctx)
    with ctx.step("Sweep previous FG-03 fixtures (fresh namespace)"):
        sweep_fg03(rpc, ctx.log)
    with ctx.step("Preconditions: wkhtmltopdf for PDF rendering + AvaTax does "
                  "not hijack action_confirm"):
        ok, state = attempt(rpc.call, "ir.actions.report",
                            "get_wkhtmltopdf_state")
        ctx.log(f"wkhtmltopdf state: {state!r}")
        if not ok or state != "ok":
            ctx.blocked(
                f"report rendering requires wkhtmltopdf — "
                f"ir.actions.report.get_wkhtmltopdf_state() = {state!r}; "
                "the workbook lists it as an environment precondition")
        avatax_confirm_probe(ctx, rpc)
    with ctx.step("Fixture: confirmed order with a converted dollar "
                  "discount (auto-invoice off)"):
        cid = company_id(rpc)
        flag = get_auto_invoice_flag(rpc, cid)
        partner = make_partner(rpc, "Print Customer")
        product = make_product(rpc, "Print Artwork 500", 500.0)
    try:
        set_auto_invoice_flag(rpc, cid, False)
        order = make_order(rpc, partner, [(product, 2.0, 500.0)])
        line = order_lines(rpc, order, ["id"])[0]["id"]
        attempt(rpc.write, "sale.order.line", [line], {"x_discount": 100.0})
        ok, res = attempt(rpc.call, "sale.order", "action_confirm", [order])
        ctx.log(f"fixture confirm ok={ok} result={res!r} — the report renders "
                "for a quotation as well, so a refused confirm does not "
                "invalidate the assertions below")
        head = rpc.read("sale.order", [order], ["name", "amount_total"])[0]
        line_data = line_state(rpc, line, ["name", "discount"])
        ctx.log(f"order {head['name']}: total={head['amount_total']} "
                f"line discount={line_data['discount']}")
        with ctx.step("PDF rendering returns a real PDF payload"):
            status, payload = report_response(ctx, "pdf", QUOTATION_REPORT,
                                             order)
            ctx.log(f"/report/pdf status={status} bytes={len(payload)}")
            checks.record("PDF endpoint HTTP status", 200, status)
            checks.record("payload is a PDF", True,
                          payload[:5] == b"%PDF-")
            checks.record("PDF payload is not empty", True, len(payload) > 0)
        with ctx.step("The rendered document shows the order name, the "
                      "product, the converted discount and the total"):
            status, payload = report_response(ctx, "html", QUOTATION_REPORT,
                                              order)
            text = _plain_text(payload)
            ctx.log(f"/report/html status={status} text chars={len(text)}")
            checks.record("HTML endpoint HTTP status", 200, status)
            checks.record("report shows the order name", True,
                          head["name"] in text)
            checks.record("report shows the product", True,
                          (line_data["name"] or "").split("\n")[0] in text)
            checks.record("report shows the converted discount 10.00", True,
                          "10.00" in text)
            checks.record("report shows the order total", True,
                          any(form in text for form in
                              _amount_forms(head["amount_total"])))
        with ctx.step("Print > Quotation / Order from the form (manual)"):
            ctx.log("Manual UI check: Print > Quotation / Order on the order "
                    "form resolves and downloads the same PDF without a "
                    "traceback. Note that no FG-03 module customises the "
                    "sale report template, so any layout difference belongs "
                    "to another feature group (mmg_report / "
                    "mmg_change_invoice_template).")
        with ctx.step("Assert the workbook's expected results"):
            checks.assert_all()
    finally:
        with ctx.step("Cleanup fixtures and restore the auto-invoice flag"):
            restore_auto_invoice_flag(ctx, rpc, cid, flag)
            sweep_fg03(rpc, ctx.log)


@test_case(
    id="TEST-FG03-DAT-009",
    name="Sales order totals reconcile by year and state",
    workflow="FG-03", workflow_name="Sales & Pricing", module="sale",
    priority="P0", kind="DATA", order=324,
    description="Read-only per (year, mapped state) reconciliation of order "
                "count, amount_untaxed, amount_tax and amount_total. The "
                "v15 'sale' and 'done' buckets are merged at capture time "
                "because v19 has no separate 'done' state (locked orders are "
                "'sale' with locked = TRUE); QA fixture orders are excluded.",
    traceability=trace("TC-DAT-009"))
def test_dat_009(ctx):
    """Expected v15 outcome: PASS — it captures and persists the baseline.

    DATA_RECONCILIATION: on v15 the snapshot is written to `data/baselines/`
    and attached as an artifact (no anchor is asserted — the workbook's
    ~43,117-order volume is a dated property of the source database, logged as
    context, never asserted, so this test cannot drift into a false failure).
    On v19 the same capture is diffed against that baseline and any delta is
    the finding. BLOCKED when the environment has no read-only PostgreSQL
    configuration, which the workbook lists as a precondition.

    Read-only: it never creates a fixture, and every bucket excludes this
    platform's own fixture partners so reruns of the functional FG-03 tests
    cannot move the baseline.
    """
    def capture(inner_ctx):
        total = inner_ctx.sql.one(
            "SELECT count(*) FROM sale_order "
            f"WHERE partner_id NOT IN {QA_PARTNER_SQL}")
        # The workbook's ~43,117-order volume is a dated precondition of the
        # source database, not an invariant of the clone: it is logged as
        # context, never asserted (the v15 <-> v19 diff below is the check).
        inner_ctx.log(f"  sale orders in scope (QA fixtures excluded): "
                      f"{total} (workbook context: ~43,117)")
        out = {"sale_order rows": total}
        for year, state, count, untaxed, tax, amount in inner_ctx.sql.rows(
                "SELECT coalesce(date_part('year', date_order)::text, "
                "       'no-date') AS yr, "
                "       CASE WHEN state IN ('sale', 'done') THEN 'sale+done' "
                "            ELSE coalesce(state, 'none') END AS st, "
                "       count(*), round(sum(amount_untaxed), 2), "
                "       round(sum(amount_tax), 2), "
                "       round(sum(amount_total), 2) "
                "FROM sale_order "
                f"WHERE partner_id NOT IN {QA_PARTNER_SQL} "
                "GROUP BY 1, 2 ORDER BY 1, 2"):
            out[f"{year}|{state}"] = (f"count={count}|untaxed={untaxed}|"
                                      f"tax={tax}|total={amount}")
        return out

    with ctx.step("Scope note: this reconciliation is read-only and never "
                  "touches fixtures"):
        ctx.log(f"QA fixture partners (marker '{MARK} ' and ref QA-AUTO) are "
                "excluded from every bucket so reruns of the functional "
                "FG-03 tests cannot drift this baseline.")
    reconcile(ctx, "TC-DAT-009", capture)
