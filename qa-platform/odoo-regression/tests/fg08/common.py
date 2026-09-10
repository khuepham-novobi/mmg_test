"""FG-08 — E-commerce Channel Management. Shared read-only helpers and gates.

Source of truth for this suite is the CLIENT MANUAL TESTING GUIDELINE
``MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0.xlsx``, sheet
``Testing Guideline``, rows 44-46 (TC-CHN-001, TC-CHN-005, TC-CHN-011).
Every assertion in this suite implements that workbook's *Expected Result*
column verbatim — never weakened, never inverted.

Odoo 19 only
------------
The workbook describes the v19 screens: the menu path it names
(*E-commerce Connectors > Configuration > **Store Configuration** > Manage
Stores*) only exists on v19 — v15 hung *Manage Stores* straight off
*Configuration* (``novobi-omni-addons/omni_manage_channel/views/
ecommerce_channel_views.xml:82``) and gained the ``Store Configuration``
level in the port (``omni_manage_channel/views/ecommerce_channel_views.xml:
76-77``). The Overview screen was rebuilt as well. Running these
assertions against a v15 target would report version differences as product
defects, so every test calls :func:`require_v19` first and reports BLOCKED
on anything else.

Why this whole suite is STRUCTURALLY read-only
----------------------------------------------
All three cases are read-only by the workbook's own *Test Data* column
("Change nothing in this case", "The two baseline values", "Nothing to
enter. This case is read-only"), and TC-CHN-001 step 8 says in as many
words: *"Do NOT press Reconnect, Refresh Locations or the Auto Import
buttons anywhere on this screen."*

On the MMG v19 restore that is not a nicety. The single
``ecommerce.channel`` row is the **live** Medicine Man Gallery Shopify
store: ``active = True``, ``auto_import_data = True``, ``environment =
'production'``, ``shopify_hostname = medicinemangallery.myshopify.com``,
and a real access token in the channel secret store. Several public methods
on that record reach Shopify:

* ``check_connection`` / ``button_check_connection`` / ``reconnect`` —
  ``_shopify_check_connection`` calls ``shopify_api.shop.all()``
  (``multichannel_shopify/models/ecommerce_channel.py:123-138``);
* ``write()`` itself, for a shopify channel, routes through
  ``extract_shopify_store_settings`` — an outbound
  ``shopify_get_store_settings`` call — whenever either credential field is
  in ``vals`` (``multichannel_shopify/models/ecommerce_channel.py:427-435,
  445-451``);
* ``shopify_refresh_location``, ``bulk_inventory_sync``,
  ``action_import_order_manually``, ``action_import_product_manually``,
  ``refresh_currencies``, ``sync_data``, ``get_credentials``,
  ``get_thumbnail``, ``check_new_orders`` and ``enable_auto_import_data``
  all either call the store or re-arm the import cron
  (``omni_manage_channel/models/ecommerce_channel.py:325-337, 339-345,
  430-452, 516-528, 597-603, 700-705``).

``AUTOMATION_CONVENTIONS`` rules 3 and 4 forbid both writing to a
pre-existing business record and triggering an outbound integration, so
rather than *remembering* not to call those, this suite routes every call
through :class:`ReadOnlyRPC`, which refuses anything outside a small
allow-list of read methods. The property "this suite cannot write and
cannot reach Shopify" is therefore checkable by reading one class instead
of auditing three test files.

The two dashboard methods on the allow-list — ``get_dashboard_datas`` and
``get_graph_datas`` — are pure ``SELECT``s over ``sale_order``
(``multichannel_order/models/ecommerce_channel.py:212-251, 286-360``)
and are the *same* calls the Overview card makes, which is why
TC-CHN-011 can assert the figures a browser would show without a browser.

What "the Novobi baseline" means here
-------------------------------------
TC-CHN-001 and TC-CHN-005 are *comparison* cases: they tick values off a
printout of the old system that Novobi supplies. The platform does not hold
that printout, and there is no v15 database on this workstation to generate
one from (``mmg_15`` is an empty skeleton; ``framework.fg_common.reconcile``
would report BLOCKED for want of a baseline). So the suite does the half it
can do properly:

* it captures the complete, machine-readable inventory of every value the
  workbook asks the tester to compare, into CSV artifacts, so the tick-off
  is a two-column read rather than a screen-by-screen hunt;
* it asserts every invariant that does **not** need the printout — a
  configured many2one that points at an archived or missing record, a
  required sub-table that came across empty, a field the workbook names
  that is not on the screen at all;
* and it prints what is left as ``RESIDUAL MANUAL STEP``, never silently
  dropping it.
"""
from __future__ import annotations

import ast
import csv
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta

from adapters.base import OdooRPCError

# --------------------------------------------------------------- identity
FEATURE = "FG-08 E-commerce Channel Management"
WORKFLOW = "FG-08"
WORKFLOW_NAME = "E-commerce Channel Management"

MODULE = "omni_manage_channel"
MODULE_ORDER = "multichannel_order"
MODULE_PRODUCT = "multichannel_product"
MODULE_FULFILLMENT = "multichannel_fulfillment"
MODULE_SHOPIFY = "multichannel_shopify"

MARK = "FG08"
WORKBOOK = "MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0.xlsx"
SHEET = "Testing Guideline"


def trace(tc_ids, user_story: str = "") -> dict:
    """Traceability back to the client manual testing guideline."""
    return {
        "tc_ids": tc_ids if isinstance(tc_ids, list) else [tc_ids],
        "feature": FEATURE,
        "user_story": user_story,
        "source": f"{WORKBOOK} / {SHEET}",
    }


# ------------------------------------------------------------- constants
CHANNEL = "ecommerce.channel"
SALE_ORDER = "sale.order"
SHOPIFY = "shopify"

# Menus the workbook navigates by name, with the XML ids that carry them
# (omni_manage_channel/views/ecommerce_channel_views.xml).
MENU_ROOT = f"{MODULE}.menu_multichannel_root"                     # :4
MENU_OVERVIEW = f"{MODULE}.menu_omniborder_overview"               # :23
MENU_CONFIGURATION = f"{MODULE}.menu_configuration"                # :73
MENU_STORE_CONFIGURATION = (
    f"{MODULE}.menu_management_channels_store_configuration")      # :76
MENU_MANAGE_STORES = f"{MODULE}.menu_management_channels"          # :82

ACTION_MANAGE_STORES = f"{MODULE}.action_channel_list"             # :53
ACTION_OVERVIEW = f"{MODULE}.action_channel_overview"              # :9

VIEW_STORE_LIST = f"{MODULE}.ecommerce_channel_tree_view"          # :26
VIEW_STORE_SEARCH = f"{MODULE}.ecommerce_channel_search_view"      # :41
VIEW_STORE_KANBAN = f"{MODULE}.ecommerce_channel_kanban"           # dashboard view :4
VIEW_STORE_FORM = f"{MODULE}.view_ecommerce_channel_form_settings"

GROUP_MANAGER = f"{MODULE}.group_listing_manager"    # "E-commerce Manager"
GROUP_USER = f"{MODULE}.group_listing_user"          # "E-commerce User"
GROUP_MULTI_COMPANY = "base.group_multi_company"

# The four notebook pages the workbook calls "tabs", in the order the view
# priorities put them: multichannel_product (40) -> multichannel_fulfillment
# (50) -> multichannel_order (1000). The header area above the notebook is
# the workbook's first "tab" (its step 2).
PAGE_PRODUCT = ("product_configuration_page", "Product Configuration")
PAGE_INVENTORY = ("inventory_sync_page", "Inventory Configuration")
PAGE_ORDER = ("order_configuration_page", "Order Configuration")
EXPECTED_PAGES = (PAGE_PRODUCT, PAGE_INVENTORY, PAGE_ORDER)

# multichannel_order/models/ecommerce_channel.py:20-25.
PERIOD_DAYS = {
    "last_30_days": 30,
    "last_60_days": 60,
    "last_90_days": 90,
    "last_120_days": 120,
}
PERIOD_FIELD = "kanban_dashboard_period"
DEFAULT_PERIOD = "last_30_days"

# ecommerce.channel.status — a compute over `active`, NOT a probe of the
# store (omni_manage_channel/models/ecommerce_channel.py:311-313). Reading
# it makes no outbound call, which is why TC-CHN-005 is safe to run.
STATUS_CONNECTED = "connected"
STATUS_DISCONNECTED = "disconnected"

# omni_manage_channel/tests/test_ecommerce_channel.py — the four v15 fields
# the port drops on purpose. Named here so a tester hunting for them on the
# screen is told they are gone by decision, not lost by accident.
DROPPED_V15_FIELDS = ("oauth_version", "state", "is_in_syncing",
                      "last_option_sync_product")

# v15 -> v19 renames that a field-by-field printout comparison walks into.
RENAMED_SINCE_V15 = {
    "default_payment_method_id": "default_payment_method_line_id",
    # on payment.method.mapping lines
    "payment_method_id": "payment_method_line_id",
}


# ------------------------------------------------------- the safety guard
class ReadOnlyViolation(RuntimeError):
    """A test in this suite tried to reach a method that can write to the
    database or call Shopify. Raised instead of performing the call."""


#: Model methods this suite is allowed to call. Everything else — including
#: ``create``/``write``/``unlink`` and every ``button_*`` / ``action_*`` /
#: ``open_*`` / ``toggle_*`` on ``ecommerce.channel`` — is refused.
SAFE_METHODS = frozenset({
    "search", "search_read", "search_count", "read", "read_group",
    "fields_get", "get_view", "get_views", "name_search", "has_group",
    "web_search_read", "web_read", "context_get",
})

#: Public methods that are pure ``SELECT``s and produce exactly what the
#: Overview card renders. Both are plain queries over ``sale_order`` with no
#: write and no outbound call:
#:   multichannel_order/models/ecommerce_channel.py:212-223 (get_dashboard_datas
#:   -> _get_dashboard_datas_query -> _process_dashboard_datas) and :288-322
#:   (get_graph_datas).
SAFE_CHANNEL_METHODS = frozenset({"get_dashboard_datas", "get_graph_datas"})

#: Named so a reader can see the danger this guard exists for. Not
#: exhaustive by construction — the guard is an allow-list, so a method
#: missing from this tuple is still refused.
OUTBOUND_METHODS = (
    "check_connection", "button_check_connection", "reconnect", "disconnect",
    "sync_data", "get_credentials", "get_thumbnail", "refresh_currencies",
    "shopify_refresh_location", "bulk_inventory_sync",
    "action_import_order_manually", "action_import_product_manually",
    "open_import_other_data", "enable_auto_import_data",
    "disable_auto_import_data", "toggle_safe_mode", "toggle_debug_logging",
    "check_new_orders", "done_synching", "unlink", "write", "create",
    "copy", "shopify_get_locations", "shopify_get_store_settings",
    "extract_shopify_store_settings",
)


class ReadOnlyRPC:
    """A read-only face on ``ctx.adapter.rpc``.

    Delegates the read methods in :data:`SAFE_METHODS` (plus the two
    allow-listed dashboard producers) and raises
    :class:`ReadOnlyViolation` for anything else, so no test in this suite
    can write to the database or reach Shopify even by mistake.
    """

    def __init__(self, rpc, ctx=None):
        self._rpc = rpc
        self._ctx = ctx
        self.calls = 0

    # -- the guard ------------------------------------------------------
    def call(self, model: str, method: str, *args, **kwargs):
        allowed = method in SAFE_METHODS or (
            model == CHANNEL and method in SAFE_CHANNEL_METHODS)
        if not allowed:
            hint = ""
            if method in OUTBOUND_METHODS:
                hint = (" — this is one of the methods that writes to the "
                        "store record or calls Shopify; the workbook's step "
                        "8 forbids it and AUTOMATION_CONVENTIONS rule 4 "
                        "forbids it")
            raise ReadOnlyViolation(
                f"FG-08 is a read-only suite: {model}.{method}() is not on "
                f"the allow-list{hint}. Allowed: "
                f"{', '.join(sorted(SAFE_METHODS))}"
                f" (+ {', '.join(sorted(SAFE_CHANNEL_METHODS))} on "
                f"{CHANNEL}).")
        self.calls += 1
        return self._rpc.call(model, method, *args, **kwargs)

    # -- delegated reads ------------------------------------------------
    def search(self, model, domain, **kw):
        return self.call(model, "search", domain, **kw)

    def search_read(self, model, domain, fields, **kw):
        return self.call(model, "search_read", domain, fields=fields, **kw)

    def search_count(self, model, domain, **kw):
        return self.call(model, "search_count", domain, **kw)

    def read(self, model, ids, fields):
        return self.call(model, "read", ids, fields=fields)

    def read_group(self, model, domain, fields, groupby, **kw):
        return self.call(model, "read_group", domain, fields, groupby, **kw)

    def fields_get(self, model, names=None, attributes=None):
        args = [names] if names is not None else []
        kw = {"attributes": attributes} if attributes else {}
        return self.call(model, "fields_get", *args, **kw)

    def field_exists(self, model, field) -> bool:
        return field in self.fields_get(model, [field], ["type"])

    def model_exists(self, model) -> bool:
        return bool(self.search("ir.model", [("model", "=", model)], limit=1))

    def ref(self, xmlid: str):
        """Resolve an XML id without ir.model.data's private helpers."""
        module, _, name = xmlid.partition(".")
        rec = self.search_read(
            "ir.model.data",
            [("module", "=", module), ("name", "=", name)],
            ["res_id", "model"], limit=1)
        return rec[0]["res_id"] if rec else None

    @property
    def uid(self):
        return self._rpc.uid


def readonly_rpc(ctx) -> ReadOnlyRPC:
    """The single RPC handle every FG-08 test uses. Cached per context."""
    existing = getattr(ctx, "_fg08_rpc", None)
    if existing is None:
        existing = ReadOnlyRPC(ctx.adapter.rpc, ctx)
        ctx._fg08_rpc = existing
    return existing


# ------------------------------------------------------------ evidence
def manual(ctx, text: str):
    """A step the platform cannot do, printed rather than dropped."""
    ctx.log(f"RESIDUAL MANUAL STEP — {text}")


def observation(ctx, text: str):
    """Something worth recording that is deliberately asserted in neither
    direction (the workbook says not to raise it, or a legitimate database
    can hold either shape)."""
    ctx.log(f"OBSERVATION — {text}")


def finding(ctx, text: str):
    """A divergence between the workbook and the shipped v19 build, found
    while writing the assertions. Not a test defect and not silently
    absorbed — see reports/data/fg08_feasibility.json, keys
    ``_finding_salesperson`` / ``_finding_card_readings`` /
    ``_finding_period_write``."""
    ctx.log(f"FINDING — {text}")


def write_csv(ctx, name: str, header: list, rows: list):
    """Write a CSV artifact. Called from ``finally`` blocks so the evidence
    exists even when an assertion failed — which is when it is most
    useful."""
    path = ctx.artifacts_dir / name
    try:
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(header)
            for row in rows:
                writer.writerow(row)
    except OSError as exc:                       # pragma: no cover
        ctx.log(f"[warn] could not write {name}: {exc}")
        return None
    ctx.add_artifact(path, "log", name)
    ctx.log(f"artifact written: {name} ({len(rows)} rows)")
    return path


# ---------------------------------------------------------------- gates
def require_v19(ctx):
    """The workbook describes the v19 screens; see the module docstring."""
    if ctx.env.version != "19":
        ctx.blocked(
            f"FG-08 targets Odoo 19 only — this run is against "
            f"'{ctx.env.name}' (version {ctx.env.version}). The workbook "
            f"navigates 'E-commerce Connectors > Configuration > Store "
            f"Configuration > Manage Stores', a menu level that only exists "
            f"in the v19 port, and its Overview expectations describe the "
            f"rebuilt v19 dashboard. Point TARGET at Odoo 19.")


def require_connector(ctx):
    """The omni e-commerce stack must be installed, or every expectation in
    FG-08 is about a screen that is not there."""
    rpc = readonly_rpc(ctx)
    if not rpc.model_exists(CHANNEL):
        ctx.blocked(
            f"model '{CHANNEL}' does not exist — install the e-commerce "
            f"connector stack ({MODULE}, {MODULE_ORDER}, {MODULE_PRODUCT}, "
            f"{MODULE_FULFILLMENT}, {MODULE_SHOPIFY}) on the target "
            f"database.")
    fields = rpc.fields_get(CHANNEL)
    missing = [(mod, field) for mod, field in (
        (MODULE, "status"),
        (MODULE_PRODUCT, "auto_create_master_product"),
        (MODULE_FULFILLMENT, "is_enable_inventory_sync"),
        (MODULE_ORDER, PERIOD_FIELD),
        (MODULE_SHOPIFY, "shopify_hostname"),
    ) if field not in fields]
    if missing:
        ctx.blocked(
            "the e-commerce connector stack is only partly installed — "
            + "; ".join(f"{mod} is absent ({CHANNEL}.{field} missing)"
                        for mod, field in missing)
            + ". Install the missing modules; FG-08's expectations span all "
              "five.")
    return fields


def channel_fields(ctx) -> dict:
    """``fields_get`` on ecommerce.channel, cached per context."""
    cached = getattr(ctx, "_fg08_fields", None)
    if cached is None:
        cached = readonly_rpc(ctx).fields_get(CHANNEL)
        ctx._fg08_fields = cached
    return cached


# ------------------------------------------------------- actions & views
def resolve_action(ctx, xmlid: str) -> dict:
    """Read an ``ir.actions.act_window`` by XML id, with its own domain,
    context and pinned views resolved.

    The action's *own* domain and context are read at run time rather than
    retyped into the test: that way a changed action is reported instead of
    the test silently measuring something else.
    """
    rpc = readonly_rpc(ctx)
    action_id = rpc.ref(xmlid)
    if not action_id:
        ctx.blocked(f"action '{xmlid}' does not exist on this database — "
                    f"the e-commerce connector menus are not installed.")
    data = rpc.read("ir.actions.act_window", [action_id],
                    ["name", "res_model", "view_mode", "domain", "context",
                     "target", "search_view_id", "view_ids"])[0]
    data["xmlid"] = xmlid
    data["parsed_domain"] = _literal(ctx, data.get("domain"), default=[])
    data["parsed_context"] = _literal(ctx, data.get("context"), default={})
    views = []
    if data.get("view_ids"):
        for row in rpc.read("ir.actions.act_window.view", data["view_ids"],
                            ["view_mode", "view_id", "sequence"]):
            views.append({"mode": row["view_mode"],
                          "view_id": _m2o_id(row.get("view_id")),
                          "sequence": row.get("sequence")})
    data["views"] = sorted(views, key=lambda v: (v["sequence"] or 0))
    return data


def _literal(ctx, raw, default):
    """``ast.literal_eval`` a stored domain/context, never ``eval``.

    The FG-08 actions hold plain literals
    (``omni_manage_channel/views/ecommerce_channel_views.xml:13-14, 57-58``),
    so anything that will not parse is reported rather than guessed at.
    """
    if raw in (None, False, ""):
        return default
    if isinstance(raw, (list, dict)):
        return raw
    try:
        return ast.literal_eval(str(raw))
    except (ValueError, SyntaxError):
        ctx.log(f"[warn] {raw!r} is not a plain literal — recorded as "
                f"unparsed rather than guessed")
        return default


def _m2o_id(value):
    """RPC read() returns m2o as [id, display_name] or False."""
    return value[0] if isinstance(value, (list, tuple)) else (value or None)


m2o_id = _m2o_id


def view_arch(ctx, xmlid: str, view_type: str) -> str:
    """The **assembled** arch of one view, resolved by its own XML id.

    ``get_view`` returns the inherited/merged architecture — every
    ``inherit_id`` view in the database is applied — which is exactly what
    the browser is handed. That is what makes a "which tab is this field
    on?" assertion meaningful: the notebook pages TC-CHN-001 walks are
    contributed by three different modules.
    """
    rpc = readonly_rpc(ctx)
    view_id = rpc.ref(xmlid)
    if not view_id:
        ctx.blocked(f"view '{xmlid}' does not exist on this database.")
    return rpc.call(CHANNEL, "get_view", view_id=view_id,
                    view_type=view_type)["arch"]


def parse_arch(arch: str):
    """Parse an arch string into an ElementTree root."""
    return ET.fromstring(arch)


def arch_field_map(root) -> dict:
    """``{field name: {...}}`` for every ``<field>`` in a form arch,
    annotated with the notebook page it sits under.

    A field can appear more than once (the settings form declares
    ``company_id`` twice — once ``invisible="1"`` to make it available to
    other expressions, once for display,
    ``omni_manage_channel/views/omnichannel_dashboard_views.xml:256-260``).
    All occurrences are kept, so an assertion can ask about the *visible*
    one rather than whichever came first.
    """
    result: dict[str, dict] = {}
    for page_name, page_string, element in _iter_with_page(root):
        if element.tag != "field":
            continue
        name = element.get("name")
        if not name:
            continue
        entry = result.setdefault(name, {"name": name, "occurrences": []})
        entry["occurrences"].append({
            "page": page_name,
            "page_string": page_string,
            "attrs": dict(element.attrib),
            "string": element.get("string"),
            "widget": element.get("widget"),
            "invisible": element.get("invisible"),
            "readonly": element.get("readonly"),
            "required": element.get("required"),
            "groups": element.get("groups"),
            "password": element.get("password"),
            "is_subtable": any(child.tag in ("list", "tree", "form", "kanban")
                               for child in element),
        })
    return result


def _iter_with_page(root, page_name="", page_string=""):
    """Walk the arch yielding ``(page name, page string, element)``."""
    for child in root:
        if child.tag == "page":
            name = child.get("name") or ""
            string = child.get("string") or ""
            yield name, string, child
            yield from _iter_with_page(child, name, string)
        else:
            yield page_name, page_string, child
            yield from _iter_with_page(child, page_name, page_string)


def arch_pages(root) -> list:
    """``[(name, string)]`` for every notebook page, in arch order."""
    return [(p.get("name") or "", p.get("string") or "")
            for p in root.iter("page")]


def arch_buttons(root) -> list:
    """Every ``<button>`` in the arch, with the method it calls."""
    out = []
    for page_name, page_string, element in _iter_with_page(root):
        if element.tag != "button":
            continue
        label = (element.get("string") or "").strip()
        if not label:
            label = " ".join(
                t.strip() for t in element.itertext() if t and t.strip())
        # Several buttons on this form carry no text at all: their content is
        # a <field widget="boolean_button"> whose own `terminology` option
        # supplies the caption (e.g. the Auto Import and Connected stat
        # buttons, omni_manage_channel/views/omnichannel_dashboard_views.xml:
        # 189-247). Capture the icon and the inner field names so a log line
        # still identifies the control the tester sees.
        inner_fields = [f.get("name") for f in element.iter("field")
                        if f.get("name")]
        out.append({
            "name": element.get("name") or "",
            "type": element.get("type") or "",
            "label": label or element.get("name") or "",
            "icon": element.get("icon"),
            "fields": inner_fields,
            "page": page_name,
            "page_string": page_string,
            "invisible": element.get("invisible"),
            "confirm": element.get("confirm"),
            "groups": element.get("groups"),
        })
    return out


def field_on_page(field_map: dict, name: str, page_name: str):
    """The occurrence of ``name`` that sits on ``page_name``, or ``None``."""
    for occurrence in field_map.get(name, {}).get("occurrences", []):
        if occurrence["page"] == page_name:
            return occurrence
    return None


def visible_occurrence(field_map: dict, name: str):
    """The occurrence a user actually sees, i.e. the first one that is not
    unconditionally ``invisible="1"``."""
    for occurrence in field_map.get(name, {}).get("occurrences", []):
        if str(occurrence.get("invisible") or "").strip() not in ("1", "True"):
            return occurrence
    return None


def search_filters(arch: str) -> dict:
    """``{filter name: {'string':…, 'domain':…}}`` from a search arch."""
    out = {}
    for element in parse_arch(arch).iter("filter"):
        name = element.get("name")
        if not name:
            continue
        out[name] = {"string": element.get("string") or "",
                     "domain": element.get("domain") or "",
                     "context": element.get("context") or ""}
    return out


def list_columns(arch: str) -> list:
    """``[(field name, label override, widget)]`` in display order."""
    root = parse_arch(arch)
    return [(f.get("name"), f.get("string"), f.get("widget"))
            for f in root.iter("field") if f.get("name")]


#: Enough to identify a store and log what is under test. Every one of
#: these is defined by omni_manage_channel itself, so a partly-installed
#: stack still reads them (and require_connector() reports the gap).
IDENTITY_FIELDS = ["id", "name", "platform", "active", "status",
                   "company_id", "environment"]


def require_manager_group(ctx):
    """The workbook's own precondition, asserted rather than assumed.

    TC-CHN-001: *"You have the 'E-commerce Manager' group — without it the
    Manage Stores menu does not appear. For the payment and rule sub-tables
    you additionally need the group shown as Access Rights on your user."*

    It matters more than a missing menu. In v19 the ORM enforces field
    ``groups=`` on every attribute read, and ``fields_get`` **omits** a
    group-restricted field entirely rather than returning it empty
    (asserted by the module's own
    ``omni_manage_channel/tests/test_sec_007.py:96-125``). So a run as a
    plain *E-commerce User* would see no ``shopify_access_token`` at all and
    a naive test would report the store's token as missing — a false P0.
    Better to block with the workbook's precondition in hand.
    """
    rpc = readonly_rpc(ctx)
    try:
        is_manager = rpc.call("res.users", "has_group", [rpc.uid],
                              GROUP_MANAGER)
    except OdooRPCError as exc:
        ctx.log(f"[warn] has_group({GROUP_MANAGER}) failed ({exc}) — "
                f"continuing; a missing Access Token reading may then be an "
                f"access artefact rather than a migration problem")
        return None
    if not is_manager:
        ctx.blocked(
            f"the RPC user (uid {rpc.uid}) is not in "
            f"'{GROUP_MANAGER}' (E-commerce Manager). That is the "
            f"workbook's own precondition — without it the Manage Stores "
            f"menu does not appear, and v19 omits group-restricted fields "
            f"from fields_get()/read() entirely, so the Access Token would "
            f"read as empty when it is merely invisible. Add the group to "
            f"the user named in config/local.yaml.")
    ctx.log(f"RPC user uid {rpc.uid} is in {GROUP_MANAGER} — the "
            f"group-restricted credential fields are readable, so an empty "
            f"Access Token reading would be real")
    return True


def require_user_group(ctx):
    """TC-CHN-011's own precondition, asserted rather than assumed.

    The workbook's precondition for the Overview case is *"you have the
    'E-commerce User' group at least"* — not the Manager group TC-CHN-001
    needs, and the menus agree. The Overview menu carries no ``groups`` of
    its own and hangs off a root restricted to ``group_listing_user``;
    *Manage Stores* is the one restricted to ``group_listing_manager``
    (``omni_manage_channel/views/ecommerce_channel_views.xml:4-6, 23-24,
    82-84``). TC-CHN-011 reads no group-restricted field — it never calls
    :func:`secret_state` — so demanding Manager here would report a
    correctly-provisioned E-commerce User as BLOCKED against a screen they
    are entitled to open.

    A Manager still passes: ``group_listing_manager`` implies
    ``group_listing_user``
    (``omni_manage_channel/security/listing_channel_security.xml:44-49``)
    and ``has_group`` resolves through ``all_group_ids``
    (``odoo/addons/base/models/res_users.py:1085-1096``).
    """
    rpc = readonly_rpc(ctx)
    try:
        is_user = rpc.call("res.users", "has_group", [rpc.uid], GROUP_USER)
    except OdooRPCError as exc:
        ctx.log(f"[warn] has_group({GROUP_USER}) failed ({exc}) — "
                f"continuing; this case reads no group-restricted field, so "
                f"a wrong group shows up as an empty screen rather than as "
                f"a wrong value")
        return None
    if not is_user:
        ctx.blocked(
            f"the RPC user (uid {rpc.uid}) is not in '{GROUP_USER}' "
            f"(E-commerce User). That is the workbook's own precondition "
            f"for this case — without it the 'E-commerce Connectors' menu "
            f"does not appear at all (omni_manage_channel/views/"
            f"ecommerce_channel_views.xml:4-6). Add the group to the user "
            f"named in config/local.yaml.")
    ctx.log(f"RPC user uid {rpc.uid} is in {GROUP_USER} — the workbook's "
            f"'E-commerce User at least' precondition is met")
    return True


# --------------------------------------------------------------- the store
def store_domain(ctx, action: dict, include_inactive=True) -> list:
    """The domain the Manage Stores / Overview screen itself applies.

    Both actions carry ``{'active_test': False, 'search_default_connected':
    1}`` and a domain excluding template rows and platform-less channels
    (``omni_manage_channel/views/ecommerce_channel_views.xml:13-14,
    57-58``). ``include_inactive=False`` adds the *Connected* filter's own
    term, which is what "clear the Connected filter" toggles in TC-CHN-005
    step 4.
    """
    domain = list(action["parsed_domain"])
    if not include_inactive:
        domain = domain + [("active", "=", True)]
    return domain


def store_context(action: dict) -> dict:
    """The action's own context. ``active_test: False`` is what lets an
    archived (disconnected) store appear at all."""
    return dict(action["parsed_context"] or {})


def find_shopify_store(ctx, action: dict) -> dict:
    """The gallery's Shopify store, as the Manage Stores screen would list
    it — resolved through the action's own domain and context, never a
    hard-coded id.

    BLOCKED when there is no Shopify store (nothing in FG-08 is meaningful
    then) and when there is more than one, because the workbook says "the
    gallery's Shopify store" in the singular and a suite that silently
    picked one would be measuring an arbitrary record.
    """
    rpc = readonly_rpc(ctx)
    context = store_context(action)
    domain = store_domain(ctx, action) + [("platform", "=", SHOPIFY)]
    # A minimal, always-present field set: this runs before store_values()
    # has had a chance to drop fields a partly-installed stack lacks, and a
    # search_read naming an absent field raises instead of reporting the gap.
    rows = rpc.search_read(CHANNEL, domain, IDENTITY_FIELDS, context=context)
    if not rows:
        every = rpc.search_read(
            CHANNEL, [("active", "in", (True, False))],
            ["name", "platform", "active"], context={"active_test": False})
        ctx.blocked(
            f"no Shopify store is listed by {action['xmlid']} — the "
            f"database holds {len(every)} channel row(s): "
            f"{[(r['name'], r['platform'], r['active']) for r in every]}. "
            f"FG-08 describes the migrated Medicine Man Gallery Shopify "
            f"store; without it there is nothing to compare against the "
            f"Novobi printout.")
    if len(rows) > 1:
        ctx.blocked(
            f"{len(rows)} Shopify stores are listed by {action['xmlid']} "
            f"({[r['name'] for r in rows]}), but the workbook says 'the "
            f"gallery's Shopify store' in the singular. Say which one the "
            f"Novobi printout describes before running FG-08 — picking one "
            f"here would measure an arbitrary record.")
    store = rows[0]
    ctx.log(f"store under test: #{store['id']} {store['name']!r} "
            f"(platform={store['platform']!r}, active={store['active']}, "
            f"company={store.get('company_id')}, "
            f"environment={store.get('environment')!r})")
    return store


#: Every ecommerce.channel field the three FG-08 cases read. Kept in one
#: place so the CSV inventory and the assertions cannot drift apart.
STORE_FIELDS = [
    # header area (workbook step 2-3)
    "id", "name", "platform", "company_id", "active", "status",
    "shopify_hostname", "secure_url", "admin_email", "environment",
    "api_version", "currency_id", "weight_unit", "dimension_unit",
    "safe_mode", "debug_logging", "auto_import_data", "is_default_channel",
    "show_on_dashboard", "color", "warning_message", "measure_unit",
    "image_url", "logo_and_name",
    # Product Configuration (step 4)
    "auto_create_master_product", "auto_override_product",
    "auto_override_imported_field_ids", "pricelist_id",
    "can_export_product", "can_export_product_from_master",
    "can_export_product_from_mapping", "can_export_pricelist_from_master",
    "master_template_exported_field_ids",
    "mapping_template_exported_field_ids",
    "master_variant_exported_field_ids",
    "mapping_variant_exported_field_ids",
    "is_mapping_managed", "manage_images", "default_categ_id",
    "hide_auto_override_product",
    # Inventory Configuration (steps 5-6)
    "is_enable_inventory_sync", "is_allow_manual_bulk_inventory_sync",
    "active_warehouse_ids", "include_inventory_sync_ids",
    "exclude_inventory_sync_ids", "fulfillment_location_id",
    "has_multi_warehouses", "default_warehouse_id",
    "display_default_warehouse",
    "shopify_location_mapping_ids", "last_all_inventory_sync",
    "is_running_bulk_inventory_sync",
    # Order Configuration (step 7)
    "auto_export_shipment_to_store",
    "auto_export_fulfillment_location_to_shopify",
    "min_order_date_to_import", "order_prefix", "sales_team_id",
    "default_guest_customer", "user_id", "default_order_tag_ids",
    "default_shipping_policy", "default_tax_product_id",
    "default_discount_product_id", "default_shipping_cost_product_id",
    "default_fee_product_id", "default_handling_cost_product_id",
    "default_wrapping_cost_product_id", "is_import_customer_allowed",
    "default_customer_id", "manage_taxes_on_order_lines",
    "order_process_rule_ids", "payment_method_mapping_ids",
    "default_payment_journal_id", "default_payment_method_line_id",
    "default_deposit_account_id", "allow_update_order",
    "min_order_date_created",
    # sync state (TC-CHN-005) and the dashboard (TC-CHN-011)
    "last_sync_order", "last_sync_product", PERIOD_FIELD,
]


def store_values(ctx, store_id: int, context=None) -> dict:
    """Read every FG-08 field of the store, skipping any this database does
    not have (so a partly-installed stack reports the gap instead of
    erroring)."""
    rpc = readonly_rpc(ctx)
    available = channel_fields(ctx)
    wanted = [f for f in STORE_FIELDS if f in available or f == "id"]
    absent = [f for f in STORE_FIELDS if f not in available and f != "id"]
    if absent:
        ctx.log(f"fields not present on this database (skipped): {absent}")
    return rpc.read(CHANNEL, [store_id], wanted)[0]


# ------------------------------------------------- secret-bearing fields
#: Read to prove "not empty" and NEVER logged. ``shopify_access_token`` and
#: ``app_client_secret`` are non-stored computes over the channel secret
#: store (``ir.config_parameter``, System-only ACL) and carry
#: ``groups='omni_manage_channel.group_listing_manager,base.group_erp_manager'``
#: (FG-19 BC-OMC-001 / D-2 —
#: ``omni_manage_channel/models/ecommerce_channel.py:60-68, 150-172`` and
#: ``multichannel_shopify/models/ecommerce_channel.py:50-62``). A read by a
#: user outside those groups returns nothing, which is a legitimate outcome
#: to report rather than a failure to assert around.
SECRET_FIELDS = ("shopify_access_token", "app_client_secret")


def secret_state(ctx, store_id: int) -> dict:
    """``{field: 'set' | 'empty' | 'not readable by this user'}``.

    The value itself never leaves this function — the workbook only asks
    the tester to confirm the token "is not empty", and the platform must
    not put a live Shopify token into an execution log or a CSV artifact.
    """
    rpc = readonly_rpc(ctx)
    available = channel_fields(ctx)
    out = {}
    for name in SECRET_FIELDS:
        if name not in available:
            out[name] = "field absent on this database"
            continue
        try:
            raw = rpc.read(CHANNEL, [store_id], [name])[0]
        except OdooRPCError as exc:
            out[name] = f"read refused ({exc})"
            continue
        if name not in raw:
            out[name] = ("not readable by this user — the field is "
                         "group-restricted (FG-19 D-2)")
            continue
        value = raw[name]
        out[name] = "set" if value else "empty"
        if value:
            # length only; never the value, and never a hash of a live token
            out[f"{name}__length"] = len(str(value))
    return out


# --------------------------------------------------------------- the clock
def server_now(ctx):
    """The **server's** current time, and where it came from.

    "Last Order Sync … is not today's date" (TC-CHN-005) has to be decided
    against the database's clock, not the workstation's: the two can differ
    by a day across a timezone boundary and the workbook's whole point is
    that a *fresh* timestamp means the migration re-stamped it
    (``last_sync_order`` carries ``default=fields.Datetime.now`` —
    ``omni_manage_channel/models/ecommerce_channel.py:83``).

    The web session this platform opens has just authenticated, and
    ``_login`` calls ``_update_last_login`` which creates a ``res.users.log``
    row (``odoo/addons/base/models/res_users.py:742-746, 775``);
    ``res.users.login_date`` is related to that row's ``create_date``
    (``res_users.py:233``). So the current user's ``login_date`` *is* the
    server clock, to within the age of this run.

    Which clock, precisely: **UTC**. ``create_date`` is stamped from the
    cursor's ``now() AT TIME ZONE 'UTC'`` (``odoo/sql_db.py:272-274``), so
    what comes back here is UTC and *not* the wall clock of the machine the
    Odoo process runs on. For TC-CHN-005's "is not today's date" the two
    disagree only on the hours either side of local midnight; for the
    dashboard window it is load-bearing every day — see
    :func:`window_start_candidates`.
    """
    rpc = readonly_rpc(ctx)
    try:
        row = rpc.read("res.users", [rpc.uid], ["login_date"])[0]
        raw = row.get("login_date")
        if raw:
            return _parse_dt(raw), f"res.users({rpc.uid}).login_date"
    except OdooRPCError as exc:
        ctx.log(f"[warn] could not read login_date ({exc})")
    try:
        rows = rpc.search_read("res.users.log", [], ["create_date"],
                               order="id desc", limit=1)
        if rows and rows[0].get("create_date"):
            return _parse_dt(rows[0]["create_date"]), \
                "res.users.log newest create_date"
    except OdooRPCError as exc:
        ctx.log(f"[warn] could not read res.users.log ({exc})")
    ctx.log("[warn] falling back to the PLATFORM host's clock for 'today' — "
            "if the database server is in another timezone, judge the "
            "'not today' assertion by hand")
    return datetime.now(), "platform host clock (fallback)"


def _parse_dt(raw):
    if isinstance(raw, datetime):
        return raw
    text = str(raw).strip().replace("T", " ")
    text = re.sub(r"\.\d+$", "", text)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def as_date(raw):
    parsed = _parse_dt(raw) if raw else None
    return parsed.date() if isinstance(parsed, datetime) else None


def window_start(now_utc: datetime, days: int) -> datetime:
    """The window the dashboard queries, rebuilt from a UTC clock.

    Both producers use ``datetime.now().replace(hour=0, minute=0,
    second=0) - timedelta(days=delta)``
    (``multichannel_order/models/ecommerce_channel.py:228-229, 290-291``) —
    note that ``microsecond`` is NOT zeroed, so the real boundary carries
    the call's microseconds and there is no upper bound at all (a
    future-dated order is counted).

    The clock this suite can read (:func:`server_now`) is second-resolution,
    so the reproduced boundary is ``00:00:00.000000`` — at most one second
    *earlier* than the card's. An order stamped inside that sub-second
    sliver would be counted here and not there; the recomputation logs the
    boundary it used so such a one-order disagreement can be recognised for
    what it is rather than read as a defect.

    That sliver is the SMALL discrepancy. The large one is the timezone:
    this rebuilds the boundary from UTC while the product builds it from
    the Odoo process's local clock. Any comparison against a figure the
    product produced must go through :func:`window_start_candidates`.
    """
    return now_utc.replace(hour=0, minute=0, second=0) - timedelta(days=days)


def window_start_candidates(now_utc: datetime, days: int) -> list:
    """Every boundary the card's query could be using, given that the
    server's own timezone is not readable. ``[(label, boundary, shift)]``.

    ``_get_dashboard_datas_query`` takes its boundary from
    ``datetime.now()`` — a NAIVE local timestamp, i.e. the wall clock of
    the machine the Odoo process runs on (``multichannel_order/models/
    ecommerce_channel.py:229``; ``get_graph_datas`` does the same at
    ``:292``). :func:`server_now` returns ``res.users.login_date``, which
    is ``res.users.log.create_date``, stamped ``now() AT TIME ZONE 'UTC'``
    (``odoo/sql_db.py:272-274``). On a server that does not run in UTC the
    two differ by the UTC offset — and because the expression zeroes the
    time before subtracting, they differ by a WHOLE DAY of orders for as
    many hours of each day as that offset is wide.

    Nothing this suite may call reports that local clock: ``ReadOnlyRPC``
    allows reads only, ``res.users.context_get`` returns the *user's* tz
    preference rather than the server's, and ``ctx.sql`` would report
    BLOCKED wherever it is unconfigured — and would be the PostgreSQL
    host's clock, not the Odoo host's, even where it is configured. So the
    offset is not measured; it is bounded. Real UTC offsets run from -12:00
    to +14:00, so the server's local date is the UTC date, the day before,
    or the day after. All three boundaries are returned so a caller can
    compare a product figure against the resulting envelope rather than
    against one guess. Where the three windows hold the same orders the
    envelope collapses and the comparison is exact, which is the normal
    case; where they do not, a timezone difference is reported as one
    instead of being triaged as a GATE-6 product defect.
    """
    return [
        (label, window_start(now_utc + timedelta(days=shift), days), shift)
        for shift, label in (
            (-1, "server clock a day BEHIND UTC"),
            (0, "server clock on the same date as UTC"),
            (1, "server clock a day AHEAD of UTC"),
        )
    ]


# ---------------------------------------------------- dashboard payloads
def dashboard_payload(ctx, store_id: int) -> dict:
    """``get_dashboard_datas()`` — exactly what the Overview card renders.

    ``multichannel_order`` **overrides** the base producer without calling
    ``super()`` (``multichannel_order/models/ecommerce_channel.py:212-223``),
    so on an installed stack this returns ``total_sales`` /
    ``num_of_orders`` / ``num_of_unshipped_orders`` / ``lead_time`` (each
    with a ``formatted_`` twin) and **not** the base module's
    ``sales_unit`` / ``sales_total``
    (``omni_manage_channel/models/ecommerce_channel.py:530-572``). That
    matters for TC-CHN-011 — see the findings section of the suite doc.
    """
    return readonly_rpc(ctx).call(CHANNEL, "get_dashboard_datas",
                                  [store_id]) or {}


def graph_payload(ctx, store_id: int) -> dict:
    """``get_graph_datas()`` — the series behind the card's sales graph
    (``multichannel_order/models/ecommerce_channel.py:286-360``)."""
    return readonly_rpc(ctx).call(CHANNEL, "get_graph_datas",
                                  [store_id]) or {}


#: The keys ``_process_dashboard_datas`` returns
#: (multichannel_order/models/ecommerce_channel.py:253-283) — i.e. what the
#: Store Statistics panel and the card can bind to.
DASHBOARD_KEYS = ("total_sales", "formatted_total_sales",
                  "num_of_orders", "formatted_num_of_orders",
                  "num_of_unshipped_orders",
                  "formatted_num_of_unshipped_orders",
                  "lead_time", "formatted_lead_time")

#: The keys the BASE module's producer returned, which the v15 card
#: displayed as "Total sales last 30 days" / "Total orders last 30 days".
BASE_DASHBOARD_KEYS = ("sales_total", "sales_unit")


#: Sales > Orders > Orders. Its default facet is
#: ``search_default_sales`` -> ``[('state', '=', 'sale')]``
#: (``odoo-19.0/addons/sale/views/sale_order_views.xml:978``), which is the
#: same state the dashboard query uses — so a step-9 comparison done with
#: the screen's default facet left alone agrees with the card by
#: construction, and one done with it cleared does not.
SALE_ORDERS_ACTION = "sale.action_orders"
SALE_ORDERS_DEFAULT_STATES = ("sale",)
#: The "Store" group-by the workbook's step 9 uses
#: (``multichannel_order/views/sale_order_views.xml:243``).
SALE_STORE_GROUPBY = "channel_id"


def channel_order_domain(store_id: int, start: datetime,
                         states=("sale",)) -> list:
    """The dashboard's own order domain, in ORM form.

    ``_get_dashboard_datas_query`` selects
    ``date_order >= %(date_from)s AND channel_id = %(channel_id)s AND
    state = 'sale'`` (``multichannel_order/models/ecommerce_channel.py:
    229-247``). BC-016 is quoted inline there: ``'done'`` is not a v19
    sale-order state, so the v15 ``state IN ('sale','done')`` of the base
    module's query became a single-state test.
    """
    return [("channel_id", "=", store_id),
            ("date_order", ">=", start.strftime("%Y-%m-%d %H:%M:%S")),
            ("state", "in", list(states))]


def count_and_total(ctx, domain: list) -> dict:
    """Read-only ``COUNT`` / ``SUM(amount_total)`` over sale.order for a
    domain, plus the unshipped count the statistics panel shows."""
    rpc = readonly_rpc(ctx)
    rows = rpc.search_read(SALE_ORDER, domain,
                           ["amount_total", "shipping_status", "date_order",
                            "create_date"])
    total = sum(r.get("amount_total") or 0.0 for r in rows)
    unshipped = sum(1 for r in rows
                    if r.get("shipping_status") == "unshipped")
    return {"count": len(rows), "total": round(total, 2),
            "unshipped": unshipped, "rows": rows}


#: ``lead_time`` / ``formatted_lead_time`` carry a " day"/" days" tail
#: (``multichannel_order/models/ecommerce_channel.py:282-283``).
_DAY_TAIL = re.compile(r"\s*days?\s*$", re.IGNORECASE)
#: ``readable_repr`` abbreviates above its threshold and appends a magnitude
#: suffix — K, M, B, T and a long tail of others
#: (``multichannel_order/utils/utils.py:22-27``). Any of them makes the
#: figure not comparable, so it is reported rather than mis-parsed.
_MAGNITUDE_TAIL = re.compile(r"[A-Za-z]+\s*$")


def number_from(text) -> float | None:
    """Pull the numeric part out of a formatted dashboard figure.

    The dashboard returns strings, not numbers. Every figure goes through
    ``thousand_repr(value, dg=0)`` — ``'{:,.0f}'``, so comma grouping and
    **no** decimal part — optionally wrapped by ``currency_repr`` (a
    currency symbol joined with a space, before or after depending on
    ``currency.position``) or produced by ``readable_repr``, which
    abbreviates above its threshold (``multichannel_order/utils/utils.py:
    4-5, 12-45, 47-56``).

    Returns ``None`` — never a wrong number — when the figure was
    abbreviated, so the caller reports it instead of asserting against it.

    Separator handling: with a single separator whose tail is exactly three
    digits the separator is read as thousands grouping, which is what this
    producer emits. That means a genuine three-decimal figure like
    ``"1.234"`` would be read as 1234 — impossible from ``dg=0``, and noted
    here rather than left as a silent assumption.
    """
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    cleaned = _DAY_TAIL.sub("", str(text).strip())
    if _MAGNITUDE_TAIL.search(cleaned):
        return None                      # abbreviated: not comparable
    cleaned = re.sub(r"[^\d.,\-]", "", cleaned)
    if not cleaned.strip("-"):
        return None
    separator = max(cleaned.rfind("."), cleaned.rfind(","))
    if separator == -1:
        number = cleaned
    else:
        head, tail = cleaned[:separator], cleaned[separator + 1:]
        if len(tail) == 3 and head.lstrip("-").replace(".", "")                 .replace(",", "").isdigit():
            number = cleaned.replace(".", "").replace(",", "")
        else:
            number = (head.replace(".", "").replace(",", "") + "." + tail)
    try:
        return float(number)
    except ValueError:
        return None


def date_only(value) -> date | None:
    return as_date(value)
