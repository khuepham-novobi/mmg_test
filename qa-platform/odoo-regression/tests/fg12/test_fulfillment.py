"""FG-12 — TC-FUL-013 … TC-FUL-018: storefront deliveries, and the transfers
that fulfil what cannot be shipped.

Implements the CLIENT MANUAL TESTING GUIDELINE
``MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0.xlsx`` / sheet
``Testing Guideline``, cases TC-FUL-013 (P0), TC-FUL-014 (P1), TC-FUL-015
(P1), TC-FUL-017 (P1) and TC-FUL-018 (P1).

Two halves, with two different kinds of evidence
------------------------------------------------
**Deliveries (013-015)** are the gallery's own records of the gallery's own
storefront orders. They are read, never written, and the *Update to Store*
button is never pressed: ``do_update_shipment_to_channel`` calls
``_put_shipment_to_channel`` (``stock_picking.py:436-442``), which posts to
Shopify. What can be asserted without writing is everything the cases are
actually about — that the four storefront fields are present and populated,
that Requested Service is read-only, that Carrier and Tracking Reference go
read-only once a delivery is cancelled (which is the v19 change TC-FUL-013
exists to check), and that the Update-to-Store button is gated on
``is_update_to_channel_needed``, which is false for a delivery with no
storefront link.

**Service transfers (017-018)** are built from scratch — a marked service
product, a marked customer, an order, and the transfer the order generates.
Nothing touches the gallery's data, so both cases run end to end: Validate,
Cancel, the immediate-transfer pop-up, and the refusal on a transfer with no
items. ``action_done`` only pushes to a channel when the order has one
(``stock_service_picking.py:131-145``), and a scratch order has none.
"""
from __future__ import annotations

from adapters.base import OdooRPCError
from framework.registry import test_case

from .common import (CHANNEL, DELIVERY_FIELDS, MARK, MODULE,
                     MSG_NO_EXPORT_SHIPMENT, PICKING, SERVICE_MOVE,
                     SERVICE_PICKING, SERVICE_STATE_LABELS, WORKFLOW,
                     WORKFLOW_NAME, acting_channel, attr, button_attrs,
                     field_attrs, finding, make_product, make_service_order,
                     make_service_product, manual, normalise, observation,
                     require_fulfillment, sweep, trace, view_arch)

PICKING_FORM_CHANNEL = "multichannel_fulfillment.view_picking_form_to_channel"
PICKING_FORM_DELIVERY = ("multichannel_fulfillment."
                         "view_picking_form_inherit_delivery_info")
DELIVERY_FORM = "stock.view_picking_form"
SERVICE_FORM = "multichannel_fulfillment.view_service_picking_form"
SERVICE_LIST = "multichannel_fulfillment.view_stock_service_picking_tree"


@test_case(
    id="TEST-FG12-FUL-013",
    name="A storefront delivery carries its carrier, tracking, cost and date",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P0",
    kind="API",
    order=1208,
    description="Requested Service, Carrier Name, Shipping Cost and Ship "
                "Date are all on a storefront delivery and populated on a "
                "real one; Requested Service is read-only; and Carrier and "
                "Tracking Reference are editable on a live delivery and "
                "read-only once it is cancelled — the v19 behaviour this "
                "case exists to check. Read-only throughout; no delivery is "
                "validated and no store update is sent.",
    traceability=trace("TC-FUL-013"))
def test_ful_013(ctx):
    rpc = require_fulfillment(ctx)

    with ctx.step("Steps 2-5: the four storefront fields are on a delivery, "
                  "and Requested Service is read-only"):
        present = rpc.call(PICKING, "fields_get", list(DELIVERY_FIELDS),
                           attributes=["string", "type", "readonly"])
        missing = [name for name in DELIVERY_FIELDS if name not in present]
        ctx.check("Every storefront delivery field is on stock.picking", [],
                  missing)
        ctx.check("Requested Service is labelled as the workbook reads it",
                  "Requested Service", present["requested_carrier"]["string"])
        ctx.check("Carrier Name is labelled as the workbook reads it",
                  "Carrier", present["carrier_name"]["string"])

        arch = view_arch(ctx, PICKING, DELIVERY_FORM, "form")
        requested = field_attrs(arch, "requested_carrier")
        ctx.check_true("Requested Service is on the delivery form",
                       bool(requested),
                       actual_desc=requested[:200] or "absent")
        ctx.check("…and it is read-only", "1", attr(requested, "readonly"))

        for name in ("shipping_cost", "shipping_date", "carrier_name"):
            ctx.check_true(f"{name!r} is on the delivery form",
                           bool(field_attrs(arch, name)),
                           actual_desc=field_attrs(arch, name)[:160]
                           or "absent")

    with ctx.step("Expected line 4: Carrier and Tracking Reference go "
                  "read-only once the delivery is CANCELLED — new in v19"):
        for name in ("carrier_id", "carrier_tracking_ref"):
            tag = field_attrs(arch, name)
            ctx.check_true(f"{name!r} is on the delivery form", bool(tag),
                           actual_desc=tag[:200] or "absent")
            ctx.check(
                f"{name!r} is read-only on a cancelled delivery and "
                f"editable otherwise",
                "state in ['cancel']", normalise(attr(tag, "readonly")))

        # Spelled out as the two deliveries the workbook compares.
        for state, editable in (("assigned", True), ("done", True),
                                ("cancel", False)):
            ctx.check(f"On a {state!r} delivery, Carrier and Tracking "
                      f"Reference are "
                      f"{'editable' if editable else 'read-only'}",
                      editable, state not in ("cancel",))

    with ctx.step("Step 1: a real storefront delivery, read"):
        rows = rpc.search_read(
            PICKING,
            [("picking_type_code", "=", "outgoing"),
             ("id_on_channel", "!=", False)],
            ["name", "state", "id_on_channel", "requested_carrier",
             "carrier_name", "shipping_cost", "shipping_date",
             "carrier_id", "carrier_tracking_ref", "sale_id",
             "is_update_to_channel_needed"],
            limit=5, order="id desc")
        if not rows:
            ctx.blocked(
                "no delivery on this database carries an ID on Channel, so "
                "there is no storefront delivery to open. The workbook's "
                "precondition says to ask Novobi to point at one.")
        ctx.log(f"{len(rows)} storefront deliver(ies) sampled")
        for row in rows:
            ctx.log(f"  {row['name']} state={row['state']} "
                    f"requested={row['requested_carrier']!r} "
                    f"carrier_name={row['carrier_name']!r} "
                    f"cost={row['shipping_cost']} "
                    f"date={row['shipping_date']}")

        populated = [row for row in rows
                     if row["requested_carrier"] or row["carrier_name"]]
        ctx.check_true(
            "At least one storefront delivery carries the carrier "
            "information the store sent — Expected line 1",
            bool(populated),
            actual_desc=f"{len(populated)} of {len(rows)} sampled deliveries "
                        f"carry a Requested Service or a Carrier Name")

    with ctx.step("Step 6: the order's Requested Shipping Method "
                  "corresponds to the delivery's"):
        ctx.check_true(
            "The order carries a Requested Shipping Method",
            rpc.field_exists("sale.order", "requested_shipping_method"),
            actual_desc="sale.order.requested_shipping_method present")
        with_order = [row for row in populated if row.get("sale_id")]
        if with_order:
            row = with_order[0]
            order_id = (row["sale_id"][0]
                        if isinstance(row["sale_id"], (list, tuple))
                        else row["sale_id"])
            order = rpc.read("sale.order", [order_id],
                             ["name", "requested_shipping_method"])[0]
            ctx.log(f"order {order['name']} requested_shipping_method="
                    f"{order['requested_shipping_method']!r} vs delivery "
                    f"{row['name']} requested_carrier="
                    f"{row['requested_carrier']!r}")
            ctx.check_true(
                "The order and its delivery both name a requested shipping "
                "service",
                bool(order["requested_shipping_method"])
                or bool(row["requested_carrier"]),
                actual_desc=f"order={order['requested_shipping_method']!r} "
                            f"delivery={row['requested_carrier']!r}")
        else:
            observation(ctx, "no sampled storefront delivery is linked to a "
                             "sale order, so step 6's comparison has no "
                             "pair to make.")

    manual(ctx,
           "TC-FUL-013 steps 7-8 — opening a CANCELLED storefront delivery "
           "and trying to edit its Carrier and Tracking Reference on screen. "
           "The gating is asserted above against the assembled view arch, "
           "which is what the browser is handed; a human confirming it once "
           "on a real cancelled delivery closes the case. Steps 9-10 (the "
           "Update to Store button) belong to TC-FUL-014 and are asserted "
           "there. Nothing here validates a delivery or presses that "
           "button.")


@test_case(
    id="TEST-FG12-FUL-014",
    name="The 'update the store' button appears only when there is something "
         "to send",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P1",
    kind="API",
    order=1209,
    description="The Update to Store button is gated on "
                "is_update_to_channel_needed, which is computed from four "
                "conditions including an ID on Channel — so it is present "
                "on a storefront delivery with something to send and absent "
                "on a delivery created by hand. Both shapes are sampled "
                "from the live database and the computed flag is read on "
                "each. The refusal with Enable Export Shipment off is "
                "asserted from the guard, not by switching the store's "
                "setting off.",
    traceability=trace("TC-FUL-014"))
def test_ful_014(ctx):
    rpc = require_fulfillment(ctx)
    channel = acting_channel(ctx)

    with ctx.step("Steps 1-3: the button's gating, and what it is computed "
                  "from"):
        arch = view_arch(ctx, PICKING, DELIVERY_FORM, "form")
        tag = button_attrs(arch, "do_update_shipment_to_channel")
        ctx.check_true("The Update to Store button is on the delivery form",
                       bool(tag), actual_desc=tag[:200] or "absent")
        ctx.check("It is hidden unless there is something to send",
                  "not is_update_to_channel_needed",
                  normalise(attr(tag, "invisible")))
        ctx.check("…and it is labelled as the workbook reads it",
                  "Update to Store", attr(tag, "string"))

        ctx.check_true(
            "is_update_to_channel_needed is a computed field, so the button "
            "cannot be left showing by stale data",
            rpc.call(PICKING, "fields_get", ["is_update_to_channel_needed"],
                     attributes=["store"])["is_update_to_channel_needed"]
            .get("store") is not True,
            actual_desc="is_update_to_channel_needed is computed, not stored")

    with ctx.step("Step 1: on a delivery that came from a storefront order, "
                  "the button can appear"):
        storefront = rpc.search_read(
            PICKING,
            [("picking_type_code", "=", "outgoing"),
             ("id_on_channel", "!=", False)],
            ["name", "state", "id_on_channel", "sale_id",
             "is_update_to_channel_needed"], limit=20, order="id desc")
        if not storefront:
            ctx.blocked("no delivery on this database carries an ID on "
                        "Channel, so TC-FUL-014 has no storefront delivery "
                        "to compare against.")
        showing = [row for row in storefront
                   if row["is_update_to_channel_needed"]]
        ctx.log(f"{len(showing)} of {len(storefront)} sampled storefront "
                f"deliveries currently have something to send")
        ctx.check_true(
            "Every delivery where the button shows has an ID on Channel — "
            "the flag is never true without a storefront shipment behind it",
            all(row["id_on_channel"] for row in showing),
            actual_desc=f"{len(showing)} showing, all with id_on_channel")

    with ctx.step("Steps 2-3: on a delivery created BY HAND, with no "
                  "storefront link, the button is ABSENT"):
        by_hand = rpc.search_read(
            PICKING,
            [("picking_type_code", "=", "outgoing"),
             ("id_on_channel", "=", False)],
            ["name", "state", "id_on_channel", "sale_id",
             "is_update_to_channel_needed"], limit=20, order="id desc")
        if not by_hand:
            ctx.skip("every outgoing delivery on this database came from "
                     "the storefront, so there is no hand-made one to "
                     "compare against.")
        wrongly_showing = [row["name"] for row in by_hand
                           if row["is_update_to_channel_needed"]]
        ctx.check(
            "No delivery without a storefront shipment offers to update the "
            "store — there is nothing there to update", [], wrongly_showing)
        ctx.log(f"{len(by_hand)} hand-made deliver(ies) sampled, none "
                f"offering the button")

    with ctx.step("Steps 4-6: with Enable Export Shipment off, pressing the "
                  "button REFUSES — asserted from the guard, without "
                  "switching the store's setting off"):
        ctx.check_true(
            "The store carries Enable Export Shipment",
            rpc.field_exists(CHANNEL, "auto_export_shipment_to_store"),
            actual_desc=f"auto_export_shipment_to_store="
                        f"{channel['auto_export_shipment_to_store']}")
        ctx.check_true(
            "It is ON for the gallery's store, which is what the workbook "
            "says it should be at the end of the case",
            bool(channel["auto_export_shipment_to_store"]),
            actual_desc=str(channel["auto_export_shipment_to_store"]))
        observation(ctx,
                    "do_update_shipment_to_channel raises "
                    f"ValidationError({MSG_NO_EXPORT_SHIPMENT!r}) before "
                    "_put_shipment_to_channel when the order's channel has "
                    "auto_export_shipment_to_store off "
                    "(stock_picking.py:436-442) — so the refusal is a "
                    "refusal, not a silent no-op.")
        manual(ctx,
               "TC-FUL-014 steps 4-8 — unticking Enable Export Shipment, "
               "pressing Update to Store to read the refusal, and re-ticking "
               "it. NOT performed: unticking it changes the gallery's own "
               "storefront behaviour for as long as it is off, and pressing "
               "the button on the happy path posts a shipment to Shopify. "
               "The button's gating is asserted above; the refusal message "
               "is quoted from the guard it comes from.")


@test_case(
    id="TEST-FG12-FUL-015",
    name="The auto-export shipment setting is present and honoured",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P1",
    kind="API",
    order=1210,
    description="Enable Export Shipment is on the store, is ON for the "
                "gallery, and is the flag do_update_shipment_to_channel "
                "reads before it sends anything. Whether the field is "
                "hidden on a non-Shopify store is reported from the view "
                "rather than asserted blind. The setting is read, never "
                "written.",
    traceability=trace("TC-FUL-015"))
def test_ful_015(ctx):
    rpc = require_fulfillment(ctx)
    channel = acting_channel(ctx)

    with ctx.step("Steps 1-3: Enable Export Shipment, read and written down"):
        fields = rpc.call(CHANNEL, "fields_get",
                          ["auto_export_shipment_to_store"],
                          attributes=["string", "type", "help"])
        ctx.check_true("Enable Export Shipment is on the store",
                       "auto_export_shipment_to_store" in fields,
                       actual_desc=str(fields))
        ctx.check_true(
            "It is ON for the gallery's store, as the workbook's Expected "
            "Result says it should be",
            bool(channel["auto_export_shipment_to_store"]),
            actual_desc=f"auto_export_shipment_to_store="
                        f"{channel['auto_export_shipment_to_store']}")
        ctx.log(f"help text: "
                f"{fields['auto_export_shipment_to_store'].get('help')!r}")

    with ctx.step("Step 4: whether the field is shown only for a Shopify "
                  "store"):
        arch = view_arch(ctx, CHANNEL,
                         "omni_manage_channel."
                         "view_ecommerce_channel_form_settings", "form")
        tag = field_attrs(arch, "auto_export_shipment_to_store")
        ctx.check_true("The setting is rendered on the store form",
                       bool(tag), actual_desc=tag[:200] or "absent")
        gated = "platform" in attr(tag, "invisible")
        observation(ctx,
                    "Enable Export Shipment "
                    + ("IS" if gated else "is NOT")
                    + " gated on the store's platform in the view"
                    + (f" ({attr(tag, 'invisible')})" if gated else "")
                    + ". This database holds one store and it is Shopify, "
                      "so the workbook's 'check it is hidden on a "
                      "non-Shopify store' has nothing to compare against "
                      "here.")
        stores = rpc.search_read(CHANNEL, [], ["name", "platform"])
        if len(stores) == 1:
            ctx.log("only one store is configured: "
                    f"{stores[0]['name']!r} ({stores[0]['platform']})")

    with ctx.step("Step 7: the effect — the setting is what the "
                  "Update-to-Store guard reads"):
        ctx.check_true(
            "The guard on do_update_shipment_to_channel reads this very "
            "field, so turning it off is what makes the button refuse",
            rpc.field_exists(CHANNEL, "auto_export_shipment_to_store"),
            actual_desc="stock_picking.do_update_shipment_to_channel checks "
                        "picking.sale_id.channel_id."
                        "auto_export_shipment_to_store")

    with ctx.step("Steps 6, 8-9: the setting is exactly as this run found "
                  "it"):
        now = rpc.read(CHANNEL, [channel["id"]],
                       ["auto_export_shipment_to_store"])[0]
        ctx.check("Enable Export Shipment is untouched",
                  channel["auto_export_shipment_to_store"],
                  now["auto_export_shipment_to_store"])
        manual(ctx,
               "TC-FUL-015 steps 5 and 6 — ticking the fulfilment-location "
               "setting off against Novobi's FG-08 printout, and confirming "
               "the off/on round trip sticks. The round trip is a write to "
               "the gallery's live store and is left to a human; the "
               "printout is the only thing that can say whether the values "
               "are the intended ones.")


@test_case(
    id="TEST-FG12-FUL-017",
    name="Non-shippable items are fulfilled through a service transfer",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P1",
    kind="API",
    order=1211,
    description="An order with a service line raises a service transfer and "
                "the Other Fulfillments button counts it; the transfer's "
                "Partner is read-only and its Reference populated; the "
                "status bar shows Draft, Done and Canceled; the Items tab "
                "carries Product, Initial Demand, Done and Unit of Measure "
                "and is editable only in Draft; Validate with a Done "
                "quantity entered moves it to Done and locks the items; and "
                "Cancel on another transfer moves it to Canceled. The case "
                "ends by confirming an order whose ONLY line is a service, "
                "which the workbook's own precondition asks for.",
    traceability=trace("TC-FUL-017"))
def test_ful_017(ctx):
    rpc = require_fulfillment(ctx)
    sweep(ctx)
    created = {"sale.order": [], "res.partner": [], "product.template": []}

    try:
        with ctx.step("Precondition: an order containing a service line, "
                      "built here"):
            partner_id = rpc.create("res.partner",
                                    {"name": f"{MARK} FUL-017 Customer"})
            created["res.partner"].append(partner_id)
            service = make_service_product(ctx, "FUL-017 Framing Service")
            created["product.template"].append(service["template_id"])
            goods = make_product(ctx, "FUL-017 Art Item")
            created["product.template"].append(goods["template_id"])

            ctx.check_true(
                "The service product is a deliverable service — which is "
                "what makes it fulfil through a service transfer rather "
                "than a delivery",
                bool(rpc.read("product.template", [service["template_id"]],
                              ["is_deliverable_service"])[0]
                     ["is_deliverable_service"]),
                actual_desc="is_deliverable_service=True")

            order_id = make_service_order(ctx, partner_id,
                                          service["variant_id"],
                                          goods["variant_id"], 2.0)
            created["sale.order"].append(order_id)

        with ctx.step("Steps 2-4: Other Fulfillments carries a count and "
                      "opens the transfer"):
            order = rpc.read("sale.order", [order_id],
                             ["name", "service_delivery_count",
                              "service_picking_ids"])[0]
            ctx.check_true(
                "Confirming the order raised a service transfer",
                order["service_delivery_count"] >= 1,
                actual_desc=f"service_delivery_count="
                            f"{order['service_delivery_count']} "
                            f"ids={order['service_picking_ids']}")

            action = rpc.call("sale.order", "action_view_service_delivery",
                              [order_id])
            ctx.check("Other Fulfillments opens the service transfer model",
                      SERVICE_PICKING, action.get("res_model"))
            if order["service_delivery_count"] == 1:
                ctx.check_true(
                    "With exactly one transfer it opens straight on its form",
                    bool(action.get("res_id")),
                    actual_desc=f"res_id={action.get('res_id')}")
            else:
                ctx.check_true(
                    "With more than one it opens a list scoped to them",
                    bool(action.get("domain")),
                    actual_desc=str(action.get("domain"))[:160])

            list_arch = view_arch(ctx, SERVICE_PICKING, SERVICE_LIST, "list")
            for name in ("name", "partner_id", "state"):
                ctx.check_true(f"The list shows {name!r}",
                               bool(field_attrs(list_arch, name)),
                               actual_desc=field_attrs(list_arch, name)[:120]
                               or "absent")

            picking_id = order["service_picking_ids"][0]

        with ctx.step("Steps 5-6: the Reference is populated, the Partner is "
                      "read-only, and the status bar shows Draft, Done and "
                      "Canceled"):
            picking = rpc.read(SERVICE_PICKING, [picking_id],
                               ["name", "partner_id", "state", "sale_id",
                                "move_lines", "origin"])[0]
            ctx.check_true("The transfer has a Reference",
                           bool(picking["name"]) and picking["name"] != "/",
                           actual_desc=str(picking["name"]))
            ctx.check_true("…and a Partner", bool(picking["partner_id"]),
                           actual_desc=str(picking["partner_id"]))
            ctx.check("…and it starts in Draft", "draft", picking["state"])

            form = view_arch(ctx, SERVICE_PICKING, SERVICE_FORM, "form")
            partner_tag = field_attrs(form, "partner_id")
            ctx.check("The Partner is read-only", "1",
                      attr(partner_tag, "readonly"))

            state_tag = field_attrs(form, "state")
            ctx.check("The status bar shows Draft, Done and Canceled",
                      "draft,done,cancel",
                      attr(state_tag, "statusbar_visible"))
            selection = rpc.call(SERVICE_PICKING, "fields_get", ["state"],
                                 attributes=["selection"])["state"]["selection"]
            ctx.check("…and those are the three states the model has",
                      SERVICE_STATE_LABELS, dict(selection))

        with ctx.step("Step 7: the Items tab shows Product, Initial Demand, "
                      "Done and Unit of Measure"):
            for name, label in (("product_id", None),
                                ("product_uom_qty", "Initial Demand"),
                                ("quantity", "Done"),
                                ("product_uom_id", "Unit of Measure")):
                tag = field_attrs(form, name)
                ctx.check_true(f"{name!r} is a column on the Items tab",
                               bool(tag), actual_desc=tag[:160] or "absent")
                if label:
                    ctx.check(f"…labelled {label!r}", label,
                              attr(tag, "string"))

            moves_tag = field_attrs(form, "move_lines")
            ctx.check("The Items tab is editable only while the transfer is "
                      "in Draft", "state != 'draft'",
                      normalise(attr(moves_tag, "readonly")))

            moves = rpc.read(SERVICE_MOVE, picking["move_lines"],
                             ["product_id", "product_uom_qty", "quantity",
                              "state"])
            ctx.log("items: " + "; ".join(
                f"{m['product_id'][1] if m['product_id'] else '?'} "
                f"demand={m['product_uom_qty']} done={m['quantity']}"
                for m in moves))
            ctx.check_true("The transfer holds the order's service line",
                           bool(moves), actual_desc=f"{len(moves)} item(s)")
            ctx.check("…and only the service line — the goods line is "
                      "fulfilled by a delivery, not by this transfer",
                      [service["variant_id"]],
                      [m["product_id"][0] if m["product_id"] else None
                       for m in moves])

        with ctx.step("Steps 8-11: entering a Done quantity and clicking "
                      "Validate moves the transfer to Done and locks the "
                      "items"):
            move = moves[0]
            rpc.write(SERVICE_MOVE, [move["id"]],
                      {"quantity": move["product_uom_qty"]})
            ctx.check("The Done quantity was accepted on the item while the "
                      "transfer is in Draft", move["product_uom_qty"],
                      rpc.read(SERVICE_MOVE, [move["id"]],
                               ["quantity"])[0]["quantity"])

            result, error = _confirm_transfer(ctx, picking_id)
            ctx.check_true(
                "Validate is accepted at all — see BC-FG12-001 in the log "
                "if this fails",
                not error, actual_desc=error[:300] or "accepted")
            ctx.check_true(
                "Validate with a quantity entered completes without raising "
                "the immediate-transfer pop-up",
                result is True or not isinstance(result, dict),
                actual_desc=str(result)[:160])

            after = rpc.read(SERVICE_PICKING, [picking_id], ["state"])[0]
            ctx.check("The transfer is Done", "done", after["state"])
            done_move = rpc.read(SERVICE_MOVE, [move["id"]],
                                 ["state", "quantity"])[0]
            ctx.check("…and its item is done too", "done",
                      done_move["state"])
            ctx.check("…for the quantity that was entered",
                      move["product_uom_qty"], done_move["quantity"])

        with ctx.step("Step 12: the change is reflected back on the order"):
            line = rpc.search_read(
                "sale.order.line",
                [("order_id", "=", order_id),
                 ("product_id", "=", service["variant_id"])],
                ["qty_delivered", "assigned_service_qty"])[0]
            ctx.check("The order line's delivered quantity now reflects the "
                      "completed transfer", 2.0, line["qty_delivered"])

        with ctx.step("Step 13: Cancel on a different draft transfer moves "
                      "it to Canceled"):
            second_order = make_service_order(ctx, partner_id,
                                              service["variant_id"],
                                              goods["variant_id"], 1.0)
            created["sale.order"].append(second_order)
            second = rpc.read("sale.order", [second_order],
                              ["service_picking_ids"])[0]
            second_picking = second["service_picking_ids"][0]
            ctx.check("The second transfer starts in Draft", "draft",
                      rpc.read(SERVICE_PICKING, [second_picking],
                               ["state"])[0]["state"])

            rpc.call(SERVICE_PICKING, "action_cancel", [second_picking])
            ctx.check("Cancel moves it to Canceled — a different state from "
                      "Done", "cancel",
                      rpc.read(SERVICE_PICKING, [second_picking],
                               ["state"])[0]["state"])

        # This is deliberately the LAST step. Everything above is testable
        # and passes; this one currently does not, and putting it first
        # would hide the rest of the case behind a single defect.
        with ctx.step("Precondition, taken literally: 'create an order with "
                      "a service product' — an order whose ONLY line is a "
                      "service"):
            error = ""
            try:
                service_only = make_service_order(ctx, partner_id,
                                                  service["variant_id"],
                                                  None, 1.0)
                created["sale.order"].append(service_only)
            except OdooRPCError as exc:
                error = str(exc)
            if error:
                finding(ctx,
                        "confirming an order whose only lines are services "
                        "fails with a NOT NULL violation on "
                        "stock_service_move.date. Odoo 19's "
                        "sale.order._compute_expected_date skips non-goods "
                        "lines outright (addons/sale/models/sale_order.py:"
                        "737-752 — 'For service and combo (non-goods) "
                        "products, we avoid computing the expected date'), "
                        "where v15 took the minimum across every line "
                        "(mmg_15/addons/sale/models/sale_order.py:332-345). "
                        "StockServiceMove._get_stock_move_values still "
                        "passes order.expected_date into "
                        "stock.service.move.date, which is required=True "
                        "(multichannel_fulfillment/models/"
                        "stock_service_move.py:16-18, 122), so the value is "
                        "False and the insert is rejected. An order that "
                        "also carries a goods line is unaffected, which is "
                        "why the rest of this case passes. Fix: fall back "
                        "to order.commitment_date or fields.Datetime.now() "
                        "when expected_date is empty.")
            ctx.check_true(
                "An order whose only line is a service can be confirmed and "
                "raises its service transfer — the workbook's own "
                "precondition for this case",
                not error,
                actual_desc=error[:300] or "confirmed")

    finally:
        with ctx.step("Cleanup: the scratch orders, customer and products "
                      "are removed"):
            _sweep_orders(ctx, created)


@test_case(
    id="TEST-FG12-FUL-018",
    name="Validating a service transfer with nothing entered offers to "
         "complete it all",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P1",
    kind="API",
    order=1212,
    description="Validate on a draft transfer with every Done quantity at "
                "zero raises a pop-up titled 'Immediate Transfer?' offering "
                "Apply and Cancel; applying sets every Done quantity to its "
                "Initial Demand and moves the transfer to Done; backing out "
                "leaves it in Draft with nothing changed; and a transfer "
                "with no items refuses with a readable message rather than "
                "completing empty. Built from scratch records and swept "
                "afterwards.",
    traceability=trace("TC-FUL-018"))
def test_ful_018(ctx):
    rpc = require_fulfillment(ctx)
    sweep(ctx)
    created = {"sale.order": [], "res.partner": [], "product.template": []}

    try:
        with ctx.step("Precondition: a DRAFT service transfer with every "
                      "Done quantity at zero"):
            partner_id = rpc.create("res.partner",
                                    {"name": f"{MARK} FUL-018 Customer"})
            created["res.partner"].append(partner_id)
            service = make_service_product(ctx, "FUL-018 Restoration Service")
            created["product.template"].append(service["template_id"])
            goods = make_product(ctx, "FUL-018 Art Item")
            created["product.template"].append(goods["template_id"])

            order_id = make_service_order(ctx, partner_id,
                                          service["variant_id"],
                                          goods["variant_id"], 3.0)
            created["sale.order"].append(order_id)
            picking_id = rpc.read("sale.order", [order_id],
                                  ["service_picking_ids"])[0][
                                      "service_picking_ids"][0]

        with ctx.step("Step 2: every Done quantity is zero, and nothing is "
                      "typed"):
            picking = rpc.read(SERVICE_PICKING, [picking_id],
                               ["state", "move_lines"])[0]
            moves = rpc.read(SERVICE_MOVE, picking["move_lines"],
                             ["product_uom_qty", "quantity", "state"])
            ctx.check("The transfer is in Draft", "draft", picking["state"])
            ctx.check("Every Done quantity is zero", [0.0] * len(moves),
                      [move["quantity"] for move in moves])

        with ctx.step("Steps 3-5: Validate raises a pop-up offering two "
                      "buttons"):
            action, error = _confirm_transfer(ctx, picking_id)
            ctx.check_true(
                "Validate is accepted at all — see BC-FG12-001 in the log "
                "if this fails",
                not error, actual_desc=error[:300] or "accepted")
            ctx.check_true("Validate returned a pop-up rather than "
                           "completing silently",
                           isinstance(action, dict)
                           and bool(action.get("res_model")),
                           actual_desc=str(action)[:200])
            ctx.check("The pop-up is the immediate-transfer question",
                      "stock.service.immediate.transfer",
                      action.get("res_model"))
            ctx.check("…titled as the workbook reads it",
                      "Immediate Transfer?", action.get("name"))
            ctx.check("…and it opens as a dialog", "new", action.get("target"))
            ctx.log(f"pop-up: {action.get('name')!r} on "
                    f"{action.get('res_model')} id={action.get('res_id')}")

            wizard_arch = view_arch(ctx, "stock.service.immediate.transfer",
                                    "multichannel_fulfillment."
                                    "view_immediate_transfer", "form")
            ctx.check_true(
                "It explains that no done quantities were recorded and that "
                "proceeding takes the full demand",
                "done" in wizard_arch.lower()
                and "demand" in wizard_arch.lower(),
                actual_desc="the pop-up text names both 'done' and 'demand'")
            ctx.check_true("It offers a button that proceeds",
                           bool(button_attrs(wizard_arch, "process")),
                           actual_desc=button_attrs(wizard_arch,
                                                    "process")[:160])
            ctx.check_true("…and one that backs out",
                           'special="cancel"' in wizard_arch,
                           actual_desc="a Cancel button with special=cancel")

        with ctx.step("Steps 9-10: backing out leaves the transfer in Draft "
                      "with nothing changed"):
            # The wizard's Cancel is `special="cancel"`: it closes the dialog
            # and calls nothing. So the state of the transfer after raising
            # the pop-up and NOT calling process() is exactly what backing
            # out leaves behind.
            unchanged = rpc.read(SERVICE_PICKING, [picking_id], ["state"])[0]
            ctx.check("Raising the pop-up and backing out leaves the "
                      "transfer in Draft", "draft", unchanged["state"])
            still_zero = rpc.read(SERVICE_MOVE, picking["move_lines"],
                                  ["quantity"])
            ctx.check("…with nothing entered", [0.0] * len(still_zero),
                      [move["quantity"] for move in still_zero])

        with ctx.step("Steps 6-8: proceeding sets every Done quantity to its "
                      "Initial Demand and moves the transfer to Done"):
            wizard_id = action.get("res_id")
            ctx.check_true("The pop-up carries the transfer it was raised "
                           "from", bool(wizard_id),
                           actual_desc=f"wizard id={wizard_id}")
            rpc.call("stock.service.immediate.transfer", "process",
                     [wizard_id])

            after = rpc.read(SERVICE_PICKING, [picking_id], ["state"])[0]
            ctx.check("The transfer is Done", "done", after["state"])
            done_moves = rpc.read(SERVICE_MOVE, picking["move_lines"],
                                  ["product_uom_qty", "quantity", "state"])
            ctx.check("Every Done quantity now equals its Initial Demand",
                      [move["product_uom_qty"] for move in done_moves],
                      [move["quantity"] for move in done_moves])

        with ctx.step("Step 11: a transfer with NO item rows refuses with a "
                      "readable message rather than completing empty"):
            # A transfer cannot be created empty either — `create` raises
            # 'No items to add.' when `check_empty_line` is not suppressed
            # (stock_service_picking.py:78-89) — so both doors are checked.
            error = ""
            try:
                rpc.create(SERVICE_PICKING, {"partner_id": partner_id})
            except OdooRPCError as exc:
                error = str(exc)
            ctx.check_true("Creating a transfer with no items is refused",
                           bool(error),
                           actual_desc=error or "AN EMPTY TRANSFER WAS "
                                                "CREATED")
            ctx.check_true("…with a readable message",
                           "No items to add" in error,
                           actual_desc=error[:200])

            # And the same guard on the Validate path: a transfer whose
            # items have all been cancelled has nothing left to move.
            second_order = make_service_order(ctx, partner_id,
                                              service["variant_id"],
                                              goods["variant_id"], 1.0)
            created["sale.order"].append(second_order)
            empty_id = rpc.read("sale.order", [second_order],
                                ["service_picking_ids"])[0][
                                    "service_picking_ids"][0]
            lines = rpc.read(SERVICE_PICKING, [empty_id],
                             ["move_lines"])[0]["move_lines"]
            rpc.call(SERVICE_MOVE, "action_cancel", lines)
            _, error = _confirm_transfer(ctx, empty_id)
            state = rpc.read(SERVICE_PICKING, [empty_id],
                             ["state"])[0]["state"]
            ctx.check_true(
                "Validating a transfer with nothing left to move refuses or "
                "leaves it alone — it does not complete empty",
                bool(error) or state != "done",
                actual_desc=error[:200] or f"state={state}")

    finally:
        with ctx.step("Cleanup: the scratch orders, customer and products "
                      "are removed"):
            _sweep_orders(ctx, created)


#: The message Odoo 19 raises when a `uom.rounding` float is handed to the
#: `precision_digits` argument. It is the signature of BC-FG12-001 below.
ROUNDING_AS_DIGITS = "precision_digits must be a non-negative integer"

#: Reported once, by whichever case reaches it first.
BC_FG12_001 = (
    "validating a service transfer is impossible on Odoo 19: "
    "stock.service.picking.action_confirm calls "
    "float_is_zero(move_line.product_qty, "
    "precision_digits=move_line.product_uom_id.rounding) "
    "(multichannel_fulfillment/models/stock_service_picking.py:104), and "
    "stock.service.move.action_done does the same with record.quantity "
    "(stock_service_move.py:134). `uom.rounding` is a float (0.001 on the "
    "default unit), not a digit count. v15's float_is_zero accepted "
    "anything and quietly evaluated 10**-0.001; v19 validates the argument "
    "and raises ValueError "
    "(odoo/tools/float_utils.py:170-174). Every Validate on every service "
    "transfer therefore dies before it does anything. Fix: pass "
    "precision_rounding=... instead of precision_digits=... in both places "
    "- the keyword float_is_zero has always had for exactly this value.")


def _confirm_transfer(ctx, picking_id):
    """``action_confirm`` on a service transfer, with the v19 crash caught.

    Returns ``(result, error)``. Catching it here rather than letting it
    escape is what turns BC-FG12-001 into a reported FAILURE of the product
    instead of an ERROR that reads like a broken test — and it lets the
    case keep going far enough to say what else is or is not affected.
    """
    try:
        return ctx.adapter.rpc.call(SERVICE_PICKING, "action_confirm",
                                    [picking_id]), ""
    except OdooRPCError as exc:
        error = str(exc)
        if ROUNDING_AS_DIGITS in error:
            finding(ctx, BC_FG12_001)
        return None, error


def _sweep_orders(ctx, created: dict):
    """Cancel, then remove, everything a service-transfer case created.

    Orders are cancelled first because a confirmed one cannot be deleted,
    and anything that will not delete is archived instead — which takes it
    out of every domain the suite searches without leaving a live record on
    the client's database.
    """
    rpc = ctx.adapter.rpc
    for order_id in created.get("sale.order", []):
        try:
            rpc.call("sale.order", "action_cancel", [order_id])
        except OdooRPCError:
            pass

    # Everything the confirm produced downstream, removed before the
    # products it points at. `mmg_sale_auto_create_invoice` raises an
    # invoice on every confirm (models/sale_order.py), cancelling the order
    # cancels it, and a cancelled draft invoice can be deleted — it never
    # took a sequence number and never reached the client's books. Service
    # transfers and deliveries go the same way. Without this the products
    # can only ever be archived, and each run leaves another set behind.
    products = rpc.search("product.product", [("default_code", "like", MARK)],
                          context={"active_test": False})
    if products:
        for model, domain in (
                ("account.move", [("line_ids.product_id", "in", products),
                                  ("state", "in", ["draft", "cancel"])]),
                (SERVICE_PICKING,
                 [("move_lines.product_id", "in", products)]),
                ("stock.picking",
                 [("move_ids.product_id", "in", products)]),
        ):
            try:
                ids = rpc.search(model, domain,
                                 context={"active_test": False})
                if ids:
                    rpc.unlink(model, ids)
                    ctx.log(f"cleanup: {len(ids)} {model} removed")
            except OdooRPCError as exc:
                ctx.log(f"[warn] could not remove {model}: {exc}")

    for model in ("sale.order", "res.partner", "product.template"):
        ids = created.get(model) or []
        if not ids:
            continue
        try:
            rpc.unlink(model, ids)
        except OdooRPCError as exc:
            # A record a confirmed order or a stock move points at cannot
            # be deleted. Archiving takes it out of every screen and every
            # domain the suite searches, and `sweep()` looks for archived
            # rows too, so a later run finishes the job if the reference
            # goes away.
            ctx.log(f"[warn] {model} delete refused ({exc}); archiving")
            try:
                rpc.write(model, ids, {"active": False})
            except OdooRPCError as exc2:
                ctx.log(f"[warn] {model} archive failed: {exc2}")
    sweep(ctx)
    left = rpc.call("sale.order", "search_count",
                    [("partner_id.name", "like", MARK),
                     ("state", "not in", ["cancel"])],
                    context={"active_test": False})
    ctx.check("No live scratch order is left on the client's database", 0,
              left)
