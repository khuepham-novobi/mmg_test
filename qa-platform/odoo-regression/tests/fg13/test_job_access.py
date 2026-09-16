"""FG-13 — TC-JOB-015 and TC-JOB-016: the job record's chatter, and who is
allowed near the job screens at all.

Implements the CLIENT MANUAL TESTING GUIDELINE
``MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0.xlsx`` / sheet
``Testing Guideline``, cases TC-JOB-015 (P2) and TC-JOB-016 (P1).

TC-JOB-016 is the one case in FG-13 that can be tested end to end, and it
is worth saying why. Everything else in this suite is blocked by the fact
that jobs cannot be created over RPC and real jobs must not be re-run.
Access control has neither problem: the second login the workbook's
precondition asks Novobi to prepare is something this platform can prepare
for itself — a throw-away user in ``base.group_user`` and nothing else —
and the assertions are all refusals, which leave nothing behind. The user
is removed in a ``finally`` whether the case passes or fails.

TC-JOB-015 does write to the client's database: a logged note and a
scheduled activity on one of their job records. Both are housekeeping
records rather than business data, both are marked, and both are removed in
a ``finally``. The case cannot be answered any other way — "does the
chatter render and does a note survive a reload" is a question about a
round trip, not about a view definition.
"""
from __future__ import annotations

import dataclasses
import time

from adapters.base import OdooRPC, OdooRPCError
from framework.registry import test_case

from .common import (JOB, MANAGER_GROUP, MODULE, WORKFLOW, WORKFLOW_NAME,
                     field_attrs, finding, has_group, manual, ref,
                     require_queue_job, trace, view_arch)

#: The note TC-JOB-015 step 3 asks for, marked so the cleanup can find
#: exactly what this run wrote and nothing else.
NOTE_MARK = "FG13-TC-JOB-015 automated check"

#: Models the workbook's step 6/7 walk. ``mail.activity.mixin`` contributes
#: ``activity_ids``; ``mail.thread`` contributes ``message_ids``.
CHATTER_FIELDS = ("message_ids", "message_follower_ids", "activity_ids")


@test_case(
    id="TEST-FG13-JOB-015",
    name="A job record can be commented on and assigned",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P2",
    kind="API",
    order=1304,
    description="queue.job inherits mail.thread and mail.activity.mixin, the "
                "form renders a chatter, a logged note saves with the "
                "author and timestamp and is still there when the record is "
                "read again, and an activity can be scheduled and marked "
                "done. The note and the activity this test writes are both "
                "removed afterwards.",
    traceability=trace("TC-JOB-015"))
def test_job_015(ctx):
    rpc = require_queue_job(ctx)
    posted_ids: list[int] = []
    activity_ids: list[int] = []
    job = None

    try:
        with ctx.step("Steps 1-2: a job form with a message and activity "
                      "area at the bottom"):
            rows = rpc.search_read(JOB, [], ["uuid", "name", "state"],
                                   limit=1, order="date_created desc")
            if not rows:
                ctx.blocked("this database holds no queue.job record at "
                            "all, so there is nothing to comment on.")
            job = rows[0]
            ctx.log(f"job {job['uuid']} — {job['name']!r} "
                    f"state={job['state']}")

            present = rpc.call(JOB, "fields_get", list(CHATTER_FIELDS),
                               attributes=["type"])
            missing = [name for name in CHATTER_FIELDS if name not in present]
            ctx.check("queue.job carries the chatter's own fields — it "
                      "inherits mail.thread and mail.activity.mixin", [],
                      missing)

            arch = view_arch(ctx, JOB, "queue_job.view_queue_job_form",
                             "form")
            ctx.check_true(
                "The form renders a chatter",
                "<chatter" in arch or bool(field_attrs(arch, "message_ids")),
                actual_desc="chatter element present" if "<chatter" in arch
                else "message_ids field present"
                if field_attrs(arch, "message_ids") else "neither")

        with ctx.step("Steps 3-4: a logged note saves with the author's name "
                      "and the time on it"):
            body = f"{NOTE_MARK} — {time.strftime('%Y-%m-%d %H:%M:%S')}"
            posted = rpc.call(JOB, "message_post", [job["id"]],
                              body=body, message_type="comment",
                              subtype_xmlid="mail.mt_note")
            # v19's message_post returns the new mail.message as an id, a
            # one-element list, or a read-style dict depending on the path
            # taken; normalise rather than assume.
            if isinstance(posted, dict):
                message_id = posted.get("id")
            elif isinstance(posted, (list, tuple)):
                message_id = posted[0] if posted else None
                if isinstance(message_id, dict):
                    message_id = message_id.get("id")
            else:
                message_id = posted
            ctx.check_true("The note was accepted", bool(message_id),
                           actual_desc=f"mail.message id={message_id} "
                                       f"(message_post returned {posted!r})")
            posted_ids.append(message_id)

            row = rpc.read("mail.message", [message_id],
                           ["body", "author_id", "date", "model", "res_id"])[0]
            ctx.check("The note is attached to this job", JOB, row["model"])
            ctx.check("…and to this job's id", job["id"], row["res_id"])
            ctx.check_true("The note carries an author",
                           bool(row["author_id"]),
                           actual_desc=str(row["author_id"]))
            ctx.check_true("…and a timestamp", bool(row["date"]),
                           actual_desc=str(row["date"]))
            ctx.check_true("…and the text that was typed",
                           NOTE_MARK in (row["body"] or ""),
                           actual_desc=(row["body"] or "")[:160])

        with ctx.step("Step 5: the note is still there when the record is "
                      "read again"):
            again = rpc.search_read(
                "mail.message",
                [("model", "=", JOB), ("res_id", "=", job["id"]),
                 ("body", "like", NOTE_MARK)], ["id", "body"])
            ctx.check_true(
                "Re-reading the record finds the note — it was committed, "
                "not held in the session",
                any(row["id"] == posted_ids[0] for row in again),
                actual_desc=f"{len(again)} matching message(s)")

        with ctx.step("Steps 6-8: an activity can be scheduled, assigned "
                      "and marked done"):
            todo = ref(rpc, "mail.mail_activity_data_todo")
            if not todo:
                ctx.skip("mail.mail_activity_data_todo is not installed on "
                         "this database, so there is no activity type to "
                         "schedule.")
            deadline = time.strftime("%Y-%m-%d")
            try:
                scheduled = rpc.call(
                    JOB, "activity_schedule", [job["id"]],
                    act_type_xmlid="mail.mail_activity_data_todo",
                    date_deadline=deadline, user_id=rpc.uid,
                    summary=NOTE_MARK)
            except OdooRPCError as exc:
                ctx.check_true(
                    "Scheduling an activity on a job record is accepted",
                    False, actual_desc=str(exc))
                raise
            ids = scheduled if isinstance(scheduled, list) else [scheduled]
            activity_ids.extend(i for i in ids if isinstance(i, int))
            ctx.check_true("The activity was created", bool(activity_ids),
                           actual_desc=str(activity_ids))

            shown = rpc.read(JOB, [job["id"]], ["activity_ids"])[0]
            ctx.check_true(
                "The scheduled activity shows on the record",
                all(i in (shown["activity_ids"] or []) for i in activity_ids),
                actual_desc=f"job activity_ids={shown['activity_ids']}")

            rpc.call("mail.activity", "action_feedback", activity_ids,
                     feedback=NOTE_MARK)
            done = rpc.read(JOB, [job["id"]], ["activity_ids"])[0]
            ctx.check_true(
                "Marking it done moves it off the record and into the "
                "history",
                not any(i in (done["activity_ids"] or [])
                        for i in activity_ids),
                actual_desc=f"job activity_ids={done['activity_ids']}")
            # action_feedback unlinks the activity and posts a message in
            # its place; that message is this run's too and is swept below.
            activity_ids.clear()

    finally:
        with ctx.step("Cleanup: the note and the activity this test wrote "
                      "are removed from the client's record"):
            removed = 0
            if job:
                mine = rpc.search_read(
                    "mail.message",
                    [("model", "=", JOB), ("res_id", "=", job["id"]),
                     "|", ("body", "like", NOTE_MARK),
                     ("subject", "like", NOTE_MARK)], ["id"])
                ids = [row["id"] for row in mine]
                if ids:
                    try:
                        rpc.unlink("mail.message", ids)
                        removed = len(ids)
                    except OdooRPCError as exc:
                        ctx.log(f"[warn] could not remove {ids}: {exc}")
            if activity_ids:
                try:
                    rpc.unlink("mail.activity", activity_ids)
                except OdooRPCError as exc:
                    ctx.log(f"[warn] could not remove activities: {exc}")
            ctx.log(f"cleanup: {removed} message(s) removed, "
                    f"{len(activity_ids)} activity(ies) removed")
            leftover = rpc.call(
                "mail.message", "search_count",
                [("model", "=", JOB), ("body", "like", NOTE_MARK)]) \
                if job else 0
            ctx.check("Nothing this test wrote is left on the client's job "
                      "record", 0, leftover)


@test_case(
    id="TEST-FG13-JOB-016",
    name="Only the job-queue managers can see or touch the job screens",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P1",
    kind="API",
    order=1305,
    description="With a throw-away ordinary user created for the purpose: "
                "the Job Queue app and all three Queue menus are invisible "
                "to them, reading a job, a channel or a job function is "
                "refused with an access message rather than returning rows, "
                "and the manager's own access is unaffected afterwards. The "
                "throw-away user is removed whether the case passes or "
                "fails.",
    traceability=trace("TC-JOB-016"))
def test_job_016(ctx):
    rpc = require_queue_job(ctx)
    probe_uid = None
    login = f"fg13-probe-{int(time.time())}"
    password = f"Probe!{int(time.time())}"

    try:
        with ctx.step("Steps 1-3: Login A — the manager — sees the app, the "
                      "screens and the buttons"):
            manager = ref(rpc, MANAGER_GROUP)
            ctx.check_true("The Job Queue Manager group exists",
                           bool(manager), actual_desc=str(manager))
            ctx.check_true(
                "The acting user is in it", has_group(ctx, MANAGER_GROUP),
                actual_desc="has_group(queue_job.group_queue_job_manager)")
            for model in (JOB, "queue.job.channel", "queue.job.function"):
                count = rpc.call(model, "search_count", [])
                ctx.check_true(f"Login A can read {model}", count >= 0,
                               actual_desc=f"{count} record(s)")

        with ctx.step("Step 4: a second login that is NOT in the group"):
            # v19 renamed res.users.groups_id to group_ids
            # (odoo/addons/base/models/res_users.py). Writing the v15 name
            # would create a user with NO groups at all and quietly make
            # every refusal below meaningless, so the field is checked
            # rather than assumed.
            field = "group_ids" if rpc.field_exists("res.users", "group_ids") \
                else "groups_id"
            ctx.check("res.users spells its groups field the v19 way",
                      "group_ids", field)
            internal = ref(rpc, "base.group_user")
            probe_uid = rpc.create("res.users", {
                "name": "FG-13 access probe (automated, removed after run)",
                "login": login,
                "password": password,
                field: [(6, 0, [internal["res_id"]])],
            })
            ctx.check_true("The ordinary test user was created",
                           bool(probe_uid), actual_desc=f"uid={probe_uid}")

            # `base.group_user` implies a handful of other groups, so the
            # user ends up in more than the one written. What must NOT be
            # among them is the manager group — checked against the
            # *resolved* set rather than the one that was written.
            granted = rpc.read("res.users", [probe_uid], [field])[0][field]
            ctx.check_true(
                "…and it is NOT a Job Queue Manager",
                manager["res_id"] not in (granted or []),
                actual_desc=f"{field}={granted}")

            probe_env = dataclasses.replace(ctx.env, username=login,
                                            password=password)
            probe = OdooRPC(probe_env)
            probe.authenticate()
            ctx.check("Login B authenticates as its own user", probe_uid,
                      probe.uid)

        with ctx.step("Steps 5-6: Login B sees no Job Queue app and no jobs, "
                      "channels or job-functions menu anywhere"):
            # `ir.ui.menu.search` is NOT group-filtered in v19 — a plain
            # search returns every menu row to any user. Visibility is
            # decided by `_filter_visible_menus` inside `load_menus`
            # (odoo/addons/base/models/ir_ui_menu.py:236-244), which is what
            # the web client actually calls to build the apps menu. Asking
            # the wrong question here would report a defect that is not
            # there, so the question asked is the one the browser asks.
            menus = probe.call("ir.ui.menu", "load_menus", False)
            loaded = {int(key) for key in menus if str(key).isdigit()}
            ctx.check_true(
                "Login B's menu tree loaded, so the check below is against "
                "a real answer rather than an empty response",
                bool(menus), actual_desc=f"{len(loaded)} menu(s) visible")

            visible = []
            for xmlid in ("queue_job.menu_queue_job_root",
                          "queue_job.menu_queue",
                          "queue_job.menu_queue_job",
                          "queue_job.menu_queue_job_channel",
                          "queue_job.menu_queue_job_function"):
                row = ref(rpc, xmlid)
                if row and row["res_id"] in loaded:
                    visible.append(xmlid)
            ctx.check("No Job Queue menu is in the menu tree an ordinary "
                      "user is served", [], visible)

            # And the manager IS served them, or the check above would pass
            # for the wrong reason — e.g. if load_menus had returned nothing.
            mine = rpc.call("ir.ui.menu", "load_menus", False)
            mine_ids = {int(key) for key in mine if str(key).isdigit()}
            manager_sees = [xmlid for xmlid in (
                "queue_job.menu_queue_job_root", "queue_job.menu_queue_job")
                if ref(rpc, xmlid)["res_id"] in mine_ids]
            ctx.check("Login A IS served the Job Queue menus, which is what "
                      "makes Login B's empty result meaningful",
                      ["queue_job.menu_queue_job_root",
                       "queue_job.menu_queue_job"], manager_sees)

        with ctx.step("Step 7: reaching a job screen directly as Login B is "
                      "refused with an access message, not shown"):
            for model in (JOB, "queue.job.channel", "queue.job.function"):
                error, rows = "", None
                try:
                    rows = probe.search_read(model, [], ["id"], limit=1)
                except OdooRPCError as exc:
                    error = str(exc)
                ctx.check_true(
                    f"Reading {model} as an ordinary user is refused",
                    bool(error) and rows is None,
                    actual_desc=error or f"RETURNED {rows!r}")
                ctx.check_true(
                    f"…and the refusal names access rather than failing "
                    f"obscurely",
                    "access" in error.lower() or "not allowed" in error.lower()
                    or "permission" in error.lower(),
                    actual_desc=error[:200])
                if rows is not None:
                    finding(ctx,
                            f"an ordinary user in base.group_user only was "
                            f"able to read {model}. queue_job/security/"
                            f"ir.model.access.csv grants every line to "
                            f"queue_job.group_queue_job_manager alone, so a "
                            f"read that succeeds means an access rule was "
                            f"added elsewhere during the upgrade.")

        with ctx.step("Step 8: Login A is unaffected afterwards"):
            for model in (JOB, "queue.job.channel", "queue.job.function"):
                count = rpc.call(model, "search_count", [])
                ctx.check_true(f"Login A can still read {model}", count >= 0,
                               actual_desc=f"{count} record(s)")
            ctx.check_true(
                "Login A is still a Job Queue Manager",
                has_group(ctx, MANAGER_GROUP),
                actual_desc="has_group(queue_job.group_queue_job_manager)")

    finally:
        with ctx.step("Cleanup: the throw-away login is removed"):
            if not probe_uid:
                ctx.log("no probe user was created — nothing to remove")
            else:
                removed = False
                try:
                    rpc.unlink("res.users", [probe_uid])
                    removed = True
                except OdooRPCError as exc:
                    # A user that has touched anything cannot be deleted;
                    # archiving takes the login out of use just as
                    # completely, which is what matters here.
                    ctx.log(f"[warn] delete refused ({exc}); archiving "
                            f"instead")
                    try:
                        rpc.write("res.users", [probe_uid],
                                  {"active": False})
                    except OdooRPCError as exc2:
                        ctx.log(f"[warn] archive also failed: {exc2}")
                still = rpc.call("res.users", "search_count",
                                 [("login", "=", login),
                                  ("active", "=", True)])
                ctx.check("The throw-away login is gone or archived — no "
                          "usable account is left behind on the client's "
                          "database", 0, still)
                ctx.log(f"probe user {login} "
                        + ("deleted" if removed else "archived"))
            manual(ctx,
                   "TC-JOB-016 step 5 as the workbook words it — looking at "
                   "the apps menu with Login B's own eyes. The menu "
                   "visibility is asserted above through ir.ui.menu, which "
                   "is the same filter the web client applies when it "
                   "builds that menu; a human confirming it on screen costs "
                   "one sign-in and is worth doing once.")
