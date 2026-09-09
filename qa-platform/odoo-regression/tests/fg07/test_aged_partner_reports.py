"""FG-07 — TC-DAT-004: what customers owe and what the gallery owes still matches.

Implements row 31.0 (P0, "Accounting reports") of the CLIENT MANUAL TESTING
GUIDELINE ``MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0.xlsx`` /
sheet ``Testing Guideline``.

The workbook's framing: *"The aged receivable and payable reports drive
collections and payments. If an invoice's due date or open balance changed in
the upgrade, the gallery will chase the wrong customers and miss real ones."*
And, on why the buckets matter as much as the totals: *"a right total in the
wrong bucket still means the wrong collections list."*

Read-only by construction
-------------------------
The workbook's *State After The Test* is "Nothing changed. Keep both exports."
This module creates no record, writes no field, and calls neither
``sweep_fg07`` nor ``cleanup`` — a sweep is itself a delete. The only writes
anywhere near this case are the two evidence CSVs, which go to
``ctx.artifacts_dir``.

The 3 Expected Result lines, and what each is read from
------------------------------------------------------
1. **"Both grand totals match the baseline exactly."** — read from the ONE
   root ``account.report.line`` of each report
   (``enterprise-19.0/account_reports/data/aged_partner_balance.xml:73``
   ``aged_receivable_line`` and ``:235`` ``aged_payable_line``, both with
   ``groupby = "partner_id, id"`` at ``:75`` and ``:237``), column ``total``,
   taken out of the cell's ``no_format`` — the float, never the formatted
   string (``.../models/account_report.py:3269``). When
   ``data/baselines/TC-DAT-004.json`` holds the old system's figures this is a
   real assertion; when it does not, it falls back to a RESIDUAL MANUAL STEP
   carrying both captured grand totals. Asserted either way is the internal
   identity ``period0 + … + period5 == total`` on each root line.
2. **"Every ageing column total matches."** — read from the same root line,
   columns ``period0`` … ``period5``, addressed by ``expression_label`` and
   never by position or display name. There are **six** ageing columns, not
   the five the workbook names: ``period0`` (At Date), ``period1`` … ``period4``
   (renamed at run time to ``1-30`` / ``31-60`` / ``61-90`` / ``91-120`` from
   ``options['aging_interval']`` —
   ``.../models/account_aged_partner_balance.py:47-53``) and ``period5``
   (Older). Compared bucket by bucket against the baseline file when it holds
   them, residual otherwise; asserted either way is that all six exist, and
   that the partner rows add up to each column's grand total, which is the
   "right total, wrong bucket" failure the workbook is worried about, caught
   from the inside.
3. **"The top ten customers and top ten vendors, and their balances, match."**
   — read from the partner-level lines produced by ``unfold_all`` (both
   reports carry ``filter_unfold_all eval="True"`` —
   ``aged_partner_balance.xml:6`` and ``:168``), identified by the ``res.partner``
   segment of the generic line id (``account_report.py:2447-2454`` documents
   the ``markup~model~value`` shape), sorted by the ``total`` cell descending.
   Names and figures are written to the two CSVs and printed, and compared
   rank by rank — "name by name and figure by figure", workbook step 5 —
   against the baseline file when it holds a partner list; residual otherwise.

The Novobi baseline file
------------------------
The workbook's Expected Result is three comparisons against reports from the
old system. This platform already has a place to keep those figures
(``framework/baselines.py:22-39``), so they are asserted rather than deferred
whenever they are present. ``data/baselines/TC-DAT-004.json``::

    {"data": {
       "as_at": "2024-12-31",
       "aged_receivable": {"total": 0.0,
                           "buckets": {"period0": 0.0, "1-30": 0.0, …},
                           "partners": {"A Customer": 0.0}},
       "aged_payable":    {"total": 0.0, "buckets": {…}, "partners": {…}}}}

Every key is optional and only the keys present are compared, so a partial
transcription still asserts what it names and hands the rest back as a
residual step — a half-typed baseline never silently shrinks the Expected
Result. ``receivable`` / ``payable`` are accepted as short aliases; buckets may
be keyed by ``period0`` … ``period5`` or by the printed names the workbook
uses (``current`` / ``1-30`` / ``31-60`` / ``61-90`` / ``91-120`` / ``older``);
partners may be a ``{name: balance}`` mapping or a list of rows. ``as_at``, when
present, is the as-at date the whole case runs on — which is exactly what the
workbook's Test Data column asks for ("use the same as-at date as the Novobi
baseline").

Options this case pins, and why each one is load-bearing
--------------------------------------------------------
* ``{'date': {'mode': 'single', 'filter': 'custom', 'date_to': <as-at>}}``.
  Both reports carry ``filter_date_range eval="False"``
  (``aged_partner_balance.xml:5`` and ``:167``), so their date mode is
  ``single`` (``account_report.py:694``) — a ``range`` payload would be
  converted and any ``date_from`` ignored. ``default_opening_date_filter`` is
  ``today``, so failing to pin the date would silently produce a different
  as-at date on every run and nothing comparable to a printout.
* ``{'unfold_all': True}`` — honoured only because ``filter_unfold_all`` is
  True (``account_report.py:1605``). Without it the root line comes back
  foldable with no partner rows at all and Expected line 3 has nothing to read.
* ``aging_interval`` and ``aging_based_on`` are **verified, not assumed**.
  They default to 30 and ``base_on_maturity_date``
  (``account_aged_partner_balance.py:44-45``) and the bucket boundaries are
  computed from them (``:96-106``). If a customisation moved either, every
  bucket figure compared against the baseline is void, so this case BLOCKS
  rather than printing figures that would be quietly wrong.

Documented adaptation — the as-at date
--------------------------------------
The workbook says "Use the same as-at date as the Novobi baseline". A date is
derived, in this order, and always printed:

0. ``as_at`` out of the baseline file, when one has been transcribed — the
   only source that is the baseline's own date by construction;
1. the ``FG07_AS_AT_DATE`` environment variable, when the tester sets it to
   the baseline's own as-at date;
2. otherwise the latest accounting lock date on the acting company
   (``fiscalyear_lock_date`` / ``tax_lock_date`` / … —
   ``addons/account/models/company.py``), which on a migrated database is in
   practice the upgrade cut-off;
3. otherwise the date of the latest posted receivable-or-payable journal item.

None of the three depends on today's date, so a re-run against an unchanged
database reproduces the same figures — the property AUTOMATION_CONVENTIONS.md
rule 5 asks for. When none of the three yields a date the case BLOCKS, because
a report with no as-at date cannot be compared with anything.

Documented adaptation — no ``amount_residual`` shadow calculation
-----------------------------------------------------------------
It is tempting to recompute the ageing from ``account.move.line`` and assert
the report against it. That check would be wrong, not merely redundant: the
report computes a POINT-IN-TIME residual (``balance`` minus only those partial
reconciliations whose date falls on or before the as-at date —
``account_aged_partner_balance.py:196-213``), it ages on
``COALESCE(date_maturity, date)`` (``:235``), and by default it selects only
``trade_receivable`` / ``trade_payable`` accounts
(``account_report.py:1085-1095, 1112-1115``). A naive ``amount_residual``
comparison diverges for every invoice paid after the cut-off and would report
a correct report as broken. So it is not attempted, and the reason is logged.

Findings this case is built to surface
--------------------------------------
* **Six ageing buckets in v19, five in the workbook.** The workbook lists
  "current, 1-30, 31-60, 61-90, older"; v19 also shows ``91-120``. A v15
  baseline's "older" column therefore contains what v19 splits across
  ``91-120`` and ``Older``. This is logged as a FINDING and folded into the
  residual note so the human adds the two v19 columns before comparing —
  it is asserted in neither direction, because the workbook's own Expected
  Result speaks of "every ageing column total", not of a column count.
* **Only trade receivable / trade payable are in scope by default**
  (``account_report.py:1086-1095``: ``non_trade_receivable`` and
  ``non_trade_payable`` ship unselected). If the baseline was produced from a
  report that included non-trade accounts, the grand totals cannot match. The
  selected set is printed with the figures.
* **An "Unknown" partner row** (``account_report.py:7836-7837``) means
  receivable or payable amounts carrying no partner: money that appears in no
  customer's balance and that no collections list will ever chase. It is
  reported as a FINDING with its amount.

A weakness this docstring will not hide
---------------------------------------
``period0 + … + period5 == total`` holds by construction in stock v19 — the
engine literally computes ``total`` as that sum
(``account_aged_partner_balance.py:140``). Asserting it therefore guards
against a customised handler and against a currency-table anomaly, not against
an arithmetic slip in Odoo. The assertion that carries real weight is the
partner-rows-add-up-to-each-column one: those figures come from separate
grouped queries than the root line's single aggregate query.
"""
from __future__ import annotations

import csv
import datetime
import os

from adapters.base import OdooRPCError
from framework.baselines import baseline_path, load_baseline
from framework.registry import test_case
from tests.fg07.common import (LOCK_DATE_FIELDS, REPORT_LABEL,
                               REPORT_MENU_XMLID, REPORT_SECTION_XMLID,
                               WORKFLOW, WORKFLOW_NAME, acting_company,
                               cell_value, column_index, company_ctx,
                               fields_present, finding, menu_by_xmlid,
                               money, report_ref, require_account_reports,
                               residual_manual_step, run_report, trace)

RECEIVABLE_CSV = "TC-DAT-004-aged-receivable.csv"
PAYABLE_CSV = "TC-DAT-004-aged-payable.csv"

# The two sides of the case, in the workbook's own order: steps 1-5 on the
# receivable, then step 6 ("repeat steps 2 to 5") on the payable.
SIDES = (
    ("aged_receivable", "customers", RECEIVABLE_CSV),
    ("aged_payable", "vendors", PAYABLE_CSV),
)

# The SIX ageing columns, addressed by expression_label. Never by display
# name: period1..period4 are renamed at run time from options['aging_interval']
# (account_aged_partner_balance.py:48-53), so '1-30' is a label that only
# exists once the report has been opened, and only while the interval is 30.
BUCKET_LABELS = ("period0", "period1", "period2", "period3", "period4",
                 "period5")
TOTAL_LABEL = "total"

# The defaults every bucket figure in a baseline comparison depends on
# (account_aged_partner_balance.py:44-45).
EXPECTED_AGING_INTERVAL = 30
EXPECTED_AGING_BASIS = "base_on_maturity_date"

TOP_N = 10                 # the workbook's "top ten customers by balance"
CSV_LIMIT = 5000
AS_AT_ENV = "FG07_AS_AT_DATE"
TC_ID = "TC-DAT-004"

# How a human transcribing the old system's printout is allowed to key the
# ageing buckets. The workbook itself names five ("current, 1-30, 31-60,
# 61-90, older"), the v19 report has six, and the engine renames period1..4 at
# run time from options['aging_interval'] — so the file is accepted either in
# the engine's stable expression labels or in the names actually printed.
BUCKET_ALIASES = {
    "current": "period0", "at date": "period0", "not due": "period0",
    "0-30": "period1", "1-30": "period1",
    "31-60": "period2", "61-90": "period3", "91-120": "period4",
    "older": "period5", "120+": "period5", "older than 120": "period5",
}

# One cent of slack, and only on the partner-rows-versus-grand-total check.
# The grand total comes from one aggregate SQL query and the partner rows from
# per-partner grouped queries (account_report.py:7671-7730), so the two sums
# are made in a different order over the same cents; a sub-cent float
# difference is arithmetic, not a defect. Everything else compares exactly
# through money().
SUM_TOLERANCE = 0.01

FALLBACK_HEADER = ["rank", "partner"] + list(BUCKET_LABELS) + [TOTAL_LABEL]

NO_AS_AT_DATE = (
    "No as-at date could be established for the two aged partner reports. The "
    "workbook's test data is 'use the same as-at date as the Novobi baseline', "
    "and this database offers nothing to derive one from: the acting company "
    "carries no accounting lock date, and there is no posted journal item on "
    "any trade receivable or trade payable account. Either this is not the "
    "migrated database (in which case point the runner at the right one), or "
    "the receivable and payable ledgers are empty, which is itself the "
    "migration failure this case exists to find — check Accounting > "
    "Reporting > Partner Reports > Aged Receivable by hand before concluding "
    "anything. To pin the date explicitly, set the environment variable "
    + AS_AT_ENV + " to the baseline's own as-at date (YYYY-MM-DD) and re-run"
)

AGEING_CONFIG_CHANGED = (
    "The ageing configuration of the aged partner reports is not the Odoo "
    "default, so no bucket figure this case could print would be comparable "
    "with the Novobi baseline and the whole of the workbook's Expected Result "
    "line 2 ('every ageing column total matches') would be meaningless. Odoo "
    "19 defaults to a 30-day interval aged on the maturity date "
    "(enterprise-19.0/account_reports/models/account_aged_partner_balance.py:"
    "44-45), and the bucket boundaries are computed from those two values "
    "(:96-106). Restore the defaults, or obtain a baseline produced on the "
    "same settings, before re-running"
)


def _baseline_side(data: dict, key: str) -> dict:
    """One side of the Novobi baseline, normalised.

    ``{'total': float|None, 'buckets': {expression_label: float},
    'partners': [(name, float)] sorted by balance descending}``.

    Deliberately tolerant about SHAPE and strict about VALUES: the person
    transcribing a printout should not have to guess a schema, but every
    figure they do type is compared exactly through :func:`money`. Anything
    the file omits comes back absent and is handed to the residual step rather
    than being treated as zero — a missing key must never turn into a
    silently-passing comparison against 0.00.
    """
    raw = data.get(key)
    if raw is None:
        raw = data.get(key.replace("aged_", ""))     # 'receivable' / 'payable'
    if not isinstance(raw, dict):
        return {"total": None, "buckets": {}, "partners": []}

    total = raw.get("total")
    if total is None:
        total = raw.get("grand_total")

    buckets: dict[str, float] = {}
    for label, value in (raw.get("buckets") or {}).items():
        name = BUCKET_ALIASES.get(str(label).strip().lower(),
                                  str(label).strip().lower())
        if name in BUCKET_LABELS and isinstance(value, (int, float)):
            buckets[name] = money(value)

    partners: list[tuple] = []
    rows = raw.get("partners")
    if isinstance(rows, dict):
        items = list(rows.items())
    elif isinstance(rows, list):
        items = []
        for row in rows:
            if isinstance(row, dict):
                items.append((row.get("name") or row.get("partner"),
                              row.get("total") if row.get("total") is not None
                              else row.get("balance")))
            elif isinstance(row, (list, tuple)) and len(row) == 2:
                items.append((row[0], row[1]))
    else:
        items = []
    for name, value in items:
        if name in (None, "") or not isinstance(value, (int, float)):
            continue
        partners.append((str(name).strip(), money(value)))
    partners.sort(key=lambda row: -row[1])

    return {"total": None if total is None else money(total),
            "buckets": buckets, "partners": partners}


def _line_model(line_id) -> str:
    """The model of a report line, out of its generic id.

    A report line id is ``markup~model~value`` repeated once per hierarchy
    level and joined with ``|``
    (``enterprise-19.0/account_reports/models/account_report.py:2396-2402``).
    The LAST segment says what the line is: ``account.report.line`` for the
    report's own root line, ``res.partner`` for a partner group line,
    ``account.move.line`` for one open item under a partner, and an empty
    string for the synthetic prefix-group and total lines.

    Parsed here rather than through ``_get_model_info_from_id`` because Odoo
    refuses every leading-underscore method over RPC
    (``odoo/service/model.py``).
    """
    last = str(line_id or "").split("|")[-1]
    parts = last.rsplit("~", 2)
    return parts[1] if len(parts) == 3 else ""


def _as_at_date(ctx, company: dict, baseline: dict | None = None
                ) -> tuple[str, str]:
    """``(date, where it came from)`` — never today, so a re-run reproduces.

    See the module docstring for the derivation and why each step is
    deterministic.
    """
    rpc = ctx.adapter.rpc

    stated = str((baseline or {}).get("as_at")
                 or (baseline or {}).get("date_to") or "").strip()
    if stated:
        try:
            datetime.date.fromisoformat(stated)
        except ValueError:
            ctx.log(f"the baseline file names as_at={stated!r}, which is not "
                    f"an ISO date (YYYY-MM-DD) and was IGNORED")
        else:
            return stated, ("the 'as_at' date recorded in the Novobi baseline "
                            "file — the workbook's Test Data column verbatim")

    override = (os.environ.get(AS_AT_ENV) or "").strip()
    if override:
        try:
            datetime.date.fromisoformat(override)
        except ValueError:
            # A bad override must not silently become "today": say so loudly
            # and fall through to the database-derived date.
            ctx.log(f"{AS_AT_ENV}={override!r} is not an ISO date (YYYY-MM-DD) "
                    f"and was IGNORED — deriving the as-at date from the "
                    f"database instead")
        else:
            return override, (f"the {AS_AT_ENV} environment variable, set by "
                              f"the tester to match the Novobi baseline")

    readable = [name for name in LOCK_DATE_FIELDS
                if name in fields_present(rpc, "res.company", LOCK_DATE_FIELDS)]
    locks: dict[str, str] = {}
    if readable:
        try:
            row = rpc.call("res.company", "read", [company["id"]],
                           fields=readable,
                           context=company_ctx(company))[0]
        except (OdooRPCError, IndexError):
            row = {}
        locks = {name: str(row.get(name)) for name in readable
                 if row.get(name)}
    if locks:
        # ISO dates sort lexicographically, so max() is the latest lock.
        name, value = max(locks.items(), key=lambda item: item[1])
        return value, (f"res.company.{name} = {value}, the latest accounting "
                       f"lock date on the acting company — on a migrated "
                       f"database that is in practice the upgrade cut-off")

    try:
        rows = rpc.search_read(
            "account.move.line",
            [("parent_state", "=", "posted"),
             ("company_id", "=", company["id"]),
             ("account_id.account_type", "in",
              ["asset_receivable", "liability_payable"])],
            ["date"], order="date desc", limit=1,
            context=company_ctx(company))
    except OdooRPCError as exc:
        ctx.log(f"could not read the latest posted receivable/payable journal "
                f"item ({exc})")
        rows = []
    if rows and rows[0].get("date"):
        value = str(rows[0]["date"])
        return value, (f"the date of the latest posted receivable or payable "
                       f"journal item in this company ({value}) — the company "
                       f"carries no accounting lock date to use instead")
    return "", ""


def _capture(ctx, key: str, cutoff: str, company: dict) -> dict:
    """Open one aged partner report at ``cutoff`` and read everything off it.

    Deliberately assertion-free. Every figure the human needs is captured and
    logged BEFORE any check runs, so that a failing assertion still leaves the
    full evidence in the log and in the CSV — a check raises, and anything
    gathered after it would never happen.
    """
    data = {
        "key": key,
        "menu": REPORT_LABEL[key],
        "name": key.replace("_", " ").title(),
        "opened": False,
        "error": "",
        "line_count": 0,
        "roots": [],
        "missing_columns": [],
        "bucket_names": {},
        "grand": {},
        "grand_total": 0.0,
        "partners": [],
        "unknown_partner": None,
        "aging_interval": None,
        "aging_basis": "",
        "account_types": [],
        "all_entries": None,
        "date_to": "",
        "header": list(FALLBACK_HEADER),
        "rows": [],
    }

    report_id = report_ref(ctx, key)      # BLOCKs when the xmlid is absent
    options = {
        # mode 'single' because filter_date_range is eval="False" on both
        # reports (aged_partner_balance.xml:5, :167); a 'range' payload would
        # be converted by _init_options_date and date_from ignored.
        "date": {"mode": "single", "filter": "custom", "date_to": cutoff},
        # honoured because filter_unfold_all is eval="True" on both (:6, :168)
        "unfold_all": True,
    }
    try:
        opts, info = run_report(ctx, report_id, options, company)
    except OdooRPCError as exc:
        # A report that will not open is a finding about the report, not an
        # automation error: it is recorded and asserted on below.
        data["error"] = str(exc)
        ctx.log(f"{data['menu']} did NOT open: {exc}")
        return data

    data["opened"] = True
    data["name"] = ((info.get("report") or {}).get("name")
                    or REPORT_LABEL[key])
    data["date_to"] = str((opts.get("date") or {}).get("date_to") or "")
    data["aging_interval"] = opts.get("aging_interval")
    data["aging_basis"] = str(opts.get("aging_based_on") or "")
    data["all_entries"] = opts.get("all_entries")
    data["account_types"] = [entry.get("id")
                             for entry in (opts.get("account_type") or [])
                             if entry.get("selected")]

    # Column indices by expression_label. Position is never used: the visible
    # column set changes with show_currency / show_account
    # (account_aged_partner_balance.py:20-36).
    index = {}
    for label in list(BUCKET_LABELS) + [TOTAL_LABEL]:
        position = column_index(opts, label)
        index[label] = position
        if position < 0:
            data["missing_columns"].append(label)
    for column in (opts.get("columns") or []):
        label = column.get("expression_label")
        if label in BUCKET_LABELS:
            data["bucket_names"][label] = str(column.get("name") or label)

    lines = info.get("lines") or []
    data["line_count"] = len(lines)

    # The root line. Each report declares exactly one report line
    # (aged_partner_balance.xml:135 / :236) and, because its groupby is
    # 'partner_id, id', its own columns ARE the grand totals.
    roots = [line for line in lines
             if _line_model(line.get("id")) == "account.report.line"]
    data["roots"] = [str(line.get("name") or "") for line in roots]
    if roots:
        root = roots[0]
        data["grand"] = {label: money(cell_value(root, index[label]))
                         for label in BUCKET_LABELS}
        data["grand_total"] = money(cell_value(root, index[TOTAL_LABEL]))

    for line in lines:
        if _line_model(line.get("id")) != "res.partner":
            continue
        row = {
            "partner": str(line.get("name") or ""),
            "buckets": {label: money(cell_value(line, index[label]))
                        for label in BUCKET_LABELS},
            "total": money(cell_value(line, index[TOTAL_LABEL])),
        }
        data["partners"].append(row)
        # A partner group line whose grouping key was NULL is named "Unknown"
        # (account_report.py:7836-7837) — receivable money attached to nobody.
        if not str(line.get("id") or "").rsplit("~", 1)[-1]:
            data["unknown_partner"] = row

    # "Top ten by balance": biggest owed first. Both reports return positive
    # amounts — the payable engine multiplies by -1
    # (account_aged_partner_balance.py:167) — so a plain descending sort is
    # the right one, and a credit-note-driven negative balance sorts last.
    data["partners"].sort(key=lambda row: -row["total"])

    data["header"] = (["rank", "partner"]
                      + [f"{label} ({data['bucket_names'].get(label, label)})"
                         for label in BUCKET_LABELS]
                      + [TOTAL_LABEL])
    data["rows"] = [["", f"GRAND TOTAL — the report's own {data['name']} line "
                         f"as at {data['date_to']}"]
                    + [data["grand"].get(label, "") for label in BUCKET_LABELS]
                    + [data["grand_total"]]]
    for rank, row in enumerate(data["partners"][:CSV_LIMIT], start=1):
        data["rows"].append([rank, row["partner"]]
                            + [row["buckets"][label] for label in BUCKET_LABELS]
                            + [row["total"]])
    return data


def _log_capture(ctx, data: dict):
    """Print one side's figures in the shape a human ticks off a printout."""
    if not data["opened"]:
        return
    ctx.log(f"{data['menu']} — report {data['name']!r} as at "
            f"{data['date_to']}, {data['line_count']} report line(s), "
            f"{len(data['partners'])} partner row(s)")
    ctx.log(f"    ageing: interval={data['aging_interval']} day(s), "
            f"based on {data['aging_basis']!r}; account types in scope="
            f"{data['account_types']}; draft entries included="
            f"{data['all_entries']!r}")
    for label in BUCKET_LABELS:
        ctx.log(f"    {label:<8} {data['bucket_names'].get(label, label):<10} "
                f"{data['grand'].get(label, 0.0):>16,.2f}")
    ctx.log(f"    {'TOTAL':<19} {data['grand_total']:>16,.2f}")
    for rank, row in enumerate(data["partners"][:TOP_N], start=1):
        ctx.log(f"    #{rank:>2} {row['partner'][:48]:<48} "
                f"{row['total']:>16,.2f}")


@test_case(
    id="TEST-FG07-DAT-004",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module="account_reports",
    priority="P0",
    kind="DATA",
    order=702,
    name="What customers owe and what the gallery owes still matches",
    description="Read-only capture of the v19 Aged Receivable and Aged "
                "Payable reports at one fixed as-at date: both grand totals, "
                "all six ageing bucket totals and the top ten partners per "
                "side, with the ageing settings verified, the partner rows "
                "proven to add up to every column, and the baseline "
                "comparison left as a residual manual step. Creates nothing.",
    traceability=trace("TC-DAT-004"))
def test_dat_004(ctx):
    # Declared before the try: the evidence block runs from `finally` and must
    # never raise a NameError over a step an earlier failure skipped — that
    # would replace a real FAILED or BLOCKED verdict with an AUTOMATION_ERROR.
    sides: dict[str, dict] = {}
    residual: list[str] = []
    cutoff = ""
    baseline: dict = {}

    with ctx.step("Precondition (workbook): TC-DAT-002 has passed, and Novobi "
                  "has given you the aged receivable and aged payable reports "
                  "from the old system, both as at the upgrade cut-off date"):
        # ir.module.module, never model_exists: account.report exists in
        # Community with no engine at all, so its presence proves nothing
        # (tests/fg07/common.py:39-48).
        require_account_reports(ctx)
        company = acting_company(ctx)
        ctx.log(f"acting company #{company['id']} {company['name']!r} — "
                f"company currency {company['currency_name']}")
        # The workbook's precondition is "Novobi has given you the aged
        # receivable and aged payable reports from the old system". When those
        # figures have been transcribed into the platform's own baseline file
        # the three Expected Result lines are ASSERTED; when they have not,
        # each one falls back to a residual manual step carrying the captured
        # v19 figures. Nothing is ever invented in the baseline's place.
        stored = load_baseline(TC_ID) or {}
        baseline = stored.get("data") or {}
        if stored:
            ctx.log(f"baseline file found: {baseline_path(TC_ID)} — captured "
                    f"{stored.get('captured_at')!r} from "
                    f"{stored.get('captured_env')!r}/"
                    f"{stored.get('captured_db')!r}")
        else:
            ctx.log(f"no baseline file at {baseline_path(TC_ID)} — the three "
                    f"Expected Result lines become residual manual steps "
                    f"carrying the v19 figures, and nothing is invented in "
                    f"their place")

        cutoff, provenance = _as_at_date(ctx, company, baseline)
        if not cutoff:
            ctx.blocked(NO_AS_AT_DATE)
        ctx.log(f"as-at date for BOTH reports: {cutoff} — from {provenance}")
        ctx.log("NOT attempted, deliberately: recomputing the ageing from "
                "account.move.line.amount_residual. The report's residual is "
                "point-in-time (only partial reconciliations dated on or "
                "before the as-at date are subtracted, "
                "account_aged_partner_balance.py:196-213) and it ages on "
                "COALESCE(date_maturity, date) (:235), so every invoice paid "
                "after the cut-off would diverge and a correct report would "
                "be reported as broken")

    try:
        with ctx.step("Steps 1 and 6: Accounting > Reporting > Partner "
                      "Reports > Aged Receivable, then Aged Payable"):
            # The workbook's navigation is asserted, not trusted: a report
            # that exists but hangs off no menu is not reachable by the
            # accountant the workbook addresses.
            misplaced = []
            for key, _who, _csv_name in SIDES:
                menu = menu_by_xmlid(ctx, REPORT_MENU_XMLID[key])
                section = menu_by_xmlid(ctx, REPORT_SECTION_XMLID[key])
                ctx.log(f"{REPORT_LABEL[key]} -> menu {menu.get('name')!r} "
                        f"under {menu.get('parent_name')!r} "
                        f"(action {menu.get('action')!r})")
                if not menu:
                    misplaced.append(
                        f"{REPORT_LABEL[key]}: the menu "
                        f"{REPORT_MENU_XMLID[key]} does not resolve, or this "
                        f"user may not see it (ir.ui.menu is group-filtered; "
                        f"the workbook's Run By is 'Client (Accountant)')")
                elif not section:
                    misplaced.append(
                        f"{REPORT_LABEL[key]}: the Partner Reports section "
                        f"{REPORT_SECTION_XMLID[key]} does not resolve")
                elif menu.get("parent_id") != section.get("id"):
                    misplaced.append(
                        f"{REPORT_LABEL[key]}: the menu sits under "
                        f"{menu.get('parent_name')!r}, not under the Partner "
                        f"Reports section {section.get('name')!r}")
            ctx.check("Both aged partner reports are reachable where the "
                      "workbook says they are — Accounting > Reporting > "
                      "Partner Reports", [], misplaced)

        with ctx.step("Steps 2-5 and 6: set the as-at date to match the "
                      "baseline and read both reports right through"):
            for key, _who, _csv_name in SIDES:
                sides[key] = _capture(ctx, key, cutoff, company)
                _log_capture(ctx, sides[key])

            failed_to_open = [f"{data['menu']}: {data['error']}"
                              for data in sides.values()
                              if not data["opened"]]
            ctx.check("Both aged partner reports open at the as-at date "
                      "(account.report.get_options then "
                      "get_report_information, the two calls the client "
                      "itself makes)", [], failed_to_open)

            wrong_date = [f"{data['menu']}: the report came back as at "
                          f"{data['date_to']!r}, not {cutoff!r}"
                          for data in sides.values()
                          if data["date_to"] != cutoff]
            ctx.check("Both reports honoured the as-at date the tester set, "
                      "so the two printouts describe the same moment "
                      "(options['date']['date_to'])", [], wrong_date)

        with ctx.step("Guard on Expected line 2: the ageing settings the "
                      "bucket figures depend on are Odoo's defaults"):
            # Not an assertion but a BLOCK: with a different interval or a
            # different ageing basis the buckets are simply not the same
            # buckets as the baseline's, and printing them would invite a
            # comparison that cannot mean anything.
            for data in sides.values():
                if (data["aging_interval"] != EXPECTED_AGING_INTERVAL
                        or data["aging_basis"] != EXPECTED_AGING_BASIS):
                    ctx.blocked(
                        f"{AGEING_CONFIG_CHANGED}. {data['menu']} came back "
                        f"with aging_interval={data['aging_interval']!r} "
                        f"(expected {EXPECTED_AGING_INTERVAL}) and "
                        f"aging_based_on={data['aging_basis']!r} (expected "
                        f"{EXPECTED_AGING_BASIS!r})")
            ctx.log(f"both reports age on {EXPECTED_AGING_BASIS!r} in "
                    f"{EXPECTED_AGING_INTERVAL}-day buckets — the bucket "
                    f"boundaries are therefore the standard ones and the "
                    f"baseline comparison is meaningful")

        with ctx.step("Expected line 2: every ageing column exists — six of "
                      "them, keyed by expression label"):
            missing = []
            for data in sides.values():
                for label in data["missing_columns"]:
                    missing.append(f"{data['menu']}: no column with "
                                   f"expression_label {label!r}")
            # Named columns, never positions: show_currency / show_account
            # add and remove columns around them
            # (account_aged_partner_balance.py:20-36).
            ctx.check("Both reports carry all six ageing columns period0…"
                      "period5 and a Total column (addressed by "
                      "expression_label, never by position or by the "
                      "run-time-renamed display name)", [], missing)

            # The workbook names five buckets; v19 shows six. Reported, never
            # asserted — the Expected Result speaks of column totals, not of a
            # column count, and inventing a count expectation would be
            # inventing a requirement.
            for data in sides.values():
                shown = ", ".join(f"{label}={data['bucket_names'].get(label, label)!r}"
                                  for label in BUCKET_LABELS)
                finding(ctx, f"{data['menu']} shows SIX ageing buckets "
                             f"({shown}), while the workbook's step 4 names "
                             f"five (current, 1-30, 31-60, 61-90, older). A "
                             f"v15 baseline's 'older' column corresponds to "
                             f"v19's '91-120' PLUS 'Older' — add those two "
                             f"before comparing, or the last bucket will look "
                             f"short and the one before it will look invented")
                if any(not str(kind).startswith("trade_")
                       for kind in data["account_types"]):
                    finding(ctx, f"{data['menu']} has non-trade accounts "
                                 f"selected ({data['account_types']}). Odoo "
                                 f"ships them unselected "
                                 f"(account_report.py:1086-1095), so a "
                                 f"baseline produced with the defaults will "
                                 f"not match this run's grand total")

        with ctx.step("Expected line 1 (the printout-free half): on each "
                      "report the six buckets add up to the Total column"):
            unbalanced = []
            for data in sides.values():
                bucket_sum = money(sum(data["grand"].get(label, 0.0)
                                       for label in BUCKET_LABELS))
                if bucket_sum != data["grand_total"]:
                    unbalanced.append(
                        f"{data['menu']}: the six buckets add to "
                        f"{bucket_sum:,.2f} but the Total column reads "
                        f"{data['grand_total']:,.2f} (difference "
                        f"{money(bucket_sum - data['grand_total']):,.2f})")
            ctx.check("On both reports period0 + period1 + period2 + period3 "
                      "+ period4 + period5 equals the Total column, so the "
                      "grand total and the buckets tell the same story", [],
                      unbalanced)

        with ctx.step("Step 5 and Expected line 3: the partner rows behind "
                      "the totals — the top ten by balance"):
            empty = [data["menu"] for data in sides.values()
                     if not data["partners"]]
            for name in empty:
                ctx.log(f"{name} returned no partner row at {cutoff} — either "
                        f"nothing is outstanding on that side at the as-at "
                        f"date, or the ledger did not come across")
            # Both sides empty is not a business state: it means the reports,
            # the as-at date or the migration is wrong. One side empty can be
            # legitimate (a gallery may owe nothing at a cut-off), so it is
            # reported rather than failed — the platform holds no baseline
            # that could tell the two apart.
            ctx.check_true(
                "At least one of the two aged partner reports returned a "
                "partner row at the as-at date, so there is a collections "
                "list to compare at all",
                any(data["partners"] for data in sides.values()),
                actual_desc=f"Aged Receivable: "
                            f"{len(sides['aged_receivable']['partners'])} "
                            f"partner row(s); Aged Payable: "
                            f"{len(sides['aged_payable']['partners'])} "
                            f"partner row(s), as at {cutoff}")

            duplicated = []
            for data in sides.values():
                seen: dict[str, int] = {}
                for row in data["partners"]:
                    seen[row["partner"]] = seen.get(row["partner"], 0) + 1
                duplicated.extend(
                    f"{data['menu']}: {name!r} appears on {count} separate "
                    f"rows" for name, count in seen.items() if count > 1)
            # Two rows for one customer would split a balance across two
            # entries in the collections list and could hide a debt below the
            # top ten.
            ctx.check("No partner appears on more than one row of either "
                      "report", [], duplicated)

            for data in sides.values():
                if data["unknown_partner"]:
                    finding(ctx, f"{data['menu']} carries an 'Unknown' partner "
                                 f"row of "
                                 f"{data['unknown_partner']['total']:,.2f} — "
                                 f"receivable or payable amounts posted with "
                                 f"no partner. They are inside the grand "
                                 f"total but inside nobody's balance, so no "
                                 f"collections list will ever chase them "
                                 f"(account_report.py:7836-7837)")

        with ctx.step("Expected line 2 (the printout-free half): the partner "
                      "rows add up to every ageing column, not just to the "
                      "grand total"):
            # This is the workbook's own worry read from the inside: "a right
            # total in the wrong bucket still means the wrong collections
            # list". The grand total comes from one aggregate query and the
            # partner rows from per-partner grouped queries, so agreement
            # column by column is a real property, not an identity.
            mismatched = []
            for data in sides.values():
                if not data["partners"]:
                    continue
                for label in list(BUCKET_LABELS) + [TOTAL_LABEL]:
                    if label == TOTAL_LABEL:
                        rolled = money(sum(row["total"]
                                           for row in data["partners"]))
                        expected = data["grand_total"]
                    else:
                        rolled = money(sum(row["buckets"][label]
                                           for row in data["partners"]))
                        expected = data["grand"].get(label, 0.0)
                    if abs(rolled - expected) > SUM_TOLERANCE:
                        mismatched.append(
                            f"{data['menu']} column {label} "
                            f"({data['bucket_names'].get(label, label)}): the "
                            f"{len(data['partners'])} partner rows add to "
                            f"{rolled:,.2f} but the report's own total reads "
                            f"{expected:,.2f} (difference "
                            f"{money(rolled - expected):,.2f})")
            ctx.check("On both reports the partner rows add up to every "
                      "ageing column total and to the grand total, so no "
                      "customer's balance is missing from the collections "
                      "list and none is counted twice", [], mismatched)

        with ctx.step("The baseline comparison (workbook Expected Result) — "
                      "the figures a human must tick off against Novobi's "
                      "two reports"):
            for key, who, csv_name in SIDES:
                data = sides[key]
                buckets = "; ".join(
                    f"{data['bucket_names'].get(label, label)} "
                    f"({label})={data['grand'].get(label, 0.0):,.2f}"
                    for label in BUCKET_LABELS)
                top = "; ".join(
                    f"#{rank} {row['partner']}={row['total']:,.2f}"
                    for rank, row in enumerate(data["partners"][:TOP_N],
                                               start=1)) or "(none)"
                residual.append(
                    f"{data['menu']} as at {cutoff} — the v19 side of the "
                    f"comparison against the Novobi baseline"
                    + (", which the step below ASSERTS from "
                       f"{baseline_path(TC_ID)}" if baseline
                       else ", which this platform does not hold")
                    + f". GRAND TOTAL = {data['grand_total']:,.2f}. AGEING "
                    f"COLUMNS: {buckets}. TOP {TOP_N} {who.upper()} BY "
                    f"BALANCE: {top}. Every partner row is in {csv_name}. "
                    f"Note before comparing: v19 shows SIX buckets, so a v15 "
                    f"'older' figure must be compared against 91-120 plus "
                    f"Older added together; the report covers "
                    f"{data['account_types']} accounts only; draft entries "
                    f"included = {data['all_entries']!r}.")
            residual.append(
                "If the figures do not match, the workbook's If It Fails asks "
                "you to attach all four reports (two baseline, two v19) and "
                "to say WHICH shape the mismatch has, because they point at "
                "different things: the GRAND TOTAL matching while the buckets "
                "differ is a DUE-DATE problem (invoice_date/date_maturity did "
                "not come across intact — the report ages on "
                "COALESCE(date_maturity, date)); the GRAND TOTAL itself "
                "differing is an OPEN-BALANCE problem (residuals, "
                "reconciliation or missing invoices). Novobi will investigate "
                "the two differently. Both v19 CSVs are attached to this run; "
                f"the as-at date used was {cutoff}, and you can pin it to the "
                f"baseline's own date by setting {AS_AT_ENV} and re-running.")
            if not baseline:
                residual.append(
                    "To have the platform ASSERT all three Expected Result "
                    "lines on the next run instead of handing them back, "
                    f"transcribe the two old-system reports into "
                    f"{baseline_path(TC_ID)} as "
                    '{"data": {"as_at": "YYYY-MM-DD", "aged_receivable": '
                    '{"total": …, "buckets": {"current": …, "1-30": …, '
                    '"31-60": …, "61-90": …, "91-120": …, "older": …}, '
                    '"partners": {"<name>": …}}, "aged_payable": {…}}} — '
                    "every key is optional and only the keys present are "
                    "compared, so a partial transcription still asserts what "
                    "it names.")

        with ctx.step("Expected lines 1, 2 and 3 against the Novobi baseline: "
                      "grand totals, every ageing column, and the top ten "
                      "partners name by name and figure by figure"):
            # The residual notes above are queued BEFORE these assertions on
            # purpose: ctx.check raises on the first failure, and a note
            # appended after it would never reach the evidence block — the
            # human would lose the captured figures precisely on the run where
            # they matter most.
            if not baseline:
                ctx.log("no Novobi baseline was supplied, so Expected Result "
                        "lines 1, 2 and 3 stand as the residual manual steps "
                        "recorded above, each carrying the v19 figure it is "
                        "to be compared against. They are NOT asserted here, "
                        "because the platform holds no old-system figure and "
                        "must not invent one")
            else:
                # Everything the baseline DOES NOT state is worked out and
                # queued as a residual first, before a single assertion runs:
                # ctx.check raises on the first failure, so a note appended
                # afterwards would be lost on exactly the run that needs it.
                wants = {key: _baseline_side(baseline, key)
                         for key, _who, _csv in SIDES}
                unstated = []
                for key, who, _csv_name in SIDES:
                    want, data = wants[key], sides[key]
                    if want["total"] is None:
                        unstated.append(f"{data['menu']}: grand total")
                    if not want["buckets"]:
                        unstated.append(f"{data['menu']}: ageing columns")
                    if not want["partners"]:
                        unstated.append(f"{data['menu']}: top {TOP_N} {who}")
                if unstated:
                    # A partial transcription must not quietly shrink the
                    # Expected Result to whichever figures were typed in.
                    residual.append(
                        f"The baseline file {baseline_path(TC_ID)} does not "
                        f"state {unstated}, so those comparisons were NOT "
                        f"asserted — tick them off by hand against the "
                        f"figures recorded above, and add them to the file to "
                        f"have the platform assert them next time.")

                # Expected line 1 — "Both grand totals match the baseline
                # exactly." One assertion per side rather than one over both,
                # so the log names WHICH side moved: the workbook's If It
                # Fails column treats receivable and payable as separate
                # investigations.
                for key, who, _csv_name in SIDES:
                    want = wants[key]
                    data = sides[key]
                    if want["total"] is None:
                        ctx.log(f"{data['menu']}: the baseline states no "
                                f"grand total — deferred above, not asserted")
                    else:
                        ctx.check(
                            f"{data['menu']} — the grand total matches the "
                            f"Novobi baseline exactly",
                            want["total"], data["grand_total"])

                    # Expected line 2 — "Every ageing column total matches."
                    # An offender list, not a first-difference: a right total
                    # in the wrong bucket usually moves TWO columns, and the
                    # workbook's diagnosis needs both named.
                    if not want["buckets"]:
                        ctx.log(f"{data['menu']}: the baseline states no "
                                f"ageing column — deferred above, not "
                                f"asserted")
                    else:
                        wrong_bucket = [
                            f"{label} "
                            f"({data['bucket_names'].get(label, label)}): "
                            f"baseline {value:,.2f} vs v19 "
                            f"{data['grand'].get(label, 0.0):,.2f} "
                            f"(difference "
                            f"{money(data['grand'].get(label, 0.0) - value):+,.2f})"
                            for label, value in sorted(want["buckets"].items())
                            if money(data["grand"].get(label, 0.0)) != value]
                        ctx.check(
                            f"{data['menu']} — every ageing column total "
                            f"named by the baseline matches "
                            f"({sorted(want['buckets'])})",
                            [], wrong_bucket)

                    # Expected line 3 — "The top ten customers and top ten
                    # vendors, and their balances, match." Rank by rank, which
                    # is workbook step 5's "name by name and figure by
                    # figure"; a name in the wrong position is a different
                    # collections list even when every figure is present.
                    if not want["partners"]:
                        ctx.log(f"{data['menu']}: the baseline lists no "
                                f"{who} — deferred above, not asserted")
                    else:
                        got_top = [(row["partner"], row["total"])
                                   for row in data["partners"][:TOP_N]]
                        want_top = want["partners"][:TOP_N]
                        ctx.check(
                            f"{data['menu']} — the top {TOP_N} {who} and "
                            f"their balances match the Novobi baseline, name "
                            f"by name and figure by figure",
                            want_top, got_top)
    finally:
        with ctx.step("Evidence: write the aged receivable and aged payable "
                      "CSVs"):
            for key, _who, csv_name in SIDES:
                data = sides.get(key) or {}
                header = data.get("header") or list(FALLBACK_HEADER)
                rows = data.get("rows") or []
                path = ctx.artifacts_dir / csv_name
                try:
                    with path.open("w", newline="", encoding="utf-8") as fh:
                        writer = csv.writer(fh)
                        writer.writerow(header)
                        writer.writerows(rows)
                    ctx.add_artifact(path, "log", csv_name)
                    ctx.log(f"wrote {len(rows)} row(s) to {csv_name}")
                except OSError as exc:
                    ctx.log(f"could not write {csv_name} ({exc}) — the figures "
                            f"above are still in this log")
            for note in residual:
                residual_manual_step(ctx, note)
            ctx.log("NOTHING WAS CREATED OR MODIFIED by this case — the "
                    "workbook's State After The Test is 'Nothing changed. "
                    "Keep both exports.', so no sweep and no cleanup runs "
                    "here either (a sweep is itself a delete).")
