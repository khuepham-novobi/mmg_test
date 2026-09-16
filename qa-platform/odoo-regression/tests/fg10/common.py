"""FG-10 — Shopify Storefront Integration. Shared gates and fixtures.

Source of truth is the CLIENT MANUAL TESTING GUIDELINE
``MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0.xlsx``, sheet
``Testing Guideline`` — the copy pulled from the client's Google Drive on
2026-09-16. Four cases: TC-SHP-002, -016, -027 and -031.

What this suite will not do to the store
----------------------------------------
There is exactly ONE ``ecommerce.channel`` on this database and it is the
gallery's live Shopify store, restored from production with
``status = 'connected'``. Three of the four cases describe actions on it
that a test must not simply perform:

* **TC-SHP-002 disconnects it.** Its own precondition says to "confirm with
  Novobi that it is acceptable to disconnect the store on this test copy,
  and agree who reconnects it afterwards", and its step 10 says in capitals
  not to press Reconnect. A platform that disconnected the store would
  leave the instance in a state the next case (TC-SHP-016, whose
  precondition is "the store is connected") cannot run in, and would need a
  human to undo. So the disconnect is NOT performed: everything the case
  can check without it is checked, and the button press is BLOCKED with the
  precise authorisation it needs.
* **TC-SHP-027 flips the multi-warehouse switch** and asks to save with the
  mapping list emptied. Both write to the live store. Neither is done.
  Every one of that case's Expected Results is instead settled from the
  VIEW ARCH and the model's own ``@api.constrains``, which is stronger
  evidence than a flip: the arch states the invisible rules for all values
  of the switch at once, where a flip only ever shows two of them.
* **TC-SHP-016 and TC-SHP-031 create a collection.** That is safe and is
  done for real — ``product.collection`` rows are ordinary records, the
  ones this suite creates are marked with :data:`MARK`, and they are
  removed in a ``finally``. What is never called is anything that reaches
  Shopify: the collection is left in ``status = 'draft'`` and
  ``published = False``, exactly as TC-SHP-016 step 11 requires, and no
  export or publish method is invoked.
"""
from __future__ import annotations

import re

from adapters.base import OdooRPCError

# --------------------------------------------------------------- identity
FEATURE = "FG-10 Shopify Storefront Integration"
WORKFLOW = "FG-10"
WORKFLOW_NAME = "Shopify Storefront Integration"
MODULE = "multichannel_shopify"

WORKBOOK = "MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0.xlsx"
SHEET = "Testing Guideline"

MARK = "FG10-AUTOMATED-PROBE"


def trace(tc_ids, user_story: str = "") -> dict:
    return {
        "tc_ids": tc_ids if isinstance(tc_ids, list) else [tc_ids],
        "feature": FEATURE,
        "user_story": user_story,
        "source": f"{WORKBOOK} / {SHEET}",
    }


# ------------------------------------------------------ workbook constants
CHANNEL = "ecommerce.channel"
COLLECTION = "product.collection"
RULE = "rule.collection"
RELATION = "rule.relation"
LOCATION = "shopify.location"
MAPPING = "shopify.location.mapping"
WAREHOUSE = "stock.warehouse"

#: ``ecommerce.channel.status`` — the two values TC-SHP-002 reads off the
#: card badge and the Status column.
STATUS_CONNECTED = "connected"
STATUS_DISCONNECTED = "disconnected"

#: ``product.collection.type`` — the workbook says "Manual" and "Automated";
#: the stored values are these
#: (``multichannel_shopify/models/product_collection.py``).
TYPE_MANUAL = "custom"
TYPE_AUTOMATED = "smart"

#: ``product.collection.condition_type`` — TC-SHP-016 step 7's "all
#: condition" and "any condition".
MATCH_ALL = "all"
MATCH_ANY = "any"

#: TC-SHP-016 step 11 / TC-SHP-031 precondition: the collection is left in
#: Draft and never published.
STATUS_DRAFT = "draft"

#: Four ``rule.collection.column`` values that no ``rule.relation`` row
#: covers, so picking one leaves the Condition dropdown EMPTY while
#: ``relation_id`` is ``required=True``. They are deliberate — the module's
#: own comment (``product_collection.py:65-67``) says they exist so that
#: importing a Shopify collection that uses them does not raise and roll
#: back the whole channel creation. Named here so TC-SHP-031 can report
#: them with their reason instead of discovering an empty dropdown and
#: calling it a defect.
IMPORT_ONLY_COLUMNS = ("product_taxonomy_node_id", "is_price_reduced",
                       "product_metafield_definition",
                       "variant_metafield_definition")

V19_ONLY = ("FG-10 describes the Odoo 19 Shopify screens — the store form's "
            "Inventory Configuration tab, the Collections list and the "
            "collection rule editor")


# ------------------------------------------------------------------- gates
def require_v19(ctx):
    if ctx.env.version != "19":
        ctx.blocked(f"{V19_ONLY} (current target: {ctx.env.name}).")


def require_shopify(ctx):
    require_v19(ctx)
    rpc = ctx.adapter.rpc
    for model in (CHANNEL, COLLECTION, RULE, RELATION):
        if not rpc.model_exists(model):
            ctx.blocked(
                f"model '{model}' does not exist on this database — the "
                f"'{MODULE}' module is not installed, so none of FG-10's "
                f"screens exist.")
    return rpc


def acting_store(ctx) -> dict:
    """The one Shopify store every FG-10 case is about. READ, never written.

    ``platform`` is asserted rather than assumed: every expectation in this
    group is Shopify-specific, and the constraint that settles TC-SHP-027
    step 9 filters on ``platform == 'shopify'`` before it does anything
    (``multichannel_shopify/models/ecommerce_channel.py:96``), so a
    non-Shopify store would make the case vacuous instead of failing.
    """
    rpc = ctx.adapter.rpc
    rows = rpc.search_read(
        CHANNEL, [("platform", "=", "shopify")],
        ["name", "platform", "status", "active", "company_id",
         "has_multi_warehouses", "is_enable_inventory_sync",
         "default_warehouse_id", "fulfillment_location_id",
         "shopify_location_mapping_ids", "active_warehouse_ids"],
        limit=2, order="id")
    if not rows:
        ctx.blocked(
            "no Shopify ecommerce.channel exists on this database, so there "
            "is no store card, no Collections screen and no Inventory "
            "Configuration tab for FG-10 to open.")
    if len(rows) > 1:
        ctx.log(f"more than one Shopify store configured; using "
                f"{rows[0]['name']!r} (#{rows[0]['id']})")
    return rows[0]


def require_connected(ctx, store: dict):
    """TC-SHP-016's and TC-SHP-031's stated precondition."""
    if store.get("status") != STATUS_CONNECTED:
        ctx.blocked(
            f"the store {store['name']!r} is {store.get('status')!r}, and "
            f"this case's precondition is 'the store is connected (if "
            f"TC-SHP-002 disconnected it, have Novobi reconnect first)'. "
            f"Reconnecting calls Shopify, so it is Novobi's to do.")


# ---------------------------------------------------------------- evidence
def manual(ctx, text: str):
    ctx.log(f"RESIDUAL MANUAL STEP — {text}")


def observation(ctx, text: str):
    ctx.log(f"OBSERVATION — {text}")


def finding(ctx, text: str):
    ctx.log(f"FINDING — {text}")


# ------------------------------------------------------------ view arches
def raw_arch(rpc, xmlid: str) -> str:
    """One view's OWN arch, before inheritance is applied.

    ``get_view`` returns the ASSEMBLED arch, and assembly rewrites the very
    attributes TC-SHP-027 turns on. The ``invisible=`` and ``required=``
    expressions are written in the source view, so they are read from
    ``ir.ui.view.arch_db``.
    """
    module, _, name = xmlid.partition(".")
    rows = rpc.search_read(
        "ir.model.data",
        [("model", "=", "ir.ui.view"), ("module", "=", module),
         ("name", "=", name)], ["res_id"], limit=1)
    if not rows:
        return ""
    value = rpc.read("ir.ui.view", [rows[0]["res_id"]],
                     ["arch_db"])[0].get("arch_db") or ""
    if isinstance(value, dict):          # translated Char comes back as a map
        value = value.get("en_US") or next(iter(value.values()), "")
    return value


def field_tag(arch: str, name: str) -> str:
    """The ``<field name="...">`` opening tag, or '' if the field is absent."""
    match = re.search(r'<field[^>]*\bname="' + re.escape(name) + r'"[^>]*>',
                      arch)
    return match.group(0) if match else ""


def attr(tag: str, name: str) -> str:
    match = re.search(r'\b' + re.escape(name) + r'="([^"]*)"', tag)
    return match.group(1) if match else ""


# --------------------------------------------------------- rule dropdowns
def selection_of(rpc, model: str, field: str) -> list:
    info = rpc.call(model, "fields_get", [field], attributes=["selection"])
    return list((info.get(field) or {}).get("selection") or [])


def selection_labels(rpc, model: str, field: str) -> dict:
    return {str(k): v for k, v in selection_of(rpc, model, field)}


def conditions_by_column(rpc) -> dict:
    """Field value -> the Condition rows the editor would offer for it.

    ``rule.collection.change_column`` is an ``@api.onchange`` returning
    ``{'domain': {'relation_id': [('columns', '=ilike', '%<column>%')]}}``
    (``multichannel_shopify/models/product_collection.py:91-95``). The same
    domain is applied here, per column, so what this reports is what the
    dropdown would really contain rather than a guess at it.
    """
    out = {}
    for value, _label in selection_of(rpc, RULE, "column"):
        out[value] = rpc.search_read(
            RELATION, [("columns", "=ilike", "%" + str(value) + "%")],
            ["name", "value"], order="id")
    return out


# ----------------------------------------------------------------- helpers
def m2o_id(value):
    if isinstance(value, (list, tuple)) and value:
        return value[0]
    return value or False


def m2o_name(value):
    if isinstance(value, (list, tuple)) and len(value) > 1:
        return value[1]
    return ""


# ---------------------------------------------------------------- sweeping
def sweep_fg10(ctx):
    """Remove collections left by a previous run. Marker-scoped.

    Never touches the client's own collections: the domain matches
    :data:`MARK` in the name, and the rules go with their parent. Records
    are removed ONE AT A TIME because a batch unlink is all-or-nothing —
    one undeletable row would otherwise leave every other leftover behind.
    """
    rpc = ctx.adapter.rpc
    ids = rpc.search(COLLECTION, [("name", "like", MARK)])
    if not ids:
        return 0
    removed = 0
    for one in ids:
        try:
            rpc.unlink(COLLECTION, [one])
            removed += 1
        except OdooRPCError as exc:
            ctx.log("  could not remove collection #%s: %s" % (one, exc))
    ctx.log("swept %s of %s leftover FG-10 collection(s)"
            % (removed, len(ids)))
    return removed
