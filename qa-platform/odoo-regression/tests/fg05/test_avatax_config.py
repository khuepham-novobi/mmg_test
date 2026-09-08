"""FG-05 — TC-DAT-017: AvaTax setup is complete and correct after upgrade.

Registers ``TEST-FG05-DAT-017`` (client manual testing guideline row 1.0,
P0, business area "Tax setup"). This is the ONLY setup-verification case in
FG-05 and the workbook says to run it FIRST (GATE 3): if it fails, every
other FG-05 case gives a misleading answer, because tax is still calculated
— just wrongly — and nothing on screen says so.

What it proves (one assertion per workbook Expected Result line)
---------------------------------------------------------------
1. ``Use AvaTax`` is on and all seven values of workbook step 2 are
   readable (Environment, API ID, API KEY, Company Code, Use UPC, Commit
   Transactions, Address Validation).
2. ``Test connection`` returns "Authentication success." — not a failure
   message.
3. Every fiscal position with ``Use AvaTax API`` ticked carries BOTH
   ``avatax_invoice_account_id`` and ``avatax_refund_account_id``, and both
   accounts exist in the Chart of Accounts with a non-empty code.
4. AvaTax categories survived: product categories still carry
   ``avatax_category_id`` and every referenced ``product.avatax.category``
   still exists with a code.
5. The exempt customer survived: partners still carry
   ``avalara_exemption_id`` (at least one alongside an
   ``avalara_partner_code``), and every referenced ``avatax.exemption``
   still exists with a code.

Read-only by construction
-------------------------
The workbook's Test Data says "Do not type new values in this case — you
are only comparing", and its State After The Test says "Nothing changed".
This module therefore creates NO business record, writes NO field, and
calls neither ``sweep_fg05`` nor ``cleanup`` — a sweep is itself a delete
and would violate the workbook. The single exception is one
``res.config.settings`` TransientModel row, which exists only because
``avatax_ping()`` is a method on that model; ``execute()`` is never called,
no setting is written, and the row is unlinked again in a ``finally``.

``ctx.sql`` is deliberately NOT used: it raises BLOCKED when ``pg_*`` is
unconfigured, and every value this case needs is reachable over RPC.

Documented adaptation — the Novobi printout
-------------------------------------------
The workbook compares every value against "the old-system printout of the
AvaTax settings screen, the AvaTax fiscal positions with their two account
codes, and the AvaTax category on each product category". The platform does
not have that printout and must not invent one. The adaptation is:

* assert every structural invariant that does not need the printout — the
  fields exist in v19, ``Use AvaTax`` is on, the credentials are SET, the
  connection authenticates, at least one AvaTax fiscal position exists with
  both accounts present and resolvable, at least one product category
  carries an AvaTax category, at least one customer carries an exemption;
* capture the FULL inventory into the execution log and into a CSV
  artifact (``TC-DAT-017-avatax-setup-inventory.csv``) so the human tester
  ticks it off against the printout, and name each remaining comparison as
  a RESIDUAL MANUAL STEP log line. The evidence step runs from a
  ``finally`` block, so the inventory is produced even when an assertion
  fails — which is exactly when the tester needs it.

Credential values never enter evidence: ``avalara_api_id`` /
``avalara_api_key`` carry ``groups='base.group_system'``
(account_avatax/models/res_company.py:15-16) and are recorded as ``set`` /
``not set`` only, per the suite contract in ``tests/fg05/common.py``.

Documented adaptation — no sandbox gate on the whole test
---------------------------------------------------------
The workbook's "What You Need" for this row is "Novobi baseline", not an
Avalara sandbox, so the case calls :func:`require_v19` and NOT
``require_sandbox``. Workbook steps 1-2 and 4-8 are provable offline. Only
step 3 (Test connection) reaches Avalara, so only step 3 is gated, on the
same conditions ``require_sandbox`` applies (Use AvaTax on, environment ==
'sandbox', both credentials set — never production: safety rule 1 of the
guideline Read Me). When the gate is not met, or when the ping call itself
fails for transport reasons, step 3 is recorded as NOT EVALUATED with a
precise reason instead of blocking the whole test.

Verified v19 API surface (read from source, not guessed)
--------------------------------------------------------
* ``res.company``: ``setting_account_avatax``, ``avalara_environment``,
  ``avalara_api_id``, ``avalara_api_key``, ``avalara_commit``,
  ``avalara_address_validation``, ``avalara_use_upc``
  (account_avatax/models/res_company.py:12-30).
* "Company Code" has NO ``res.company`` field in v19. The settings label
  "Company Code" (views/res_config_settings_views.xml:47-48) is bound to
  ``res.config.settings.avalara_partner_code``, a ``related`` on
  ``company_id.partner_id.avalara_partner_code`` — the value lives on
  ``res.partner.avalara_partner_code`` of the COMPANY's own partner
  (models/res_company.py:44-51, models/res_partner.py:15-18). The test
  reads it there and logs the mapping; an empty value is legal, Avalara
  reads an empty Company Code as DEFAULT.
* "Test connection" = ``res.config.settings.avatax_ping()``; it returns an
  ``ir.actions.act_window`` on ``avatax.connection.test.result`` whose
  ``server_response`` Html field starts with "Authentication success." or
  "Authentication failed." (models/res_company.py:118-140).
* ``account.fiscal.position``: ``is_avatax`` ("Use AvaTax API"),
  ``avatax_invoice_account_id``, ``avatax_refund_account_id``
  (models/account_fiscal_position.py:16-27).
* AvaTax category master is ``product.avatax.category`` (``code`` and
  ``description`` both required, display name ``[code] description``);
  ``avatax_category_id`` exists on ``product.category``,
  ``product.template`` AND ``product.product``, resolved product ->
  template -> category (models/product.py:6-58).
* ``res.partner``: ``avalara_exemption_id`` -> ``avatax.exemption``
  (**company_dependent**, so values read here are the acting company's),
  ``avalara_partner_code``, and ``avatax_unique_code`` (label "Avalara
  Code", computed, not stored) from the ``account.avatax.unique.code``
  mixin (models/res_partner.py:11-25,
  models/account_avatax_unique_code.py:9-22).
"""
from __future__ import annotations

import csv
import re

from adapters.base import OdooRPCError
from framework.registry import test_case
from tests.fg05.common import (MODULE, WORKFLOW, WORKFLOW_NAME,
                               company_avatax_config, require_v19, trace)

# The seven values workbook step 2 reads off the AvaTax settings block, in
# screen order (account_avatax/views/res_config_settings_views.xml:35-60).
SETTINGS_ORDER = ("Environment", "API ID", "API KEY", "Company Code",
                  "Use UPC", "Commit Transactions", "Address Validation")

COMPANY_SETTING_FIELDS = ("setting_account_avatax", "avalara_environment",
                          "avalara_commit", "avalara_address_validation",
                          "avalara_use_upc")

FISCAL_POSITION_FIELDS = ("is_avatax", "avatax_invoice_account_id",
                          "avatax_refund_account_id")

PARTNER_AVATAX_FIELDS = ("avalara_exemption_id", "avalara_partner_code",
                         "avatax_unique_code")

SAMPLE = 20        # rows echoed into the execution log per section
CSV_LIMIT = 500    # rows captured into the evidence CSV per section

TAG_RE = re.compile(r"<[^>]+>")

INVENTORY_CSV = "TC-DAT-017-avatax-setup-inventory.csv"


def _m2o(value):
    """Many2one read back as ``[id, name]`` -> id (None when unset)."""
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    return value or None


def _m2o_name(value) -> str:
    if isinstance(value, (list, tuple)) and len(value) > 1:
        return value[1] or ""
    return ""


def _fields_present(rpc, model: str, names) -> set:
    """Field names of ``model`` the acting user can actually see.

    ``fields_get`` omits fields the user has no group for, which is the
    right verdict here: a value that cannot be read cannot be ticked off
    against the printout.
    """
    try:
        return set(rpc.call(model, "fields_get", list(names),
                            attributes=["type"]))
    except OdooRPCError:
        return set()


def _plain(html: str) -> str:
    """Html field -> single-line readable text (evidence, not parsing)."""
    return " ".join(TAG_RE.sub(" ", html or "").split())


def _connection_gate(config) -> list:
    """Reasons this run must NOT call Avalara (empty list = safe to ping).

    Mirrors ``tests.fg05.common.require_sandbox`` without blocking: this
    case is a Novobi-baseline read, and steps 1-2 / 4-8 stay provable.
    """
    gate = []
    if not config["use_avatax"]:
        gate.append("'Use AvaTax' is not enabled on the company")
    if config["environment"] != "sandbox":
        gate.append(
            f"Avalara Environment reads "
            f"{config['environment'] or 'empty'!r}, not 'sandbox' — this "
            f"suite never calls a non-sandbox Avalara account (guideline "
            f"Read Me, safety rule 1)")
    absent = [f"avalara_{key}" for key in ("api_id", "api_key")
              if config[key] != "set"]
    if absent:
        gate.append(f"credential(s) not readable as set: "
                    f"{', '.join(absent)}")
    return gate


def _check_connection(ctx, rpc, config, evidence, residual):
    """Workbook step 3 — 'Test connection' / Server Response box.

    The only part of TC-DAT-017 that reaches Avalara. Records the workbook
    assertion when the sandbox is usable, and a precise NOT EVALUATED note
    otherwise (an unreachable endpoint is an environment condition; a wrong
    credential comes back INSIDE the response as "Authentication failed."
    and is therefore a real failure of the expected result).
    """
    gate = _connection_gate(config)
    if gate:
        reason = "; ".join(gate)
        ctx.log(f"NOT EVALUATED — workbook step 3 (Test connection "
                f"returns 'Authentication success.') was not run because "
                f"{reason}. Steps 1-2 and 4-8 are unaffected.")
        residual.append(
            f"workbook step 3 — Test connection was NOT evaluated "
            f"({reason}). Run it by hand from Accounting > Configuration > "
            f"Settings > Taxes > AvaTax and confirm the Server Response "
            f"reads 'Authentication success.'")
        evidence.append(("connection", "test_connection",
                         f"NOT EVALUATED: {reason}"))
        return

    settings_id = None
    try:
        # avatax_ping() is a method on res.config.settings, so one
        # transient row is unavoidable. execute() is never called and no
        # setting is written: this reads the credentials and pings.
        settings_id = rpc.create("res.config.settings", {})
        action = rpc.call("res.config.settings", "avatax_ping",
                          [settings_id]) or {}
        ctx.check("Test connection opens the AvaTax connection test result "
                  "window", "avatax.connection.test.result",
                  action.get("res_model"))
        result_id = action.get("res_id")
        ctx.check_true("Test connection created an "
                       "avatax.connection.test.result record",
                       bool(result_id),
                       actual_desc=f"act_window res_id={result_id!r}")
        raw = rpc.read("avatax.connection.test.result", [result_id],
                       ["server_response"])[0].get("server_response") or ""
        response = _plain(raw)
        # NOTHING but the leading verdict sentence may leave this scope.
        # res.config.settings._format_response() is not a verdict string:
        # it appends '<ul>' and one '<li>{Key}: {value}</li>' for EVERY
        # key of the raw Avalara utilities/ping payload
        # (account_avatax/models/res_company.py:137-144). Avalara's
        # PingResultModel echoes authenticatedUserName /
        # authenticatedUserId / authenticatedAccountId /
        # authenticatedCompanyId, and _get_client authenticates with
        # HTTPBasicAuth(company.avalara_api_id, company.avalara_api_key)
        # (models/account_external_tax_mixin.py:308-323,
        # lib/avatax_client.py:57-64), so that identifier IS the value of
        # avalara_api_id. _plain() drops the tags but keeps the values.
        # The body is therefore credential material: it never reaches the
        # execution log, the CSV artifact or the assertion evidence, per
        # this module's contract and tests/fg05/common.py, which record
        # avalara_api_id as set / not set only.
        ok = response.startswith("Authentication success.")
        failed = response.startswith("Authentication failed.")
        verdict = ("Authentication success." if ok else
                   "Authentication failed." if failed else
                   "unrecognised response")
        ctx.log(f"Server Response — verdict sentence only ({verdict!r}); "
                f"the rest of the box lists the raw Avalara ping payload, "
                f"which echoes the authenticated Avalara account "
                f"identifier and is deliberately not recorded")
        evidence.append(("connection", "server_response", verdict))
        if not ok and not failed:
            residual.append(
                "workbook step 3 — the Server Response box started with "
                "neither 'Authentication success.' nor 'Authentication "
                "failed.'; only that leading sentence is captured here, "
                "because the remainder of the box echoes the Avalara "
                "account identifier. Read the box by hand in Accounting > "
                "Configuration > Settings > Taxes > AvaTax > Test "
                "connection.")
        # Expected Result line 2.
        ctx.check_true(
            "Test connection Server Response reads 'Authentication "
            "success.' and not a failure message",
            ok and not failed,
            actual_desc=f"server_response verdict sentence = {verdict!r} "
                        f"(the rest of the response body is withheld: it "
                        f"echoes the Avalara account identifier)")
    except OdooRPCError as exc:
        ctx.log(f"NOT EVALUATED — workbook step 3 (Test connection returns "
                f"'Authentication success.') could not be completed: the "
                f"call itself failed ({exc}). A wrong credential comes back "
                f"as 'Authentication failed.' inside the Server Response, "
                f"so a raised error here is a transport / reachability "
                f"problem rather than an AvaTax setup defect. Steps 1-2 "
                f"and 4-8 are unaffected.")
        residual.append(
            f"workbook step 3 — Test connection could not be reached from "
            f"the runner ({exc}); confirm 'Authentication success.' by "
            f"hand in the settings screen.")
        evidence.append(("connection", "test_connection",
                         f"NOT EVALUATED: call failed ({exc})"))
    finally:
        if settings_id:
            try:
                rpc.unlink("res.config.settings", [settings_id])
            except OdooRPCError as exc:
                ctx.log(f"transient res.config.settings #{settings_id} not "
                        f"removed ({exc}) — TransientModel rows are "
                        f"vacuumed automatically; no setting was written")


@test_case(
    id="TEST-FG05-DAT-017",
    name="AvaTax setup is complete and correct after the upgrade",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P0",
    kind="DATA",
    order=500,
    description="Read-only FG-05 setup gate: Use AvaTax on and the seven "
                "AvaTax settings readable, Test connection authenticates, "
                "every AvaTax fiscal position carries both Avatax "
                "accounts, AvaTax product categories and customer "
                "exemptions survived the upgrade. Creates nothing.",
    traceability=trace("TC-DAT-017"))
def test_dat_017(ctx):
    rpc = ctx.adapter.rpc
    evidence = []   # (section, key, value) rows -> CSV artifact
    residual = []   # comparisons only the Novobi printout can settle

    with ctx.step("Precondition (workbook): Odoo 19 with account_avatax "
                  "installed and a company country that shows the AvaTax "
                  "settings block"):
        require_v19(ctx)
        config = company_avatax_config(ctx)
        company_row = rpc.read("res.company", [config["company_id"]],
                               ["partner_id", "country_id"])[0]
        country_id = _m2o(company_row["country_id"])
        country_code = ""
        if country_id:
            country_code = rpc.read("res.country", [country_id],
                                    ["code"])[0].get("code") or ""
        country_name = _m2o_name(company_row["country_id"]) or "no country"
        ctx.log(f"acting company #{config['company_id']} "
                f"{config['company_name']!r} — country {country_name} "
                f"({country_code or 'unset'})")
        evidence.append(("company", "name", config["company_name"] or ""))
        evidence.append(("company", "country_code", country_code))
        ctx.check_true(
            "Company country makes the AvaTax settings block visible "
            "(the block is hidden when country_code is not US or CA)",
            country_code in ("US", "CA"),
            actual_desc=f"res.company.country_id = {country_name} (code "
                        f"{country_code or 'unset'}); the workbook "
                        f"precondition names United States")

    try:
        with ctx.step("Workbook steps 1-2: Accounting > Configuration > "
                      "Settings > Taxes > AvaTax — 'Use AvaTax' ticked, "
                      "then the seven values on the block"):
            company_fields = _fields_present(rpc, "res.company",
                                             COMPANY_SETTING_FIELDS)
            ctx.check("AvaTax settings fields readable on res.company", [],
                      [f for f in COMPANY_SETTING_FIELDS
                       if f not in company_fields])

            # Expected Result line 1, first half.
            ctx.check("'Use AvaTax' is ticked "
                      "(res.company.setting_account_avatax)",
                      True, config["use_avatax"])

            ctx.log("v19 mapping for the workbook's 'Company Code': there "
                    "is NO res.company.avalara_company_code. The settings "
                    "label 'Company Code' is bound to "
                    "res.config.settings.avalara_partner_code, a related "
                    "field on company_id.partner_id.avalara_partner_code "
                    "— the value is stored on "
                    "res.partner.avalara_partner_code of the company's own "
                    "partner. An empty value is legal: Avalara reads it as "
                    "DEFAULT.")
            settings_has_code = "avalara_partner_code" in _fields_present(
                rpc, "res.config.settings", ["avalara_partner_code"])
            partner_has_code = "avalara_partner_code" in _fields_present(
                rpc, "res.partner", ["avalara_partner_code"])
            code_located = settings_has_code and partner_has_code
            company_code = ""
            if code_located:
                company_partner_id = _m2o(company_row["partner_id"])
                if company_partner_id:
                    company_code = rpc.read(
                        "res.partner", [company_partner_id],
                        ["avalara_partner_code"]
                    )[0].get("avalara_partner_code") or ""
                display_code = company_code or "(empty — Avalara: DEFAULT)"
            else:
                display_code = "(field not found on this database)"
                ctx.log(f"FINDING — the workbook's 'Company Code' could "
                        f"not be located: "
                        f"res.config.settings.avalara_partner_code "
                        f"present={settings_has_code}, "
                        f"res.partner.avalara_partner_code "
                        f"present={partner_has_code}. Recorded as an "
                        f"informational finding; no field name was "
                        f"invented to stand in for it.")

            captured = {
                "Environment": config["environment"] or "",
                # values NEVER recorded for these two — set / not set only
                "API ID": config["api_id"],
                "API KEY": config["api_key"],
                "Company Code": display_code,
                "Use UPC": config["use_upc"],
                "Commit Transactions": config["commit"],
                "Address Validation": config["address_validation"],
            }
            for label in SETTINGS_ORDER:
                ctx.log(f"AvaTax setting — {label}: {captured[label]!r}")
                evidence.append(("settings", label, str(captured[label])))

            creds = config["credential_fields_readable"]
            readable = (
                ("Environment", "avalara_environment" in company_fields),
                ("API ID", creds),
                ("API KEY", creds),
                ("Company Code", code_located),
                ("Use UPC", "avalara_use_upc" in company_fields),
                ("Commit Transactions",
                 "avalara_commit" in company_fields),
                ("Address Validation",
                 "avalara_address_validation" in company_fields),
            )
            # Expected Result line 1, second half. The values themselves
            # are ticked off against the printout by the tester; what the
            # platform proves is that all seven are present and readable,
            # and it logs each one above for that comparison.
            ctx.check("All seven values of workbook step 2 are readable "
                      "on this database", [],
                      [label for label, ok in readable if not ok])

            ctx.check_true(
                "Avalara Environment is one of the two AvaTax environments",
                config["environment"] in ("sandbox", "production"),
                actual_desc=f"res.company.avalara_environment = "
                            f"{config['environment'] or 'empty'!r}")
            if config["environment"] == "production":
                ctx.log("FINDING — this company points at the PRODUCTION "
                        "Avalara environment. No FG-05 case may compute "
                        "tax against it (Read Me, safety rule 1); the "
                        "Test connection step below is skipped too.")
            ctx.check_true(
                "Avalara API ID is set (value never recorded)",
                config["api_id"] == "set",
                actual_desc=f"res.company.avalara_api_id reads "
                            f"{config['api_id']!r}; credential fields "
                            f"readable by the runner user "
                            f"(base.group_system): {creds}")
            ctx.check_true(
                "Avalara API KEY is set (value never recorded)",
                config["api_key"] == "set",
                actual_desc=f"res.company.avalara_api_key reads "
                            f"{config['api_key']!r}; credential fields "
                            f"readable by the runner user "
                            f"(base.group_system): {creds}")
            residual.append(
                "workbook step 2 — tick Environment, Company Code, Use "
                "UPC, Commit Transactions and Address Validation (logged "
                "above) off against the Novobi printout. API ID / API KEY "
                "are captured as set/not set only and must be compared by "
                "someone holding the printout.")

        with ctx.step("Workbook step 3: click 'Test connection' and read "
                      "the Server Response box "
                      "(res.config.settings.avatax_ping)"):
            _check_connection(ctx, rpc, config, evidence, residual)

        with ctx.step("Workbook steps 4-6: every fiscal position with "
                      "'Use AvaTax API' ticked, its Avatax Invoice / "
                      "Refund Account, and those accounts in the Chart "
                      "of Accounts"):
            fp_fields = _fields_present(rpc, "account.fiscal.position",
                                        FISCAL_POSITION_FIELDS)
            ctx.check("AvaTax fields present on account.fiscal.position",
                      [], [f for f in FISCAL_POSITION_FIELDS
                           if f not in fp_fields])

            positions = rpc.search_read(
                "account.fiscal.position", [("is_avatax", "=", True)],
                ["name", "company_id", "avatax_invoice_account_id",
                 "avatax_refund_account_id"], order="id")

            account_ids = sorted({
                aid
                for fp in positions
                for aid in (_m2o(fp["avatax_invoice_account_id"]),
                            _m2o(fp["avatax_refund_account_id"]))
                if aid})
            accounts = {}
            if account_ids:
                try:
                    for row in rpc.read("account.account", account_ids,
                                        ["code", "name"]):
                        accounts[row["id"]] = (row.get("code") or "",
                                               row.get("name") or "")
                except OdooRPCError as exc:
                    ctx.log(f"FINDING — reading the Avatax accounts "
                            f"referenced by the fiscal positions failed "
                            f"({exc}); they are reported as unresolved "
                            f"below (workbook step 6).")

            for fp in positions:
                inv = fp["avatax_invoice_account_id"]
                ref = fp["avatax_refund_account_id"]
                inv_code = accounts.get(_m2o(inv), ("", ""))[0] or "MISSING"
                ref_code = accounts.get(_m2o(ref), ("", ""))[0] or "MISSING"
                fp_name = fp["name"] or f"#{fp['id']}"
                company = _m2o_name(fp["company_id"]) or "all companies"
                ctx.log(f"AvaTax fiscal position #{fp['id']} {fp_name!r} "
                        f"[{company}] — Avatax Invoice Account {inv_code} "
                        f"({_m2o_name(inv) or 'not set'}) / Avatax Refund "
                        f"Account {ref_code} "
                        f"({_m2o_name(ref) or 'not set'})")
                evidence.append(("fiscal_position",
                                 f"{fp_name} [{company}]",
                                 f"invoice_account={inv_code} "
                                 f"refund_account={ref_code}"))

            # Expected Result line 3.
            ctx.check_true(
                "At least one fiscal position has 'Use AvaTax API' ticked",
                bool(positions),
                actual_desc=f"{len(positions)} account.fiscal.position "
                            f"record(s) with is_avatax=True")
            ctx.check(
                "Every AvaTax fiscal position has an Avatax Invoice "
                "Account", [],
                sorted(fp["name"] or f"#{fp['id']}" for fp in positions
                       if not _m2o(fp["avatax_invoice_account_id"])))
            ctx.check(
                "Every AvaTax fiscal position has an Avatax Refund "
                "Account", [],
                sorted(fp["name"] or f"#{fp['id']}" for fp in positions
                       if not _m2o(fp["avatax_refund_account_id"])))
            ctx.check(
                "Every Avatax account referenced by those fiscal "
                "positions exists in the Chart of Accounts (step 6)", [],
                [aid for aid in account_ids if aid not in accounts])
            ctx.check(
                "Every Avatax account referenced by those fiscal "
                "positions has a non-empty code", [],
                sorted(f"#{aid} {accounts[aid][1]}" for aid in accounts
                       if not accounts[aid][0]))
            residual.append(
                "workbook steps 4-5 — tick each AvaTax fiscal position "
                "name and its two account codes (logged above) off "
                "against the Novobi printout; a code that differs "
                "silently posts tax to the wrong account.")

        with ctx.step("Workbook step 7: Avatax Category on the product "
                      "categories reached through a product's Internal "
                      "Category"):
            ctx.check_true(
                "Model product.avatax.category exists (the v19 AvaTax "
                "category master)",
                rpc.model_exists("product.avatax.category"),
                actual_desc="ir.model lookup for 'product.avatax.category'")
            categ_fields = _fields_present(rpc, "product.category",
                                           ["avatax_category_id"])
            ctx.check("product.category.avatax_category_id present", [],
                      [f for f in ("avatax_category_id",)
                       if f not in categ_fields])

            categories = rpc.search_read(
                "product.category", [("avatax_category_id", "!=", False)],
                ["name", "complete_name", "avatax_category_id"],
                order="id", limit=CSV_LIMIT)
            try:
                categ_total = rpc.call(
                    "product.category", "search_count",
                    [("avatax_category_id", "!=", False)])
            except OdooRPCError:
                categ_total = len(categories)

            categ_ids = sorted({_m2o(c["avatax_category_id"])
                                for c in categories
                                if _m2o(c["avatax_category_id"])})
            avatax_categs = {}
            if categ_ids:
                try:
                    for row in rpc.read("product.avatax.category",
                                        categ_ids,
                                        ["code", "description"]):
                        avatax_categs[row["id"]] = (
                            row.get("code") or "",
                            row.get("description") or "")
                except OdooRPCError as exc:
                    ctx.log(f"FINDING — reading the referenced "
                            f"product.avatax.category records failed "
                            f"({exc}); reported as unresolved below.")

            ctx.log(f"product categories carrying an Avatax Category: "
                    f"{categ_total} (logging up to {SAMPLE}; up to "
                    f"{CSV_LIMIT} in the attached CSV)")
            for index, categ in enumerate(categories):
                code, desc = avatax_categs.get(
                    _m2o(categ["avatax_category_id"]), ("MISSING", ""))
                name = (categ.get("complete_name") or categ["name"]
                        or f"#{categ['id']}")
                if index < SAMPLE:
                    ctx.log(f"product category #{categ['id']} {name!r} — "
                            f"Avatax Category {code} ({desc})")
                evidence.append(("product_category", name,
                                 f"avatax_category={code} ({desc})"))

            # A product- or template-level AvaTax category overrides the
            # category's (product.product._get_avatax_category_id ->
            # product.template -> product.category), so a printout that
            # lists categories only would not show it. Informational.
            for model in ("product.template", "product.product"):
                try:
                    count = rpc.call(
                        model, "search_count",
                        [("avatax_category_id", "!=", False)])
                    ctx.log(f"informational — {count} {model} record(s) "
                            f"carry their own avatax_category_id, which "
                            f"overrides the product category's value")
                    evidence.append(("avatax_category_override", model,
                                     str(count)))
                except OdooRPCError as exc:
                    ctx.log(f"informational — could not count "
                            f"{model}.avatax_category_id ({exc})")

            # Expected Result line 4.
            ctx.check_true(
                "At least one product category still carries an Avatax "
                "Category", bool(categories),
                actual_desc=f"{categ_total} product.category record(s) "
                            f"with avatax_category_id set")
            ctx.check(
                "Every product.avatax.category referenced by a product "
                "category still exists", [],
                [cid for cid in categ_ids if cid not in avatax_categs])
            ctx.check(
                "Every product.avatax.category referenced by a product "
                "category has a non-empty code", [],
                sorted(f"#{cid} {avatax_categs[cid][1]}"
                       for cid in avatax_categs
                       if not avatax_categs[cid][0]))
            residual.append(
                "workbook step 7 — tick each product category and its "
                "Avatax Category code (logged above) off against the "
                "Novobi printout.")

        with ctx.step("Workbook step 8: the tax-exempt customer's Avalara "
                      "Code, Avalara Partner Code and Avalara Exemption "
                      "(Sales & Purchase tab, Sales group)"):
            ctx.check_true(
                "Model avatax.exemption exists (the v19 exemption master)",
                rpc.model_exists("avatax.exemption"),
                actual_desc="ir.model lookup for 'avatax.exemption'")
            partner_fields = _fields_present(rpc, "res.partner",
                                             PARTNER_AVATAX_FIELDS)
            ctx.check("AvaTax partner fields present on res.partner", [],
                      [f for f in PARTNER_AVATAX_FIELDS
                       if f not in partner_fields])
            ctx.log(f"note — res.partner.avalara_exemption_id is "
                    f"company_dependent, so every value below is the "
                    f"exemption seen by the ACTING company "
                    f"(#{config['company_id']} "
                    f"{config['company_name']!r}); another company can "
                    f"legitimately read a different one.")

            partners = None
            partner_total = 0
            partner_with_code_total = 0
            try:
                # Evidence window: capped, feeds the log and the CSV only.
                partners = rpc.search_read(
                    "res.partner",
                    [("avalara_exemption_id", "!=", False)],
                    ["name", "avalara_exemption_id",
                     "avalara_partner_code", "avatax_unique_code"],
                    order="id", limit=CSV_LIMIT)
                # Assertion population: the FULL set, never the window. The
                # two Expected Result line 5 assertions below are scoped
                # counts over the whole database, so a qualifying exempt
                # customer sitting past row CSV_LIMIT cannot make this P0
                # GATE-3 case report FAILED.
                partner_total = rpc.call(
                    "res.partner", "search_count",
                    [("avalara_exemption_id", "!=", False)])
                partner_with_code_total = rpc.call(
                    "res.partner", "search_count",
                    ['&', ("avalara_exemption_id", "!=", False),
                     ("avalara_partner_code", "!=", False)])
            except OdooRPCError as exc:
                partners = None
                ctx.log(f"NOT EVALUATED — workbook step 8 (the exempt "
                        f"customer still carries the same Avalara "
                        f"Exemption and Avalara Partner Code): listing "
                        f"the exempt customers failed ({exc}). "
                        f"avalara_exemption_id is company_dependent and "
                        f"stored in a JSONB column in v19; a search "
                        f"failure is an ORM/environment condition, not an "
                        f"AvaTax setup defect, so it is recorded rather "
                        f"than asserted.")
                residual.append(
                    f"workbook step 8 — the exempt customers could not be "
                    f"listed from the runner ({exc}); open one exempt "
                    f"customer from the Novobi printout by hand and read "
                    f"Avalara Code, Avalara Partner Code and Avalara "
                    f"Exemption.")
                evidence.append(("exempt_customer", "listing",
                                 f"NOT EVALUATED: search failed ({exc})"))

            if partners is not None:
                exemption_ids = sorted({_m2o(p["avalara_exemption_id"])
                                        for p in partners
                                        if _m2o(p["avalara_exemption_id"])})
                exemptions = {}
                if exemption_ids:
                    try:
                        for row in rpc.read("avatax.exemption",
                                            exemption_ids,
                                            ["code", "name"]):
                            exemptions[row["id"]] = (row.get("code") or "",
                                                     row.get("name") or "")
                    except OdooRPCError as exc:
                        ctx.log(f"FINDING — reading the referenced "
                                f"avatax.exemption records failed "
                                f"({exc}); reported as unresolved below.")

                ctx.log(f"customers carrying an Avalara Exemption: "
                        f"{partner_total} (logging up to {SAMPLE}; up to "
                        f"{CSV_LIMIT} in the attached CSV)")
                for index, partner in enumerate(partners):
                    code, label = exemptions.get(
                        _m2o(partner["avalara_exemption_id"]),
                        ("MISSING", ""))
                    name = partner["name"] or f"#{partner['id']}"
                    partner_code = partner.get("avalara_partner_code") or ""
                    if index < SAMPLE:
                        unique = (partner.get("avatax_unique_code")
                                  or "(empty)")
                        ctx.log(f"exempt customer #{partner['id']} "
                                f"{name!r} — Avalara Exemption {code} "
                                f"({label}), Avalara Partner Code "
                                f"{partner_code or '(empty)'}, Avalara "
                                f"Code {unique}")
                    evidence.append(("exempt_customer", name,
                                     f"exemption={code} ({label}) "
                                     f"partner_code={partner_code}"))

                no_code = [p["name"] or f"#{p['id']}" for p in partners
                           if not p.get("avalara_partner_code")]
                if no_code:
                    ctx.log(f"informational — {len(no_code)} of the "
                            f"{len(partners)} exempt customer(s) in the "
                            f"capped evidence window (of {partner_total} "
                            f"in total) have an empty Avalara Partner Code "
                            f"(legal: Avalara falls back to the partner "
                            f"id). This listing is evidence only — the two "
                            f"assertions below count the FULL population. "
                            f"Check whether the printout's customer is one "
                            f"of them: {sorted(no_code)[:SAMPLE]}")

                # Expected Result line 5. Both assertions are stated over
                # the full population (search_count), not over the
                # CSV_LIMIT evidence window read above.
                ctx.check_true(
                    "At least one customer still carries an Avalara "
                    "Exemption", partner_total > 0,
                    actual_desc=f"{partner_total} res.partner record(s) "
                                f"with avalara_exemption_id set for "
                                f"company #{config['company_id']} "
                                f"(full population via search_count; the "
                                f"capped evidence window listed "
                                f"{len(partners)})")
                ctx.check_true(
                    "At least one exempt customer carries BOTH an Avalara "
                    "Exemption and an Avalara Partner Code (the "
                    "workbook's exempt customer)",
                    partner_with_code_total > 0,
                    actual_desc=f"{partner_with_code_total} of "
                                f"{partner_total} exempt customer(s) also "
                                f"carry an avalara_partner_code (full "
                                f"population via search_count; the capped "
                                f"evidence window listed {len(partners)}, "
                                f"{len(partners) - len(no_code)} of which "
                                f"carry one)")
                ctx.check(
                    "Every avatax.exemption referenced by a customer "
                    "still exists", [],
                    [eid for eid in exemption_ids
                     if eid not in exemptions])
                ctx.check(
                    "Every avatax.exemption referenced by a customer has "
                    "a non-empty code", [],
                    sorted(f"#{eid} {exemptions[eid][1]}"
                           for eid in exemptions
                           if not exemptions[eid][0]))
                residual.append(
                    "workbook step 8 — tick the exempt customer's Avalara "
                    "Exemption and Avalara Partner Code (logged above) "
                    "off against the Novobi printout.")
    finally:
        with ctx.step("Evidence: the captured AvaTax inventory the tester "
                      "ticks off against the Novobi printout"):
            path = ctx.artifacts_dir / INVENTORY_CSV
            try:
                with open(path, "w", newline="",
                          encoding="utf-8") as handle:
                    writer = csv.writer(handle)
                    writer.writerow(["section", "key", "value"])
                    writer.writerows(evidence)
                ctx.add_artifact(path, "log",
                                 "AvaTax setup inventory — compare "
                                 "against the Novobi printout")
                ctx.log(f"wrote {len(evidence)} inventory row(s) to "
                        f"{path.name}")
            except OSError as exc:
                ctx.log(f"could not write the inventory CSV ({exc}); the "
                        f"full inventory is still in the log above")
            for note in residual:
                ctx.log(f"RESIDUAL MANUAL STEP — {note}")
            ctx.log("State After The Test (workbook): nothing changed. "
                    "This case created no business record, wrote no field "
                    "and deleted nothing; the only row it made was one "
                    "transient res.config.settings needed to call "
                    "avatax_ping(), and execute() was never called.")
