"""FG-14 — TC-LOG-001: each sync leaves one readable log entry that points
back at the record.

Implements the CLIENT MANUAL TESTING GUIDELINE
``MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0.xlsx`` / sheet
``Testing Guideline``, case TC-LOG-001 (P1).

The case is read-only from end to end, which suits it: its subject is what
the log screens *show*, and every one of those facts is on the database.
The store is opened, its seven log actions are resolved, their domains and
pinned views are read, the columns are checked on the assembled arches, a
real failed entry is read field by field, and the search/group-by the
workbook's steps 12 and 13 use are actually run.

The closing note of the workbook is the sharpest part of the case:

    *"if any entry shows the status Cancelled, that value is NEW in Odoo 19.
    Novobi added a filter and a colour for it during the upgrade — confirm
    you can filter on it."*

That is asserted literally, against the search view and the list
decorations, and it is the one part of TC-LOG-001 that is expected to fail
on the current build.
"""
from __future__ import annotations

from framework.registry import test_case

from .common import (CHANNEL, IMPORT_LIST_COLUMNS, LABEL_EXPORTED_BY,
                     LABEL_IMPORTED_BY, LOG, LOG_STATUSES, MODULE,
                     SEARCH_FILTERS, STATUS_LABELS, STORE_LOG_ACTIONS,
                     WORKFLOW, WORKFLOW_NAME, acting_channel, attr,
                     field_attrs, filter_attrs, finding, manual, observation,
                     require_logs, trace, view_arch)

IMPORT_LIST = "omni_log.omni_log_base_import_tree_view"
IMPORT_FORM = "omni_log.omni_log_base_import_form_view"
EXPORT_LIST = "omni_log.omni_log_base_export_tree_view"
SEARCH_VIEW = "omni_log.view_log_filter"

#: Fields TC-LOG-001 step 7 reads off a failed entry's form.
FORM_READS = ("channel_record_id", "entity_name", "create_uid", "create_date",
              "write_date", "status", "message")


@test_case(
    id="TEST-FG14-LOG-001",
    name="Each sync leaves one readable log entry that points back at the "
         "record",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P1",
    kind="API",
    order=1400,
    description="The store card offers all seven log screens, each scoped "
                "to its own operation type and titled with the store; the "
                "import list carries Imported by / ID on Store / Created on "
                "/ Last Updated on / Status / Message and the export list "
                "says Exported by instead; a real failed entry carries a "
                "readable message and its payload; and search by ID on "
                "Store and group by Status both work. The workbook's "
                "closing note about the new Cancelled status is checked "
                "against the search view and the list colours.",
    traceability=trace("TC-LOG-001"))
def test_log_001(ctx):
    rpc = require_logs(ctx)
    channel = acting_channel(ctx)
    ctx.log(f"store: {channel['name']!r} ({channel['platform']})")

    with ctx.step("Step 1: the store card's three-dot menu offers every log "
                  "screen, each scoped to its own operation type"):
        # There is nothing in ``fields_get`` to check — these are methods,
        # not fields. What decides the case is that calling each one returns
        # a window action pointing at omni.log, with a domain naming both
        # this store and exactly one operation type.
        seen = {}
        for name in STORE_LOG_ACTIONS:
            action = rpc.call(CHANNEL, name, [channel["id"]])
            ctx.check_true(f"{name}() returns a screen", bool(action),
                           actual_desc=str(action)[:160])
            ctx.check(f"{name}() opens the log model", LOG,
                      action.get("res_model"))
            domain = str(action.get("domain"))
            ctx.check_true(
                f"{name}() is scoped to this store",
                f"{channel['id']}" in domain and "channel_id" in domain,
                actual_desc=domain[:200])
            operation = [op for op in (
                "import_product", "import_order", "import_shipment",
                "import_others", "export_master", "export_mapping",
                "export_order", "export_inventory", "export_others")
                if f"'{op}'" in domain]
            # Product Export covers TWO operation types — export_master and
            # export_mapping, the master product and its listing — so the
            # assertion is that the screen is scoped to a named operation,
            # not that it is scoped to exactly one.
            ctx.check_true(f"{name}() is scoped to a named operation type",
                           bool(operation), actual_desc=str(operation))
            seen[name] = {"title": action.get("display_name"),
                          "operations": operation}

        # Each screen must still be distinguishable: no two of them may
        # cover the same set, or the three-dot menu would open the same
        # list twice under different names.
        sets = [tuple(sorted(data["operations"])) for data in seen.values()]
        duplicates = sorted({item for item in sets if sets.count(item) > 1})
        ctx.check("No two log screens cover the same operation types", [],
                  duplicates)

        ctx.log("log screens: " + "; ".join(
            f"{k} -> {','.join(v['operations'])}" for k, v in seen.items()))

    with ctx.step("Step 2: each screen is titled with the store and the log "
                  "type"):
        untitled = [name for name, data in seen.items()
                    if not data["title"]
                    or channel["name"] not in str(data["title"])]
        ctx.check("Every log screen's title names the store", [], untitled)
        ctx.log("titles: " + "; ".join(str(v["title"]) for v in seen.values()))

    with ctx.step("Step 3: which filters are pre-applied when a log screen "
                  "opens"):
        action = rpc.call(CHANNEL, "open_log_import_product",
                          [channel["id"]])
        context = str(action.get("context") or "")
        applied = sorted(name for name in SEARCH_FILTERS
                         if f"search_default_{name}" in context)
        observation(ctx, f"pre-applied filters: {applied or 'none'} "
                         f"(context={context[:200]})")
        manual(ctx,
               "TC-LOG-001 step 3 as the workbook words it — the screen's "
               "pre-applied Draft/Failed/Unresolved filters. On this build "
               "the per-store action carries "
               f"{applied or 'no search_default_* keys'}, so what the "
               "tester sees depends on the user's own last-used filters "
               "rather than on the action. Worth one look on screen.")

    with ctx.step("Step 4: the import list's columns"):
        arch = view_arch(ctx, IMPORT_LIST, "list")
        absent = [name for name in IMPORT_LIST_COLUMNS
                  if not field_attrs(arch, name)]
        ctx.check("Every column the workbook names is on the import list",
                  [], absent)
        ctx.check("The author column reads 'Imported by' on an import log",
                  LABEL_IMPORTED_BY, attr(field_attrs(arch, "create_uid"),
                                          "string"))

    with ctx.step("Step 5: every distinct status the log holds"):
        counts = {}
        for status in LOG_STATUSES:
            counts[status] = rpc.call(LOG, "search_count",
                                      [("status", "=", status)])
        ctx.log(f"log entries by status: {counts}")
        ctx.check_true("The log holds entries in more than one status, so "
                       "step 5's 'many more entries appear' is meaningful",
                       sum(1 for value in counts.values() if value) > 1,
                       actual_desc=str(counts))

        fields = rpc.call(LOG, "fields_get", ["status"],
                          attributes=["selection"])
        values = [value for value, _ in fields["status"]["selection"]]
        ctx.check("omni.log.status offers exactly the four values the port "
                  "defined", sorted(LOG_STATUSES), sorted(values))
        labels = dict(fields["status"]["selection"])
        ctx.check("…spelled as the workbook reads them", STATUS_LABELS,
                  labels)

    failed = None
    with ctx.step("Steps 6-9: a failed entry's fields, its message and its "
                  "payload"):
        rows = rpc.search_read(
            LOG, [("status", "=", "failed"), ("channel_id", "=", channel["id"])],
            list(FORM_READS) + ["res_model", "res_id", "shortened_datas_string",
                                "datas_string", "is_resolved",
                                "operation_type"],
            limit=1, order="id desc")
        if not rows:
            ctx.blocked("this store has no failed log entry, so steps 6 to "
                        "10 have nothing to open. The workbook says to mark "
                        "a genuinely empty log N/A rather than raise it.")
        failed = rows[0]
        ctx.log(f"failed entry #{failed['id']} op={failed['operation_type']} "
                f"id_on_store={failed['channel_record_id']!r}")

        empty = [name for name in FORM_READS
                 if failed.get(name) in (False, None, "")]
        # `entity_name` is legitimately empty on a failure that never got as
        # far as naming the record it was working on.
        empty = [name for name in empty if name != "entity_name"]
        ctx.check("Every field the workbook's step 7 reads is populated on "
                  "the failed entry", [], empty)

        message = str(failed.get("message") or "")
        ctx.check_true("The failed entry carries a readable Message",
                       bool(message.strip()),
                       actual_desc=message.strip().splitlines()[0][:160]
                       if message.strip() else "(empty)")
        ctx.log("first line of the message: "
                + (message.strip().splitlines() or ["(empty)"])[0][:200])

        payload = str(failed.get("shortened_datas_string") or "")
        ctx.check_true("The Import Data section shows the payload",
                       bool(payload.strip()),
                       actual_desc=f"{len(payload)} characters")
        if payload and len(str(failed.get("datas_string") or "")) > len(payload):
            observation(ctx, "the payload is truncated on screen and the "
                             "full value is held behind it, which is what "
                             "step 9 asks to be noted.")

    with ctx.step("Step 10: Record in Odoo navigates to the underlying "
                  "document"):
        ctx.check_true("omni.log carries the reference back to the record",
                       rpc.field_exists(LOG, "res_model")
                       and rpc.field_exists(LOG, "res_id"),
                       actual_desc="res_model / res_id present")
        if failed.get("res_model") and failed.get("res_id"):
            exists = rpc.call(failed["res_model"], "search_count",
                              [("id", "=", failed["res_id"])])
            ctx.check_true(
                f"The record this entry points at still exists "
                f"({failed['res_model']}#{failed['res_id']})",
                bool(exists), actual_desc=f"{exists} record(s)")
        else:
            observation(ctx,
                        "this failed entry names no Odoo record — which is "
                        "correct for a failure that happened before the "
                        "record was created. The link is asserted on the "
                        "model above.")

    with ctx.step("Step 12: search by ID on Store finds the entry"):
        search = view_arch(ctx, SEARCH_VIEW, "search")
        name_field = field_attrs(search, "entity_name")
        ctx.check_true(
            "The search box searches the ID on Store as well as the name",
            "channel_record_id" in attr(name_field, "filter_domain"),
            actual_desc=attr(name_field, "filter_domain") or "absent")
        if failed.get("channel_record_id"):
            found = rpc.search(
                LOG, [("channel_record_id", "=", failed["channel_record_id"])],
                limit=5)
            ctx.check_true("Searching that ID on Store finds the entry",
                           failed["id"] in found,
                           actual_desc=f"found ids {found}")

    with ctx.step("Step 13: group by Status works and its groups match the "
                  "counts"):
        group_filter = filter_attrs(search, "status")
        ctx.check_true("A group-by Status is offered", bool(group_filter),
                       actual_desc=group_filter[:160] or "absent")
        ctx.check_true("…and it groups on the status field",
                       "'group_by': 'status'" in attr(group_filter,
                                                      "context"),
                       actual_desc=attr(group_filter, "context"))
        grouped = rpc.read_group(
            LOG, [("channel_id", "=", channel["id"])], ["status"], ["status"])
        ctx.check_true("Grouping by status returns groups",
                       bool(grouped), actual_desc=f"{len(grouped)} group(s)")
        ctx.log("groups: " + ", ".join(
            f"{row.get('status')}={row.get('status_count') or row.get('__count')}"
            for row in grouped))

    with ctx.step("Step 14: the export log reads 'Exported by' and carries "
                  "an Action column"):
        export_arch = view_arch(ctx, EXPORT_LIST, "list")
        ctx.check("The author column reads 'Exported by' on an export log",
                  LABEL_EXPORTED_BY,
                  attr(field_attrs(export_arch, "create_uid"), "string"))
        ctx.check_true(
            "The export list carries the Action column the workbook names",
            bool(field_attrs(export_arch, "data_operation"))
            or "Action" in export_arch,
            actual_desc=field_attrs(export_arch, "data_operation")[:160]
            or "no data_operation column")

    with ctx.step("The workbook's closing note: the Cancelled status is new "
                  "in v19 and must be filterable"):
        cancelled_rows = rpc.call(LOG, "search_count",
                                  [("status", "=", "cancelled")])
        observation(ctx, f"{cancelled_rows} entr(ies) currently hold the "
                         f"'cancelled' status")

        ctx.check_true(
            "'cancelled' is a real value of omni.log.status — the port "
            "added it so a superseded job's log row does not stay 'draft' "
            "for ever",
            "cancelled" in LOG_STATUSES, actual_desc="status selection")

        cancelled_filter = filter_attrs(search, "cancelled")
        has_filter = bool(cancelled_filter) or "'cancelled'" in search
        ctx.check_true(
            "A Cancelled filter is offered on the log search view, as the "
            "workbook's note says it should be",
            has_filter,
            actual_desc=cancelled_filter[:160] if cancelled_filter
            else "the search view offers Draft, Success, Failed, Resolved "
                 "and Unresolved — and no Cancelled filter")

        list_arch = view_arch(ctx, IMPORT_LIST, "list")
        status_tag = field_attrs(list_arch, "status")
        decorations = [name for name in ("decoration-success",
                                         "decoration-danger",
                                         "decoration-info",
                                         "decoration-warning",
                                         "decoration-muted")
                       if name in status_tag]
        has_colour = "cancelled" in status_tag
        ctx.check_true(
            "…and a colour for it on the list",
            has_colour,
            actual_desc=f"status column decorations: {decorations}; "
                        f"'cancelled' is not among their conditions")

        if not (has_filter and has_colour):
            finding(ctx,
                    "omni.log.status gained the 'cancelled' value in the "
                    "v19 port (omni_log/models/omni_log.py:67-80), but "
                    "omni_log/views/base_omni_log_views.xml offers no "
                    "Cancelled filter (only Draft/Success/Failed at lines "
                    "14-20) and the status column's decorations cover only "
                    "done/failed/draft (lines 92-95 and 161-164). An entry "
                    "in that status is therefore invisible to every filter "
                    "on the screen and renders with no colour. TC-LOG-001's "
                    "closing note states the filter was added during the "
                    "upgrade; it was not. Two lines of view XML per list.")
