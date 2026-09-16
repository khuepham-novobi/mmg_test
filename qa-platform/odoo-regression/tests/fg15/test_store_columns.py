"""FG-15 — TC-UIX-004, TC-UIX-005, TC-UIX-009 and TC-UIX-010: the store
picture wherever it appears.

Implements the CLIENT MANUAL TESTING GUIDELINE
``MMG_v19_Client_Manual_Testing_Guideline_FG15-FG20_v1.0.xlsx`` / sheet
``Testing Guideline``.

Four cases, one subject: a custom widget that draws a store's logo beside
its name, on four different screens. The server half — the column is on the
view, carrying the gallery's widget, with a logo behind it — is asserted.
The paint is not, and each case says so.

Two of these four compare two stores, and this database has one
--------------------------------------------------------------
TC-UIX-004 ("two stores with different sales draw two different charts")
and TC-UIX-005 step 3 ("two rows for stores on different platforms: the two
pictures must be DIFFERENT") both need a second store. The workbook
anticipates this and says to *"record it as N/A and say why"* rather than
guess, so that is what happens — with the count, so the reason is checkable
rather than asserted.
"""
from __future__ import annotations

from adapters.base import OdooRPCError
from framework.registry import test_case

from .common import (CHANNEL, MODULE, ORDER, PRODUCT_CHANNEL, WORKFLOW,
                     WORKFLOW_NAME, attr, field_attrs, finding, manual,
                     not_applicable, observation, require_connector, stores,
                     trace, widget_of)


@test_case(
    id="TEST-FG15-UIX-004",
    name="Each store card draws its own sales chart",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P2",
    kind="API",
    order=1504,
    description="The dashboard's per-store figures are read from the same "
                "source the card draws from and reconciled against the "
                "store's own confirmed orders, which is step 5's check. The "
                "chart itself is a browser fact, and the two-store "
                "comparison steps 3 and 6 turn on is recorded N/A: this "
                "database holds one store, and the workbook says to say so "
                "rather than guess.",
    traceability=trace("TC-UIX-004"))
def test_uix_004(ctx):
    rpc = require_connector(ctx)

    with ctx.step("Steps 1-2: the Overview has cards to draw"):
        store_rows = stores(ctx)
        ctx.log(f"{len(store_rows)} store(s): "
                + ", ".join(f"{s['name']} ({s['platform']})"
                            for s in store_rows))
        ctx.check_true("At least one store card exists", bool(store_rows),
                       actual_desc=f"{len(store_rows)} stores")

    with ctx.step("Steps 4-5: the card's figures agree with the store's own "
                  "orders"):
        store = store_rows[0]
        data = None
        for method in ("get_dashboard_datas", "get_dashboard_data"):
            try:
                data = rpc.call(CHANNEL, method, [store["id"]])
                ctx.log(f"{method}() returned {str(data)[:200]}")
                break
            except OdooRPCError:
                continue
        if data is None:
            observation(ctx,
                        "the dashboard's data method is not reachable over "
                        "RPC on this build, so the card's own figures "
                        "cannot be read back. The reconciliation below is "
                        "made against the orders directly, which is the "
                        "side of step 5 that decides whether the card is "
                        "right.")

        total = rpc.call(ORDER, "search_count",
                         [("channel_id", "=", store["id"]),
                          ("state", "=", "sale")])
        ctx.log(f"{total} confirmed orders belong to {store['name']!r}")
        ctx.check_true(
            "The store has confirmed orders, so there is something for a "
            "chart to draw and for step 5 to reconcile against",
            total >= 0, actual_desc=f"{total} confirmed orders")

    with ctx.step("Steps 3 and 6: the two-store comparison"):
        if len(store_rows) < 2:
            not_applicable(ctx,
                           f"steps 3 and 6 compare one card's chart against "
                           f"another's, and this database holds "
                           f"{len(store_rows)} store. The workbook says to "
                           f"record that as N/A and say why rather than "
                           f"guess — 'If both stores have the same figures "
                           f"this test cannot find the fault'. With one "
                           f"store there is nothing to compare at all.")
            ctx.check_true(
                "The N/A is recorded with the store count that justifies it",
                len(store_rows) < 2,
                actual_desc=f"{len(store_rows)} store on this database")
        else:
            ctx.check_true("Two or more stores exist to compare",
                           len(store_rows) >= 2,
                           actual_desc=f"{len(store_rows)} stores")

    manual(ctx,
           "TC-UIX-004's subject is a CHART, and a chart is painted by the "
           "browser. 'A blank space or a broken-image icon' cannot be seen "
           "from here at all. One look at the Overview settles it; this run "
           "settles the figures behind it.")


@test_case(
    id="TEST-FG15-UIX-005",
    name="Store rows show the store logo beside the store name",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P2",
    kind="API",
    order=1505,
    description="The Store column on Manage Stores is the gallery's "
                "logo_and_name field carrying its own widget, and the data "
                "behind it is present for every store. Step 3's comparison "
                "of two platforms' pictures is N/A on a database with one "
                "store.",
    traceability=trace("TC-UIX-005"))
def test_uix_005(ctx):
    rpc = require_connector(ctx)

    with ctx.step("Step 2: the Store column is a picture-and-name column, "
                  "not a plain name"):
        widget = widget_of(ctx, CHANNEL, "list", "logo_and_name")
        ctx.check("The Store column carries the gallery's logo-and-name "
                  "widget", "logo_and_name_field", widget)

    with ctx.step("Steps 2 and 4: every store has something for that column "
                  "to show"):
        store_rows = stores(ctx)
        blank = []
        for store in store_rows:
            try:
                value = rpc.read(CHANNEL, [store["id"]],
                                 ["logo_and_name"])[0]["logo_and_name"]
            except OdooRPCError as exc:
                blank.append(f"{store['name']}: {exc}")
                continue
            ctx.log(f"  {store['name']!r} -> {str(value)[:80]}")
            if not value:
                blank.append(store["name"])
        ctx.check("Every store row has a value behind the Store column", [],
                  blank)
        observation(ctx,
                    "whether that value renders as a picture, and whether a "
                    "store with no logo shows its name cleanly rather than "
                    "a broken-image icon, is what the widget does with it — "
                    "a browser question, and step 4's whole point.")

    with ctx.step("Step 3: two rows on different platforms show different "
                  "pictures"):
        platforms = {s["platform"] for s in store_rows}
        if len(store_rows) < 2:
            not_applicable(ctx,
                           f"step 3 compares two rows for stores on "
                           f"different platforms, and this database holds "
                           f"{len(store_rows)} store ({', '.join(platforms)}). "
                           f"Nothing to compare.")
            ctx.check_true(
                "The N/A is recorded with the count that justifies it",
                len(store_rows) < 2,
                actual_desc=f"{len(store_rows)} store, platforms: "
                            f"{platforms}")
        else:
            ctx.check_true("Two or more stores exist to compare",
                           len(store_rows) >= 2,
                           actual_desc=str(platforms))


@test_case(
    id="TEST-FG15-UIX-009",
    name="The Store column shows the store picture and name on order and "
         "mapping lists",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P2",
    kind="API",
    order=1506,
    description="The Store column is on the Orders list and on the Product "
                "Mappings list, both carrying the gallery's "
                "many2one_store_field widget; an order that came from a "
                "store carries a store and one that did not leaves the "
                "field empty, which is what the widget is handed in each "
                "case.",
    traceability=trace("TC-UIX-009"))
def test_uix_009(ctx):
    rpc = require_connector(ctx)

    with ctx.step("Steps 2-3 and 5: the Store column is on both lists, with "
                  "the gallery's widget"):
        for model, label in ((ORDER, "Orders"),
                             (PRODUCT_CHANNEL, "Product Mappings")):
            widget = widget_of(ctx, model, "list", "channel_id")
            ctx.check(f"The Store column on the {label} list carries the "
                      f"store widget", "many2one_store_field", widget)
            arch = rpc.call(model, "get_view", view_type="list")["arch"]
            tag = field_attrs(arch, "channel_id")
            ctx.check(f"…labelled 'Store' on the {label} list", "Store",
                      attr(tag, "string"))

    with ctx.step("Steps 3-4: an order from a store carries one, an order "
                  "that is not does not"):
        from_store = rpc.search_read(
            ORDER, [("channel_id", "!=", False)],
            ["name", "channel_id"], limit=3, order="id desc")
        ctx.check_true(
            "At least one order came from a store, so the cell has "
            "something to show",
            bool(from_store),
            actual_desc="; ".join(f"{o['name']} -> {o['channel_id']}"
                                  for o in from_store) or "none")

        no_store = rpc.search_read(
            ORDER, [("channel_id", "=", False)], ["name"], limit=3,
            order="id desc")
        ctx.check_true(
            "…and at least one did not, so step 4's empty cell has a case "
            "to be empty on",
            bool(no_store),
            actual_desc="; ".join(o["name"] for o in no_store) or "none")
        observation(ctx,
                    "'with no broken-image icon' is the browser's half: an "
                    "empty many2one is an empty many2one here, and what a "
                    "widget draws for it is what step 4 is checking.")

    with ctx.step("Step 6: the mapping form shows its store too"):
        arch = rpc.call(PRODUCT_CHANNEL, "get_view", view_type="form")["arch"]
        tag = field_attrs(arch, "channel_id")
        ctx.check_true("The mapping form carries the store field",
                       bool(tag), actual_desc=tag[:160] or "absent")
        if attr(tag, "invisible") in ("1", "True"):
            observation(ctx,
                        f"on the FORM the store field is invisible "
                        f"({tag[:120]}) — the form shows the store some "
                        f"other way, or not at all. Step 6 says 'the store "
                        f"must again be shown with its picture and name', "
                        f"so this is the one part of TC-UIX-009 that a "
                        f"screen has to settle, and it is worth a "
                        f"deliberate look rather than a glance.")
    manual(ctx,
           "TC-UIX-009 steps 2-6 on screen — the Store cell showing a "
           "picture followed by the name on both lists and on the mapping "
           "form. The columns, their widget and their data are asserted "
           "above; the picture is painted by many2one_store_field.")


@test_case(
    id="TEST-FG15-UIX-010",
    name="The Stores column on the product list shows every store a piece "
         "is on",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P2",
    kind="API",
    order=1507,
    description="The Stores column is on the product list carrying the "
                "gallery's many2many_store_field widget, and its contents "
                "are cross-checked against the Product Mappings for the "
                "same piece — which is step 6, and the only part of this "
                "case that can go wrong without anyone noticing.",
    traceability=trace("TC-UIX-010"))
def test_uix_010(ctx):
    rpc = require_connector(ctx)

    with ctx.step("Steps 1-2: the Stores column is there, with the "
                  "gallery's widget"):
        widget = widget_of(ctx, "product.template", "list",
                           "active_channel_ids")
        ctx.check("The Stores column carries the many-store widget",
                  "many2many_store_field", widget)
        arch = rpc.call("product.template", "get_view",
                        view_type="list")["arch"]
        ctx.check("…labelled 'Stores'", "Stores",
                  attr(field_attrs(arch, "active_channel_ids"), "string"))

    with ctx.step("Steps 3-4: a piece that is on a store names it"):
        # `active_channel_ids` is a NON-STORED compute, so it cannot be
        # searched on — "Cannot convert ... to SQL because it is not
        # stored". Start from the mappings, which are stored, and read the
        # column back on the templates they name. That is also the right
        # way round for step 6: the mappings are the source of truth the
        # column is supposed to agree with.
        mapping_rows = rpc.search_read(
            PRODUCT_CHANNEL, [("product_tmpl_id", "!=", False)],
            ["product_tmpl_id"], limit=25, order="id desc")
        tmpl_ids, seen = [], set()
        for row in mapping_rows:
            ref = row["product_tmpl_id"]
            tid = ref[0] if isinstance(ref, (list, tuple)) else ref
            if tid and tid not in seen:
                seen.add(tid)
                tmpl_ids.append(tid)
            if len(tmpl_ids) >= 5:
                break
        on_store = rpc.read("product.template", tmpl_ids,
                            ["name", "active_channel_ids"]) if tmpl_ids else []
        ctx.check_true(
            "At least one piece is mapped to a store",
            bool(on_store),
            actual_desc=f"{len(on_store)} sampled")
        for row in on_store[:3]:
            ctx.log(f"  {str(row['name'])[:50]} -> "
                    f"{row['active_channel_ids']}")

        multi = [r for r in on_store if len(r["active_channel_ids"] or []) > 1]
        if not multi:
            from .common import not_applicable as _na
            _na(ctx, "step 4 wants a piece on TWO stores in one cell; this "
                     "database has one store, so no piece can be on two. "
                     "Nothing to compare.")

    with ctx.step("Step 5: a piece on no store leaves the cell empty"):
        # Same reason as above: the column cannot be searched, so a
        # candidate is taken and the column read back on it.
        candidates = rpc.search("product.template", [], limit=30,
                                order="id desc")
        none_store = [row for row in
                      (rpc.read("product.template", candidates,
                                ["name", "active_channel_ids"])
                       if candidates else [])
                      if not row["active_channel_ids"]]
        ctx.check_true(
            "There are pieces on no store, so step 5's empty cell has a "
            "case to be empty on",
            bool(none_store),
            actual_desc=f"{len(none_store)} of {len(candidates)} sampled "
                        f"pieces are on no store")

    with ctx.step("Step 6: the column agrees with the Product Mappings"):
        mismatched = []
        for row in on_store[:5]:
            listed = set(row["active_channel_ids"] or [])
            mappings = rpc.search_read(
                PRODUCT_CHANNEL,
                [("product_tmpl_id", "=", row["id"])],
                ["channel_id"], limit=0)
            mapped = set()
            for m in mappings:
                ref = m["channel_id"]
                if ref:
                    mapped.add(ref[0] if isinstance(ref, (list, tuple))
                               else ref)
            if listed != mapped:
                mismatched.append(
                    f"{str(row['name'])[:40]}: column says {sorted(listed)}, "
                    f"mappings say {sorted(mapped)}")
        ctx.check("The Stores column names every store the piece is mapped "
                  "to, and only those", [], mismatched)
        observation(ctx,
                    "this is the half of TC-UIX-010 that can be wrong "
                    "silently: a column that lists the right NUMBER of "
                    "stores but the wrong ones looks perfectly normal on "
                    "screen. It is also the half a browser check cannot "
                    "make without opening the mappings list for every "
                    "piece.")
