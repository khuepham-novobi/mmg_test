"""FG-15 — UI Widgets & Client Framework. Gates and helpers.

Source of truth is the CLIENT MANUAL TESTING GUIDELINE
``MMG_v19_Client_Manual_Testing_Guideline_FG15-FG20_v1.0.xlsx``, sheet
``Testing Guideline``. Cases TC-UIX-001, -003, -004, -005, -008, -009,
-010 and -011.

This is the feature group about custom OWL widgets, and that shapes what
can be asserted
------------------------------------------------------------------------
Five of the eight cases are about a widget drawing something: a logo beside
a store name, a picture in a Store cell, a chart on a card, tick-boxes
instead of a drop-down. What a widget *renders* is a browser fact. What an
RPC client can establish is the half that decides it — that the field is on
the view, that it carries the widget the gallery's module provides, and
that the data behind it is what the widget will be handed.

That is not a dodge, and it is worth being precise about which half is
which. A blank Store cell has exactly two causes: the column is not there
(server), or the widget failed to draw (browser). This suite settles the
first conclusively and says so plainly about the second, so a tester
reading a green result knows what they still have to look at. Every case
that needs eyes carries a ``RESIDUAL MANUAL STEP`` naming what and why.

One store on this database
--------------------------
TC-UIX-004 compares two store cards' charts and TC-UIX-005 compares two
rows' logos. Both say what to do when there is only one store: *"record it
as N/A and say why"*. This database has one, so those comparisons are
reported N/A with the count rather than passed on a technicality.
"""
from __future__ import annotations

import re

from adapters.base import OdooRPCError

# --------------------------------------------------------------- identity
FEATURE = "FG-15 UI Widgets & Client Framework"
WORKFLOW = "FG-15"
WORKFLOW_NAME = "UI Widgets & Client Framework"
MODULE = "omni_manage_channel"
MODULE_ORDER = "multichannel_order"

WORKBOOK = "MMG_v19_Client_Manual_Testing_Guideline_FG15-FG20_v1.0.xlsx"
SHEET = "Testing Guideline"

MARK = "FG15-AUTOMATED-PROBE"


def trace(tc_ids, user_story: str = "") -> dict:
    return {
        "tc_ids": tc_ids if isinstance(tc_ids, list) else [tc_ids],
        "feature": FEATURE,
        "user_story": user_story,
        "source": f"{WORKBOOK} / {SHEET}",
    }


# ------------------------------------------------------ workbook constants
CHANNEL = "ecommerce.channel"
PRODUCT_CHANNEL = "product.channel"
ORDER = "sale.order"
RULE = "order.process.rule"
STATUS = "order.status.channel"
CARRIER = "shipping.method.channel"

#: TC-UIX-011 step 1, by the menu path the workbook opens each screen from.
#: ``None`` means the screen is reached from the store card's three-dot menu
#: rather than from a menu of its own.
SWEEP_SCREENS = [
    ("a", "E-commerce Connectors > Overview"),
    ("b", "E-commerce Connectors > Products > Products"),
    ("c", "E-commerce Connectors > Products > Product Variants"),
    ("d", "E-commerce Connectors > Products > Product Mappings"),
    ("e", "E-commerce Connectors > Configuration > Store Configuration > "
          "Manage Stores"),
    ("g", "E-commerce Connectors > Configuration > Mappings > Scheduled "
          "Mappings Updates"),
    ("h", "Sales > Orders > Orders"),
    ("i", "Inventory > Operations > Transfers > Deliveries"),
    ("j", "Job Queue > Queue > Jobs"),
]

#: Menus this client removed ON PURPOSE. TC-SMK-003 step 7 allows exactly
#: this and nothing wider: "every menu that existed before must either be
#: present, or be on Novobi's list of menus deliberately removed."
#:
#: THE RULES THIS LIST OBEYS, because an allowance is how a P0 case gets
#: quietly weakened:
#:  1. Every entry names WHERE the decision is written down. A path with no
#:     citation is not evidence, it is an excuse, and does not go here.
#:  2. An entry is honoured only while the menu is genuinely ARCHIVED. A
#:     menu that is active and merely unreachable - broken action, missing
#:     group - is a defect wearing a removal's clothes and still fails the
#:     case. removal_allowed() enforces that; the list alone cannot.
#:  3. The allowance is still LOGGED and still reported as an observation.
#:     Nothing disappears; it moves from "fail" to "fail nothing, and tell
#:     the reader why".
DELIBERATELY_REMOVED = {
    "E-commerce Connectors > Products > Product Variants":
        "NOVOBI-514 - MMG hides every Product Variants menu under the E-commerce connector. The decision is recorded in mmg_19-custom/tools/staging19_cleanup.sh step 4g, whose WANT_OFF list re-archives 'multichannel_product.menu_omniborder_product_variants' on every staging rebuild and names the v15 enforcer that used to do it (mmg_multichannel_shopify, FG-10b, not ported). Measured on this database: 69,539 templates against 69,539 variants, and only 6 templates with more than one variant - the variant list shows nothing the product list does not.",
}


def all_menus(ctx) -> dict:
    """Every menu in the DATABASE by full path, archived ones included.

    ``complete_name`` is a non-stored compute on ir.ui.menu, so it cannot be
    searched; the path has to be rebuilt from parent_id like this.
    """
    cached = getattr(ctx, "_fg15_all_menus", None)
    if cached is not None:
        return cached
    rows = ctx.adapter.rpc.call(
        "ir.ui.menu", "search_read", [],
        fields=["name", "parent_id", "active"],
        context={"active_test": False}, limit=0)
    by_id = {row["id"]: row for row in rows}

    def path(row):
        names, seen = [], set()
        while row and row["id"] not in seen:
            seen.add(row["id"])
            names.append(row["name"])
            ref = row["parent_id"]
            row = by_id.get(ref[0]) if isinstance(ref, (list, tuple)) else None
        return " > ".join(reversed(names))

    index = {path(row): row for row in rows}
    ctx._fg15_all_menus = index
    return index


def removal_allowed(ctx, path: str) -> str:
    """The evidence for ``path`` being absent on purpose, or "" if none.

    Returns "" for a menu absent for any reason OTHER than being archived,
    so a broken or group-gated screen can never borrow this list's
    permission.
    """
    why = DELIBERATELY_REMOVED.get(path)
    if not why:
        return ""
    row = all_menus(ctx).get(path)
    if not row:
        return ""                       # gone entirely, not archived
    if row.get("active"):
        return ""                       # active but unreachable = a defect
    return why


#: Step 1k: one entry under the store card's 'Log' heading.
LOG_ACTION = "open_log_import_order"

#: The custom widgets this feature group exists for, by where they live.
#: Each is provided by one of the gallery's own modules — none is stock
#: Odoo — which is why an upgrade can silently drop one.
WIDGETS = {
    (CHANNEL, "list", "logo_and_name"): "logo_and_name_field",
    (ORDER, "list", "channel_id"): "many2one_store_field",
    (PRODUCT_CHANNEL, "list", "channel_id"): "many2one_store_field",
    ("product.template", "list", "active_channel_ids"): "many2many_store_field",
    (RULE, "form", "order_status_channel_ids"):
        "many2many_checkboxes_select_all_field",
    (CHANNEL, "form", "auto_import_data"): "boolean_button",
    (CHANNEL, "form", "active"): "boolean_button",
    (CARRIER, "form", "active"): "boolean_button",
}

#: TC-UIX-008 step 4: what the Manage Stores list must NOT offer.
STORE_LIST_FORBIDDEN = ("create", "edit", "delete", "export_xlsx")

#: TC-UIX-001 step 5: no payment status may appear in the fulfilment list.
#: ``order.status.channel.type`` is the field that separates them.
FULFILMENT = "fulfillment"
PAYMENT = "payment"

V19_ONLY = ("FG-15 is about the v19 omnichannel screens and the custom "
            "widgets on them")


# ------------------------------------------------------------------- gates
def require_v19(ctx):
    if ctx.env.version != "19":
        ctx.blocked(f"{V19_ONLY} (current target: {ctx.env.name}).")
    return ctx.adapter.rpc


def require_connector(ctx):
    rpc = require_v19(ctx)
    if not rpc.model_exists(CHANNEL):
        ctx.blocked(
            f"model '{CHANNEL}' does not exist — the e-commerce connector "
            f"stack is not installed, so none of FG-15's screens exist.")
    return rpc


def stores(ctx) -> list:
    return ctx.adapter.rpc.search_read(
        CHANNEL, [], ["name", "platform", "active", "auto_import_data"],
        order="id")


# ---------------------------------------------------------------- evidence
def manual(ctx, text: str):
    ctx.log(f"RESIDUAL MANUAL STEP — {text}")


def observation(ctx, text: str):
    ctx.log(f"OBSERVATION — {text}")


def finding(ctx, text: str):
    ctx.log(f"FINDING — {text}")


def not_applicable(ctx, text: str):
    """A comparison the workbook itself says to mark N/A, with the reason.

    Recorded rather than quietly skipped: "two charts differ" cannot be
    judged with one chart, and a reader of a green result is entitled to
    know that half the case did not run.
    """
    ctx.log(f"N/A — {text}")


# ------------------------------------------------------------- menu tree
def served_menus(ctx) -> dict:
    cached = getattr(ctx, "_fg15_menus", None)
    if cached is not None:
        return cached
    served = ctx.adapter.rpc.call("ir.ui.menu", "load_menus", False)
    by_id = {int(k): v for k, v in served.items() if str(k).isdigit()}
    parent = {}
    for mid, entry in by_id.items():
        for child in entry.get("children") or []:
            parent[child] = mid

    def path(mid):
        names, seen = [], set()
        while mid in by_id and mid not in seen:
            seen.add(mid)
            names.append(by_id[mid]["name"])
            mid = parent.get(mid)
        return " > ".join(reversed(names))

    index = {path(mid): entry for mid, entry in by_id.items()}
    ctx._fg15_menus = index
    return index


def open_screen(ctx, path: str) -> dict:
    """Follow a menu path to its action and build every view it pins."""
    rpc = ctx.adapter.rpc
    entry = served_menus(ctx).get(path)
    if not entry:
        return {"views": {}, "error": f"menu '{path}' is not served to this "
                                      f"user"}
    action_id, model = entry.get("action_id"), entry.get("action_model")
    if not action_id:
        return {"views": {}, "error": f"menu '{path}' carries no action"}
    if model != "ir.actions.act_window":
        return {"views": {}, "error": "", "kind": model}
    try:
        action = rpc.read(model, [action_id],
                          ["name", "res_model", "view_mode"])[0]
    except OdooRPCError as exc:
        return {"views": {}, "error": f"its action could not be read: {exc}"}

    views, error = {}, ""
    for mode in (action.get("view_mode") or "list").split(","):
        mode = mode.strip()
        if mode not in ("list", "form", "kanban", "search"):
            continue
        try:
            views[mode] = rpc.call(action["res_model"], "get_view",
                                   view_type=mode)["arch"]
        except OdooRPCError as exc:
            error = f"its {mode} view will not build: {exc}"
            break
    return {"action": action, "views": views, "error": error}


# ------------------------------------------------------------ view arches
def field_attrs(arch: str, name: str, occurrence: int = 0) -> str:
    matches = re.findall(rf'<field[^>]*name="{re.escape(name)}"[^>]*>', arch)
    return matches[occurrence] if len(matches) > occurrence else ""


def all_field_tags(arch: str, name: str) -> list:
    return re.findall(rf'<field[^>]*name="{re.escape(name)}"[^>]*>', arch)


def root_attrs(arch: str, tag: str) -> str:
    match = re.search(rf'<{tag}[^>]*>', arch)
    return match.group(0) if match else ""


def attr(tag: str, name: str) -> str:
    match = re.search(rf'{re.escape(name)}="([^"]*)"', tag)
    return match.group(1) if match else ""


def widget_of(ctx, model: str, view_type: str, field: str) -> str:
    """The widget a field carries on the assembled view, or ``''``.

    Assembled, not source: what the browser is handed is what decides
    whether the gallery's widget is the one that runs.
    """
    try:
        arch = ctx.adapter.rpc.call(model, "get_view",
                                    view_type=view_type)["arch"]
    except OdooRPCError:
        return ""
    for tag in all_field_tags(arch, field):
        found = attr(tag, "widget")
        if found:
            return found
    return ""
