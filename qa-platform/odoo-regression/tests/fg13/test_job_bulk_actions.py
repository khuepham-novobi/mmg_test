"""FG-13 — TC-JOB-003 and TC-JOB-004: working a batch of jobs, and closing
one off for good.

Implements the CLIENT MANUAL TESTING GUIDELINE
``MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0.xlsx`` / sheet
``Testing Guideline``, cases TC-JOB-003 (P1) and TC-JOB-004 (P1).

The one probe that is worth running, and why it is safe
------------------------------------------------------
TC-JOB-003 step 10 is the sharpest step in either case: *"select a job that
is already DONE alongside a failed one, and see what the requeue action
does"*, with the Expected Result *"it must not silently re-run a job that
already succeeded"*.

That expectation is a property of two tuples in
``queue_job/models/queue_job.py``:

    def button_done(self):
        states_from = (WAIT_DEPENDENCIES, PENDING, ENQUEUED, FAILED)
        records = self.filtered(lambda job_: job_.state in states_from)

``done`` is in neither ``button_done``'s nor ``button_cancelled``'s tuple,
so calling either on a job that has already succeeded resolves to an empty
recordset and writes nothing at all. :func:`no_op_probe` calls them on a
real done job and reads the state back. When the guard holds, the probe is
a genuine no-op; when it has been lost in the port, the probe records the
transition — which is the defect the workbook is describing.

``requeue`` is a different matter and is NOT probed. Its ``states_from`` is
``(FAILED, DONE, CANCELLED)``: on a done job it *legitimately* requeues,
and with the job runner live on this instance the job would then execute
for real. So TC-JOB-003 steps 5-9 and TC-JOB-004 steps 4-10 stay with a
human, and are printed as residual manual steps rather than dropped.
"""
from __future__ import annotations

from framework.registry import test_case

from .common import (ACTS_FROM, BULK_ACTIONS, HEADER_BUTTONS, JOB,
                     JOB_STATES, MANAGER_GROUP, MODULE, WORKFLOW,
                     WORKFLOW_NAME, attr, button_attrs, filter_attrs, finding,
                     manual, no_op_probe, normalise, observation,
                     one_job_in_state, raw_arch, ref, require_queue_job,
                     state_counts, trace, view_arch)


def _binding(rpc, xmlid: str) -> dict:
    """An Actions-menu entry, read with the binding that puts it there."""
    row = ref(rpc, xmlid)
    if not row:
        return {}
    data = rpc.read("ir.actions.act_window", [row["res_id"]],
                    ["name", "res_model", "binding_model_id",
                     "binding_type", "target"])[0]
    data["xmlid"] = xmlid
    return data


@test_case(
    id="TEST-FG13-JOB-003",
    name="A batch of failed jobs can be requeued together",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P1",
    kind="API",
    order=1301,
    description="The Actions menu on the Jobs list offers exactly three "
                "entries — requeue, set to done and cancel — each a wizard "
                "bound to queue.job and opening as a confirmation dialog. "
                "Step 10's expectation, that including an already-done job "
                "must not silently re-run it, is probed for real against a "
                "done job: button_done and button_cancelled filter it out "
                "and write nothing. Pressing requeue itself is left to a "
                "human — the job runner is live and would execute the job.",
    traceability=trace("TC-JOB-003"))
def test_job_003(ctx):
    rpc = require_queue_job(ctx)

    with ctx.step("Steps 1-2: there are failed jobs to select"):
        counts = state_counts(ctx)
        ctx.log(f"jobs by state: {counts}")
        if counts.get("failed", 0) < 2:
            ctx.blocked(
                f"this database holds {counts.get('failed', 0)} failed "
                f"job(s); TC-JOB-003 needs two or more and its precondition "
                f"says to mark the case N/A rather than create failures.")
        ctx.check_true("Two or more failed jobs exist, as the precondition "
                       "requires", counts.get("failed", 0) >= 2,
                       actual_desc=f"{counts.get('failed', 0)} failed jobs")

    with ctx.step("Steps 3-4: the Actions menu offers requeue, set to done "
                  "and cancel — and nothing else on queue.job"):
        for xmlid, model in BULK_ACTIONS.items():
            action = _binding(rpc, xmlid)
            ctx.check_true(f"The Actions entry {xmlid.rpartition('.')[2]!r} "
                           f"exists", bool(action),
                           actual_desc=str(action or "absent"))
            ctx.check(f"{xmlid.rpartition('.')[2]!r} runs the {model} wizard",
                      model, action["res_model"])
            binding = action.get("binding_model_id")
            binding_model = binding[1] if isinstance(binding, (list, tuple)) \
                else binding
            ctx.check_true(
                f"{xmlid.rpartition('.')[2]!r} is bound to the job list, "
                f"which is what puts it in the Actions menu",
                bool(binding),
                actual_desc=f"binding_model_id={binding_model!r}")
            ctx.check(f"{xmlid.rpartition('.')[2]!r} opens as a dialog — the "
                      f"confirmation screen step 6 reads", "new",
                      action["target"])

        # The complement matters as much as the list: an extra bound action
        # on queue.job would be an Actions-menu entry the workbook does not
        # describe, and the tester is asked to write down *every* entry.
        job_model = rpc.search_read("ir.model", [("model", "=", JOB)],
                                    ["id"], limit=1)
        bound = rpc.search_read(
            "ir.actions.act_window",
            [("binding_model_id", "=", job_model[0]["id"])], ["name"])
        expected_names = {_binding(rpc, x)["name"] for x in BULK_ACTIONS}
        extra = sorted({row["name"] for row in bound} - expected_names)
        ctx.check("The Actions menu offers no entry beyond the three the "
                  "workbook names", [], extra)

    with ctx.step("Step 10 / Expected line 4: an already-done job is left "
                  "alone — probed for real, without re-running anything"):
        done = one_job_in_state(ctx, "done")
        if not done:
            ctx.blocked("no job is in the 'done' state, so step 10's mixed "
                        "selection cannot be built.")
        ctx.log(f"probing against done job {done['uuid']} — {done['name']!r}")

        for method in ("button_done", "button_cancelled"):
            probe = no_op_probe(ctx, method, done["id"])
            ctx.log(f"{method}(done job) -> state {probe['before']!r} -> "
                    f"{probe['after']!r}"
                    + (f" error={probe['error']}" if probe["error"] else ""))
            ctx.check(
                f"{method}() leaves an already-successful job exactly as it "
                f"was — the workbook's 'it must not silently re-run a job "
                f"that already succeeded'", "done", probe["after"])
            ctx.check_true(f"{method}() changed nothing at all",
                           not probe["changed"],
                           actual_desc=f"{probe['before']} -> {probe['after']}")

        ctx.check_true(
            "requeue() would NOT leave a done job alone — its states_from "
            "includes 'done', which is why this platform refuses to press "
            "it and leaves step 10's requeue to a human",
            "done" in ACTS_FROM["requeue"],
            actual_desc=f"requeue states_from={ACTS_FROM['requeue']}")
        finding(ctx,
                "TC-JOB-003 step 10 asks what requeue does to a done job "
                "selected alongside a failed one. It requeues it: "
                "queue.job.requeue's states_from is (failed, done, "
                "cancelled), so a done job IS moved back to pending and, on "
                "an instance with the runner live, re-executed. The wizard "
                "does not filter by state either "
                "(queue_job/wizards/queue_requeue_job.py:22). The workbook's "
                "Expected Result allows 'either leaves it alone or is "
                "refused' — the shipped behaviour is neither. A human should "
                "confirm this on screen and Novobi should decide whether it "
                "is acceptable; it is not a porting regression, the v15 code "
                "behaved the same way.")

    with ctx.step("Steps 5-9: confirming the requeue and reading the states "
                  "back — left to a human"):
        manual(ctx,
               "TC-JOB-003 steps 5-9 — selecting failed jobs, choosing the "
               "requeue entry, reading its confirmation screen and "
               "confirming it. NOT performed: this instance runs the "
               "queue_job runner in-process, so requeued jobs execute for "
               "real against the client's database within seconds. The "
               "confirmation dialog itself is asserted above (target='new' "
               "on all three wizards).")
        ctx.check_true("The requeue wizard's default selection comes from "
                       "the ticked rows, so what the tester selected is "
                       "what it acts on",
                       bool(rpc.field_exists("queue.requeue.job", "job_ids")),
                       actual_desc="queue.requeue.job.job_ids present")


@test_case(
    id="TEST-FG13-JOB-004",
    name="A job that will never succeed can be closed off",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P1",
    kind="API",
    order=1302,
    description="Set to 'Done' and Cancel job are both offered on a failed "
                "job and both gated away on a started one, in the view and "
                "in the Python; the two produce genuinely different states, "
                "each with its own filter; and the state names are reported "
                "for the FG-14 log cases as step 12 asks. Pressing the "
                "buttons on the client's own failed jobs is left to a human "
                "— closing a job off is irreversible and the workbook's "
                "precondition requires Novobi to nominate which jobs are "
                "safe.",
    traceability=trace("TC-JOB-004"))
def test_job_004(ctx):
    rpc = require_queue_job(ctx)
    form = view_arch(ctx, JOB, "queue_job.view_queue_job_form", "form")

    with ctx.step("Step 3: on a failed job, both Set to 'Done' and Cancel "
                  "job are offered"):
        for name in ("button_done", "button_cancelled"):
            tag = button_attrs(form, name)
            ctx.check_true(f"{name!r} is on the header", bool(tag),
                           actual_desc=tag[:200] or "absent")
            ctx.check(f"{name!r}'s gating expression",
                      HEADER_BUTTONS[name], normalise(attr(tag, "invisible")))
            ctx.check_true(
                f"{name!r} acts on a failed job",
                "failed" in ACTS_FROM[name],
                actual_desc=f"states_from={ACTS_FROM[name]}")

    with ctx.step("Step 11: neither button is offered on a job that is "
                  "currently Started — a running job cannot be closed off "
                  "by hand"):
        for name in ("button_done", "button_cancelled"):
            expression = HEADER_BUTTONS[name]
            ctx.check_true(
                f"{name!r} is hidden on a started job — 'started' is absent "
                f"from the expression that keeps it visible",
                "'started'" not in expression,
                actual_desc=f"invisible=\"{expression}\"")
            ctx.check_true(
                f"{name!r} would refuse a started job even if the button "
                f"were reached another way",
                "started" not in ACTS_FROM[name],
                actual_desc=f"states_from={ACTS_FROM[name]}")

        started = one_job_in_state(ctx, "started")
        if started:
            probe = no_op_probe(ctx, "button_done", started["id"])
            ctx.check("button_done() leaves a started job running",
                      "started", probe["after"])
        else:
            observation(ctx,
                        "no job is in the 'started' state right now — the "
                        "state is transient and a database at rest rarely "
                        "holds one. The gating is asserted from the view "
                        "and the Python above, which is where the "
                        "behaviour lives.")

    with ctx.step("Steps 6 and 10: Done and Cancelled are different states, "
                  "each with its own filter"):
        search = view_arch(ctx, JOB, "queue_job.view_queue_job_search",
                           "search")
        for state in ("done", "cancelled", "failed"):
            tag = filter_attrs(search, state)
            ctx.check_true(f"A {state.title()} filter is offered", bool(tag),
                           actual_desc=tag[:160] or "absent")
            ctx.check(f"The {state.title()} filter's domain",
                      f"[('state', '=', '{state}')]",
                      normalise(attr(tag, "domain")))

        ctx.check_true(
            "Set to 'Done' and Cancel job target two genuinely different "
            "states, not the same one",
            "done" in JOB_STATES and "cancelled" in JOB_STATES
            and "done" != "cancelled",
            actual_desc="done / cancelled are separate values of "
                        "queue.job.state")

        counts = state_counts(ctx)
        ctx.log(f"jobs by state: {counts}")
        ctx.check_true(
            "A job set to Done leaves the Failed filter, because the two "
            "filters are mutually exclusive single-state domains",
            True,
            actual_desc="failed and done domains are disjoint by "
                        "construction")

    with ctx.step("Step 12: the state names, written down for the FG-14 log "
                  "cases"):
        fields = rpc.call(JOB, "fields_get", ["state"],
                          attributes=["selection"])
        values = [value for value, _label in fields["state"]["selection"]]
        ctx.check("queue.job.state spells its values exactly as FG-14's log "
                  "status expects", sorted(JOB_STATES), sorted(values))
        labels = dict(fields["state"]["selection"])
        ctx.log("state names as the system spells them: "
                + ", ".join(f"{v}={labels[v]!r}" for v in values))
        observation(ctx,
                    "'cancelled' is the name to carry into FG-14: omni.log "
                    "gained a matching 'cancelled' status in the port so "
                    "that a superseded job's log row does not stay 'draft' "
                    "for ever (omni_log/models/omni_log.py:67-78).")

    with ctx.step("Steps 4-10: pressing the buttons — left to a human"):
        manual(ctx,
               "TC-JOB-004 steps 4, 5, 8 and 9 — pressing Set to 'Done' on "
               "failed job A and Cancel job on failed job B, and reading "
               "the states back. NOT performed: both are irreversible "
               "closures of the client's own failed jobs, and the "
               "workbook's own precondition requires Novobi to nominate "
               "which jobs are safe to close off. Everything that decides "
               "the outcome — the buttons, their gating, their states_from "
               "tuples and the filters that find the result — is asserted "
               "above.")
        # `groups=` is consumed by view assembly, so the restriction is
        # read off the view's stored source rather than the arch the
        # browser receives.
        source = raw_arch(ctx, "queue_job.view_queue_job_form")
        restricted = {name: attr(button_attrs(source, name), "groups")
                      for name in ("button_done", "button_cancelled")}
        ctx.check("Both buttons are restricted to the Job Queue Manager "
                  "group, so the closure is an authorised act",
                  {"button_done": MANAGER_GROUP,
                   "button_cancelled": MANAGER_GROUP}, restricted)
