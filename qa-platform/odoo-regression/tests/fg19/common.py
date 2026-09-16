"""FG-19 — Security & Access Control. Gates and the two probe logins.

Source of truth is the CLIENT MANUAL TESTING GUIDELINE
``MMG_v19_Client_Manual_Testing_Guideline_FG15-FG20_v1.0.xlsx``, sheet
``Testing Guideline``. Cases TC-SEC-007, TC-SEC-010 and TC-SEC-011.

Every case here is "look at the same screen as two different people"
---------------------------------------------------------------------
TC-SEC-007's Test Data says so in as many words. That is why this is the
one feature group in the workbook that automates cleanly end to end: the
answer is never "does this work" but "is this refused", and a refusal
leaves nothing behind.

The two logins the workbook asks Novobi to prepare — one *E-commerce User*,
one *E-commerce Manager*, neither with Administration rights — are created
here, used, and removed in a ``finally``. Creating them is the honest way
to run these cases: reading ``ir.model.access`` and ``groups=`` attributes
would describe the intent of the configuration, and what TC-SEC-007 is
actually about is what the screen hands over.

Asking the questions the browser asks
--------------------------------------
Two RPC habits matter here, both learned the hard way in FG-13:

* **Menus.** ``ir.ui.menu.search`` is NOT group-filtered on v19 — every
  menu comes back to every user. Visibility is decided by
  ``_filter_visible_menus`` inside ``load_menus``
  (``odoo/addons/base/models/ir_ui_menu.py:236-244``), which is what the
  web client calls. :func:`visible_menus` asks that.
* **Fields and buttons.** ``groups=`` is consumed during view assembly:
  Odoo drops the element for a user without the group and strips the
  attribute for one who has it, so an assembled arch never carries it.
  Building the arch **as each user** and comparing is therefore not a
  shortcut — it is the only way to see what each person is served.
"""
from __future__ import annotations

import dataclasses
import re
import time

from adapters.base import OdooRPC, OdooRPCError

# --------------------------------------------------------------- identity
FEATURE = "FG-19 Security & Access Control"
WORKFLOW = "FG-19"
WORKFLOW_NAME = "Security & Access Control"
MODULE = "omni_manage_channel"

WORKBOOK = "MMG_v19_Client_Manual_Testing_Guideline_FG15-FG20_v1.0.xlsx"
SHEET = "Testing Guideline"

MARK = "fg19-probe"


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

GROUP_USER = "omni_manage_channel.group_listing_user"
GROUP_MANAGER = "omni_manage_channel.group_listing_manager"

#: The storefront credential TC-SEC-007 is about. The workbook calls it
#: "a row labelled 'Access Token' near the top, just under the store name";
#: on the form that is ``shopify_access_token`` rendered with
#: ``string="Access Token"`` and ``password="1"``.
TOKEN_FIELD = "shopify_access_token"
TOKEN_LABEL = "Access Token"

#: The three menus TC-SEC-010 step 2 requires to be ABSENT for a User.
RESTRICTED_MENUS = {
    "omni_manage_channel.menu_management_channels":
        "E-commerce Connectors > Configuration > Store Configuration > "
        "Manage Stores",
    "multichannel_product.menu_omniborder_listings_root":
        "E-commerce Connectors > Products > Product Mappings",
    "multichannel_product.menu_product_channel_export_scheduler":
        "E-commerce Connectors > Configuration > Mappings > Scheduled "
        "Mappings Updates",
}

#: The storefront buttons of TC-SEC-010 step 3, by method name and the
#: wording the workbook reads off them.
COLLECTION_BUTTONS = {
    "set_to_draft": "Set to Draft",
    "publish": "Publish To Shopify",
    "do_update": "Update To Shopify",
    "get_data": "SYNC FROM SHOPIFY",
}

#: The seven scheduled actions TC-SEC-011 step 2 names, plus the one step 3
#: says is switched off on purpose.
SCHEDULED_ACTIONS = (
    "Omni: Clear Resolved Logs",
    "Omni: Clear API Process Logs",
    "Product Export Scheduler: Execute",
    "Channel Inventory Sync",
    "Bulk Inventory Sync",
    "AutoVacuum Job Queue",
    "Job Queue: Requeue Stuck Jobs",
)
SCHEDULED_OFF_ON_PURPOSE = "Check new orders"

#: The two TC-SEC-011 steps 4-7 edit and put straight back.
SCHEDULED_EDITABLE = ("Omni: Clear Resolved Logs", "AutoVacuum Job Queue")

V19_ONLY = ("FG-19 asks what the v19 access configuration hands to each "
            "kind of user; there is nothing to ask of v15")


# ------------------------------------------------------------------- gates
def require_v19(ctx):
    if ctx.env.version != "19":
        ctx.blocked(f"{V19_ONLY} (current target: {ctx.env.name}).")


def require_connector(ctx):
    require_v19(ctx)
    rpc = ctx.adapter.rpc
    if not rpc.model_exists(CHANNEL):
        ctx.blocked(
            f"model '{CHANNEL}' does not exist — the e-commerce connector "
            f"stack is not installed, so there are no storefront rights to "
            f"test.")
    for xmlid in (GROUP_USER, GROUP_MANAGER):
        if not ref(rpc, xmlid):
            ctx.blocked(
                f"group '{xmlid}' does not exist on this database. The "
                f"workbook's preconditions ask for one login in each, so "
                f"without them the case cannot be set up — and a missing "
                f"group is itself the finding.")
    return rpc


# ---------------------------------------------------------------- evidence
def manual(ctx, text: str):
    ctx.log(f"RESIDUAL MANUAL STEP — {text}")


def observation(ctx, text: str):
    ctx.log(f"OBSERVATION — {text}")


def finding(ctx, text: str):
    ctx.log(f"FINDING — {text}")


# ------------------------------------------------------------------ lookup
def ref(rpc, xmlid: str):
    module, _, name = xmlid.partition(".")
    rows = rpc.search_read("ir.model.data",
                           [("module", "=", module), ("name", "=", name)],
                           ["res_id", "model"], limit=1)
    return rows[0] if rows else None


def field_attrs(arch: str, name: str, occurrence: int = 0) -> str:
    matches = re.findall(rf'<field[^>]*name="{re.escape(name)}"[^>]*>', arch)
    return matches[occurrence] if len(matches) > occurrence else ""


def button_attrs(arch: str, name: str, occurrence: int = 0) -> str:
    matches = re.findall(rf'<button[^>]*name="{re.escape(name)}"[^>]*>', arch)
    return matches[occurrence] if len(matches) > occurrence else ""


def attr(tag: str, name: str) -> str:
    match = re.search(rf'{re.escape(name)}="([^"]*)"', tag)
    return match.group(1) if match else ""


# ------------------------------------------------------------ probe logins
class Probe:
    """One throw-away login, and the RPC session that belongs to it."""

    def __init__(self, ctx, label: str, group_xmlid: str):
        rpc = ctx.adapter.rpc
        self.ctx = ctx
        self.label = label
        self.login = f"{MARK}-{label}-{int(time.time() * 1000) % 10 ** 7}"
        self.password = f"Probe!{int(time.time())}"
        self.group_xmlid = group_xmlid

        # v19 renamed res.users.groups_id to group_ids. Writing the v15
        # name would create a user with NO groups at all and make every
        # refusal below pass for the wrong reason, so the name is resolved.
        self.groups_field = ("group_ids"
                             if rpc.field_exists("res.users", "group_ids")
                             else "groups_id")
        internal = ref(rpc, "base.group_user")
        wanted = ref(rpc, group_xmlid)
        self.group_id = wanted["res_id"]
        self.uid = rpc.create("res.users", {
            "name": f"FG-19 {label} probe (automated, removed after run)",
            "login": self.login,
            "password": self.password,
            self.groups_field: [(6, 0, [internal["res_id"], self.group_id])],
        })

        env = dataclasses.replace(ctx.env, username=self.login,
                                  password=self.password)
        self.rpc = OdooRPC(env)
        self.rpc.authenticate()
        ctx.log(f"probe login '{label}' uid={self.uid} in {group_xmlid}")

    # -- what this login is served ------------------------------------
    def groups(self) -> list:
        return self.ctx.adapter.rpc.read(
            "res.users", [self.uid], [self.groups_field])[0][self.groups_field]

    def visible_menus(self) -> set:
        """Menu ids this login is actually served, via ``load_menus``."""
        try:
            served = self.rpc.call("ir.ui.menu", "load_menus", False)
        except OdooRPCError as exc:
            self.ctx.log(f"[warn] {self.label}: load_menus failed: {exc}")
            return set()
        return {int(k) for k in served if str(k).isdigit()}

    def arch(self, model: str, view_type: str = "form") -> str:
        """The view as THIS login is served it.

        ``groups=`` is consumed during assembly, so a restricted field or
        button is simply absent here for a user who lacks the group. That
        is the fact the workbook's steps 4 and 3 are asking about.
        """
        try:
            return self.rpc.call(model, "get_view", view_type=view_type)["arch"]
        except OdooRPCError as exc:
            self.ctx.log(f"[warn] {self.label}: {model} {view_type} view "
                         f"refused: {exc}")
            return ""

    def can_read(self, model: str, fields: list) -> tuple:
        """``(rows, error)`` — reading as this login, refusal captured."""
        try:
            return self.rpc.search_read(model, [], fields, limit=1), ""
        except OdooRPCError as exc:
            return None, str(exc)

    def fields_get(self, model: str, names: list) -> dict:
        """Which of ``names`` this login may read at all.

        ``fields_get`` omits a field the user has no group for, which is
        the right verdict: a value that cannot be read cannot leak.
        """
        try:
            return self.rpc.call(model, "fields_get", names,
                                 attributes=["string", "type"])
        except OdooRPCError:
            return {}

    def remove(self):
        rpc = self.ctx.adapter.rpc
        try:
            rpc.unlink("res.users", [self.uid])
            return "deleted"
        except OdooRPCError as exc:
            # A user that has touched anything cannot be deleted; archiving
            # takes the login out of use just as completely.
            self.ctx.log(f"[warn] delete refused ({exc}); archiving")
            try:
                rpc.write("res.users", [self.uid], {"active": False})
                return "archived"
            except OdooRPCError as exc2:
                self.ctx.log(f"[warn] archive also failed: {exc2}")
                return "LEFT BEHIND"


def sweep_probes(ctx) -> int:
    """Remove every probe login this suite has ever created.

    Scoped by the login prefix, so it can never reach one of the gallery's
    own users — and it clears what an interrupted earlier run left behind.
    """
    rpc = ctx.adapter.rpc
    ids = rpc.search("res.users", [("login", "like", MARK)],
                     context={"active_test": False})
    if not ids:
        return 0
    try:
        rpc.unlink("res.users", ids)
        ctx.log(f"sweep: {len(ids)} probe login(s) removed")
        return len(ids)
    except OdooRPCError as exc:
        ctx.log(f"[warn] sweep could not delete {ids}: {exc}; archiving")
        try:
            rpc.write("res.users", ids, {"active": False})
        except OdooRPCError:
            pass
        return 0


def live_probes(ctx) -> int:
    return ctx.adapter.rpc.call("res.users", "search_count",
                                [("login", "like", MARK),
                                 ("active", "=", True)])
