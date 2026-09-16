"""FG-13 — TC-JOB-006: each kind of job has its retry policy and channel.

Implements the CLIENT MANUAL TESTING GUIDELINE
``MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0.xlsx`` / sheet
``Testing Guideline``, case TC-JOB-006 (P1).

What stands in for "the baseline"
---------------------------------
The workbook's precondition is *"Novobi has given you the list of job
functions and their channels and retry patterns from the old system"*. This
platform has no v15 database to read that from — the v15 instance is up but
its database is empty — so retyping a remembered list here would be a test
that asserts a guess.

The baseline used instead is the one the client's own modules declare. Each
job function that matters is a ``<record model="queue.job.function">`` in a
module's ``data/queue_job_config_data.xml``, and every one of those leaves
an ``ir.model.data`` row naming the module that owns it. Counting those
rows per module is a statement about what the installed code intends, read
from the database rather than from a file the runner cannot see — and it
catches the two failures that matter after an upgrade: a data file that
stopped loading (the count drops) and a function that lost its channel (the
channel reads ``root`` when the module asked for something else).

Both the declared baseline and the live table are written out as CSV
artifacts, so the tester has the printout the workbook's steps 2, 6 and 10
ask them to tick against.
"""
from __future__ import annotations

import ast
import csv

from adapters.base import OdooRPCError
from framework.registry import test_case

from .common import (JOB_CHANNEL, JOB_FUNCTION, MODULE, WORKFLOW,
                     WORKFLOW_NAME, attr, field_attrs, finding, observation,
                     require_queue_job, trace, view_arch)

#: The job functions each module must own, counted from ``ir.model.data``.
#:
#: The floor is what the module's ``data/queue_job_config_data.xml`` spells
#: out as ``<record model="queue.job.function">``. The database legitimately
#: holds MORE than that: ``queue.job.function._register_job`` creates a
#: function row the first time ``with_delay()`` reaches a method that has no
#: declared one, and attributes it to the module that owns the model. So
#: this is asserted as a shortfall check, never as equality — a module with
#: an extra runtime-registered function is normal, a module that has lost
#: one is a data file that stopped loading during the upgrade.
DECLARED_BY_MODULE = {
    "queue_job": 1,
    "omni_manage_channel": 2,
    "multichannel_product": 11,
    "multichannel_order": 8,
    "multichannel_fulfillment": 6,
    "multichannel_shopify": 5,
}

#: The channel tree the connector builds
#: (``omni_manage_channel/data/queue_job_config_data.xml``). Step 10 ticks
#: the list and its parent relationships off against the baseline.
EXPECTED_CHANNELS = {
    "root": None,
    "root.enforce": "root",
    "root.synching": "root",
    "root.misc": "root",
}

#: Step 8 asks for at least one function connected to product export and
#: one to order import. These are the two the connector pins its retry
#: patterns on.
SAMPLE_FUNCTIONS = ("<product.channel>.put_to_channel",
                    "<ecommerce.channel>._run_import_product")


def _write_csv(ctx, name: str, header: list, rows: list):
    path = ctx.artifacts_dir / name
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)
    ctx.add_artifact(path, "log", name)
    ctx.log(f"artifact written: {name} ({len(rows)} rows)")
    return path


@test_case(
    id="TEST-FG13-JOB-006",
    name="Each kind of job has its retry policy and channel configured",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P1",
    kind="API",
    order=1303,
    description="Every job function the client's modules declare is present "
                "on the database with the channel its module asked for; the "
                "functions are spread across the connector's channels "
                "rather than all sitting on root; every retry pattern "
                "parses as a mapping of attempt to delay; and the root "
                "channel refuses to be renamed or re-parented, in the view "
                "and in the Python. The live table and the declared "
                "baseline are both exported as CSV.",
    traceability=trace("TC-JOB-006"))
def test_job_006(ctx):
    rpc = require_queue_job(ctx)

    functions = []
    with ctx.step("Steps 1-2: the job function list, counted against what "
                  "the installed modules declare"):
        functions = rpc.search_read(
            JOB_FUNCTION, [],
            ["name", "model_id", "method", "channel_id", "channel",
             "retry_pattern", "related_action", "edit_retry_pattern"],
            order="id")
        ctx.log(f"{len(functions)} job functions on the database")

        declared = rpc.search_read(
            "ir.model.data", [("model", "=", JOB_FUNCTION)],
            ["module", "name", "res_id"])
        by_module = {}
        for row in declared:
            by_module[row["module"]] = by_module.get(row["module"], 0) + 1

        shortfall = {module: (expected, by_module.get(module, 0))
                     for module, expected in DECLARED_BY_MODULE.items()
                     if by_module.get(module, 0) < expected}
        ctx.check("No module has lost a declared job function — module: "
                  "(declared, found)", {}, shortfall)
        ctx.log("job functions per owning module: "
                + ", ".join(f"{m}={by_module.get(m, 0)} (declares {e})"
                            for m, e in sorted(DECLARED_BY_MODULE.items())))
        extra = {module: by_module.get(module, 0) - expected
                 for module, expected in DECLARED_BY_MODULE.items()
                 if by_module.get(module, 0) > expected}
        if extra:
            observation(ctx,
                        f"these modules own more function rows than their "
                        f"data files declare: {extra}. That is "
                        f"_register_job creating a row the first time "
                        f"with_delay() reached an undeclared method — "
                        f"expected, and the rows are in the CSV artifact.")

        total_declared = sum(DECLARED_BY_MODULE.values())
        ctx.check_true(
            f"The database holds at least the {total_declared} declared "
            f"functions (extras are created by with_delay() at run time and "
            f"are expected)",
            len(functions) >= total_declared,
            actual_desc=f"{len(functions)} present, {total_declared} declared")

        _write_csv(ctx, "fg13_job_functions.csv",
                   ["name", "model", "method", "channel", "retry_pattern",
                    "related_action"],
                   [[f["name"],
                     f["model_id"][1] if f["model_id"] else "",
                     f["method"], f["channel"], f["retry_pattern"] or "",
                     f["related_action"] or ""] for f in functions])
        _write_csv(ctx, "fg13_job_functions_by_module.csv",
                   ["module", "declared", "found"],
                   [[m, e, by_module.get(m, 0)]
                    for m, e in sorted(DECLARED_BY_MODULE.items())])

    with ctx.step("Step 3: the functions are spread across the channels, "
                  "not all sitting on one"):
        spread = {}
        for row in functions:
            spread[row["channel"]] = spread.get(row["channel"], 0) + 1
        ctx.log(f"functions per channel: {spread}")
        ctx.check_true(
            "More than one channel carries job functions — everything on "
            "root would mean the connector's channel configuration did not "
            "survive the upgrade",
            len(spread) > 1, actual_desc=str(spread))
        ctx.check_true(
            "The connector's own channels carry the bulk of the work",
            sum(count for channel, count in spread.items()
                if channel and channel != "root") >= len(functions) // 2,
            actual_desc=str(spread))

    with ctx.step("Steps 4-8: a named function's model, method, channel and "
                  "retry pattern"):
        by_name = {row["name"]: row for row in functions}
        for name in SAMPLE_FUNCTIONS:
            row = by_name.get(name)
            ctx.check_true(f"The function {name!r} exists — the workbook "
                           f"asks for one on product export and one on "
                           f"order import", bool(row),
                           actual_desc=str(row and row["channel"]) or "absent")
            if not row:
                continue
            ctx.check_true(f"{name!r} names its model and method",
                           bool(row["model_id"]) and bool(row["method"]),
                           actual_desc=f"model={row['model_id']} "
                                       f"method={row['method']!r}")
            ctx.check_true(f"{name!r} is on a connector channel, not root",
                           bool(row["channel"]) and row["channel"] != "root",
                           actual_desc=f"channel={row['channel']!r}")
            ctx.log(f"{name}: channel={row['channel']} "
                    f"retry={row['retry_pattern']!r} "
                    f"related_action={row['related_action']!r}")

        patterned = [row for row in functions if row["retry_pattern"]]
        ctx.check_true(
            "Retry patterns survived the upgrade — at least one function "
            "carries one",
            bool(patterned),
            actual_desc=f"{len(patterned)} of {len(functions)} functions "
                        f"carry a retry pattern")

        unreadable = []
        for row in patterned:
            try:
                parsed = ast.literal_eval(str(row["retry_pattern"]))
                if not isinstance(parsed, dict) or not parsed:
                    unreadable.append((row["name"], row["retry_pattern"]))
                    continue
                # The keys are the attempt number and the values the delay
                # in seconds; a pattern whose values are not numbers would
                # raise inside the runner rather than on this screen.
                for key, value in parsed.items():
                    if not isinstance(int(key), int) or not isinstance(
                            value, (int, float)):
                        unreadable.append((row["name"], row["retry_pattern"]))
                        break
            except (ValueError, SyntaxError, TypeError):
                unreadable.append((row["name"], row["retry_pattern"]))
        ctx.check("Every retry pattern reads as a mapping of attempt number "
                  "to delay in seconds", [], unreadable)

    with ctx.step("Step 7: Allow Commit is present and readable on a job "
                  "function"):
        ctx.check_true("queue.job.function carries the Allow Commit setting",
                       rpc.field_exists(JOB_FUNCTION, "allow_commit"),
                       actual_desc="allow_commit present")
        commits = rpc.search_read(JOB_FUNCTION, [("allow_commit", "=", True)],
                                  ["name"])
        observation(ctx,
                    f"{len(commits)} function(s) allow commit: "
                    + (", ".join(row["name"] for row in commits[:5])
                       or "none"))

    channels = []
    with ctx.step("Steps 9-10: the channel list and its parent "
                  "relationships"):
        channels = rpc.search_read(
            JOB_CHANNEL, [], ["name", "complete_name", "parent_id",
                              "removal_interval"], order="complete_name")
        found = {row["complete_name"]:
                 (row["parent_id"][1] if row["parent_id"] else None)
                 for row in channels}
        ctx.check("The channel list and its parents match the connector's "
                  "declared tree", EXPECTED_CHANNELS, found)
        _write_csv(ctx, "fg13_job_channels.csv",
                   ["complete_name", "parent", "removal_interval"],
                   [[row["complete_name"],
                     row["parent_id"][1] if row["parent_id"] else "",
                     row["removal_interval"]] for row in channels])

    with ctx.step("Step 11: the root channel's Name and Parent Channel are "
                  "read-only, and refuse a write that reaches past the "
                  "form"):
        arch = view_arch(ctx, JOB_CHANNEL,
                         "queue_job.view_queue_job_channel_form", "form")
        for name in ("name", "parent_id"):
            tag = field_attrs(arch, name)
            ctx.check_true(f"{name!r} is on the channel form", bool(tag),
                           actual_desc=tag[:160] or "absent")
            ctx.check(f"{name!r} is read-only on the root channel",
                      "name == 'root'", attr(tag, "readonly"))

        root = [row for row in channels if row["name"] == "root"]
        ctx.check_true("A root channel exists", bool(root),
                       actual_desc=str([r["complete_name"] for r in channels]))
        root_id = root[0]["id"]

        # The view attribute only hides the field; the guard that actually
        # protects the tree is `queue.job.channel.write`
        # (queue_job/models/queue_job_channel.py:78-88), which raises. A
        # refused write rolls itself back, so nothing is left behind — and
        # if it has been lost in the port, the read-back below reports it.
        error = ""
        try:
            rpc.write(JOB_CHANNEL, [root_id], {"name": "root-probe"})
        except OdooRPCError as exc:
            error = str(exc)
        after = rpc.read(JOB_CHANNEL, [root_id], ["name", "parent_id"])[0]
        ctx.check_true(
            "Renaming the root channel is refused with a readable message",
            "Cannot change the root channel" in error,
            actual_desc=error or "the write was ACCEPTED")
        ctx.check("The root channel is still named 'root' afterwards",
                  "root", after["name"])
        ctx.check("The root channel still has no parent", False,
                  after["parent_id"])

        if "Cannot change the root channel" not in error:
            finding(ctx,
                    "queue.job.channel.write did not refuse a rename of the "
                    "root channel. The guard at "
                    "queue_job/models/queue_job_channel.py:78-88 is the only "
                    "thing protecting the channel tree from an RPC client — "
                    "the form's readonly attribute does not. "
                    f"Server said: {error or '(no error)'}")
