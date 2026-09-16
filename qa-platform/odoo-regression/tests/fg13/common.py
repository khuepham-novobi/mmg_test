"""FG-13 — Background Job Platform (Queue Jobs). Shared gates and helpers.

Source of truth is the CLIENT MANUAL TESTING GUIDELINE
``MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0.xlsx``, sheet
``Testing Guideline`` — the copy pulled from the client's Google Drive on
2026-09-16, which is now the canonical one in ``mmg/document``. Cases
TC-JOB-002, -003, -004, -006, -015 and -016.

Why this suite is mostly read-only, and why that is the correct design
---------------------------------------------------------------------
Two facts about the target database decide the shape of every test here.

1. **``queue.job.create`` is ``@api.private``** (``queue_job/models/
   queue_job.py:269``), so no RPC client — this platform included — can
   craft a job of its own. Confirmed against the target: the call returns
   ``AccessError: Private methods (such as 'queue.job.create') cannot be
   called remotely``. ``security/ir.model.access.csv`` agrees — the manager
   group is granted ``perm_read,perm_write`` and explicitly NOT
   ``perm_create``/``perm_unlink``. Jobs are created by ``with_delay()``
   inside a server transaction and by nothing else, by design.

2. **The job runner is live on this instance.** ``odoo19.conf`` carries
   ``server_wide_modules = base,web,queue_job`` and the container log shows
   ``queue job runner ready for db mmg``. A job moved back to ``pending``
   is therefore picked up and **actually executed** within seconds.

Put together: the only jobs on this database are the client's own rows
(3,148 at the time of writing, 1,727 of them ``failed``), and pressing
*Requeue Job* on one of them would re-run real connector work — a Shopify
push, an order import — against the client's acceptance database. TC-JOB-002
step 10 and TC-JOB-003 step 5 ask for exactly that.

So this suite draws a hard line:

* every **guard** is exercised for real, because a guard that holds is a
  no-op and a guard that has broken is the defect the case exists to find
  (see :func:`no_op_probe`);
* every **surface** — states, buttons and their gating expressions, search
  filters, default filters on the action, menus, groups, ACLs, job
  functions, channels, chatter — is asserted against the live database;
* the few steps that need a real state transition on a real job are
  reported through :func:`manual`, naming what a human must still do and
  why the platform refuses to do it.

A test that quietly dropped those steps would be worse than useless, so
each is printed into the run log of the case that owns it and repeated in
that case's description.
"""
from __future__ import annotations

import re

from adapters.base import OdooRPCError

# --------------------------------------------------------------- identity
FEATURE = "FG-13 Background Job Platform"
WORKFLOW = "FG-13"
WORKFLOW_NAME = "Background Job Platform"
MODULE = "queue_job"
MODULE_ENHANCEMENT = "queue_job_enhancement"

WORKBOOK = "MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0.xlsx"
SHEET = "Testing Guideline"


def trace(tc_ids, user_story: str = "") -> dict:
    return {
        "tc_ids": tc_ids if isinstance(tc_ids, list) else [tc_ids],
        "feature": FEATURE,
        "user_story": user_story,
        "source": f"{WORKBOOK} / {SHEET}",
    }


# ------------------------------------------------------ workbook constants
JOB = "queue.job"
JOB_FUNCTION = "queue.job.function"
JOB_CHANNEL = "queue.job.channel"

MANAGER_GROUP = "queue_job.group_queue_job_manager"

#: ``queue.job.state`` — ``queue_job/job.py``. TC-JOB-004 step 12 asks the
#: tester to write these down "for the FG-14 log cases", and FG-14's
#: ``omni.log.status`` gained ``cancelled`` in the port for exactly that
#: reason (``omni_log/models/omni_log.py:67-78``).
JOB_STATES = ("wait_dependencies", "pending", "enqueued", "started", "done",
              "failed", "cancelled")

#: The header buttons and the state expression each is gated on
#: (``queue_job/views/queue_job_views.xml:7-32``). TC-JOB-002 step 9 and
#: TC-JOB-004 steps 3 and 11 are assertions about exactly these three.
HEADER_BUTTONS = {
    "requeue": "state != 'failed'",
    "button_done":
        "state not in ('wait_dependencies', 'pending', 'enqueued', 'failed')",
    "button_cancelled":
        "state not in ('wait_dependencies', 'pending', 'enqueued', 'failed')",
}

#: States from which each Python method will act. TC-JOB-004's expectation
#: that neither button works on a ``started`` job is a property of these
#: tuples, not of the view (``queue_job/models/queue_job.py:333-355``).
ACTS_FROM = {
    "requeue": ("failed", "done", "cancelled"),
    "button_done": ("wait_dependencies", "pending", "enqueued", "failed"),
    "button_cancelled": ("wait_dependencies", "pending", "enqueued", "failed"),
}

#: ``action_queue_job`` context (``views/queue_job_views.xml:321-330``).
#: TC-JOB-002 step 2 asks which filters are already applied; its Expected
#: Result says the pre-applied set hides done and cancelled jobs — "note
#: this, it is expected, not a defect".
DEFAULT_FILTERS = ("wait_dependencies", "pending", "enqueued", "started",
                   "failed")
HIDDEN_BY_DEFAULT = ("done", "cancelled")

#: The three Actions-menu wizards (``queue_job/wizards/``), each bound to
#: ``queue.job`` through ``binding_model_id``. TC-JOB-003 step 4.
BULK_ACTIONS = {
    "queue_job.action_requeue_job": "queue.requeue.job",
    "queue_job.action_set_jobs_done": "queue.jobs.to.done",
    "queue_job.action_set_jobs_cancelled": "queue.jobs.to.cancelled",
}

MENUS = ("queue_job.menu_queue_job_root", "queue_job.menu_queue",
         "queue_job.menu_queue_job", "queue_job.menu_queue_job_channel",
         "queue_job.menu_queue_job_function")

V19_ONLY = ("FG-13 describes the Odoo 19 Job Queue screens. The v15 "
            "database carried the connector's own bundled job code, not "
            "the OCA queue_job app these cases navigate")


# ------------------------------------------------------------------- gates
def require_v19(ctx):
    if ctx.env.version != "19":
        ctx.blocked(f"{V19_ONLY} (current target: {ctx.env.name}).")


def has_group(ctx, xmlid: str) -> bool:
    """``res.users.has_group`` for the acting user, over RPC.

    ``has_group(self, group_ext_id)`` takes the group as its first argument
    AFTER the recordset, so the ids have to be passed explicitly — calling
    it with the xmlid alone makes the xmlid the recordset and raises.
    """
    rpc = ctx.adapter.rpc
    try:
        return bool(rpc.call("res.users", "has_group", [rpc.uid], xmlid))
    except OdooRPCError:
        return False


def require_queue_job(ctx):
    """The queue_job app must be installed, or nothing here has a screen."""
    require_v19(ctx)
    rpc = ctx.adapter.rpc
    for model in (JOB, JOB_FUNCTION, JOB_CHANNEL):
        if not rpc.model_exists(model):
            ctx.blocked(
                f"model '{model}' does not exist on this database — the "
                f"'{MODULE}' module is not installed, which is itself the "
                f"finding TC-JOB-002's precondition tells the tester to "
                f"check before reporting anything else.")
    return rpc


# ---------------------------------------------------------------- evidence
def manual(ctx, text: str):
    """A workbook step the platform deliberately will not perform.

    Printed, never dropped. Every call names the step and the reason, so a
    reader of the run log can see precisely what is still owed by hand.
    """
    ctx.log(f"RESIDUAL MANUAL STEP — {text}")


def observation(ctx, text: str):
    ctx.log(f"OBSERVATION — {text}")


def finding(ctx, text: str):
    ctx.log(f"FINDING — {text}")


# ------------------------------------------------------------ view arches
def ref(rpc, xmlid: str):
    """Resolve an XML id without ir.model.data's private helpers."""
    module, _, name = xmlid.partition(".")
    rows = rpc.search_read("ir.model.data",
                           [("module", "=", module), ("name", "=", name)],
                           ["res_id", "model"], limit=1)
    return rows[0] if rows else None


def raw_arch(ctx, xmlid: str) -> str:
    """The view's own stored source, before ``get_view`` post-processes it.

    This matters for one thing in particular: ``groups=`` on a button or a
    field is CONSUMED during view assembly. Odoo drops the element entirely
    for a user who lacks the group and strips the attribute for one who has
    it, so an assembled arch never carries it and an assertion written
    against :func:`view_arch` would always fail. ``arch_db`` is where the
    restriction is still readable.
    """
    rpc = ctx.adapter.rpc
    row = ref(rpc, xmlid)
    if not row:
        ctx.blocked(f"view '{xmlid}' does not exist on this database.")
    return rpc.read("ir.ui.view", [row["res_id"]], ["arch_db"])[0]["arch_db"]


def view_arch(ctx, model: str, xmlid: str, view_type: str) -> str:
    """The assembled arch of one view — every ``inherit_id`` applied.

    ``get_view`` is what the browser itself is handed, so an assertion
    against it is an assertion about what the tester sees, not about one
    module's source file read in isolation.
    """
    rpc = ctx.adapter.rpc
    row = ref(rpc, xmlid)
    if not row:
        ctx.blocked(f"view '{xmlid}' does not exist on this database.")
    return rpc.call(model, "get_view", view_id=row["res_id"],
                    view_type=view_type)["arch"]


def _tag_attrs(arch: str, tag: str, name: str) -> str:
    """The raw opening tag for one named element of an arch.

    Scoped to the element's own tag on purpose: ``'name="requeue"' in arch
    and "state != 'failed'" in arch`` passes whenever both strings appear
    anywhere, which in a view this size they always do — including after the
    attribute has been deleted from the button. ``[^>]`` stops at the
    element's own closing bracket and matches newlines, so a tag whose
    attributes span several lines is still matched as one unit.
    """
    match = re.search(rf'<{tag}[^>]*name="{re.escape(name)}"[^>]*>', arch)
    return match.group(0) if match else ""


def button_attrs(arch: str, name: str) -> str:
    return _tag_attrs(arch, "button", name)


def field_attrs(arch: str, name: str) -> str:
    return _tag_attrs(arch, "field", name)


def filter_attrs(arch: str, name: str) -> str:
    return _tag_attrs(arch, "filter", name)


def attr(tag: str, name: str) -> str:
    """One attribute's value out of a raw opening tag, or ``''``."""
    match = re.search(rf'{re.escape(name)}="([^"]*)"', tag)
    return match.group(1) if match else ""


def normalise(expression: str) -> str:
    """Collapse whitespace so an expression compares by content, not layout.

    ``get_view`` re-serialises the arch, and a reformatted but identical
    attribute must not read as a regression.
    """
    return " ".join(expression.split())


# ---------------------------------------------------------------- probing
def no_op_probe(ctx, method: str, job_id: int):
    """Call a state-changing button on a job it must refuse to act on.

    This is the one place the suite touches a real job, and it is safe by
    construction: ``button_done`` and ``button_cancelled`` both open with
    ``self.filtered(lambda job_: job_.state in states_from)``
    (``queue_job/models/queue_job.py:333-348``), and ``done`` is in neither
    tuple, so the call resolves to an empty recordset and writes nothing.

    That is precisely what makes the probe worth running. If the filter has
    been lost in the port, the call transitions a job that had already
    succeeded — the failure TC-JOB-003's Expected Result line 4 names in as
    many words: *"it must not silently re-run a job that already
    succeeded"*. The probe reads the state back afterwards and reports the
    difference either way.

    ``requeue`` is deliberately NOT probed this way: its ``states_from``
    legitimately includes ``done``, so the call would succeed, and with the
    job runner live the job would re-execute. See the module docstring.
    """
    rpc = ctx.adapter.rpc
    before = rpc.read(JOB, [job_id], ["state", "date_done", "uuid"])[0]
    error = ""
    try:
        rpc.call(JOB, method, [job_id])
    except OdooRPCError as exc:
        error = str(exc)
    after = rpc.read(JOB, [job_id], ["state", "date_done"])[0]
    return {
        "uuid": before["uuid"],
        "before": before["state"],
        "after": after["state"],
        "changed": before["state"] != after["state"],
        "error": error,
    }


#: The fields the job form shows, in the order TC-JOB-002 step 6 reads them.
FORM_FIELDS = ["uuid", "name", "state", "func_string", "model_name",
               "method_name", "job_function_id", "channel", "date_created",
               "date_started", "date_done", "retry", "max_retries",
               "exc_name", "exc_message", "exc_info", "result", "priority",
               "eta", "graph_uuid", "identity_key", "worker_pid"]


def one_job_in_state(ctx, state: str, extra=None) -> dict | None:
    """One existing job in ``state``, read with the fields the form shows.

    The workbook's preconditions say to ask Novobi for a failed job rather
    than break something to create one; on this database 1,727 already
    exist. Nothing here is created and nothing is written.
    """
    rpc = ctx.adapter.rpc
    domain = [("state", "=", state)] + list(extra or [])
    rows = rpc.search_read(JOB, domain, FORM_FIELDS,
                           limit=1, order="date_created desc")
    return rows[0] if rows else None


def state_counts(ctx) -> dict:
    """How many jobs sit in each state, straight from ``read_group``."""
    rpc = ctx.adapter.rpc
    rows = rpc.read_group(JOB, [], ["state"], ["state"])
    out = {}
    for row in rows:
        # v19 read_group returns the raw value for a plain selection groupby
        # and a (value, label) pair for some; accept either.
        value = row.get("state")
        if isinstance(value, (list, tuple)):
            value = value[0]
        out[value] = row.get("state_count") or row.get("__count") or 0
    return out
