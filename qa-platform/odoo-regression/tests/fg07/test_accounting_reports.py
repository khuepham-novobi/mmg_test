"""FG-07 — TC-INV-014: the accounting reports the gallery actually uses all
open and run.

Implements row 40.0 (P1, "Accounting reports") of the CLIENT MANUAL TESTING
GUIDELINE ``MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0.xlsx`` /
sheet ``Testing Guideline``.

The workbook's framing: *"Month-end depends on a handful of reports. This case
is simply proof that each one opens, runs on real data and produces a balanced
result — before anyone relies on it."* And, on why a smoke test never catches
this: *"Reports are the part of an upgrade that fails at run time rather than
install time."*

The four Expected Result lines, and what each is read from
----------------------------------------------------------
1. **"All six reports open with no error page and no blank screen."** — read
   twice, because the workbook's *If It Fails* column insists the two failure
   modes are different problems:

   * *failed to OPEN (an error page)* is the reports engine raising. Each
     report is driven through the three public calls the web client itself
     makes — ``get_options`` → re-read ``options['report_id']`` →
     ``get_report_information`` (``enterprise-19.0/account_reports/models/
     account_report.py:2126``, ``:5610``), wrapped by
     :func:`tests.fg07.common.run_report`. An ``OdooRPCError`` from that
     sequence IS the error page, and it is recorded as an offender rather than
     allowed to escape.
   * *opened EMPTY (no figures)* is read TWICE, because the workbook's own
     wording for the second failure mode is "opened EMPTY (**no figures**)",
     not "no lines": ``get_report_information()['lines']`` coming back empty
     (``lines`` is exactly what the ``AccountReport`` OWL component paints —
     ``account_report.py:5631`` — so no lines is literally the blank screen),
     AND every report that did return lines having rendered at least one
     numeric cell. A grid of lines whose every cell is blank is the workbook's
     "no figures" just as much as a page with no rows is, so both are asserted
     rather than one being asserted and the other only logged.

   The navigation the workbook types out — "Accounting > Reporting > Ledgers >
   Trial Balance" — is asserted as a menu chain rather than trusted: each leaf
   ``ir.ui.menu`` must hang under its section (Ledgers =
   ``account_reports.account_reports_audit_menu``, Statement Reports =
   ``account.account_reports_legal_statements_menu``, Partner Reports =
   ``account.account_reports_partners_reports_menu``) and each section under
   ``account.menu_finance_reports`` ("Reporting") — declared at
   ``enterprise-19.0/account_reports/data/menuitems.xml:4-15`` and
   ``addons/account/views/account_menuitem.xml:37-44``. The report each menu
   actually opens is read out of its ``ir.actions.client`` context
   (``account_reports/data/account_report_actions.xml:12-80``) and compared
   with the expected ``account.report`` record, so a menu re-pointed at the
   wrong report is caught instead of silently measured.

   ``get_report_information()['warnings']`` is logged verbatim
   (``account_report.py:5632``): a warning is not a failure, but it is what an
   accountant needs to see next to the figures.

2. **"The trial balance balances; the balance sheet balances."**

   * Trial Balance — the grand-total line's PERIOD Debit must equal its PERIOD
     Credit. The period columns are selected by
     ``column_groups[key]['forced_options']['trial_balance_column_type'] ==
     'period'`` (``account_trial_balance_report.py:91-93``) and never by
     position, because the handler injects Initial Balance and End Balance
     groups around the declared Debit/Credit pair
     (``account_trial_balance_report.py:131-140``). The total row is the LAST
     line: the handler moves it to the bottom and renames it "Total" in every
     branch (``account_trial_balance_report.py:411-427``).
   * Balance Sheet — ASSETS must equal LIABILITIES + EQUITY. The two rows are
     located by ``account.report.line.code`` — ``TA`` and ``LE`` — which are
     the same two codes on the ``account_reports`` original
     (``account_reports/data/balance_sheet.xml:24, 214``) and on the US
     variant (``l10n_us_reports/data/balance_sheet.xml:17, 68``), and each
     rendered cell carries its ``report_line_id``
     (``account_report.py:3271``), so the figure is matched to the line by id
     rather than by a translated label.

3. **"Drill-through from a figure to the underlying entries works."** —
   workbook step 7. A cell with ``auditable == True``
   (``account_report.py:3251-3253``) is passed to
   ``dispatch_report_action(options, 'action_audit_cell', params)`` with
   exactly the four params the OWL cell sends
   (``static/src/components/account_report/line_cell/line_cell.js:83-100``):
   ``report_line_id``, ``expression_label``, ``calling_line_dict_id``,
   ``column_group_key``. It goes through ``dispatch_report_action``
   (``account_report.py:2689``) and never through a direct
   ``action_audit_cell`` call, because the custom handler is allowed to
   override it. The returned ``ir.actions.act_window`` carries a ``domain``
   (``account_report.py:4802``) — and the domain is then EXECUTED with
   ``search_count`` on the action's own ``res_model``, because an action that
   returns a domain matching nothing is a drill-through that lands on an empty
   list, which is not "works".

4. **"The export produces a file that opens."** — workbook step 8, in two
   stages, because only the second one proves anything:

   * ``dispatch_report_action(options, 'export_file', 'export_to_xlsx')``
     returns ``{'type': 'ir_actions_account_report_download', 'data':
     {'options': <json>, 'file_generator': 'export_to_xlsx'}}``
     (``account_report.py:6185-6198``) — that is the button wiring, not a
     file;
   * the bytes then come from an authenticated form POST of those two values
     to ``/account_reports`` (``type='http', auth='user', methods=['POST'],
     csrf=False`` — ``account_reports/controllers/main.py:16``), asserting
     HTTP 200, the XLSX MIME type the controller sets
     (``account_report.py:1899-1908`` via ``main.py:67-70``), a
     ``Content-Disposition`` filename, and a body starting with the ZIP magic
     ``PK\\x03\\x04``. A real XLSX is a ZIP; four bytes settle "the file
     opens" better than a length check does.

   The bytes must NOT be fetched over ``call_kw``: ``json_default`` decodes
   ``bytes`` to ``str`` (``odoo/tools/json.py:70-71``) and silently corrupts
   the payload, so an XLSX pulled that way would be unusable and the test
   would still pass.

   The button set itself is asserted too, from ``options['buttons']`` and on
   the untranslated ``action_param`` rather than the label: PDF + XLSX for
   every report (``account_report.py:1869-1874``), plus CSV for the General
   Ledger only (``account_general_ledger.py:20-26``).

Read-only by construction
-------------------------
The workbook's *State After The Test* is "Nothing changed". This module
creates no record, writes no field, and calls neither ``sweep_fg07`` nor
``cleanup`` — a sweep is itself a delete. Every call it makes is a read, an
options build, a report render, or a file export; ``account.report`` writes
nothing on any of those paths.

Why the precondition probes the GROUP before the MENUS
------------------------------------------------------
``ir.ui.menu`` is group-filtered, so a missing leaf menu means either "the
menu is gone" (a real defect) or "this user may not see it" (a runner
misconfiguration). Every one of the six leaves is declared
``groups="account.group_account_readonly,account.group_account_basic"``
(``account_reports/data/menuitems.xml:4-15``), so the group is checked first
and the case BLOCKS — rather than reporting six missing menus — when the
runner user holds neither.

Documented adaptation — the two things a payload cannot show
------------------------------------------------------------
The platform asserts the report PAYLOAD, not the pixels, and asserts that the
exported bytes are a well-formed XLSX, not that Excel renders it. So two
RESIDUAL MANUAL STEPs are printed with the captured figures in them: open one
report in the browser to confirm the screen paints, and open the attached
``TC-INV-014-export.xlsx`` in a spreadsheet application. Neither is silently
dropped, and neither is faked by a weaker assertion.

Findings this case is built to surface
--------------------------------------
* **The variant reroute is EXPECTED and is asserted in neither direction.**
  ``l10n_us_reports`` ships Balance Sheet and Profit-and-Loss variants whose
  ``root_report_id`` points at the ``account_reports`` originals
  (``l10n_us_reports/data/balance_sheet.xml:5``,
  ``profit_and_loss.xml:5``), so on a US company — which the gallery is —
  opening the Balance Sheet menu ends up running the ``l10n_us_reports``
  variant via ``_init_options_variants`` (``account_report.py:1922``).
  Asserting anything about the effective ``report_id`` would fail a correct
  system, so the reroute is logged as an OBSERVATION and the effective id from
  ``options['report_id']`` is used from then on.
* **PDF export is probed, never asserted.** ``export_to_pdf``
  (``account_report.py:6205``) renders through wkhtmltopdf; its absence is an
  environment fault on the QA container, not an Odoo 19 defect. The wkhtmltopdf
  state and the POST outcome are both logged as findings.
"""
from __future__ import annotations

import ast
import csv
import json
from datetime import date, timedelta

from adapters.base import OdooRPCError
from framework.registry import test_case
from tests.fg07.common import (REPORT_LABEL, REPORT_MENU_XMLID,
                               REPORT_SECTION_XMLID, REPORT_XMLID, WORKFLOW,
                               WORKFLOW_NAME, acting_company, cell_value,
                               column_index, company_ctx, finding, has_group,
                               menu_by_xmlid, module_installed, money,
                               observation, post_account_reports_export,
                               require_account_reports, residual_manual_step,
                               run_report, trace, trial_balance_column_groups,
                               wkhtmltopdf_state)

RUN_CSV = "TC-INV-014-report-run.csv"
BALANCE_CSV = "TC-INV-014-balances.csv"
XLSX_NAME = "TC-INV-014-export.xlsx"

# The workbook's own order — steps 1 to 6, one report each.
REPORT_ORDER = ("trial_balance", "general_ledger", "balance_sheet",
                "profit_and_loss", "aged_receivable", "aged_payable")
WORKBOOK_STEP = {key: index for index, key in enumerate(REPORT_ORDER, start=1)}

# "Accounting > Reporting" itself. Every section menu must hang under it, and
# it is the one menu that proves the whole path the workbook types out.
REPORTING_MENU_XMLID = "account.menu_finance_reports"

# The two groups the six leaf menus are declared for. Either is enough.
READONLY_GROUP = "account.group_account_readonly"
BASIC_GROUP = "account.group_account_basic"

# options['buttons'], read by the untranslated action_param rather than by the
# label — 'PDF' is a translatable string, 'export_to_pdf' is not.
BASE_EXPORT_PARAMS = {"export_to_pdf", "export_to_xlsx"}
EXTRA_EXPORT_PARAMS = {"general_ledger": {"generate_csv_export"}}

XLSX_MIME = ("application/vnd.openxmlformats-officedocument"
             ".spreadsheetml.sheet")
ZIP_MAGIC = b"PK\x03\x04"

# account.report.line.code for the two Balance Sheet rows that must agree.
ASSETS_CODE = "TA"
LIABILITIES_EQUITY_CODE = "LE"

# trial_balance_column_type of the Debit/Credit pair the workbook reads.
PERIOD = "period"

NO_GROUP = (
    "The runner user holds neither 'Show Accounting Features - Readonly' "
    "(account.group_account_readonly) nor 'Basic' "
    "(account.group_account_basic). Every one of the six report menus this "
    "case opens is declared for those two groups "
    "(enterprise-19.0/account_reports/data/menuitems.xml:4-15), and ir.ui.menu "
    "is group-filtered, so the menus would read as MISSING when they are "
    "merely invisible — which is a completely different verdict from the one "
    "the workbook's If It Fails column asks for. Give the runner user an "
    "accounting role (Settings > Users, Accounting = Billing or Accountant) "
    "and run again; do NOT report the menus as absent on the strength of this "
    "run"
)


# --------------------------------------------------------------- date range
def _last_full_month(today: date) -> tuple[str, str]:
    """The workbook's Test Data: "the last full closed month".

    Computed from the run date rather than hard-coded, because a hard-coded
    month stops being "the last full month" the day after it is written. The
    range is logged and written into the evidence CSV so a re-run against a
    different month is still comparable.
    """
    first_of_this_month = today.replace(day=1)
    date_to = first_of_this_month - timedelta(days=1)
    date_from = date_to.replace(day=1)
    return date_from.isoformat(), date_to.isoformat()


# ------------------------------------------------------------- menu reading
def _literal(value, default):
    """``ast.literal_eval`` for the Char columns Odoo stores dicts in.

    ``ir.actions.client.context`` is a Char holding a Python literal. It is
    parsed, never ``eval``-ed: the six actions this case reads contain plain
    dicts (``account_report_actions.xml:12-80``), and anything else must be
    reported rather than executed.
    """
    if isinstance(value, dict):
        return value
    if not value:
        return default
    try:
        parsed = ast.literal_eval(value)
    except (ValueError, SyntaxError, TypeError):
        return default
    return parsed if isinstance(parsed, dict) else default


def _navigate(ctx, key: str) -> dict:
    """Walk the workbook's menu path for one report and read what it opens.

    Returns everything the assertions below need, and never raises: a report
    whose menu is gone must be reported alongside the other five, not instead
    of them.
    """
    rpc = ctx.adapter.rpc
    record = {
        "key": key, "label": REPORT_LABEL[key],
        "menu": {}, "section": {}, "reporting_id": None,
        "action_ref": "", "action_name": "", "action_tag": "",
        "menu_report_id": None, "expected_report_id": None,
    }
    record["expected_report_id"] = rpc.ref(REPORT_XMLID[key])
    record["reporting_id"] = rpc.ref(REPORTING_MENU_XMLID)
    record["menu"] = menu_by_xmlid(ctx, REPORT_MENU_XMLID[key])
    record["section"] = menu_by_xmlid(ctx, REPORT_SECTION_XMLID[key])

    action_ref = (record["menu"] or {}).get("action") or ""
    record["action_ref"] = action_ref
    model, _, raw_id = str(action_ref).partition(",")
    if model == "ir.actions.client" and raw_id.isdigit():
        try:
            row = rpc.read("ir.actions.client", [int(raw_id)],
                           ["name", "tag", "context"])[0]
        except (OdooRPCError, IndexError):
            row = {}
        record["action_name"] = row.get("name") or ""
        record["action_tag"] = row.get("tag") or ""
        # The menu's context is where the report id really lives; reading it
        # is what turns "the menu exists" into "the menu opens THIS report".
        record["menu_report_id"] = _literal(row.get("context"),
                                            {}).get("report_id")
    return record


# ------------------------------------------------------------ cell reading
def _cell_for_line_code(lines: list, report_line_id: int, label: str):
    """The ``no_format`` figure of one report line, matched by line id.

    Every rendered cell carries ``report_line_id`` and ``expression_label``
    (``account_report.py:3259, 3271``), so a figure can be tied to the
    ``account.report.line`` record it came from without ever matching on a
    translated row name — which is what makes the same assertion work on the
    ``account_reports`` Balance Sheet and on the ``l10n_us_reports`` variant.
    """
    for line in lines:
        for cell in line.get("columns") or []:
            if not isinstance(cell, dict):
                continue
            if (cell.get("report_line_id") == report_line_id
                    and cell.get("expression_label") == label):
                value = cell.get("no_format")
                if isinstance(value, (int, float)):
                    return money(value)
    return None


def _count_figures(lines: list) -> int:
    """How many rendered cells actually hold a number.

    Asserted, not merely logged. The workbook's If It Fails column defines the
    second failure mode as "opened EMPTY (**no figures**)", so a report that
    paints a grid of blanks has failed that line exactly as a report with no
    rows has. ``no_format`` is the cell's raw value
    (``account_report.py:3269``); a cell with no value carries ``None`` there
    (``:3251``), which is what makes counting numeric cells the same test the
    OWL component's own blank rendering makes.
    """
    total = 0
    for line in lines:
        for cell in line.get("columns") or []:
            if isinstance(cell, dict) and isinstance(
                    cell.get("no_format"), (int, float)):
                total += 1
    return total


def _auditable_cell(lines: list) -> tuple:
    """The first drillable cell: ``(line, cell)`` or ``(None, None)``.

    ``auditable`` is set only when the cell has a value AND its expression is
    auditable AND the column group is not a budget computation
    (``account_report.py:3251-3253``), which is exactly the condition under
    which the web client shows the figure as a link. Picking any other cell
    would test a path the user cannot reach.
    """
    for line in lines:
        for cell in line.get("columns") or []:
            if not isinstance(cell, dict) or not cell.get("auditable"):
                continue
            if cell.get("no_format") is None:
                continue
            if not cell.get("report_line_id") or not cell.get(
                    "column_group_key"):
                continue
            return line, cell
    return None, None


@test_case(
    id="TEST-FG07-INV-014",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module="account_reports, l10n_us_reports",
    priority="P1",
    kind="DATA",
    order=711,
    name="The accounting reports the gallery actually uses all open and run",
    description="Read-only: all six month-end reports are opened through "
                "their own menu chain and run over the last full closed "
                "month; each must return lines rather than an error or a "
                "blank screen, the trial balance's period debits must equal "
                "its credits, the balance sheet's ASSETS must equal "
                "LIABILITIES + EQUITY, an auditable figure must drill through "
                "to journal items that really exist, and the XLSX export must "
                "come back over HTTP as a real ZIP-framed workbook. Creates "
                "nothing.",
    traceability=trace("TC-INV-014"))
def test_inv_014(ctx):
    rpc = ctx.adapter.rpc
    # Accumulators are declared BEFORE the try: the evidence block runs from
    # `finally` and must never raise a NameError over a step that an earlier
    # assertion failure skipped — that would replace a real FAILED verdict
    # with an AUTOMATION_ERROR.
    evidence: list[tuple] = []
    balances: list[tuple] = []
    residual: list[str] = []
    reports: dict = {}
    xlsx_bytes = b""
    date_from = date_to = ""

    with ctx.step("Precondition (workbook): TC-DAT-002 has passed and you can "
                  "open Accounting > Reporting"):
        # The reports engine gate. require_account_reports probes
        # ir.module.module — NOT model_exists — because account.report is
        # defined in Community with zero engine methods
        # (addons/account/models/account_report.py:45), so its presence would
        # be a false positive and the test would die later with a confusing
        # "method does not exist" instead of a clean BLOCK.
        require_account_reports(ctx)

        # The group comes BEFORE the menus, for the reason in the module
        # docstring: ir.ui.menu is group-filtered.
        readonly = has_group(ctx, READONLY_GROUP)
        basic = has_group(ctx, BASIC_GROUP)
        ctx.log(f"runner user groups — {READONLY_GROUP}: {readonly}, "
                f"{BASIC_GROUP}: {basic}")
        if not (readonly or basic):
            ctx.blocked(NO_GROUP)

        company = acting_company(ctx)
        ctx.log(f"acting company #{company['id']} {company['name']!r} — "
                f"country {company['country_name']!r}, currency "
                f"{company['currency_name']}")

        # l10n_us_reports is not a gate: it is the module whose Balance Sheet
        # and Profit-and-Loss VARIANTS a US company gets rerouted onto, and
        # the case must work identically with or without it.
        us_reports = module_installed(rpc, "l10n_us_reports")
        ctx.log(f"module 'l10n_us_reports' installed: {us_reports} — this "
                f"decides whether the Balance Sheet and Profit and Loss menus "
                f"end up on the US variants "
                f"(l10n_us_reports/data/balance_sheet.xml:5)")

        date_from, date_to = _last_full_month(date.today())
        ctx.log(f"workbook Test Data 'the last full closed month' resolves to "
                f"{date_from} .. {date_to}")

        # Posted volume in the window, so a genuinely quiet month can be told
        # apart from a broken report when a figure count comes back low.
        try:
            posted_lines = rpc.call(
                "account.move.line", "search_count",
                [("parent_state", "=", "posted"),
                 ("company_id", "=", company["id"]),
                 ("date", ">=", date_from), ("date", "<=", date_to)],
                context=company_ctx(company))
        except OdooRPCError as exc:
            posted_lines = -1
            ctx.log(f"could not count posted journal items for the window "
                    f"({exc}) — the report figures below stand on their own")
        ctx.log(f"{posted_lines} posted journal item(s) in "
                f"{date_from}..{date_to} for this company")
        if posted_lines == 0:
            finding(ctx,
                    f"the last full closed month ({date_from}..{date_to}) "
                    f"holds NO posted journal item for company "
                    f"#{company['id']}. The six reports are still required to "
                    f"open, but 'shows figures' cannot distinguish a working "
                    f"report from a broken one over an empty period — re-run "
                    f"against a month the gallery actually traded in before "
                    f"concluding anything about the figures")
        evidence.append(("precondition", "-", f"{date_from}..{date_to}",
                         "", "", "", "", "", posted_lines, "", ""))

    try:
        with ctx.step("Steps 1-6 (capture): open each of the six reports "
                      "through its own menu and run it over the last full "
                      "closed month"):
            # Range reports (Trial Balance, General Ledger, Profit and Loss)
            # take date_from/date_to; single-date reports (Balance Sheet, the
            # two Aged) convert this to an as-at date_to themselves
            # (account_report.py:705-712). One options dict is therefore
            # correct for all six.
            options = {
                "date": {"mode": "range", "filter": "custom",
                         "date_from": date_from, "date_to": date_to},
                # Posted entries only — this is what an accountant means by
                # "the last full CLOSED month".
                "all_entries": False,
                # No hierarchy and no full unfold: the workbook is opening the
                # reports as they open by default, and unfold_all would expand
                # every account into its journal items and turn a smoke test
                # into a multi-minute render.
                "hierarchy": False,
                "unfold_all": False,
            }
            for key in REPORT_ORDER:
                step_no = WORKBOOK_STEP[key]
                record = _navigate(ctx, key)
                ctx.log(f"[step {step_no}] {record['label']} — menu "
                        f"{REPORT_MENU_XMLID[key]!r} -> "
                        f"{record['menu'].get('name')!r} (parent "
                        f"{record['menu'].get('parent_name')!r}), action "
                        f"{record['action_ref']!r} "
                        f"{record['action_name']!r}/{record['action_tag']!r}, "
                        f"report_id in context "
                        f"{record['menu_report_id']!r} (expected "
                        f"{record['expected_report_id']!r})")

                # The report id to run: whatever the MENU says, because that
                # is what a user clicking the menu gets. The comparison with
                # the expected xmlid is a separate assertion below.
                report_id = (record["menu_report_id"]
                             or record["expected_report_id"])
                record["opened"] = False
                record["error"] = ""
                record["lines"] = []
                record["warnings"] = {}
                record["buttons"] = set()
                record["effective_report_id"] = None
                record["opts"] = {}

                if not report_id:
                    record["error"] = ("neither the menu action's context nor "
                                       "the xmlid resolved to an "
                                       "account.report record")
                else:
                    try:
                        opts, info = run_report(ctx, report_id, options,
                                                company)
                        record["opts"] = opts or {}
                        record["opened"] = True
                        record["effective_report_id"] = (
                            record["opts"].get("report_id"))
                        record["lines"] = list((info or {}).get("lines") or [])
                        record["warnings"] = (info or {}).get("warnings") or {}
                        record["buttons"] = {
                            button.get("action_param")
                            for button in (record["opts"].get("buttons") or [])
                            if isinstance(button, dict)
                            and button.get("action") == "export_file"
                            and button.get("action_param")}
                    except OdooRPCError as exc:
                        # THIS is the workbook's "failed to OPEN (an error
                        # page)". It is captured, not raised: the other five
                        # reports still have to be opened, and the workbook
                        # asks which ones failed.
                        record["error"] = str(exc)

                if record["opened"]:
                    figures = _count_figures(record["lines"])
                    record["figures"] = figures
                    ctx.log(f"[step {step_no}] {record['label']} — OPENED, "
                            f"effective report #"
                            f"{record['effective_report_id']}, "
                            f"{len(record['lines'])} line(s), {figures} "
                            f"numeric cell(s), export buttons "
                            f"{sorted(record['buttons'])}")
                    if record["effective_report_id"] != report_id:
                        observation(
                            ctx,
                            f"{record['label']} was rerouted from report "
                            f"#{report_id} to variant "
                            f"#{record['effective_report_id']} by "
                            f"_init_options_variants "
                            f"(account_report.py:1922). On a US company this "
                            f"is exactly what l10n_us_reports is for "
                            f"(l10n_us_reports/data/balance_sheet.xml:5) — "
                            f"the variant is the report the user really sees, "
                            f"so it is the one this case measures, and no "
                            f"assertion is made about the id in either "
                            f"direction")
                    for template, params in (record["warnings"] or {}).items():
                        # Verbatim: an accountant reading the log needs the
                        # engine's own wording, not a paraphrase.
                        ctx.log(f"[step {step_no}] {record['label']} — ENGINE "
                                f"WARNING {template!r}: {params!r}")
                else:
                    record["figures"] = 0
                    ctx.log(f"[step {step_no}] {record['label']} — DID NOT "
                            f"OPEN: {record['error']}")

                reports[key] = record
                evidence.append((
                    f"step {step_no}", record["label"],
                    f"{date_from}..{date_to}",
                    record["menu"].get("name") or "(menu not resolved)",
                    record["menu"].get("parent_name") or "",
                    record["expected_report_id"] or "",
                    record["menu_report_id"] or "",
                    record["effective_report_id"] or "",
                    len(record["lines"]),
                    record["figures"],
                    record["error"] or "; ".join(
                        str(k) for k in (record["warnings"] or {})) or "ok"))

        with ctx.step("Expected line 1 (a): the navigation the workbook types "
                      "out is really there — Reporting > Ledgers / Statement "
                      "Reports / Partner Reports > <report>"):
            missing_menu, wrong_section, wrong_reporting, wrong_report = \
                [], [], [], []
            for key in REPORT_ORDER:
                record = reports[key]
                label = record["label"]
                menu, section = record["menu"], record["section"]
                if not menu:
                    # The group was already proven above, so an unresolved
                    # menu here means the record itself is gone.
                    missing_menu.append(
                        f"{label} ({REPORT_MENU_XMLID[key]} does not resolve "
                        f"— and the runner user DOES hold an accounting "
                        f"group, so this is not a visibility problem)")
                    continue
                if not menu.get("active"):
                    missing_menu.append(f"{label} (menu archived)")
                if not section:
                    wrong_section.append(
                        f"{label} (its section menu "
                        f"{REPORT_SECTION_XMLID[key]} does not resolve)")
                elif menu.get("parent_id") != section.get("id"):
                    wrong_section.append(
                        f"{label} (leaf sits under "
                        f"{menu.get('parent_name')!r} #"
                        f"{menu.get('parent_id')}, not under "
                        f"{section.get('name')!r} #{section.get('id')})")
                elif section.get("parent_id") != record["reporting_id"]:
                    wrong_reporting.append(
                        f"{label} (section {section.get('name')!r} hangs "
                        f"under #{section.get('parent_id')}, not under "
                        f"Accounting > Reporting "
                        f"#{record['reporting_id']})")
                if (record["menu_report_id"] and record["expected_report_id"]
                        and record["menu_report_id"]
                        != record["expected_report_id"]):
                    wrong_report.append(
                        f"{label} (the menu opens account.report "
                        f"#{record['menu_report_id']}, but "
                        f"{REPORT_XMLID[key]} is "
                        f"#{record['expected_report_id']})")
            ctx.check("Every one of the six reports still has its own menu "
                      "entry under Accounting > Reporting",
                      [], missing_menu)
            ctx.check("Each report sits in the section the workbook navigates "
                      "to — Ledgers, Statement Reports or Partner Reports",
                      [], wrong_section)
            ctx.check("Each of those three sections still hangs under "
                      "Accounting > Reporting (account.menu_finance_reports)",
                      [], wrong_reporting)
            ctx.check("Each menu opens the report record it is supposed to "
                      "open (report_id in the ir.actions.client context)",
                      [], wrong_report)

        with ctx.step("Expected line 1 (b): all six reports open with no "
                      "error page and no blank screen"):
            # The workbook's If It Fails column: "say whether it failed to
            # OPEN (an error page) or opened EMPTY (no figures) — they are
            # different problems". Two separate assertions, so the log names
            # which of the two happened, per report.
            failed_to_open = [f"{reports[key]['label']}: "
                              f"{reports[key]['error']}"
                              for key in REPORT_ORDER
                              if not reports[key]["opened"]]
            opened_empty = [
                f"{reports[key]['label']}: get_report_information returned 0 "
                f"lines — this is the blank screen, not an error page"
                for key in REPORT_ORDER
                if reports[key]["opened"] and not reports[key]["lines"]]
            ctx.check("No report FAILED TO OPEN — none of the six raised from "
                      "get_options / get_report_information (the workbook's "
                      "'error page')",
                      [], failed_to_open)
            ctx.check("No report OPENED EMPTY — every one of the six returned "
                      "at least one line to paint (the workbook's 'blank "
                      "screen')",
                      [], opened_empty)
            # The second half of the same Expected Result line. The workbook's
            # If It Fails column says "opened EMPTY (no figures)" — FIGURES,
            # not lines — so a report that came back with rows whose every
            # cell is blank has failed this line just as squarely as one that
            # came back with no rows at all. Counting numeric cells is
            # therefore an assertion here and not merely a logged number: a
            # month with no posted journal item still renders its brought-
            # forward figures on the Trial Balance and the Balance Sheet, and
            # a report that renders none of them is not "running on real
            # data".
            no_figures = [
                f"{reports[key]['label']}: {len(reports[key]['lines'])} "
                f"line(s) rendered but not one of their cells holds a number "
                f"— this is the workbook's 'opened EMPTY (no figures)', which "
                f"its If It Fails column separates from an error page"
                for key in REPORT_ORDER
                if reports[key]["opened"] and reports[key]["lines"]
                and not reports[key]["figures"]]
            ctx.check("No report opened WITHOUT FIGURES — every one of the six "
                      "painted at least one numeric cell, which is the "
                      "workbook's own wording for the empty-screen failure "
                      "('opened EMPTY (no figures)')",
                      [], no_figures)

        with ctx.step("Expected line 4 (a) / step 8 wiring: every report "
                      "offers PDF and XLSX, and the General Ledger also "
                      "offers CSV"):
            # Asserted on action_param, never on the button label: 'PDF' and
            # 'CSV' are translatable (account_report.py:1871-1872), the
            # action_param is not. A missing export button is the export
            # failing before the user can even press it.
            missing_buttons = []
            for key in REPORT_ORDER:
                record = reports[key]
                if not record["opened"]:
                    continue
                wanted = BASE_EXPORT_PARAMS | EXTRA_EXPORT_PARAMS.get(key,
                                                                      set())
                absent = sorted(wanted - record["buttons"])
                if absent:
                    missing_buttons.append(
                        f"{record['label']} is missing {absent} (it offers "
                        f"{sorted(record['buttons'])})")
            ctx.check("Every report that opened offers the export buttons it "
                      "ships with — PDF and XLSX for all six, plus CSV for "
                      "the General Ledger",
                      [], missing_buttons)

        with ctx.step("Expected line 2 (a) / step 1: the trial balance "
                      "balances — period debits equal period credits"):
            record = reports["trial_balance"]
            if not record["opened"]:
                # Already reported as a failure above; saying it again as a
                # different assertion would double-count one defect.
                ctx.log("the Trial Balance did not open, so its debit/credit "
                        "equality cannot be read — the failure is already "
                        "recorded against Expected line 1")
            else:
                opts, lines = record["opts"], record["lines"]
                groups = trial_balance_column_groups(opts)
                ctx.log(f"trial balance column groups by "
                        f"trial_balance_column_type: {groups}")
                period_key = groups.get(PERIOD)
                ctx.check_true(
                    "The Trial Balance presents a period Debit/Credit column "
                    "group (forced_options['trial_balance_column_type'] == "
                    "'period')",
                    bool(period_key),
                    actual_desc=f"column groups seen: {sorted(groups)}")
                # The handler moves the grand total to the bottom and renames
                # it 'Total' in every branch
                # (account_trial_balance_report.py:411-427), so the last line
                # IS the total row.
                total_line = lines[-1] if lines else {}
                debit = cell_value(total_line,
                                   column_index(opts, "debit", period_key))
                credit = cell_value(total_line,
                                    column_index(opts, "credit", period_key))
                debit = money(debit) if isinstance(debit, (int, float)) else None
                credit = money(credit) if isinstance(credit,
                                                     (int, float)) else None
                ctx.log(f"Trial Balance grand total line "
                        f"{total_line.get('name')!r} — period Debit "
                        f"{debit} | period Credit {credit}")
                balances.append(("Trial Balance", "period debit",
                                 debit if debit is not None else ""))
                balances.append(("Trial Balance", "period credit",
                                 credit if credit is not None else ""))
                ctx.check_true(
                    "The Trial Balance produced a grand-total row carrying "
                    "both a period Debit and a period Credit figure",
                    debit is not None and credit is not None,
                    actual_desc=f"last of {len(lines)} line(s): "
                                f"name={total_line.get('name')!r} "
                                f"debit={debit!r} credit={credit!r}")
                # money() on both sides: ctx.check compares with ==, and an
                # unrounded float pair that differs in the 12th decimal is a
                # balanced trial balance reported as broken.
                ctx.check("The trial balance balances — total period debits "
                          "equal total period credits",
                          debit, credit)

        with ctx.step("Expected line 2 (b) / step 3: the balance sheet "
                      "balances — ASSETS equals LIABILITIES + EQUITY"):
            record = reports["balance_sheet"]
            if not record["opened"]:
                ctx.log("the Balance Sheet did not open, so it cannot be "
                        "shown to balance — the failure is already recorded "
                        "against Expected line 1")
            else:
                effective_id = record["effective_report_id"]
                try:
                    code_rows = rpc.search_read(
                        "account.report.line",
                        [("report_id", "=", effective_id),
                         ("code", "in", [ASSETS_CODE,
                                         LIABILITIES_EQUITY_CODE])],
                        ["code", "name"])
                except OdooRPCError as exc:
                    code_rows = []
                    ctx.log(f"could not read the Balance Sheet's report lines "
                            f"({exc})")
                by_code = {row.get("code"): row for row in code_rows}
                ctx.log(f"balance sheet report #{effective_id} lines by code: "
                        f"{ {c: r.get('name') for c, r in by_code.items()} }")
                missing_codes = [code for code in (ASSETS_CODE,
                                                   LIABILITIES_EQUITY_CODE)
                                 if code not in by_code]
                # Both the account_reports original
                # (data/balance_sheet.xml:24, 214) and the US variant
                # (l10n_us_reports/data/balance_sheet.xml:17, 68) use TA and
                # LE, so a missing code means a rewritten report, which the
                # accountant needs told about before the figures are trusted.
                ctx.check("The Balance Sheet still carries its ASSETS (code "
                          "TA) and LIABILITIES + EQUITY (code LE) rows",
                          [], missing_codes)
                assets = _cell_for_line_code(
                    record["lines"], by_code.get(ASSETS_CODE, {}).get("id"),
                    "balance")
                liab_equity = _cell_for_line_code(
                    record["lines"],
                    by_code.get(LIABILITIES_EQUITY_CODE, {}).get("id"),
                    "balance")
                ctx.log(f"Balance Sheet as at {date_to} — "
                        f"{by_code.get(ASSETS_CODE, {}).get('name')!r} "
                        f"{assets} | "
                        f"{by_code.get(LIABILITIES_EQUITY_CODE, {}).get('name')!r} "
                        f"{liab_equity}")
                balances.append(("Balance Sheet", "ASSETS (TA)",
                                 assets if assets is not None else ""))
                balances.append(("Balance Sheet", "LIABILITIES + EQUITY (LE)",
                                 liab_equity if liab_equity is not None else ""))
                ctx.check_true(
                    "Both Balance Sheet totals rendered a figure (a row that "
                    "renders no number cannot be shown to balance)",
                    assets is not None and liab_equity is not None,
                    actual_desc=f"ASSETS={assets!r} "
                                f"LIABILITIES+EQUITY={liab_equity!r} over "
                                f"{len(record['lines'])} rendered line(s)")
                ctx.check("The balance sheet balances — ASSETS equals "
                          "LIABILITIES + EQUITY",
                          assets, liab_equity)

        with ctx.step("Step 7 / Expected line 3: click a figure to drill into "
                      "the underlying entries"):
            # "On any one of the above" — the Trial Balance is preferred
            # because every one of its three expressions is declared
            # auditable (account_reports/data/trial_balance.xml:37, 44, 51),
            # then the General Ledger, then whatever else opened.
            carrier_key = next(
                (key for key in ("trial_balance", "general_ledger")
                 + REPORT_ORDER
                 if reports.get(key, {}).get("opened")
                 and _auditable_cell(reports[key]["lines"])[1]), "")
            if not carrier_key:
                # Not a silent pass: the workbook's step 7 has to happen on
                # SOMETHING, and no auditable cell anywhere means no figure on
                # any of the six reports is clickable.
                ctx.check_true(
                    "At least one of the six reports rendered a drillable "
                    "(auditable) figure for step 7 to click",
                    False,
                    actual_desc="; ".join(
                        f"{reports[k]['label']}: opened="
                        f"{reports[k]['opened']} lines="
                        f"{len(reports[k]['lines'])}"
                        for k in REPORT_ORDER))
            else:
                record = reports[carrier_key]
                line, cell = _auditable_cell(record["lines"])
                params = {
                    "report_line_id": cell.get("report_line_id"),
                    "expression_label": cell.get("expression_label"),
                    "calling_line_dict_id": line.get("id"),
                    "column_group_key": cell.get("column_group_key"),
                }
                ctx.log(f"drilling into {record['label']} — line "
                        f"{line.get('name')!r} column "
                        f"{cell.get('expression_label')!r} value "
                        f"{cell.get('no_format')!r}, params {params}")
                action, drill_error = {}, ""
                try:
                    # Through dispatch_report_action, never a direct
                    # action_audit_cell: the aged handlers override it
                    # (account_report.py:2689-2710 picks the custom handler),
                    # and calling the base method would test a path no user
                    # reaches.
                    action = rpc.call(
                        "account.report", "dispatch_report_action",
                        [record["effective_report_id"]], record["opts"],
                        "action_audit_cell", params,
                        context=company_ctx(company)) or {}
                except OdooRPCError as exc:
                    drill_error = str(exc)
                ctx.check_true(
                    "Clicking an auditable figure returns an action instead "
                    "of an error (account.report.dispatch_report_action -> "
                    "action_audit_cell)",
                    bool(action) and not drill_error,
                    actual_desc=drill_error or f"returned {type(action)}")
                res_model = (action or {}).get("res_model") or ""
                domain = (action or {}).get("domain") or []
                ctx.log(f"drill-through action: type="
                        f"{(action or {}).get('type')!r} res_model="
                        f"{res_model!r} name="
                        f"{(action or {}).get('name')!r} domain={domain!r}")
                ctx.check("The drill-through opens a record list "
                          "(ir.actions.act_window)",
                          "ir.actions.act_window", (action or {}).get("type"))
                ctx.check_true(
                    "The drill-through lands on the underlying entries "
                    "(account.move.line, or account.report.external.value for "
                    "a manually keyed figure)",
                    res_model in ("account.move.line",
                                  "account.report.external.value"),
                    actual_desc=f"res_model={res_model!r}")
                ctx.check_true(
                    "The drill-through carries a domain — an action with no "
                    "domain would open the whole ledger rather than the "
                    "entries behind the figure",
                    bool(domain),
                    actual_desc=f"domain={domain!r}")
                # The real proof: EXECUTE the domain. An action whose domain
                # matches nothing is a drill-through that lands on an empty
                # list, which is not what the workbook means by "works".
                matched = -1
                if res_model and domain:
                    try:
                        matched = rpc.call(
                            res_model, "search_count", domain,
                            context=company_ctx(company, active_test=False))
                    except OdooRPCError as exc:
                        matched = -1
                        ctx.log(f"the drill-through domain could not be "
                                f"executed against {res_model} ({exc})")
                ctx.log(f"the drill-through domain matches {matched} "
                        f"{res_model} record(s)")
                evidence.append(("step 7", record["label"],
                                 f"{date_from}..{date_to}",
                                 "drill-through", res_model,
                                 params.get("report_line_id") or "",
                                 params.get("expression_label") or "",
                                 "", matched, "", str(domain)[:400]))
                ctx.check_true(
                    "The drill-through really reaches entries — its own "
                    "domain, executed, returns at least one record",
                    matched > 0,
                    actual_desc=f"search_count on {res_model!r} with the "
                                f"action's domain returned {matched} (a -1 "
                                f"means the domain could not be executed at "
                                f"all)")

        with ctx.step("Step 8 / Expected line 4: use the export button and "
                      "confirm a file downloads and opens"):
            export_key = next((key for key in ("trial_balance",
                                               "general_ledger") + REPORT_ORDER
                               if reports.get(key, {}).get("opened")), "")
            if not export_key:
                ctx.check_true(
                    "At least one report opened, so that step 8 has something "
                    "to export",
                    False,
                    actual_desc="none of the six reports opened")
            else:
                record = reports[export_key]
                ctx.log(f"exporting {record['label']} (report "
                        f"#{record['effective_report_id']})")
                download, export_error = {}, ""
                try:
                    download = rpc.call(
                        "account.report", "dispatch_report_action",
                        [record["effective_report_id"]], record["opts"],
                        "export_file", "export_to_xlsx",
                        context=company_ctx(company)) or {}
                except OdooRPCError as exc:
                    export_error = str(exc)
                ctx.log(f"export_file returned: "
                        f"{ {k: (v if k != 'data' else sorted(v)) for k, v in (download or {}).items()} } "
                        f"{export_error}")
                ctx.check("Pressing XLSX hands the browser a report download "
                          "action (account_report.py:6189)",
                          "ir_actions_account_report_download",
                          (download or {}).get("type"))
                data = (download or {}).get("data") or {}
                ctx.check("The download action names the XLSX generator",
                          "export_to_xlsx", data.get("file_generator"))

                # Stage two — the only stage that proves a FILE exists. The
                # bytes come over HTTP because call_kw's json_default would
                # decode them to str and corrupt the workbook
                # (odoo/tools/json.py:70-71).
                try:
                    export_options = json.loads(data.get("options") or "{}")
                except (TypeError, ValueError):
                    export_options = dict(record["opts"])
                    ctx.log("the download action's options were not valid "
                            "JSON — POSTing the live options instead")
                status, content_type, disposition, body = \
                    post_account_reports_export(ctx, export_options,
                                                "export_to_xlsx")
                xlsx_bytes = body or b""
                ctx.log(f"POST /account_reports -> HTTP {status}, "
                        f"Content-Type {content_type!r}, "
                        f"Content-Disposition {disposition!r}, "
                        f"{len(xlsx_bytes)} byte(s)")
                evidence.append(("step 8", record["label"],
                                 f"{date_from}..{date_to}", "export_to_xlsx",
                                 content_type, disposition, "", "",
                                 len(xlsx_bytes), status, ""))
                ctx.check("The export request succeeds "
                          "(POST /account_reports, "
                          "account_reports/controllers/main.py:16)",
                          200, status)
                ctx.check("The export comes back as a spreadsheet, not as an "
                          "HTML error page (Content-Type)",
                          XLSX_MIME, content_type)
                ctx.check_true(
                    "The export is served as a named download "
                    "(Content-Disposition carries a filename)",
                    "filename" in (disposition or "").lower(),
                    actual_desc=f"Content-Disposition: {disposition!r}")
                # "a file that opens": a real .xlsx is a ZIP container, so its
                # first four bytes are the ZIP local-file-header magic. Four
                # bytes settle this better than a length check, which a
                # rendered error page would also pass.
                ctx.check_true(
                    "The exported file is a real workbook — it opens as the "
                    "ZIP container an .xlsx is (magic PK\\x03\\x04)",
                    xlsx_bytes[:4] == ZIP_MAGIC,
                    actual_desc=f"first bytes {xlsx_bytes[:8]!r} of "
                                f"{len(xlsx_bytes)}")

                # PDF: probed and reported, never asserted. wkhtmltopdf is an
                # environment dependency of the QA container, and its absence
                # is not an Odoo 19 defect.
                state = wkhtmltopdf_state(ctx)
                ctx.log(f"ir.actions.report.get_wkhtmltopdf_state(): "
                        f"{state!r}")
                pdf_status, pdf_type, _pdf_disp, pdf_body = \
                    post_account_reports_export(ctx, export_options,
                                                "export_to_pdf")
                ctx.log(f"PDF export probe — HTTP {pdf_status}, Content-Type "
                        f"{pdf_type!r}, {len(pdf_body or b'')} byte(s)")
                evidence.append(("step 8 (probe)", record["label"],
                                 f"{date_from}..{date_to}", "export_to_pdf",
                                 pdf_type, "", "", "",
                                 len(pdf_body or b""), pdf_status, state))
                if pdf_status != 200:
                    finding(ctx,
                            f"the PDF export of {record['label']} returned "
                            f"HTTP {pdf_status} while the XLSX export "
                            f"succeeded. get_wkhtmltopdf_state() is {state!r} "
                            f"— anything other than 'ok' means the PDF engine "
                            f"is missing from the SERVER, which is an "
                            f"environment fault rather than an Odoo 19 "
                            f"regression. It is reported, not asserted, "
                            f"because the workbook's step 8 says 'use the "
                            f"export button' without naming a format; say "
                            f"which format you tried when you report it")
                else:
                    ctx.log("the PDF export also succeeded — both formats the "
                            "workbook's If It Fails column asks about are "
                            "working")

                residual.append(
                    f"workbook step 8 says the exported file must OPEN. This "
                    f"case proves the download is a well-formed XLSX "
                    f"container ({len(xlsx_bytes)} bytes, Content-Type "
                    f"{content_type!r}, first bytes "
                    f"{xlsx_bytes[:4]!r}); open the attached {XLSX_NAME} in "
                    f"Excel or LibreOffice and confirm the figures match the "
                    f"{record['label']} numbers printed above for "
                    f"{date_from}..{date_to}. A workbook that downloads but "
                    f"will not open is a different defect from one that never "
                    f"downloads.")

        with ctx.step("The part of Expected line 1 a payload cannot show"):
            opened = [reports[key]["label"] for key in REPORT_ORDER
                      if reports[key]["opened"]]
            residual.append(
                "'no error page and no blank screen' is finally a screen "
                "judgement. This case asserted the payload behind the screen "
                "— each report's get_report_information returned lines, and "
                "the figure counts were: " + "; ".join(
                    f"{reports[key]['label']} {len(reports[key]['lines'])} "
                    f"line(s)/{reports[key]['figures']} figure(s)"
                    for key in REPORT_ORDER) +
                f". Open at least one of the {len(opened)} report(s) that ran "
                f"({', '.join(opened) or 'none'}) in the browser over "
                f"{date_from}..{date_to} and confirm it paints. If it paints "
                f"blank while this case passed, the defect is in the web "
                f"client, not in the reports engine — say so, because they "
                f"are fixed by different people.")
    finally:
        with ctx.step("Evidence: write the run log, the balance figures and "
                      "the exported workbook"):
            for path_name, header, rows in (
                (RUN_CSV,
                 ["step", "report", "date_range", "menu", "section",
                  "expected_report_id", "menu_report_id",
                  "effective_report_id", "lines_or_count", "figures_or_status",
                  "detail"],
                 evidence),
                (BALANCE_CSV,
                 ["report", "measure", "value"],
                 balances),
            ):
                path = ctx.artifacts_dir / path_name
                try:
                    with path.open("w", newline="", encoding="utf-8") as fh:
                        writer = csv.writer(fh)
                        writer.writerow(header)
                        writer.writerows(rows)
                    ctx.add_artifact(path, "log", path_name)
                    ctx.log(f"wrote {len(rows)} row(s) to {path_name}")
                except OSError as exc:
                    ctx.log(f"could not write {path_name} ({exc}) — the "
                            f"figures above are still in this log")
            if xlsx_bytes:
                path = ctx.artifacts_dir / XLSX_NAME
                try:
                    path.write_bytes(xlsx_bytes)
                    ctx.add_artifact(path, "file", XLSX_NAME)
                    ctx.log(f"wrote {len(xlsx_bytes)} byte(s) to {XLSX_NAME}")
                except OSError as exc:
                    ctx.log(f"could not save {XLSX_NAME} ({exc}) — the export "
                            f"itself still succeeded, see the log above")
            for note in residual:
                residual_manual_step(ctx, note)
            ctx.log("NOTHING WAS CREATED OR MODIFIED by this case — the "
                    "workbook's State After The Test is 'Nothing changed', so "
                    "no sweep and no cleanup runs here either (a sweep is "
                    "itself a delete). Every call made was a read, an options "
                    "build, a report render or a file export.")
