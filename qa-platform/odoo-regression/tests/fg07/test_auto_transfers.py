"""FG-07 — TC-INV-016: the automatic account transfers are still configured.

Implements row 42.0 (P2, "Accounting automation") of the CLIENT MANUAL
TESTING GUIDELINE ``MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0.xlsx``
/ sheet ``Testing Guideline``.

The workbook's own framing: *"The gallery moves balances between accounts on
a schedule. Those transfer rules are configuration, and if they are lost the
balances quietly stop moving."*

The workbook's *Why It Matters* column is unusually blunt — "READ THIS FIRST.
The module behind this was RENAMED in Odoo 19, and so was its menu. It is no
longer where it was." Naming that rename precisely, on every axis, is half of
what this case delivers; the other half is the population read.

The rename, on all four axes, from the two source trees
-------------------------------------------------------
Read from ``D:/Projects/odoo15/enterprise/account_auto_transfer`` (v15) and
``D:/Projects/odoo-19.0/enterprise-19.0/account_transfer`` (v19).

===================  =====================================  ==================
axis                 Odoo 15                                Odoo 19
===================  =====================================  ==================
module directory     ``account_auto_transfer``              ``account_transfer``
manifest ``name``    "Account Automatic Transfers"          "Account Transfers"
                     (v15 ``__manifest__.py:5``)            (v19 ``__manifest__.py:2``)
``auto_install``     ``True`` (v15 ``__manifest__.py:20``)  **key absent** — the
                                                            v19 manifest has no
                                                            ``auto_install``
menu label           "Automatic Transfers", inherited from  "Transfers", set on
                     the action (v15                        the menuitem itself
                     ``views/transfer_model_views.xml:18``  (v19
                     — the menuitem at :34-36 carries no    ``views/transfer_model_views.xml:34-38``)
                     ``name`` of its own)
menu parent          ``account.menu_finance_entries_``      ``account.account_``
                     ``management`` (v15 views:36)          ``transactions_menu``
                                                            (v19 views:38)
model names          ``account.transfer.model`` /           **unchanged**
                     ``account.transfer.model.line``        (v19
                     (v15 ``models/transfer_model.py:15``,  ``models/transfer_model.py:14``,
                     ``:328``)                              ``models/transfer_model_line.py:6``)
===================  =====================================  ==================

The last row is the dangerous one. Because the MODEL names did not change, a
database that was migrated without installing ``account_transfer`` can still
be carrying every one of the gallery's transfer rules in its tables, with no
module and no menu to display them — the rules are not lost, they are
*orphaned*, and "install the module" is a very different remedy from
"re-enter the rules". The BLOCK reason this case emits says exactly that
(``tests/fg07/common.py:308-318``).

Because ``auto_install`` is gone, an upgrade does **not** bring the module
along by itself. That is the single most likely reason this case blocks.

The 3 Expected Result lines, and what each is read from
-------------------------------------------------------
1. **"Every transfer rule on the baseline is present."** — read from
   ``search_read('account.transfer.model', [], …)`` with
   ``context={'active_test': False}``. ``active`` is new in v19
   (``enterprise-19.0/account_transfer/models/transfer_model.py:29``; the v15
   model at ``odoo15/enterprise/account_auto_transfer/models/transfer_model.py
   :26-38`` has no such field), so **without** ``active_test: False`` every
   archived rule silently vanishes from the count and the case would report a
   short list as a complete one. The tick-off against the Novobi baseline
   itself is a RESIDUAL MANUAL STEP — the platform does not hold that
   printout and must not invent it. What *is* asserted without the printout:
   the menu is where the workbook says it now is, at least one rule exists,
   and no rule has lost its name, its destination journal, its origin
   accounts or its destination lines.
2. **"The rule you opened has the same accounts and frequency."** — read from
   ``account_ids`` (Origin Accounts, ``transfer_model.py:35``), ``line_ids``
   -> ``account.transfer.model.line.account_id`` (Destination Account,
   ``transfer_model_line.py:11``) and ``frequency``
   (``transfer_model.py:34``). The comparison needs the baseline, so the
   opened rule's accounts and frequency are captured in full, printed into
   the log and written to CSV, and the comparison is a RESIDUAL MANUAL STEP.
   Asserted for real: the frequency is one of the three values v19 defines,
   the rule still lists origin accounts, and every destination line names a
   destination account (which ``_constrains_account_id``,
   ``transfer_model_line.py:20-25``, guarantees for records created through
   the UI but not for records inserted by a SQL migration).
3. **"The active / archived state of each rule matches the baseline."** —
   read from ``active`` and ``state``. See the next section: half of this
   line has no baseline equivalent at all.

Documented adaptation — "active / archived" is not comparable to v15
--------------------------------------------------------------------
Odoo 15's transfer model has **no** ``active`` field, so it has no archived
state and the Novobi baseline cannot contain one. Every migrated rule will
therefore read ``active = True``, and asserting that against a baseline
column that does not exist would be theatre. What this case does instead:

* records the v19-only nature of ``active`` as an OBSERVATION;
* compares the field the two versions **do** share — ``state``, whose raw
  values ``disabled`` / ``in_progress`` are identical in v15
  (``transfer_model.py:38``) and v19 (``transfer_model.py:41``);
* prints the active/archived and disabled/in-progress tallies with every
  rule named, so the human half of the comparison is a read, not a re-run.

A finding this case will surface (expected — NOT a defect)
-----------------------------------------------------------
The ``in_progress`` state was **relabelled** from "Running" (v15
``transfer_model.py:38``) to "In Progress" (v19 ``transfer_model.py:41``).
The stored value did not move. A tester reading the screen against a v15
printout will see a word change and no data change. Logged as an OBSERVATION,
asserted in neither direction — every state comparison in this case is made
on the raw value, and the labels are read live out of ``fields_get`` rather
than from memory.

A second finding — a real functional gap, not a relabelling
------------------------------------------------------------
Odoo 15's ``account.transfer.model.line`` carried a per-destination-line
**Analytic Filter** (``analytic_account_ids``) and **Partner Filter**
(``partner_ids``) — ``odoo15/enterprise/account_auto_transfer/models/
transfer_model.py:336-337``, validated by ``_check_line_ids_filters`` at
:63-80. Odoo 19's line model has **neither**
(``enterprise-19.0/account_transfer/models/transfer_model_line.py:10-13``:
only ``transfer_model_id``, ``account_id``, ``percent``, ``sequence``). The
nearest v19 equivalent is the new *model-level* ``conditions`` domain Char
(``transfer_model.py:42-46``), which applies to the whole rule rather than to
one destination line and cannot express "this destination gets the analytic-A
share and that one the analytic-B share" at all.

So if the Novobi baseline shows any rule using an analytic or partner filter,
that filter has **no v19 home** and was silently dropped by the migration.
This case therefore reports, per rule, whether ``conditions`` is still the
default ``'[]'`` — a rule that used a filter in v15 and shows ``'[]'`` in v19
is transferring the wrong amount every period, quietly. That is a
RESIDUAL MANUAL STEP, because only the baseline says which rules had filters.

Read-only by construction, and one method that must never be called
---------------------------------------------------------------------
The workbook's *State After The Test* is "Nothing changed. Do not run a
transfer." This module creates no record, writes no field, and calls neither
``sweep_fg07`` nor ``cleanup`` — a sweep is itself a delete.

``account.transfer.model`` exposes four PUBLIC methods that are therefore
reachable over ``/web/dataset/call_kw`` and are never called here:
``action_perform_auto_transfer`` (``transfer_model.py:111`` — creates draft
journal entries), ``action_cron_auto_transfer`` (:107 — does the same for
every running rule), ``action_enable`` (:94) and ``action_disable`` (:98),
plus ``action_archive`` (:102). Only ``search_read``, ``read``, ``fields_get``
and ``ir.ui.menu.load_menus`` are used.
"""
from __future__ import annotations

import csv

from adapters.base import OdooRPCError
from framework.registry import test_case
from tests.fg07.common import (NO_TRANSFER_MODULE, TRANSFER_LINE_MODEL,
                               TRANSFER_MENU_PARENT_XMLID,
                               TRANSFER_MENU_XMLID, TRANSFER_MODEL,
                               TRANSFER_MODULE_V15, TRANSFER_MODULE_V19,
                               WORKFLOW, WORKFLOW_NAME, acting_company,
                               company_ctx, fields_present, finding,
                               has_group, m2o_id, m2o_name, menu_by_xmlid,
                               module_state, money, observation, require_v19,
                               residual_manual_step, selection_labels, trace)

RULES_CSV = "TC-INV-016-transfer-rules.csv"
LINES_CSV = "TC-INV-016-transfer-destinations.csv"

RULES_HEADER = ["rule", "active", "state", "state_label", "frequency",
                "frequency_label", "date_start", "date_stop", "journal",
                "company", "origin_accounts", "destination_accounts",
                "total_percent", "conditions", "generated_moves"]
LINES_HEADER = ["rule", "sequence", "destination_account", "percent"]

# The workbook's step 1, verbatim. v19 really does put the menu here:
# account.menu_finance_entries ("Accounting", addons/account/views/
# account_menuitem.xml:24) > account.account_transactions_menu
# ("Transactions", :25) > account_transfer.menu_auto_transfer ("Transfers",
# enterprise-19.0/account_transfer/views/transfer_model_views.xml:34-38).
MENU_PATH = "Accounting > Accounting > Transactions > Transfers"

# The menu is gated on this group (v19 views/transfer_model_views.xml:37).
# The workbook's precondition calls it "Show Full Accounting Features".
MENU_GROUP = "account.group_account_user"
MENU_GROUP_LABEL = "Show Full Accounting Features (account.group_account_user)"
# The RECORDS need only this one (v19 security/ir.model.access.csv:2 and :5
# grant read on both models to account.group_account_readonly), which is why
# a missing MENU_GROUP is reported as a permissions finding and the case then
# carries on rather than blocking.
READ_GROUP = "account.group_account_readonly"

# The three frequency values, unchanged between v15 (transfer_model.py:31-32)
# and v19 (transfer_model.py:34) — raw values AND labels.
FREQUENCIES = ("month", "quarter", "year")
# The two state values, likewise unchanged; only the LABEL of the second moved
# ("Running" -> "In Progress").
STATES = ("disabled", "in_progress")

# Fields the workbook's steps 2-4 read off a rule. Split into the ones without
# which the case has nothing to say, and the ones whose absence is itself the
# report (`active` and `conditions` are both new in v19).
CORE_FIELDS = ("name", "state", "frequency", "journal_id", "account_ids",
               "line_ids")
OPTIONAL_FIELDS = ("active", "conditions", "total_percent", "date_start",
                   "date_stop", "company_id", "move_ids_count")

# v15-only per-line filters with no v19 home.
V15_ONLY_LINE_FIELDS = ("analytic_account_ids", "partner_ids")

LINE_FIELDS = ("transfer_model_id", "account_id", "percent", "sequence")

# Cap the CSV so a database with an unexpected population cannot produce an
# artifact nobody can open. The log always carries the true totals.
CSV_LIMIT = 2000


def _account_labels(ctx, account_ids, company) -> dict:
    """``{id: 'CODE Name'}`` for a set of ``account.account`` ids.

    ``account.account.code`` is **company-dependent** in Odoo 19
    (``addons/account/models/account_account.py``: ``code`` is a compute over
    ``code_store``), so this read is pinned to the acting company like every
    other read in the suite. An unpinned read would not merely be broader —
    it could return a different code for the same account.
    """
    ids = sorted({i for i in account_ids if i})
    if not ids:
        return {}
    try:
        rows = ctx.adapter.rpc.search_read(
            "account.account", [("id", "in", ids)], ["code", "name"],
            context=company_ctx(company))
    except OdooRPCError as exc:
        ctx.log(f"account codes not readable ({exc}) — destination and origin "
                f"accounts are reported by id only")
        return {}
    return {row["id"]: f"{row.get('code') or ''} {row.get('name') or ''}".strip()
            for row in rows}


@test_case(
    id="TEST-FG07-INV-016",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module="account_auto_transfer",
    priority="P2",
    kind="DATA",
    order=713,
    name="The automatic account transfers are still configured",
    description="Read-only proof that the renamed account_transfer module is "
                "installed, that its Transfers menu sits under Accounting > "
                "Transactions where the workbook says it moved to, and that "
                "every transfer rule — archived ones included — still carries "
                "its origin accounts, destination accounts, percentages, "
                "journal, frequency and state; the baseline tick-off is a "
                "residual manual step and no transfer is ever run.",
    traceability=trace("TC-INV-016"))
def test_inv_016(ctx):
    rpc = ctx.adapter.rpc
    # Every accumulator is declared BEFORE the try. The evidence block runs
    # from `finally`, and a NameError raised there over a step that an earlier
    # assertion failure skipped would replace a real FAILED verdict with an
    # AUTOMATION_ERROR.
    evidence: list[list] = []
    line_evidence: list[list] = []
    residual: list[str] = []
    rules: list[dict] = []
    lines_by_rule: dict[int, list[dict]] = {}

    with ctx.step("Precondition (workbook): Odoo 19 with the automatic-"
                  "transfer module installed, and the 'Show Full Accounting "
                  "Features' group"):
        require_v19(ctx)
        company = acting_company(ctx)
        ctx.log(f"acting company #{company['id']} {company['name']!r} — "
                f"company currency {company['currency_name']}")

        # THE PROBE IS HALF THE DELIVERABLE. ir.module.module, never
        # model_exists: if the module is not installed its ir.model row is
        # gone too, but the reverse inference ("no model, therefore the rules
        # were lost") is exactly the wrong conclusion for the client to reach.
        v19_state = module_state(rpc, TRANSFER_MODULE_V19)
        v15_state = module_state(rpc, TRANSFER_MODULE_V15)
        ctx.log(f"ir.module.module state — {TRANSFER_MODULE_V19!r}: "
                f"{v19_state or 'no such module row'}; "
                f"{TRANSFER_MODULE_V15!r} (the v15 name): "
                f"{v15_state or 'no such module row'}")

        if v19_state != "installed":
            # Before blocking, find out whether the RULES are still there.
            # The model names did not change across the rename, so "module
            # missing" and "rules lost" are two different verdicts with two
            # different remedies, and the client must be told which one this
            # is.
            orphan = ""
            try:
                if rpc.model_exists(TRANSFER_MODEL):
                    stranded = rpc.search(
                        TRANSFER_MODEL, [],
                        context=company_ctx(company, active_test=False))
                    orphan = (f" — HOWEVER the model {TRANSFER_MODEL} still "
                              f"resolves on this database and holds "
                              f"{len(stranded)} rule(s), so the gallery's "
                              f"rules are ORPHANED rather than lost: install "
                              f"the module and they should reappear")
                else:
                    orphan = (f" — the model {TRANSFER_MODEL} does not resolve "
                              f"either, so nothing can be read over RPC. The "
                              f"rules may still exist at the SQL level in the "
                              f"account_transfer_model table; check there "
                              f"before concluding they were lost")
            except OdooRPCError as exc:
                orphan = (f" — the model {TRANSFER_MODEL} could not be probed "
                          f"({exc}), so whether the rules survived is unknown")
            legacy = ""
            if v15_state:
                legacy = (f" The v15 module name {TRANSFER_MODULE_V15!r} is "
                          f"still present on this database with state "
                          f"{v15_state!r}, which means the rename was not "
                          f"applied — that row should not exist on a v19 "
                          f"server and points at an incomplete upgrade.")
            ctx.blocked(f"{NO_TRANSFER_MODULE}{orphan}.{legacy} "
                        f"(ir.module.module state for "
                        f"{TRANSFER_MODULE_V19!r}: "
                        f"{v19_state or 'no such module row'})")
        ctx.log(f"module {TRANSFER_MODULE_V19!r}: installed")

        # Groups. The menu needs group_account_user; the RECORDS need only
        # group_account_readonly, so a missing menu group is reported and the
        # case continues.
        can_see_menu = has_group(ctx, MENU_GROUP)
        can_read_rules = has_group(ctx, READ_GROUP)
        ctx.log(f"runner groups — {MENU_GROUP}: {can_see_menu}; "
                f"{READ_GROUP}: {can_read_rules}")
        if not can_see_menu:
            finding(ctx,
                    f"the runner user does NOT hold {MENU_GROUP_LABEL}, which "
                    f"is the group the Transfers menuitem is gated on "
                    f"(enterprise-19.0/account_transfer/views/"
                    f"transfer_model_views.xml:37). The menu will therefore be "
                    f"INVISIBLE to this user even though the module is "
                    f"installed — that is a permissions finding, not a "
                    f"missing module, and the workbook's If It Fails column "
                    f"asks for exactly that distinction. The rule records "
                    f"below are still readable because "
                    f"{READ_GROUP} is enough for them "
                    f"(security/ir.model.access.csv:2,5)")
            residual.append(
                f"re-run workbook step 1 ('{MENU_PATH}') as an accountant who "
                f"holds {MENU_GROUP_LABEL}: this run's user does not, so the "
                f"menu's visibility on screen was NOT proven — only that the "
                f"menuitem record exists in the right place.")

    try:
        with ctx.step(f"Step 1 (workbook): {MENU_PATH} — the menu the "
                      f"workbook warns has MOVED"):
            # Name the rename on every axis, in the log, before asserting
            # anything: this is what the tester has to carry back to Novobi.
            ctx.log("RENAME (v15 -> v19), all four axes: module "
                    f"{TRANSFER_MODULE_V15!r} -> {TRANSFER_MODULE_V19!r}; "
                    "manifest name 'Account Automatic Transfers' -> 'Account "
                    "Transfers'; menu label 'Automatic Transfers' (inherited "
                    "from the action) -> 'Transfers' (set on the menuitem), "
                    f"xmlid account_auto_transfer.menu_auto_transfer -> "
                    f"{TRANSFER_MENU_XMLID}; menu parent "
                    "account.menu_finance_entries_management -> "
                    f"{TRANSFER_MENU_PARENT_XMLID}. MODEL NAMES UNCHANGED: "
                    f"{TRANSFER_MODEL} / {TRANSFER_LINE_MODEL}.")
            observation(ctx,
                        "the module lost its auto_install flag in v19 (v15 "
                        "__manifest__.py:20 has auto_install=True; the v19 "
                        "manifest has no such key), so an upgrade does not "
                        "bring it along by itself and it must be installed "
                        "deliberately. On this database it IS installed")

            menu = menu_by_xmlid(ctx, TRANSFER_MENU_XMLID)
            if not menu:
                # Module installed but its menuitem record absent: the Python
                # loaded and the XML did not. A half-applied module upgrade.
                ctx.blocked(
                    f"ir.module.module says {TRANSFER_MODULE_V19!r} is "
                    f"installed, but the menu record {TRANSFER_MENU_XMLID!r} "
                    f"does not resolve, so the module's views did not load. "
                    f"The Transfers menu cannot appear under "
                    f"'{MENU_PATH}' for anyone, whatever their groups. A "
                    f"module upgrade probably failed half-way — re-run "
                    f"-u {TRANSFER_MODULE_V19} and check the server log "
                    f"before reporting the rules as lost")
            parent_id = rpc.ref(TRANSFER_MENU_PARENT_XMLID)
            ctx.log(f"menu #{menu['id']} {menu['name']!r} — parent "
                    f"#{menu['parent_id']} {menu['parent_name']!r}, action "
                    f"{menu['action']!r}, sequence {menu['sequence']}, active="
                    f"{menu['active']}")

            # The workbook's If It Fails column: "If the Transfers menu is not
            # under Transactions, say so". Both halves of that sentence are
            # asserted — the label and the parent — because a menu that exists
            # under the wrong parent is just as unfindable as a missing one.
            ctx.check("The menu is labelled 'Transfers' in Odoo 19, not "
                      "'Automatic Transfers' as in Odoo 15 (menuitem name, "
                      "views/transfer_model_views.xml:35)",
                      "Transfers", menu["name"])
            ctx.check("The Transfers menu hangs under Accounting > "
                      "Accounting > Transactions, where Odoo 19 moved it "
                      "(parent account.account_transactions_menu, "
                      "views/transfer_model_views.xml:38) — not under the v15 "
                      "parent account.menu_finance_entries_management",
                      parent_id, menu["parent_id"])
            ctx.check_true(
                "The Transfers menu itself is not archived",
                menu["active"],
                actual_desc=f"ir.ui.menu.active={menu['active']}")

            # Visibility, as the web client computes it. load_menus is public
            # and @api.model (odoo/addons/base/models/ir_ui_menu.py:234-236);
            # it applies the group filtering the menuitem's groups= attribute
            # drives, which read() does not.
            visible = None
            try:
                loaded = rpc.call("ir.ui.menu", "load_menus", False,
                                  context=company_ctx(company)) or {}
                visible = (str(menu["id"]) in loaded
                           or menu["id"] in loaded)
            except OdooRPCError as exc:
                ctx.log(f"ir.ui.menu.load_menus unavailable ({exc}) — menu "
                        f"visibility for this user was not measured; the "
                        f"menuitem record's own placement is still asserted "
                        f"above")
            if visible is True:
                ctx.log(f"the Transfers menu IS in this user's menu tree — "
                        f"'{MENU_PATH}' is navigable as written")
            elif visible is False:
                # Do not fail here when the group is the known cause: that is
                # a permissions finding already recorded in the precondition.
                message = (f"the Transfers menu record exists in the right "
                           f"place but is NOT in this user's menu tree, so "
                           f"'{MENU_PATH}' is not navigable for them")
                if can_see_menu:
                    ctx.check_true(
                        f"An accountant holding {MENU_GROUP_LABEL} can see "
                        f"the Transfers menu in the '{MENU_PATH}' tree "
                        f"(ir.ui.menu.load_menus)",
                        False,
                        actual_desc=f"{message}, even though the user DOES "
                                    f"hold {MENU_GROUP}. A parent menu in the "
                                    f"path is probably hidden or empty")
                else:
                    finding(ctx, f"{message} — the cause is the missing "
                                 f"{MENU_GROUP} group recorded above, not the "
                                 f"module")

        with ctx.step("Step 2 / Expected line 1: read the list of transfer "
                      "rules — archived ones included — to tick off against "
                      "the baseline"):
            present = fields_present(rpc, TRANSFER_MODEL,
                                     list(CORE_FIELDS) + list(OPTIONAL_FIELDS))
            missing_core = [f for f in CORE_FIELDS if f not in present]
            missing_optional = [f for f in OPTIONAL_FIELDS if f not in present]
            ctx.check("Every field the workbook reads off a transfer rule — "
                      "its name, state, frequency, destination journal, "
                      "origin accounts and destination lines — is readable",
                      [], missing_core)
            if missing_optional:
                finding(ctx,
                        f"these Odoo 19 transfer-rule fields are not readable "
                        f"on this database: {', '.join(missing_optional)}. "
                        f"'active' and 'conditions' are both NEW in v19 "
                        f"(transfer_model.py:29 and :42-46); if they are "
                        f"absent the installed module is not the v19 one")
            readable = [f for f in CORE_FIELDS + OPTIONAL_FIELDS
                        if f in present]

            # active_test=False is MANDATORY, not defensive. `active` is new
            # in v19, and with the default active_test every archived rule
            # would be dropped from this read — turning "the baseline lists 9
            # rules and I see 7" into a false migration failure, and hiding
            # the archived rules that Expected line 3 is entirely about.
            context = company_ctx(company, active_test=False)
            try:
                rules = rpc.search_read(TRANSFER_MODEL, [], readable,
                                        context=context, order="name asc")
            except OdooRPCError as exc:
                ctx.blocked(
                    f"the transfer rules could not be read on this database "
                    f"({exc}). The module {TRANSFER_MODULE_V19!r} is "
                    f"installed, so this is an access problem rather than a "
                    f"missing module: reading {TRANSFER_MODEL} needs "
                    f"{READ_GROUP} "
                    f"(security/ir.model.access.csv:2). The runner user holds "
                    f"it: {can_read_rules}")

            frequency_labels = selection_labels(rpc, TRANSFER_MODEL,
                                                "frequency")
            state_labels = selection_labels(rpc, TRANSFER_MODEL, "state")
            account_labels = _account_labels(
                ctx,
                [i for row in rules for i in (row.get("account_ids") or [])],
                company)

            ctx.log(f"{len(rules)} transfer rule(s) on this database "
                    f"(archived included), company #{company['id']}")
            incomplete = []
            for row in rules:
                origins = [account_labels.get(i, f"account#{i}")
                           for i in (row.get("account_ids") or [])]
                row["_origins"] = origins
                row["_line_ids"] = list(row.get("line_ids") or [])
                ctx.log(
                    f"  {row.get('name')!r} — active="
                    f"{row.get('active')} state={row.get('state')!r} "
                    f"({state_labels.get(str(row.get('state')), '?')}) "
                    f"frequency={row.get('frequency')!r} "
                    f"({frequency_labels.get(str(row.get('frequency')), '?')}) "
                    f"period {row.get('date_start') or '?'} -> "
                    f"{row.get('date_stop') or 'forever'} journal="
                    f"{m2o_name(row.get('journal_id'))!r} "
                    f"origins={origins} "
                    f"destinations={len(row['_line_ids'])} "
                    f"total_percent={money(row.get('total_percent')):.2f} "
                    f"conditions={row.get('conditions')!r} "
                    f"generated_moves={row.get('move_ids_count')}")
                # Each of these four is a way for a rule to survive the
                # migration as a shell that produces nothing, which a count
                # against the baseline would never reveal.
                for label, empty in (
                        ("no name", not (row.get("name") or "").strip()),
                        ("no Destination Journal",
                         not m2o_id(row.get("journal_id"))),
                        ("no Origin Accounts", not row.get("account_ids")),
                        ("no Destination Accounts", not row["_line_ids"])):
                    if empty:
                        incomplete.append(
                            f"{row.get('name') or f'rule#{row.get(chr(105) + chr(100))}'}"
                            f": {label}")

            # The workbook's Preconditions say Novobi HAS supplied the rules,
            # so a database with none of them fails Expected line 1 outright —
            # no printout needed to judge that.
            ctx.check_true(
                "At least one automatic transfer rule is configured, as the "
                "workbook's precondition ('Novobi has given you the automatic "
                "transfer rules from the old system') assumes",
                bool(rules),
                actual_desc=f"{len(rules)} rule(s) found on "
                            f"{TRANSFER_MODEL} for company #{company['id']} "
                            f"with active_test disabled")
            ctx.check("Every transfer rule still carries a name, a "
                      "Destination Journal, at least one Origin Account and "
                      "at least one Destination Account — a rule missing any "
                      "of these is present in the list but moves no balance",
                      [], incomplete)

            residual.append(
                f"tick the {len(rules)} rule name(s) below off against the "
                f"Novobi baseline list of transfer rules, which the platform "
                f"does not hold: "
                + "; ".join(sorted(repr(r.get("name") or "") for r in rules))
                + f". The full detail of each — origin accounts, destination "
                  f"accounts, percentages, journal, frequency, dates, state "
                  f"and archived flag — is in {RULES_CSV} and "
                  f"{LINES_CSV}. A rule on the baseline that is absent here "
                  f"is the loss this case exists to find; a rule here that is "
                  f"not on the baseline was created after the baseline was "
                  f"taken.")

        with ctx.step("Step 3 / Expected line 2: open one rule and check its "
                      "source accounts, destination account and frequency"):
            # Deterministic pick without relying on a record id: the rules
            # were read ordered by name, so "the first one" is the same rule
            # on every run of the same database.
            opened = rules[0]
            opened_name = opened.get("name") or ""
            ctx.log(f"opening the first rule by name: {opened_name!r}")

            all_line_ids = [i for row in rules for i in row["_line_ids"]]
            lines = []
            lines_unreadable = ""
            if all_line_ids:
                try:
                    lines = rpc.search_read(
                        TRANSFER_LINE_MODEL,
                        [("transfer_model_id", "in",
                          [row["id"] for row in rules])],
                        list(LINE_FIELDS), context=context,
                        order="transfer_model_id, sequence, id")
                except OdooRPCError as exc:
                    lines_unreadable = str(exc)
                    ctx.log(f"{TRANSFER_LINE_MODEL} not readable ({exc}) — "
                            f"destination accounts are reported from the "
                            f"parent rule's line count only")
            if lines_unreadable:
                # Half of Expected line 2 ("the same accounts") and the whole
                # of the percentage-integrity step below become unmeasurable
                # here. Silence would let both pass vacuously, so the hole is
                # handed to a human with the rule named — appended before any
                # ctx.check, which raises.
                residual.append(
                    f"THE DESTINATION ACCOUNTS OF EVERY RULE WERE NOT "
                    f"MEASURED: {TRANSFER_LINE_MODEL} could not be read by "
                    f"this runner ({lines_unreadable}), so Expected line 2's "
                    f"'the same accounts' could only be checked on the ORIGIN "
                    f"side, and the percentage checks below saw no lines at "
                    f"all. Reading that model needs {READ_GROUP} "
                    f"(security/ir.model.access.csv:5). Re-run as a user who "
                    f"holds it, or open each rule at '{MENU_PATH}' and compare "
                    f"its Destination Accounts and percentages against the "
                    f"Novobi baseline by hand. The rules reference "
                    f"{len(all_line_ids)} destination line(s) in total, so "
                    f"they exist — they were simply not readable.")
            line_account_labels = _account_labels(
                ctx, [m2o_id(l.get("account_id")) for l in lines], company)
            for line in lines:
                lines_by_rule.setdefault(
                    m2o_id(line.get("transfer_model_id")), []).append(line)

            opened_lines = lines_by_rule.get(opened["id"], [])
            for line in opened_lines:
                account_id = m2o_id(line.get("account_id"))
                ctx.log(f"    destination: "
                        f"{line_account_labels.get(account_id) or m2o_name(line.get('account_id')) or '(blank)'}"
                        f" @ {money(line.get('percent')):.2f}% "
                        f"(sequence {line.get('sequence')})")
            ctx.log(f"  {opened_name!r} — origins {opened['_origins']}, "
                    f"frequency {opened.get('frequency')!r} "
                    f"({frequency_labels.get(str(opened.get('frequency')), '?')})"
                    f", journal "
                    f"{m2o_name(opened.get('journal_id'))!r}, period "
                    f"{opened.get('date_start') or '?'} -> "
                    f"{opened.get('date_stop') or 'forever'}")

            # Printout-free half of Expected line 2.
            ctx.check_true(
                f"The rule opened ({opened_name!r}) has a frequency Odoo 19 "
                f"recognises — Monthly, Quarterly or Yearly; the three raw "
                f"values are identical to Odoo 15's, so a baseline frequency "
                f"maps across unchanged (transfer_model.py:34 vs v15 :31-32)",
                opened.get("frequency") in FREQUENCIES,
                actual_desc=f"frequency={opened.get('frequency')!r} "
                            f"(expected one of {list(FREQUENCIES)})")
            ctx.check("The rule opened still lists its source (Origin) "
                      "accounts — the accounts the balance is swept FROM",
                      [], [] if opened["_origins"]
                      else [f"{opened_name}: Origin Accounts empty"])
            ctx.check_true(
                "The rule opened still lists at least one destination "
                "account with a percentage",
                bool(opened_lines) or bool(opened["_line_ids"]),
                actual_desc=f"{len(opened_lines)} destination line(s) read, "
                            f"{len(opened['_line_ids'])} referenced by the "
                            f"rule")
            # _constrains_account_id (transfer_model_line.py:20-25) guarantees
            # this for anything created through the UI, but NOT for rows a SQL
            # migration inserted — which is precisely how these rules arrived.
            blank_destinations = [
                f"{(next((r.get('name') for r in rules if r['id'] == m2o_id(line.get('transfer_model_id'))), '') or '?')}"
                f": destination line at sequence {line.get('sequence')} names "
                f"no account"
                for line in lines if not m2o_id(line.get("account_id"))]
            ctx.check("Every destination line of every rule names a "
                      "destination account (account.transfer.model.line."
                      "_constrains_account_id, transfer_model_line.py:20-25 — "
                      "a blank one sends the balance nowhere)",
                      [], blank_destinations)

            residual.append(
                f"workbook step 3 opened the rule {opened_name!r}. Compare "
                f"against the Novobi baseline: Origin Accounts "
                f"{opened['_origins']}; Destination Accounts "
                + str([f"{line_account_labels.get(m2o_id(l.get('account_id'))) or m2o_name(l.get('account_id')) or '(blank — the line names no account)'} "
                       f"@ {money(l.get('percent')):.2f}%"
                       for l in opened_lines]
                      if opened_lines else
                      ("(not readable — see the residual note above)"
                       if lines_unreadable else "(none)"))
                + f"; frequency {opened.get('frequency')!r} "
                  f"({frequency_labels.get(str(opened.get('frequency')), '?')})"
                  f"; Destination Journal "
                  f"{m2o_name(opened.get('journal_id'))!r}; period "
                  f"{opened.get('date_start') or '?'} to "
                  f"{opened.get('date_stop') or 'forever'}. The other "
                  f"{max(0, len(rules) - 1)} rule(s) are in {LINES_CSV} in "
                  f"the same shape, so the whole comparison can be done from "
                  f"the artifacts without re-opening the screens.")

        with ctx.step("Step 4 / Expected line 3: check whether each rule is "
                      "active or archived, and compare against the baseline"):
            # HALF OF THIS LINE HAS NO BASELINE EQUIVALENT. Say so plainly
            # rather than asserting something that cannot be wrong.
            observation(ctx,
                        "'active / archived' is a v19-ONLY concept for "
                        "transfer rules: Odoo 15's account.transfer.model has "
                        "no `active` field at all (odoo15/enterprise/"
                        "account_auto_transfer/models/transfer_model.py:26-38"
                        "), so the Novobi baseline cannot carry an archived "
                        "column and every migrated rule will read "
                        "active=True. Nothing is asserted about it in either "
                        "direction; the shared field `state` is compared "
                        "instead")
            observation(ctx,
                        "the state Odoo 15 labelled 'Running' is labelled 'In "
                        "Progress' in Odoo 19 (v15 transfer_model.py:38 vs "
                        "v19 transfer_model.py:41). The STORED value is "
                        "'in_progress' in both, so a baseline that says "
                        "'Running' and a screen that says 'In Progress' are "
                        "the same state — this is a relabelling, not a "
                        "change, and this case compares raw values only. "
                        f"Labels read live from this database: {state_labels}")

            archived = [r.get("name") for r in rules if not r.get("active")]
            active_rules = [r.get("name") for r in rules if r.get("active")]
            by_state: dict[str, list] = {}
            for row in rules:
                by_state.setdefault(str(row.get("state")), []).append(
                    row.get("name"))
            ctx.log(f"active: {len(active_rules)} rule(s) {active_rules}")
            ctx.log(f"archived: {len(archived)} rule(s) {archived}")
            for state, names in sorted(by_state.items()):
                ctx.log(f"state {state!r} "
                        f"({state_labels.get(state, '?')}): {len(names)} "
                        f"rule(s) {names}")

            # Raw values only — a label comparison would report a translation
            # or the 'Running' relabelling above as a defect.
            bad_states = [f"{r.get('name')}: state={r.get('state')!r}"
                          for r in rules if r.get("state") not in STATES]
            ctx.check("Every transfer rule's state is one of the two values "
                      "Odoo 19 defines — 'disabled' or 'in_progress' — the "
                      "same two raw values Odoo 15 used",
                      [], bad_states)

            # Archiving goes through action_archive, which disables first
            # (transfer_model.py:102-104), so a rule that is archived AND
            # in_progress can only have been produced by a write that
            # bypassed the button — i.e. by the data migration. Reported, not
            # asserted: the workbook states no expectation about it, and the
            # combination is inert rather than harmful (the daily cron's
            # search at :143 uses the default active_test and skips archived
            # rules anyway).
            contradictory = [r.get("name") for r in rules
                             if not r.get("active")
                             and r.get("state") == "in_progress"]
            if contradictory:
                finding(ctx,
                        f"{len(contradictory)} rule(s) are ARCHIVED while "
                        f"still carrying state 'in_progress': "
                        f"{contradictory}. Odoo's own Archive button disables "
                        f"a rule first (action_archive, transfer_model.py:"
                        f"102-104), so this combination cannot be produced "
                        f"through the screens — it came from the migration. "
                        f"The rules will not run (the daily cron searches "
                        f"state='in_progress' with archived rules filtered "
                        f"out, transfer_model.py:107-109), but the form will "
                        f"show them as In Progress, which reads as 'this is "
                        f"working' when it is not")

            residual.append(
                f"compare the state of each rule against the Novobi "
                f"baseline, remembering that 'Running' in the old system is "
                f"'In Progress' here and is the SAME stored value: "
                + "; ".join(f"{state} ({state_labels.get(state, '?')}): "
                            f"{sorted(str(n) for n in names)}"
                            for state, names in sorted(by_state.items()))
                + f". The archived flag has no baseline counterpart (v15 had "
                  f"no such field); on this database "
                  f"{len(archived)} rule(s) are archived: {archived}. If any "
                  f"of those is a rule the gallery still relies on, it will "
                  f"never run again and nothing on screen will say so.")

        with ctx.step("Integrity the baseline cannot give: every rule's "
                      "destination percentages still add up"):
            # account.transfer.model._check_line_ids_percent
            # (transfer_model.py:80-85) requires 0 < total_percent <= 100.
            # It is a Python @api.constrains, so it fires on UI writes but NOT
            # on rows a SQL migration inserted. A rule whose destinations sum
            # to 60% silently leaves 40% of the balance behind every period.
            over = []
            mismatched = []
            for row in rules:
                own = lines_by_rule.get(row["id"], [])
                if not own:
                    # Already reported as "no Destination Accounts" above;
                    # counting it here too would double-report one fault.
                    continue
                # The compute sums only lines that HAVE an account
                # (transfer_model.py:91), so mirror that exactly.
                summed = money(sum(money(line.get("percent")) for line in own
                                   if m2o_id(line.get("account_id"))))
                stated = money(row.get("total_percent"))
                if not 0 < summed <= 100.0:
                    over.append(f"{row.get('name')}: destinations sum to "
                                f"{summed:.2f}% (the model's own constraint "
                                f"requires more than 0 and at most 100)")
                if "total_percent" in present and summed != stated:
                    mismatched.append(
                        f"{row.get('name')}: the lines sum to {summed:.2f}% "
                        f"but Total Percent shows {stated:.2f}%")
                row["_summed_percent"] = summed
            ctx.check("No transfer rule's destination percentages fall "
                      "outside the 0-100 range its own constraint enforces "
                      "(_check_line_ids_percent, transfer_model.py:80-85) — "
                      "a rule summing to less than 100% leaves part of the "
                      "balance behind every period",
                      [], over)
            ctx.check("Every rule's Total Percent equals the sum of its "
                      "destination lines (_compute_total_percent, "
                      "transfer_model.py:87-92)",
                      [], mismatched)

        with ctx.step("Functional gap (v15 -> v19): the per-line Analytic "
                      "Filter and Partner Filter have no Odoo 19 home"):
            line_present = fields_present(
                rpc, TRANSFER_LINE_MODEL,
                list(LINE_FIELDS) + list(V15_ONLY_LINE_FIELDS))
            survivors = [f for f in V15_ONLY_LINE_FIELDS
                         if f in line_present]
            ctx.log(f"{TRANSFER_LINE_MODEL} fields readable here: "
                    f"{sorted(line_present)}")
            # Asserted, not merely logged, because it PINS the shape the
            # residual step below depends on: if these two fields were present
            # the gap would not exist and the tester should not go hunting for
            # dropped filters. A failure here means the installed module is
            # not stock Odoo 19 — worth surfacing either way.
            ctx.check("Odoo 19 no longer offers a per-destination-line "
                      "Analytic Filter or Partner Filter on a transfer rule "
                      "(v15 transfer_model.py:336-337; the v19 line model at "
                      "transfer_model_line.py:10-13 carries only the transfer "
                      "model, destination account, percent and sequence)",
                      [], survivors)

            with_conditions = [
                (r.get("name"), r.get("conditions"))
                for r in rules
                if (r.get("conditions") or "[]").strip() not in ("[]", "")]
            plain = [r.get("name") for r in rules
                     if (r.get("conditions") or "[]").strip() in ("[]", "")]
            ctx.log(f"rules carrying a model-level Conditions domain: "
                    f"{with_conditions}")
            ctx.log(f"rules whose Conditions is still the default '[]': "
                    f"{plain}")
            residual.append(
                f"check the Novobi baseline for any rule that used an "
                f"ANALYTIC or PARTNER filter on one of its destination lines. "
                f"Odoo 19 removed both fields; the nearest equivalent is the "
                f"new model-level Conditions domain, which applies to the "
                f"whole rule rather than to one destination line and cannot "
                f"express a per-destination split at all. On this database "
                f"{len(plain)} of {len(rules)} rule(s) have Conditions still "
                f"at the default '[]' ({plain}) and "
                f"{len(with_conditions)} carry a domain "
                f"({with_conditions}). A baseline rule that had a filter and "
                f"shows '[]' here has had that filter SILENTLY DROPPED and is "
                f"transferring the wrong amount every period — that is a "
                f"functional gap for Novobi, not a test failure.")
    finally:
        with ctx.step("Evidence: write the transfer-rule and destination "
                      "CSVs"):
            for row in rules:
                lines_here = lines_by_rule.get(row.get("id"), [])
                destinations = "; ".join(
                    f"{m2o_name(line.get('account_id')) or '(blank)'} @ "
                    f"{money(line.get('percent')):.2f}%"
                    for line in lines_here)
                evidence.append([
                    row.get("name") or "",
                    row.get("active"),
                    row.get("state") or "",
                    state_labels.get(str(row.get("state")), "")
                    if "state_labels" in dir() else "",
                    row.get("frequency") or "",
                    "",
                    row.get("date_start") or "",
                    row.get("date_stop") or "",
                    m2o_name(row.get("journal_id")),
                    m2o_name(row.get("company_id")),
                    "; ".join(row.get("_origins") or []),
                    destinations,
                    money(row.get("total_percent")),
                    row.get("conditions") or "",
                    row.get("move_ids_count"),
                ])
                for line in lines_here:
                    line_evidence.append([
                        row.get("name") or "",
                        line.get("sequence"),
                        m2o_name(line.get("account_id")) or "(blank)",
                        money(line.get("percent")),
                    ])

            for path_name, header, csv_rows in (
                    (RULES_CSV, RULES_HEADER, evidence[:CSV_LIMIT]),
                    (LINES_CSV, LINES_HEADER, line_evidence[:CSV_LIMIT])):
                path = ctx.artifacts_dir / path_name
                try:
                    with path.open("w", newline="", encoding="utf-8") as fh:
                        writer = csv.writer(fh)
                        writer.writerow(header)
                        writer.writerows(csv_rows)
                    ctx.add_artifact(path, "log", path_name)
                    ctx.log(f"wrote {len(csv_rows)} row(s) to {path_name}")
                except OSError as exc:
                    ctx.log(f"could not write {path_name} ({exc}) — the "
                            f"figures above are still in this log")

            for note in residual:
                residual_manual_step(ctx, note)

            ctx.log("NOTHING WAS CREATED OR MODIFIED by this case — the "
                    "workbook's State After The Test is 'Nothing changed. Do "
                    "not run a transfer.', so no sweep and no cleanup runs "
                    "here either (a sweep is itself a delete). No transfer "
                    "was run: action_perform_auto_transfer, "
                    "action_cron_auto_transfer, action_enable, action_disable "
                    "and action_archive are all PUBLIC on "
                    "account.transfer.model and therefore reachable over this "
                    "transport, and none of them was called.")
