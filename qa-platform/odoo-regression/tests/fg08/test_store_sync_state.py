"""FG-08 — TC-CHN-005: the store's connection state and last-sync time.

Implements row 45.0 (P1, "Store setup") of the CLIENT MANUAL TESTING
GUIDELINE ``MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0.xlsx`` /
sheet ``Testing Guideline``. The workbook's own *Order of Testing* puts it
in step 2.0 alongside TC-CHN-001, behind **GATE 2**.

The workbook's framing: *"The connector decides what to pull next from the
last-sync time. If it came across blank or reset, the next sync either
re-imports history or skips a gap of real orders."* Its *If It Fails*: *"A
BLANK Last Order Sync is the most serious version — raise it before
go-live, because the first sync will then decide for itself where to
start."*

The two values, and why reading them is safe
--------------------------------------------
* **Status** is ``ecommerce.channel.status``, a Selection
  ``connected/disconnected`` that is **computed** — and computed from
  nothing but ``active``::

      def _get_status(self):
          for record in self:
              record.with_context(for_channel_creation=True).status = \\
                  'connected' if record.active else 'disconnected'

  (``omni_manage_channel/models/ecommerce_channel.py:311-313``; byte-identical
  to v15's ``novobi-omni-addons/omni_manage_channel/models/
  ecommerce_channel.py:222-224``.) So reading Status does **not** probe
  Shopify. What probes Shopify is ``reconnect()`` /
  ``button_check_connection()``, which this suite cannot call.

  It is easy to read the wrong field here: ``is_sync`` is a *different*
  Selection on the same model, labelled **Sync Data**
  (``…/ecommerce_channel.py:78``), and on the MMG restore it is NULL. It is
  not the Status column; the list view binds ``status``
  (``omni_manage_channel/views/ecommerce_channel_views.xml:32-35``).

* **Last Order Sync** is ``last_sync_order``, a stored Datetime carrying
  ``default=fields.Datetime.now`` (``…/ecommerce_channel.py:83``) — which is
  exactly why the workbook says the value must not be *today's* date. Three
  code paths stamp it to "now": ``reconnect()`` (``…:329-338``),
  ``enable_auto_import_data()`` (``…:588-593``) and the order-import
  completion path. A fresh-looking value therefore means something
  re-stamped it, not that a sync legitimately happened at the cut-off.

Both the Manage Stores list and the Overview card are the *same* two fields
on the *same* single record, so "the card and the list agree with each
other" is not a data question — it is a question about what each view
binds. Which is where this case runs into the v19 rebuild.

FINDING — the Overview card no longer shows Last Order Sync
-----------------------------------------------------------
Step 5 says: *"Go to E-commerce Connectors > Overview and read the same two
values off the store's card, plus the Total sales and Total orders tiles."*
On this build the card shows neither.

The base kanban card had a ``col-md-9`` block holding **Last order sync**,
**Total sales last 30 days** and **Total orders last 30 days**
(``omni_manage_channel/views/omnichannel_dashboard_views.xml:61-88``).
``multichannel_order`` **replaces that whole block** with the period
selector::

    <xpath expr="//div[hasclass('o_kanban_card_header_title')]/div[hasclass('row')]/div[hasclass('col-md-9')]"
           position="replace">

(``multichannel_order/views/omnichannel_dashboard_views.xml:8-14``.) The
``col-md-3`` sibling holding the connection badge survives, so **Status is
still on the card** — only Last Order Sync and the two tiles are gone.

That is not an accident of layout: the same module newly overrides
``get_dashboard_datas()`` without calling ``super()``
(``multichannel_order/models/ecommerce_channel.py:212-223``), so the
``sales_total`` / ``sales_unit`` keys those two tiles read
(``omni_manage_channel/models/ecommerce_channel.py:568-571``) are no longer
in the payload either. The removal and the payload change agree with each
other; on v15 neither had happened —
``novobi-omni-addons/multichannel_order`` only *added* the graph
(``…/omnichannel_dashboard_views.xml:8-16``) and did not override the
producer.

So the *substance* of step 6 ("the card and the list agree") is asserted
here on the record and on what each view binds, and the removal is recorded
as a **workbook amendment item** with its source — not inverted into a
pass, and not reported as a data-migration defect, because no migrated
value is wrong. TC-CHN-011 carries the same finding for the two figure
tiles.
"""
from __future__ import annotations

from framework.registry import test_case
from tests.fg08.common import (ACTION_MANAGE_STORES, ACTION_OVERVIEW,
                               CHANNEL, MENU_MANAGE_STORES, MENU_OVERVIEW,
                               MODULE, PERIOD_FIELD, SHOPIFY,
                               STATUS_CONNECTED, STATUS_DISCONNECTED,
                               VIEW_STORE_KANBAN, VIEW_STORE_LIST,
                               VIEW_STORE_SEARCH, WORKFLOW, WORKFLOW_NAME,
                               as_date, channel_fields, dashboard_payload,
                               find_shopify_store, finding, list_columns,
                               m2o_id, manual, observation, readonly_rpc,
                               require_connector, require_manager_group,
                               require_v19,
                               resolve_action, search_filters, server_now,
                               store_context, store_domain, store_values,
                               trace, view_arch, write_csv)

#: The Connected filter's name in the search view, and the ``search_default_``
#: key both actions set (omni_manage_channel/views/
#: ecommerce_channel_views.xml:47-48; the actions set it at :13 and :57).
CONNECTED_FILTER = "connected"
CONNECTED_SEARCH_DEFAULT = "search_default_connected"

#: The three "last …" datetimes on the model. The workbook names only the
#: first; the other two are reported so a printout showing them is not read
#: as a mismatch against the wrong field.
LAST_SYNC_FIELDS = (
    ("last_sync_order", "Last Order Sync",
     "what the next order import reads to decide where to start"),
    ("last_sync_product", "Last Sync",
     "product import; stamped by done_synching "
     "(omni_manage_channel/models/ecommerce_channel.py:466-477)"),
    ("last_all_inventory_sync", "Last all inventory updated",
     "nightly/bulk inventory sync (multichannel_fulfillment/models/"
     "ecommerce_channel.py:26, 237-250)"),
)

#: Card strings the v19 rebuild removed. Asserted against the ASSEMBLED
#: kanban arch, which is what the browser is handed.
V15_CARD_READINGS = ("Last order sync", "Total sales last 30 days",
                     "Total orders last 30 days")


@test_case(
    id="TEST-FG08-CHN-005",
    name="The store's connection state and last-sync time are preserved",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P1",
    kind="DATA",
    order=801,
    description="Reads Status and Last Order Sync off the Manage Stores "
                "list the way the screen resolves them, asserts Last Order "
                "Sync is neither blank nor today's date (against the "
                "SERVER's clock), reproduces 'clear the Connected filter' "
                "through the filter's own domain and asserts no template, "
                "platform-less or duplicate store row appears, and checks "
                "what the list and the Overview card each bind. Records the "
                "v19 finding that the card no longer displays Last Order "
                "Sync or the two figure tiles at all.",
    traceability=trace(
        "TC-CHN-005",
        user_story="As the E-commerce Manager I need the store's connection "
                   "state and last-sync time to have come across exactly, "
                   "because the first sync after go-live reads them to "
                   "decide what to pull — and a blank value lets it decide "
                   "for itself."))
def test_chn_005(ctx):
    rpc = readonly_rpc(ctx)
    baseline_rows: list[list] = []
    store_rows: list[list] = []

    try:
        with ctx.step("Gate: Odoo 19 target with the e-commerce connector "
                      "stack installed"):
            require_v19(ctx)
            require_manager_group(ctx)
            fields_meta = require_connector(ctx)
            manual(ctx, "the workbook's precondition is 'TC-CHN-001 has "
                        "passed'. AUTOMATION_CONVENTIONS rule 5 forbids "
                        "depending on another test's state, so this case "
                        "resolves the store itself; the registry order (801) "
                        "still runs it straight after TEST-FG08-CHN-001")
            manual(ctx, "the workbook's other precondition is the Novobi "
                        "baseline: 'the store's Status and Last Order Sync "
                        "from the old system, read at the upgrade cut-off'. "
                        "The platform does not hold it — the two v19 values "
                        "are captured into TC-CHN-005-sync-state.csv with a "
                        "blank Baseline column to fill in")

        with ctx.step("Steps 1-2: open Manage Stores and read the Status "
                      "column — the field, the widget, and where the value "
                      "comes from"):
            action = resolve_action(ctx, ACTION_MANAGE_STORES)
            ctx.check_true(
                "The Manage Stores menu resolves to this action",
                bool(rpc.ref(MENU_MANAGE_STORES)),
                actual_desc=f"{MENU_MANAGE_STORES} = "
                            f"{rpc.ref(MENU_MANAGE_STORES)}, "
                            f"{ACTION_MANAGE_STORES} = "
                            f"{rpc.ref(ACTION_MANAGE_STORES)}")

            list_arch = view_arch(ctx, VIEW_STORE_LIST, "list")
            columns = list_columns(list_arch)
            ctx.log(f"Manage Stores list columns: {columns}")
            ctx.check(
                "The list carries exactly the columns the workbook reads: "
                "the store, its Status and its Last Order Sync",
                ["logo_and_name", "status", "last_sync_order"],
                [name for name, _string, _widget in columns])

            status_meta = fields_meta.get("status") or {}
            ctx.check(
                "The 'Status' column is ecommerce.channel.status, whose "
                "values are Connected / Disconnected",
                [STATUS_CONNECTED, STATUS_DISCONNECTED],
                [key for key, _label in (status_meta.get("selection") or [])])
            ctx.check_true(
                "…and it is COMPUTED, not stored — so reading it cannot "
                "probe the store",
                not status_meta.get("store", False),
                actual_desc=f"status: store={status_meta.get('store')!r} "
                            f"readonly={status_meta.get('readonly')!r} "
                            f"(_get_status returns 'connected' if active "
                            f"else 'disconnected' — omni_manage_channel/"
                            f"models/ecommerce_channel.py:311-313)")
            is_sync_meta = fields_meta.get("is_sync") or {}
            is_sync_keys = [key for key, _label
                            in (is_sync_meta.get("selection") or [])]
            observation(
                ctx,
                f"do not read 'Sync Data' by mistake: is_sync is a separate "
                f"Selection on the same model "
                f"(string={is_sync_meta.get('string')!r}, "
                f"values={is_sync_keys}) and is not what the Status column "
                f"binds. On the MMG restore it is empty, which is not a "
                f"connection problem")

            store = find_shopify_store(ctx, action)
            store_id = store["id"]
            values = store_values(ctx, store_id)
            status = values.get("status")
            ctx.log(f"Status column reads {status!r}; active="
                    f"{values.get('active')!r}")
            ctx.check(
                "Status is consistent with the only input its compute has "
                "(active) — a disagreement would mean a stale value, not a "
                "connection problem",
                STATUS_CONNECTED if values.get("active")
                else STATUS_DISCONNECTED,
                status)
            baseline_rows.append(
                ["Status", "status", str(status), "",
                 "computed from active; Connected == active"])

        with ctx.step("Step 3: read Last Order Sync — not blank, and not "
                      "today's date"):
            now, clock_source = server_now(ctx)
            ctx.log(f"server clock = {now} (from {clock_source})")

            raw = values.get("last_sync_order")
            ctx.log(f"Last Order Sync reads {raw!r}")
            ctx.check_true(
                "Last Order Sync is not blank — the workbook calls a blank "
                "value the most serious version, because the first sync "
                "then decides for itself where to start",
                bool(raw), actual_desc=f"last_sync_order={raw!r}")

            sync_date = as_date(raw)
            today = now.date() if now else None
            ctx.check_true(
                "Last Order Sync is not today's date",
                bool(sync_date) and bool(today) and sync_date != today,
                actual_desc=f"last_sync_order date={sync_date}, server "
                            f"today={today}. The field carries "
                            f"default=fields.Datetime.now "
                            f"(omni_manage_channel/models/"
                            f"ecommerce_channel.py:83) and is re-stamped to "
                            f"now by reconnect() (…:329-338) and "
                            f"enable_auto_import_data() (…:588-593), so a "
                            f"today value means something re-stamped it "
                            f"rather than a sync having happened at the "
                            f"cut-off")
            if sync_date and today and sync_date > today:
                observation(
                    ctx,
                    f"Last Order Sync is in the FUTURE ({sync_date} > "
                    f"{today}). The workbook does not name this shape, so "
                    f"it is not asserted — but the next import would skip "
                    f"every order created before it. Worth raising with the "
                    f"blank case.")

            for name, label, note in LAST_SYNC_FIELDS:
                if name not in fields_meta:
                    continue
                baseline_rows.append(
                    [label, name, str(values.get(name) or ""), "", note])
            observation(
                ctx,
                "the model carries three 'last …' datetimes "
                f"({', '.join(n for n, _l, _x in LAST_SYNC_FIELDS)}); the "
                "workbook names only Last Order Sync. All three are in the "
                "CSV so a printout showing several is not compared against "
                "the wrong one")

        with ctx.step("Step 4: clear the Connected filter and confirm no "
                      "store appears that should not be there"):
            search_arch = view_arch(ctx, VIEW_STORE_SEARCH, "search")
            filters = search_filters(search_arch)
            ctx.log(f"Manage Stores search filters: {filters}")
            connected = filters.get(CONNECTED_FILTER) or {}
            ctx.check("The search view carries a filter labelled "
                      "'Connected'", "Connected", connected.get("string"))
            ctx.check(
                "…and it filters on active, which is the same input Status "
                "is computed from",
                "[('active','=',True)]",
                str(connected.get("domain") or "").replace(" ", ""))
            ctx.check_true(
                "…and the action switches it on by default, which is why "
                "the workbook has to clear it",
                store_context(action).get(CONNECTED_SEARCH_DEFAULT) == 1,
                actual_desc=f"action context={store_context(action)!r}")

            context = store_context(action)
            with_filter = rpc.search_read(
                CHANNEL, store_domain(ctx, action, include_inactive=False),
                ["name", "platform", "active", "status", "last_sync_order"],
                context=context)
            without_filter = rpc.search_read(
                CHANNEL, store_domain(ctx, action, include_inactive=True),
                ["name", "platform", "active", "status", "last_sync_order"],
                context=context)
            revealed = [row for row in without_filter
                        if row["id"] not in {r["id"] for r in with_filter}]
            ctx.log(f"Connected filter ON: {len(with_filter)} store(s); "
                    f"filter cleared: {len(without_filter)}; revealed by "
                    f"clearing: "
                    f"{[(r['name'], r['platform'], r['active']) for r in revealed]}")
            for row in without_filter:
                store_rows.append([
                    row["id"], row.get("name"), row.get("platform"),
                    "Yes" if row.get("active") else "No",
                    row.get("status"), str(row.get("last_sync_order") or ""),
                    "shown with the Connected filter on" if row["id"] in
                    {r["id"] for r in with_filter} else
                    "only visible once the filter is cleared",
                ])

            # The action's own domain is what keeps template rows and
            # platform-less channels off this screen
            # (omni_manage_channel/views/ecommerce_channel_views.xml:14, 58).
            templates = [f"#{row['id']} {row.get('name')!r}"
                         for row in without_filter
                         if str(row.get("name") or "").endswith("(Template)")]
            ctx.check(
                "No template row appears once the filter is cleared — the "
                "action's own domain excludes '%(Template)' names, and one "
                "leaking through would be a store 'that should not be "
                "there'",
                [], templates)
            platformless = [f"#{row['id']} {row.get('name')!r}"
                            for row in without_filter
                            if not row.get("platform")
                            or row.get("platform") == "none"]
            if platformless:
                observation(
                    ctx,
                    f"a channel row with no platform is listed: "
                    f"{platformless}. Not asserted against, because the "
                    f"action's ('platform','!=','none') term is a DEAD term "
                    f"on this build — ecommerce.channel.platform has no "
                    f"('none','None') key at all (its base selection is "
                    f"empty and multichannel_shopify adds only "
                    f"('shopify','Shopify') — omni_manage_channel/models/"
                    f"ecommerce_channel.py:45-48, multichannel_shopify/"
                    f"models/ecommerce_channel.py:49), so the term excludes "
                    f"nothing and a platform-less row legitimately reaches "
                    f"the screen. Screen hygiene, not a migration defect")

            duplicates = sorted(
                {row.get("name") for row in without_filter
                 if [r.get("name") for r in without_filter]
                 .count(row.get("name")) > 1})
            ctx.check(
                "No two store rows share a name — the same store migrated "
                "twice would import every order twice",
                [], duplicates)

            shopify_rows = [row for row in without_filter
                            if row.get("platform") == SHOPIFY]
            ctx.check(
                "Exactly one Shopify store exists, as the workbook's "
                "singular 'the gallery's Shopify store' assumes",
                1, len(shopify_rows))
            manual(ctx, f"confirm against the printout that the "
                        f"{len(without_filter)} row(s) in "
                        f"TC-CHN-005-stores-listed.csv are the stores that "
                        f"should exist — only the baseline says which "
                        f"disconnected stores were expected to come across")

        with ctx.step("Steps 5-6: the Overview card — the same record, and "
                      "what each view actually binds"):
            overview = resolve_action(ctx, ACTION_OVERVIEW)
            ctx.check_true(
                "The Overview menu resolves to the channel-overview action",
                bool(rpc.ref(MENU_OVERVIEW)),
                actual_desc=f"{MENU_OVERVIEW} = {rpc.ref(MENU_OVERVIEW)}, "
                            f"{ACTION_OVERVIEW} = {rpc.ref(ACTION_OVERVIEW)}")
            ctx.check(
                "The Overview screen scopes to the same stores as Manage "
                "Stores, so the two cannot be showing different "
                "populations",
                (action["parsed_domain"], store_context(action)),
                (overview["parsed_domain"], store_context(overview)))

            on_overview = rpc.search_read(
                CHANNEL, store_domain(ctx, overview, include_inactive=True),
                ["name"], context=store_context(overview))
            ctx.check_true(
                "…and the store under test is one of them",
                store_id in {row["id"] for row in on_overview},
                actual_desc=f"Overview lists "
                            f"{[(r['id'], r['name']) for r in on_overview]}")

            kanban_arch = view_arch(ctx, VIEW_STORE_KANBAN, "kanban")
            ctx.check_true(
                "The card binds Status — the connection badge survived the "
                "v19 rebuild",
                'name="status"' in kanban_arch,
                actual_desc="the base card's col-md-3 block holding "
                            "<field name=\"status\" "
                            "widget=\"label_selection\"> is not touched by "
                            "multichannel_order's replace "
                            "(omni_manage_channel/views/"
                            "omnichannel_dashboard_views.xml:56-60)")
            ctx.check(
                "The card and the list read the same Status value, because "
                "they read the same field on the same record",
                values.get("status"),
                rpc.read(CHANNEL, [store_id], ["status"])[0]["status"])

            missing_from_card = [text for text in V15_CARD_READINGS
                                 if text not in kanban_arch]
            card_has_last_sync = 'name="last_sync_order"' in kanban_arch
            ctx.log(f"assembled kanban arch: last_sync_order bound="
                    f"{card_has_last_sync}; v15 card readings still "
                    f"present={[t for t in V15_CARD_READINGS if t in kanban_arch]}")
            if missing_from_card or not card_has_last_sync:
                finding(
                    ctx,
                    f"step 5 cannot be performed as written. The v19 card "
                    f"shows neither Last Order Sync nor the two figure "
                    f"tiles: multichannel_order replaces the whole "
                    f"col-md-9 block that held them with the period "
                    f"selector (multichannel_order/views/"
                    f"omnichannel_dashboard_views.xml:8-14, against the "
                    f"base card at omni_manage_channel/views/"
                    f"omnichannel_dashboard_views.xml:61-88). Removed from "
                    f"the card: {missing_from_card}. The connection badge "
                    f"(col-md-3) survives, so Status IS still readable "
                    f"there. Consistently, the same module overrides "
                    f"get_dashboard_datas() without super() "
                    f"(multichannel_order/models/ecommerce_channel.py:"
                    f"212-223) so the sales_total / sales_unit keys those "
                    f"tiles read are no longer in the payload either. On "
                    f"v15 neither had happened. This is a WORKBOOK "
                    f"AMENDMENT item — no migrated value is wrong — and "
                    f"step 6's substance is asserted above on the record "
                    f"and on what each view binds.")
                manual(ctx, "read Last Order Sync off the Manage Stores "
                            "list (step 3), not the Overview card — the "
                            "card no longer displays it on this build")

            payload = dashboard_payload(ctx, store_id)
            ctx.log(f"the card's own figure payload (get_dashboard_datas): "
                    f"{payload}")
            observation(
                ctx,
                f"the tiles the workbook calls 'Total sales' and 'Total "
                f"orders' now live in the Store Statistics panel, over a "
                f"period the card's {PERIOD_FIELD} field selects "
                f"(currently {values.get(PERIOD_FIELD)!r}). TC-CHN-011 is "
                f"the case that asserts those figures; here they are only "
                f"reported: total_sales={payload.get('total_sales')!r} "
                f"num_of_orders={payload.get('num_of_orders')!r}")

        with ctx.step("Expected Result: the two values, captured for the "
                      "baseline comparison"):
            manual(ctx, f"compare against the Novobi baseline read at the "
                        f"upgrade cut-off — Status = {values.get('status')!r}"
                        f", Last Order Sync = "
                        f"{values.get('last_sync_order')!r}. Both are in "
                        f"TC-CHN-005-sync-state.csv. If they differ, the "
                        f"workbook asks for BOTH baseline values and BOTH "
                        f"v19 values in the report")
            ctx.check_true(
                "Both values the workbook compares are present and "
                "readable, so the baseline comparison can actually be made",
                bool(values.get("status")) and
                bool(values.get("last_sync_order")),
                actual_desc=f"status={values.get('status')!r}, "
                            f"last_sync_order="
                            f"{values.get('last_sync_order')!r}")
            ctx.log(f"store under test: #{store_id} "
                    f"{values.get('name')!r} — company="
                    f"{m2o_id(values.get('company_id'))}, environment="
                    f"{values.get('environment')!r}, auto_import_data="
                    f"{values.get('auto_import_data')!r}. Nothing on this "
                    f"record was modified.")

    finally:
        write_csv(ctx, "TC-CHN-005-sync-state.csv",
                  ["Workbook label", "Technical field", "Value on v19",
                   "Novobi baseline (fill in)", "Note"],
                  baseline_rows)
        write_csv(ctx, "TC-CHN-005-stores-listed.csv",
                  ["id", "Store", "Platform", "Active", "Status",
                   "Last Order Sync", "Visibility"],
                  store_rows)
        ctx.log(f"read-only RPC calls made: {rpc.calls}; records created or "
                f"modified: 0")
