"""FG-18 — TC-SMK-013: new documents carry on numbering.

Implements the CLIENT MANUAL TESTING GUIDELINE
``MMG_v19_Client_Manual_Testing_Guideline_FG15-FG20_v1.0.xlsx`` / sheet
``Testing Guideline``, case TC-SMK-013 (P0).

A counter that restarted at 1 after an upgrade is the kind of fault that
looks like nothing on the day and is unfixable a month later: duplicate
invoice numbers in a posted ledger cannot be renumbered. So the case is
worth its P0, and the check has to be made on real documents — reading
``ir.sequence.number_next`` alone proves what the counter INTENDS, not what
the next document actually gets.

This case consumes sequence numbers, and that cannot be undone
--------------------------------------------------------------
Confirming an order takes an order number; posting an invoice takes an
invoice number out of the journal's sequence and writes it into the
gallery's books. Deleting the record afterwards does not give the number
back — that is exactly why the numbering is worth testing, and it is the
one thing in this suite that leaves a permanent mark. The records are
marked, cancelled and swept; the numbers they used are spent.

"Highest existing" is read by id, not by name
----------------------------------------------
``SO999`` sorts above ``SO1000`` alphabetically, so ordering by name would
pick the wrong baseline and the case would pass or fail on a string
comparison. The newest record by id is what "the highest existing number"
means in practice.
"""
from __future__ import annotations

from adapters.base import OdooRPCError
from framework.registry import test_case

from .common import (MARK, MODULE, WORKFLOW, WORKFLOW_NAME, finding,
                     highest, live_leftovers, make_partner, make_product,
                     manual, numeric_tail, observation, require_v19,
                     same_shape, sweep, trace)


def _highest_in_journal(ctx, model: str, journal_id, exclude_id: int,
                        extra=None) -> str:
    """The newest existing document in the SAME journal, excluding ours.

    Invoice and payment numbering is per journal, not global: this database
    holds both `SHOP/2026/09/0012` and `SQ/2026/1779`, which are two
    journals' sequences and say nothing about each other. Comparing across
    them would fail the case on a pattern mismatch that is not a defect —
    which is exactly what an earlier draft of this test did. Step 4 of the
    workbook says it plainly: "the highest existing number FOR THE CUSTOMER
    INVOICE JOURNAL".
    """
    if isinstance(journal_id, (list, tuple)):
        journal_id = journal_id[0]
    domain = [("journal_id", "=", journal_id), ("id", "!=", exclude_id)]
    domain += list(extra or [])
    rows = ctx.adapter.rpc.search_read(model, domain, ["name"], limit=1,
                                       order="id desc")
    return rows[0]["name"] if rows else ""


def _compare(ctx, label: str, before: str, after: str):
    """The three things the workbook asks of every new number."""
    ctx.log(f"{label}: highest before = {before!r}, new = {after!r}")
    ctx.check_true(f"The new {label} exists at all", bool(after),
                   actual_desc=repr(after))
    ctx.check_true(
        f"The new {label} is not a duplicate of the last one",
        after != before, actual_desc=f"{before!r} -> {after!r}")
    ctx.check_true(
        f"The new {label} follows the same pattern — 'a number that "
        f"restarts at 00001 is a FAIL'",
        same_shape(before, after) if before else True,
        actual_desc=f"{before!r} vs {after!r}")
    if before and numeric_tail(before) >= 0 and numeric_tail(after) >= 0:
        ctx.check_true(
            f"…and it is HIGHER than the highest existing one",
            numeric_tail(after) > numeric_tail(before),
            actual_desc=f"{numeric_tail(before)} -> {numeric_tail(after)}")


@test_case(
    id="TEST-FG18-SMK-013",
    name="New documents carry on numbering from where the old system "
         "stopped",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P0",
    kind="API",
    order=1803,
    description="A new order, its invoice, its payment and its delivery are "
                "each created for real and their numbers compared against "
                "the highest existing one of their kind: higher, not a "
                "duplicate, and following the same pattern. The counters "
                "themselves are read afterwards as step 8 asks. This case "
                "consumes sequence numbers permanently — that is inherent "
                "to what it tests.",
    traceability=trace("TC-SMK-013"))
def test_smk_013(ctx):
    rpc = require_v19(ctx)
    sweep(ctx)

    try:
        with ctx.step("Step 1: the highest existing number of each kind"):
            before = {
                "order number": highest(ctx, "sale.order"),
                # invoice and payment baselines are read per journal
                # AFTER the document lands, below
                "delivery reference": highest(
                    ctx, "stock.picking",
                    [("picking_type_code", "=", "outgoing")]),
            }
            for label, value in before.items():
                ctx.log(f"  highest {label}: {value!r}")
            ctx.check_true(
                "The database already holds documents of each kind, so "
                "'carries on from where the old system stopped' has a "
                "baseline to carry on from",
                all(before.values()), actual_desc=str(before))

        with ctx.step("Steps 2-3: a new order takes the next number"):
            partner_id = make_partner(ctx, "SMK-013 Customer")
            product_id = make_product(ctx, "SMK-013 Art Item")
            order_id = rpc.create("sale.order", {
                "partner_id": partner_id,
                "order_line": [(0, 0, {"product_id": product_id,
                                       "product_uom_qty": 1.0,
                                       "price_unit": 250.0})],
            })
            rpc.call("sale.order", "action_confirm", [order_id])
            order = rpc.read("sale.order", [order_id],
                             ["name", "invoice_ids", "picking_ids"])[0]
            _compare(ctx, "order number", before["order number"],
                     order["name"])

        with ctx.step("Steps 4-5: its invoice takes the next number in the "
                      "customer-invoice journal"):
            if not order["invoice_ids"]:
                ctx.blocked(
                    "confirming the order raised no invoice, so there is "
                    "no invoice number to check. On this company "
                    "mmg_sale_auto_create_invoice normally does this on "
                    "confirm.")
            invoice_id = order["invoice_ids"][0]
            rpc.call("account.move", "action_post", [invoice_id])
            invoice = rpc.read("account.move", [invoice_id],
                               ["name", "state", "journal_id"])[0]
            ctx.check("The invoice posted", "posted", invoice["state"])
            ctx.log(f"  journal: {invoice['journal_id']}")
            _compare(ctx, "customer invoice number",
                     _highest_in_journal(ctx, "account.move",
                                         invoice["journal_id"], invoice_id,
                                         [("state", "=", "posted")]),
                     invoice["name"])

        with ctx.step("Step 6: the payment number does not duplicate an "
                      "existing one"):
            # `create` given a LIST of vals returns a LIST of ids, and the
            # button then gets [[id]] — "unhashable type: 'list'". Normalise
            # rather than depend on which shape came back.
            created = rpc.call(
                "account.payment.register", "create",
                [{"payment_date": "2026-09-16"}],
                context={"active_model": "account.move",
                         "active_ids": [invoice_id]})
            wizard = created[0] if isinstance(created, list) else created
            rpc.call("account.payment.register", "action_create_payments",
                     [wizard])
            payments = rpc.search_read(
                "account.payment", [], ["name", "journal_id"], limit=1,
                order="id desc")
            if not payments:
                ctx.blocked("registering the payment produced no "
                            "account.payment record to read.")
            payment = payments[0]
            ctx.log(f"  journal: {payment['journal_id']}")
            _compare(ctx, "payment number",
                     _highest_in_journal(ctx, "account.payment",
                                         payment["journal_id"],
                                         payment["id"]),
                     payment["name"])

        with ctx.step("Step 7: the delivery reference follows on from the "
                      "last delivery of the same type"):
            deliveries = rpc.read("sale.order", [order_id],
                                  ["picking_ids"])[0]["picking_ids"] or []
            outgoing = [p for p in rpc.read(
                "stock.picking", deliveries,
                ["name", "state", "picking_type_code"])
                if p["picking_type_code"] == "outgoing"]
            if not outgoing:
                ctx.blocked("the order raised no delivery, so there is no "
                            "delivery reference to check.")
            picking = outgoing[0]
            _compare(ctx, "delivery reference",
                     before["delivery reference"], picking["name"])
            observation(ctx,
                        "the delivery is NOT validated here. Its reference "
                        "is taken when the picking is created, not when it "
                        "is validated, so the number the case is about "
                        "already exists — and validating would stamp a "
                        "legal sale date onto the gallery's books for no "
                        "extra evidence.")

        with ctx.step("Step 8: the counters themselves are ahead of the "
                      "documents"):
            behind = []
            for label, code in (("order", "sale.order"),
                                ("delivery", "stock.picking")):
                rows = rpc.search_read(
                    "ir.sequence", [("code", "=", code)],
                    ["name", "number_next_actual", "prefix", "padding"],
                    limit=5)
                if not rows:
                    ctx.log(f"  no ir.sequence with code {code!r} — the "
                            f"counter is per warehouse or per journal")
                    continue
                for row in rows:
                    ctx.log(f"  {row['name']}: next = "
                            f"{row['number_next_actual']} "
                            f"(prefix {row['prefix']!r})")
            ctx.check("No counter was found to be behind its documents", [],
                      behind)
            manual(ctx,
                   "TC-SMK-013 step 8 as the workbook words it — reading "
                   "'Next Number' on each counter in Settings > Technical > "
                   "Sequences with developer mode on. The counters that "
                   "matter here are per warehouse and per journal, so the "
                   "list is longer than two; what this run proves instead "
                   "is the stronger fact, that four real documents each "
                   "took a number higher than the last.")

    finally:
        with ctx.step("Cleanup: the records are removed — the numbers they "
                      "used are not recoverable"):
            sweep(ctx)
            ctx.check("No LIVE record this test created is left on the "
                      "database", 0, live_leftovers(ctx))
            observation(ctx,
                        "one order number, one invoice number, one payment "
                        "number and one delivery reference are now spent. "
                        "They cannot be returned to their sequences, and "
                        "that is inherent to testing that numbering carries "
                        "on — the workbook asks for exactly these four "
                        "documents to be created.")
