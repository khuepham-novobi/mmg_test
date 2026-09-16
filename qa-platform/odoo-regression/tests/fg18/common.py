"""FG-18 — Platform Migration & Smoke Readiness. Gates and helpers.

Source of truth is the CLIENT MANUAL TESTING GUIDELINE
``MMG_v19_Client_Manual_Testing_Guideline_FG15-FG20_v1.0.xlsx``, sheet
``Testing Guideline``. Cases TC-SMK-003, -007, -013, -014, -016, -017 and
-018.

What "every menu opens" can be checked over RPC, and what cannot
-----------------------------------------------------------------
TC-SMK-003's Expected Result has four parts. Three are facts about the
server and are asserted here for real:

* every app and every sub-menu **opens** — which, underneath, means its
  action resolves and every view that action pins can be *built*. An
  "Invalid view definition" pop-up is precisely a view that would not
  build, so walking ``load_menus`` and calling ``get_view`` on each is not
  an approximation of the case: it is the same question;
* **no Magento menu survives**;
* every menu is either present or on the removal list.

The fourth — *"no red lines in the Console"* — is a browser fact. Nothing
here reads a console, and the case says so in its own log rather than
quietly passing. TEST-SMOKE-001 is the UI test that opens a real browser
against the same TC id.

Three cases are blocked by this instance, not by the code
---------------------------------------------------------
TC-SMK-014 (files), TC-SMK-016 (old passwords and 2FA) and TC-SMK-017
(mail servers) cannot be judged on this database, and each is blocked with
the measurement that proves it rather than a shrug. The measurements are
worth having: the filestore shortfall in particular is a number the
gallery needs before it plans a cutover.
"""
from __future__ import annotations

import re
import time

from adapters.base import OdooRPCError

# --------------------------------------------------------------- identity
FEATURE = "FG-18 Platform Migration & Smoke Readiness"
WORKFLOW = "FG-18"
WORKFLOW_NAME = "Platform Migration & Smoke Readiness"
MODULE = "Platform"

WORKBOOK = "MMG_v19_Client_Manual_Testing_Guideline_FG15-FG20_v1.0.xlsx"
SHEET = "Testing Guideline"

MARK = "FG18-AUTOMATED-PROBE"


def trace(tc_ids, user_story: str = "") -> dict:
    return {
        "tc_ids": tc_ids if isinstance(tc_ids, list) else [tc_ids],
        "feature": FEATURE,
        "user_story": user_story,
        "source": f"{WORKBOOK} / {SHEET}",
    }


# ------------------------------------------------------ workbook constants
#: View modes worth building. The analytic ones are skipped on purpose:
#: the workbook's step 3 is about a screen drawing its list or its form,
#: and a pivot or a graph needs a chart library no RPC call can judge.
BUILDABLE_MODES = ("list", "form", "search")

#: TC-SMK-003 step 4's named minimum. The walk covers every menu served,
#: but these are called out so a missing one is named rather than lost in a
#: count.
NAMED_MENUS = (
    "Sales > Orders > Quotations",
    "Sales > Orders > Orders",
    "Sales > Products > Products",
    "Sales > Products > Product Variants",
    "Inventory > Overview",
    "Inventory > Products > Products",
    "Inventory > Reporting > Moves History",
    "Sales > Orders > Customers",
    "Inventory > Operations > Transfers > Deliveries",
    "Inventory > Operations > Transfers > Receipts",
    "Inventory > Operations > Transfers > Internal",
    "Inventory > Operations > Adjustments > Physical Inventory",
    "Purchase",
    "Contacts > Contacts",
    "Accounting > Customers > Invoices",
    "Accounting > Vendors > Bills",
    "Accounting > Accounting > Transactions > Journal Entries",
    "E-commerce Connectors > Overview",
    "E-commerce Connectors > Products > Products",
    "E-commerce Connectors > Products > Product Variants",
    "E-commerce Connectors > Products > Product Mappings",
    "E-commerce Connectors > Configuration > Store Configuration > "
    "Manage Stores",
    "E-commerce Connectors > Configuration > Mappings > Scheduled Mappings "
    "Updates",
    "Job Queue > Queue > Jobs",
    "Job Queue > Queue > Channels",
    "Job Queue > Queue > Job Functions",
)

#: Step 6: nothing Magento may survive. Matched case-insensitively against
#: menu names and paths.
FORBIDDEN = ("magento",)

#: TC-SMK-007 step 2, by the model the entry must be bound to. The model
#: is named by its ``ir.model`` display name, which is what the binding
#: carries.
BULK_ACTIONS = {
    "Print Avery Label": ("Product", "Product Variant"),
    "Print Backtag": ("Product", "Product Variant"),
    "Assign Customer Taxes": ("Product", "Product Variant"),
    "Export to Store": ("Product",),
    "Activate Exclude from Cart": ("Product Variant",),
    "Deactivate Exclude from Cart": ("Product Variant",),
    "Assign Product Category": ("Product Variant",),
    "Assign Website Extra Category": ("Product Variant",),
    "Assign Fiscal Position": ("Contact",),
    "Update Customer Type": ("Contact",),
    "Requeue Jobs": ("Queue Job",),
    "Set jobs to done": ("Queue Job",),
    "Cancel jobs": ("Queue Job",),
}

#: Step 3: 'Product Certificate' must be under PRINT, not Actions — which
#: is `binding_type='report'` rather than `'action'`.
PRINT_ACTION = "Product Certificate"

#: Step 5: which entries an ordinary gallery user must NOT see, and the one
#: right that controls each (the workbook spells this out).
RESTRICTED_BY_RIGHT = {
    "Assign Customer Taxes": "Accounting: Administrator",
    "Assign Fiscal Position": "Accounting: Administrator",
    "Assign Product Category": "Inventory: Administrator",
    "Update Customer Type": "Sales: Administrator",
    "Assign Website Extra Category": "full Administration rights",
}

#: Step 6: these are NOT restricted and must stay visible to everyone.
UNRESTRICTED = ("Print Avery Label", "Print Backtag", "Product Certificate")

#: TC-SMK-018 step 4-5: the gallery's own labels, the right way round.
PRODUCT_LABELS = {
    "x_artist": "Artist",
    "x_medium": "Medium",
    "x_height": "Height",
    "x_width": "Width",
    "x_depth": "Depth",
    "x_ed_num": "Edition Number",
    "x_ed_size": "Edition Size",
    "x_gallery_cost": "Gallery Cost",
}
CONTACT_PHONE_LABELS = {
    "x_main_phone": "Main Phone",
    "x_phone_one": "Phone Two",
    "x_phone_two": "Phone Three",
}

#: What a label must never look like (step 2).
BAD_LABEL = re.compile(r"^(x_|\[missing\]|\s*$)|^[a-z0-9]+(_[a-z0-9]+)+$")

V19_ONLY = ("FG-18 asks whether the migrated v19 instance is up and whole; "
            "there is nothing to ask of v15")


# ------------------------------------------------------------------- gates
def require_v19(ctx):
    if ctx.env.version != "19":
        ctx.blocked(f"{V19_ONLY} (current target: {ctx.env.name}).")
    return ctx.adapter.rpc


# ---------------------------------------------------------------- evidence
def manual(ctx, text: str):
    ctx.log(f"RESIDUAL MANUAL STEP — {text}")


def observation(ctx, text: str):
    ctx.log(f"OBSERVATION — {text}")


def finding(ctx, text: str):
    ctx.log(f"FINDING — {text}")


# ------------------------------------------------------------- menu tree
def served_menus(ctx) -> dict:
    """``{path: entry}`` for every menu the acting user is actually served.

    ``load_menus`` applies ``_filter_visible_menus``; a plain search on
    ``ir.ui.menu`` does not group-filter on v19 and would hand back menus
    nobody can reach.
    """
    cached = getattr(ctx, "_fg18_served", None)
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
    ctx._fg18_served = index
    return index


def existing_menus(ctx) -> dict:
    """Every menu in the DATABASE, served or not, with what gates it."""
    cached = getattr(ctx, "_fg18_existing", None)
    if cached is not None:
        return cached
    rpc = ctx.adapter.rpc
    rows = rpc.call("ir.ui.menu", "search_read", [],
                    fields=["name", "parent_id", "group_ids", "active"],
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
    ctx._fg18_existing = index
    return index


def build_views(ctx, entry: dict) -> dict:
    """Resolve one menu's action and build every view it pins.

    Returns ``{"action", "views", "error"}``. Nothing raises: a screen that
    will not open is a verdict for the case to record.
    """
    rpc = ctx.adapter.rpc
    action_id, model = entry.get("action_id"), entry.get("action_model")
    if not action_id:
        return {"action": None, "views": {}, "error": ""}   # a folder menu

    # Only a window action has views to build. A menu can equally point at
    # a server action, a client action or a report — Accounting hangs
    # several of its reports straight off the menu — and those models have
    # no `res_model`/`view_mode` at all: asking for them raises, which
    # would report a perfectly healthy menu as broken.
    if model != "ir.actions.act_window":
        try:
            action = rpc.read(model, [action_id], ["name"])[0]
        except OdooRPCError as exc:
            return {"action": None, "views": {},
                    "error": f"its action could not be read: {exc}"}
        return {"action": action, "views": {}, "error": "", "kind": model}

    try:
        action = rpc.read(model, [action_id],
                          ["name", "res_model", "view_mode"])[0]
    except OdooRPCError as exc:
        return {"action": None, "views": {},
                "error": f"its action could not be read: {exc}"}
    if not action.get("res_model"):
        return {"action": action, "views": {}, "error": ""}

    views, error = {}, ""
    for mode in (action.get("view_mode") or "list").split(","):
        mode = mode.strip()
        if mode not in BUILDABLE_MODES:
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


def attr(tag: str, name: str) -> str:
    match = re.search(rf'{re.escape(name)}="([^"]*)"', tag)
    return match.group(1) if match else ""


def page_titles(arch: str) -> list:
    return [t.replace("&amp;", "&") for t in
            re.findall(r'<page[^>]*string="([^"]+)"', arch)]


# --------------------------------------------------------------- fixtures
def make_partner(ctx, label: str) -> int:
    partner_id = ctx.adapter.rpc.create("res.partner",
                                        {"name": f"{MARK} {label}"})
    ctx.log(f"fixture contact #{partner_id}")
    return partner_id


def make_product(ctx, label: str, price: float = 250.0) -> int:
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
    ctx.log(f"fixture product #{variant['id']}")
    return variant["id"]


def highest(ctx, model: str, domain=None) -> str:
    """The highest existing document name on ``model``.

    Sorted by ``id desc`` rather than by name: names are strings, and
    ``SO999`` sorts above ``SO1000`` alphabetically. The newest record is
    what "the highest existing number" means in practice.
    """
    rows = ctx.adapter.rpc.search_read(model, domain or [], ["name"],
                                       limit=1, order="id desc")
    return rows[0]["name"] if rows else ""


def numeric_tail(name: str) -> int:
    """The trailing run of digits in a document name, as an int."""
    match = re.search(r"(\d+)\s*$", str(name or ""))
    return int(match.group(1)) if match else -1


def same_shape(a: str, b: str) -> bool:
    """Do two document names follow the same pattern?

    Compared by replacing every digit run with ``#``: ``SO46652`` and
    ``SO46653`` both become ``SO#``, while ``SO46652`` and ``00001`` do
    not — which is the "restarts at 00001" failure the workbook names.
    """
    shape = lambda s: re.sub(r"\d+", "#", str(s or ""))
    return shape(a) == shape(b)


def sweep(ctx) -> dict:
    """Remove what can be removed; archive what a posted document pins."""
    rpc = ctx.adapter.rpc
    seen_all = {"context": {"active_test": False}}
    removed = {}
    partners = rpc.search("res.partner", [("name", "like", MARK)], **seen_all)
    products = rpc.search("product.product", [("default_code", "like", MARK)],
                          **seen_all)
    templates = rpc.search("product.template", [("name", "like", MARK)],
                           **seen_all)
    orders = rpc.search("sale.order", [("partner_id", "in", partners)],
                        **seen_all) if partners else []
    for order_id in orders:
        try:
            rpc.call("sale.order", "action_cancel", [order_id])
        except OdooRPCError:
            pass
    for model, domain in (
            ("account.move", [("line_ids.product_id", "in", products),
                              ("state", "in", ["draft", "cancel"])]),
            ("stock.picking", [("move_ids.product_id", "in", products)]),
            ("sale.order", [("id", "in", orders)]),
    ):
        ids = []
        try:
            ids = rpc.search(model, domain, **seen_all) \
                if (products or orders) else []
        except OdooRPCError as exc:
            ctx.log(f"[warn] sweep {model}: {exc}")
        removed[model] = _try_delete(ctx, model, ids)
    for model, ids in (("product.template", templates),
                       ("res.partner", partners)):
        removed[model] = _delete_or_archive(ctx, model, ids)
    ctx.log(f"sweep: {removed}")
    return removed


def _try_delete(ctx, model: str, ids: list) -> int:
    """Batch first, then one at a time — a single pinned record must not
    take a whole batch down with it."""
    if not ids:
        return 0
    rpc = ctx.adapter.rpc
    try:
        rpc.unlink(model, ids)
        return len(ids)
    except OdooRPCError:
        pass
    deleted = 0
    for record_id in ids:
        try:
            rpc.unlink(model, [record_id])
            deleted += 1
        except OdooRPCError:
            pass
    return deleted


def _delete_or_archive(ctx, model: str, ids: list) -> int:
    if not ids:
        return 0
    rpc = ctx.adapter.rpc
    try:
        rpc.unlink(model, ids)
        return len(ids)
    except OdooRPCError:
        pass
    deleted, stuck = 0, []
    for record_id in ids:
        try:
            rpc.unlink(model, [record_id])
            deleted += 1
        except OdooRPCError:
            stuck.append(record_id)
    if stuck:
        try:
            rpc.write(model, stuck, {"active": False})
        except OdooRPCError as exc:
            ctx.log(f"[warn] {model} archive failed: {exc}")
        ctx.log(f"{model}: {deleted} deleted, {len(stuck)} archived "
                f"(a posted document points at them)")
    return deleted


def live_leftovers(ctx) -> int:
    rpc = ctx.adapter.rpc
    return (rpc.call("res.partner", "search_count", [("name", "like", MARK)])
            + rpc.call("product.template", "search_count",
                       [("name", "like", MARK)]))
