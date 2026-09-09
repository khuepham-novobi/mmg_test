"""FG-07 — TC-DAT-002: the trial balance matches the old system.

Implements row 30.0 (P0, "Accounting reports") of the CLIENT MANUAL TESTING
GUIDELINE ``MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0.xlsx`` /
sheet ``Testing Guideline``.

The workbook's framing: *"The trial balance is the single number-for-number
proof that the accounting data came across. If it balances and matches, the
gallery's books survived the upgrade."* The workbook is equally explicit that
this is *"genuinely a manual one: you run a standard report and compare it to
a report from the old system"*, and that it *"must be run on the SAME date
range as the baseline or the comparison is meaningless"*.

Read-only by construction
-------------------------
The workbook's *State After The Test* is "Nothing changed". This module
creates no record, writes no field, and calls neither ``sweep_fg07`` nor
``cleanup`` — a sweep is itself a delete. The only server-side side effects
are the ones ``account.report`` performs on its own to render a report:
``get_report_information`` calls ``env.flush_all()`` and, on a multicurrency
database, ``_init_currency_table`` materialises a temporary currency table
(``enterprise-19.0/account_reports/models/account_report.py:5614, 1555-1566``).
Neither touches a business record.

The 3 Expected Result lines, and what each is read from
-------------------------------------------------------
1. **"Debits equal credits — the report balances."** — read from the report's
   own grand-total line. The Trial Balance's ``_custom_line_postprocessor``
   names the last line ``Total`` and stamps it
   (``enterprise-19.0/account_reports/models/
   account_trial_balance_report.py:411-430``); its Debit and Credit figures
   are the cells of the column group whose
   ``forced_options['trial_balance_column_type']`` is ``'period'``
   (:88-142). Asserted three ways — period Debit == period Credit, the
   Initial Balance grand total is 0.00, and the End Balance grand total is
   0.00 — because those three are the accountant's own definition of "the
   report balances", and the End Balance is computed by the handler as
   ``initial + debit - credit`` (:398-410).
2. **"The grand totals match the baseline exactly."** — needs figures from the
   old system, which the platform does not hold and must never invent. See
   *Documented adaptation* below.
3. **"Every account balance matches the baseline. Zero differing accounts."**
   — same. The v19 side of the comparison is captured in full: one row per
   account line of the report, selected by the ``account.account`` segment of
   the report line id (``account_report.py:2393-2454, 2481-2494``), written to
   ``TC-DAT-002-trial-balance.csv`` and, through the report's own export
   button, to ``TC-DAT-002-trial-balance.xlsx``.

How the report is driven, and why it is driven this way
-------------------------------------------------------
Three public calls, exactly the sequence the web client makes — no
leading-underscore method is reachable over ``/web/dataset/call_kw``
(``odoo/service/model.py:45-71``)::

    get_options -> re-read opts['report_id'] -> get_report_information

The re-read is mandatory, not defensive: ``get_options`` reroutes to a country
variant when one exists and returns *that* report's options
(``account_report.py:2147-2156``). ``common.run_report`` performs all three
steps and logs a reroute.

Two option values are load-bearing:

* ``hierarchy=False``. ``trial_balance.xml:11`` sets
  ``filter_hierarchy = 'by_default'``, so on any database that has
  ``account.group`` rows the lines come back as a *tree* of group lines
  (``account_report.py:1145-1155, 1158-1166``) and a per-account extraction
  would silently read group subtotals instead of accounts.
* ``unfold_all=False``. The root report line is ``foldable=False``
  (``trial_balance.xml:32``) so the per-account lines are produced anyway;
  turning unfold-all on would additionally expand every account into its
  individual journal items.

Cells are read by **expression label within a column group**, never by
position, because the handler injects an Initial Balance group before and an
End Balance group after the declared Debit/Credit pair
(``account_trial_balance_report.py:63-127``). With a single header level those
two injected groups carry ONE column labelled ``balance``
(:145-176), so this module falls back to ``debit - credit`` only if a database
somehow presents them as a pair. The value read is ``no_format`` — the float —
never ``name``, which is the formatted string, and never ``currency``, which
arrives over JSON as the repr ``"res.currency(2,)"``.

An independent cross-check the report cannot give itself
--------------------------------------------------------
The period Debit and Credit totals are recomputed straight off
``account.move.line`` with the same domain the reports engine builds
(``account_report.py:2263-2272``): ``display_type not in ('line_section',
'line_subsection', 'line_note')``, ``company_id in`` the report's own
companies, ``parent_state = 'posted'`` (:1049-1054) and the date range. If the
engine and the ledger disagree, the report — not the data — is wrong, and no
baseline is needed to say so.

The cross-check is applied to the PERIOD columns only, and only when
``options['currency_table']['type'] == 'monocurrency'`` (:1460-1494): with a
currency table in play every figure is multiplied by a rate
(``_currency_table_apply_rate``, :1497-1502) and a raw ``debit`` sum is not
the same number. It also excludes the synthetic *Undistributed Profits and
Losses* line, which is not an account at all: it aggregates P&L journal items
dated before the fiscal-year start and is added into the grand total by the
postprocessor (:6959-7020 and
``account_trial_balance_report.py:355-396``).

Documented adaptation — the Novobi baseline
-------------------------------------------
Expected Result lines 2 and 3 are comparisons against a printout from the old
system. Two paths, and the platform never invents a figure:

* **If ``data/baselines/TC-DAT-002.json`` exists**, its figures are used and
  lines 2 and 3 become real assertions. The file is the platform's own
  baseline format (``framework/baselines.py:22-39``); the ``data`` object may
  carry any of::

      {"date_from": "2024-01-01", "date_to": "2024-12-31",
       "total_initial": 0.0, "total_debit": 0.0, "total_credit": 0.0,
       "total_end": 0.0,
       "accounts": {"101401": {"initial": 0.0, "debit": 0.0,
                               "credit": 0.0, "end": 0.0}}}

  Every key is optional and only the keys present are compared. ``balance`` is
  accepted as an alias of ``end``, and an account may be given as a bare
  number, which is read as its End Balance. The four column names map
  one-for-one onto the four columns the v19 report prints, so the person
  transcribing the printout does not have to interpret anything.
* **If it does not exist**, every captured figure is printed into the log and
  written to CSV, and the comparison is named as a RESIDUAL MANUAL STEP with
  the actual numbers in the message — never silently dropped, never faked.

The date range is settled the same way. The workbook says to use the exact
range printed on the baseline; when the baseline file supplies
``date_from``/``date_to`` those are used verbatim. Otherwise the range is the
**full span of posted journal items** in the acting company — deterministic,
independent of today's date (rule 5), and the widest range a completeness
check can be run over — and the residual note prints it so the human can
re-run against the baseline's own range.

Findings this case is built to surface
--------------------------------------
* The v19 Trial Balance prints an **Undistributed Profits and Losses** line
  that most legacy trial balances have no counterpart for. It is not an
  account, it carries no account code, and it is added into the grand total
  (``account_report.py:7002-7020``). A tester diffing account by account will
  otherwise report it as an account that appeared out of nowhere. It is
  logged as a FINDING with its own figures and excluded from the ledger
  cross-check.
* ``account.account.code`` is company-dependent in v19
  (``addons/account/models/account_account.py:39-40, 97``), so every read in
  this module pins ``allowed_company_ids`` through ``common.company_ctx``. An
  unpinned read does not merely widen the population — it can return a
  different code for the same account.
* The XLSX export is fetched over HTTP rather than over ``call_kw``, because
  the RPC layer's ``json_default`` turns ``bytes`` into ``str`` and silently
  corrupts a binary payload (``common.post_account_reports_export``). A
  failing export is reported as a FINDING and not as this case's verdict: the
  workbook offers the export button as a convenience in step 5, not as an
  Expected Result.
"""
from __future__ import annotations

import csv

from adapters.base import OdooRPCError
from framework.baselines import baseline_path, load_baseline
from framework.registry import test_case
from tests.fg07.common import (REPORT_LABEL, REPORT_MENU_XMLID,
                               REPORT_SECTION_XMLID, WORKFLOW, WORKFLOW_NAME,
                               acting_company, cell_value, column_index,
                               company_ctx, finding, has_group, m2o_id,
                               menu_by_xmlid, money,
                               post_account_reports_export, report_ref,
                               require_account_reports, residual_manual_step,
                               run_report, trace, trial_balance_column_groups)

TC_ID = "TC-DAT-002"
REPORT_KEY = "trial_balance"

ACCOUNTS_CSV = "TC-DAT-002-trial-balance.csv"
TOTALS_CSV = "TC-DAT-002-grand-totals.csv"
DIFF_CSV = "TC-DAT-002-baseline-differences.csv"
XLSX_NAME = "TC-DAT-002-trial-balance.xlsx"
CSV_LIMIT = 20000

# Journal-item rows that carry no figures. The reports engine excludes exactly
# these three (account_report.py:2264), so the cross-check must too or it
# would count layout rows as ledger rows.
LAYOUT_DISPLAY_TYPES = ("line_section", "line_subsection", "line_note")

# Any one of these is enough to see Accounting > Reporting > Ledgers
# (account_reports/data/menuitems.xml:6-7 restricts the leaf menu to the first
# two; group_account_user implies group_account_basic).
READER_GROUPS = ("account.group_account_readonly",
                 "account.group_account_basic",
                 "account.group_account_user")

# The three column groups the Trial Balance always presents, keyed by the
# handler's own trial_balance_column_type
# (account_trial_balance_report.py:106-141).
INITIAL, PERIOD, END = "initial_balance", "period", "end_balance"


# --------------------------------------------------------------- line ids
def _line_tail(line_id) -> tuple:
    """``(markup, model, value)`` of the LAST segment of a report line id.

    Report line ids are ``markup~model~value`` patterns joined by ``|``, one
    per level of hierarchy (``account_report.py:2393-2411, 2447-2454``).
    Parsing the tail is how a line is classified without guessing from its
    ``name``, which is translated: the grand-total line is literally named
    ``_("Total")`` (``account_trial_balance_report.py:428``), so a database
    running in French would break a name match.
    """
    segment = str(line_id or "").split("|")[-1]
    parts = segment.rsplit("~", 2)
    if len(parts) != 3:
        return "", "", ""
    return parts[0], parts[1], parts[2]


def _is_total(line: dict) -> bool:
    """The grand-total line, whichever branch the handler took.

    With ``totals_below_sections`` on, the total-below line already carries
    the ``total`` markup; with it off, the handler moves the root line to the
    end and appends that markup to its id
    (``account_trial_balance_report.py:411-430``). Both branches therefore end
    in ``total``.
    """
    return _line_tail(line.get("id"))[0] == "total"


def _is_account(line: dict) -> bool:
    return _line_tail(line.get("id"))[1] == "account.account"


def _account_id(line: dict) -> int:
    try:
        return int(_line_tail(line.get("id"))[2])
    except (TypeError, ValueError):
        return 0


def _is_undistributed(line: dict) -> bool:
    """The synthetic Undistributed Profits and Losses line.

    ``account_report.py:6998`` builds its id with the markup
    ``undistributed_profits_losses``. It is not an account and has no code.
    """
    return _line_tail(line.get("id"))[0] == "undistributed_profits_losses"


# ------------------------------------------------------------------ cells
def _amount(opts: dict, line: dict, group_key: str, label: str):
    """One cell's ``no_format`` float, or None when the column is absent."""
    if not group_key:
        return None
    value = cell_value(line, column_index(opts, label, group_key))
    if isinstance(value, (int, float)):
        return money(value)
    return None


def _balance_of(opts: dict, line: dict, group_key: str) -> float:
    """The signed balance of one column group on one line.

    The Initial Balance and End Balance groups normally hold a single column
    labelled ``balance``; they hold a Debit/Credit pair instead when the
    report has more than one header level
    (``account_trial_balance_report.py:145-152``). Handling both means a
    horizontally grouped database reports figures rather than blanks.
    """
    value = _amount(opts, line, group_key, "balance")
    if value is not None:
        return value
    debit = _amount(opts, line, group_key, "debit") or 0.0
    credit = _amount(opts, line, group_key, "credit") or 0.0
    return money(debit - credit)


# --------------------------------------------------------------- the ledger
def _group_by_account(ctx, domain: list, context: dict) -> tuple:
    """The ledger side: ``({account_id: {debit, credit, balance, rows}},
    method)``.

    ``formatted_read_group`` is the v19 public grouping entry point
    (``addons/web/models/models.py:800-813``); ``read_group`` still exists but
    is deprecated (``odoo/orm/models.py:2746-2749``). Both are tried so a
    database whose ``web`` module is in an odd state still yields figures
    instead of turning a product question into an AUTOMATION_ERROR.
    """
    rpc = ctx.adapter.rpc
    out: dict = {}
    try:
        rows = rpc.call("account.move.line", "formatted_read_group", domain,
                        ["account_id"],
                        ["debit:sum", "credit:sum", "balance:sum", "__count"],
                        context=context) or []
        for row in rows:
            account_id = m2o_id(row.get("account_id"))
            if not account_id:
                continue
            out[account_id] = {"debit": money(row.get("debit:sum")),
                               "credit": money(row.get("credit:sum")),
                               "balance": money(row.get("balance:sum")),
                               "rows": int(row.get("__count") or 0)}
        return out, "formatted_read_group"
    except OdooRPCError as exc:
        ctx.log(f"formatted_read_group unavailable on account.move.line "
                f"({exc}) — falling back to the deprecated read_group")
    try:
        rows = rpc.read_group("account.move.line", domain,
                              ["debit:sum", "credit:sum", "balance:sum"],
                              ["account_id"], context=context) or []
    except OdooRPCError as exc:
        ctx.log(f"could not group account.move.line by account ({exc}) — the "
                f"independent ledger cross-check cannot run")
        return {}, ""
    for row in rows:
        account_id = m2o_id(row.get("account_id"))
        if not account_id:
            continue
        out[account_id] = {
            "debit": money(row.get("debit")),
            "credit": money(row.get("credit")),
            "balance": money(row.get("balance")),
            "rows": int(row.get("account_id_count")
                        or row.get("__count") or 0),
        }
    return out, "read_group"


def _posted_span(ctx, company: dict) -> tuple:
    """``(first, last)`` posting date of the company's posted journal items.

    Used as the date range when the baseline file does not name one. It is a
    property of the data rather than of the clock, so the case is repeatable
    (AUTOMATION_CONVENTIONS.md:31-35 — "no time-dependent values").
    """
    rpc = ctx.adapter.rpc
    domain = [("parent_state", "=", "posted"),
              ("company_id", "=", company["id"]),
              ("display_type", "not in", list(LAYOUT_DISPLAY_TYPES))]
    context = company_ctx(company)
    try:
        first = rpc.search_read("account.move.line", domain, ["date"],
                                order="date asc", limit=1, context=context)
        last = rpc.search_read("account.move.line", domain, ["date"],
                               order="date desc", limit=1, context=context)
    except OdooRPCError as exc:
        ctx.log(f"could not read the posted-entry date span ({exc})")
        return "", ""
    if not first or not last:
        return "", ""
    return str(first[0].get("date") or ""), str(last[0].get("date") or "")


# ---------------------------------------------------------------- baseline
def _baseline_accounts(data: dict) -> dict:
    """``{account code: {initial, debit, credit, end}}`` out of the baseline.

    Tolerant on purpose: a value may be a mapping of the four printed columns,
    or a bare number, which is read as the End Balance — the column a legacy
    trial balance most often prints as "Balance". Any key the file omits stays
    ``None`` and is not compared, so a partial transcription is still useful
    rather than being rejected wholesale.
    """
    raw = data.get("accounts")
    if isinstance(raw, dict):
        items = list(raw.items())
    elif isinstance(raw, list):
        items = [(row.get("code"), row) for row in raw
                 if isinstance(row, dict)]
    else:
        return {}
    out: dict = {}
    for code, value in items:
        if code in (None, ""):
            continue
        key = str(code).strip()
        if isinstance(value, dict):
            end = value.get("end")
            if end is None:
                end = value.get("balance")
            out[key] = {
                "initial": None if value.get("initial") is None
                else money(value.get("initial")),
                "debit": None if value.get("debit") is None
                else money(value.get("debit")),
                "credit": None if value.get("credit") is None
                else money(value.get("credit")),
                "end": None if end is None else money(end),
            }
        elif isinstance(value, (int, float)):
            out[key] = {"initial": None, "debit": None, "credit": None,
                        "end": money(value)}
    return out


@test_case(
    id="TEST-FG07-DAT-002",
    name="The trial balance matches the old system",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module="account, account_reports",
    priority="P0",
    kind="DATA",
    order=701,
    description="Read-only run of Accounting > Reporting > Ledgers > Trial "
                "Balance over a fixed date range: the report is proven to "
                "balance (debits equal credits, initial and end grand totals "
                "zero), its period figures are reconciled account by account "
                "against account.move.line, and the whole report is captured "
                "to CSV and XLSX so the account-by-account comparison against "
                "the Novobi baseline is a tick-off. Creates nothing.",
    traceability=trace("TC-DAT-002"))
def test_dat_002(ctx):
    rpc = ctx.adapter.rpc
    # Accumulators are declared BEFORE the try: the evidence block runs from
    # `finally` and must never raise a NameError over a step that an earlier
    # assertion failure skipped — that would replace a real FAILED verdict
    # with an AUTOMATION_ERROR (AUTOMATION_CONVENTIONS.md:69-71).
    account_rows: list[dict] = []
    total_rows: list[tuple] = []
    diff_rows: list[tuple] = []
    residual: list[str] = []

    with ctx.step("Preconditions (workbook): TC-SMK-015 has passed, the "
                  "Enterprise reports engine is live, and Accounting > "
                  "Reporting is reachable"):
        # require_account_reports probes ir.module.module — NOT
        # model_exists('account.report'), which is True on a Community-only
        # database that carries no report engine at all
        # (tests/fg07/common.py:38-48).
        require_account_reports(ctx)
        company = acting_company(ctx)
        context = company_ctx(company)
        ctx.log(f"acting company #{company['id']} {company['name']!r} — "
                f"company currency {company['currency_name']}")
        report_id = report_ref(ctx, REPORT_KEY)
        ctx.log(f"account.report {REPORT_KEY!r} resolves to #{report_id}")

    try:
        with ctx.step("Step 1: Accounting > Reporting > Ledgers > Trial "
                      "Balance is where the workbook says it is"):
            readable = [group for group in READER_GROUPS
                        if has_group(ctx, group)]
            ctx.log(f"accounting groups held by the runner user: "
                    f"{readable or 'none'}")
            menu = menu_by_xmlid(ctx, REPORT_MENU_XMLID[REPORT_KEY])
            section = menu_by_xmlid(ctx, REPORT_SECTION_XMLID[REPORT_KEY])
            ctx.log(f"leaf menu: {menu or '(not visible)'}")
            ctx.log(f"section menu: {section or '(not visible)'}")
            if not readable:
                # ir.ui.menu is group-filtered, so an empty read here would
                # mean "this user may not see it", not "it is gone". Reporting
                # that as a missing menu would be a false defect.
                residual.append(
                    "the runner user holds none of "
                    f"{', '.join(READER_GROUPS)}, so the Trial Balance menu "
                    "could not be checked from this session. Open Accounting "
                    "> Reporting > Ledgers as the gallery's accountant and "
                    "confirm the entry is present.")
                ctx.log("menu placement not asserted — the runner user has no "
                        "accounting reader group, and ir.ui.menu is "
                        "group-filtered")
            else:
                ctx.check_true(
                    f"{REPORT_LABEL[REPORT_KEY]} exists as a menu entry "
                    f"and is not archived",
                    bool(menu) and menu.get("active"),
                    actual_desc=f"menu={menu.get('name') or '(unresolved)'!r} "
                                f"active={menu.get('active')}")
                ctx.check("The Trial Balance entry hangs under the Ledgers "
                          "section, as the workbook's navigation says",
                          section.get("id"), menu.get("parent_id"))

        with ctx.step("Step 2 (workbook): set the date range to exactly the "
                      "range printed on the Novobi baseline"):
            stored = load_baseline(TC_ID) or {}
            baseline = stored.get("data") or {}
            if stored:
                ctx.log(f"baseline file found: {baseline_path(TC_ID)} — "
                        f"captured {stored.get('captured_at')!r} from "
                        f"{stored.get('captured_env')!r}/"
                        f"{stored.get('captured_db')!r}")
            else:
                ctx.log(f"no baseline file at {baseline_path(TC_ID)} — "
                        f"Expected Result lines 2 and 3 become residual "
                        f"manual steps, and nothing is invented in their "
                        f"place")
            date_from = str(baseline.get("date_from") or "")
            date_to = str(baseline.get("date_to") or "")
            range_source = "the Novobi baseline file"
            if not (date_from and date_to):
                date_from, date_to = _posted_span(ctx, company)
                range_source = ("the full span of posted journal items in "
                                "this company")
            if not (date_from and date_to):
                # No posted journal item at all: the trial balance would
                # balance vacuously at 0.00 == 0.00 and prove nothing. That is
                # a precondition failure, not a product defect.
                ctx.blocked(
                    "this company has no posted journal item, so there is no "
                    "trial balance to compare. Either the accounting data did "
                    "not come across at all — in which case TC-SMK-015 should "
                    "have caught it and must be re-run first — or the runner "
                    "user is acting as the wrong company "
                    f"(currently #{company['id']} {company['name']!r})")
            ctx.log(f"date range {date_from} .. {date_to}, taken from "
                    f"{range_source}")

            options = {
                "date": {"mode": "range", "filter": "custom",
                         "date_from": date_from, "date_to": date_to},
                # by_default hierarchy would turn the lines into a tree of
                # account.group rows (trial_balance.xml:11) and a per-account
                # read would silently pick up group subtotals.
                "hierarchy": False,
                # the root line is foldable=False, so accounts appear anyway;
                # unfold_all would additionally expand every account into its
                # individual journal items.
                "unfold_all": False,
                # posted entries only — the same population the workbook's
                # baseline was exported from.
                "all_entries": False,
            }
            try:
                opts, info = run_report(ctx, report_id, options, company)
            except OdooRPCError as exc:
                opts, info = {}, {}
                ctx.check_true(
                    "The Trial Balance opens for the requested date range "
                    "(account.report.get_options / get_report_information)",
                    False,
                    actual_desc=f"the reports engine raised: {exc}")
            echoed = {"date_from": (opts.get("date") or {}).get("date_from"),
                      "date_to": (opts.get("date") or {}).get("date_to")}
            # A silent fallback to the report's default_opening_date_filter
            # ('this_month', trial_balance.xml:14) would produce a perfectly
            # plausible report for the wrong period, which is the one failure
            # mode this case cannot afford.
            ctx.check("The report is reading exactly the date range that was "
                      "asked for (options['date'])",
                      {"date_from": date_from, "date_to": date_to}, echoed)

        with ctx.step("Steps 3-6 (capture): read the grand totals and every "
                      "account balance off the report"):
            groups = trial_balance_column_groups(opts)
            ctx.log(f"column groups by trial_balance_column_type: {groups}")
            missing_groups = [name for name in (INITIAL, PERIOD, END)
                              if not groups.get(name)]
            ctx.check("The Trial Balance presents its Initial Balance, Debit "
                      "and Credit, and End Balance column groups",
                      [], missing_groups)

            lines = info.get("lines") or []
            ctx.log(f"the report returned {len(lines)} line(s)")
            total_line = next((line for line in reversed(lines)
                               if _is_total(line)), {})
            ctx.check_true(
                "The report produced a grand-total line at the foot of the "
                "debit and credit columns",
                bool(total_line),
                actual_desc=f"{len(lines)} line(s) returned; last line "
                            f"id={((lines or [{}])[-1]).get('id')!r} "
                            f"name={((lines or [{}])[-1]).get('name')!r}")

            total_initial = _balance_of(opts, total_line, groups.get(INITIAL))
            total_debit = _amount(opts, total_line, groups.get(PERIOD),
                                  "debit") or 0.0
            total_credit = _amount(opts, total_line, groups.get(PERIOD),
                                   "credit") or 0.0
            total_end = _balance_of(opts, total_line, groups.get(END))
            ctx.log(f"GRAND TOTALS {date_from}..{date_to} — "
                    f"Initial Balance {total_initial:,.2f} | "
                    f"Debit {total_debit:,.2f} | Credit {total_credit:,.2f} | "
                    f"End Balance {total_end:,.2f}")
            for label, value in (("initial", total_initial),
                                 ("debit", total_debit),
                                 ("credit", total_credit),
                                 ("end", total_end)):
                total_rows.append(("Total", label, value))

            # The synthetic Undistributed Profits and Losses line: not an
            # account, no code, and folded into the grand total by the
            # postprocessor. It has to be named for the human doing the
            # account-by-account diff, and kept out of the ledger cross-check.
            undist_debit = undist_credit = 0.0
            for line in lines:
                if not _is_undistributed(line):
                    continue
                undist_debit += _amount(opts, line, groups.get(PERIOD),
                                        "debit") or 0.0
                undist_credit += _amount(opts, line, groups.get(PERIOD),
                                         "credit") or 0.0
                row = {"code": "", "name": line.get("name") or "",
                       "account_type": "(not an account)",
                       "initial": _balance_of(opts, line,
                                              groups.get(INITIAL)),
                       "debit": _amount(opts, line, groups.get(PERIOD),
                                        "debit") or 0.0,
                       "credit": _amount(opts, line, groups.get(PERIOD),
                                         "credit") or 0.0,
                       "end": _balance_of(opts, line, groups.get(END)),
                       "ledger_debit": "", "ledger_credit": "",
                       "ledger_rows": ""}
                account_rows.append(row)
                finding(ctx,
                        f"the v19 Trial Balance prints a synthetic "
                        f"{line.get('name')!r} line (initial "
                        f"{row['initial']:,.2f}, debit {row['debit']:,.2f}, "
                        f"credit {row['credit']:,.2f}, end "
                        f"{row['end']:,.2f}). It is not an account and has no "
                        f"account code: it aggregates profit-and-loss journal "
                        f"items dated before the fiscal-year start and is "
                        f"added into the grand total "
                        f"(enterprise-19.0/account_reports/models/"
                        f"account_report.py:6959-7020). Most legacy trial "
                        f"balances have no counterpart for it — do NOT report "
                        f"it as an account that appeared out of nowhere")

            # One read for every account the report printed, with the company
            # pinned: account.account.code is company-dependent in v19
            # (addons/account/models/account_account.py:39-40, 97).
            report_lines = [line for line in lines if _is_account(line)]
            account_ids = [aid for aid in
                           (_account_id(line) for line in report_lines) if aid]
            meta: dict = {}
            if account_ids:
                try:
                    for row in rpc.call("account.account", "read", account_ids,
                                        fields=["code", "name",
                                                "account_type"],
                                        context=context) or []:
                        meta[row["id"]] = row
                except OdooRPCError as exc:
                    ctx.log(f"could not read the account codes ({exc}) — the "
                            f"CSV falls back to the report's own line labels")
            ctx.log(f"the report printed {len(report_lines)} account line(s)")

            sum_debit = sum_credit = sum_initial = sum_end = 0.0
            for line in report_lines:
                account_id = _account_id(line)
                row_meta = meta.get(account_id, {})
                row = {
                    "code": str(row_meta.get("code") or ""),
                    "name": str(row_meta.get("name")
                                or line.get("name") or ""),
                    "account_type": str(row_meta.get("account_type") or ""),
                    "initial": _balance_of(opts, line, groups.get(INITIAL)),
                    "debit": _amount(opts, line, groups.get(PERIOD),
                                     "debit") or 0.0,
                    "credit": _amount(opts, line, groups.get(PERIOD),
                                      "credit") or 0.0,
                    "end": _balance_of(opts, line, groups.get(END)),
                    "account_id": account_id,
                }
                sum_initial += row["initial"]
                sum_debit += row["debit"]
                sum_credit += row["credit"]
                sum_end += row["end"]
                account_rows.append(row)
            sum_debit, sum_credit = money(sum_debit), money(sum_credit)
            sum_initial, sum_end = money(sum_initial), money(sum_end)
            ctx.log(f"sum of the account lines — Initial {sum_initial:,.2f} | "
                    f"Debit {sum_debit:,.2f} | Credit {sum_credit:,.2f} | "
                    f"End {sum_end:,.2f}; of which the Undistributed line "
                    f"contributes Debit {money(undist_debit):,.2f} / Credit "
                    f"{money(undist_credit):,.2f} to the grand total")

            ctx.check_true(
                "The report printed at least one account line, so there is "
                "something to compare against the baseline",
                bool(report_lines),
                actual_desc=f"{len(report_lines)} account line(s) over "
                            f"{date_from}..{date_to}")

        with ctx.step("Step 5 (workbook): use the report's export button to "
                      "get the spreadsheet"):
            # Offered by the workbook as a convenience, so a failure here is a
            # FINDING and not this case's verdict. The bytes must come over
            # HTTP: call_kw's json_default decodes bytes to str and would
            # silently corrupt the XLSX.
            status, content_type, disposition, body = \
                post_account_reports_export(ctx, opts, "export_to_xlsx")
            ctx.log(f"POST /account_reports export_to_xlsx -> HTTP {status}, "
                    f"{len(body)} byte(s), Content-Type={content_type!r}, "
                    f"Content-Disposition={disposition!r}")
            if status == 200 and body:
                path = ctx.artifacts_dir / XLSX_NAME
                try:
                    path.write_bytes(body)
                    ctx.add_artifact(path, "log", XLSX_NAME)
                    ctx.log(f"wrote {len(body)} byte(s) to {XLSX_NAME} — this "
                            f"is the file the workbook's sign-off refers to")
                except OSError as exc:
                    finding(ctx, f"the XLSX export downloaded but could "
                                 f"not be written to {path} ({exc})")
            else:
                finding(ctx,
                        f"the Trial Balance XLSX export returned HTTP "
                        f"{status} with {len(body)} byte(s). Workbook step 5 "
                        f"offers it as the easy way to do the "
                        f"account-by-account comparison; use "
                        f"{ACCOUNTS_CSV} instead, which carries the same "
                        f"figures, and report the broken export separately")

        with ctx.step("Step 3 / Expected line 1: the grand totals of the "
                      "debit and credit columns are equal — the report "
                      "balances"):
            ctx.check("Debits equal credits at the foot of the Trial Balance "
                      "(period Debit total vs period Credit total)",
                      money(total_debit), money(total_credit))
            # The other two halves of "the report balances". The End Balance
            # grand total is computed by the handler as
            # initial + debit - credit (account_trial_balance_report.py:
            # 398-410), so a non-zero value here means the books did not
            # balance either at the start of the period or across it.
            ctx.check("The Initial Balance grand total is zero — the books "
                      "balanced at the start of the period", 0.0,
                      money(total_initial))
            ctx.check("The End Balance grand total is zero — the books still "
                      "balance at the end of the period", 0.0,
                      money(total_end))
            ctx.check("The grand total equals the sum of the account lines "
                      "plus the Undistributed Profits and Losses line "
                      "(period Debit)",
                      money(total_debit), money(sum_debit + undist_debit))
            ctx.check("The grand total equals the sum of the account lines "
                      "plus the Undistributed Profits and Losses line "
                      "(period Credit)",
                      money(total_credit), money(sum_credit + undist_credit))

        with ctx.step("Independent cross-check (no baseline needed): the "
                      "report's period figures against account.move.line"):
            currency_mode = str((opts.get("currency_table") or {}).get("type")
                                or "")
            company_ids = [row.get("id") for row
                           in (opts.get("companies") or [])
                           if row.get("id")] or [company["id"]]
            ctx.log(f"currency table type {currency_mode!r}; report companies "
                    f"{company_ids}")
            ledger: dict = {}
            method = ""
            if currency_mode == "monocurrency":
                domain = [("parent_state", "=", "posted"),
                          ("display_type", "not in",
                           list(LAYOUT_DISPLAY_TYPES)),
                          ("company_id", "in", company_ids),
                          ("date", ">=", date_from),
                          ("date", "<=", date_to)]
                ledger, method = _group_by_account(ctx, domain, context)
                ctx.log(f"grouped {len(ledger)} account(s) off "
                        f"account.move.line via {method or 'nothing'} over "
                        f"{domain}")

            if currency_mode != "monocurrency":
                # With a currency table in play every figure is multiplied by
                # a rate (_currency_table_apply_rate), so a raw debit sum is
                # simply a different number and comparing them would report a
                # correct report as broken.
                ctx.log(f"the ledger cross-check is SKIPPED: the report is "
                        f"running with a {currency_mode!r} currency table, so "
                        f"its figures are rate-converted and a raw "
                        f"account.move.line sum is not the same quantity "
                        f"(enterprise-19.0/account_reports/models/"
                        f"account_report.py:1460-1502)")
                residual.append(
                    f"the independent ledger cross-check did not run because "
                    f"this database's currency table type is "
                    f"{currency_mode!r} rather than 'monocurrency'. The "
                    f"report's own figures are still in {ACCOUNTS_CSV}; the "
                    f"debits-equal-credits check above was still made.")
            elif not method:
                # Neither grouping call worked. Comparing the report against
                # an empty ledger would flag every account as differing —
                # a transport failure dressed up as a product defect.
                ctx.log("the ledger cross-check is SKIPPED: neither "
                        "formatted_read_group nor read_group could be called "
                        "on account.move.line (see the errors above)")
                residual.append(
                    "the independent ledger cross-check could not run: this "
                    "session could group account.move.line with neither "
                    "formatted_read_group nor read_group. The report's own "
                    f"figures in {ACCOUNTS_CSV} are unaffected, and the "
                    "debits-equal-credits check above was still made.")
            else:
                ledger_debit = money(sum(row["debit"]
                                         for row in ledger.values()))
                ledger_credit = money(sum(row["credit"]
                                          for row in ledger.values()))
                ctx.log(f"ledger totals — Debit {ledger_debit:,.2f} | Credit "
                        f"{ledger_credit:,.2f} (this EXCLUDES the report's "
                        f"Initial Balance and End Balance columns and the "
                        f"synthetic Undistributed Profits and Losses line, "
                        f"which is not an account)")
                if not ledger:
                    ctx.log("no posted journal item in the range — every "
                            "account line on the report should therefore show "
                            "0.00 Debit and 0.00 Credit")
                # Offender lists rather than booleans: when more than one
                # account disagrees the failure must name every one of them.
                per_account = []
                for row in account_rows:
                    account_id = row.get("account_id")
                    if not account_id:
                        continue
                    seen = ledger.get(account_id) or {"debit": 0.0,
                                                      "credit": 0.0,
                                                      "rows": 0}
                    row["ledger_debit"] = seen["debit"]
                    row["ledger_credit"] = seen["credit"]
                    row["ledger_rows"] = seen.get("rows", 0)
                    if (money(row["debit"]) != money(seen["debit"])
                            or money(row["credit"]) != money(seen["credit"])):
                        per_account.append(
                            f"{row['code'] or account_id} {row['name']}: "
                            f"report {row['debit']:,.2f}/{row['credit']:,.2f} "
                            f"vs ledger {seen['debit']:,.2f}/"
                            f"{seen['credit']:,.2f}")
                for account_id, seen in ledger.items():
                    if any(row.get("account_id") == account_id
                           for row in account_rows):
                        continue
                    per_account.append(
                        f"account #{account_id}: the ledger holds "
                        f"{seen['debit']:,.2f}/{seen['credit']:,.2f} over "
                        f"{seen.get('rows', 0)} posted item(s) but the report "
                        f"printed no line for it")
                if per_account:
                    ctx.log(f"{len(per_account)} account(s) disagree between "
                            f"the report and the ledger; the assertion below "
                            f"names the first 50 and all of them are in "
                            f"{ACCOUNTS_CSV} (compare the debit/credit "
                            f"columns against ledger_debit/ledger_credit)")
                ctx.check("Every account's Debit and Credit on the report "
                          "equals the sum of its posted journal items over "
                          "the same range", [], per_account[:50])
                ctx.check("The report's period Debit total equals the "
                          "ledger's", ledger_debit, money(sum_debit))
                ctx.check("The report's period Credit total equals the "
                          "ledger's", ledger_credit, money(sum_credit))

        with ctx.step("Step 4 / Expected line 2: the grand totals match the "
                      "baseline exactly"):
            wanted = {"initial": baseline.get("total_initial"),
                      "debit": baseline.get("total_debit"),
                      "credit": baseline.get("total_credit"),
                      "end": baseline.get("total_end")}
            captured = {"initial": money(total_initial),
                        "debit": money(total_debit),
                        "credit": money(total_credit),
                        "end": money(total_end)}
            supplied = {key: money(value) for key, value in wanted.items()
                        if value is not None}
            if supplied:
                for key, value in supplied.items():
                    total_rows.append(("Novobi baseline", key, value))
                    if money(captured[key]) != value:
                        diff_rows.append(("(grand total)", key, value,
                                          captured[key],
                                          money(captured[key] - value)))
                # A PARTIAL transcription must not silently shrink the
                # workbook's Expected Result line 2 to whichever columns
                # happened to be typed in. Whatever the baseline file left out
                # is still a comparison the workbook demands, so it is handed
                # to the human with the captured figure in it rather than
                # dropped. Queued BEFORE the assertion below, because
                # ctx.check raises and anything appended after it would never
                # reach the residual block.
                omitted = [key for key in ("initial", "debit", "credit", "end")
                           if key not in supplied]
                if omitted:
                    residual.append(
                        "EXPECTED RESULT LINE 2 (partly) — the baseline file "
                        f"{baseline_path(TC_ID)} names "
                        f"{sorted(supplied)} but not {omitted}, so those "
                        f"columns were captured and NOT compared. Tick them "
                        f"off against the Novobi printout for "
                        f"{date_from} .. {date_to} by hand: "
                        + "; ".join(f"{key} {captured[key]:,.2f}"
                                    for key in omitted)
                        + f". Add them to the baseline file as "
                          f"total_{'/total_'.join(omitted)} to have the "
                          f"platform assert them on the next run.")
                ctx.check(
                    "The Trial Balance grand totals match the Novobi baseline "
                    "exactly",
                    supplied,
                    {key: captured[key] for key in supplied})
            else:
                residual.append(
                    "EXPECTED RESULT LINE 2 — compare these grand totals, for "
                    f"{date_from} .. {date_to}, against the Novobi baseline "
                    f"printed for the SAME range (the workbook: 'It must be "
                    f"run on the SAME date range as the baseline or the "
                    f"comparison is meaningless'): Initial Balance "
                    f"{money(total_initial):,.2f}; Debit "
                    f"{money(total_debit):,.2f}; Credit "
                    f"{money(total_credit):,.2f}; End Balance "
                    f"{money(total_end):,.2f}; "
                    f"{len([r for r in account_rows if r.get('code')])} "
                    f"account line(s). The date range used here came from "
                    f"{range_source}. To have the platform assert this on the "
                    f"next run, drop the baseline figures into "
                    f"{baseline_path(TC_ID)} as "
                    '{"data": {"date_from": …, "date_to": …, "total_debit": …,'
                    ' "total_credit": …}}.')

        with ctx.step("Steps 5-7 / Expected line 3: every account balance "
                      "matches the baseline, zero differing accounts"):
            wanted_accounts = _baseline_accounts(baseline)
            if wanted_accounts:
                by_code = {}
                for row in account_rows:
                    if row.get("code"):
                        by_code[str(row["code"]).strip()] = row
                offenders = []
                net = 0.0
                for code in sorted(set(by_code) | set(wanted_accounts)):
                    want = wanted_accounts.get(code)
                    got = by_code.get(code)
                    if want is None:
                        # Present in v19, absent from the baseline. Real, and
                        # exactly what "mark every account whose balance
                        # differs" means in the other direction.
                        offenders.append(
                            f"{code} {got['name']}: not on the baseline; v19 "
                            f"End Balance {got['end']:,.2f}")
                        diff_rows.append((code, "end", "", got["end"],
                                          got["end"]))
                        net += got["end"]
                        continue
                    if got is None:
                        offenders.append(
                            f"{code}: on the baseline (End Balance "
                            f"{want['end']}) but the v19 report printed no "
                            f"line for it")
                        diff_rows.append((code, "end", want["end"], "",
                                          money(-(want["end"] or 0.0))))
                        net -= (want["end"] or 0.0)
                        continue
                    for key in ("initial", "debit", "credit", "end"):
                        if want[key] is None:
                            continue
                        if money(got[key]) != money(want[key]):
                            delta = money(got[key] - want[key])
                            offenders.append(
                                f"{code} {got['name']} [{key}]: baseline "
                                f"{want[key]:,.2f} vs v19 {got[key]:,.2f} "
                                f"(difference {delta:+,.2f})")
                            diff_rows.append((code, key, want[key], got[key],
                                              delta))
                            if key == "end":
                                net += delta
                # Workbook step 7: do the differences cancel out, or is there
                # a net figure? The two answers point at different failures,
                # and the workbook's If It Fails asks for the distinction
                # explicitly, so it is computed rather than left to the human.
                if offenders:
                    residual.append(
                        f"WORKBOOK STEP 7 — the End Balance differences net "
                        f"to {money(net):+,.2f}. "
                        + ("They cancel out, which points at money moved "
                           "BETWEEN accounts (a mapping problem)."
                           if money(net) == 0.0 else
                           "They leave a net figure, which points at money "
                           "CREATED OR LOST (a data problem).")
                        + f" The full list is in {DIFF_CSV}.")
                ctx.check("Every account balance matches the Novobi baseline "
                          "— zero differing accounts", [], offenders[:200])
            else:
                residual.append(
                    "EXPECTED RESULT LINE 3 — work down "
                    f"{ACCOUNTS_CSV} (and {XLSX_NAME}, the report's own "
                    f"export) account by account against the Novobi baseline "
                    f"and mark every account whose balance differs, and by "
                    f"how much. The CSV carries one row per account with the "
                    f"four columns the report prints — Initial Balance, "
                    f"Debit, Credit, End Balance — plus the posted-journal-"
                    f"item Debit/Credit each figure was reconciled against. "
                    f"Then add the differences up (workbook step 7): if they "
                    f"cancel out, money moved BETWEEN accounts; if they leave "
                    f"a net figure, money was CREATED OR LOST. The row with "
                    f"an empty code is the v19 'Undistributed Profits and "
                    f"Losses' line and has no baseline counterpart — do not "
                    f"count it as a difference.")
                residual.append(
                    "to have the platform assert Expected Result line 3 on "
                    f"the next run, transcribe the baseline into "
                    f"{baseline_path(TC_ID)} as "
                    '{"data": {"accounts": {"<code>": {"initial": …, '
                    '"debit": …, "credit": …, "end": …}}}} — every key is '
                    "optional and only the keys present are compared.")
    finally:
        with ctx.step("Evidence: write the trial balance, the grand totals "
                      "and any baseline differences"):
            for name, header, rows in (
                (ACCOUNTS_CSV,
                 ["code", "name", "account_type", "initial", "debit",
                  "credit", "end", "ledger_debit", "ledger_credit",
                  "ledger_rows"],
                 [[row.get("code", ""), row.get("name", ""),
                   row.get("account_type", ""), row.get("initial", ""),
                   row.get("debit", ""), row.get("credit", ""),
                   row.get("end", ""), row.get("ledger_debit", ""),
                   row.get("ledger_credit", ""), row.get("ledger_rows", "")]
                  for row in account_rows[:CSV_LIMIT]]),
                (TOTALS_CSV, ["line", "column", "amount"],
                 total_rows[:CSV_LIMIT]),
                (DIFF_CSV, ["code", "column", "baseline", "v19", "difference"],
                 diff_rows[:CSV_LIMIT]),
            ):
                if not rows and name == DIFF_CSV:
                    # No baseline, or no difference: an empty differences file
                    # would read as "the comparison was made and found
                    # nothing", which is not what happened.
                    continue
                path = ctx.artifacts_dir / name
                try:
                    with path.open("w", newline="", encoding="utf-8") as fh:
                        writer = csv.writer(fh)
                        writer.writerow(header)
                        writer.writerows(rows)
                    ctx.add_artifact(path, "log", name)
                    ctx.log(f"wrote {len(rows)} row(s) to {name}")
                except OSError as exc:
                    ctx.log(f"could not write {name} ({exc}) — the figures "
                            f"above are still in this log")
            for note in residual:
                residual_manual_step(ctx, note)
            ctx.log("NOTHING WAS CREATED OR MODIFIED by this case — the "
                    "workbook's State After The Test is 'Nothing changed', so "
                    "no sweep and no cleanup runs here either (a sweep is "
                    "itself a delete). Keep the exported files: the sign-off "
                    "refers to them.")
