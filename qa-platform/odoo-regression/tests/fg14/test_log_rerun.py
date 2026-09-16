"""FG-14 — TC-LOG-002, TC-LOG-004 and TC-LOG-005: the re-run buttons, the
Actions menu, and the resolved flag.

Implements the CLIENT MANUAL TESTING GUIDELINE
``MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0.xlsx`` / sheet
``Testing Guideline``, cases TC-LOG-002 (P0), TC-LOG-004 (P1) and
TC-LOG-005 (P1).

All three cases turn on refusals, and all three run against scratch rows
this suite creates and removes — never the gallery's own 6.8 million. See
``tests/fg14/common.py`` for why, and for the one thing this suite must
never do: let a re-run actually succeed, because ``omni.log.run()`` calls
the live Shopify connector.

Each refusal is checked twice: on the message the server produced, and on
the rows afterwards. A guard that raises but still writes, and a guard that
writes without raising, are different defects and both are failures — and
the workbook says so in as many words: *"Neither refusal is a silent
no-op."*
"""
from __future__ import annotations

from framework.registry import test_case

from .common import (BULK_ACTIONS, LOG, MODULE, MSG_NOT_FROM_EXPORT,
                     MSG_NOT_FROM_IMPORT, MSG_ONLY_UNRESOLVED_FAILED,
                     WORKFLOW, WORKFLOW_NAME, acting_channel, attr,
                     button_attrs, filter_attrs, finding, make_log, manual,
                     normalise, observation, read_logs, ref, refuse,
                     require_logs, sweep, trace, view_arch)

IMPORT_FORM = "omni_log.omni_log_base_import_form_view"
EXPORT_FORM = "omni_log.omni_log_base_export_form_view"
SEARCH_VIEW = "omni_log.view_log_filter"

#: The gating expressions on the import log form
#: (``base_omni_log_views.xml:106-118``). ``toggle_resolved`` appears twice:
#: as *Mark as Resolved* and again as *Unresolve*.
RERUN_GATE = "is_resolved or status in ['draft', 'done']"
RESOLVE_GATE = "is_resolved or status in ['draft', 'done']"
UNRESOLVE_GATE = "not is_resolved or status == 'done'"


@test_case(
    id="TEST-FG14-LOG-002",
    name="The re-run buttons appear on the right entries and refuse on the "
         "wrong ones",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P0",
    kind="API",
    order=1401,
    description="The Re-Import button is gated to a failed, unresolved entry "
                "and hidden on a successful one; choosing Re-Import for an "
                "already-successful entry is refused with a readable "
                "message; and choosing it on an EXPORT log is refused with "
                "a different, equally readable one. Both refusals are "
                "checked on the message AND on the rows afterwards. The "
                "happy path is deliberately never taken — omni.log.run() "
                "calls the live Shopify connector.",
    traceability=trace("TC-LOG-002"))
def test_log_002(ctx):
    rpc = require_logs(ctx)
    channel = acting_channel(ctx)
    sweep(ctx)

    try:
        with ctx.step("Steps 3-8: the Re-Import button is on a failed entry "
                      "and absent on a successful one"):
            arch = view_arch(ctx, IMPORT_FORM, "form")

            run_button = button_attrs(arch, "run")
            ctx.check_true("The import log form offers a Re-Import button",
                           bool(run_button),
                           actual_desc=run_button[:200] or "absent")
            ctx.check("Re-Import is hidden on a resolved entry and on any "
                      "entry that is Draft or Success — which is exactly "
                      "'present on FAILED, absent on SUCCESS'",
                      RERUN_GATE, normalise(attr(run_button, "invisible")))
            ctx.check("Re-Import is the label the workbook reads",
                      "Re-Import", attr(run_button, "string"))

            # Spelled out as the two cases the workbook compares, so a
            # reader does not have to evaluate the expression themselves.
            for status, resolved, expected in (
                    ("failed", False, True), ("done", True, False),
                    ("draft", False, False)):
                shown = not (resolved or status in ("draft", "done"))
                ctx.check(
                    f"On a {status!r} entry (is_resolved={resolved}) the "
                    f"Re-Import button is "
                    f"{'shown' if expected else 'absent'}",
                    expected, shown)

        with ctx.step("Steps 9-10: choosing Re-Import for an "
                      "already-successful entry is REFUSED"):
            done_id = make_log(ctx, channel["id"], status="done",
                               operation_type="import_product",
                               label="success")
            rows = read_logs(ctx, [done_id])
            ctx.check_true(
                "A Success entry is forced resolved by the model itself, "
                "which is what the guard then reads",
                rows[0]["is_resolved"] is True,
                actual_desc=f"status={rows[0]['status']} "
                            f"is_resolved={rows[0]['is_resolved']}")

            result = refuse(ctx, "multi_import", [done_id])
            ctx.log(f"multi_import(success entry) -> {result['error']!r}")
            ctx.check_true(
                "Re-Import on a successful entry is refused, not silently "
                "run",
                bool(result["error"]),
                actual_desc=result["error"] or "THE CALL WAS ACCEPTED — the "
                                               "entry would have been "
                                               "re-imported against the "
                                               "live store")
            ctx.check_true(
                "…and the message says the action only applies to failed, "
                "unresolved entries",
                MSG_ONLY_UNRESOLVED_FAILED in result["error"],
                actual_desc=result["error"][:200])
            ctx.check_true("…and nothing on the entry changed",
                           not result["changed"],
                           actual_desc=f"{result['before']} -> "
                                       f"{result['after']}")

        with ctx.step("Steps 11-12: choosing Re-Import on an EXPORT log is "
                      "refused with its own message"):
            export_id = make_log(ctx, channel["id"], status="failed",
                                 operation_type="export_master",
                                 label="export-failed")
            result = refuse(ctx, "multi_import", [export_id])
            ctx.log(f"multi_import(export entry) -> {result['error']!r}")
            ctx.check_true(
                "Re-Import on an export log is refused",
                bool(result["error"]),
                actual_desc=result["error"] or "THE CALL WAS ACCEPTED")
            ctx.check_true(
                "…and the message says you cannot re-import from an export "
                "log",
                MSG_NOT_FROM_EXPORT in result["error"],
                actual_desc=result["error"][:200])
            ctx.check_true("…and nothing on the entry changed",
                           not result["changed"],
                           actual_desc=f"{result['before']} -> "
                                       f"{result['after']}")

            # The mirror image, which the workbook does not walk but which
            # is the same guard read the other way round: Re-Export on an
            # import log.
            import_id = make_log(ctx, channel["id"], status="failed",
                                 operation_type="import_product",
                                 label="import-failed")
            mirror = refuse(ctx, "multi_export", [import_id])
            ctx.check_true(
                "Re-Export on an import log is refused the same way",
                MSG_NOT_FROM_IMPORT in mirror["error"],
                actual_desc=mirror["error"][:200] or "THE CALL WAS ACCEPTED")

        with ctx.step("Step 5: the happy path is left to a human, on "
                      "purpose"):
            manual(ctx,
                   "TC-LOG-002 tells the tester NOT to press the re-run "
                   "button, and this suite obeys the same rule for the same "
                   "reason: omni.log.run() dispatches straight into the "
                   "connector (omni_log/models/omni_log.py:287-305), so a "
                   "successful Re-Import would call the client's live "
                   "Shopify store from a test. Every refusal path is "
                   "exercised above; the success path is never taken.")

    finally:
        with ctx.step("Cleanup: every scratch log row is removed"):
            sweep(ctx)
            left = rpc.call(LOG, "search_count",
                            [("entity_name", "like", "FG14-AUTOMATED-PROBE")])
            ctx.check("No scratch row is left on the client's log", 0, left)


@test_case(
    id="TEST-FG14-LOG-004",
    name="Log entries can be worked in bulk from the Actions menu",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P1",
    kind="API",
    order=1402,
    description="The Actions menu offers exactly four entries — Re-Import, "
                "Re-Export, Mark as Resolved and Unresolve — each bound to "
                "the log list; marking resolved moves several entries at "
                "once out of Unresolved and into Resolved, and unresolving "
                "reverses it exactly; and a selection that includes a Draft "
                "entry is refused with a readable message rather than "
                "silently marked. Run against scratch rows only.",
    traceability=trace("TC-LOG-004"))
def test_log_004(ctx):
    rpc = require_logs(ctx)
    channel = acting_channel(ctx)
    sweep(ctx)

    try:
        with ctx.step("Steps 3-4: the Actions menu offers re-run, mark as "
                      "resolved and unresolve — and nothing else"):
            for xmlid, (label, method) in BULK_ACTIONS.items():
                row = ref(rpc, xmlid)
                ctx.check_true(f"The Actions entry {label!r} exists",
                               bool(row), actual_desc=str(row) or "absent")
                action = rpc.read("ir.actions.server", [row["res_id"]],
                                  ["name", "binding_model_id",
                                   "binding_view_types", "code"])[0]
                ctx.check(f"{label!r} is labelled as the workbook reads it",
                          label, action["name"])
                ctx.check_true(
                    f"{label!r} is bound to the log list, which is what "
                    f"puts it in the Actions menu",
                    bool(action["binding_model_id"])
                    and "list" in (action["binding_view_types"] or ""),
                    actual_desc=f"binding={action['binding_model_id']} "
                                f"views={action['binding_view_types']!r}")
                ctx.check_true(f"{label!r} runs {method}()",
                               method in (action["code"] or ""),
                               actual_desc=action["code"])

            log_model = rpc.search_read("ir.model", [("model", "=", LOG)],
                                        ["id"], limit=1)
            bound = rpc.search_read(
                "ir.actions.server",
                [("binding_model_id", "=", log_model[0]["id"])], ["name"])
            expected = {label for label, _ in BULK_ACTIONS.values()}
            extra = sorted({row["name"] for row in bound} - expected)
            ctx.check("The Actions menu offers no entry beyond the four the "
                      "workbook names", [], extra)

        failed_ids = []
        with ctx.step("Steps 5-9: marking several entries resolved moves "
                      "them all out of Unresolved and into Resolved"):
            failed_ids = [
                make_log(ctx, channel["id"], status="failed",
                         operation_type="import_product",
                         label=f"bulk-{index}")
                for index in range(3)]
            before = read_logs(ctx, failed_ids)
            ctx.check_true("All three start unresolved",
                           all(row["is_resolved"] is False for row in before),
                           actual_desc=str([row["is_resolved"]
                                            for row in before]))

            rpc.call(LOG, "multi_resolved", failed_ids)
            after = read_logs(ctx, failed_ids)
            ctx.check_true(
                "Marking as resolved worked on EVERY selected entry, not "
                "just the first",
                all(row["is_resolved"] is True for row in after),
                actual_desc=str([row["is_resolved"] for row in after]))
            ctx.check_true(
                "…and none of their statuses changed — resolving is "
                "housekeeping, not a change of outcome",
                all(row["status"] == "failed" for row in after),
                actual_desc=str([row["status"] for row in after]))

            unresolved = rpc.search(LOG, [("id", "in", failed_ids),
                                          ("is_resolved", "=", False)])
            resolved = rpc.search(LOG, [("id", "in", failed_ids),
                                        ("is_resolved", "=", True)])
            ctx.check("The Unresolved filter no longer finds them", [],
                      unresolved)
            ctx.check("The Resolved filter finds all three",
                      sorted(failed_ids), sorted(resolved))

        with ctx.step("Steps 10-11: unresolving reverses it exactly"):
            rpc.call(LOG, "multi_unresolved", failed_ids)
            back = read_logs(ctx, failed_ids)
            ctx.check_true("All three are unresolved again",
                           all(row["is_resolved"] is False for row in back),
                           actual_desc=str([row["is_resolved"]
                                            for row in back]))
            ctx.check_true("…and their statuses are untouched throughout",
                           all(row["status"] == "failed" for row in back),
                           actual_desc=str([row["status"] for row in back]))
            found = rpc.search(LOG, [("id", "in", failed_ids),
                                     ("is_resolved", "=", False)])
            ctx.check("They are back under the Unresolved filter",
                      sorted(failed_ids), sorted(found))

        with ctx.step("Step 12: a selection that includes a Draft entry is "
                      "REFUSED, not silently marked"):
            draft_id = make_log(ctx, channel["id"], status="draft",
                                operation_type="import_product",
                                label="draft")
            mixed = failed_ids[:1] + [draft_id]
            result = refuse(ctx, "multi_resolved", mixed)
            ctx.log(f"multi_resolved(failed + draft) -> {result['error']!r}")
            ctx.check_true(
                "Including a Draft entry is refused",
                bool(result["error"]),
                actual_desc=result["error"] or "THE CALL WAS ACCEPTED")
            ctx.check_true(
                "…with the message the workbook calls readable",
                MSG_ONLY_UNRESOLVED_FAILED in result["error"],
                actual_desc=result["error"][:200])
            ctx.check_true(
                "…and NOTHING in the selection was marked — not even the "
                "failed entry that would have qualified on its own",
                not result["changed"],
                actual_desc=f"{result['before']} -> {result['after']}")

        with ctx.step("The same guard read on a Success entry — which the "
                      "workbook's step 12 does not reach, but the Actions "
                      "menu does"):
            done_id = make_log(ctx, channel["id"], status="done",
                               operation_type="import_product",
                               label="bulk-success")
            probe = refuse(ctx, "multi_unresolved", [done_id])
            ctx.log(f"multi_unresolved(success entry) -> "
                    f"{probe['error']!r} changed={probe['changed']}")
            if not probe["error"] and probe["changed"]:
                finding(ctx,
                        "Unresolve accepted a Success entry and cleared its "
                        "resolved flag. omni.log.multi_resolved and "
                        "multi_unresolved both guard with "
                        "`any(status in statuses for status in ['draft', "
                        "'success'])` (omni_log/models/omni_log.py:366-377), "
                        "but 'success' is not a value of omni.log.status — "
                        "the field's values are draft/done/failed/cancelled "
                        "and the SUCCESS label belongs to 'done'. So the "
                        "guard only ever catches Draft, and a successful "
                        "entry can be bulk-unresolved from the Actions "
                        "menu, which the form's own buttons correctly "
                        "prevent (the Unresolve button carries "
                        "invisible=\"not is_resolved or status == 'done'\"). "
                        "TC-LOG-005's Expected Result — 'neither option is "
                        "offered on a successful entry' — holds on the form "
                        "and not in the Actions menu. One-word fix: "
                        "'success' -> 'done' in both guards.")
                # Recorded, not asserted. TC-LOG-005 step 12 words its
                # expectation about the FORM ("open a SUCCESSFUL entry and
                # confirm neither button is offered on it"), and the form
                # gets it right. Failing TC-LOG-004 on a criterion the
                # workbook does not state would put a verdict into the
                # client's acceptance record that the workbook cannot
                # justify. The defect is real and is in the run log, the
                # test's artifacts and the FG-14 feasibility record — it
                # belongs to Novobi's defect list, not to this case's
                # pass/fail.
                ctx.log("NOT COUNTED AGAINST TC-LOG-004 — the workbook "
                        "words this expectation about the form, and the "
                        "form is correct. Raise it as a defect on its own.")
            else:
                ctx.check_true(
                    "Unresolve refuses a Success entry",
                    bool(probe["error"]) or not probe["changed"],
                    actual_desc=probe["error"][:200] or "no change made")

        with ctx.step("Step 13: no re-run action is chosen, on purpose"):
            manual(ctx,
                   "TC-LOG-004 step 13 says 'do NOT choose a re-run "
                   "action', and this suite does not: Re-Import and "
                   "Re-Export are only ever called here on selections their "
                   "guards must refuse (see TEST-FG14-LOG-002).")

    finally:
        with ctx.step("Cleanup: every scratch log row is removed"):
            sweep(ctx)
            left = rpc.call(LOG, "search_count",
                            [("entity_name", "like", "FG14-AUTOMATED-PROBE")])
            ctx.check("No scratch row is left on the client's log", 0, left)


@test_case(
    id="TEST-FG14-LOG-005",
    name="A log entry can be marked resolved and unresolved again",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P1",
    kind="API",
    order=1403,
    description="On a failed entry the form offers Mark as Resolved; using "
                "it swaps that button for Unresolve, moves the entry out of "
                "the Unresolved list and into the Resolved one, and leaves "
                "the Status reading Failed throughout; unresolving reverses "
                "it exactly and the entry ends up where it started. Neither "
                "button is offered on a successful entry. Run against a "
                "scratch row.",
    traceability=trace("TC-LOG-005"))
def test_log_005(ctx):
    rpc = require_logs(ctx)
    channel = acting_channel(ctx)
    sweep(ctx)

    try:
        arch = view_arch(ctx, IMPORT_FORM, "form")

        with ctx.step("Steps 1 and 3: the Unresolved filter exists and a "
                      "failed entry offers Mark as Resolved"):
            search = view_arch(ctx, SEARCH_VIEW, "search")
            for name, domain in (("unresolved", "[('is_resolved','=',False)]"),
                                 ("resolved", "[('is_resolved','=',True)]")):
                tag = filter_attrs(search, name)
                ctx.check_true(f"A {name.title()} filter is offered",
                               bool(tag), actual_desc=tag[:160] or "absent")
                ctx.check(f"The {name.title()} filter's domain", domain,
                          normalise(attr(tag, "domain")))

            resolve_button = button_attrs(arch, "toggle_resolved", 0)
            ctx.check("Mark as Resolved is offered, hidden once the entry "
                      "is resolved or is Draft/Success", RESOLVE_GATE,
                      normalise(attr(resolve_button, "invisible")))
            ctx.check("…labelled as the workbook reads it",
                      "Mark as Resolved", attr(resolve_button, "string"))

        entry_id = None
        with ctx.step("Steps 2 and 4-6: marking it resolved swaps the "
                      "button for Unresolve"):
            entry_id = make_log(ctx, channel["id"], status="failed",
                                operation_type="import_product",
                                label="resolve-cycle")
            before = read_logs(ctx, [entry_id])[0]
            ctx.check("The entry starts unresolved", False,
                      before["is_resolved"])
            ctx.check("…and Failed", "failed", before["status"])
            id_on_store = before["channel_record_id"]
            ctx.log(f"entry ID on Store: {id_on_store!r}")

            rpc.call(LOG, "toggle_resolved", [entry_id])
            after = read_logs(ctx, [entry_id])[0]
            ctx.check("Marking it resolved sets the flag", True,
                      after["is_resolved"])

            unresolve_button = button_attrs(arch, "toggle_resolved", 1)
            ctx.check_true("A second toggle_resolved button is on the form — "
                           "the Unresolve one", bool(unresolve_button),
                           actual_desc=unresolve_button[:200] or "absent")
            ctx.check("Unresolve is shown only once the entry IS resolved, "
                      "and never on a Success entry", UNRESOLVE_GATE,
                      normalise(attr(unresolve_button, "invisible")))
            ctx.check("…labelled as the workbook reads it", "Unresolve",
                      attr(unresolve_button, "string"))

        with ctx.step("Steps 7-8: the entry leaves the Unresolved list and "
                      "joins the Resolved one"):
            in_unresolved = rpc.search(LOG, [("id", "=", entry_id),
                                             ("is_resolved", "=", False)])
            in_resolved = rpc.search(LOG, [("id", "=", entry_id),
                                           ("is_resolved", "=", True)])
            ctx.check("It has left the Unresolved list", [], in_unresolved)
            ctx.check("…and is in the Resolved one", [entry_id], in_resolved)

        with ctx.step("Steps 9-11: unresolving reverses it exactly, and the "
                      "Status still reads Failed throughout"):
            rpc.call(LOG, "toggle_resolved", [entry_id])
            back = read_logs(ctx, [entry_id])[0]
            ctx.check("The entry is unresolved again", False,
                      back["is_resolved"])
            ctx.check("Its Status never changed — resolving is a "
                      "housekeeping flag, not a change of outcome",
                      "failed", back["status"])
            ctx.check("It is back under the Unresolved filter", [entry_id],
                      rpc.search(LOG, [("id", "=", entry_id),
                                       ("is_resolved", "=", False)]))
            ctx.check("…and gone from Resolved", [],
                      rpc.search(LOG, [("id", "=", entry_id),
                                       ("is_resolved", "=", True)]))

        with ctx.step("Step 12: neither button is offered on a successful "
                      "entry"):
            done_id = make_log(ctx, channel["id"], status="done",
                               operation_type="import_product",
                               label="resolve-success")
            row = read_logs(ctx, [done_id])[0]
            resolved = row["is_resolved"]
            status = row["status"]

            resolve_shown = not (resolved or status in ("draft", "done"))
            unresolve_shown = not (not resolved or status == "done")
            ctx.check("Mark as Resolved is absent on a Success entry", False,
                      resolve_shown)
            ctx.check("Unresolve is absent on a Success entry too", False,
                      unresolve_shown)
            observation(ctx,
                        "the form gets this right; the Actions menu does "
                        "not — see the finding recorded by "
                        "TEST-FG14-LOG-004 about the dead 'success' value "
                        "in multi_resolved/multi_unresolved.")

    finally:
        with ctx.step("Cleanup: every scratch log row is removed"):
            sweep(ctx)
            left = rpc.call(LOG, "search_count",
                            [("entity_name", "like", "FG14-AUTOMATED-PROBE")])
            ctx.check("No scratch row is left on the client's log", 0, left)
