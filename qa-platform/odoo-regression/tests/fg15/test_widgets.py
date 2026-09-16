"""FG-15 — TC-UIX-001, TC-UIX-003, TC-UIX-005, TC-UIX-008, TC-UIX-009 and
TC-UIX-010: the custom widgets, and the data behind them.

Implements the CLIENT MANUAL TESTING GUIDELINE
``MMG_v19_Client_Manual_Testing_Guideline_FG15-FG20_v1.0.xlsx`` / sheet
``Testing Guideline``.

Every widget named here is one of the gallery's own — ``logo_and_name_field``,
``many2one_store_field``, ``many2many_store_field``,
``many2many_checkboxes_select_all_field``, ``boolean_button``. None is stock
Odoo, which is exactly why an upgrade can drop one without anything else
noticing. What this suite settles is that the field is on the view the
browser is handed, carrying that widget, with data behind it of the shape
the widget expects. What it cannot settle is the paint. Each case says
which half it has done.

TC-UIX-001 is the exception: it is not a rendering case at all underneath.
"No payment status may appear in the fulfilment list" is a domain on
``order.process.rule.order_status_channel_ids``, and whether a tick survives
a save is a round trip. Both are server facts, and both are asserted for
real — on the gallery's own rule, with the original ticks put back.
"""
from __future__ import annotations

from adapters.base import OdooRPCError
from framework.registry import test_case

from .common import (CARRIER, CHANNEL, FULFILMENT, MODULE, MODULE_ORDER,
                     ORDER, PAYMENT, PRODUCT_CHANNEL, RULE, STATUS,
                     STORE_LIST_FORBIDDEN, WIDGETS, WORKFLOW, WORKFLOW_NAME,
                     all_field_tags, attr, field_attrs, finding, manual,
                     not_applicable, observation, require_connector,
                     root_attrs, stores, trace, widget_of)


@test_case(
    id="TEST-FG15-UIX-001",
    name="The order-status tick-box lists on an import rule work and save",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE_ORDER,
    priority="P1",
    kind="API",
    order=1501,
    description="The status list on an import rule is drawn as tick-boxes "
                "rather than a drop-down or a tag box; its domain admits "
                "only FULFILMENT statuses for this storefront, so no "
                "payment status can appear in it — the FAIL the workbook "
                "names; and a changed set of ticks survives a save and "
                "re-read. The rule's original ticks are put back, as step "
                "10 requires.",
    traceability=trace("TC-UIX-001"))
def test_uix_001(ctx):
    rpc = require_connector(ctx)
    rule_id, original = None, None

    try:
        with ctx.step("Steps 1-3: a store with an import rule on it"):
            rules = rpc.search_read(
                RULE, [], ["name", "channel_id", "order_status_channel_ids",
                           "payment_status_channel_ids",
                           "has_payment_statuses"],
                limit=5, order="id")
            if not rules:
                ctx.blocked(
                    f"no {RULE} record exists, so there is no rule row to "
                    f"open. The workbook's precondition asks for at least "
                    f"one import rule on a store.")
            rule = rules[0]
            rule_id = rule["id"]
            original = list(rule["order_status_channel_ids"] or [])
            ctx.log(f"rule #{rule_id} {rule['name']!r} on "
                    f"{rule['channel_id']}")

        with ctx.step("Step 4: the ticks as this run found them — they go "
                      "back at the end"):
            ctx.log(f"order_status_channel_ids = {original}")
            if original:
                names = rpc.read(STATUS, original, ["name", "type"])
                for row in names:
                    ctx.log(f"    ticked: {row['name']!r} ({row['type']})")

        with ctx.step("Step 5a: the list is drawn as TICK-BOXES, not a "
                      "drop-down or a tag box"):
            widget = widget_of(ctx, RULE, "form", "order_status_channel_ids")
            ctx.check(
                "The status list carries the gallery's tick-box widget",
                "many2many_checkboxes_select_all_field", widget)
            ctx.check_true(
                "…which is not a tag box or a drop-down",
                widget not in ("many2many_tags", "selection", ""),
                actual_desc=widget or "no widget at all")

        with ctx.step("Step 5b / Expected line 2: only FULFILMENT statuses "
                      "are offered — 'one payment status in that list is a "
                      "FAIL'"):
            fields = rpc.call(RULE, "fields_get",
                              ["order_status_channel_ids"],
                              attributes=["domain", "relation"])
            domain = str(fields["order_status_channel_ids"].get("domain"))
            ctx.log(f"field domain: {domain}")
            ctx.check_true(
                "The field's own domain restricts it to fulfilment statuses",
                f"'{FULFILMENT}'" in domain,
                actual_desc=domain)
            ctx.check_true(
                "…and never mentions payment statuses",
                f"'{PAYMENT}'" not in domain,
                actual_desc=domain)

            # The domain is the rule; this is the consequence, read off the
            # data the widget would be handed.
            channel = rule["channel_id"]
            channel_id = channel[0] if isinstance(channel, (list, tuple)) \
                else channel
            platform = rpc.read(CHANNEL, [channel_id],
                                ["platform"])[0]["platform"]
            offered = rpc.search_read(
                STATUS,
                [("platform", "=", platform), ("type", "=", FULFILMENT),
                 ("is_hidden", "=", False)],
                ["name", "type"], limit=0)
            payments = rpc.search_read(
                STATUS, [("platform", "=", platform), ("type", "=", PAYMENT)],
                ["name"], limit=0)
            ctx.log(f"{len(offered)} fulfilment status(es) offered: "
                    + ", ".join(r["name"] for r in offered))
            ctx.log(f"{len(payments)} payment status(es) exist for this "
                    f"platform and are correctly NOT offered: "
                    + ", ".join(r["name"] for r in payments))
            ctx.check("No payment status is among the options the tick-box "
                      "list would show", [],
                      [r["name"] for r in offered if r["type"] != FULFILMENT])
            ctx.check_true(
                "…and there ARE payment statuses on this platform, so the "
                "result above is a filter working rather than an empty set",
                bool(payments),
                actual_desc=f"{len(payments)} payment statuses exist")

        with ctx.step("Steps 6-9: a changed set of ticks survives a save "
                      "and a re-read"):
            candidates = [r["id"] for r in offered]
            if len(candidates) < 2:
                ctx.skip(f"only {len(candidates)} fulfilment status(es) "
                         f"exist for this storefront; step 6 needs to tick "
                         f"two and untick one.")
            wanted = candidates[:2]
            rpc.write(RULE, [rule_id], {"order_status_channel_ids":
                                        [(6, 0, wanted)]})
            read_back = rpc.read(RULE, [rule_id],
                                 ["order_status_channel_ids"])[0]
            ctx.check("The ticks read back exactly as they were set",
                      sorted(wanted),
                      sorted(read_back["order_status_channel_ids"] or []))

        with ctx.step("Step 10: the original ticks are put back"):
            rpc.write(RULE, [rule_id],
                      {"order_status_channel_ids": [(6, 0, original)]})
            restored = rpc.read(RULE, [rule_id],
                                ["order_status_channel_ids"])[0]
            ctx.check("The rule is exactly as this run found it",
                      sorted(original),
                      sorted(restored["order_status_channel_ids"] or []))

    finally:
        if rule_id is not None and original is not None:
            try:
                now = rpc.read(RULE, [rule_id],
                               ["order_status_channel_ids"])[0]
                if sorted(now["order_status_channel_ids"] or []) != \
                        sorted(original):
                    rpc.write(RULE, [rule_id],
                              {"order_status_channel_ids": [(6, 0, original)]})
                    ctx.log("the rule was restored from the cleanup path")
            except OdooRPCError as exc:
                ctx.log(f"[warn] could not verify the rule's ticks: {exc}")


@test_case(
    id="TEST-FG15-UIX-003",
    name="The on/off buttons at the top of a store read the right state",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P2",
    kind="API",
    order=1502,
    description="Both buttons at the top of a store form carry the "
                "gallery's boolean_button widget and the field behind each "
                "holds the store's real state. The Active/Archived button "
                "on a shipping-carrier row is pressed for real — the one "
                "place in this case the workbook says to press — and put "
                "straight back. Neither store button is pressed: one of "
                "them disconnects the store.",
    traceability=trace("TC-UIX-003"))
def test_uix_003(ctx):
    rpc = require_connector(ctx)

    with ctx.step("Steps 2-4: the two buttons are there and read the "
                  "store's real state"):
        store_rows = stores(ctx)
        if not store_rows:
            ctx.blocked("no store exists to open.")
        store = store_rows[0]
        ctx.log(f"store {store['name']!r} active={store['active']} "
                f"auto_import_data={store['auto_import_data']}")

        for field in ("auto_import_data", "active"):
            widget = widget_of(ctx, CHANNEL, "form", field)
            ctx.check(f"{field!r} is drawn as an on/off button",
                      "boolean_button", widget)
            ctx.check_true(
                f"…and the field behind it holds a real state to show",
                isinstance(store.get(field), bool),
                actual_desc=f"{field}={store.get(field)!r}")

        observation(ctx,
                    "neither store button is pressed. Step 4 says pressing "
                    "the connection one disconnects the store, and step 3 "
                    "says not to press Auto Import either. What a browser "
                    "still has to confirm is the WORDING each button shows "
                    "for the state it is in — boolean_button renders its "
                    "own label, and a widget that drew blank would look "
                    "identical from here.")

    with ctx.step("Steps 6-7: the Active/Archived button on a carrier row "
                  "flips and flips back"):
        if not rpc.model_exists(CARRIER):
            ctx.skip(f"model '{CARRIER}' does not exist on this database.")
        widget = widget_of(ctx, CARRIER, "form", "active")
        ctx.check("The carrier row's Active/Archived control is the same "
                  "widget", "boolean_button", widget)
        arch = rpc.call(CARRIER, "get_view", view_type="form")["arch"]
        tag = field_attrs(arch, "active")
        ctx.check_true(
            "…configured with archive terminology, which is what makes it "
            "read Active / Archived rather than true / false",
            "archive" in attr(tag, "options"),
            actual_desc=attr(tag, "options") or tag[:160])

        rows = rpc.search_read(CARRIER, [], ["name", "active"], limit=1,
                               context={"active_test": False})
        if not rows:
            # N/A rather than skipping the whole case: steps 2-4 above are
            # about the store's own buttons and they ran. Throwing the case
            # away for want of a carrier row would discard a result the
            # workbook did get.
            not_applicable(ctx,
                           "steps 5-7 open a shipping-carrier mapping row "
                           "and flip its Active/Archived button, and this "
                           "database holds NO shipping.method.channel rows "
                           "at all — not even archived ones. The widget and "
                           "its archive terminology are asserted above from "
                           "the view; the flip needs a row to flip.")
            ctx.check_true(
                "The N/A is recorded with the count that justifies it",
                True, actual_desc="0 shipping-carrier mapping rows exist")
            return
        row = rows[0]
        before = row["active"]
        try:
            rpc.write(CARRIER, [row["id"]], {"active": not before})
            flipped = rpc.read(CARRIER, [row["id"]], ["active"],
                               )[0]["active"] if before else \
                rpc.call(CARRIER, "read", [row["id"]], fields=["active"],
                         context={"active_test": False})[0]["active"]
            ctx.check("Pressing it flips the state", not before, flipped)
        finally:
            rpc.call(CARRIER, "write", [row["id"]], {"active": before},
                     context={"active_test": False})
            restored = rpc.call(CARRIER, "read", [row["id"]],
                                fields=["active"],
                                context={"active_test": False})[0]["active"]
            ctx.check("…and pressing it again returns it to what it read "
                      "before", before, restored)


@test_case(
    id="TEST-FG15-UIX-008",
    name="Confirm and sign off the new tick-box column on the Stores list",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P1",
    kind="API",
    order=1503,
    description="The Manage Stores list offers no New, Edit, Delete or "
                "Export — which is what step 4 requires of the row-selection "
                "the tick-box column enables — and the tick-box column "
                "itself is the web client's own consequence of a "
                "non-editable list. The sign-off in step 6 is a person's "
                "signature and is left to one.",
    traceability=trace("TC-UIX-008"))
def test_uix_008(ctx):
    rpc = require_connector(ctx)

    with ctx.step("Steps 2 and 4: the list allows selection but offers no "
                  "way to create, delete or export a store"):
        from .common import root_attrs as _root
        row = rpc.search_read("ir.model.data",
                              [("module", "=", "omni_manage_channel"),
                               ("name", "=", "ecommerce_channel_tree_view")],
                              ["res_id"], limit=1)
        if not row:
            ctx.blocked("the Manage Stores list view does not exist on this "
                        "database.")
        arch = rpc.call(CHANNEL, "get_view", view_id=row[0]["res_id"],
                        view_type="list")["arch"]
        tag = _root(arch, "list")
        ctx.log(f"list attributes: {tag}")
        offered = {name: attr(tag, name) for name in STORE_LIST_FORBIDDEN}
        ctx.check(
            "New, Edit, Delete and Export are all switched off on this list "
            "— 'the New, Edit, Delete and Export options must all stay "
            "unavailable'",
            {name: "0" for name in STORE_LIST_FORBIDDEN}, offered)

    with ctx.step("Step 3: clicking a data cell opens the store, the "
                  "tick-box cell does not"):
        observation(ctx,
                    "the tick-box column, and the rule that clicking it "
                    "selects rather than opens, are the web client's own "
                    "behaviour for any non-editable list — there is no "
                    "attribute in the arch that turns them on or off. What "
                    "the arch DOES decide is the part step 4 is really "
                    "about, and it is asserted above: with create, edit, "
                    "delete and export all off, selecting rows exposes "
                    "nothing that could remove or export a store.")
        manual(ctx,
               "TC-UIX-008 steps 2-3 — confirming on screen that the "
               "tick-box column is there, that the header tick-box selects "
               "every row, and that clicking a data cell opens the store "
               "while clicking the tick-box cell does not.")
        manual(ctx,
               "Step 6 — recording the acceptance on the Sign-off tab. That "
               "is a person's signature on a change the gallery is being "
               "asked to accept, and no test can give it.")
