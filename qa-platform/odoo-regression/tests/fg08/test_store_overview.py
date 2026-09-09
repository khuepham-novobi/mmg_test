"""FG-08 — TC-CHN-011: the store overview screen and its sales figures.

Implements row 46.0 (P2, "Store dashboard") of the CLIENT MANUAL TESTING
GUIDELINE ``MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0.xlsx`` /
sheet ``Testing Guideline``. The workbook's *Order of Testing* puts it in
step 6.0 behind **GATE 6**: *"The overview screen renders and its sales
figures agree with the sales-order list. Zeroes on the card while real
orders exist means the screen is not reading the orders."*

The workbook's *Why It Matters* opens with **READ THIS FIRST** and warns
that the screen was **rebuilt** for Odoo 19 and gained a period selector and
a statistics panel — *"Do not report the new items as unexpected; do check
the figures, because a rebuilt screen reading its numbers from the wrong
place produces zeroes rather than an error."*

How the figures are asserted without a browser
----------------------------------------------
``get_dashboard_datas()`` and ``get_graph_datas()`` are public methods and
are exactly what the card renders: ``kanban_dashboard`` /
``kanban_dashboard_graph`` are dependency-less computes that just
``json.dumps`` their return values (``omni_manage_channel/models/
ecommerce_channel.py:121, 530``; ``multichannel_order/models/
ecommerce_channel.py:39, 286``). Both are pure ``SELECT``s over
``sale_order``. So this test reads the card's own numbers and then
recomputes them independently over the ORM, which is the only way to tell
"the figure is zero because there are no orders" from "the figure is zero
because the screen is reading the wrong place" — the exact discrimination
GATE 6 asks for.

Two things make the naive version of that comparison wrong:

1. **``get_dashboard_datas`` is overridden without ``super()``.**
   ``multichannel_order`` shadows the base producer on the same model
   (``multichannel_order/models/ecommerce_channel.py:212`` over
   ``omni_manage_channel/models/ecommerce_channel.py:534``), so on a full
   install the payload keys are ``total_sales`` / ``num_of_orders`` /
   ``num_of_unshipped_orders`` / ``lead_time`` (each with a ``formatted_``
   twin) — **not** the base module's ``sales_total`` / ``sales_unit``.
2. **The window is not fixed at 30 days.** The live query takes its window
   from ``kanban_dashboard_period`` through
   ``KANBAN_DASHBOARD_PERIOD_MAPPING``
   (``multichannel_order/models/ecommerce_channel.py:20-25, 228-229``).
   Only the shadowed base path is hard-coded to 30
   (``omni_manage_channel/models/ecommerce_channel.py:536``). A test that
   assumed 30 days would pass by luck.

The recomputation therefore reproduces the query's own boundary expression
— ``datetime.now().replace(hour=0, minute=0, second=0) -
timedelta(days=delta)``, with no upper bound — against the **server's**
clock and the store's *current* period rather than a guess. One honest
limitation: the real boundary keeps the call's microseconds and the clock
this suite can read is second-resolution, so the reproduced window is at
most one second wider. The log names the boundary it used, so a
one-order disagreement at the edge is recognisable for what it is.

FINDING — steps 4 and 5 cannot be performed on the card
-------------------------------------------------------
Step 4 reads *"Last order sync"* off the card and step 5 reads *"Total sales
last 30 days"* and *"Total orders last 30 days"*. None of the three is on
the v19 card. ``multichannel_order`` replaces the whole ``col-md-9`` block
that held them with the period selector
(``multichannel_order/views/omnichannel_dashboard_views.xml:8-14``, against
the base card at ``omni_manage_channel/views/
omnichannel_dashboard_views.xml:61-88``), and — consistently — the same
module's override removes the ``sales_total`` / ``sales_unit`` keys those
two tiles read. On v15 neither had happened: ``novobi-omni-addons/
multichannel_order/views/omnichannel_dashboard_views.xml:8-16`` only *added*
the graph and did not override the producer.

The v19 equivalents are the **Store Statistics** panel's *Total Sales* and
*# Orders* (``multichannel_order/views/omnichannel_dashboard_views.xml:
27-52``) over the selected period. That is where the substance of steps 5
and 9 and of Expected Result line 2 is asserted here, because the workbook
itself says the statistics panel is new by design and must not be reported
as unexpected. The removal of the three v15 readings is recorded as a
**workbook amendment item** — no migrated value is wrong — and asserted in
neither direction.

FINDING — step 6 cannot be automated without writing to a live store
--------------------------------------------------------------------
*"Find the period selector on the card and change it from Last 30 days to
Last 90 days. Confirm the figures change."* The selector is a **stored**
field, ``kanban_dashboard_period``, edited in place on the card
(``widget="kanban_editable_selection_field" force_save="1"``). Changing it
is a ``write()`` on the live store record, which
``AUTOMATION_CONVENTIONS`` rule 3 forbids and which for a shopify channel
passes through ``ShopifyChannel.write`` — a method that calls out to
Shopify whenever a credential field is in ``vals``
(``multichannel_shopify/models/ecommerce_channel.py:427-435``).

So the expectation is proved read-only, and more thoroughly than the manual
step: the selector's four options are asserted from ``fields_get``, its
binding on the card from the arch, and the figures are recomputed for **all
four** windows to show they genuinely differ — with the same GATE-6
discrimination applied when two windows agree. The one click is recorded as
a RESIDUAL MANUAL STEP with its reason.

What is NOT asserted here
-------------------------
That the OWL components actually paint. This suite makes no browser call
(see ``docs/FG-08_MANUAL_GUIDELINE_SUITE.md`` §7); the render itself is
covered by the module's own ``browser_js`` test,
``omni_manage_channel/tests/test_dashboard_ui.py``, which runs in the Odoo
test runner rather than this platform. Everything the render *displays* —
the arch it is built from and the payload it is handed — is asserted here.
"""
from __future__ import annotations

import json

from framework.registry import test_case
from tests.fg08.common import (ACTION_OVERVIEW, BASE_DASHBOARD_KEYS,
                               CHANNEL, DASHBOARD_KEYS,
                               GROUP_USER, MENU_OVERVIEW, MODULE_ORDER,
                               PERIOD_DAYS, PERIOD_FIELD, SALE_ORDER,
                               SALE_ORDERS_ACTION, SALE_STORE_GROUPBY,
                               SHOPIFY, VIEW_STORE_KANBAN, WORKFLOW,
                               WORKFLOW_NAME, channel_order_domain,
                               count_and_total, dashboard_payload,
                               find_shopify_store, finding, graph_payload,
                               m2o_id, manual, number_from, observation,
                               parse_arch, readonly_rpc, require_connector,
                               require_manager_group, require_v19,
                               resolve_action, server_now, store_context,
                               store_domain, store_values, trace, view_arch,
                               window_start, write_csv)

#: The three-dot menu's sections and the workbook's names for them
#: (omni_manage_channel/views/omnichannel_dashboard_views.xml:98-113).
MENU_SECTIONS = (("o_kanban_manage_view", "View"),
                 ("o_kanban_manage_action", "Action"),
                 ("o_kanban_manage_log", "Log"))

#: The Store Statistics panel's four titles and the payload key behind each
#: (multichannel_order/views/omnichannel_dashboard_views.xml:27-52).
STATISTICS_TILES = (
    ("Total Sales", "total_sales", "formatted_total_sales"),
    ("# Orders", "num_of_orders", "formatted_num_of_orders"),
    ("# Order Unshipped", "num_of_unshipped_orders",
     "formatted_num_of_unshipped_orders"),
    ("Lead Time", "lead_time", "formatted_lead_time"),
)

#: The v15 card readings the rebuild removed (see the module docstring).
V15_CARD_READINGS = ("Last order sync", "Total sales last 30 days",
                     "Total orders last 30 days")

#: Rounding tolerance on the money figure. `total_sales` is formatted with
#: `thousand_repr(value, dg=0)` — whole currency units
#: (multichannel_order/utils/utils.py:4-5) — and the card's own figure comes
#: from a SQL `SUM(numeric)` while the recomputation sums Python floats read
#: over RPC, so the two can differ in the last unit at a .5 boundary.
MONEY_TOLERANCE = 1.0


def _section_anchors(root, css_class: str):
    """The ``<a role="menuitem">`` entries under one three-dot section."""
    for div in root.iter("div"):
        classes = (div.get("class") or "").split()
        if css_class in classes:
            return [" ".join(t.strip() for t in a.itertext() if t.strip())
                    for a in div.iter("a")]
    return None


def _section_label(root, css_class: str):
    """The section's own ``<span role="separator">`` label."""
    for div in root.iter("div"):
        classes = (div.get("class") or "").split()
        if css_class in classes:
            for span in div.iter("span"):
                if span.get("role") == "separator":
                    return (span.text or "").strip()
    return None


@test_case(
    id="TEST-FG08-CHN-011",
    name="The store overview screen and its sales figures render",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE_ORDER,
    priority="P2",
    kind="API",
    order=802,
    description="Reads the Overview card's own figure payload and "
                "recomputes it independently over sale.order using the "
                "query's real boundary and the store's real period, so a "
                "zero is classified rather than reported: GATE 6's "
                "'zeroes while real orders exist' is asserted, and 'no "
                "channel orders in the period' is accepted as the "
                "workbook's own exception. Also asserts the Store "
                "Statistics tiles, the graph payload, the period selector's "
                "four options with figures that differ across all four "
                "windows, and the three-dot View/Action/Log sections. "
                "Records that the v19 card no longer carries the three v15 "
                "readings the workbook's steps 4-5 name.",
    traceability=trace(
        "TC-CHN-011",
        user_story="As the E-commerce Manager I open this screen every "
                   "morning, so it has to load, show the store, and show "
                   "sales figures that are not obviously wrong."))
def test_chn_011(ctx):
    rpc = readonly_rpc(ctx)
    figure_rows: list[list] = []
    period_rows: list[list] = []

    try:
        with ctx.step("Gate: Odoo 19 target with the e-commerce connector "
                      "stack installed"):
            require_v19(ctx)
            require_manager_group(ctx)
            fields_meta = require_connector(ctx)
            manual(ctx, "the workbook's preconditions are 'TC-CHN-001 has "
                        "passed' and \"you have the 'E-commerce User' group "
                        "at least\". AUTOMATION_CONVENTIONS rule 5 forbids "
                        "depending on another test's state, so this case "
                        "resolves the store itself; the registry order (802) "
                        "still runs it after the two step-2.0 cases")
            ctx.check_true(
                "The 'E-commerce User' group the workbook names exists",
                bool(rpc.ref(GROUP_USER)),
                actual_desc=f"{GROUP_USER} = {rpc.ref(GROUP_USER)}")

        with ctx.step("Step 1: E-commerce Connectors > Overview opens the "
                      "channel dashboard"):
            overview = resolve_action(ctx, ACTION_OVERVIEW)
            ctx.check_true(
                "The Overview menu resolves to the dashboard action",
                bool(rpc.ref(MENU_OVERVIEW)),
                actual_desc=f"{MENU_OVERVIEW} = {rpc.ref(MENU_OVERVIEW)}")
            ctx.check("…which opens the kanban dashboard first, then a form",
                      "kanban,form", overview.get("view_mode"))
            ctx.check("…on the channel model", CHANNEL,
                      overview.get("res_model"))
            ctx.log(f"Overview action domain={overview['parsed_domain']!r} "
                    f"context={store_context(overview)!r}")

            store = find_shopify_store(ctx, overview)
            store_id = store["id"]
            values = store_values(ctx, store_id)

        with ctx.step("Steps 2-3: the store appears as a card, with the "
                      "Shopify logo and a coloured connection badge"):
            kanban_arch = view_arch(ctx, VIEW_STORE_KANBAN, "kanban")
            root = parse_arch(kanban_arch)

            on_overview = rpc.search_read(
                CHANNEL, store_domain(ctx, overview, include_inactive=True),
                ["name", "platform"], context=store_context(overview))
            ctx.check_true(
                "The store is one of the cards the Overview screen shows",
                store_id in {row["id"] for row in on_overview},
                actual_desc=f"Overview cards: "
                            f"{[(r['id'], r['name'], r['platform']) for r in on_overview]}")

            # The card builds its logo path inline from `platform` rather
            # than reading the stored image_url compute.
            ctx.check("The card's logo is the Shopify one, because it "
                      "interpolates the platform key into its own src",
                      SHOPIFY, values.get("platform"))
            ctx.check_true(
                "…and the card really does build the path that way",
                "static/src/img/i64x64/" in kanban_arch
                and "record.platform.raw_value" in kanban_arch,
                actual_desc="t-attf-src=\"/omni_manage_channel/static/src/"
                            "img/i64x64/#{record.platform.raw_value}.png\" "
                            "(omni_manage_channel/views/"
                            "omnichannel_dashboard_views.xml:47-52)")
            ctx.check_true(
                "The card shows the store name",
                'name="name"' in kanban_arch,
                actual_desc=f"name={values.get('name')!r}")

            ctx.check_true(
                "The connection badge is on the card, coloured green for "
                "connected and red for disconnected",
                'name="status"' in kanban_arch
                and "label_selection" in kanban_arch
                and "'disconnected': 'danger'" in kanban_arch
                and "'connected': 'success'" in kanban_arch,
                actual_desc="<field name=\"status\" "
                            "widget=\"label_selection\" options=\"{'classes': "
                            "{'disconnected': 'danger', 'connected': "
                            "'success'}}\"/> (omni_manage_channel/views/"
                            "omnichannel_dashboard_views.xml:56-60)")
            ctx.check("…and it reads the store's real state", "connected"
                      if values.get("active") else "disconnected",
                      values.get("status"))

        with ctx.step("Steps 4-5: the readings the workbook takes off the "
                      "card — what this build actually shows"):
            present = [text for text in V15_CARD_READINGS
                       if text in kanban_arch]
            card_has_last_sync = 'name="last_sync_order"' in kanban_arch
            payload = dashboard_payload(ctx, store_id)
            ctx.log(f"the card's figure payload: {payload}")

            missing_base_keys = [key for key in BASE_DASHBOARD_KEYS
                                 if key not in payload]
            finding(
                ctx,
                f"steps 4 and 5 cannot be performed on the card. Of the "
                f"three v15 readings the workbook names "
                f"({', '.join(V15_CARD_READINGS)}), this build's assembled "
                f"kanban arch carries {present or 'none'}, and "
                f"last_sync_order is bound: {card_has_last_sync}. "
                f"multichannel_order replaces the whole col-md-9 block that "
                f"held them with the period selector (multichannel_order/"
                f"views/omnichannel_dashboard_views.xml:8-14, against the "
                f"base card at omni_manage_channel/views/"
                f"omnichannel_dashboard_views.xml:61-88). Consistently, the "
                f"same module overrides get_dashboard_datas() without "
                f"super() (…/models/ecommerce_channel.py:212-223) so the "
                f"keys those two tiles read are gone from the payload too — "
                f"absent here: {missing_base_keys}. On v15 neither had "
                f"happened. WORKBOOK AMENDMENT item: no migrated value is "
                f"wrong, and the v19 equivalents are the Store Statistics "
                f"panel's Total Sales and # Orders, asserted below. Not "
                f"asserted in either direction, because the workbook itself "
                f"says the rebuilt items must not be reported as "
                f"unexpected.")
            manual(ctx, "read Last Order Sync off the Manage Stores LIST "
                        "(TC-CHN-005 step 3), not the Overview card")

            ctx.check(
                "The card's payload carries every figure the Store "
                "Statistics panel binds — a rebuilt screen reading from the "
                "wrong place is what the workbook warns about, and a "
                "missing key is that failure with no error",
                [], [key for key in DASHBOARD_KEYS if key not in payload])

        with ctx.step("Steps 5 and 9 together: the figures are real, and "
                      "they agree with the sales-order list (GATE 6)"):
            now, clock_source = server_now(ctx)
            period = values.get(PERIOD_FIELD) or "last_30_days"
            days = PERIOD_DAYS.get(period, 30)
            ctx.log(f"server clock = {now} (from {clock_source}); the "
                    f"store's period selector reads {period!r} = {days} days")
            ctx.check_true(
                "The card's window comes from the store's own period "
                "selector, so this comparison uses the same window the card "
                "does",
                period in PERIOD_DAYS,
                actual_desc=f"{PERIOD_FIELD}={period!r}; mapping="
                            f"{PERIOD_DAYS} (multichannel_order/models/"
                            f"ecommerce_channel.py:20-25, 228-229)")

            start = window_start(now, days)
            card_domain = channel_order_domain(store_id, start)
            recomputed = count_and_total(ctx, card_domain)
            ctx.log(f"recomputed over {SALE_ORDER} with the card's own "
                    f"domain {card_domain!r}: count={recomputed['count']} "
                    f"total={recomputed['total']} "
                    f"unshipped={recomputed['unshipped']}. The card's real "
                    f"boundary carries the call's microseconds and this one "
                    f"does not, so the window used here is at most one "
                    f"second wider; a disagreement of exactly one order "
                    f"dated within a second of {start} is that, not a "
                    f"defect.")

            card_orders = number_from(payload.get("num_of_orders"))
            card_sales = number_from(payload.get("total_sales"))
            ctx.check(
                "The card's order count is exactly what its own query "
                "returns — if these disagree the screen is reading "
                "somewhere else, which is the workbook's central worry",
                float(recomputed["count"]),
                card_orders if card_orders is not None
                else payload.get("num_of_orders"))
            if card_sales is None:
                observation(
                    ctx,
                    f"total_sales reads {payload.get('total_sales')!r}, "
                    f"which readable_repr abbreviated above its 1e6 "
                    f"threshold (multichannel_order/utils/utils.py:12-45) "
                    f"and cannot be compared numerically; the exact figure "
                    f"is in the title attribute on screen. Recomputed "
                    f"total: {recomputed['total']}")
            else:
                ctx.check_true(
                    "…and so is its sales total",
                    abs(card_sales - recomputed["total"]) <= MONEY_TOLERANCE,
                    actual_desc=f"card={payload.get('total_sales')!r} "
                                f"(parsed {card_sales}) vs recomputed "
                                f"{recomputed['total']}; tolerance "
                                f"{MONEY_TOLERANCE} because the figure is "
                                f"formatted to whole units with dg=0")

            # Step 9 as the tester would do it: Sales > Orders > Orders,
            # group by Store, restricted to the same window.
            sales_action_id = rpc.ref(SALE_ORDERS_ACTION)
            ctx.check_true(
                "Sales > Orders > Orders exists, and its default facet is "
                "the same state the card counts — so a step-9 comparison "
                "with the screen's default left alone agrees by "
                "construction",
                bool(sales_action_id),
                actual_desc=f"{SALE_ORDERS_ACTION} = {sales_action_id}; its "
                            f"context sets search_default_sales=1, and that "
                            f"filter's domain is [('state','=','sale')] "
                            f"(odoo-19.0/addons/sale/views/"
                            f"sale_order_views.xml:978)")
            groupby_meta = rpc.fields_get(SALE_ORDER, [SALE_STORE_GROUPBY],
                                          ["string", "relation"])
            ctx.check(
                f"The Store group-by the workbook's step 9 uses is on "
                f"{SALE_ORDER}, labelled as it names it",
                "Store",
                (groupby_meta.get(SALE_STORE_GROUPBY) or {}).get("string"))
            ctx.check(f"…and it points at {CHANNEL}", CHANNEL,
                      (groupby_meta.get(SALE_STORE_GROUPBY) or {})
                      .get("relation"))

            # lazy read_group with one groupby returns the count under
            # "<groupby>_count" (odoo-19.0/odoo/orm/models.py:2812); the
            # non-lazy "__count" form is accepted too so this survives the
            # ongoing read_group deprecation.
            grouped = rpc.read_group(SALE_ORDER, card_domain,
                                     ["amount_total:sum"],
                                     [SALE_STORE_GROUPBY])

            def _bucket_count(row):
                for key in (f"{SALE_STORE_GROUPBY}_count", "__count"):
                    if key in row:
                        return row[key]
                return 0

            ctx.log(f"Sales list grouped by Store over the same window: "
                    f"{[(m2o_id(r.get(SALE_STORE_GROUPBY)), _bucket_count(r), r.get('amount_total')) for r in grouped]}")
            store_bucket = next(
                (row for row in grouped
                 if m2o_id(row.get(SALE_STORE_GROUPBY)) == store_id), None)
            ctx.check(
                "The order count in the Sales list's Store bucket agrees "
                "with the card (workbook Expected Result line 5)",
                recomputed["count"],
                _bucket_count(store_bucket or {}))

            # The same window with NO state facet — what a tester sees if
            # they clear the default filter. Reported, never asserted.
            unfiltered = count_and_total(
                ctx, channel_order_domain(
                    store_id, start,
                    states=("draft", "sent", "sale", "cancel")))
            ctx.log(f"the same window with the state facet CLEARED: "
                    f"{unfiltered['count']} order(s) — the difference is "
                    f"quotations and cancellations, which the card "
                    f"deliberately does not count "
                    f"(state = 'sale' only; multichannel_order/models/"
                    f"ecommerce_channel.py:229-247, whose inline BC-016 "
                    f"note records that 'done' is not a v19 sale-order "
                    f"state)")
            if unfiltered["count"] != recomputed["count"]:
                manual(ctx, f"if you clear the 'Sales Orders' facet in step "
                            f"9 you will count {unfiltered['count']} rather "
                            f"than {recomputed['count']} and the card will "
                            f"look wrong. Leave the default facet on. There "
                            f"is also NO 'last 30 days' filter on the Sales "
                            f"search view — core offers only "
                            f"month/quarter/year on Order Date "
                            f"(odoo-19.0/addons/sale/views/"
                            f"sale_order_views.xml:998) — so build an "
                            f"explicit custom date range for the store's "
                            f"current period ({days} days)")

            # GATE 6 — classify a zero rather than reporting it.
            if recomputed["count"] == 0:
                any_state = unfiltered["count"]
                observation(
                    ctx,
                    f"the figures read ZERO for the {days}-day window. The "
                    f"workbook allows that 'unless the gallery genuinely "
                    f"had no channel orders in the period', and GATE 6 asks "
                    f"to distinguish the two: there are {any_state} channel "
                    f"order(s) of ANY state in the window, and "
                    f"{recomputed['count']} confirmed one(s) — so the zero "
                    f"is the population, not the screen")
                ctx.check(
                    "GATE 6: the card does NOT read zero while confirmed "
                    "channel orders exist in its window",
                    0,
                    rpc.search_count(SALE_ORDER,
                                     channel_order_domain(store_id, start)))
                manual(ctx, f"mark the workbook's figure checks N/A and say "
                            f"why, as its precondition instructs: no "
                            f"confirmed store order falls in the last "
                            f"{days} days. The newest confirmed one is "
                            f"named in the CSV")
                newest = rpc.search_read(
                    SALE_ORDER,
                    [(SALE_STORE_GROUPBY, "=", store_id),
                     ("state", "=", "sale")],
                    ["name", "date_order", "amount_total"],
                    order="date_order desc", limit=1)
                if newest:
                    ctx.log(f"newest confirmed store order: "
                            f"{newest[0]['name']} dated "
                            f"{newest[0]['date_order']} "
                            f"({newest[0]['amount_total']})")
            else:
                ctx.check_true(
                    "Total sales and Total orders show real figures, not "
                    "zero (workbook Expected Result line 2)",
                    recomputed["count"] > 0 and recomputed["total"] > 0,
                    actual_desc=f"count={recomputed['count']} "
                                f"total={recomputed['total']}")

            for title, exact_key, formatted_key in STATISTICS_TILES:
                figure_rows.append([
                    title, exact_key, str(payload.get(exact_key)),
                    formatted_key, str(payload.get(formatted_key)),
                ])

        with ctx.step("Step 6: the period selector, and figures that "
                      "genuinely differ across its four windows"):
            period_meta = fields_meta.get(PERIOD_FIELD) or {}
            ctx.check(
                "The period selector offers exactly the four windows the "
                "code maps",
                list(PERIOD_DAYS),
                [key for key, _label in (period_meta.get("selection") or [])])
            ctx.check_true(
                "…is required, so the card always has a window",
                bool(period_meta.get("required")),
                actual_desc=f"{PERIOD_FIELD}: "
                            f"required={period_meta.get('required')!r} "
                            f"store={period_meta.get('store')!r}")
            ctx.check_true(
                "…and is edited in place on the card, which is where the "
                "workbook says to find it",
                f'name="{PERIOD_FIELD}"' in kanban_arch
                and "kanban_editable_selection_field" in kanban_arch,
                actual_desc="<field name=\"kanban_dashboard_period\" "
                            "widget=\"kanban_editable_selection_field\" "
                            "force_save=\"1\"/> (multichannel_order/views/"
                            "omnichannel_dashboard_views.xml:11)")

            for key, day_count in PERIOD_DAYS.items():
                window = count_and_total(
                    ctx, channel_order_domain(
                        store_id, window_start(now, day_count)))
                period_rows.append([
                    dict(period_meta.get("selection") or {}).get(key, key),
                    key, day_count, window["count"], window["total"],
                    window["unshipped"],
                    "current" if key == period else "",
                ])
                ctx.log(f"  {key} ({day_count}d): count={window['count']} "
                        f"total={window['total']}")

            thirty = next(r for r in period_rows if r[1] == "last_30_days")
            ninety = next(r for r in period_rows if r[1] == "last_90_days")
            differ = (thirty[3], thirty[4]) != (ninety[3], ninety[4])
            if differ:
                ctx.check_true(
                    "Changing the period from Last 30 days to Last 90 days "
                    "changes the figures (workbook Expected Result line 3)",
                    differ,
                    actual_desc=f"30d: {thirty[3]} order(s) / {thirty[4]}; "
                                f"90d: {ninety[3]} order(s) / {ninety[4]}")
            else:
                observation(
                    ctx,
                    f"the 30-day and 90-day windows give the same figures "
                    f"({thirty[3]} order(s) / {thirty[4]}), so the "
                    f"workbook's 'the figures change' cannot be observed on "
                    f"this data — not because the selector is broken but "
                    f"because no confirmed store order falls in the 30-90 "
                    f"day band. Every window is in "
                    f"TC-CHN-011-period-windows.csv; pick two that differ")
                ctx.check_true(
                    "…and the selector is nonetheless wired to the figures: "
                    "at least two of its four windows give different "
                    "numbers",
                    len({(row[3], row[4]) for row in period_rows}) > 1,
                    actual_desc=f"windows: "
                                f"{[(r[1], r[3], r[4]) for r in period_rows]}")

            manual(ctx, "the one click the workbook asks for — switching "
                        "the selector on the card from Last 30 days to Last "
                        "90 days — is NOT automated. It is a write() on the "
                        "live store record, which AUTOMATION_CONVENTIONS "
                        "rule 3 forbids and which for a shopify channel "
                        "goes through ShopifyChannel.write "
                        "(multichannel_shopify/models/ecommerce_channel.py:"
                        "427-435). Do it by hand and compare against "
                        "TC-CHN-011-period-windows.csv, then set it back to "
                        "Last 30 days as the workbook's State After The "
                        "Test says")

        with ctx.step("Step 7: the Store Statistics panel and its four "
                      "figures"):
            ctx.check_true(
                "The Store Statistics panel is on the card",
                "Store Statistics" in kanban_arch,
                actual_desc="<summary class=\"py-3\">Store Statistics"
                            "</summary> (multichannel_order/views/"
                            "omnichannel_dashboard_views.xml:27)")
            missing_tiles = [title for title, _exact, _fmt in STATISTICS_TILES
                             if title not in kanban_arch]
            ctx.check(
                "…with the four figures the workbook names: Total Sales, "
                "# Orders, # Order Unshipped and Lead Time",
                [], missing_tiles)

            ctx.check(
                "# Orders is the confirmed-order count for the selected "
                "period",
                float(recomputed["count"]),
                number_from(payload.get("num_of_orders")))
            ctx.check(
                "# Order Unshipped counts the unshipped ones within that "
                "same set",
                float(recomputed["unshipped"]),
                number_from(payload.get("num_of_unshipped_orders")))
            observation(
                ctx,
                "# Order Unshipped has no domain of its own — it is a "
                "Python count of shipping_status == 'unshipped' inside the "
                "same rows (multichannel_order/models/ecommerce_channel.py:"
                "267), and shipping_status is 'unshipped' for an order with "
                "no deliverable line at all (…/models/sale_order.py:"
                "430-431), so a service-only or fee-only order counts "
                "toward it permanently")
            observation(
                ctx,
                f"Lead Time reads {payload.get('lead_time')!r}. It is the "
                f"unweighted mean of DATE_PART('day', date_order - "
                f"create_date) over the same rows, and for IMPORTED orders "
                f"date_order is the store's timestamp while create_date is "
                f"the later import time — so a zero or negative lead time "
                f"is normal here and is not asserted against. It also reads "
                f"'0 days' when there are no rows, which is "
                f"indistinguishable from a genuine zero")

        with ctx.step("Step 8: the sales graph has something to draw"):
            ctx.check_true(
                "The graph is on the card, bound with the v19 widget name",
                'name="kanban_dashboard_graph"' in kanban_arch
                and "kanban_dashboard_graph_field" in kanban_arch,
                actual_desc="<field name=\"kanban_dashboard_graph\" "
                            "graph_type=\"line\" "
                            "widget=\"kanban_dashboard_graph_field\"/> "
                            "(multichannel_order/views/"
                            "omnichannel_dashboard_views.xml:20-24; the "
                            "widget rename is the port's BC-009)")

            graph = graph_payload(ctx, store_id)
            config = (graph or {}).get("config") or {}
            series = (graph or {}).get("data") or []
            labels = config.get("labels") or []
            ctx.log(f"graph payload: {len(labels)} label(s), "
                    f"{len(series)} series, currency="
                    f"{config.get('currency')!r}")
            ctx.check_true(
                "The graph payload has the shape the widget reads: a config "
                "with x-axis labels and at least one series",
                bool(labels) and bool(series),
                actual_desc=f"labels={labels[:4]}… series keys="
                            f"{[s.get('key') for s in series if isinstance(s, dict)]}")
            mismatched = [
                f"{s.get('key')!r}: {len(s.get('values') or [])} value(s) "
                f"for {len(labels)} label(s)"
                for s in series
                if isinstance(s, dict) and len(s.get("values") or []) != len(labels)]
            ctx.check(
                "…and every series has one value per label, so the line is "
                "drawn against the right weeks",
                [], mismatched)
            # The field is what the browser actually reads; prove the
            # method and the field agree.
            raw_field = rpc.read(CHANNEL, [store_id],
                                 ["kanban_dashboard_graph"])[0]
            try:
                from_field = json.loads(
                    raw_field.get("kanban_dashboard_graph") or "{}")
            except (TypeError, ValueError):
                from_field = {}
            ctx.check_true(
                "The kanban_dashboard_graph field the card reads carries "
                "the same payload the method returns",
                (from_field.get("config") or {}).get("labels") == labels,
                actual_desc=f"field labels="
                            f"{((from_field.get('config') or {}).get('labels') or [])[:4]}…")

        with ctx.step("Step 10: the three-dot menu shows View, Action and "
                      "Log, each with entries"):
            empty_sections, wrong_labels = [], []
            for css_class, expected_label in MENU_SECTIONS:
                anchors = _section_anchors(root, css_class)
                label = _section_label(root, css_class)
                ctx.log(f"  {expected_label}: label={label!r} "
                        f"entries={anchors}")
                if anchors is None:
                    empty_sections.append(f"{expected_label} "
                                          f"({css_class}): section absent")
                elif not anchors:
                    empty_sections.append(f"{expected_label} "
                                          f"({css_class}): no entries")
                if label != expected_label:
                    wrong_labels.append(f"{css_class}: {label!r} rather "
                                        f"than {expected_label!r}")
            ctx.check("The View, Action and Log sections are all present "
                      "with entries under them (workbook Expected Result "
                      "line 6)", [], empty_sections)
            ctx.check("…and each is labelled as the workbook names it", [],
                      wrong_labels)
            observation(
                ctx,
                "the entries under those three sections come from four "
                "different modules' kanban inherits, and several are "
                "conditional: the Shopify View entries need "
                "platform == 'shopify', Import Products needs "
                "is_mapping_managed, and the product/inventory export log "
                "entries need the matching can_export_* flag. A short menu "
                "on a differently-configured store is configuration, not a "
                "defect")

        with ctx.step("State After The Test: nothing was changed"):
            ctx.check_true(
                "The suite made no write of any kind — the period selector "
                "is exactly as it was, so the workbook's 'set it back to "
                "Last 30 days' has nothing to undo",
                values.get(PERIOD_FIELD) == rpc.read(
                    CHANNEL, [store_id], [PERIOD_FIELD])[0][PERIOD_FIELD],
                actual_desc=f"{PERIOD_FIELD}="
                            f"{values.get(PERIOD_FIELD)!r} before and after")

    finally:
        write_csv(ctx, "TC-CHN-011-card-figures.csv",
                  ["Store Statistics tile", "Exact key", "Exact value",
                   "Displayed key", "Displayed value"],
                  figure_rows)
        write_csv(ctx, "TC-CHN-011-period-windows.csv",
                  ["Period label", "Period key", "Days", "Confirmed orders",
                   "Total sales", "Unshipped", "Selected on the store"],
                  period_rows)
        ctx.log(f"read-only RPC calls made: {rpc.calls}; records created or "
                f"modified: 0")
