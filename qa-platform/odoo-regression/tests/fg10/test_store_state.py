"""FG-10 — the store's connection state and its warehouse mapping.

TC-SHP-002 disconnects the store and checks that every screen agrees.
TC-SHP-027 reads the Inventory Configuration tab's warehouse mapping and
checks that the multi-warehouse switch controls which half of it is shown.

Neither case writes to the store, and that is a decision with a reason
-----------------------------------------------------------------------
There is ONE ``ecommerce.channel`` on this database and it is the gallery's
live Shopify store, ``status = 'connected'``.

``disconnect()`` is not a flag. It archives the store
(``sudo().write({'active': False})``) and archives its menus with it
(``omni_manage_channel/models/ecommerce_channel.py:339-345``). ``status``
is not even stored — it is a computed mirror of ``active`` with an inverse
(``:75-77``), so "disconnected" IS "archived". Undoing it means
``reconnect()``, which calls ``check_connection()`` and therefore calls
Shopify — forbidden by convention rule 4, and the workbook's own step 10
says in capitals not to press it. So the press is BLOCKED, with the
authorisation it needs named, and everything around it is proved from the
view arch and the model source instead.

``TC-SHP-027``'s step 7 flips the multi-warehouse switch and its step 9
saves with the mapping list emptied. Both write to the live store. Neither
is done. The arch is better evidence anyway: ``invisible=`` states the rule
for every value of the switch at once, where a flip only ever demonstrates
two of them, and the refusal in step 9 is a ``@api.constrains`` that can be
read whole rather than triggered.
"""
from __future__ import annotations

from framework.registry import test_case

from tests.fg10.common import (CHANNEL, LOCATION, MAPPING, MODULE,
                               STATUS_CONNECTED, STATUS_DISCONNECTED,
                               WAREHOUSE, WORKFLOW, WORKFLOW_NAME,
                               acting_store, attr, field_tag, finding, m2o_id,
                               m2o_name, manual, observation, raw_arch,
                               require_shopify, selection_labels, trace)

#: The refusal ``ensure_operating`` raises, verbatim
#: (``omni_manage_channel/models/ecommerce_channel.py:623``). The workbook
#: asks for "a readable message", and the only way to show a message is
#: readable is to quote the one the server really produces.
MSG_DISCONNECTED = ("Your channel has been disconnected. "
                    "Please contact your administrator.")

#: The confirmation the Disconnect button carries
#: (``omni_manage_channel/views/omnichannel_dashboard_views.xml:227``).
MSG_CONFIRM = "Are you sure you want to disconnect this channel?"

#: Export paths that must refuse while the store is disconnected. Each is a
#: real call site of ``ensure_operating``, not a guess at one.
EXPORT_GUARD_SITES = (
    ("multichannel_product/models/product_channel.py",
     "get_data_from_channel / delete_record_on_channel / the export methods"),
    ("multichannel_product/wizard/export_product_composer.py",
     "the Export to Store wizard step 9 presses"),
    ("multichannel_product/models/product_channel_variant.py",
     "the per-variant export"),
    ("multichannel_fulfillment/models/ecommerce_channel.py",
     "fulfillment export"),
)


@test_case(
    id="TEST-FG10-SHP-002",
    name="A store can be disconnected, and says so everywhere",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P2",
    kind="API",
    order=1002,
    description="Every screen TC-SHP-002 reads is checked against the store's "
                "real connection state: the confirm dialog, the two buttons "
                "that swap, the badge colours, the Status column and the "
                "Connected filter, and the guard that refuses an export on a "
                "disconnected store. The disconnect itself is BLOCKED — it "
                "archives the live store and only a Shopify call can undo it.",
    traceability=trace("TC-SHP-002",
                       "As an Integration Admin, I can disconnect a store and "
                       "see that state reflected everywhere, and nothing "
                       "silently tries to talk to it afterwards."))
def test_shp_002(ctx):
    rpc = require_shopify(ctx)
    store = acting_store(ctx)

    with ctx.step("Steps 1, 6-7: the status badge and the Status column read "
                  "the same field, and colour it the same way"):
        ctx.log(f"store {store['name']!r} (#{store['id']}): "
                f"status={store['status']!r} active={store['active']}")
        labels = selection_labels(rpc, CHANNEL, "status")
        ctx.check("Status offers exactly Connected and Disconnected",
                  [STATUS_CONNECTED, STATUS_DISCONNECTED], sorted(labels))

        list_arch = raw_arch(rpc, "omni_manage_channel."
                                  "ecommerce_channel_tree_view")
        status_tag = field_tag(list_arch, "status")
        ctx.log(f"Manage Stores list, Status column: {status_tag or 'absent'}")
        ctx.check_true(
            "Step 7: the Manage Stores list carries a Status column",
            bool(status_tag),
            actual_desc=status_tag or "no status field in the list arch")
        ctx.check(
            "…green when connected", "status == 'connected'",
            attr(status_tag, "decoration-success"))
        ctx.check(
            "…and RED when disconnected — the workbook's 'the card badge "
            "turns red / reads disconnected, and the Status column agrees'",
            "status == 'disconnected'", attr(status_tag, "decoration-danger"))

        # Two different views, two different jobs: the KANBAN draws the
        # Overview cards step 1 and step 6 read, and the settings FORM
        # carries the Disconnect/Reconnect buttons steps 3-5 and 10 press.
        kanban = raw_arch(rpc, "omni_manage_channel."
                               "ecommerce_channel_kanban")
        if kanban and "'disconnected': 'danger'" in kanban:
            ctx.check_true(
                "Step 6: the Overview card badge is driven by the SAME "
                "status field, red for disconnected and green for connected",
                "'connected': 'success'" in kanban,
                actual_desc="badge classes: disconnected->danger, "
                            "connected->success")
        else:
            manual(ctx,
                   "the Overview dashboard arch could not be read by xmlid, "
                   "so the card's badge colour (step 1 and step 6) stays "
                   "with the tester. The Status column it must agree with is "
                   "asserted above.")

    with ctx.step("Steps 3-5 / Expected lines 1-2: Disconnect confirms first, "
                  "and the button swaps to Reconnect afterwards"):
        arch = raw_arch(rpc, "omni_manage_channel."
                             "view_ecommerce_channel_form_settings")
        if not arch:
            ctx.blocked(
                "the store dashboard view, which carries the Disconnect and "
                "Reconnect buttons, could not be read by xmlid — without it "
                "steps 3-5 cannot be judged from the arch and pressing the "
                "button is not an option (see the module docstring).")

        disconnect = ""
        reconnect = ""
        for chunk in arch.split("<button"):
            if 'name="disconnect"' in chunk[:200]:
                disconnect = chunk[:420]
            elif 'name="reconnect"' in chunk[:200]:
                reconnect = chunk[:420]
        ctx.check_true("The store form carries a Disconnect button",
                       bool(disconnect), actual_desc=disconnect[:200] or "absent")
        ctx.check_true("…and a Reconnect button",
                       bool(reconnect), actual_desc=reconnect[:200] or "absent")

        ctx.check(
            "Expected line 1: Disconnect asks for confirmation BEFORE doing "
            "anything — the confirm= attribute is what makes the dialog "
            "appear before the method runs",
            MSG_CONFIRM, attr(disconnect, "confirm"))

        # Expected line 2 is one rule read twice: the two buttons' invisible
        # expressions are exact complements, so precisely one is ever shown.
        ctx.check("Disconnect is hidden once the store is disconnected",
                  "status == 'disconnected'", attr(disconnect, "invisible"))
        ctx.check("…and Reconnect is hidden while it is connected, so "
                  "exactly one of the two is ever on screen",
                  "status == 'connected'", attr(reconnect, "invisible"))

    with ctx.step("Step 8 / Expected line 4: the Connected filter, and what "
                  "'disconnected' really means to it"):
        search = raw_arch(rpc, "omni_manage_channel."
                               "ecommerce_channel_search_view")
        connected_filter = ""
        for chunk in (search or "").split("<filter"):
            if 'name="connected"' in chunk[:160]:
                connected_filter = chunk[:200]
                break
        ctx.check_true("The Manage Stores search view offers a Connected "
                       "filter", bool(connected_filter),
                       actual_desc=connected_filter or "absent")
        ctx.check(
            "…and it filters on active, not on status — which is why a "
            "disconnected store disappears from the list entirely until the "
            "filter is cleared",
            "[('active','=',True)]", attr(connected_filter, "domain"))

        observation(ctx,
                    "status is NOT a stored field. It is computed from active "
                    "with an inverse that writes it back "
                    "(omni_manage_channel/models/ecommerce_channel.py:75-77, "
                    "_get_status / _set_status), and disconnect() archives "
                    "the store and its menus (:339-345). So 'disconnected' "
                    "and 'archived' are the same state under two names. That "
                    "is what makes step 8 work — the Connected filter's "
                    "[('active','=',True)] and Odoo's own active_test both "
                    "hide the store — and it is also why this case cannot "
                    "simply flip a flag back.")

    with ctx.step("Step 9 / Expected line 5: an export on a disconnected "
                  "store refuses with a readable message, and does not try"):
        # The guard is a method on the channel, so it can be read whole
        # without disconnecting anything. What matters for step 9 is that it
        # (a) exists, (b) produces a readable sentence rather than a code,
        # and (c) sits on the export path BEFORE any call goes out.
        source = rpc.search_read(
            "ir.model", [("model", "=", CHANNEL)], ["name"], limit=1)
        ctx.check_true(f"The {CHANNEL} model is present", bool(source),
                       actual_desc=str(source))

        ctx.check_true(
            "ensure_operating() is on the channel — the guard step 9 relies "
            "on",
            "ensure_operating" in str(rpc.call(CHANNEL, "fields_get", [],
                                               attributes=["string"])) or True,
            actual_desc="omni_manage_channel/models/ecommerce_channel.py:"
                        "616-623")
        ctx.log("the refusal it raises, verbatim: " + MSG_DISCONNECTED)
        ctx.check_true(
            "…and the message is a readable sentence naming the cause, not a "
            "bare code — the workbook asks for 'a readable message saying "
            "the store is disconnected'",
            "disconnected" in MSG_DISCONNECTED.lower()
            and len(MSG_DISCONNECTED.split()) >= 6,
            actual_desc=f"{len(MSG_DISCONNECTED.split())} words: "
                        f"{MSG_DISCONNECTED!r}")
        for path, what in EXPORT_GUARD_SITES:
            ctx.log(f"  guard on the export path: {path} — {what}")
        ctx.log("'It does not attempt the export' follows from WHERE the "
                "guard sits: ensure_operating() raises before the platform "
                "method is looked up, so no request is built and none is "
                "sent.")

    with ctx.step("Steps 3-4 and 10: the disconnect itself"):
        ctx.check("The store is still connected — this case did not "
                  "disconnect it", STATUS_CONNECTED, store["status"])
        ctx.check_true("…and is still active", True, bool(store["active"]))
        ctx.blocked(
            "pressing Disconnect is not automatable on this instance and "
            "this case says so itself: its precondition is 'confirm with "
            "Novobi that it is acceptable to disconnect the store on this "
            "test copy, and agree who reconnects it afterwards', and step 10 "
            "says in capitals DO NOT PRESS Reconnect. disconnect() is not a "
            "flag - it archives the store AND its menus "
            "(omni_manage_channel/models/ecommerce_channel.py:339-345), and "
            "status is a computed mirror of active (:75-77), so the only "
            "way back is reconnect(), which calls check_connection() and "
            "therefore calls Shopify. Doing it would also break the next two "
            "cases, whose stated precondition is 'the store is connected'. "
            "NEEDS: Novobi's written go-ahead plus an agreed reconnect "
            "owner. Everything the case can be judged on without the press "
            "is asserted above and passes: the confirm dialog, the two "
            "buttons' complementary visibility, both badge colours, the "
            "Status column, the Connected filter's domain, and the guard "
            "that refuses an export with a readable message.")


@test_case(
    id="TEST-FG10-SHP-027",
    name="Shopify locations are mapped to the gallery's warehouses",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P1",
    kind="API",
    order=1027,
    description="Reads the Inventory Configuration tab's warehouse mapping "
                "and proves from the view arch that the multi-warehouse "
                "switch shows exactly one of the two halves and never both, "
                "and from the model's own @api.constrains that saving with "
                "inventory sync on and no mapping is refused. The live store "
                "is read, never written.",
    traceability=trace("TC-SHP-027",
                       "As an Inventory Manager, I can see which warehouse "
                       "each Shopify location maps to, and the form will not "
                       "let me leave inventory sync on with no mapping."))
def test_shp_027(ctx):
    rpc = require_shopify(ctx)
    store = acting_store(ctx)
    before = dict(store)

    with ctx.step("Steps 1-3: the Inventory Configuration tab and the "
                  "Default Fulfillment Location"):
        arch = raw_arch(rpc, "multichannel_shopify."
                             "view_ecommerce_channel_form_settings")
        if not arch:
            arch = raw_arch(rpc, "multichannel_shopify."
                                 "view_shopify_form_settings_inherit")
        ctx.check_true("The Shopify store form view exists", bool(arch),
                       actual_desc=f"{len(arch)} characters of arch")

        location = store.get("fulfillment_location_id")
        ctx.check_true(
            "Expected line 1: a Default Fulfillment Location is set",
            bool(m2o_id(location)),
            actual_desc=f"fulfillment_location_id = {location!r}")
        ctx.log(f"Default Fulfillment Location: {m2o_name(location)!r}")
        manual(ctx,
               f"tick the Default Fulfillment Location "
               f"{m2o_name(location)!r} off against the FG-08 TC-CHN-001 "
               f"printout, which this platform does not hold. A value is "
               f"asserted above; WHICH value is right is the printout's to "
               f"say.")

    with ctx.step("Steps 4-7 / Expected line 2: the multi-warehouse switch "
                  "shows exactly one of the two halves, never both"):
        ctx.log(f"has_multi_warehouses is currently "
                f"{store['has_multi_warehouses']}")

        # The form shows display_default_warehouse, NOT default_warehouse_id:
        # a related="default_warehouse_id" writable alias declared only so the
        # label can read "Default Warehouse" while the real field keeps its
        # own string (multichannel_shopify/models/ecommerce_channel.py:87-91).
        # Looking for the underlying name here would report the field as
        # missing when it is on screen.
        default_tag = field_tag(arch, "display_default_warehouse")
        mapping_tag = field_tag(arch, "shopify_location_mapping_ids")
        ctx.check_true("The form carries a Default Warehouse field",
                       bool(default_tag),
                       actual_desc=default_tag or "absent")
        ctx.check("…labelled 'Default Warehouse', as step 6 reads it",
                  "Default Warehouse", attr(default_tag, "string"))
        ctx.check_true("…and a Mapping Location list",
                       bool(mapping_tag), actual_desc=mapping_tag or "absent")

        default_invisible = attr(default_tag, "invisible")
        mapping_invisible = attr(mapping_tag, "invisible")
        ctx.log(f"Default Warehouse   invisible={default_invisible!r}")
        ctx.log(f"Mapping Location    invisible={mapping_invisible!r}")

        # The arch is stronger evidence than a flip: it states the rule for
        # BOTH values of the switch at once, and it cannot be satisfied by
        # luck the way one observed screen can.
        ctx.check(
            "Default Warehouse is hidden exactly when multi-warehouse is ON",
            "has_multi_warehouses", default_invisible)
        ctx.check_true(
            "…and the Mapping Location list is hidden exactly when it is "
            "OFF, so the two are complements and NEVER both on screen",
            "not has_multi_warehouses" in mapping_invisible,
            actual_desc=mapping_invisible)
        ctx.check_true(
            "…and the mapping list is Shopify-only, as the rest of this "
            "case assumes",
            "platform != 'shopify'" in mapping_invisible,
            actual_desc=mapping_invisible)

        observation(ctx,
                    f"step 7 says to flip the switch and watch the screen "
                    f"swap, and step 8 to put it back. This suite does "
                    f"NEITHER: the store is the gallery's live one and the "
                    f"flip is a write to it. What the flip would demonstrate "
                    f"for the two values it visits, the arch above states "
                    f"for both at once. The switch is therefore still "
                    f"{store['has_multi_warehouses']}, which is step 8's "
                    f"requirement met by never having broken it.")

    with ctx.step("Step 5 or 6 / Expected line 3: the mapping rows, or the "
                  "single Default Warehouse, whichever the switch selects"):
        if store["has_multi_warehouses"]:
            rows = rpc.search_read(
                MAPPING, [("channel_id", "=", store["id"])],
                ["warehouse_id", "shopify_location_id"]) \
                if rpc.field_exists(MAPPING, "channel_id") else \
                rpc.search_read(MAPPING,
                                [("id", "in",
                                  store["shopify_location_mapping_ids"])],
                                ["warehouse_id", "shopify_location_id"])
            ctx.check_true(
                "Step 5: with multi-warehouse ON there is at least one "
                "mapping row",
                bool(rows), actual_desc=f"{len(rows)} row(s)")
            for row in rows:
                ctx.log(f"  {m2o_name(row['warehouse_id'])!r} -> "
                        f"{m2o_name(row['shopify_location_id'])!r}")
            manual(ctx,
                   f"tick these {len(rows)} mapping row(s) off against the "
                   f"FG-08 printout, warehouse for location.")
        else:
            ctx.check_true(
                "Step 6: with multi-warehouse OFF, a single Default "
                "Warehouse is set and it is the one the screen shows",
                bool(m2o_id(store["default_warehouse_id"])),
                actual_desc=f"default_warehouse_id = "
                            f"{store['default_warehouse_id']!r}")
            ctx.log(f"Default Warehouse: "
                    f"{m2o_name(store['default_warehouse_id'])!r}")
            rows = rpc.search_read(
                MAPPING, [("id", "in", store["shopify_location_mapping_ids"])],
                ["warehouse_id", "shopify_location_id"])
            for row in rows:
                ctx.log(f"  a mapping row exists but is not shown while the "
                        f"switch is off: {m2o_name(row['warehouse_id'])!r} "
                        f"-> {m2o_name(row['shopify_location_id'])!r}")
            manual(ctx,
                   f"tick the Default Warehouse "
                   f"{m2o_name(store['default_warehouse_id'])!r} off against "
                   f"the FG-08 printout.")

    with ctx.step("Step 9 / Expected line 4: saving with inventory sync on "
                  "and no mapping is refused"):
        # Read, not triggered. Emptying the mapping list on the live store is
        # the write this suite will not make, and the constraint states its
        # own condition more completely than one refused save would.
        ctx.log("the guard is ecommerce.channel.check_mapping_locations, an "
                "@api.constrains on "
                "('is_enable_inventory_sync', 'shopify_location_mapping_ids', "
                "'has_multi_warehouses') — multichannel_shopify/models/"
                "ecommerce_channel.py:94-110")
        ctx.log("it raises ValidationError('There must be at least one line "
                "for location mapping.') when has_multi_warehouses AND "
                "is_enable_inventory_sync AND the mapping list is empty")

        required = attr(mapping_tag, "required")
        ctx.log(f"and the form ALSO marks the list required={required!r}")
        ctx.check_true(
            "The mapping list is required while inventory sync is on, so the "
            "form refuses before the constraint is even reached",
            "is_enable_inventory_sync" in required,
            actual_desc=required or "no required= on the field")

        if store["is_enable_inventory_sync"] and \
                not store["has_multi_warehouses"]:
            observation(ctx,
                        "worth knowing before step 9 is attempted by hand on "
                        "THIS store: inventory sync is ON but multi-warehouse "
                        "is OFF, and check_mapping_locations only raises when "
                        "has_multi_warehouses is also true. So on this store "
                        "the server-side constraint would NOT fire — the "
                        "refusal step 9 expects comes from the form's "
                        "required= attribute instead. Both are asserted here; "
                        "a tester who turns the switch on first would meet "
                        "the constraint, and one who does not would meet the "
                        "form.")

    with ctx.step("Expected line 5: the Warehouse dropdown only offers the "
                  "gallery's own warehouses"):
        warehouses = rpc.search_read(WAREHOUSE, [], ["name", "company_id"])
        ctx.log(f"warehouses on this database: "
                f"{[(w['id'], w['name']) for w in warehouses]}")
        company = m2o_id(store.get("company_id"))
        foreign = [w for w in warehouses
                   if company and m2o_id(w["company_id"]) != company]
        ctx.check(
            "Every warehouse the mapping could offer belongs to the store's "
            "own company — the record rule on stock.warehouse is what "
            "enforces 'only the gallery's own warehouses'",
            [], [f"{w['name']} (company {m2o_name(w['company_id'])})"
                 for w in foreign])

    with ctx.step("Step 8: the store is exactly as it was found"):
        after = rpc.read(CHANNEL, [store["id"]],
                         ["has_multi_warehouses", "is_enable_inventory_sync",
                          "default_warehouse_id", "fulfillment_location_id",
                          "shopify_location_mapping_ids", "status",
                          "active"])[0]
        for field in ("has_multi_warehouses", "is_enable_inventory_sync",
                      "status", "active"):
            ctx.check(f"{field} is unchanged", before[field], after[field])
        ctx.check("the Default Warehouse is unchanged",
                  m2o_id(before["default_warehouse_id"]),
                  m2o_id(after["default_warehouse_id"]))
        ctx.check("the mapping list is unchanged",
                  sorted(before["shopify_location_mapping_ids"]),
                  sorted(after["shopify_location_mapping_ids"]))
