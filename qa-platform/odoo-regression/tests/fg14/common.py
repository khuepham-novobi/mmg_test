"""FG-14 — Integration Monitoring & Logging. Shared gates and fixtures.

Source of truth is the CLIENT MANUAL TESTING GUIDELINE
``MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0.xlsx``, sheet
``Testing Guideline`` — the copy pulled from the client's Google Drive on
2026-09-16. Cases TC-LOG-001, -002, -004 and -005.

Scratch log rows, and the one thing this suite must never do
------------------------------------------------------------
``omni.log`` holds 6.8 million of the client's own rows. Marking their
entries resolved, or unresolving them, would rewrite the gallery's own
housekeeping state, and the workbook's cases all end with "the entry ends
up back where it started".

Unlike ``queue.job``, ``omni.log`` is an ordinary model — it can be created
over RPC. So every state-changing assertion in this suite runs against rows
this suite creates, marked with :data:`MARK` in ``entity_name`` and removed
in a ``finally``. The client's own 6.8 million rows are read and counted,
never written.

The one thing that must never happen here is a **successful** re-run.
``omni.log.run()`` dispatches to ``_import_product`` / ``_export_master``
and the rest (``omni_log/models/omni_log.py:287-305``), which call the live
Shopify connector. So ``multi_import`` and ``multi_export`` are called only
on selections their guards must REFUSE — an export row on the import
action, a draft row, a resolved row. Each of those raises before ``run()``
is reached (``omni_log.py:348-364``), which is exactly what TC-LOG-002
steps 10 and 12 and TC-LOG-004 step 12 ask to be checked. A guard that has
broken would let the call through; that is the defect, and the test reports
it rather than pretending it did not happen.
"""
from __future__ import annotations

import re
import time

from adapters.base import OdooRPCError

# --------------------------------------------------------------- identity
FEATURE = "FG-14 Integration Monitoring & Logging"
WORKFLOW = "FG-14"
WORKFLOW_NAME = "Integration Monitoring & Logging"
MODULE = "omni_log"

WORKBOOK = "MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0.xlsx"
SHEET = "Testing Guideline"

MARK = "FG14-AUTOMATED-PROBE"


def trace(tc_ids, user_story: str = "") -> dict:
    return {
        "tc_ids": tc_ids if isinstance(tc_ids, list) else [tc_ids],
        "feature": FEATURE,
        "user_story": user_story,
        "source": f"{WORKBOOK} / {SHEET}",
    }


# ------------------------------------------------------ workbook constants
LOG = "omni.log"
CHANNEL = "ecommerce.channel"

#: ``omni.log.status`` — ``omni_log/models/omni_log.py:75-80``. ``cancelled``
#: is NEW in the v19 port: it is the companion to ``queue_job_enhancement``'s
#: ``set_as_overridden``, which records a superseded job as ``cancelled``
#: rather than ``done``. TC-LOG-001's closing note is about this value.
LOG_STATUSES = ("draft", "done", "failed", "cancelled")
STATUS_LABELS = {"draft": "Draft", "done": "Success", "failed": "Failed",
                 "cancelled": "Cancelled"}

#: ``omni.log.operation_type`` split the way the guards split it
#: (``omni_log.py:348-364``). ``multi_import`` refuses anything in
#: EXPORT_GUARDED; ``multi_export`` refuses anything in IMPORT_GUARDED.
IMPORT_OPERATIONS = ("import_product", "import_order", "import_shipment",
                     "import_others")
EXPORT_OPERATIONS = ("export_master", "export_mapping", "export_order",
                     "export_inventory", "export_others")
IMPORT_GUARDED = ("import_product", "import_order", "import_shipment")
EXPORT_GUARDED = ("export_master", "export_mapping", "export_inventory")

#: The four Actions-menu server actions, each bound to the log list
#: (``omni_log/views/base_omni_log_views.xml:35-73``). TC-LOG-004 step 3
#: asks the tester to write down every entry the menu offers.
BULK_ACTIONS = {
    "omni_log.re_import_action": ("Re-Import", "multi_import"),
    "omni_log.re_export_action": ("Re-Export", "multi_export"),
    "omni_log.mark_as_resolved_action": ("Mark as Resolved", "multi_resolved"),
    "omni_log.unresolved_action": ("Unresolve", "multi_unresolved"),
}

#: The refusal messages the guards raise, verbatim (``omni_log.py:348-376``).
#: The workbook asks for "a readable message", and the only way to show a
#: message is readable is to quote the one the server actually produced.
MSG_NOT_FROM_EXPORT = "You cannot re-import any entry from export log view"
MSG_NOT_FROM_IMPORT = "You cannot re-export any entry from import log view"
MSG_ONLY_UNRESOLVED_FAILED = ("This action only applies for failed logs "
                              "which have not been resolved")
MSG_ONLY_RESOLVED_FAILED = ("This action only applies for failed logs "
                            "which have been resolved")

#: The filters the log search view offers
#: (``base_omni_log_views.xml:11-28``).
SEARCH_FILTERS = {
    "logs_today": None,
    "draft": "[('status','=','draft')]",
    "done": "[('status','=','done')]",
    "failed": "[('status','=','failed')]",
    "resolved": "[('is_resolved','=',True)]",
    "unresolved": "[('is_resolved','=',False)]",
}

#: Columns TC-LOG-001 step 4 reads off an import log list, and the two
#: labels step 14 says an export log must use instead.
IMPORT_LIST_COLUMNS = ("create_uid", "channel_record_id", "create_date",
                       "write_date", "status", "message_display")
LABEL_IMPORTED_BY = "Imported by"
LABEL_EXPORTED_BY = "Exported by"

#: The per-store actions the three-dot menu on the store card offers.
STORE_LOG_ACTIONS = ("open_log_import_product", "open_log_import_order",
                     "open_log_import_shipment", "open_log_import_other_data",
                     "open_log_export_product", "open_log_export_inventory",
                     "open_log_export_other_data")

V19_ONLY = ("FG-14 describes the Odoo 19 log screens, including the "
            "'cancelled' status the port added to omni.log")


# ------------------------------------------------------------------- gates
def require_v19(ctx):
    if ctx.env.version != "19":
        ctx.blocked(f"{V19_ONLY} (current target: {ctx.env.name}).")


def require_logs(ctx):
    require_v19(ctx)
    rpc = ctx.adapter.rpc
    if not rpc.model_exists(LOG):
        ctx.blocked(
            f"model '{LOG}' does not exist on this database — the "
            f"'{MODULE}' module is not installed, so none of FG-14's "
            f"screens exist.")
    return rpc


def acting_channel(ctx) -> dict:
    """The store whose logs the workbook's steps open.

    Read, never written. FG-14 touches the store only to reach its log
    screens.
    """
    rpc = ctx.adapter.rpc
    rows = rpc.search_read(CHANNEL, [], ["name", "platform", "active"],
                           limit=2, order="id")
    if not rows:
        ctx.blocked("no ecommerce.channel exists on this database, so there "
                    "is no store card to open a log screen from.")
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


def view_arch(ctx, xmlid: str, view_type: str) -> str:
    rpc = ctx.adapter.rpc
    row = ref(rpc, xmlid)
    if not row:
        ctx.blocked(f"view '{xmlid}' does not exist on this database.")
    return rpc.call(LOG, "get_view", view_id=row["res_id"],
                    view_type=view_type)["arch"]


def _tag_attrs(arch: str, tag: str, name: str, occurrence: int = 0) -> str:
    """The raw opening tag for the ``occurrence``-th element of that name.

    The log form carries ``toggle_resolved`` TWICE — once as *Mark as
    Resolved* and once as *Unresolve*, gated on opposite expressions
    (``base_omni_log_views.xml:111-118``). A helper that returned only the
    first would make the second untestable and the first misleading, so the
    occurrence is explicit.
    """
    matches = re.findall(rf'<{tag}[^>]*name="{re.escape(name)}"[^>]*>', arch)
    return matches[occurrence] if len(matches) > occurrence else ""


def button_attrs(arch: str, name: str, occurrence: int = 0) -> str:
    return _tag_attrs(arch, "button", name, occurrence)


def field_attrs(arch: str, name: str, occurrence: int = 0) -> str:
    return _tag_attrs(arch, "field", name, occurrence)


def filter_attrs(arch: str, name: str, occurrence: int = 0) -> str:
    return _tag_attrs(arch, "filter", name, occurrence)


def attr(tag: str, name: str) -> str:
    match = re.search(rf'{re.escape(name)}="([^"]*)"', tag)
    return match.group(1) if match else ""


def normalise(expression: str) -> str:
    return " ".join(expression.split())


# ------------------------------------------------------------- scratch rows
def make_log(ctx, channel_id: int, *, status: str, operation_type: str,
             label: str, resolved: bool | None = None) -> int:
    """One scratch ``omni.log`` row, marked so the sweep can find it.

    ``status='done'`` is forced resolved by ``consider_done_as_resolved``
    (``omni_log.py:389-405``) whatever is passed, which is the model's own
    rule and is left alone here — a fixture that fought it would be testing
    something the product does not do.
    """
    rpc = ctx.adapter.rpc
    values = {
        "channel_id": channel_id,
        "status": status,
        "operation_type": operation_type,
        "entity_name": f"{MARK} {label}",
        "channel_record_id": f"{MARK}-{label}-{int(time.time() * 1000) % 10 ** 7}",
        "message": f"{MARK} — scratch row created by the FG-14 regression "
                   f"suite; removed at the end of the run.",
        "data_operation": "by_ids",
    }
    if resolved is not None:
        values["is_resolved"] = resolved
    log_id = rpc.create(LOG, values)
    ctx.log(f"scratch log #{log_id} status={status} op={operation_type} "
            f"label={label}")
    return log_id


def read_logs(ctx, ids) -> list[dict]:
    if not ids:
        return []
    return ctx.adapter.rpc.read(
        LOG, list(ids),
        ["status", "is_resolved", "operation_type", "entity_name",
         "channel_record_id", "message"])


def sweep(ctx) -> int:
    """Remove every row this suite has ever created on this database.

    Scoped by the marker in ``entity_name``, so it can never reach one of
    the client's 6.8 million rows. Called from a ``finally`` in each case,
    and it also clears anything an earlier interrupted run left behind.
    """
    rpc = ctx.adapter.rpc
    try:
        ids = rpc.search(LOG, [("entity_name", "like", MARK)])
    except OdooRPCError as exc:
        ctx.log(f"[warn] sweep could not search: {exc}")
        return 0
    if not ids:
        return 0
    try:
        rpc.unlink(LOG, ids)
    except OdooRPCError as exc:
        ctx.log(f"[warn] sweep could not remove {len(ids)} row(s): {exc}")
        return 0
    ctx.log(f"sweep: {len(ids)} scratch log row(s) removed")
    return len(ids)


def refuse(ctx, method: str, ids) -> dict:
    """Call one of the bulk actions and capture whether it refused.

    Only ever called with a selection the guard must reject — see the module
    docstring. The rows are read back afterwards so that a guard which
    raised but still wrote is reported as loudly as one that did not raise
    at all.
    """
    before = {row["id"]: (row["status"], row["is_resolved"])
              for row in read_logs(ctx, ids)}
    error = ""
    try:
        ctx.adapter.rpc.call(LOG, method, list(ids))
    except OdooRPCError as exc:
        error = str(exc)
    after = {row["id"]: (row["status"], row["is_resolved"])
             for row in read_logs(ctx, ids)}
    return {"error": error, "before": before, "after": after,
            "changed": before != after}
