"""FG-16 — TC-LEG-005 and TC-LEG-006: the Legal Sale Date chain.

Implements the CLIENT MANUAL TESTING GUIDELINE
``MMG_v19_Client_Manual_Testing_Guideline_FG15-FG20_v1.0.xlsx`` / sheet
``Testing Guideline``, cases TC-LEG-005 (P0) and TC-LEG-006 (P0).

The workbook calls an empty Legal Sale Date after a validated delivery *"the
most serious failure in this feature group"*, and it is right to: the date is
what the gallery's books treat as the moment of sale. The chain that
maintains it is two hooks in ``mmg_legal_date``:

* ``stock.picking._action_done`` stamps ``date_done`` onto the order's
  ``x_legal_sale_date`` and onto its unlocked invoices
  (``models/stock_picking.py:39-73``);
* ``sale.order.write`` re-propagates whenever that field is written
  (``models/sale_order.py:120-124``), skipping invoices
  ``_legal_date_invoice_is_locked`` returns True for — today, cancelled ones
  (``:67-88``).

Both cases run end to end on records this suite creates. That matters here
more than usual: TC-LEG-006 asks for three orders in three different invoice
states, and validating a delivery is irreversible, so borrowing the
gallery's own orders would mean stamping a legal date onto their books.

The posted-invoice branch is recorded, not judged
--------------------------------------------------
TC-LEG-006's Expected Result says of a POSTED invoice: *"The posted
invoice's legal date ALSO changes. This is expected. Record the value and
flag it to the Controller as a decision, not a defect."* So this suite
asserts the behaviour the shipped guard produces and reports it as the open
decision FG-16 D5 already names — ``_legal_date_invoice_is_locked`` is
written as one isolated predicate precisely so the Controller's answer is a
one-line change.
"""
from __future__ import annotations

from adapters.base import OdooRPCError
from framework.registry import test_case

from .common import (MARK, MODULE, MOVE, MOVE_LEGAL_DATE,
                     MOVE_LEGAL_DATE_LEGACY, ORDER, ORDER_LEGAL_DATE,
                     ORDER_LEGAL_DATE_LEGACY, PICKING, WORKFLOW,
                     WORKFLOW_NAME, archived, field_attrs, leftovers,
                     make_order, make_partner, make_product, manual,
                     observation, order_deliveries, order_invoices,
                     require_legal_date, sweep, trace)


def _validate(ctx, picking_id: int):
    """Validate a delivery the way the screen does it.

    The workbook's step 4 says "If a dialog asks about quantities, answer it
    as you normally would". On v19 there is no dialog to answer: the form
    arrives with the quantities already filled and `button_validate` refuses
    outright — *"Set some quantities and let's get moving!"* — when nothing
    is picked. So the quantities are set first, which is the state a tester
    pressing Validate is actually in, and only then is the button pressed.
    A dialog IS still handled, because a picking that needs a backorder or a
    lot raises one.
    """
    rpc = ctx.adapter.rpc
    moves = rpc.search_read("stock.move", [("picking_id", "=", picking_id)],
                            ["product_uom_qty", "quantity", "picked"])
    for move in moves:
        rpc.write("stock.move", [move["id"]],
                  {"quantity": move["product_uom_qty"], "picked": True})
    ctx.log(f"quantities set on {len(moves)} move(s), as the form arrives")

    result = rpc.call(PICKING, "button_validate", [picking_id])
    if isinstance(result, dict) and result.get("res_model"):
        model, wizard = result["res_model"], result.get("res_id")
        ctx.log(f"delivery raised {model} — answering it")
        if wizard:
            rpc.call(model, "process", [wizard])
        else:
            ctx.log(f"[warn] {model} came back without a record to act on")
    return rpc.read(PICKING, [picking_id], ["state", "date_done", "name"])[0]


@test_case(
    id="TEST-FG16-LEG-005",
    name="Validating a delivery stamps the Legal Sale Date on the order",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P0",
    kind="API",
    order=1600,
    description="On a confirmed order whose Legal Sale Date is empty and "
                "whose invoice's is empty too, validating the delivery fills "
                "the order's Legal Sale Date with the delivery's Effective "
                "Date to the minute, and the invoice's read-only Legal Sale "
                "Date shows the same value. Both fields labelled 'Legal Sale "
                "Date' are confirmed on the invoice form, as the workbook's "
                "step 2 describes. Built from scratch records — validating a "
                "delivery cannot be undone.",
    traceability=trace("TC-LEG-005"))
def test_leg_005(ctx):
    rpc = require_legal_date(ctx)
    sweep(ctx)

    try:
        with ctx.step("Preconditions: a confirmed order with an unvalidated "
                      "delivery, an invoice, and both legal dates empty"):
            partner_id = make_partner(ctx, "LEG-005 Customer")
            product_id = make_product(ctx, "LEG-005 Art Item")
            order_id = make_order(ctx, partner_id, product_id)

            order = rpc.read(ORDER, [order_id],
                             ["name", ORDER_LEGAL_DATE, "state"])[0]
            ctx.check("The order is confirmed", "sale", order["state"])
            ctx.check("Its Legal Sale Date starts empty", False,
                      order[ORDER_LEGAL_DATE])
            ctx.log(f"order {order['name']}")

            invoices = order_invoices(ctx, order_id)
            if not invoices:
                ctx.blocked(
                    "confirming the order raised no invoice, so the "
                    "workbook's precondition 'the order has at least one "
                    "invoice raised against it' cannot be met. On this "
                    "company mmg_sale_auto_create_invoice normally does "
                    "this on confirm.")
            ctx.check_true(
                "An invoice exists against the order, with its legal date "
                "empty",
                all(not inv[MOVE_LEGAL_DATE] for inv in invoices),
                actual_desc=str([(i["name"], i["state"], i[MOVE_LEGAL_DATE])
                                 for i in invoices]))

            deliveries = [d for d in order_deliveries(ctx, order_id)
                          if d["picking_type_code"] == "outgoing"]
            if not deliveries:
                ctx.blocked("the order raised no delivery, so there is "
                            "nothing to validate.")
            delivery = deliveries[0]
            ctx.check_true("The delivery is not yet validated",
                           delivery["state"] != "done",
                           actual_desc=f"{delivery['name']} "
                                       f"state={delivery['state']}")

        with ctx.step("Step 2: the invoice form carries TWO fields labelled "
                      "'Legal Sale Date', the second read-only"):
            arch = rpc.call(MOVE, "get_view", view_type="form")["arch"]
            live = field_attrs(arch, MOVE_LEGAL_DATE)
            legacy = field_attrs(arch, MOVE_LEGAL_DATE_LEGACY)
            ctx.check_true(f"{MOVE_LEGAL_DATE!r} is on the invoice form",
                           bool(live), actual_desc=live[:160] or "absent")
            ctx.check_true(
                f"…and so is the second one, {MOVE_LEGAL_DATE_LEGACY!r} — "
                f"the greyed-out one the workbook's step 2 names",
                bool(legacy), actual_desc=legacy[:160] or "absent")
            labels = rpc.call(MOVE, "fields_get",
                              [MOVE_LEGAL_DATE, MOVE_LEGAL_DATE_LEGACY],
                              attributes=["string"])
            ctx.check("Both are labelled 'Legal Sale Date' — which is why the "
                      "workbook tells the tester to expect two",
                      ["Legal Sale Date", "Legal Sale Date"],
                      [labels[MOVE_LEGAL_DATE]["string"],
                       labels[MOVE_LEGAL_DATE_LEGACY]["string"]])
            observation(ctx,
                        "the datetime pair is the live chain; the date pair "
                        "(x_slsdate / x_lsdate) is the older Studio one the "
                        "automations wrote and FG-16 D5 proposes retiring. "
                        "Two fields with one label on one form is itself "
                        "worth the Controller's attention.")

        with ctx.step("Steps 3-5: validate the delivery and read its "
                      "Effective Date"):
            done = _validate(ctx, delivery["id"])
            ctx.check("The delivery is Done", "done", done["state"])
            ctx.check_true("…and carries an Effective Date",
                           bool(done["date_done"]),
                           actual_desc=str(done["date_done"]))
            effective = done["date_done"]
            ctx.log(f"delivery {done['name']} effective {effective}")

        with ctx.step("Step 6 / Expected line 1: the order's Legal Sale Date "
                      "now equals the delivery's Effective Date"):
            after = rpc.read(ORDER, [order_id],
                             [ORDER_LEGAL_DATE, ORDER_LEGAL_DATE_LEGACY])[0]
            ctx.check_true(
                "The order's Legal Sale Date is no longer empty — an empty "
                "one here is the most serious failure in this feature group",
                bool(after[ORDER_LEGAL_DATE]),
                actual_desc=str(after[ORDER_LEGAL_DATE]))
            ctx.check("…and it equals the delivery's Effective Date, to the "
                      "minute", effective, after[ORDER_LEGAL_DATE])

        with ctx.step("Step 7 / Expected line 2: the invoice's read-only "
                      "Legal Sale Date shows the same value"):
            invoices = order_invoices(ctx, order_id)
            ctx.check("Every invoice on the order carries the delivery's "
                      "date", [effective] * len(invoices),
                      [inv[MOVE_LEGAL_DATE] for inv in invoices])
            ctx.log("invoices: " + "; ".join(
                f"{i['name']} ({i['state']}) -> {i[MOVE_LEGAL_DATE]}"
                for i in invoices))

    finally:
        with ctx.step("Cleanup: every record this test created is removed"):
            sweep(ctx)
            kept = archived(ctx)
            if kept:
                ctx.log(f"archived rather than deleted (a posted invoice "
                        f"and anything it references can never be removed): "
                        f"{kept}")
            ctx.check("No LIVE record this test created is left on the "
                      "database", 0, leftovers(ctx))


@test_case(
    id="TEST-FG16-LEG-006",
    name="Changing the Legal Sale Date on an order updates its invoices",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P0",
    kind="API",
    order=1601,
    description="Moving an order's Legal Sale Date back by seven days "
                "immediately moves its DRAFT invoice's; a POSTED invoice's "
                "also moves, which the workbook says to record and flag to "
                "the Controller as a decision rather than judge; and a "
                "CANCELLED invoice's does not move. All three branches are "
                "built here, on three scratch orders, because the case needs "
                "invoices in three different states and posting one is not "
                "something to do to the gallery's books.",
    traceability=trace("TC-LEG-006"))
def test_leg_006(ctx):
    rpc = require_legal_date(ctx)
    sweep(ctx)
    built = {}

    def build(label, invoice_state):
        """One order whose single invoice is left in ``invoice_state``."""
        partner_id = make_partner(ctx, f"LEG-006 {label}")
        product_id = make_product(ctx, f"LEG-006 {label} Item")
        order_id = make_order(ctx, partner_id, product_id)
        invoices = order_invoices(ctx, order_id)
        if not invoices:
            return None
        invoice_id = invoices[0]["id"]
        if invoice_state == "posted":
            rpc.call(MOVE, "action_post", [invoice_id])
        elif invoice_state == "cancel":
            rpc.call(MOVE, "button_cancel", [invoice_id])
        state = rpc.read(MOVE, [invoice_id], ["state"])[0]["state"]
        # Seed a legal date so there is something to change, exactly as the
        # workbook's precondition describes ("a Legal Sale Date already
        # filled in").
        seed = "2026-09-01 10:00:00"
        rpc.write(ORDER, [order_id], {ORDER_LEGAL_DATE: seed})
        ctx.log(f"{label}: order #{order_id} invoice #{invoice_id} "
                f"state={state} seeded {seed}")
        return {"order": order_id, "invoice": invoice_id, "state": state,
                "seed": seed}

    try:
        with ctx.step("Preconditions: three orders, one with a DRAFT "
                      "invoice, one POSTED, one CANCELLED"):
            for label, wanted in (("draft", "draft"), ("posted", "posted"),
                                  ("cancelled", "cancel")):
                built[label] = build(label, wanted)
                if not built[label]:
                    ctx.blocked(
                        f"the {label} order raised no invoice, so that "
                        f"branch of TC-LEG-006 has nothing to check.")
            ctx.check("The three invoices are in the three states the case "
                      "needs", ["draft", "posted", "cancel"],
                      [built[k]["state"] for k in
                       ("draft", "posted", "cancelled")])

            seeded = {k: rpc.read(MOVE, [built[k]["invoice"]],
                                  [MOVE_LEGAL_DATE])[0][MOVE_LEGAL_DATE]
                      for k in built}
            ctx.log(f"invoice legal dates after seeding: {seeded}")

        # Seven days back, same time — the workbook's own suggestion.
        new_value = "2026-08-25 10:00:00"

        with ctx.step("Steps 3-4 / Expected line 1: the DRAFT invoice's "
                      "legal date changes immediately on save"):
            row = built["draft"]
            before = rpc.read(MOVE, [row["invoice"]],
                              [MOVE_LEGAL_DATE])[0][MOVE_LEGAL_DATE]
            rpc.write(ORDER, [row["order"]], {ORDER_LEGAL_DATE: new_value})
            after = rpc.read(MOVE, [row["invoice"]],
                             [MOVE_LEGAL_DATE])[0][MOVE_LEGAL_DATE]
            ctx.log(f"draft invoice: {before} -> {after}")
            ctx.check("The order took the new value", new_value,
                      rpc.read(ORDER, [row["order"]],
                               [ORDER_LEGAL_DATE])[0][ORDER_LEGAL_DATE])
            ctx.check("…and the draft invoice followed it", new_value, after)

        with ctx.step("Step 5 / Expected line 2: the POSTED invoice's legal "
                      "date ALSO changes — recorded, not judged"):
            row = built["posted"]
            before = rpc.read(MOVE, [row["invoice"]],
                              [MOVE_LEGAL_DATE])[0][MOVE_LEGAL_DATE]
            rpc.write(ORDER, [row["order"]], {ORDER_LEGAL_DATE: new_value})
            after = rpc.read(MOVE, [row["invoice"]],
                             [MOVE_LEGAL_DATE, "state"])[0]
            ctx.log(f"posted invoice: {before} -> {after[MOVE_LEGAL_DATE]} "
                    f"(state {after['state']})")
            ctx.check("The invoice is still posted — the propagation does "
                      "not disturb its state", "posted", after["state"])
            ctx.check(
                "The posted invoice's legal date changed too, which is the "
                "shipped behaviour the workbook says to record",
                new_value, after[MOVE_LEGAL_DATE])
            observation(ctx,
                        f"FG-16 D5, for the Controller: a POSTED invoice's "
                        f"legal date was rewritten from {before} to "
                        f"{after[MOVE_LEGAL_DATE]} by editing the order. "
                        f"This reproduces v15's automated action 664, whose "
                        f"guard `state not in ('paid','cancel')` reduces to "
                        f"`state != 'cancel'`. If the answer is that a "
                        f"posted invoice must be frozen, the change is one "
                        f"line: mmg_legal_date/models/sale_order.py:88 "
                        f"becomes `return invoice.state != 'draft'`.")

        with ctx.step("Step 6 / Expected line 3: the CANCELLED invoice's "
                      "legal date does NOT change"):
            row = built["cancelled"]
            before = rpc.read(MOVE, [row["invoice"]],
                              [MOVE_LEGAL_DATE])[0][MOVE_LEGAL_DATE]
            rpc.write(ORDER, [row["order"]], {ORDER_LEGAL_DATE: new_value})
            after = rpc.read(MOVE, [row["invoice"]],
                             [MOVE_LEGAL_DATE, "state"])[0]
            ctx.log(f"cancelled invoice: {before} -> "
                    f"{after[MOVE_LEGAL_DATE]}")
            ctx.check("The cancelled invoice is left alone", before,
                      after[MOVE_LEGAL_DATE])
            ctx.check_true(
                "…and it is specifically NOT the order's new value",
                after[MOVE_LEGAL_DATE] != new_value,
                actual_desc=f"invoice={after[MOVE_LEGAL_DATE]} "
                            f"order={new_value}")

        with ctx.step("Expected line 5: saving raised no error at any point"):
            ctx.check_true(
                "All three writes completed", True,
                actual_desc="draft, posted and cancelled branches all saved")

        with ctx.step("Step 8: the original value is put back on all three "
                      "orders"):
            for label, row in built.items():
                rpc.write(ORDER, [row["order"]],
                          {ORDER_LEGAL_DATE: row["seed"]})
            restored = {k: rpc.read(ORDER, [v["order"]],
                                    [ORDER_LEGAL_DATE])[0][ORDER_LEGAL_DATE]
                        for k, v in built.items()}
            ctx.check("Every order is back to the value it started with",
                      {k: v["seed"] for k, v in built.items()}, restored)

        manual(ctx,
               "TC-LEG-006 step 7 — printing the draft invoice to PDF and "
               "confirming the line 'Legal Sale Date:' appears under the "
               "order number with the new value. The field and its "
               "propagation are asserted above; what the PDF renders is a "
               "QWeb template question, and reading a PDF is not something "
               "this platform does. One print closes it.")

    finally:
        with ctx.step("Cleanup: the three orders and their records are "
                      "removed"):
            sweep(ctx)
            kept = archived(ctx)
            if kept:
                ctx.log(f"archived rather than deleted (a posted invoice "
                        f"and anything it references can never be removed): "
                        f"{kept}")
            ctx.check("No LIVE record this test created is left on the "
                      "database", 0, leftovers(ctx))
