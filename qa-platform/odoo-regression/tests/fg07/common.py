"""FG-07 — Invoicing, Payments & Accounting Documents. Shared gates and fixtures.

Source of truth for this suite is the CLIENT MANUAL TESTING GUIDELINE
``MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0.xlsx``, sheet
``Testing Guideline``, rows 30–43 (TC-DAT-002, TC-DAT-004, TC-INV-001 …
TC-INV-016 and TC-SMK-015). Every assertion in this suite implements that
workbook's *Expected Result* column verbatim — never weakened, never
inverted.

Odoo 19 only
------------
The workbook describes Odoo 19 screens, and three of the five surfaces this
suite reads are a different generation from v15's:

* the accounting reports are driven by ``account.report`` + the **Enterprise**
  ``account_reports`` engine, whose public entry points (``get_options``,
  ``get_report_information``, ``dispatch_report_action``) do not exist in v15
  at all — v15 used one Python class per report;
* ``account.account.company_id`` became a Many2many ``company_ids`` and
  ``code`` became a company-dependent compute over ``code_store``
  (``addons/account/models/account_account.py:39-40, 97``), so a v15-shaped
  domain raises rather than returning the wrong answer;
* ``account.move`` gained ``status_in_payment`` — the field the v19 list view
  and ribbon actually display — while v15 relabelled ``payment_state``
  itself.

Running these assertions against a v15 target would report version
differences as product defects, so every test calls :func:`require_v19`
first and reports BLOCKED on anything else. This mirrors FG-05 and FG-06.

Source trees these citations were read from
-------------------------------------------
* Odoo 19 Community — ``D:/Projects/odoo-19.0/addons``
* Odoo 19 Enterprise — ``D:/Projects/odoo-19.0/enterprise-19.0`` (787 modules)
* MMG v15 custom modules — ``D:/Projects/mmg/psus-medicine-man-gallery``

A trap this module exists to avoid
----------------------------------
``account.report`` **is** defined in Community
(``addons/account/models/account_report.py:45``) and Community even ships
``account.report`` data rows, but it carries **zero public engine methods**
there — ``get_options`` and ``get_report_information`` live only in the
Enterprise override (``enterprise-19.0/account_reports/models/
account_report.py:65-72``). So ``model_exists('account.report')`` returns
True on a Community-only database and the test would then die with a
confusing "method does not exist" error instead of a clean BLOCK. Every
report gate in this suite therefore probes **``ir.module.module``**, never
model existence — see :func:`require_account_reports`.

How this suite drives Odoo
--------------------------
The platform talks to Odoo over ``/web/dataset/call_kw``, the endpoint the
browser itself uses (``adapters/base.py``). Three consequences:

1. **No leading-underscore method may be called.** ``odoo/service/model.py``
   refuses a private method before it is even looked up. Everything this
   module calls is public: ``get_options``, ``get_report_information``,
   ``dispatch_report_action``, ``get_wkhtmltopdf_state``, ``load_menus``,
   ``has_access``, ``has_group``, ``onchange``, ``action_post``,
   ``action_create_payments``, ``action_generate``. ``check_access`` is NOT
   among them: it is ``@api.private`` in v19 (``odoo/orm/models.py:4099``),
   so every access probe here uses ``has_access``.
2. **Every RECORD-style method needs a leading ids argument.** ``call_kw``
   splits the argument list itself: only a method carrying ``_api_model``
   (set by ``@api.model`` and ``@api.model_create_multi`` —
   ``odoo/orm/decorators.py:324, 371``) receives the whole list; for anything
   else ``ids, args = args[0], args[1:]`` and the FIRST positional is
   consumed as the recordset (``odoo/service/model.py:82-87``, the split is
   line 86). Omit it and Odoo browses the real first argument, then calls the
   method one argument short — the failure surfaces as "missing 1 required
   positional argument".

   * ids-first here: ``onchange`` (``[]`` — it is undecorated,
     ``addons/web/models/models.py:1973``), ``res.users.has_group``
     (``[uid]`` — ``@api.readonly`` only, and it calls ``ensure_one()``,
     ``odoo/addons/base/models/res_users.py:1065-1075``), ``has_access``,
     ``read``, ``write``, ``get_options``, ``get_report_information``,
     ``dispatch_report_action``, ``action_post``,
     ``action_create_payments``, ``action_generate``.
   * NO ids, correctly: ``create`` (``@api.model_create_multi``),
     ``fields_get``, ``default_get``, ``search_count``, ``get_view``,
     ``get_views``, ``formatted_read_group``, ``load_menus``,
     ``get_wkhtmltopdf_state`` — all ``@api.model``.
3. **``@api.onchange`` does not fire on ``create()``/``write()``.** Where a
   workbook expectation is "the field fills itself in", use
   :func:`form_defaults` / :func:`onchange_values`, which call the public
   ``onchange`` the form view itself calls (``addons/web/models/
   models.py:1973``).

Safety properties
-----------------
* Every record this suite creates is namespaced with the ``FG07`` marker and
  swept before and after each test that creates anything. Pre-existing
  business records — the chart of accounts, company journals, real customers,
  payment providers, follow-up levels, transfer rules — are **read-only**.
* Six of the fourteen cases (TC-SMK-015, TC-DAT-002, TC-DAT-004, TC-INV-010,
  TC-INV-013, TC-INV-016) create nothing at all and never call
  :func:`sweep_fg07` — a sweep is itself a delete, and the workbook's *State
  After The Test* for those is "Nothing changed".
* **No provider state, credential, cron or connector is ever written.**
  TC-INV-010 reads provider configuration and records each credential as
  ``set`` / ``not set`` / ``not readable`` — never a value.
* **No transfer is ever run.** ``account.transfer.model`` exposes
  ``action_perform_auto_transfer`` publicly and it creates draft journal
  entries; TC-INV-016 must never call it. The workbook says so too ("Do not
  run a transfer").
* A POSTED ``account.move`` is never handed to ``unlink()``: callers drop the
  id from ``created`` once posted, and :func:`cleanup` refuses it anyway.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from adapters.base import OdooRPCError

# --------------------------------------------------------------- identity
FEATURE = "FG-07 Invoicing, Payments & Accounting Documents"
WORKFLOW = "FG-07"
WORKFLOW_NAME = "Invoicing, Payments & Accounting Documents"
MARK = "FG07"

WORKBOOK = "MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0.xlsx"
SHEET = "Testing Guideline"


def trace(tc_ids, user_story: str = "") -> dict:
    """Traceability back to the client manual testing guideline.

    Deliberately local rather than ``framework.fg_common.make_trace``: that
    helper stamps the *automation catalogue* workbook
    (``MMG_v19_Test_Cases_Grouped_by_Feature_v3.0.xlsx``) as the source, and
    FG-07's expectations come from the client manual guideline, which is a
    different document with a different — and in several places corrected —
    set of expectations.
    """
    return {
        "tc_ids": tc_ids if isinstance(tc_ids, list) else [tc_ids],
        "feature": FEATURE,
        "user_story": user_story,
        "source": f"{WORKBOOK} / {SHEET}",
    }


# ------------------------------------------------------- workbook constants
# The printed invoice. account.move._get_name_invoice_report returns
# 'account.report_invoice_document' and the ir.actions.report that the Print
# button runs is 'account.report_invoice_with_payments'
# (addons/account/report/account_invoice_report.xml). The with_payments
# variant is the one TC-INV-001 must render: workbook item (g), the
# "Payment Type:" line, lives inside t-if="print_with_payments".
INVOICE_REPORT = "account.report_invoice_with_payments"
INVOICE_REPORT_PLAIN = "account.report_invoice"

# The six reports of TC-INV-014, and the two of TC-DAT-002 / TC-DAT-004.
# XML ids read from enterprise-19.0/account_reports/data/*.xml.
REPORT_XMLID = {
    "trial_balance": "account_reports.trial_balance_report",
    "general_ledger": "account_reports.general_ledger_report",
    "balance_sheet": "account_reports.balance_sheet",
    "profit_and_loss": "account_reports.profit_and_loss",
    "aged_receivable": "account_reports.aged_receivable_report",
    "aged_payable": "account_reports.aged_payable_report",
}

# The leaf menu of each, and the section it must hang under. The workbook's
# navigation ("Reporting > Ledgers > Trial Balance") is asserted against
# these rather than trusted.
REPORT_MENU_XMLID = {
    "trial_balance": "account_reports.menu_action_account_report_coa",
    "general_ledger":
        "account_reports.menu_action_account_report_general_ledger",
    "balance_sheet":
        "account_reports.menu_action_account_report_balance_sheet",
    "profit_and_loss":
        "account_reports.menu_action_account_report_profit_and_loss",
    "aged_receivable":
        "account_reports.menu_action_account_report_aged_receivable",
    "aged_payable":
        "account_reports.menu_action_account_report_aged_payable",
}
REPORT_SECTION_XMLID = {
    "trial_balance": "account_reports.account_reports_audit_menu",
    "general_ledger": "account_reports.account_reports_audit_menu",
    "balance_sheet": "account.account_reports_legal_statements_menu",
    "profit_and_loss": "account.account_reports_legal_statements_menu",
    "aged_receivable": "account.account_reports_partners_reports_menu",
    "aged_payable": "account.account_reports_partners_reports_menu",
}
REPORT_LABEL = {
    "trial_balance": "Reporting > Ledgers > Trial Balance",
    "general_ledger": "Reporting > Ledgers > General Ledger",
    "balance_sheet": "Reporting > Statement Reports > Balance Sheet",
    "profit_and_loss": "Reporting > Statement Reports > Profit and Loss",
    "aged_receivable": "Reporting > Partner Reports > Aged Receivable",
    "aged_payable": "Reporting > Partner Reports > Aged Payable",
}

# res.company lock-date fields, by their EXACT v19 names
# (addons/account/models/company.py:74-102). v15's period_lock_date is GONE
# in v19 — a baseline value for it has no v19 equivalent, which TC-SMK-015
# reports as information rather than as a difference.
FISCAL_FIELDS = ("fiscalyear_last_day", "fiscalyear_last_month")
LOCK_DATE_FIELDS = ("fiscalyear_lock_date", "tax_lock_date", "sale_lock_date",
                    "purchase_lock_date", "hard_lock_date")
LOCK_DATE_REMOVED_IN_V19 = ("period_lock_date",)

# account.move.payment_state / status_in_payment
# (addons/account/models/account_move.py). TC-INV-004 turns on the
# distinction: v15 relabelled payment_state itself, v19 displays a separate
# status_in_payment field in the list and the ribbon.
PAYMENT_STATE_IN_PAYMENT = "in_payment"
PAYMENT_STATE_PAID = "paid"
STATUS_FIELD = "status_in_payment"

# payment.provider — the transfer -> custom rename of v17+
# (addons/payment_custom/). TC-INV-010's whole premise.
PROVIDER_CUSTOM_CODE = "custom"
PROVIDER_CUSTOM_MODE_WIRE = "wire_transfer"
PROVIDER_LEGACY_CODE = "transfer"
# Credential field names per provider code. Read to decide set / not set —
# NEVER recorded as a value (workbook: "the values themselves will be
# masked — you are checking they are not empty").
PROVIDER_CREDENTIAL_FIELDS = {
    "stripe": ("stripe_publishable_key", "stripe_secret_key",
               "stripe_webhook_secret"),
    "authorize": ("authorize_login", "authorize_transaction_key",
                  "authorize_signature_key", "authorize_client_key"),
    "paypal": ("paypal_email_account", "paypal_client_id",
               "paypal_client_secret", "paypal_webhook_id"),
}

# TC-INV-016. The v15 Enterprise module account_auto_transfer was RENAMED
# account_transfer in v19 and is NO LONGER auto_install; the MODEL names are
# unchanged, so migrated rules can sit in the database with no module to
# display them.
TRANSFER_MODULE_V19 = "account_transfer"
TRANSFER_MODULE_V15 = "account_auto_transfer"
TRANSFER_MODEL = "account.transfer.model"
TRANSFER_LINE_MODEL = "account.transfer.model.line"
TRANSFER_MENU_XMLID = "account_transfer.menu_auto_transfer"
TRANSFER_MENU_PARENT_XMLID = "account.account_transactions_menu"

# TC-INV-013 / TC-INV-015.
FOLLOWUP_MODEL = "account_followup.followup.line"
FOLLOWUP_MENU_XMLID = "account_followup.account_followup_menu"
WIZARD_1099 = "l10n_us_1099.wizard"
MENU_1099_XMLID = "l10n_us_1099.menu_action_view_l10n_us_1099_wizard"
TAXES_AND_FISCAL_MENU_XMLID = "account.account_reports_taxes_and_fiscal_menu"
# The menu label ends in a real single-character ellipsis, U+2026 — not three
# ASCII periods. The workbook calls this out ("the name ends in three dots").
ELLIPSIS = "\u2026"

# Odoo 19's own shipped follow-up defaults. If a database returns exactly
# these and the baseline says otherwise, the gallery's levels were not
# migrated and a fresh default set was created — a far more actionable
# verdict than "the count does not match".
FOLLOWUP_V19_DEFAULTS = ((15, "15 Days"), (30, "30 Days"))


# ------------------------------------------------------------ block reasons
V19_ONLY = (
    "FG-07 targets Odoo 19 only: the client manual testing guideline describes "
    "the v19 accounting surface, where the reports run on the Enterprise "
    "account_reports engine (get_options / get_report_information, which do "
    "not exist in v15), account.account.company_id has become the Many2many "
    "company_ids with a company-dependent computed code, and account.move "
    "displays a separate status_in_payment field rather than a relabelled "
    "payment_state. On a v15 target every one of those expectations would "
    "report a version difference as a product defect. Point the runner at the "
    "odoo19 environment (ODOO19_URL / ODOO19_DB in config/local.yaml)"
)

NO_ACCOUNT_REPORTS = (
    "'account_reports' (Odoo Enterprise, 'Accounting Reports', licence "
    "OEEL-1) is not installed on this database, so the Trial Balance, General "
    "Ledger, Balance Sheet, Profit and Loss and the two Aged Partner reports "
    "do not exist and no figure this case reads can be produced. NOTE the "
    "model account.report DOES exist in Community and carries no engine at "
    "all, so its presence proves nothing. account_reports has "
    "auto_install=True and depends on account_accountant, so on an Enterprise "
    "database with Accounting installed it installs itself — its absence "
    "means the Enterprise addons path is not on this server"
)

NO_ACCOUNTANT = (
    "'accountant' (Odoo Enterprise, 'Accounting') is not installed on this "
    "database. It is the module that introduces the outstanding-payments "
    "flow, so account.move.payment_state can never reach 'in_payment' and "
    "this case's 'a cheque still in transit reads Paid' expectation would "
    "pass vacuously against a status that cannot occur. NOTE this is NOT the "
    "module called 'account_accountant', which in Odoo 19 is named "
    "'Invoicing' and carries none of that behaviour"
)

NO_MMG_INVOICE_TEMPLATE = (
    "'mmg_account' is not installed on this database, so none of the nine "
    "layout changes the workbook checks can be present and the invoice would "
    "print as a stock Odoo document. In Odoo 19 mmg_account is the ONLY "
    "module that owns the printed invoice: it ABSORBED the v15 module "
    "mmg_change_invoice_template as part of the upgrade (decision D1 — see "
    "mmg_account/__manifest__.py, 'Absorbs mmg_change_invoice_template as of "
    "the v19 upgrade'), and the whole consolidated layout now lives in "
    "mmg_account/report/report_invoice.xml. Do NOT look for a module called "
    "mmg_change_invoice_template on a v19 database: it does not exist on the "
    "staging_19 branch and its absence is correct, not damage. Install "
    "mmg_account from the MMG v19 addons path before running the three PDF "
    "cases"
)

NO_DEFAULT_JOURNAL = (
    "'mmg_default_payment_journal' was not ported to Odoo 19: "
    "res.company.payment_default_journal_id does not exist on this database, "
    "so there is no company default for the Pay pop-up to offer and the whole "
    "premise of this case is absent. This is itself a migration finding — "
    "report it rather than treating the case as untestable"
)

NO_FOLLOWUP = (
    "'account_followup' (Odoo Enterprise, licence OEEL-1) is not installed on "
    "this database, so the Follow-up Levels menu and the "
    "account_followup.followup.line model do not exist. This is the "
    "module-did-not-install branch, which the workbook's If It Fails column "
    "distinguishes from 'the levels are missing' — they need different fixes"
)

NO_1099 = (
    "'l10n_us_1099' (Odoo Enterprise) is not installed on this database, so "
    "the '1099 Report" + ELLIPSIS + "' entry and the l10n_us_1099.wizard "
    "model do not exist. It auto-installs only when BOTH l10n_us and "
    "account_accountant are installed — check which of the two is missing, "
    "because a missing l10n_us means the US localisation itself did not come "
    "across, which is a much larger problem"
)

NO_TRANSFER_MODULE = (
    "The automatic-transfer module is not installed on this database. In "
    "Odoo 19 the v15 Enterprise module 'account_auto_transfer' was RENAMED "
    "'account_transfer', and unlike v15 it is NO LONGER auto_install — so an "
    "upgrade does not bring it along by itself and it must be installed "
    "deliberately. The MODEL names are unchanged (account.transfer.model / "
    "account.transfer.model.line), which means the gallery's migrated rules "
    "may still be sitting in the database, orphaned, with no module to "
    "display them. Install 'account_transfer' and re-run before concluding "
    "the rules were lost"
)


# ----------------------------------------------------------------- plumbing
def m2o_id(value):
    """RPC ``read()`` returns a Many2one as ``[id, display_name]`` or False."""
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    if isinstance(value, dict):          # web_read / onchange shape
        return value.get("id") or None
    return value or None


def m2o_name(value) -> str:
    if isinstance(value, (list, tuple)) and len(value) > 1:
        return value[1] or ""
    if isinstance(value, dict):
        return value.get("display_name") or ""
    return ""


def money(value) -> float:
    """Round to the cent — every workbook figure is stated to two places,
    and ``ctx.check`` compares with ``==``."""
    return round(float(value or 0.0), 2)


def x2m_ids(value) -> list[int]:
    """Ids out of an x2many value, in any shape the transports return.

    ``read()`` gives a plain list of ids; ``onchange()`` gives x2many values
    as commands (``addons/web/models/models.py:1990-1993``), so the same
    field arrives as ``[(6, 0, [ids])]`` or a run of ``(4, id)`` tuples.
    Guessing wrong yields an empty list, which would silently turn an
    assertion about the contents into an assertion about nothing.
    """
    if not value:
        return []
    ids: list[int] = []
    for item in value:
        if isinstance(item, int):
            ids.append(item)
        elif isinstance(item, dict):
            if item.get("id"):
                ids.append(item["id"])
        elif isinstance(item, (list, tuple)) and item:
            code = item[0]
            if code == 6 and len(item) > 2:          # SET
                ids = list(item[2] or [])
            elif code == 4 and len(item) > 1:        # LINK
                ids.append(item[1])
            elif code == 1 and len(item) > 1:        # UPDATE
                ids.append(item[1])
            elif code == 5:                          # CLEAR
                ids = []
            elif code == 3 and len(item) > 1:        # UNLINK
                ids = [i for i in ids if i != item[1]]
    return [i for i in ids if isinstance(i, int)]


def fields_present(rpc, model: str, names) -> set:
    """Field names of ``model`` the acting user can actually read.

    ``fields_get`` omits fields the user has no group for, which is the right
    verdict here: a value that cannot be read cannot be checked.
    """
    try:
        return set(rpc.call(model, "fields_get", list(names),
                            attributes=["type"]))
    except OdooRPCError:
        return set()


def selection_labels(rpc, model: str, field: str) -> dict:
    """``{raw value: label}`` for a Selection field.

    Every state comparison in this suite is made on the RAW value; labels are
    only ever reported. ('Test Mode' and 'Test' are the same state, and a
    test that compares labels reports a translation as a defect.)
    """
    try:
        spec = rpc.call(model, "fields_get", [field],
                        attributes=["selection"])
    except OdooRPCError:
        return {}
    return {str(k): str(v) for k, v in
            (spec.get(field, {}).get("selection") or [])}


# ------------------------------------------------------------------- gates
def require_v19(ctx):
    """BLOCK unless the target is Odoo 19 with a v19-shaped chart."""
    if ctx.env.version != "19":
        ctx.blocked(f"{V19_ONLY} (current target: {ctx.env.name})")
    rpc = ctx.adapter.rpc
    if not rpc.field_exists("account.account", "company_ids"):
        ctx.blocked(
            f"{V19_ONLY} — the target reports version {ctx.env.version} but "
            f"account.account has no 'company_ids' field, so this is not an "
            f"Odoo 19 chart of accounts "
            f"(addons/account/models/account_account.py:97)")


def module_state(rpc, name: str) -> str:
    """``ir.module.module.state`` for one module, '' when the row is absent.

    This — not ``model_exists`` — is the correct installed-probe. See the
    module docstring: ``account.report`` exists in Community with no engine.
    """
    try:
        rows = rpc.search_read("ir.module.module", [("name", "=", name)],
                               ["state"], limit=1)
    except OdooRPCError:
        return ""
    return (rows[0].get("state") or "") if rows else ""


def module_installed(rpc, name: str) -> bool:
    return module_state(rpc, name) == "installed"


def require_module(ctx, name: str, reason: str):
    """BLOCK with ``reason`` unless ``name`` is installed, naming its state."""
    state = module_state(ctx.adapter.rpc, name)
    if state != "installed":
        ctx.blocked(f"{reason} (ir.module.module state for {name!r}: "
                    f"{state or 'no such module row'})")
    ctx.log(f"module {name!r}: installed")


def require_account_reports(ctx):
    """BLOCK unless the Enterprise reports engine is live.

    Two probes, because either alone gives a false positive: the module row
    proves the engine's Python is loaded, and resolving a report xmlid proves
    its data rows were created.
    """
    require_v19(ctx)
    require_module(ctx, "account_reports", NO_ACCOUNT_REPORTS)
    rpc = ctx.adapter.rpc
    if "custom_handler_model_id" not in fields_present(
            rpc, "account.report", ["custom_handler_model_id"]):
        ctx.blocked(
            f"{NO_ACCOUNT_REPORTS} — ir.module.module says account_reports is "
            f"installed, but account.report has no 'custom_handler_model_id' "
            f"field, which the Enterprise override is what adds "
            f"(enterprise-19.0/account_reports/models/account_report.py:72). "
            f"The registry and the module list disagree; a module upgrade "
            f"probably failed half-way")


def report_ref(ctx, key: str) -> int:
    """Resolve one of :data:`REPORT_XMLID`, BLOCKing when it is absent."""
    xmlid = REPORT_XMLID[key]
    report_id = ctx.adapter.rpc.ref(xmlid)
    if not report_id:
        ctx.blocked(
            f"{NO_ACCOUNT_REPORTS} — the module is installed but the report "
            f"record {xmlid!r} does not resolve, so its data file did not "
            f"load")
    return report_id


def acting_company(ctx) -> dict:
    """The company the runner user acts as.

    Everything in this suite is scoped to this one company. The platform
    sends no ``allowed_company_ids``, so ``env.companies`` falls back to every
    company the user may enter and an unscoped search would reach a sibling
    company's records — which for ``account.account.code``, a
    company-dependent compute, would silently read a different value.
    """
    rpc = ctx.adapter.rpc
    user = rpc.call("res.users", "read", [rpc.uid], fields=["company_id"])[0]
    company_id = m2o_id(user["company_id"])
    wanted = ["name", "currency_id", "country_id", "vat", "chart_template",
              "payment_default_journal_id"]
    readable = [f for f in wanted
                if f in fields_present(rpc, "res.company", wanted)]
    row = rpc.read("res.company", [company_id], readable)[0]
    return {
        "id": company_id,
        "name": row.get("name") or "",
        "currency_id": m2o_id(row.get("currency_id")),
        "currency_name": m2o_name(row.get("currency_id")),
        "country_id": m2o_id(row.get("country_id")),
        "country_name": m2o_name(row.get("country_id")),
        "vat": row.get("vat") or "",
        "chart_template": row.get("chart_template") or "",
        "has_default_journal_field":
            "payment_default_journal_id" in readable,
        "payment_default_journal_id":
            m2o_id(row.get("payment_default_journal_id")),
    }


def company_ctx(company: dict, **extra) -> dict:
    """Context pinning the acting company — mandatory on every read.

    Three of the five surfaces this suite reads carry a multi-company
    ``ir.rule``, and ``account.account.code`` is company-dependent, so an
    unpinned read is not merely broader: it can return a different value.
    """
    context = {"allowed_company_ids": [company["id"]],
               "company_id": company["id"]}
    context.update(extra)
    return context


# ------------------------------------------------- form / onchange mirroring
def _spec(names) -> dict:
    """``fields_spec`` for onchange — the shape the web client sends."""
    return {name: {} for name in names}


def form_defaults(ctx, model: str, names, context: dict) -> dict:
    """The values a form shows when it OPENS, under ``context``.

    ``onchange(values, [], fields_spec)`` with an empty ``field_names`` is the
    web client's "record created from scratch" call: it applies
    ``default_get`` for every field in the spec, then runs the onchange
    methods over all of them (``addons/web/models/models.py:2019-2031``).
    That is precisely what the workbook means by "the pop-up offers…".

    **The leading ``[]`` is the ids argument and is mandatory.**
    ``BaseModel.onchange`` (``addons/web/models/models.py:1973``) carries no
    ``@api.model``, so ``call_kw`` consumes the first positional as the
    recordset — ``ids, args = args[0], args[1:]``
    (``odoo/service/model.py:86``). Sending ``values`` first makes Odoo browse
    the values dict and then call ``onchange(recs, field_names, fields_spec)``
    one argument short, failing with
    ``Base.onchange() missing 1 required positional argument: 'fields_spec'``.
    An empty ids list is exactly what the web client sends for an unsaved
    record.
    """
    payload = ctx.adapter.rpc.call(model, "onchange", [], {}, [], _spec(names),
                                   context=context) or {}
    return payload.get("value") or {}


def onchange_values(ctx, model: str, values: dict, changed, names,
                    context: dict | None = None) -> dict:
    """The values a form shows after the user edits ``changed``.

    Same ids-first rule as :func:`form_defaults`: the leading ``[]`` is the
    recordset ``call_kw`` slices off before the method is called
    (``odoo/service/model.py:86``), not part of ``onchange``'s own signature.
    """
    payload = ctx.adapter.rpc.call(
        model, "onchange", [], values, list(changed), _spec(names),
        context=context or {}) or {}
    return payload.get("value") or {}


# ------------------------------------------------------------ menu reading
def menu_by_xmlid(ctx, xmlid: str) -> dict:
    """One ``ir.ui.menu`` row, or ``{}`` when the xmlid does not resolve.

    ``ir.ui.menu`` is group-filtered, so an empty result means either "the
    menu is gone" or "this user may not see it" — callers must check the
    group before reporting the first. That distinction is the whole of
    TC-INV-014's precondition and half of TC-INV-016's.
    """
    menu_id = ctx.adapter.rpc.ref(xmlid)
    if not menu_id:
        return {}
    try:
        rows = ctx.adapter.rpc.read("ir.ui.menu", [menu_id],
                                    ["name", "parent_id", "action",
                                     "sequence", "active"])
    except OdooRPCError:
        return {}
    if not rows:
        return {}
    row = rows[0]
    return {"id": menu_id, "name": row.get("name") or "",
            "parent_id": m2o_id(row.get("parent_id")),
            "parent_name": m2o_name(row.get("parent_id")),
            "action": row.get("action") or "",
            "sequence": row.get("sequence"),
            "active": bool(row.get("active"))}


def has_group(ctx, xmlid: str) -> bool:
    """``res.users.has_group`` — public, and the correct precondition probe.

    **ids-first, and the id must be the calling user's own.** In v19
    ``has_group`` is a RECORD method — only ``@api.readonly``
    (``odoo/addons/base/models/res_users.py:1065-1066``) — and it opens with
    ``ensure_one()`` and refuses any user but ``self.env.user``
    (``:1073-1078``). ``call_kw`` therefore slices the first positional off as
    the recordset (``odoo/service/model.py:86``): passing ``xmlid`` alone made
    Odoo ``browse()`` the string — ``tuple("base.group_x")``,
    ``odoo/orm/models.py:5892-5898`` — and then call ``has_group`` with no
    group at all, so every probe raised and this helper answered ``False`` for
    a user who *is* in the group. Sending ``[rpc.uid]`` is the same recordset
    the web client sends.
    """
    rpc = ctx.adapter.rpc
    try:
        return bool(rpc.call("res.users", "has_group", [rpc.uid], xmlid))
    except OdooRPCError:
        return False


# --------------------------------------------------------- report running
def run_report(ctx, report_id: int, options: dict, company: dict) -> tuple:
    """Open one ``account.report`` and return ``(opts, info)``.

    Three public calls, exactly what the client does:
    ``get_options`` -> re-read ``opts['report_id']`` -> ``get_report_information``.

    **Re-reading the report id is mandatory, not defensive.**
    ``_init_options_variants`` can reroute to a country variant, and
    ``l10n_us_reports`` ships Balance Sheet and Profit-and-Loss variants whose
    ``root_report_id`` points at the ``account_reports`` originals
    (``enterprise-19.0/l10n_us_reports/data/balance_sheet.xml:5``). On a US
    company — which the gallery is — opening the Balance Sheet menu ends up
    running the ``l10n_us_reports`` variant. Asserting anything about the
    report id would therefore fail for a correct system.
    """
    rpc = ctx.adapter.rpc
    context = company_ctx(company)
    opts = rpc.call("account.report", "get_options", [report_id], options,
                    context=context)
    effective_id = opts.get("report_id") or report_id
    if effective_id != report_id:
        ctx.log(f"report #{report_id} rerouted to variant #{effective_id} by "
                f"_init_options_variants — using the variant, as the client "
                f"does (l10n_us_reports ships BS/PL variants for a US company)")
    info = rpc.call("account.report", "get_report_information",
                    [effective_id], opts, context=context)
    return opts, info


def column_index(opts: dict, expression_label: str,
                 column_group_key: str | None = None) -> int:
    """Index of a column by its EXPRESSION LABEL, never by position.

    The trial-balance handler injects Initial Balance and End Balance column
    groups around the declared Debit/Credit pair, so a positional read is
    wrong on exactly the report the workbook cares most about.
    """
    for index, column in enumerate(opts.get("columns") or []):
        if column.get("expression_label") != expression_label:
            continue
        if (column_group_key is None
                or column.get("column_group_key") == column_group_key):
            return index
    return -1


def cell_value(line: dict, index: int):
    """``no_format`` out of one report cell — the float, not the string.

    ``name`` is the formatted string ('1,234.56 $'), and ``currency`` arrives
    over JSON as the repr ``"res.currency(2,)"``, so neither is usable.
    """
    if index < 0:
        return None
    columns = line.get("columns") or []
    if index >= len(columns):
        return None
    return (columns[index] or {}).get("no_format")


def trial_balance_column_groups(opts: dict) -> dict:
    """``{trial_balance_column_type: column_group_key}``.

    The type lives in each group's ``forced_options``; selecting cells by it
    is what keeps the period figures apart from the initial and end balances.
    """
    found = {}
    for key, group in (opts.get("column_groups") or {}).items():
        forced = group.get("forced_options") or {}
        kind = forced.get("trial_balance_column_type")
        if kind:
            found[kind] = key
    return found


# ------------------------------------------------------------ HTTP reports
def _http(ctx):
    """An authenticated web session, created once per test."""
    from framework.fg_common import http_session
    if getattr(ctx, "_fg07_opener", None) is None:
        ctx._fg07_opener = http_session(ctx.env)
    return ctx._fg07_opener


def report_html(ctx, report_name: str, res_id: int,
                report_type: str = "pdf") -> tuple:
    """``(status, text)`` for ``/report/html/<report_name>/<id>``.

    ``?report_type=pdf`` is **mandatory**, not cosmetic. In html mode every
    section row emits an extra mobile ``<td colspan="2">`` that is
    ``d-none`` in pdf mode, so the colspan arithmetic TC-INV-002 performs
    would read the wrong cell and report a correct template as broken.

    Never raises for an HTTP error status: the status is returned so the
    caller can ``ctx.check`` it. A 500 here is a finding about the report,
    and it must be recorded as one rather than becoming AUTOMATION_ERROR.
    """
    url = (f"{ctx.env.base_url}/report/html/"
           f"{urllib.parse.quote(report_name)}/{int(res_id)}"
           f"?report_type={urllib.parse.quote(report_type)}")
    try:
        with _http(ctx).open(url, timeout=180) as res:
            return res.status, res.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", "replace")
        except Exception:                       # noqa: BLE001
            pass
        return exc.code, body
    except OSError as exc:
        return 0, f"{type(exc).__name__}: {exc}"


def report_pdf(ctx, report_name: str, res_id: int) -> tuple:
    """``(status, bytes)`` for ``/report/pdf/<report_name>/<id>``.

    Requires wkhtmltopdf on the server — probe
    :func:`wkhtmltopdf_state` first and keep the PDF assertions optional, so
    a QA container without it reports an environment fact rather than a
    product defect.
    """
    url = (f"{ctx.env.base_url}/report/pdf/"
           f"{urllib.parse.quote(report_name)}/{int(res_id)}")
    try:
        with _http(ctx).open(url, timeout=300) as res:
            return res.status, res.read()
    except urllib.error.HTTPError as exc:
        return exc.code, b""
    except OSError:
        return 0, b""


def wkhtmltopdf_state(ctx) -> str:
    """``ir.actions.report.get_wkhtmltopdf_state()`` — public, ``@api.model``."""
    try:
        return str(ctx.adapter.rpc.call("ir.actions.report",
                                        "get_wkhtmltopdf_state") or "")
    except OdooRPCError as exc:
        ctx.log(f"get_wkhtmltopdf_state unavailable ({exc})")
        return ""


def post_account_reports_export(ctx, options: dict, file_generator: str
                                ) -> tuple:
    """POST the export form to ``/account_reports`` and return the file.

    ``(status, content_type, disposition, body)``.

    The bytes must come over HTTP, not over ``call_kw``: the RPC layer's
    ``json_default`` decodes ``bytes`` to ``str`` and corrupts a binary
    payload, so an XLSX fetched that way is silently unusable. The controller
    is ``type='http', auth='user', methods=['POST'], csrf=False``
    (``enterprise-19.0/account_reports/controllers/main.py:16``).
    """
    payload = urllib.parse.urlencode({
        "options": json.dumps(options, default=str),
        "file_generator": file_generator,
    }).encode()
    request = urllib.request.Request(
        f"{ctx.env.base_url}/account_reports", data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with _http(ctx).open(request, timeout=300) as res:
            return (res.status,
                    res.headers.get("Content-Type", ""),
                    res.headers.get("Content-Disposition", ""),
                    res.read())
    except urllib.error.HTTPError as exc:
        return exc.code, "", "", b""
    except OSError as exc:
        ctx.log(f"export POST failed: {type(exc).__name__}: {exc}")
        return 0, "", "", b""


# ---------------------------------------------------------------- fixtures
def make_partner(ctx, label: str, *, company: dict) -> int:
    """One FG07-marked contact. Never reuses a business record."""
    partner_id = ctx.adapter.rpc.call("res.partner", "create", {
        "name": f"{MARK} {label}",
        "is_company": True,
        "comment": "Created by the odoo-regression platform (FG-07). "
                   "Safe to delete.",
    }, context=company_ctx(company))
    ctx.log(f"fixture partner #{partner_id} {MARK} {label!r}")
    return partner_id


def make_product(ctx, label: str, price: float) -> int:
    """One FG07-marked product carrying NO Odoo-side tax.

    Taxes are cleared so that every figure the workbook quotes (1,000.00 /
    2,000.00 / 1,500.00) is the figure the invoice actually shows, and — more
    importantly — so that no AvaTax computation can fire from a fixture. The
    only FG-07 case that wants tax is TC-INV-003, which reads an existing
    posted AvaTax invoice rather than creating one.
    """
    rpc = ctx.adapter.rpc
    values = {
        "name": f"{MARK} {label}",
        "default_code": f"{MARK}-{label.upper().replace(' ', '-')}",
        "list_price": price,
        "sale_ok": True,
        "taxes_id": [(6, 0, [])],
    }
    values.update(ctx.adapter.storable_product_values())
    tmpl_id = rpc.create("product.template", values)
    variant = rpc.search_read("product.product",
                              [("product_tmpl_id", "=", tmpl_id)],
                              ["id"], limit=1)
    ctx.log(f"fixture product #{variant[0]['id']} {values['name']!r} @ {price}")
    return variant[0]["id"]


def make_invoice(ctx, partner_id: int, lines, *, company: dict,
                 post: bool = False, origin: str = "",
                 payment_reference: str = "", extra: dict | None = None
                 ) -> int:
    """One FG07 customer invoice. ``lines`` is ``[(product_id, qty, price)]``.

    ``origin`` fills ``invoice_origin`` — TC-INV-001 item (d) checks that the
    header label reads "Order Number:" rather than "Source", and the label is
    only rendered when the field has a value, so an assertion on an invoice
    without one would pass vacuously.

    ``payment_reference`` matters for the same reason on item (i): the
    "Payment Communication" paragraph is only emitted when there is a
    reference to communicate.
    """
    rpc = ctx.adapter.rpc
    invoice_lines = []
    for product_id, qty, price in lines:
        invoice_lines.append((0, 0, {
            "product_id": product_id,
            "quantity": qty,
            "price_unit": price,
            "tax_ids": [(6, 0, [])],
        }))
    values = {"move_type": "out_invoice", "partner_id": partner_id,
              "invoice_line_ids": invoice_lines}
    if origin:
        values["invoice_origin"] = origin
    if payment_reference:
        values["payment_reference"] = payment_reference
    if extra:
        values.update(extra)
    move_id = rpc.call("account.move", "create", values,
                       context=company_ctx(company))
    if post:
        rpc.call("account.move", "action_post", [move_id])
    row = rpc.read("account.move", [move_id],
                   ["name", "state", "amount_total"])[0]
    ctx.log(f"fixture invoice #{move_id} {row.get('name')!r} — "
            f"state={row.get('state')!r} "
            f"total={money(row.get('amount_total')):.2f}")
    return move_id


def structured_invoice_lines(product_id: int, *, n_product: int = 25,
                             long_text: str = "") -> list:
    """Invoice lines for TC-INV-002: sections, a note and N product lines.

    The long description is ONE long paragraph, deliberately not many hard
    newlines: ``has_long_desc`` (``addons/account/views/report_invoice.xml:
    172``) counts newlines and, once tripped, stops the table head repeating
    on later pages — which would make workbook step 7 report a false failure
    caused by the fixture rather than by the template.
    """
    lines = [(0, 0, {"display_type": "line_section",
                     "name": f"{MARK} Section A — Exhibition pieces"})]
    half = max(1, n_product // 2)
    for index in range(n_product):
        values = {"display_type": "product", "product_id": product_id,
                  "quantity": 1, "price_unit": 100.0 + index,
                  "tax_ids": [(6, 0, [])]}
        if index == 0 and long_text:
            values["name"] = long_text
        lines.append((0, 0, values))
        if index == half - 1:
            lines.append((0, 0, {
                "display_type": "line_section",
                "name": f"{MARK} Section B — Estate consignment"}))
    lines.append((0, 0, {"display_type": "line_note",
                         "name": f"{MARK} Note — condition report supplied "
                                 f"separately."}))
    return lines


def register_payment(ctx, move_ids, values: dict | None = None, *,
                     company: dict) -> int:
    """Create an ``account.payment.register`` wizard over ``move_ids``.

    Returns the wizard id; the caller reads it, writes to it and confirms.
    The context is the one the Pay button sends
    (``active_model='account.move'``), because the wizard's defaults are
    computed from it.
    """
    context = company_ctx(company, active_model="account.move",
                          active_ids=list(move_ids),
                          active_id=list(move_ids)[0])
    return ctx.adapter.rpc.call("account.payment.register", "create",
                                dict(values or {}), context=context)


def confirm_payment_register(ctx, wizard_id: int, move_ids, *,
                             company: dict) -> list:
    """``action_create_payments`` and return the payment ids it produced.

    ``dont_redirect_to_payments`` is deliberately NOT passed: with it the
    method returns a bare ``True`` and the ids have to be guessed from a
    search, which on a live database can pick up a payment another process
    created. Without it the returned act_window carries them.
    """
    context = company_ctx(company, active_model="account.move",
                          active_ids=list(move_ids),
                          active_id=list(move_ids)[0])
    action = ctx.adapter.rpc.call("account.payment.register",
                                  "action_create_payments", [wizard_id],
                                  context=context) or {}
    if isinstance(action, dict):
        if action.get("res_id"):
            return [action["res_id"]]
        domain = action.get("domain") or []
        for clause in domain:
            if (isinstance(clause, (list, tuple)) and len(clause) == 3
                    and clause[0] == "id" and clause[1] == "in"):
                return list(clause[2] or [])
    return []


# ----------------------------------------------------------------- readers
def move_row(ctx, move_id: int, extra=()) -> dict:
    """The invoice fields every FG-07 payment case reads."""
    fields = ["name", "state", "payment_state", "amount_total",
              "amount_residual", "partner_id", "invoice_origin",
              "payment_reference"]
    rpc = ctx.adapter.rpc
    if STATUS_FIELD in fields_present(rpc, "account.move", [STATUS_FIELD]):
        fields.append(STATUS_FIELD)
    fields.extend(f for f in extra if f not in fields)
    row = rpc.read("account.move", [move_id], fields)[0]
    row["amount_total"] = money(row.get("amount_total"))
    row["amount_residual"] = money(row.get("amount_residual"))
    return row


def payment_row(ctx, payment_id: int) -> dict:
    """One ``account.payment`` as the workbook reads it."""
    row = ctx.adapter.rpc.read(
        "account.payment", [payment_id],
        ["name", "state", "amount", "partner_id", "journal_id",
         "payment_method_line_id", "is_matched", "currency_id"])[0]
    return {"id": payment_id, "name": row.get("name") or "",
            "state": row.get("state") or "",
            "amount": money(row.get("amount")),
            "partner_id": m2o_id(row.get("partner_id")),
            "partner": m2o_name(row.get("partner_id")),
            "journal_id": m2o_id(row.get("journal_id")),
            "journal": m2o_name(row.get("journal_id")),
            "method_line_id": m2o_id(row.get("payment_method_line_id")),
            "method_line": m2o_name(row.get("payment_method_line_id")),
            "is_matched": bool(row.get("is_matched")),
            "currency": m2o_name(row.get("currency_id"))}


def residual_manual_step(ctx, text: str):
    """Record a comparison only a human (or a Novobi baseline) can settle."""
    ctx.log(f"RESIDUAL MANUAL STEP — {text}")


def observation(ctx, text: str):
    """Record a v19 difference the workbook says is EXPECTED.

    Five FG-07 cases carry one of these, and the workbook is explicit that
    raising them is wrong: the 'In payment' search filter (TC-INV-004), the
    on-screen Taxes column (TC-INV-003), the all-journals dropdown and the
    customer-preference precedence (TC-INV-006), the 'Wire Transfer' label on
    the renamed Custom provider (TC-INV-010), and the 'Running' -> 'In
    Progress' relabelling (TC-INV-016). They are logged, never asserted in
    either direction.
    """
    ctx.log(f"OBSERVATION (expected in v19, NOT a defect) — {text}")


def finding(ctx, text: str):
    """Record something the client should act on that is not this case's
    pass/fail question."""
    ctx.log(f"FINDING — {text}")


# ----------------------------------------------------------------- sweeping
def sweep_fg07(ctx):
    """Remove leftovers from previous FG-07 runs — marker-scoped only.

    Order matters: payments before the invoices they are matched to, invoices
    before the partners and products they point at.

    POSTED moves are excluded **in the domain** rather than attempted and
    logged. A posted invoice legitimately refuses to unlink, and several
    FG-07 cases are required by the workbook's *State After The Test* to
    leave one behind ("One invoice paid through the transit journal").

    Never called by the six read-only cases: a sweep is itself a delete, and
    their *State After The Test* is "Nothing changed".
    """
    rpc = ctx.adapter.rpc
    marker = f"{MARK} %"
    try:
        company_id = acting_company(ctx)["id"]
    except (OdooRPCError, IndexError, KeyError) as exc:
        ctx.log(f"[sweep] could not resolve the acting company ({exc}) — "
                f"nothing swept")
        return
    scope = [("company_id", "=", company_id)]

    def _drop(model, domain, label):
        try:
            ids = rpc.search(model, domain)
        except OdooRPCError as exc:
            ctx.log(f"[sweep] {model} not searchable ({exc}) — skipped")
            return
        if not ids:
            return
        try:
            rpc.unlink(model, ids)
            ctx.log(f"[sweep] removed {len(ids)} {label}")
        except OdooRPCError as exc:
            ctx.log(f"[sweep] {len(ids)} {label} not removable ({exc}) — "
                    f"left in place")

    # 1. payments whose journal entry never posted. A posted payment is left
    #    alone: v19's account.payment.unlink() calls button_draft() on the
    #    move and then unlinks it, so the posted-move guard never fires and
    #    accounting evidence would be destroyed silently.
    _drop("account.payment",
          [("partner_id.name", "like", marker),
           ("move_id.state", "!=", "posted")] + scope,
          "FG07 payment(s) whose journal entry never posted")

    # 2. draft/cancelled invoices and entries.
    _drop("account.move",
          [("partner_id.name", "like", marker),
           ("state", "in", ("draft", "cancel"))] + scope,
          "FG07 invoice(s)/journal entr(ies)")

    # 3. products, then partners.
    for model in ("product.product", "product.template"):
        try:
            ids = rpc.search(model, [("name", "like", marker),
                                     ("active", "in", [True, False])])
        except OdooRPCError:
            continue
        if not ids:
            continue
        try:
            rpc.unlink(model, ids)
        except OdooRPCError:
            try:
                rpc.write(model, ids, {"active": False})
            except OdooRPCError:
                pass
    _drop("res.partner",
          [("name", "like", marker), ("user_ids", "=", False)],
          "FG07 contact(s)")


def cleanup(ctx, created: dict):
    """Best-effort teardown of ids captured during a test, then a sweep.

    ``created`` maps model name -> list of ids, deleted in the order given.
    Never raises: an unguarded call here would escape the caller's ``finally``
    and be recorded as ERROR/AUTOMATION_ERROR, destroying the real FAILED or
    BLOCKED verdict the test had already reached.

    **Callers MUST remove an id from ``created`` once its record is posted.**
    This function refuses posted moves and payments itself as well, rather
    than trusting every caller.
    """
    rpc = ctx.adapter.rpc
    for model, ids in (created or {}).items():
        ids = [i for i in ids if i]
        if not ids:
            continue
        if model in ("account.move", "account.payment"):
            state_field = "state" if model == "account.move" else "move_id.state"
            try:
                posted = rpc.search(model, [("id", "in", ids),
                                            (state_field, "=", "posted")])
            except Exception as exc:              # noqa: BLE001
                ctx.log(f"[cleanup] could not classify {model}{ids} ({exc}) — "
                        f"left in place rather than risking a delete that "
                        f"resets a posted entry to draft")
                continue
            if posted:
                ctx.log(f"[cleanup] posted {model} {posted} left in place BY "
                        f"DESIGN — deleting a posted entry destroys accounting "
                        f"evidence, and the workbook's State After The Test "
                        f"expects several of these to survive")
                ids = [i for i in ids if i not in set(posted)]
                if not ids:
                    continue
        try:
            rpc.unlink(model, ids)
        except Exception as exc:                  # noqa: BLE001
            ctx.log(f"[cleanup] {model}{ids} not removable ({exc}) — left in "
                    f"place")
    try:
        sweep_fg07(ctx)
    except Exception as exc:                      # noqa: BLE001
        ctx.log(f"[cleanup] sweep incomplete: {exc}")


def restore_company_value(ctx, company: dict, field: str, value):
    """Put a company-wide setting back, never raising.

    TC-INV-006 changes ``payment_default_journal_id``, which every future
    payment in the database reads. The workbook is emphatic ("CONFIRM THIS
    before closing the case"), so the restore runs from ``finally`` and the
    caller asserts the restored value afterwards.
    """
    try:
        ctx.adapter.rpc.call("res.company", "write", [company["id"]],
                             {field: value or False},
                             context=company_ctx(company))
        ctx.log(f"restored res.company.{field} = {value!r}")
        return True
    except Exception as exc:                      # noqa: BLE001
        ctx.log(f"[restore] could not put res.company.{field} back to "
                f"{value!r} ({exc}) — RAISE THIS: it is a company-wide "
                f"setting and every future payment reads it")
        return False
