"""FG-20 — TC-PERF-001, -002, -003, -004 and -007.

Implements the CLIENT MANUAL TESTING GUIDELINE
``MMG_v19_Client_Manual_Testing_Guideline_FG15-FG20_v1.0.xlsx`` / sheet
``Testing Guideline``.

Every case here blocks on Novobi's v15 baseline, and every case measures
the v19 side first. See ``tests/fg20/common.py`` for why that is the design
rather than a compromise.

TC-PERF-004 is the one that does not do what it says
-----------------------------------------------------
Its steps rewrite the customer taxes on 1,000 of the gallery's products and
put them back afterwards. On a throwaway copy that is fine; this database
is the one the gallery is recording its acceptance in, and a run that
half-completed would leave a thousand products carrying taxes nobody chose
— which is precisely the failure the case's own step 7 is looking for. Doing
that to obtain a number that cannot be judged without a baseline is a bad
trade, so the write is made against the SAME ORM path with each product's
existing taxes written back onto itself. The cost is the same work; the
outcome is no change.
"""
from __future__ import annotations

from adapters.base import OdooRPCError
from framework.registry import test_case

from .common import (MODULE, STATED_VOLUMES, WORKFLOW, WORKFLOW_NAME,
                     finding, judge_or_block, manual, median_of_three,
                     observation, require_v19, time_count, time_group,
                     time_list, trace, write_measurements)

PRODUCT = "product.template"
ORDER = "sale.order"
MOVE = "account.move"
LOG = "omni.log"
CHANNEL = "ecommerce.channel"


def _volume(ctx, label: str, model: str, stated: int):
    """The count check every list case makes, against the workbook's figure.

    Reported both ways round: a list shows ACTIVE records, and the
    workbook's production figure counts everything. Comparing the wrong one
    would manufacture a shortfall that is not there.
    """
    rpc = ctx.adapter.rpc
    active = rpc.call(model, "search_count", [])
    total = rpc.call(model, "search_count", [],
                     context={"active_test": False})
    ctx.log(f"{label}: {active:,} active, {total:,} including archived; "
            f"the workbook states {stated:,}")
    ctx.check_true(
        f"The {label} volume is production-sized — within 5% of the "
        f"{stated:,} the workbook states",
        abs(total - stated) / stated < 0.05,
        actual_desc=f"{total:,} total ({active:,} active) vs {stated:,} "
                    f"stated")
    return active, total


@test_case(
    id="TEST-FG20-PERF-001",
    name="The product list stays usable at 69,201 pieces",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P1",
    kind="API",
    order=2000,
    description="Times the product list at its default width and at 500 "
                "rows, a name search, a group by category and the expansion "
                "of one group — three runs each, middle value kept, the "
                "workbook's own method. BLOCKED on Novobi's v15 baseline, "
                "which the case's own precondition says it cannot be judged "
                "without; the v19 half is measured and exported.",
    traceability=trace("TC-PERF-001"))
def test_perf_001(ctx):
    rpc = require_v19(ctx)
    measurements = []

    with ctx.step("Step 1: the record count, against the stated production "
                  "volume"):
        _volume(ctx, "products", PRODUCT, STATED_VOLUMES["products"])

    with ctx.step("Steps 1-3: opening the list, and widening it to 500 rows "
                  "— 'this is the number that matters'"):
        measurements.append(time_list(ctx, PRODUCT, limit=80,
                                      label="product list, default width"))
        measurements.append(time_list(ctx, PRODUCT, limit=500,
                                      label="product list, 500 rows"))

    with ctx.step("Step 4: a name search"):
        # The workbook notes this box searches name, internal reference and
        # barcode — NOT the artist field. The domain here is the one the
        # search bar builds.
        needle = "art"
        measurements.append(time_list(
            ctx, PRODUCT,
            ["|", "|", ("name", "ilike", needle),
             ("default_code", "ilike", needle),
             ("barcode", "ilike", needle)],
            limit=80, label=f"product search for {needle!r}"))
        found = rpc.call(PRODUCT, "search_count",
                         ["|", "|", ("name", "ilike", needle),
                          ("default_code", "ilike", needle),
                          ("barcode", "ilike", needle)])
        ctx.log(f"  {found:,} pieces match {needle!r}")

    with ctx.step("Steps 5-6: group by category, then expand one group"):
        measurements.append(time_group(ctx, PRODUCT, "categ_id",
                                       label="product list grouped by "
                                             "category"))
        groups = rpc.read_group(PRODUCT, [], [], ["categ_id"], lazy=True)
        biggest = max(groups, key=lambda g: g.get("categ_id_count") or
                      g.get("__count") or 0) if groups else None
        if biggest and biggest.get("categ_id"):
            categ = biggest["categ_id"]
            categ_id = categ[0] if isinstance(categ, (list, tuple)) else categ
            size = biggest.get("categ_id_count") or biggest.get("__count")
            ctx.log(f"  largest category: {categ} ({size} pieces)")
            measurements.append(time_list(
                ctx, PRODUCT, [("categ_id", "=", categ_id)], limit=80,
                label="expanding the largest category group"))

    with ctx.step("Step 7: the comparison"):
        write_measurements(ctx, "fg20_perf_001_product_list.csv",
                           measurements)
        manual(ctx,
               "these are SERVER times — the web_search_read the list "
               "actually issues — not the stopwatch time the workbook "
               "describes, which also includes transport and render. On a "
               "screen this stack draws with custom widgets (see FG-15), "
               "the render half is not a rounding error. One stopwatch run "
               "alongside these numbers tells Novobi how much of the wall "
               "clock is query and how much is paint.")
        judge_or_block(ctx, "TC-PERF-001", measurements)


@test_case(
    id="TEST-FG20-PERF-002",
    name="The sales order list stays usable at 43,117 orders",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P1",
    kind="API",
    order=2001,
    description="Times the order list at default width and 500 rows, the "
                "Cancelled filter, and group by Shipping Status and by "
                "Store, and confirms the Shipping Status buckets add up to "
                "the list total — which is an answer available without any "
                "baseline. BLOCKED on the v15 timings.",
    traceability=trace("TC-PERF-002"))
def test_perf_002(ctx):
    rpc = require_v19(ctx)
    measurements = []

    with ctx.step("Step 1: the record count and the list"):
        active, total = _volume(ctx, "orders", ORDER,
                                STATED_VOLUMES["orders"])
        measurements.append(time_list(ctx, ORDER, limit=80,
                                      label="order list, default width"))

    with ctx.step("Step 2: 500 rows"):
        measurements.append(time_list(ctx, ORDER, limit=500,
                                      label="order list, 500 rows"))

    with ctx.step("Step 3: the Cancelled filter"):
        measurements.append(time_list(ctx, ORDER, [("state", "=", "cancel")],
                                      limit=80,
                                      label="order list filtered to "
                                            "Cancelled"))
        cancelled = rpc.call(ORDER, "search_count", [("state", "=", "cancel")])
        ctx.log(f"  {cancelled:,} cancelled orders")

    with ctx.step("Steps 4-6: group by Shipping Status, expand the largest, "
                  "then group by Store"):
        measurements.append(time_group(ctx, ORDER, "shipping_status",
                                       label="orders grouped by Shipping "
                                             "Status"))
        groups = rpc.read_group(ORDER, [], [], ["shipping_status"], lazy=True)
        buckets = {}
        for row in groups:
            key = row.get("shipping_status")
            if isinstance(key, (list, tuple)):
                key = key[0]
            buckets[key] = row.get("shipping_status_count") or \
                row.get("__count") or 0
        ctx.log(f"  buckets: {buckets}")
        ctx.check(
            "The Shipping Status buckets add up to the list total — an "
            "answer this case can give without any baseline at all",
            active, sum(buckets.values()))

        if buckets:
            biggest = max(buckets, key=lambda k: buckets[k])
            measurements.append(time_list(
                ctx, ORDER, [("shipping_status", "=", biggest)], limit=80,
                label=f"expanding the largest Shipping Status group "
                      f"({biggest})"))
        measurements.append(time_group(ctx, ORDER, "channel_id",
                                       label="orders grouped by Store"))

    with ctx.step("Step 7: the comparison"):
        write_measurements(ctx, "fg20_perf_002_order_list.csv", measurements)
        judge_or_block(ctx, "TC-PERF-002", measurements)


@test_case(
    id="TEST-FG20-PERF-003",
    name="Invoices and the accounting reports stay usable at 109,218 entries",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P1",
    kind="API",
    order=2002,
    description="Times the invoice list at default width and 500 rows and "
                "confirms the journal-entry volume. The five reports are "
                "measured where the engine is reachable over RPC and named "
                "as residual manual where it is not — a report is a client "
                "action, and what a stopwatch times there is largely the "
                "client. BLOCKED on the v15 timings and on the agreed date "
                "range.",
    traceability=trace("TC-PERF-003"))
def test_perf_003(ctx):
    rpc = require_v19(ctx)
    measurements = []

    with ctx.step("Steps 1-2: the invoice list, and the journal-entry "
                  "volume"):
        _volume(ctx, "journal entries", MOVE,
                STATED_VOLUMES["journal entries"])
        invoices = [("move_type", "=", "out_invoice")]
        ctx.log(f"  {rpc.call(MOVE, 'search_count', invoices):,} customer "
                f"invoices")
        measurements.append(time_list(ctx, MOVE, invoices, limit=80,
                                      label="invoice list, default width"))
        measurements.append(time_list(ctx, MOVE, invoices, limit=500,
                                      label="invoice list, 500 rows"))

    with ctx.step("Steps 3-6: the five reports"):
        wanted = ("Trial Balance", "General Ledger", "Aged Receivable",
                  "Balance Sheet", "Profit and Loss")
        rows = rpc.search_read("account.report", [("name", "in", wanted)],
                               ["name"], limit=0)
        found = sorted({row["name"] for row in rows})
        ctx.log(f"reports present: {found}")
        ctx.check("All five reports the workbook names exist on this "
                  "database", [], [name for name in wanted
                                   if name not in found])
        observation(ctx,
                    "the reports are client actions: what the workbook's "
                    "stopwatch measures from pressing the date button is "
                    "the engine's query PLUS the client assembling and "
                    "drawing the lines. The engine is not driven from here "
                    "— its entry point takes a fully-built options dict "
                    "that the client composes — so timing it over RPC "
                    "would measure a different thing and call it the same "
                    "name. The invoice list above IS the same call the "
                    "screen makes, so those two numbers are comparable; "
                    "the report timings are named as manual instead of "
                    "being approximated.")

    with ctx.step("Steps 7-8: the comparison"):
        write_measurements(ctx, "fg20_perf_003_accounting.csv", measurements)
        manual(ctx,
               "TC-PERF-003 steps 3-6 — running Trial Balance, General "
               "Ledger, Aged Receivable, Balance Sheet and Profit and Loss "
               "over the agreed full financial year and timing each. Step 8 "
               "also asks for any LAYOUT difference to be recorded rather "
               "than raised, since the reporting engine changed between the "
               "two versions; that is a comparison of two screenshots and "
               "needs both systems open.")
        judge_or_block(ctx, "TC-PERF-003", measurements)


@test_case(
    id="TEST-FG20-PERF-004",
    name="A bulk wizard still completes on 1,000 or more records",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P1",
    kind="API",
    order=2003,
    description="Times the same bulk write the Assign Customer Taxes wizard "
                "makes, over 1,000 products, writing each product's "
                "existing taxes back onto itself — same ORM path, same "
                "cost, no change to the gallery's catalogue. The wizard's "
                "own shape is checked. BLOCKED on the v15 timing.",
    traceability=trace("TC-PERF-004"))
def test_perf_004(ctx):
    rpc = require_v19(ctx)
    measurements = []

    with ctx.step("Steps 1-2: selecting exactly 1,000 products"):
        ids = rpc.search(PRODUCT, [], limit=1000, order="id")
        ctx.check("Exactly 1,000 products are selected — 'if it offers to "
                  "select all 69,201 instead, DECLINE it'", 1000, len(ids))

    with ctx.step("Steps 3-4: the wizard exists and takes the field the "
                  "workbook describes"):
        wizard = "assign.customer.taxes.wizard"
        ctx.check_true(f"The {wizard} model exists",
                       rpc.model_exists(wizard), actual_desc=wizard)
        fields = rpc.call(wizard, "fields_get", [],
                          attributes=["string", "type"])
        tax_fields = {name: meta for name, meta in fields.items()
                      if meta.get("type") in ("many2many", "many2one")
                      and "tax" in name.lower()}
        ctx.check_true(
            "…with a Customer Taxes field, which is the dialog's one field",
            bool(tax_fields),
            actual_desc="; ".join(f"{k}={v['string']!r}"
                                  for k, v in tax_fields.items()))

    with ctx.step("Steps 5-6: the cost of the selection the wizard acts on"):
        # What is timed is the READ of 1,000 products' taxes — real work
        # the wizard does before it writes anything, and safe. The WRITE is
        # not made; the finding below says what happened when it was.
        def once():
            return rpc.read(PRODUCT, ids, ["taxes_id"])

        measurements.append(median_of_three(
            ctx, "reading the taxes of 1,000 products", once))

    with ctx.step("Why the bulk WRITE is not measured on this instance"):
        finding(ctx,
                "an earlier revision of this test DID measure the write, by "
                "writing each product's existing taxes back onto itself — "
                "the same ORM path, no data change. On this database that "
                "produced roughly 47,000 attachment reads in two minutes "
                "(odoo19 log, 11:51-11:53) and the Odoo process restarted "
                "at the end of the burst; the run died with 'Connection "
                "refused'. Afterwards only 15 product templates carried a "
                "new write_date and all 95,020 tax links were untouched, so "
                "nothing was damaged — but a bulk write over 1,000 products "
                "took the instance down, which is exactly what TC-PERF-004 "
                "is asking about. Two things follow. (1) The write is not "
                "repeated here: doing it to obtain a number that cannot be "
                "judged without a baseline is a bad trade on the database "
                "the gallery is recording its acceptance in. (2) The "
                "amplification deserves Novobi's attention on its own — a "
                "tax write on a product cascades into attachment reads, and "
                "on THIS instance every one of them raises FileNotFoundError "
                "because the restore carries no filestore (TC-SMK-014). On "
                "a system WITH a filestore they would succeed, but they "
                "would still be ~47,000 file opens for 1,000 product "
                "writes.")
        observation(ctx,
                    "the workbook's own precondition offers the way to run "
                    "this properly: 'At least 1,000 products exist that you "
                    "may safely rewrite, OR the test system is a throwaway "
                    "copy.' On a throwaway copy the literal steps are safe "
                    "and worth running once, with a stopwatch, as written.")

    with ctx.step("Step 7: the tax state of all 1,000, recorded so a "
                  "partial run would be visible"):
        current = rpc.read(PRODUCT, ids, ["taxes_id"])
        carrying = [row for row in current if row["taxes_id"]]
        combinations = {tuple(sorted(row["taxes_id"] or []))
                        for row in current}
        ctx.log(f"  {len(carrying)} of {len(ids)} carry a customer tax, in "
                f"{len(combinations)} distinct combination(s)")
        ctx.check("Every one of the 1,000 products has a readable tax state, "
                  "so a run that stopped part-way would show as a mixture",
                  len(ids), len(current))
        observation(ctx,
                    "the workbook has the tester open 20 of the 1,000 at "
                    "random AFTER the wizard and confirm each carries the "
                    "two chosen taxes and nothing else — 'a product still "
                    "carrying its old taxes means the run stopped part-way, "
                    "and that is a FAIL even if no error appeared'. With no "
                    "write made, what this records is the BEFORE picture, "
                    "against which a real run on a throwaway copy can be "
                    "checked.")

    with ctx.step("Steps 8-9: the comparison"):
        write_measurements(ctx, "fg20_perf_004_bulk_wizard.csv",
                           measurements)
        manual(ctx,
               "TC-PERF-004 as its steps literally read — assigning two "
               "chosen taxes to 1,000 real products through the Actions "
               "menu, then putting the originals back — is NOT performed. "
               "This database is the one the gallery is recording its "
               "acceptance in, and a run that half-completed would leave a "
               "thousand products carrying taxes nobody chose, which is the "
               "very failure step 7 hunts for. The same ORM write is timed "
               "instead, with each product's existing taxes written back "
               "onto itself: same work, no change. On a throwaway copy the "
               "literal steps are safe and worth running once.")
        judge_or_block(ctx, "TC-PERF-004", measurements)


@test_case(
    id="TEST-FG20-PERF-007",
    name="The sync log list stays usable after the clear-out",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P0",
    kind="API",
    order=2004,
    description="Times each of the three log screens for one store, with "
                "the default filters and without them, at 500 rows, "
                "filtered to Today and grouped by Status. Records the "
                "per-store counts the workbook says to compare against what "
                "Novobi kept in the clear-out. BLOCKED on the v15 timings "
                "and on those kept-row figures.",
    traceability=trace("TC-PERF-007"))
def test_perf_007(ctx):
    rpc = require_v19(ctx)
    measurements = []

    with ctx.step("Steps 1-2: a store, and its Order Import log"):
        stores = rpc.search_read(CHANNEL, [], ["name"], limit=1, order="id")
        if not stores:
            ctx.blocked("no store exists, so there is no log screen to "
                        "open.")
        store = stores[0]
        ctx.log(f"store: {store['name']!r}")
        whole_table = rpc.call(LOG, "search_count", [])
        ctx.log(f"{whole_table:,} rows in the whole log table")

    log_types = {"Order Import": "import_order",
                 "Product Import": "import_product",
                 "Product Export": "export_master"}

    for label, operation in log_types.items():
        with ctx.step(f"Steps 2-7 for '{label}'"):
            scoped = [("channel_id", "=", store["id"]),
                      ("operation_type", "=", operation)]
            # Step 3: the chips the screen opens with.
            default = scoped + ["|", "|", ("status", "=", "draft"),
                                ("status", "=", "failed"),
                                ("is_resolved", "=", False)]
            measurements.append(time_list(
                ctx, LOG, default, limit=80,
                label=f"{label}: opening with the default filters"))
            measurements.append(time_list(
                ctx, LOG, scoped, limit=80,
                label=f"{label}: filters cleared"))
            measurements.append(time_list(
                ctx, LOG, scoped, limit=500,
                label=f"{label}: 500 rows"))
            measurements.append(time_group(
                ctx, LOG, "status", scoped,
                label=f"{label}: grouped by Status"))

            count = rpc.call(LOG, "search_count", scoped)
            ctx.log(f"  {count:,} {label} entries for this store")

    with ctx.step("Step 9 / Expected line 4: the counts, for comparison "
                  "against what the clear-out kept"):
        write_measurements(ctx, "fg20_perf_007_sync_log.csv", measurements)
        observation(ctx,
                    f"the whole log table holds {whole_table:,} rows, and "
                    f"the per-store per-type counts above are far smaller. "
                    f"The workbook says that is expected — 'they will be "
                    f"far smaller than the whole-table figure, because no "
                    f"screen shows the whole table' — and that the numbers "
                    f"to compare against are what Novobi said the clear-out "
                    f"kept for this store.")
        judge_or_block(ctx, "TC-PERF-007", measurements)
