"""FG-12 — Fulfillment & Inventory Sync. Shared gates and fixtures.

Source of truth is the CLIENT MANUAL TESTING GUIDELINE
``MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0.xlsx``, sheet
``Testing Guideline`` — the copy pulled from the client's Google Drive on
2026-09-16. Cases TC-FUL-001 … TC-FUL-018.

The store is live, so every fixture is scoped to a product nobody sells
-----------------------------------------------------------------------
``ecommerce.channel`` id 3 on this database is the gallery's real Shopify
store: ``is_enable_inventory_sync`` is on, one warehouse is ticked, and a
single global 100% rule governs what gets published. Most of FG-12 is about
adding a rule to that store and watching the published quantity move — and
a rule added to a live store governs real listings for as long as it
exists.

So every rule this suite creates is scoped with ``applied_on =
'0_product_variant'`` onto a scratch product it created itself
(:func:`make_product`). ``IncludeInventorySync.is_product_matching`` matches
a variant rule by ``product_id`` equality
(``multichannel_fulfillment/models/include_inventory_sync.py:137-139``), so
such a rule can never match one of the gallery's items, whatever order the
rules are evaluated in. The blast radius is a product with no listing.

What that buys, and what it does not
------------------------------------
It buys the arithmetic and every guard, asserted for real:
``calc_available_qty`` is a pure function of the rule
(``include_inventory_sync.py:158-166``) and the four ``@api.constrains``
are the refusals the workbook's steps 8, 9, 11 and 12 ask about.

It does not buy the end-to-end reading of the *Available* figure on a
listing, because that needs a ``product.channel.variant`` mapping, and a
mapping is created by importing from the store. Where the workbook says
"reload the listing and read Available", this suite asserts the function
that produces that number and reconciles one of the gallery's real listings
against it read-only — and prints what is left for a human.

Nothing here writes to the store's own configuration except one probe
in TC-FUL-001 — a write that the ``check_active_warehouses`` constraint
must refuse — and that probe restores what it found before it asserts
anything. It is deliberate and is explained where it lives.

The goods line on every service-transfer fixture
------------------------------------------------
:func:`make_service_order` puts a **storable** line on the order beside the
service line, and that is not padding. Odoo 19's
``sale.order._compute_expected_date`` skips non-goods lines outright
(``addons/sale/models/sale_order.py:737-752`` — *"For service and combo
(non-goods) products, we avoid computing the expected date"*), where v15
took the minimum across every line
(``mmg_15/addons/sale/models/sale_order.py:332-345``). The connector's
``StockServiceMove._get_stock_move_values`` still passes
``sale_line_id.order_id.expected_date`` into ``stock.service.move.date``,
which is ``required=True``
(``multichannel_fulfillment/models/stock_service_move.py:16-18, 122``), so
on an order whose only lines are services the value is ``False`` and
confirming it dies with a NOT NULL violation on ``stock_service_move.date``.

TC-FUL-017 probes that directly and reports it. The other fixtures carry a
goods line so the rest of the case can still be tested, rather than every
service-transfer assertion collapsing into one repeated defect.
"""
from __future__ import annotations

import re

from adapters.base import OdooRPCError

# --------------------------------------------------------------- identity
FEATURE = "FG-12 Fulfillment & Inventory Sync"
WORKFLOW = "FG-12"
WORKFLOW_NAME = "Fulfillment & Inventory Sync"
MODULE = "multichannel_fulfillment"

WORKBOOK = "MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0.xlsx"
SHEET = "Testing Guideline"

MARK = "FG12-AUTOMATED-PROBE"


def trace(tc_ids, user_story: str = "") -> dict:
    return {
        "tc_ids": tc_ids if isinstance(tc_ids, list) else [tc_ids],
        "feature": FEATURE,
        "user_story": user_story,
        "source": f"{WORKBOOK} / {SHEET}",
    }


# ------------------------------------------------------ workbook constants
CHANNEL = "ecommerce.channel"
INCLUDE = "include.inventory.sync"
EXCLUDE = "exclude.inventory.sync"
PICKING = "stock.picking"
SERVICE_PICKING = "stock.service.picking"
SERVICE_MOVE = "stock.service.move"
PRODUCT_CHANNEL = "product.channel"
PRODUCT_CHANNEL_VARIANT = "product.channel.variant"

#: ``include.inventory.sync.applied_on`` — the four levels TC-FUL-002 step 4
#: asks the tester to confirm. The numeric prefixes are the precedence:
#: ``_order`` is ``applied_on asc``, so a variant rule is considered before
#: a product rule, then a category, then all products
#: (``include_inventory_sync.py:19-31, 118-124``).
INCLUDE_LEVELS = ["0_product_variant", "1_product", "2_product_category",
                  "3_global"]
INCLUDE_LABELS = {"0_product_variant": "Product Variant",
                  "1_product": "Product",
                  "2_product_category": "Product Category",
                  "3_global": "All Products"}

#: ``exclude.inventory.sync.applied_on`` — three levels, no global one.
#: TC-FUL-005 step 4 says so: a category, a product and a variant.
EXCLUDE_LEVELS = ["0_product_variant", "1_product", "2_product_category"]
EXCLUDE_LABELS = {"0_product_variant": "Product Variant",
                  "1_product": "Product",
                  "2_product_category": "Product Category"}

#: The refusal messages, verbatim (``include_inventory_sync.py:10-15`` and
#: ``:129``, ``ecommerce_channel.py:60-76``).
MSG_PERCENTAGE = "Please enter a percentage between 0.01% and 100.00%."
MSG_MAXIMUM = "Maximum must be greater than 0."
MSG_MINIMUM = "Minimum must be at least 0."
MSG_MIN_BELOW_MAX = "Minimum must be less than maximum."
MSG_NO_WAREHOUSE = "Please select at least one warehouse to sync inventory."
MSG_NO_INCLUDE_RULE = ('There must be at least one rule for "Inventory '
                       'Export Rules".')
MSG_NO_EXPORT_SHIPMENT = ("You cannot update to store. Please check your "
                          "settings in store settings and try again.")

#: Inventory Sync Settings, the group TC-FUL-001 walks.
INVENTORY_SETTINGS = ("is_enable_inventory_sync",
                      "is_allow_manual_bulk_inventory_sync",
                      "last_all_inventory_sync", "active_warehouse_ids",
                      "default_warehouse_id")

#: The delivery fields TC-FUL-013 reads
#: (``multichannel_fulfillment/models/stock_picking.py:26-44``).
DELIVERY_FIELDS = ("requested_carrier", "carrier_name", "shipping_cost",
                   "shipping_date", "carrier_id", "carrier_tracking_ref",
                   "id_on_channel", "is_update_to_channel_needed")

#: ``stock.service.picking.state`` — TC-FUL-017 step 6 reads the status bar.
SERVICE_STATES = ("draft", "done", "cancel")
SERVICE_STATE_LABELS = {"draft": "Draft", "done": "Done",
                        "cancel": "Canceled"}

V19_ONLY = ("FG-12 describes the Odoo 19 store configuration and delivery "
            "screens; the cancelled-delivery read-only behaviour TC-FUL-013 "
            "checks is new in v19")


# ------------------------------------------------------------------- gates
def require_v19(ctx):
    if ctx.env.version != "19":
        ctx.blocked(f"{V19_ONLY} (current target: {ctx.env.name}).")


def require_fulfillment(ctx):
    require_v19(ctx)
    rpc = ctx.adapter.rpc
    for model in (CHANNEL, INCLUDE, EXCLUDE):
        if not rpc.model_exists(model):
            ctx.blocked(
                f"model '{model}' does not exist on this database — "
                f"'{MODULE}' is not installed, so FG-12's Inventory "
                f"Configuration tab does not exist either.")
    return rpc


def acting_channel(ctx) -> dict:
    """The store FG-12 configures. Read; written only where a case says so."""
    rpc = ctx.adapter.rpc
    rows = rpc.search_read(
        CHANNEL, [],
        ["name", "platform", "company_id", "active"] +
        list(INVENTORY_SETTINGS) + ["auto_export_shipment_to_store"],
        limit=2, order="id")
    if not rows:
        ctx.blocked("no ecommerce.channel exists on this database, so there "
                    "is no Inventory Configuration tab to open.")
    if len(rows) > 1:
        ctx.log(f"more than one store configured; using {rows[0]['name']!r}")
    return rows[0]


# ---------------------------------------------------------------- evidence
def manual(ctx, text: str):
    ctx.log(f"RESIDUAL MANUAL STEP — {text}")


def observation(ctx, text: str):
    ctx.log(f"OBSERVATION — {text}")


def finding(ctx, text: str):
    ctx.log(f"FINDING — {text}")


# ------------------------------------------------------------ view arches
def ref(rpc, xmlid: str):
    module, _, name = xmlid.partition(".")
    rows = rpc.search_read("ir.model.data",
                           [("module", "=", module), ("name", "=", name)],
                           ["res_id", "model"], limit=1)
    return rows[0] if rows else None


def view_arch(ctx, model: str, xmlid: str, view_type: str) -> str:
    rpc = ctx.adapter.rpc
    row = ref(rpc, xmlid)
    if not row:
        ctx.blocked(f"view '{xmlid}' does not exist on this database.")
    return rpc.call(model, "get_view", view_id=row["res_id"],
                    view_type=view_type)["arch"]


def _tag_attrs(arch: str, tag: str, name: str, occurrence: int = 0) -> str:
    matches = re.findall(rf'<{tag}[^>]*name="{re.escape(name)}"[^>]*>', arch)
    return matches[occurrence] if len(matches) > occurrence else ""


def field_attrs(arch: str, name: str, occurrence: int = 0) -> str:
    return _tag_attrs(arch, "field", name, occurrence)


def button_attrs(arch: str, name: str, occurrence: int = 0) -> str:
    return _tag_attrs(arch, "button", name, occurrence)


def attr(tag: str, name: str) -> str:
    match = re.search(rf'{re.escape(name)}="([^"]*)"', tag)
    return match.group(1) if match else ""


def normalise(expression: str) -> str:
    return " ".join(expression.split())


# ---------------------------------------------------------------- fixtures
def make_product(ctx, label: str, qty_on_hand: float = 0.0) -> dict:
    """One marked storable product, and its single variant.

    The rules this suite creates all point at this variant, which is what
    keeps them from ever matching one of the gallery's own items.
    """
    rpc = ctx.adapter.rpc
    values = {
        "name": f"{MARK} {label}",
        "default_code": f"{MARK}-{label.upper().replace(' ', '-')}",
        "list_price": 100.0,
        "sale_ok": True,
        "taxes_id": [(6, 0, [])],
    }
    values.update(ctx.adapter.storable_product_values())
    tmpl_id = rpc.create("product.template", values)
    variant = rpc.search_read("product.product",
                              [("product_tmpl_id", "=", tmpl_id)],
                              ["id", "display_name"], limit=1)[0]
    ctx.log(f"fixture product #{variant['id']} {values['name']!r}")
    return {"template_id": tmpl_id, "variant_id": variant["id"],
            "name": values["name"]}


def make_service_order(ctx, partner_id: int, service_id: int,
                       goods_id: int | None, qty: float) -> int:
    """A confirmed order that raises a service transfer.

    ``goods_id`` is passed on every fixture order in this suite. See the
    module docstring: without a goods line, Odoo 19 leaves ``expected_date``
    empty and the connector writes NULL into ``stock_service_move.date``.
    Passing ``None`` is how TC-FUL-017 probes that defect on purpose.
    """
    rpc = ctx.adapter.rpc
    lines = [(0, 0, {"product_id": service_id, "product_uom_qty": qty,
                     "price_unit": 250.0})]
    if goods_id:
        lines.insert(0, (0, 0, {"product_id": goods_id,
                                "product_uom_qty": 1.0,
                                "price_unit": 100.0}))
    order_id = rpc.create("sale.order", {"partner_id": partner_id,
                                         "order_line": lines})
    rpc.call("sale.order", "action_confirm", [order_id])
    ctx.log(f"order #{order_id} confirmed "
            f"({'goods + ' if goods_id else ''}{qty} service)")
    return order_id


def make_service_product(ctx, label: str) -> dict:
    """A marked, sellable service product — a 'deliverable service'."""
    rpc = ctx.adapter.rpc
    tmpl_id = rpc.create("product.template", {
        "name": f"{MARK} {label}",
        "default_code": f"{MARK}-{label.upper().replace(' ', '-')}",
        "type": "service",
        "sale_ok": True,
        "list_price": 250.0,
        "taxes_id": [(6, 0, [])],
    })
    variant = rpc.search_read("product.product",
                              [("product_tmpl_id", "=", tmpl_id)],
                              ["id"], limit=1)[0]
    ctx.log(f"fixture service product #{variant['id']} {label!r}")
    return {"template_id": tmpl_id, "variant_id": variant["id"]}


def make_category(ctx, label: str) -> int:
    rpc = ctx.adapter.rpc
    categ_id = rpc.create("product.category", {"name": f"{MARK} {label}"})
    ctx.log(f"fixture category #{categ_id}")
    return categ_id


def make_rule(ctx, channel_id: int, product: dict, **overrides) -> int:
    """One scratch inventory export rule, scoped to the scratch variant."""
    rpc = ctx.adapter.rpc
    values = {
        "channel_id": channel_id,
        "applied_on": "0_product_variant",
        "product_id": product["variant_id"],
        "percentage_sync": 100.0,
    }
    values.update(overrides)
    rule_id = rpc.create(INCLUDE, values)
    ctx.log(f"rule #{rule_id} {values}")
    return rule_id


def try_rule(ctx, channel_id: int, product: dict, **overrides) -> dict:
    """Attempt a rule that a constraint is expected to refuse.

    Returns the error and whether anything survived. A refused ``create``
    rolls itself back, so a rule that *is* found afterwards means the
    constraint did not fire — which is the defect, not a fixture problem.
    """
    rpc = ctx.adapter.rpc
    before = rpc.call(INCLUDE, "search_count",
                      [("channel_id", "=", channel_id)])
    rule_id, error = None, ""
    try:
        rule_id = make_rule(ctx, channel_id, product, **overrides)
    except OdooRPCError as exc:
        error = str(exc)
    after = rpc.call(INCLUDE, "search_count",
                     [("channel_id", "=", channel_id)])
    return {"error": error, "rule_id": rule_id, "leaked": after > before,
            "before": before, "after": after}


def calc(ctx, rule_id: int, qty: float) -> int:
    """``calc_available_qty`` on one rule — a pure function, no writes.

    ``include_inventory_sync.py:158-166``: floor the percentage, then clamp
    between the minimum and the maximum where each is enabled. This is the
    number the storefront is told about, so the whole of TC-FUL-002 and
    TC-FUL-003 is an assertion about it.
    """
    return ctx.adapter.rpc.call(INCLUDE, "calc_available_qty", [rule_id], qty)


def sweep(ctx) -> dict:
    """Remove everything this suite has created on this database.

    Order matters: rules and exclusions reference the products, so they go
    first. Scoped by the marker throughout, so it can never reach one of the
    gallery's own rules — and it also clears what an interrupted earlier run
    left behind.
    """
    rpc = ctx.adapter.rpc
    removed = {}

    # `active_test=False` matters: a product or partner that could not be
    # deleted on an earlier run was ARCHIVED, and an archived record is
    # invisible to a plain search. Without this, every rerun would leave
    # another set behind and the count would climb for ever.
    seen_all = {"context": {"active_test": False}}
    products = rpc.search("product.product", [("default_code", "like", MARK)],
                          **seen_all)
    templates = rpc.search("product.template", [("name", "like", MARK)],
                           **seen_all)
    categories = rpc.search("product.category", [("name", "like", MARK)],
                            **seen_all)

    for model, domain in (
            (INCLUDE, ["|", ("product_id", "in", products),
                       ("product_tmpl_id", "in", templates)]),
            (EXCLUDE, ["|", ("product_product_ids", "in", products),
                       "|", ("product_tmpl_ids", "in", templates),
                       ("categ_ids", "in", categories)]),
    ):
        try:
            ids = rpc.search(model, domain) if (products or templates
                                                or categories) else []
            if ids:
                rpc.unlink(model, ids)
            removed[model] = len(ids)
        except OdooRPCError as exc:
            ctx.log(f"[warn] sweep {model}: {exc}")
            removed[model] = -1

    # Partners created by an earlier, interrupted run are archived rather
    # than deleted when something still points at them. Retrying them here
    # — not only the ones this run created — is what keeps the count from
    # climbing across runs.
    partners = rpc.search("res.partner", [("name", "like", MARK)],
                          **seen_all)

    for model, ids in (("product.template", templates),
                       ("product.category", categories),
                       ("res.partner", partners)):
        try:
            if ids:
                rpc.unlink(model, ids)
            removed[model] = len(ids)
        except OdooRPCError as exc:
            # A product that has been referenced cannot be deleted; archiving
            # takes it out of every domain that matters here.
            ctx.log(f"[warn] sweep {model} delete refused ({exc}); archiving")
            try:
                rpc.write(model, ids, {"active": False})
                removed[model] = -len(ids)
            except OdooRPCError as exc2:
                ctx.log(f"[warn] sweep {model} archive failed: {exc2}")
                removed[model] = -1

    ctx.log(f"sweep: {removed}")
    return removed


def leftover_exclusions(ctx, channel_id: int) -> list:
    """Exclusion rows on the store pointing at anything this suite created.

    Scoped by the m2m targets, never by ``name``: that field is a non-stored
    compute (``exclude_inventory_sync.py:9, 19-30``), so a domain on it is
    rejected by the ORM — "Cannot convert ... to SQL because it is not
    stored".
    """
    rpc = ctx.adapter.rpc
    seen_all = {"context": {"active_test": False}}
    products = rpc.search("product.product", [("default_code", "like", MARK)],
                          **seen_all)
    templates = rpc.search("product.template", [("name", "like", MARK)],
                           **seen_all)
    categories = rpc.search("product.category", [("name", "like", MARK)],
                            **seen_all)
    if not (products or templates or categories):
        return []
    return rpc.search(EXCLUDE, [
        ("channel_id", "=", channel_id),
        "|", ("product_product_ids", "in", products),
        "|", ("product_tmpl_ids", "in", templates),
        ("categ_ids", "in", categories)])


def leftover_rules(ctx, channel_id: int) -> list:
    """Rules on the store pointing at a product this suite created."""
    rpc = ctx.adapter.rpc
    products = rpc.search("product.product", [("default_code", "like", MARK)],
                          context={"active_test": False})
    if not products:
        return []
    return rpc.search(INCLUDE, [("channel_id", "=", channel_id),
                                ("product_id", "in", products)])
