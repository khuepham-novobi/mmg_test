"""FG-15 — TC-UIX-011: every omnichannel screen opens, draws and saves.

Implements the CLIENT MANUAL TESTING GUIDELINE
``MMG_v19_Client_Manual_Testing_Guideline_FG15-FG20_v1.0.xlsx`` / sheet
``Testing Guideline``, case TC-UIX-011 (P0).

This is the gate for the rest of FG-15 — every other case in the group
opens with "TC-UIX-011 has passed" — and its Expected Result draws the line
this test has to respect: *"A screen that draws but will not save is a
FAIL, not a pass."* So the two saves step 3 asks for are made for real,
not inferred from the view.

The store form is deliberately NOT one of them. Step 3 says so in as many
words: an E-commerce Manager is not allowed to save a store, and a rights
message there is correct behaviour recorded under TC-SEC-010 — which
TEST-FG19-SEC-010 has already established on this database.
"""
from __future__ import annotations

from adapters.base import OdooRPCError
from framework.registry import test_case

from .common import (CHANNEL, LOG_ACTION, MODULE, ORDER, PRODUCT_CHANNEL,
                     SWEEP_SCREENS, WORKFLOW, WORKFLOW_NAME, manual,
                     observation, open_screen, removal_allowed,
                     require_connector, stores, trace)


@test_case(
    id="TEST-FG15-UIX-011",
    name="Every omnichannel screen opens, draws and saves",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P0",
    kind="API",
    order=1500,
    description="All nine menu-reachable screens of step 1 are opened "
                "through the menus the workbook names and every view each "
                "pins is built; the store card's Log entry is opened too. "
                "The two saves step 3 requires — a product mapping and a "
                "sales order — are made for real, because 'a screen that "
                "draws but will not save is a FAIL, not a pass'. The store "
                "form is excluded from the saves exactly as step 3 "
                "instructs.",
    traceability=trace("TC-UIX-011"))
def test_uix_011(ctx):
    rpc = require_connector(ctx)
    opened = {}

    with ctx.step("Steps 1-2: every screen the workbook lists opens and "
                  "every view behind it builds"):
        failures, allowed = [], {}
        for letter, path in SWEEP_SCREENS:
            result = open_screen(ctx, path)
            opened[path] = result
            if result["error"]:
                # A screen the client removed ON PURPOSE is not a broken
                # screen. removal_allowed() gives evidence only for a menu
                # that is genuinely archived, so a screen that is present
                # and will not draw still fails here.
                evidence = removal_allowed(ctx, path)
                if evidence:
                    allowed[path] = evidence
                    ctx.log(f"  {letter}. ALLOWED {path} — "
                            f"deliberately removed")
                    ctx.log(f"        {evidence}")
                    continue
                failures.append(f"({letter}) {path} — {result['error']}")
                ctx.log(f"  {letter}. FAILED  {path}")
                ctx.log(f"        {result['error']}")
            else:
                ctx.log(f"  {letter}. ok      {path} "
                        f"[{', '.join(result['views']) or result.get('kind', '')}]")

        if allowed:
            observation(ctx,
                        f"{len(allowed)} of the screens the workbook sweeps "
                        f"are absent BY DESIGN and are not counted against "
                        f"this case: {sorted(allowed)}. The citation is "
                        f"logged above; the decision lives in "
                        f"staging19_cleanup.sh step 4g, which re-applies it "
                        f"on every staging rebuild, so this is not drift "
                        f"waiting to be noticed.")

        ctx.check("Every omnichannel screen opens and draws, or is a "
                  "documented deliberate removal", [], failures)

    with ctx.step("Step 1f: the store form's every tab builds"):
        arch = rpc.call(CHANNEL, "get_view", view_type="form")["arch"]
        from .common import root_attrs
        import re
        tabs = [t.replace("&amp;", "&") for t in
                re.findall(r'<page[^>]*string="([^"]+)"', arch)]
        ctx.log(f"store form tabs: {tabs}")
        ctx.check_true(
            "The store form carries its notebook of tabs — 'click through "
            "EVERY tab across the top of the form'",
            len(tabs) >= 3, actual_desc=f"{len(tabs)} tabs: {tabs}")
        # A tab that will not draw is a view that will not build, and the
        # whole form arch built above, so every tab in it built with it.
        observation(ctx,
                    "the tabs are pages of ONE form view: the arch built, "
                    "so every page in it built. What a browser still has to "
                    "confirm is that each page renders — a page whose "
                    "content depends on a widget can build and still draw "
                    "blank.")

    with ctx.step("Step 1k: the store card's Log entry opens"):
        store_rows = stores(ctx)
        if not store_rows:
            ctx.blocked("no store exists, so the Overview has no card and "
                        "step 1k has nothing to open.")
        store = store_rows[0]
        action = rpc.call(CHANNEL, LOG_ACTION, [store["id"]])
        ctx.check_true(f"{LOG_ACTION}() returns a screen", bool(action),
                       actual_desc=str(action)[:160])
        ctx.check("…on the log model", "omni.log", action.get("res_model"))
        ctx.check_true("…scoped to this store",
                       str(store["id"]) in str(action.get("domain")),
                       actual_desc=str(action.get("domain"))[:160])

    with ctx.step("Step 3: the two saves the workbook requires — and only "
                  "those two"):
        refused = []

        mappings = rpc.search_read(PRODUCT_CHANNEL, [], ["id"], limit=1,
                                   order="id desc")
        if mappings:
            row = rpc.read(PRODUCT_CHANNEL, [mappings[0]["id"]],
                           ["description_sale"])[0] \
                if rpc.field_exists(PRODUCT_CHANNEL, "description_sale") \
                else None
            # Write a free-text field back onto itself: the workbook's own
            # "trivial edit" — nothing really changes, and the save is the
            # fact under test.
            field = "description_sale" if row is not None else "name"
            current = rpc.read(PRODUCT_CHANNEL, [mappings[0]["id"]],
                               [field])[0][field]
            try:
                rpc.write(PRODUCT_CHANNEL, [mappings[0]["id"]],
                          {field: current})
                ctx.log(f"  product mapping #{mappings[0]['id']}: saved")
            except OdooRPCError as exc:
                refused.append(f"product mapping: {exc}")
        else:
            observation(ctx, "no product mapping exists to save.")

        orders = rpc.search_read(ORDER, [], ["id", "note"], limit=1,
                                 order="id desc")
        if orders:
            try:
                rpc.write(ORDER, [orders[0]["id"]],
                          {"note": orders[0]["note"] or False})
                ctx.log(f"  sales order #{orders[0]['id']}: saved")
            except OdooRPCError as exc:
                refused.append(f"sales order: {exc}")
        else:
            observation(ctx, "no sales order exists to save.")

        ctx.check("Both saves complete — 'a screen that draws but will not "
                  "save is a FAIL, not a pass'", [], refused)
        observation(ctx,
                    "the store form is deliberately not saved here. Step 3 "
                    "excludes it: an E-commerce Manager is not allowed to "
                    "save a store and a rights message there is correct "
                    "behaviour, which TEST-FG19-SEC-010 records under "
                    "TC-SEC-010.")

    manual(ctx,
           "TC-UIX-011 steps 4 and 5 — reading the browser Console on each "
           "screen for RED lines, and repeating the whole sweep in the "
           "second browser of the agreed pair. Nothing here opens a "
           "browser. This matters more in FG-15 than anywhere else in the "
           "workbook: this feature group is about custom OWL widgets, and a "
           "widget that throws in the browser leaves the server side "
           "looking perfectly healthy. A screen that builds here can still "
           "draw blank there.")
    manual(ctx,
           "Step 2's 'the store cards show a chart' is the same kind of "
           "fact — see TC-UIX-004, which is where the chart is the subject "
           "rather than an aside.")
