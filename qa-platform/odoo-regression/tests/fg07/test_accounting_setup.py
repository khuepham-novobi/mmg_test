"""FG-07 — TC-SMK-015: company, chart of accounts and fiscal settings are unchanged.

Implements row 43.0 (P0, "Accounting setup") of the CLIENT MANUAL TESTING
GUIDELINE ``MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0.xlsx`` /
sheet ``Testing Guideline``.

The workbook's framing: *"Every figure the gallery reports comes out of the
chart of accounts and the company's fiscal settings. If an account was
renumbered or a fiscal year moved during the upgrade, every report after it is
wrong in a way that is very hard to trace back."* It is the first case in
FG-07 by the workbook's own instruction ("Run this FIRST in FG-07"), because
it is what decides whether TC-DAT-002 and TC-DAT-004 can be trusted at all.

Read-only by construction
-------------------------
The workbook's *State After The Test* is "Nothing changed" and its *Test Data*
is "Use the Novobi baseline. Do not change anything." This module therefore
creates no record, writes no field, and calls neither ``sweep_fg07`` nor
``cleanup`` — a sweep is itself a delete.

The 4 Expected Result lines, and what each is read from
------------------------------------------------------
1. **"Company name, address, Tax ID and Currency all match."** — read from
   ``res.company`` fields ``name`` (``odoo/addons/base/models/
   res_company.py:48``), ``street``/``street2``/``zip``/``city``/``state_id``/
   ``country_id`` (:69-78, all non-stored computes proxied off
   ``partner_id``, so they are readable but NOT usable in a search domain),
   ``vat`` — labelled "Tax ID" (:84) — ``company_registry`` labelled
   "Company ID" (:85) and ``currency_id`` (:67).
2. **"The account count matches the baseline, and the three sampled accounts
   have the same name and type."** — count from
   ``account.account.search_count([])`` with the company pinned through
   ``allowed_company_ids``, which is exactly what the Chart of Accounts menu
   does: its action carries no context and no default filter
   (``addons/account/views/account_account_views.xml:173-178``) and the
   multi-company ``ir.rule`` is ``[('company_ids','parent_of',company_ids)]``
   (``addons/account/security/account_security.xml:154-155``). A
   ``('company_id','=',cid)`` domain — the v15 shape — raises in v19, because
   ``company_ids`` is a Many2many (``addons/account/models/
   account_account.py:97``). The sampled rows are read with
   ``code``/``name``/``account_type``/``internal_group``/``active``.
3. **"Fiscal year end and lock dates match."** — read from
   ``res.company.fiscalyear_last_day`` / ``fiscalyear_last_month``
   (``addons/account/models/company.py:74-75``) and the five v19 lock dates
   ``fiscalyear_lock_date`` / ``tax_lock_date`` / ``sale_lock_date`` /
   ``purchase_lock_date`` / ``hard_lock_date`` (:76-102).
4. **"Every journal the gallery uses is present with the same short code."** —
   read from ``account.journal`` ``name``/``code``/``type``/``active``, with
   ``active_test`` off so an archived journal is reported as archived rather
   than as missing. ``code`` is v19's "Sequence Prefix", ``size=5``
   (``addons/account/models/account_journal.py:97-99``).

Workbook step 6 reads the tax count. It has **no** Expected Result line of its
own, so the tax figures are captured as evidence and handed to the human, and
nothing is asserted about them.

Documented adaptation — the Novobi baseline
-------------------------------------------
Every one of the four lines above is a comparison against figures Novobi
supplies from the old system. The platform does not hold those figures and
must never invent them. So this case does three things instead:

* it **captures** every number and field the workbook's six steps read, prints
  them into the execution log and writes them to three CSV artifacts, so the
  human step is a tick-off and never a re-run;
* it **asserts for real** every invariant that needs no baseline — the address
  components an invoice prints are populated, the currency is a live currency,
  no two accounts in the company share a code, no account carries an
  ``account_type`` outside the v19 selection, a search on each sampled code
  returns the very account it was read from and that account is not archived,
  the four journal families invoicing depends on all exist, and every journal
  carries a sequence prefix;
* it names the baseline comparison itself as a RESIDUAL MANUAL STEP with the
  captured values in the message, per Expected Result line.

Adaptation — the account_type taxonomy
--------------------------------------
The workbook's step 3 says "confirm each one's ... type match". v15's
``account.account.user_type_id`` and the model ``account.account.type`` are
gone in v19; the type is now the Selection ``account_type``
(``addons/account/models/account_account.py:44-66``). A v15 type LABEL that
reads differently in v19 is therefore a taxonomy-mapping question, not a data
defect, so the full v19 label map is printed for the human and only
membership of the selection is asserted.

Findings this case is built to surface
--------------------------------------
* ``period_lock_date`` — v15's fourth lock date — **does not exist in v19**
  (``addons/account/models/company.py:76-102`` lists five, and that is not one
  of them). A baseline value for it has no v19 equivalent. Recorded as an
  OBSERVATION and asserted in neither direction.
* **The workbook's own navigation for step 4 is wrong on v19.** Settings >
  Fiscal Periods contains only the Fiscal Year setting — and that setting is
  ``invisible="1"`` in Community (``addons/account/views/
  res_config_settings_views.xml:347-349``), un-hidden only by the Enterprise
  ``account_accountant`` module (``enterprise-19.0/account_accountant/views/
  res_config_settings_views.xml:8-16``). The lock dates are not on that screen
  at all: they moved behind the ``account.change.lock.date`` wizard at
  Accounting > Accounting > Closing > **Lock Dates…**
  (``enterprise-19.0/account_accountant/wizard/
  account_change_lock_date.xml:232-246``). Recorded as a FINDING against the
  workbook, with the values still read straight off ``res.company``.
* **``l10n_generic_coa`` is not a module in Odoo 19.** The workbook's Module
  column names it, but the generic chart now ships as template data inside
  ``account`` itself (``addons/account/data/template/
  account.account-generic_coa.csv``), and ``l10n_us`` has been reduced to a
  bank-account localisation depending only on ``base``
  (``addons/l10n_us/__manifest__.py``). Both module states are reported; only
  ``account`` blocks.
* **``account.journal.code`` is capped at 5 characters in v19**
  (``addons/account/models/account_journal.py:97-99``). Any baseline short
  code longer than five characters cannot have survived intact, so every
  journal sitting exactly at the cap is listed as a truncation candidate.
* ``account.account.code`` is a company-dependent compute over ``code_store``
  and its ``_search_code`` disables ``active_test``
  (``addons/account/models/account_account.py:39-40, 342-343``), so a search
  by code can surface an **archived** account. Its uniqueness is enforced by
  the Python constraint ``_ensure_code_is_unique`` (:1096-1113), not by a
  database constraint — so migrated data can violate it and nothing will
  notice until a report double-counts. That is asserted here.
* ``res.company.payment_default_journal_id`` (the ``mmg_default_payment_
  journal`` field TC-INV-006 and TC-INV-008 are built on) is probed here so
  its absence is known one case early rather than at order 707.
"""
from __future__ import annotations

import csv

from adapters.base import OdooRPCError
from framework.registry import test_case
from tests.fg07.common import (FISCAL_FIELDS, LOCK_DATE_FIELDS,
                               LOCK_DATE_REMOVED_IN_V19, WORKFLOW,
                               WORKFLOW_NAME, acting_company, company_ctx,
                               fields_present, finding, m2o_id, m2o_name,
                               menu_by_xmlid, module_state, observation,
                               require_module, require_v19,
                               residual_manual_step, selection_labels, trace)

ACCOUNTS_CSV = "TC-SMK-015-accounts.csv"
JOURNALS_CSV = "TC-SMK-015-journals.csv"
SUMMARY_CSV = "TC-SMK-015-company-and-counts.csv"
CSV_LIMIT = 20000

# The workbook's Module(s) column. Only 'account' is a real gate: without it
# there is no chart of accounts to read at all. The other two are reported.
NO_ACCOUNT_MODULE = (
    "'account' (Invoicing) is not installed on this database, so there is no "
    "chart of accounts, no journal, no tax and no fiscal setting for this "
    "case to read. Nothing in FG-07 can run until it is installed — this is "
    "the precondition every other case in the suite inherits"
)

# Enterprise module that un-hides Settings > Fiscal Periods > Fiscal Year and
# that owns the Lock Dates… wizard the lock dates moved into.
ACCOUNTANT_MODULE = "account_accountant"
LOCK_DATE_MENU_XMLID = "account_accountant.menu_action_change_lock_date"

# The address components an invoice header prints. A blank one cannot match a
# printed baseline address that carries it, so this is the printout-free half
# of Expected Result line 1.
ADDRESS_FIELDS = (("street", "Street"), ("city", "City"), ("zip", "ZIP"),
                  ("country_id", "Country"))

# Journal families invoicing depends on. 'bank' / 'cash' / 'credit' are one
# family — a gallery needs somewhere to bank money, not all three. v19 added
# 'credit' (Credit Card) as a sixth type
# (addons/account/models/account_journal.py:106-113).
JOURNAL_FAMILIES = (
    ("a Sales journal (customer invoices)", ("sale",)),
    ("a Purchase journal (vendor bills)", ("purchase",)),
    ("a Miscellaneous journal (manual entries)", ("general",)),
    ("at least one money journal (Bank, Cash or Credit Card)",
     ("bank", "cash", "credit")),
)

# v19's Sequence Prefix cap (account_journal.py:99). A v15 short code longer
# than this cannot have migrated intact.
JOURNAL_CODE_SIZE = 5


def _search_count(ctx, model: str, domain: list, context: dict) -> int:
    """``search_count`` — public, and the figure the list view's counter shows.

    Wrapped rather than called inline so that a model the acting user cannot
    read reports ``-1`` and is diagnosed from the log, instead of letting an
    ``OdooRPCError`` escape and turn a product question into an
    AUTOMATION_ERROR.
    """
    try:
        return int(ctx.adapter.rpc.call(model, "search_count", domain,
                                        context=context) or 0)
    except OdooRPCError as exc:
        ctx.log(f"could not count {model} over {domain!r} ({exc}) — reported "
                f"as -1 rather than as zero, which would read as 'nothing "
                f"there'")
        return -1


def _sample_indexes(total: int) -> list[int]:
    """First, middle and last position of a code-ordered chart.

    The workbook samples "three account codes from the baseline"; the platform
    holds no baseline, so the three are chosen deterministically from the
    chart's own code ordering (``_order = "code, placeholder_code"``,
    ``addons/account/models/account_account.py:23``). Deterministic matters:
    rule 5 forbids a sample that changes between runs, because then two runs
    of this case would not be comparable to each other either.
    """
    if total <= 0:
        return []
    return sorted({0, total // 2, total - 1})


@test_case(
    id="TEST-FG07-SMK-015",
    name="Company, chart of accounts and fiscal settings are unchanged",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module="account, l10n_us, l10n_generic_coa",
    priority="P0",
    kind="DATA",
    order=700,
    description="Read-only capture of the whole accounting setup — company "
                "identity and address, the chart of accounts count with three "
                "sampled codes round-tripped through the v19 company-dependent "
                "code search, the fiscal year end and all five v19 lock dates, "
                "the journal list with its sequence prefixes and the tax "
                "counts — plus every integrity check that needs no Novobi "
                "baseline. Creates nothing; the baseline tick-off is a "
                "residual manual step.",
    traceability=trace("TC-SMK-015"))
def test_smk_015(ctx):
    rpc = ctx.adapter.rpc
    # Every accumulator is declared BEFORE the try. The evidence block runs
    # from `finally`, and a NameError raised there over a step that an earlier
    # assertion failure skipped would replace a real FAILED verdict with an
    # AUTOMATION_ERROR.
    residual: list[str] = []
    summary_rows: list[tuple] = []
    account_rows: list[dict] = []
    journal_rows: list[dict] = []

    with ctx.step("Precondition (workbook): the gallery's company on Odoo 19, "
                  "with the Administrator accounting group so Configuration "
                  "opens"):
        # Probe-then-BLOCK. require_v19 checks BOTH the declared version and
        # that account.account carries the Many2many company_ids — a target
        # that calls itself 19 without a v19-shaped chart would let every
        # count below read the wrong population silently.
        require_v19(ctx)
        require_module(ctx, "account", NO_ACCOUNT_MODULE)

        company = acting_company(ctx)
        pin = company_ctx(company)
        ctx.log(f"acting company #{company['id']} {company['name']!r} — "
                f"currency {company['currency_name']!r}, country "
                f"{company['country_name']!r}, chart template "
                f"{company['chart_template']!r}")
        ctx.log(f"every read below pins allowed_company_ids="
                f"[{company['id']}] — account.account.code is "
                f"company-dependent and three of these surfaces carry a "
                f"multi-company ir.rule, so an unpinned read does not merely "
                f"widen the population, it can return a different value")

        # The workbook's Module(s) column names three modules. Two of them no
        # longer mean in v19 what they meant in v15; report, do not block.
        for name in ("l10n_us", "l10n_generic_coa"):
            state = module_state(rpc, name) or "no such module row"
            ctx.log(f"module {name!r}: {state}")
        if module_state(rpc, "l10n_generic_coa") != "installed":
            finding(ctx,
                    "the workbook's Module(s) column names 'l10n_generic_coa', "
                    "but that module does not exist in Odoo 19 — the generic "
                    "chart ships as template data inside 'account' itself "
                    "(addons/account/data/template/"
                    "account.account-generic_coa.csv). Its absence is NOT a "
                    "migration failure and must not be reported as one; the "
                    "chart to compare against the baseline is the one counted "
                    "below")
        if module_state(rpc, "l10n_us") != "installed":
            finding(ctx,
                    "'l10n_us' is not installed. In v19 it is only a "
                    "bank-account localisation depending on 'base' "
                    "(addons/l10n_us/__manifest__.py) and it no longer carries "
                    "chart data, but l10n_us_reports and l10n_us_1099 — which "
                    "TC-INV-014 and TC-INV-015 need — sit on top of it")

    try:
        with ctx.step("Step 1 / Expected line 1: Settings > Users & Companies "
                      "> Companies — tick off Name, address, Tax ID and "
                      "Currency against the baseline"):
            wanted = ["name", "street", "street2", "city", "state_id", "zip",
                      "country_id", "phone", "email", "vat",
                      "company_registry", "currency_id", "chart_template"]
            readable = [f for f in wanted
                        if f in fields_present(rpc, "res.company", wanted)]
            unreadable = [f for f in wanted if f not in readable]
            if unreadable:
                # "not readable" and "empty" are different verdicts and must
                # never be collapsed: the first is a permissions fact about the
                # runner user, the second is a data fact about the company.
                ctx.log(f"res.company fields not readable by this user "
                        f"(reported as unreadable, NOT as blank): "
                        f"{unreadable}")
            row = rpc.read("res.company", [company["id"]], readable)[0]

            captured = {
                "Name": row.get("name") or "",
                "Street": row.get("street") or "",
                "Street 2": row.get("street2") or "",
                "City": row.get("city") or "",
                "State": m2o_name(row.get("state_id")),
                "ZIP": row.get("zip") or "",
                "Country": m2o_name(row.get("country_id")),
                "Phone": row.get("phone") or "",
                "Email": row.get("email") or "",
                "Tax ID (vat)": row.get("vat") or "",
                "Company ID (company_registry)":
                    row.get("company_registry") or "",
                "Currency": m2o_name(row.get("currency_id")),
                "Chart template": row.get("chart_template") or "",
            }
            for label, value in captured.items():
                ctx.log(f"    {label}: {value!r}")
                summary_rows.append(("company", label, value))

            # Printout-free half of Expected line 1: a blank component cannot
            # match a baseline address that carries it, and it is also what
            # every invoice header prints.
            blank_address = [label for field, label in ADDRESS_FIELDS
                             if field in readable and not row.get(field)]
            ctx.check("Every address component the invoice header prints is "
                      "populated on the company (Street, City, ZIP, Country)",
                      [], blank_address)

            # A US company with no state prints an incomplete address and, more
            # importantly, cannot be matched to a US tax jurisdiction.
            country_code = ""
            country_id = m2o_id(row.get("country_id"))
            if country_id:
                try:
                    country_code = (rpc.read("res.country", [country_id],
                                             ["code"])[0].get("code") or "")
                except OdooRPCError as exc:
                    ctx.log(f"could not read the country code ({exc})")
            if country_code == "US":
                ctx.check_true(
                    "The US company carries a State, without which neither the "
                    "printed address nor any US tax jurisdiction is complete",
                    bool(m2o_id(row.get("state_id"))),
                    actual_desc=f"state_id="
                                f"{m2o_name(row.get('state_id'))!r}")

            # Currency: set AND live. A deactivated currency still reads back
            # by name but silently breaks every rate-dependent report.
            currency_id = m2o_id(row.get("currency_id"))
            currency_active = None
            if currency_id:
                try:
                    currency_active = bool(rpc.read(
                        "res.currency", [currency_id],
                        ["active"])[0].get("active"))
                except OdooRPCError as exc:
                    ctx.log(f"could not read res.currency #{currency_id} "
                            f"({exc})")
            ctx.check_true(
                "The company currency is set and is an ACTIVE currency (a "
                "deactivated currency reads back by name and then breaks every "
                "rate-dependent report)",
                bool(currency_id) and currency_active is not False,
                actual_desc=f"currency={captured['Currency']!r} "
                            f"active={currency_active!r}")

            if not captured["Tax ID (vat)"]:
                # Not asserted: a Tax ID is not mandatory on res.company, and
                # only the baseline can say whether the gallery had one.
                finding(ctx,
                        "the company's Tax ID (res.company.vat) is EMPTY. If "
                        "the Novobi baseline shows a Tax ID, this is an "
                        "Expected-line-1 mismatch and every document that "
                        "prints it is now wrong; if the baseline is empty too, "
                        "ignore this line")

            residual.append(
                "Expected line 1 — tick these off against the Novobi company "
                "details screen from the old system, which the platform does "
                "not hold: Name=" + repr(captured["Name"]) + ", Address=" +
                repr(", ".join(part for part in (
                    captured["Street"], captured["Street 2"],
                    captured["City"], captured["State"], captured["ZIP"],
                    captured["Country"]) if part)) +
                ", Tax ID=" + repr(captured["Tax ID (vat)"]) +
                ", Currency=" + repr(captured["Currency"]) + ". All four are "
                "also in " + SUMMARY_CSV + ". Report each mismatch separately "
                "with the baseline value and the v19 value, as the workbook's "
                "If It Fails asks.")

        with ctx.step("Step 2 / Expected line 2: Accounting > Configuration > "
                      "Chart of Accounts with all filters cleared — read the "
                      "record count"):
            # The Chart of Accounts action carries no context and no default
            # filter (account_account_views.xml:173-178), so "all filters
            # cleared" is exactly an empty domain under the default
            # active_test. The company pin does the rest, via the ir.rule
            # [('company_ids','parent_of',company_ids)]
            # (account_security.xml:154-155).
            ui_count = _search_count(ctx, "account.account", [], pin)
            all_count = _search_count(ctx, "account.account", [],
                                      company_ctx(company, active_test=False))
            archived_count = (all_count - ui_count
                              if ui_count >= 0 and all_count >= 0 else -1)
            ctx.log(f"Chart of Accounts — {ui_count} account(s) visible with "
                    f"filters cleared; {all_count} including archived "
                    f"({archived_count} archived)")
            summary_rows.append(("counts", "accounts (as the list counter "
                                           "shows them)", ui_count))
            summary_rows.append(("counts", "accounts including archived",
                                 all_count))
            summary_rows.append(("counts", "accounts archived",
                                 archived_count))

            rows = rpc.search_read(
                "account.account", [],
                ["code", "name", "account_type", "internal_group", "active",
                 "reconcile", "company_ids"],
                context=company_ctx(company, active_test=False))
            for entry in rows:
                account_rows.append({
                    "id": entry.get("id"),
                    "code": entry.get("code") or "",
                    "name": entry.get("name") or "",
                    "account_type": entry.get("account_type") or "",
                    "internal_group": entry.get("internal_group") or "",
                    "active": bool(entry.get("active")),
                    "reconcile": bool(entry.get("reconcile")),
                })
            ctx.log(f"read {len(account_rows)} account row(s) into "
                    f"{ACCOUNTS_CSV}")

            # Cross-check: the row-by-row read and the counter must agree. If
            # they do not, one of them is being filtered by something this
            # case did not ask for, and every figure below is suspect.
            live_rows = [r for r in account_rows if r["active"]]
            ctx.check("The chart read row by row holds the same number of "
                      "live accounts as the list counter reports (if these "
                      "disagree, something is filtering the population and "
                      "every figure in this case is suspect)",
                      ui_count, len(live_rows))

            # Integrity that needs no baseline #1: account code uniqueness is
            # enforced only by the Python constraint _ensure_code_is_unique
            # (account_account.py:1096-1113), which migrated rows never had to
            # pass. A duplicated code makes a report double-count.
            seen: dict[str, list] = {}
            for entry in account_rows:
                seen.setdefault(entry["code"], []).append(entry["id"])
            duplicates = [f"code {code!r} on accounts {ids}"
                          for code, ids in sorted(seen.items())
                          if code and len(ids) > 1]
            ctx.check("No two accounts in this company share the same code "
                      "(uniqueness is a Python constraint in v19, not a "
                      "database one, so migrated rows can violate it)",
                      [], duplicates)

            # Integrity #2: a blank code cannot be searched for, printed or
            # matched to a baseline line.
            blank_codes = [f"account #{e['id']} {e['name']!r}"
                           for e in account_rows if not e["code"]]
            ctx.check("Every account carries a code (a blank code cannot be "
                      "matched to any baseline line, printed or searched for)",
                      [], blank_codes)

            # Integrity #3: v15's user_type_id was mapped onto v19's
            # account_type selection during the upgrade. A value outside the
            # selection is a mapping that did not complete, and it silently
            # drops the account out of every report that groups by type.
            type_labels = selection_labels(rpc, "account.account",
                                           "account_type")
            ctx.log(f"v19 account_type selection ({len(type_labels)} values) — "
                    f"the taxonomy the baseline's v15 type names must be read "
                    f"against: " +
                    ", ".join(f"{k}={v!r}" for k, v in
                              sorted(type_labels.items())))
            if not type_labels:
                # selection_labels() returns {} on OdooRPCError, and the
                # off-taxonomy check below is guarded on it. Say so out loud:
                # a check that passes because it could not read the selection
                # is NOT the same verdict as a check that passed, and leaving
                # that silent is how a permissions hiccup gets recorded as a
                # clean chart of accounts.
                finding(ctx,
                        "the account_type SELECTION could not be read from "
                        "fields_get on this database, so the taxonomy check "
                        "below could not run and PASSED VACUOUSLY. It is not "
                        "evidence that every account carries a valid v19 type. "
                        "Re-run as a user who can read account.account's field "
                        "definitions before trusting Expected line 2's 'type' "
                        "half; the raw account_type of every account is still "
                        "in " + ACCOUNTS_CSV)
            off_taxonomy = [
                f"account {e['code']!r} {e['name']!r} -> "
                f"account_type={e['account_type']!r}"
                for e in account_rows
                if type_labels and e["account_type"] not in type_labels]
            ctx.check("Every account's Type is one of the 19 values Odoo 19 "
                      "actually offers (a value outside the selection is a v15 "
                      "user_type_id mapping that did not complete, and it drops "
                      "the account out of every report grouped by type)",
                      [], off_taxonomy)

            residual.append(
                f"Expected line 2 (count) — compare {ui_count} account(s) "
                f"against the Novobi baseline account count. The workbook's If "
                f"It Fails is emphatic that the DIRECTION matters: MORE than "
                f"the baseline usually means the v19 localisation added its "
                f"own accounts on top of the migrated chart, FEWER means "
                f"accounts were lost, and they are completely different "
                f"problems. {archived_count} further account(s) are archived "
                f"and are NOT in that {ui_count} — if the baseline count is "
                f"higher, check the archived ones in {ACCOUNTS_CSV} before "
                f"reporting anything as missing.")

        with ctx.step("Step 3 / Expected line 2: search three account codes "
                      "and confirm each one's name and type"):
            ordered = sorted(live_rows, key=lambda e: (e["code"], e["id"]))
            sampled = [ordered[i] for i in _sample_indexes(len(ordered))]
            # The workbook's step 3 is "search for THREE account codes", so
            # three is the contract — not "at least one". A chart that cannot
            # yield three distinct live accounts cannot satisfy Expected line
            # 2's sampled half at all, and that is a finding about the chart,
            # not a reason to sample fewer.
            ctx.check("The chart yields the three account codes workbook step "
                      "3 samples (first, middle and last of the chart's own "
                      "code order) — a chart holding fewer than three live "
                      "accounts cannot satisfy Expected line 2 at all",
                      3, len(sampled))

            # The round trip is the real assertion here. code is a
            # company-dependent compute over code_store with a custom
            # _search_code (account_account.py:39-40, 342-343): reading a code
            # and searching for it exercise two different code paths, and a
            # half-migrated code_store makes them disagree.
            mismatched, archived_hits = [], []
            for entry in sampled:
                found = rpc.search_read(
                    "account.account", [("code", "=", entry["code"])],
                    ["code", "name", "account_type", "internal_group",
                     "active"],
                    context=company_ctx(company, active_test=False))
                labels = ", ".join(
                    f"#{f['id']} {f.get('code')!r} {f.get('name')!r} "
                    f"type={f.get('account_type')!r}"
                    f"{'' if f.get('active') else ' [ARCHIVED]'}"
                    for f in found)
                ctx.log(f"    searched code {entry['code']!r} -> "
                        f"{labels or '(nothing found)'}")
                summary_rows.append(
                    ("sampled account", entry["code"],
                     f"{entry['name']} | type={entry['account_type']} "
                     f"({type_labels.get(entry['account_type'], '?')}) | "
                     f"group={entry['internal_group']}"))
                ids = [f["id"] for f in found]
                if ids != [entry["id"]]:
                    mismatched.append(
                        f"code {entry['code']!r} was read off account "
                        f"#{entry['id']} but searching for it returned {ids}")
                # _search_code disables active_test, so an archived account
                # CAN come back here even though the chart list would not show
                # it. Left unasserted, that would let an archived account
                # masquerade as the baseline's account.
                archived_hits.extend(
                    f"code {entry['code']!r} also matches ARCHIVED account "
                    f"#{f['id']} {f.get('name')!r}"
                    for f in found if not f.get("active"))

            ctx.check("Searching the Chart of Accounts for each sampled code "
                      "returns exactly the account that code was read from",
                      [], mismatched)
            ctx.check("No sampled code matches an ARCHIVED account (v19's "
                      "_search_code disables active_test, so an archived "
                      "account can answer a code search that the list view "
                      "would never show)",
                      [], archived_hits)

            residual.append(
                "Expected line 2 (three sampled accounts) — the platform holds "
                "no baseline, so the three were sampled deterministically from "
                "the chart's own code order (first, middle, last): " +
                "; ".join(f"{e['code']} {e['name']!r} type="
                          f"{type_labels.get(e['account_type'], e['account_type'])!r}"
                          for e in sampled) + ". Tick these three off against "
                "the baseline, then repeat the check for whichever three codes "
                "the Novobi printout actually names — every code, name and "
                "type in the chart is in " + ACCOUNTS_CSV + ", so this is a "
                "lookup and not a re-run.")

        with ctx.step("Step 4 / Expected line 3: fiscal year end and lock "
                      "dates"):
            fiscal_wanted = (list(FISCAL_FIELDS) + list(LOCK_DATE_FIELDS)
                             + list(LOCK_DATE_REMOVED_IN_V19))
            fiscal_readable = fields_present(rpc, "res.company", fiscal_wanted)
            present = [f for f in fiscal_wanted if f in fiscal_readable]
            frow = rpc.read("res.company", [company["id"]], present)[0]

            months = selection_labels(rpc, "res.company",
                                      "fiscalyear_last_month")
            last_month = str(frow.get("fiscalyear_last_month") or "")
            fiscal_end = (f"{frow.get('fiscalyear_last_day')} "
                          f"{months.get(last_month, last_month)}").strip()
            ctx.log(f"    Fiscal Year end: {fiscal_end!r} "
                    f"(fiscalyear_last_day={frow.get('fiscalyear_last_day')!r} "
                    f"fiscalyear_last_month={last_month!r})")
            summary_rows.append(("fiscal", "Fiscal Year end", fiscal_end))

            for field in LOCK_DATE_FIELDS:
                value = frow.get(field) if field in present else None
                shown = value if value else ("(not set)" if field in present
                                             else "(field not readable)")
                ctx.log(f"    {field}: {shown}")
                summary_rows.append(("lock date", field, str(shown)))

            # Expected line 3 has no baseline-free pass/fail of its own, but
            # the SHAPE of the company does: all five v19 lock-date fields must
            # be readable, or the company row is not a v19 company and the
            # baseline tick-off below would be comparing against nothing.
            missing_lock_fields = [f for f in LOCK_DATE_FIELDS
                                   if f not in fiscal_readable]
            ctx.check("All five Odoo 19 lock-date fields exist and are "
                      "readable on the company (fiscalyear, tax, sale, "
                      "purchase and hard — addons/account/models/"
                      "company.py:76-102)",
                      [], missing_lock_fields)

            # Workbook-sanctioned v19 difference: asserted in NEITHER
            # direction, per the suite's observation policy.
            for field in LOCK_DATE_REMOVED_IN_V19:
                if field not in fiscal_readable:
                    observation(ctx,
                                f"res.company.{field} was REMOVED in Odoo 19 — "
                                f"v19 has five lock dates and that is not one "
                                f"of them (addons/account/models/"
                                f"company.py:76-102). A baseline value for "
                                f"{field} has no v19 equivalent and must not be "
                                f"reported as a lost setting; the nearest "
                                f"v19 equivalents are fiscalyear_lock_date and "
                                f"the new hard_lock_date")

            # The workbook's own navigation for this step does not work on v19.
            accountant_state = module_state(rpc, ACCOUNTANT_MODULE)
            lock_menu = menu_by_xmlid(ctx, LOCK_DATE_MENU_XMLID)
            finding(ctx,
                    "the workbook's step 4 says to read the lock dates from "
                    "Accounting > Configuration > Settings > Fiscal Periods. "
                    "On Odoo 19 that section contains ONLY the Fiscal Year "
                    "setting, and even that is invisible=\"1\" in Community "
                    "(addons/account/views/res_config_settings_views.xml:"
                    "347-349), un-hidden by the Enterprise account_accountant "
                    "module (enterprise-19.0/account_accountant/views/"
                    "res_config_settings_views.xml:8-16). The lock dates moved "
                    "to the 'Lock Dates" + "…" + "' wizard at Accounting > "
                    "Accounting > Closing (enterprise-19.0/account_accountant/"
                    "wizard/account_change_lock_date.xml:232-246). On this "
                    f"database account_accountant is "
                    f"{accountant_state or 'not present'} and that menu "
                    f"{'resolves as ' + repr(lock_menu.get('name')) if lock_menu else 'does not resolve'}"
                    ". The values above were read straight off res.company, so "
                    "they are correct whichever screen you use")

            residual.append(
                "Expected line 3 — tick these off against the Novobi fiscal "
                "settings from the old system: Fiscal Year end=" +
                repr(fiscal_end) + "; " +
                "; ".join(f"{f}={frow.get(f) or '(not set)'}"
                          for f in LOCK_DATE_FIELDS if f in present) +
                ". If the baseline carries a period_lock_date, it has no v19 "
                "equivalent — see the OBSERVATION above and do NOT raise it as "
                "a lost setting.")

        with ctx.step("Step 5 / Expected line 4: Accounting > Configuration > "
                      "Journals — count them and confirm the short codes"):
            # active_test off, so an archived journal is reported as ARCHIVED
            # rather than silently counted as missing — those are different
            # findings and need different fixes.
            rows = rpc.search_read(
                "account.journal", [],
                ["name", "code", "type", "active", "currency_id"],
                context=company_ctx(company, active_test=False),
                order="type, code")
            type_names = selection_labels(rpc, "account.journal", "type")
            for entry in rows:
                journal_rows.append({
                    "id": entry.get("id"),
                    "name": entry.get("name") or "",
                    "code": entry.get("code") or "",
                    "type": entry.get("type") or "",
                    "type_label": type_names.get(entry.get("type") or "", ""),
                    "active": bool(entry.get("active")),
                    "currency": m2o_name(entry.get("currency_id")),
                })
            live_journals = [j for j in journal_rows if j["active"]]
            archived_journals = [j for j in journal_rows if not j["active"]]
            ctx.log(f"Journals — {len(live_journals)} active, "
                    f"{len(archived_journals)} archived")
            for entry in journal_rows:
                ctx.log(f"    [{entry['code']}] {entry['name']!r} — "
                        f"{entry['type']} ({entry['type_label']})"
                        f"{'' if entry['active'] else ' [ARCHIVED]'}")
            summary_rows.append(("counts", "journals active",
                                 len(live_journals)))
            summary_rows.append(("counts", "journals archived",
                                 len(archived_journals)))

            # Expected line 4's printout-free half: a journal with no sequence
            # prefix has no short code to compare to the baseline at all.
            no_code = [f"journal #{j['id']} {j['name']!r}"
                       for j in journal_rows if not j["code"]]
            ctx.check("Every journal carries a Sequence Prefix — v19's name "
                      "for the short code (addons/account/models/"
                      "account_journal.py:97-99)", [], no_code)

            # The families invoicing depends on. This is the one part of
            # Expected line 4 that can be judged without the baseline: whatever
            # the gallery's journal list looks like, invoicing is broken
            # without these.
            have = {j["type"] for j in live_journals}
            missing_families = [label for label, types in JOURNAL_FAMILIES
                                if not have.intersection(types)]
            ctx.check("The journal families invoicing depends on are all "
                      "present and active (Sales, Purchase, Miscellaneous and "
                      "at least one money journal)", [], missing_families)

            if archived_journals:
                finding(ctx,
                        "these journals exist but are ARCHIVED, so they do NOT "
                        "appear in the Journals list the workbook's step 5 "
                        "counts: " +
                        "; ".join(f"[{j['code']}] {j['name']!r}"
                                  for j in archived_journals) +
                        ". If the baseline lists any of them, the finding is "
                        "'archived during the upgrade', not 'missing' — a "
                        "completely different fix")

            at_cap = [f"[{j['code']}] {j['name']!r}" for j in journal_rows
                      if len(j["code"]) >= JOURNAL_CODE_SIZE]
            if at_cap:
                finding(ctx,
                        f"account.journal.code is capped at "
                        f"{JOURNAL_CODE_SIZE} characters in Odoo 19 "
                        f"(addons/account/models/account_journal.py:97-99). "
                        f"These journals sit exactly at the cap and are "
                        f"therefore truncation candidates — if the baseline "
                        f"short code is longer, it CANNOT have survived "
                        f"intact: " + "; ".join(at_cap))

            observation(ctx,
                        "the column the workbook calls 'short code' is "
                        "labelled 'Sequence Prefix' in Odoo 19 "
                        "(addons/account/models/account_journal.py:98), and "
                        "v19 offers a sixth journal type, 'credit' (Credit "
                        "Card), that v15 did not (:106-113). Neither is a "
                        "defect")

            residual.append(
                "Expected line 4 — confirm every journal the gallery uses is "
                "in this list with the same short code. Active journals (" +
                str(len(live_journals)) + "): " +
                "; ".join(f"[{j['code']}] {j['name']}"
                          for j in live_journals) +
                (". Archived (" + str(len(archived_journals)) + "): " +
                 "; ".join(f"[{j['code']}] {j['name']}"
                           for j in archived_journals)
                 if archived_journals else "") +
                ". The full list with types is in " + JOURNALS_CSV + ".")

        with ctx.step("Step 6: Accounting > Configuration > Taxes — read the "
                      "count (the workbook states no Expected Result for it, "
                      "so nothing is asserted)"):
            # The Taxes menu is NOT an unfiltered list. Its action turns on
            # search_default_sale AND search_default_purchase and sets
            # active_test False (addons/account/views/
            # account_tax_views.xml:236-241), and the two filters sit in one
            # group so they OR together
            # (:121-122 -> type_tax_use in ('sale','purchase')). Counting the
            # bare model would report a number no tester can reproduce on
            # screen.
            ui_ctx = company_ctx(company, active_test=False)
            tax_ui = _search_count(
                ctx, "account.tax",
                [("type_tax_use", "in", ["sale", "purchase"])], ui_ctx)
            tax_all = _search_count(ctx, "account.tax", [], ui_ctx)
            tax_active = _search_count(ctx, "account.tax", [], pin)
            ctx.log(f"Taxes — {tax_ui} shown by the menu (Sale + Purchase "
                    f"filters, archived included, which is what the screen's "
                    f"counter says); {tax_all} taxes in total including "
                    f"'none'-type and archived; {tax_active} active")
            summary_rows.append(("counts", "taxes as the Taxes menu shows "
                                           "them (sale+purchase, incl. "
                                           "archived)", tax_ui))
            summary_rows.append(("counts", "taxes total incl. archived and "
                                           "type 'none'", tax_all))
            summary_rows.append(("counts", "taxes active", tax_active))

            residual.append(
                f"Step 6 (no Expected Result line of its own) — the Taxes "
                f"screen will read {tax_ui}, because its menu pre-applies the "
                f"Sale and Purchase filters and switches archived records on "
                f"(addons/account/views/account_tax_views.xml:236-241). If the "
                f"baseline tax count was taken from an unfiltered v15 list, "
                f"compare it to {tax_all} instead. Quote WHICH of the two you "
                f"used when you report.")

        with ctx.step("Look-ahead probe for TC-INV-006 / TC-INV-008: does the "
                      "company still carry a Default Payment Journal?"):
            # Not a workbook expectation — a courtesy probe. Knowing this at
            # order 700 rather than at order 707 saves a whole run.
            if company["has_default_journal_field"]:
                ctx.log(f"res.company.payment_default_journal_id is present — "
                        f"currently "
                        f"#{company['payment_default_journal_id'] or 0}")
                summary_rows.append(
                    ("look-ahead", "payment_default_journal_id",
                     company["payment_default_journal_id"] or "(not set)"))
            else:
                finding(ctx,
                        "res.company.payment_default_journal_id does NOT exist "
                        "on this database, so 'mmg_default_payment_journal' "
                        "was not ported to Odoo 19. TC-INV-006 and TC-INV-008 "
                        "(orders 707 and 708) will BLOCK on this. Raising it "
                        "now, from the first case in the suite, saves the run")
                summary_rows.append(("look-ahead",
                                     "payment_default_journal_id",
                                     "FIELD ABSENT"))
    finally:
        # Belt AND braces. Everything below already guards itself, but the
        # whole block is fenced as well: ctx.step re-raises anything that
        # escapes it (framework/context.py:117-122), and an exception
        # escaping a `finally` replaces the real FAILED / BLOCKED verdict
        # this case had already reached with an AUTOMATION_ERROR — which
        # reads as "the test is broken" rather than "the chart is wrong".
        try:
          with ctx.step("Evidence: write the chart, journal and summary CSVs"):
            for path_name, header, rows_out in (
                (ACCOUNTS_CSV,
                 ["id", "code", "name", "account_type", "internal_group",
                  "active", "reconcile"],
                 [[e["id"], e["code"], e["name"], e["account_type"],
                   e["internal_group"], e["active"], e["reconcile"]]
                  for e in account_rows[:CSV_LIMIT]]),
                (JOURNALS_CSV,
                 ["id", "code", "name", "type", "type_label", "active",
                  "currency"],
                 [[j["id"], j["code"], j["name"], j["type"], j["type_label"],
                   j["active"], j["currency"]]
                  for j in journal_rows[:CSV_LIMIT]]),
                (SUMMARY_CSV,
                 ["section", "item", "value"],
                 [list(r) for r in summary_rows[:CSV_LIMIT]]),
            ):
                path = ctx.artifacts_dir / path_name
                try:
                    with path.open("w", newline="", encoding="utf-8") as fh:
                        writer = csv.writer(fh)
                        writer.writerow(header)
                        writer.writerows(rows_out)
                    ctx.add_artifact(path, "log", path_name)
                    ctx.log(f"wrote {len(rows_out)} row(s) to {path_name}")
                except Exception as exc:          # noqa: BLE001
                    # Deliberately broader than OSError. This runs from
                    # `finally`, and ctx.step re-raises whatever escapes it
                    # (framework/context.py:117-122), which would replace the
                    # real FAILED/BLOCKED verdict this case had already
                    # reached with an AUTOMATION_ERROR. A csv.Error or a bad
                    # value in one row must cost the artifact, never the
                    # verdict.
                    ctx.log(f"could not write {path_name} "
                            f"({type(exc).__name__}: {exc}) — the figures "
                            f"above are still in this log")
            for note in residual:
                try:
                    residual_manual_step(ctx, note)
                except Exception as exc:          # noqa: BLE001
                    ctx.log(f"could not emit a residual manual step "
                            f"({type(exc).__name__}: {exc}) — it is the note "
                            f"beginning {note[:80]!r}")
            ctx.log("NOTHING WAS CREATED OR MODIFIED by this case — the "
                    "workbook's State After The Test is 'Nothing changed' and "
                    "its Test Data says 'Do not change anything', so no sweep "
                    "and no cleanup runs here either (a sweep is itself a "
                    "delete).")
        except Exception as exc:              # noqa: BLE001
            # The outer fence described above. Nothing below the verdict is
            # worth an AUTOMATION_ERROR: the assertions have already run, so
            # losing an artifact must never lose the result.
            ctx.log(f"[evidence] the evidence block itself failed "
                    f"({type(exc).__name__}: {exc}) — the verdict this case "
                    f"already reached stands; only the artifacts were lost")
