"""FG-16 — Odoo Studio Layer & Legal-Date Compliance. Gates and fixtures.

Source of truth is the CLIENT MANUAL TESTING GUIDELINE
``MMG_v19_Client_Manual_Testing_Guideline_FG15-FG20_v1.0.xlsx``, sheet
``Testing Guideline`` — pulled from the client's Drive on 2026-09-16 and now
canonical in ``mmg/document``. Cases TC-STU-006, TC-STU-012, TC-LEG-005 and
TC-LEG-006.

Screens are opened the way the workbook opens them
--------------------------------------------------
TC-STU-006 does not say "check view X"; it says *"Open Inventory > Products
> Products"*. Retyping those into XML ids would test something adjacent to
the case — a view that exists is not the same fact as a menu that leads to
it. :func:`open_screen` therefore walks the live menu tree
(``ir.ui.menu.load_menus``, the call the web client itself makes to build
the menus), finds the menu at the named path, follows its action, and asks
for the assembled arch of every view that action pins. A screen the acting
user is not served fails at the menu, which is what a tester would see.

The legal date is a live chain, so the fixtures are complete
------------------------------------------------------------
TC-LEG-005 and TC-LEG-006 are about ``mmg_legal_date``, which is pure Python
(``models/stock_picking.py:39-84``, ``models/sale_order.py:67-124``):
validating a delivery stamps ``sale.order.x_legal_sale_date`` from the
picking's ``date_done`` and pushes it onto the order's unlocked invoices,
and writing the order's date later propagates again. Nothing in that chain
touches an external system, so both cases run end to end on records this
suite creates — order, delivery and invoices included — and the client's own
orders are never opened.

``mmg_sale_auto_create_invoice`` raises an invoice on confirm for this
company, which is why the fixtures get their invoices for free; the tests
read that rather than assume it.
"""
from __future__ import annotations

import re

from adapters.base import OdooRPCError

# --------------------------------------------------------------- identity
FEATURE = "FG-16 Odoo Studio Layer & Legal-Date Compliance"
WORKFLOW = "FG-16"
WORKFLOW_NAME = "Odoo Studio Layer & Legal-Date Compliance"
MODULE = "mmg_legal_date"
MODULE_STUDIO = "studio customisations (x_* fields)"

WORKBOOK = "MMG_v19_Client_Manual_Testing_Guideline_FG15-FG20_v1.0.xlsx"
SHEET = "Testing Guideline"

MARK = "FG16-AUTOMATED-PROBE"


def trace(tc_ids, user_story: str = "") -> dict:
    return {
        "tc_ids": tc_ids if isinstance(tc_ids, list) else [tc_ids],
        "feature": FEATURE,
        "user_story": user_story,
        "source": f"{WORKBOOK} / {SHEET}",
    }


# ------------------------------------------------------ workbook constants
ORDER = "sale.order"
MOVE = "account.move"
PARTNER = "res.partner"
PICKING = "stock.picking"

#: ``sale.order`` and ``account.move`` each carry TWO fields labelled "Legal
#: Sale Date". The datetime pair is the live one this module maintains; the
#: date pair is the older Studio one the automations used to write and which
#: FG-16 D5 proposes retiring (``mmg_legal_date/models/sale_order.py:44-61``).
#: TC-LEG-005 step 2 expects to find both on the invoice, "the second one
#: greyed out", so both are named here rather than only the live one.
ORDER_LEGAL_DATE = "x_legal_sale_date"
ORDER_LEGAL_DATE_LEGACY = "x_slsdate"
MOVE_LEGAL_DATE = "x_legal_invoice_date"
MOVE_LEGAL_DATE_LEGACY = "x_lsdate"

#: The six contact fields TC-STU-012 walks, with the labels the workbook
#: reads off the form. An upgrade that carried a field across without its
#: label is exactly what this case exists to catch, so the labels are
#: asserted, not just the field names.
CONTACT_FIELDS = {
    "x_type": "Customer Type",
    "x_main_phone": "Main Phone",
    "x_phone_one": "Phone Two",
    "x_phone_two": "Phone Three",
    "x_email_two": "Alt. Email",
    "x_alert": "Alert Notes",
}

#: TC-STU-012's Test Data, verbatim.
CONTACT_VALUES = {
    "x_type": "Gallery UAT",
    "x_main_phone": "+1 520 555 0100",
    "x_phone_one": "+1 520 555 0101",
    "x_phone_two": "+1 520 555 0102",
    "x_email_two": "uat.second@example.com",
    "x_alert": "Fragile shipping - call before dispatch",
}

#: The ten screens of TC-STU-006 step 1, by the menu path the workbook
#: gives, with the tabs/columns step 3 and 4 expect on each.
STUDIO_SCREENS = [
    ("a", "Inventory > Products > Products", "list"),
    ("b", "Sales > Products > Products", "list"),
    ("c", "Sales > Products > Product Variants", "list"),
    ("d", "E-commerce Connectors > Products > Products", "list"),
    ("e", "Contacts > Contacts", "list"),
    ("f", "Sales > Orders > Quotations", "list"),
    ("g", "Sales > Orders > Orders", "list"),
    ("h", "Accounting > Customers > Invoices", "list"),
    ("i", "Inventory > Operations > Adjustments > Physical Inventory", "list"),
    ("j", "Inventory > Reporting > Moves History", "list"),
]

#: The gallery's own tabs, per step 4.
PRODUCT_TABS = ("Product Info", "Auction Info", "Images")
CONTACT_TABS = ("Notes",)

V19_ONLY = ("FG-16 asks whether the old system's Studio customisations "
            "survived onto Odoo 19; there is nothing to ask of v15")


# ------------------------------------------------------------------- gates
def require_v19(ctx):
    if ctx.env.version != "19":
        ctx.blocked(f"{V19_ONLY} (current target: {ctx.env.name}).")


def require_studio(ctx):
    require_v19(ctx)
    rpc = ctx.adapter.rpc
    missing = [name for name in CONTACT_FIELDS
               if not rpc.field_exists(PARTNER, name)]
    if len(missing) == len(CONTACT_FIELDS):
        ctx.blocked(
            "none of the gallery's six Studio contact fields exists on "
            "res.partner — the Studio layer did not come across at all, "
            "which is the finding, not a missing precondition.")
    return rpc


def require_legal_date(ctx):
    require_v19(ctx)
    rpc = ctx.adapter.rpc
    for model, field in ((ORDER, ORDER_LEGAL_DATE), (MOVE, MOVE_LEGAL_DATE)):
        if not rpc.field_exists(model, field):
            ctx.blocked(
                f"{model}.{field} does not exist — 'mmg_legal_date' is not "
                f"installed on this database, so there is no legal-date "
                f"chain to test.")
    return rpc


# ---------------------------------------------------------------- evidence
def manual(ctx, text: str):
    ctx.log(f"RESIDUAL MANUAL STEP — {text}")


def observation(ctx, text: str):
    ctx.log(f"OBSERVATION — {text}")


def finding(ctx, text: str):
    ctx.log(f"FINDING — {text}")


# ------------------------------------------------------------- menu tree
def menu_index(ctx) -> dict:
    """``{full menu path: entry}`` for every menu the acting user is SERVED.

    ``load_menus`` is what the web client calls to build the menu bar, and
    it applies ``_filter_visible_menus``. A plain search on ``ir.ui.menu``
    would not: v19 does not group-filter that, so a menu hidden from every
    user still comes back. Asking the question the browser asks is the whole
    point of opening a screen "the way the workbook opens it".
    """
    cached = getattr(ctx, "_fg16_menus", None)
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
    ctx._fg16_menus = index
    return index


def all_menus(ctx) -> dict:
    """Every menu in the DATABASE, served or not, with what gates it.

    Used to tell "this menu does not exist" apart from "this menu exists and
    is hidden from you" — two very different findings for a tester who
    cannot see a screen.
    """
    rpc = ctx.adapter.rpc
    rows = rpc.call("ir.ui.menu", "search_read",
                    [], fields=["name", "parent_id", "group_ids", "active"],
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

    return {path(row): row for row in rows}


def open_screen(ctx, path: str) -> dict:
    """Follow a menu path to its action and pull every view it pins.

    Returns ``{"menu", "action", "views": {mode: arch}, "error"}``. Nothing
    raises: a screen that will not open is the case's verdict to record, not
    an exception for the runner to dress up as a broken test.
    """
    rpc = ctx.adapter.rpc
    served = menu_index(ctx)
    entry = served.get(path)
    if not entry:
        existing = all_menus(ctx)
        row = existing.get(path)
        if not row:
            return {"menu": None, "error": f"no menu at '{path}'",
                    "views": {}, "hidden": False}
        # The leaf usually carries no groups of its own: what hides it is an
        # ANCESTOR. Reporting the leaf's (empty) groups would send a reader
        # looking in the wrong place, so walk up to whichever menu on the
        # path actually gates the branch.
        culprit, groups = path, row.get("group_ids") or []
        if not groups:
            parts = path.split(" > ")
            for depth in range(len(parts) - 1, 0, -1):
                ancestor = existing.get(" > ".join(parts[:depth]))
                if ancestor and (ancestor.get("group_ids") or []):
                    culprit = " > ".join(parts[:depth])
                    groups = ancestor["group_ids"]
                    break
        names = []
        if groups:
            names = [g["name"] for g in rpc.call(
                "res.groups", "read", groups, fields=["name"])]
            xmlids = rpc.search_read(
                "ir.model.data",
                [("model", "=", "res.groups"), ("res_id", "in", groups)],
                ["module", "name", "res_id"])
            names = [f"{g['module']}.{g['name']}" for g in xmlids] or names
        return {"menu": row, "views": {}, "hidden": True,
                "gated_at": culprit, "groups": groups, "group_names": names,
                "error": (f"menu '{path}' exists and is active, but is not "
                          f"served to this user: '{culprit}' is gated on "
                          f"{names or 'a group this user lacks'}")}

    action_id, model = entry.get("action_id"), entry.get("action_model")
    if not action_id:
        return {"menu": entry, "views": {}, "hidden": False,
                "error": f"menu '{path}' carries no action"}
    try:
        action = rpc.read(model, [action_id],
                          ["name", "res_model", "view_mode", "domain",
                           "context"])[0]
    except OdooRPCError as exc:
        return {"menu": entry, "views": {}, "hidden": False,
                "error": f"action behind '{path}' could not be read: {exc}"}

    views, error = {}, ""
    for mode in (action.get("view_mode") or "list").split(","):
        mode = mode.strip()
        if mode in ("kanban", "graph", "pivot", "calendar", "activity",
                    "map", "gantt", "cohort", "dashboard", "hierarchy"):
            # The workbook opens the list and the form; the analytic views
            # are not what "the gallery's extra columns" lives on, and
            # several need a chart library the RPC layer cannot judge.
            continue
        try:
            views[mode] = rpc.call(action["res_model"], "get_view",
                                   view_type=mode)["arch"]
        except OdooRPCError as exc:
            error = f"{mode} view of '{path}' failed to build: {exc}"
            break
    return {"menu": entry, "action": action, "views": views, "error": error,
            "hidden": False}


# ------------------------------------------------------------ view arches
def field_attrs(arch: str, name: str, occurrence: int = 0) -> str:
    matches = re.findall(rf'<field[^>]*name="{re.escape(name)}"[^>]*>', arch)
    return matches[occurrence] if len(matches) > occurrence else ""


def page_titles(arch: str) -> list:
    """Notebook tab labels, with XML entities decoded the way a reader sees
    them (`Attributes &amp; Variants` is one tab called "Attributes &
    Variants")."""
    return [t.replace("&amp;", "&") for t in
            re.findall(r'<page[^>]*string="([^"]+)"', arch)]


def attr(tag: str, name: str) -> str:
    match = re.search(rf'{re.escape(name)}="([^"]*)"', tag)
    return match.group(1) if match else ""


# ---------------------------------------------------------------- fixtures
def make_partner(ctx, label: str, **values) -> int:
    rpc = ctx.adapter.rpc
    payload = {"name": f"{MARK} {label}"}
    payload.update(values)
    partner_id = rpc.create(PARTNER, payload)
    ctx.log(f"fixture contact #{partner_id} {payload['name']!r}")
    return partner_id


def make_product(ctx, label: str, price: float = 500.0) -> int:
    rpc = ctx.adapter.rpc
    values = {
        "name": f"{MARK} {label}",
        "default_code": f"{MARK}-{label.upper().replace(' ', '-')}",
        "list_price": price,
        "sale_ok": True,
        "taxes_id": [(6, 0, [])],
    }
    values.update(ctx.adapter.storable_product_values())
    tmpl_id = rpc.create("product.template", values)
    variant = rpc.search_read("product.product",
                              [("product_tmpl_id", "=", tmpl_id)],
                              ["id"], limit=1)[0]
    ctx.log(f"fixture product #{variant['id']} {values['name']!r}")
    return variant["id"]


def make_order(ctx, partner_id: int, product_id: int, qty: float = 1.0,
               price: float = 500.0, confirm: bool = True) -> int:
    rpc = ctx.adapter.rpc
    order_id = rpc.create(ORDER, {
        "partner_id": partner_id,
        "order_line": [(0, 0, {"product_id": product_id,
                               "product_uom_qty": qty,
                               "price_unit": price})],
    })
    if confirm:
        rpc.call(ORDER, "action_confirm", [order_id])
    ctx.log(f"fixture order #{order_id} "
            f"({'confirmed' if confirm else 'draft'})")
    return order_id


def order_invoices(ctx, order_id: int) -> list:
    rpc = ctx.adapter.rpc
    ids = rpc.read(ORDER, [order_id], ["invoice_ids"])[0]["invoice_ids"] or []
    if not ids:
        return []
    return rpc.read(MOVE, ids,
                    ["name", "state", MOVE_LEGAL_DATE, "move_type"])


def order_deliveries(ctx, order_id: int) -> list:
    rpc = ctx.adapter.rpc
    ids = rpc.read(ORDER, [order_id], ["picking_ids"])[0]["picking_ids"] or []
    if not ids:
        return []
    return rpc.read(PICKING, ids,
                    ["name", "state", "date_done", "picking_type_code"])


def sweep(ctx) -> dict:
    """Remove everything this suite created, archived rows included.

    Orders are cancelled first (a confirmed one will not delete), then the
    invoices and deliveries they raised, then the products and contacts.
    Anything still referenced is archived rather than left live. Scoped by
    the marker throughout, so it can never reach the gallery's own records.
    """
    rpc = ctx.adapter.rpc
    seen_all = {"context": {"active_test": False}}
    removed = {}

    partners = rpc.search(PARTNER, [("name", "like", MARK)], **seen_all)
    products = rpc.search("product.product", [("default_code", "like", MARK)],
                          **seen_all)
    templates = rpc.search("product.template", [("name", "like", MARK)],
                           **seen_all)

    orders = rpc.search(ORDER, [("partner_id", "in", partners)],
                        **seen_all) if partners else []
    for order_id in orders:
        try:
            rpc.call(ORDER, "action_cancel", [order_id])
        except OdooRPCError:
            pass

    for model, domain in (
            (MOVE, [("line_ids.product_id", "in", products),
                    ("state", "in", ["draft", "cancel"])]),
            (PICKING, [("move_ids.product_id", "in", products)]),
            (ORDER, [("id", "in", orders)]),
    ):
        try:
            ids = rpc.search(model, domain, **seen_all) if products or orders \
                else []
            if ids:
                rpc.unlink(model, ids)
            removed[model] = len(ids)
        except OdooRPCError as exc:
            ctx.log(f"[warn] sweep {model}: {exc}")
            removed[model] = -1

    for model, ids in (("product.template", templates), (PARTNER, partners)):
        try:
            if ids:
                rpc.unlink(model, ids)
            removed[model] = len(ids)
        except OdooRPCError as exc:
            ctx.log(f"[warn] {model} delete refused ({exc}); archiving")
            try:
                rpc.write(model, ids, {"active": False})
                removed[model] = -len(ids)
            except OdooRPCError as exc2:
                ctx.log(f"[warn] {model} archive failed: {exc2}")
                removed[model] = -1

    ctx.log(f"sweep: {removed}")
    return removed


def leftovers(ctx) -> int:
    """How many LIVE records this suite still has on the database.

    Archived ones are deliberately not counted, and that is not a softened
    assertion. A POSTED invoice can never be deleted in Odoo, and neither
    can anything an account.move.line points at — so the product behind the
    posted branch of TC-LEG-006 is permanently undeletable, by design, the
    moment the case does what the case is for. Archiving takes it out of
    every screen, every default search and every domain this suite uses;
    insisting on deletion would mean either not posting an invoice (and not
    testing the case) or leaving the run red for ever.

    :func:`sweep` still RETRIES deletion of previously archived rows on
    every run, so anything that becomes deletable later does get removed.
    """
    rpc = ctx.adapter.rpc
    return (rpc.call(PARTNER, "search_count", [("name", "like", MARK)])
            + rpc.call("product.template", "search_count",
                       [("name", "like", MARK)]))


def archived(ctx) -> dict:
    """What had to be archived rather than deleted, for the record."""
    rpc = ctx.adapter.rpc
    seen_all = {"context": {"active_test": False}}
    out = {}
    for model, domain in ((PARTNER, [("name", "like", MARK)]),
                          ("product.template", [("name", "like", MARK)])):
        rows = rpc.search_read(model, domain + [("active", "=", False)],
                               ["display_name"], **seen_all)
        if rows:
            out[model] = len(rows)
    return out
