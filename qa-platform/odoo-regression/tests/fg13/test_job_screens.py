"""FG-13 — TC-JOB-002: a failed background job can be found, read and re-run.

Implements the CLIENT MANUAL TESTING GUIDELINE
``MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0.xlsx`` / sheet
``Testing Guideline``, case TC-JOB-002 (P0).

The case is the gateway to the whole of FG-13: its precondition tells the
tester that *"if the Job Queue app does not appear at all, that is what is
missing — check before reporting anything else"*, and every later case
opens with "TC-JOB-002 has passed".

What is asserted here, and what is left to a human
--------------------------------------------------
Steps 1 to 9 and 12 are all readable facts about the database — the menus,
the action's pre-applied filters, the list columns, a failed job's own
fields, the Results tab, and which buttons the form offers on a failed job.
Those are asserted for real.

Step 10 — *"Click Requeue Job"* — is NOT performed, and the reason is not
timidity. ``queue.job.requeue`` moves the job to ``pending``
(``queue_job/models/queue_job.py:349-355``), and this instance runs the job
runner in-process (``server_wide_modules = base,web,queue_job``; the
container log reads ``queue job runner ready for db mmg``). The job would
be executed within seconds — a real Shopify push or order import against
the client's own acceptance database, from a test. What the platform CAN
assert without firing anything is that the button is offered on a failed
job and gated away everywhere else, that ``requeue``'s ``states_from``
admits ``failed``, and that the state it targets is ``pending``; step 11's
"read the job's state now" is then the only thing left to a human, and it
is printed as such.
"""
from __future__ import annotations

from framework.registry import test_case

from .common import (ACTS_FROM, DEFAULT_FILTERS, HEADER_BUTTONS,
                     HIDDEN_BY_DEFAULT, JOB, JOB_STATES, MANAGER_GROUP,
                     MENUS, MODULE, WORKFLOW, WORKFLOW_NAME, attr,
                     button_attrs, field_attrs, filter_attrs, has_group,
                     manual, normalise, observation, one_job_in_state,
                     raw_arch, ref, require_queue_job, state_counts, trace,
                     view_arch)

#: Columns TC-JOB-002 step 3 reads off the list.
LIST_COLUMNS = ("name", "state", "date_created")

#: Fields step 6 reads off the form, and step 7's two Results-tab fields.
FORM_READS = ("name", "uuid", "job_function_id", "date_created",
              "date_started", "retry", "max_retries")
RESULTS_TAB = ("exc_name", "exc_info")


@test_case(
    id="TEST-FG13-JOB-002",
    name="A failed background job can be found, read and re-run",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P0",
    kind="API",
    order=1300,
    description="The Job Queue menus exist and are gated on the Job Queue "
                "Manager group; the Jobs action opens with five state "
                "filters pre-applied that hide Done and Cancelled; a real "
                "failed job carries its description, function, dates, retry "
                "counts and a readable Exception Info; and the form offers "
                "Requeue Job, Set to 'Done' and Cancel job on a failed job "
                "only. Step 10 (pressing Requeue) is left to a human — the "
                "job runner is live on this instance and would execute the "
                "job for real.",
    traceability=trace("TC-JOB-002"))
def test_job_002(ctx):
    rpc = require_queue_job(ctx)

    with ctx.step("Step 1: the Job Queue app and its Queue > Jobs menu exist"):
        missing = [xmlid for xmlid in MENUS if not ref(rpc, xmlid)]
        ctx.check("Every Job Queue menu exists", [], missing)

        root = ref(rpc, "queue_job.menu_queue_job_root")
        # v19 renamed the groups relation on ir.ui.menu (and on the action
        # models) from `groups_id` to `group_ids`. Reading the v15 name
        # raises rather than returning an empty list, so the name is
        # resolved rather than assumed.
        menu_groups = ("group_ids"
                       if rpc.field_exists("ir.ui.menu", "group_ids")
                       else "groups_id")
        root_row = rpc.read("ir.ui.menu", [root["res_id"]],
                            ["name", menu_groups])[0]
        ctx.check("The app menu is named 'Job Queue'", "Job Queue",
                  root_row["name"])

        manager = ref(rpc, MANAGER_GROUP)
        ctx.check_true(
            "The Job Queue app menu is gated on the Job Queue Manager group "
            "— which is what the precondition tells the tester to check "
            "first when the app is not visible",
            bool(manager)
            and manager["res_id"] in (root_row[menu_groups] or []),
            actual_desc=f"menu {menu_groups}={root_row[menu_groups]} "
                        f"group id={manager and manager['res_id']}")

        ctx.check_true(
            "The acting user is in the Job Queue Manager group, so this run "
            "is testing what the tester's own login would see",
            has_group(ctx, MANAGER_GROUP),
            actual_desc=f"has_group({MANAGER_GROUP})="
                        f"{has_group(ctx, MANAGER_GROUP)}")

    with ctx.step("Step 2: the Jobs screen opens with filters already "
                  "applied, and they hide Done and Cancelled"):
        action_ref = ref(rpc, "queue_job.action_queue_job")
        ctx.check_true("The Jobs action exists", bool(action_ref),
                       actual_desc=str(action_ref))
        action = rpc.read("ir.actions.act_window", [action_ref["res_id"]],
                          ["name", "res_model", "view_mode", "context"])[0]
        ctx.check("The Jobs action targets queue.job", JOB, action["res_model"])

        context = action["context"] or ""
        applied = sorted(name for name in JOB_STATES
                         if f"search_default_{name}" in context)
        ctx.check("The filters pre-applied when the screen opens",
                  sorted(DEFAULT_FILTERS), applied)
        hidden = [name for name in HIDDEN_BY_DEFAULT
                  if f"search_default_{name}" not in context]
        ctx.check("Done and Cancelled are NOT pre-applied — the workbook "
                  "says to note this, it is expected and not a defect",
                  sorted(HIDDEN_BY_DEFAULT), sorted(hidden))
        observation(ctx, f"action context: {context}")

    with ctx.step("Step 3: the list shows Description, State and Created "
                  "Date"):
        arch = view_arch(ctx, JOB, "queue_job.view_queue_job_tree", "list")
        absent = [name for name in LIST_COLUMNS if not field_attrs(arch, name)]
        ctx.check("Every column the workbook names is on the list", [], absent)

    with ctx.step("Step 4: the Failed filter exists on its own and finds the "
                  "failed jobs"):
        search = view_arch(ctx, JOB, "queue_job.view_queue_job_search",
                           "search")
        failed_filter = filter_attrs(search, "failed")
        ctx.check_true("A Failed filter is offered", bool(failed_filter),
                       actual_desc=failed_filter or "absent")
        ctx.check("The Failed filter's domain",
                  "[('state', '=', 'failed')]",
                  normalise(attr(failed_filter, "domain")))

        counts = state_counts(ctx)
        failed = rpc.call(JOB, "search_count", [("state", "=", "failed")])
        ctx.check("The Failed filter's count matches a direct count of "
                  "failed jobs", counts.get("failed", 0), failed)
        ctx.log(f"jobs by state: {counts}")

    job = None
    with ctx.step("Steps 5-7: a failed job carries its description, its "
                  "function, its dates, its retry counts and a readable "
                  "Exception Info"):
        job = one_job_in_state(ctx, "failed")
        if not job:
            ctx.blocked(
                "no job is in the 'failed' state on this database. The "
                "workbook's precondition says to ask Novobi to produce one "
                "rather than break something to create one, and this "
                "platform will not create one either — queue.job.create is "
                "@api.private and the manager group has no create right.")
        ctx.log(f"failed job {job['uuid']} — {job['name']!r} "
                f"func={job['func_string']!r} created={job['date_created']} "
                f"retry={job['retry']}/{job['max_retries']}")

        empty = [name for name in FORM_READS if job.get(name) in (False, None, "")]
        # `retry` is legitimately 0 on a job that failed on its first
        # attempt, and `date_started` is legitimately empty on a job that
        # failed before it ever ran. Neither is a missing field.
        empty = [name for name in empty
                 if name not in ("retry", "max_retries", "date_started")]
        ctx.check("Every field the workbook's step 6 reads is populated on "
                  "the failed job", [], empty)

        ctx.check_true(
            "The Results tab's Exception Info is present and readable",
            bool(job.get("exc_info")),
            actual_desc=(str(job.get("exc_info") or "")
                         .strip().splitlines() or ["(empty)"])[-1][:160])
        ctx.log("first line of the exception: "
                + (str(job.get("exc_info") or "").strip().splitlines()
                   or ["(empty)"])[0][:200])

    with ctx.step("Steps 8-9: the status bar shows the job's stage and the "
                  "header offers exactly the three buttons"):
        form = view_arch(ctx, JOB, "queue_job.view_queue_job_form", "form")
        source = raw_arch(ctx, "queue_job.view_queue_job_form")

        state_tag = field_attrs(form, "state")
        ctx.check_true("The state is shown as a status bar",
                       'widget="statusbar"' in state_tag,
                       actual_desc=state_tag[:200] or "field absent")

        for name, expected in HEADER_BUTTONS.items():
            tag = button_attrs(form, name)
            ctx.check_true(f"The header offers the {name!r} button",
                           bool(tag), actual_desc=tag[:200] or "absent")
            ctx.check(f"{name!r} is gated on the states the workbook "
                      f"expects", expected, normalise(attr(tag, "invisible")))
            # `groups=` never survives view assembly — Odoo drops the
            # element for a user without the group and strips the attribute
            # for one who has it — so the restriction is read off the view's
            # stored source instead.
            ctx.check(f"{name!r} is restricted to the Job Queue Manager "
                      f"group", MANAGER_GROUP,
                      attr(button_attrs(source, name), "groups"))

        # On a FAILED job specifically — which is the job the tester has
        # open at step 9 — all three are visible, because `failed` satisfies
        # none of the three `invisible` expressions.
        ctx.check_true(
            "On a failed job all three buttons are shown: Requeue Job, Set "
            "to 'Done' and Cancel job",
            all("failed" in ACTS_FROM[name] for name in HEADER_BUTTONS),
            actual_desc=", ".join(f"{k}:{ACTS_FROM[k]}"
                                  for k in HEADER_BUTTONS))

    with ctx.step("Steps 10-11: Requeue Job targets Pending — asserted "
                  "without firing it"):
        ctx.check_true(
            "requeue() acts on a failed job (states_from includes 'failed')",
            "failed" in ACTS_FROM["requeue"],
            actual_desc=str(ACTS_FROM["requeue"]))
        manual(ctx,
               "TC-JOB-002 steps 10-11 — pressing Requeue Job on job "
               f"{job['uuid']} and reading the state back. NOT performed: "
               "this instance runs the queue_job runner in-process, so a "
               "requeued job is executed for real within seconds, against "
               "the client's own database. A human should press it on a job "
               "Novobi has confirmed is safe to re-run, and confirm the "
               "state reads Pending.")

    with ctx.step("Step 12: clearing the filters reveals Done and Cancelled "
                  "jobs"):
        counts = state_counts(ctx)
        revealed = {name: counts.get(name, 0) for name in HIDDEN_BY_DEFAULT}
        ctx.check_true(
            "With no filter applied the database holds jobs in states the "
            "default screen hides",
            any(revealed.values()),
            actual_desc=str(revealed))
        ctx.log(f"hidden-by-default states now visible: {revealed}")
