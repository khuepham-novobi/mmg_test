"""FG-07 — TC-INV-010: the gallery's online payment providers are still configured.

Implements row 38.0 (P1, "Payment providers") of the CLIENT MANUAL TESTING
GUIDELINE ``MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0.xlsx`` /
sheet ``Testing Guideline``.

The workbook's framing: *"Customers pay by card and PayPal. If a provider lost
its configuration in the upgrade, online payments stop and nothing says so
until a customer tries."*

Read-only by construction
-------------------------
The workbook's *State After The Test* is "Nothing changed. Do not enable or
disable anything.", and its *If It Fails* column is emphatic: *"Do NOT change
a provider's state yourself — switching a provider live with half-migrated
credentials can take real customer payments into a broken configuration."*
This module therefore creates no record, writes no field, calls neither
``sweep_fg07`` nor ``cleanup`` (a sweep is itself a delete), and never calls
``write`` on ``payment.provider``.

It also never transports a credential VALUE. "Is this key filled in?" is
answered with ``search([('id','=',pid), ('<field>','!=',False)])`` — a domain
that makes the database answer the boolean question — so no secret is ever
read into this process, into the log, or into an artifact. Odoo's own domain
handling turns ``!= False`` on a Char into "not NULL and not the empty
string", which is exactly the workbook's "you are checking they are not
empty".

The 3 Expected Result lines, and what each is read from
-------------------------------------------------------
1. **"Every provider on the baseline is present, allowing for the
   transfer-to-Custom rename."** — read from
   ``fields_get('payment.provider', ['code'], attributes=['selection'])`` and
   from ``ir.model.data``. The rename is a *machine-checkable* fact, not a
   judgement call: the v15 selection value ``'transfer'`` was deleted and
   ``'custom'`` added by
   ``addons/payment_custom/models/payment_provider.py:17-18``
   (``selection_add=[('custom', "Custom")]``), and the provider RECORD kept
   its identity — ``addons/payment_custom/data/payment_provider_data.xml:4-15``
   writes ``code=custom`` / ``custom_mode=wire_transfer`` onto the very
   xmlid ``payment.payment_provider_transfer`` that
   ``addons/payment/data/payment_provider_data.xml:500-505`` creates. The v15
   xmlid was ``payment.payment_acquirer_transfer``
   (``D:/Projects/odoo15/addons/payment/data/payment_acquirer_data.xml:354``)
   on the model ``payment.acquirer``, which no longer exists.
   *Which* providers the baseline lists is not knowable here, so the full
   inventory is captured to ``TC-INV-010-providers.csv`` and the tick-off is a
   RESIDUAL MANUAL STEP.
2. **"Each live provider's state matches the baseline and its credential
   fields are populated."** — the second half is asserted for real, per
   provider code, against the credential field names read from v19 source:
   ``stripe_publishable_key`` / ``stripe_secret_key`` /
   ``stripe_webhook_secret``
   (``addons/payment_stripe/models/payment_provider.py:27,33,39``);
   ``authorize_login`` / ``authorize_transaction_key`` /
   ``authorize_signature_key`` / ``authorize_client_key``
   (``addons/payment_authorize/models/payment_provider.py:23,29,35,41``);
   ``paypal_email_account`` / ``paypal_client_id`` / ``paypal_client_secret``
   / ``paypal_webhook_id``
   (``addons/payment_paypal/models/payment_provider.py:24,31,36,54``). The
   first half ("matches the baseline") needs the baseline and is a RESIDUAL
   MANUAL STEP with every observed raw state printed into it.
3. **"No provider that should be live is sitting in Test or Disabled."** —
   *which* providers should be live needs the baseline, so the observed
   states are printed for the human. Three things line 3 implies are asserted
   here without any baseline:
   * at least one provider is in raw state ``'enabled'`` — the workbook's own
     Business Purpose says the gallery takes card and PayPal payments, so a
     database where every provider is Disabled means online payments are off
     for everyone and the case must not pass vacuously;
   * no provider is ``is_published=True`` while ``state='disabled'`` — Odoo
     itself refuses to produce that combination
     (``addons/payment/models/payment_provider.py:537-539`` raises
     ``UserError("You cannot publish a disabled provider.")``, and
     ``:272-278`` unpublishes on every state change), so a row in that state
     is upgrade damage: the website still offers a payment button that cannot
     take money;
   * no live provider has ``code == 'none'``. ``code`` defaults to ``'none'``
     (``addons/payment/models/payment_provider.py:34-40``) and is only set to
     a real value by the provider module's OWN data file (e.g.
     ``addons/payment_paypal/data/payment_provider_data.xml:5``), so
     ``code='none'`` on a live provider means the implementing module is not
     installed and the provider cannot process a payment even though the
     screen shows it as Enabled. This is precisely the workbook's "nothing
     says so until a customer tries".

Why this case probes ``ir.module.module`` and ``has_access``, not
``check_access``
----------------------------------------------------------------
``payment.provider`` is granted to **``base.group_system`` only** —
``addons/payment/security/ir.model.access.csv:4``
(``payment_provider_system,...,base.group_system,1,1,1,1``); there is no
``base.group_user`` line at all. The workbook's precondition, "You have the
Administrator accounting group", is therefore **not sufficient**: an
accounting manager who is not a Settings user cannot open this screen. That
gets its own BLOCK reason rather than a confusing AccessError.

The obvious probe, ``check_access('read')``, **cannot be used**: in Odoo 19 it
carries ``@api.private`` (``odoo/orm/models.py:4099``, decorating
``def check_access`` at ``:4100`` with the comment ``# use has_access``), and
``odoo/service/model.py`` refuses a private method before it is looked up. The
public sibling ``has_access(operation)`` (``odoo/orm/models.py:4116``) is used
instead, and the real ``search_read`` that follows is still wrapped in
``try/except OdooRPCError`` so a refusal becomes a BLOCK verdict rather than
an AUTOMATION_ERROR.

The reads are pinned to one company. ``payment.provider`` carries a global
record rule ``[('company_id','parent_of', company_ids)]``
(``addons/payment/security/payment_security.xml:6-10``, no ``groups``, so it
applies to everyone), which means an unpinned read silently changes which
providers are in the list.

Findings this case will surface
-------------------------------
* **OBSERVATION, asserted in neither direction — the provider is renamed but
  not relabelled.** Workbook step 5 tells the tester "look for a provider
  called Custom before concluding it is gone". They will not see that word in
  the list. Only the *code* became ``custom``; the record's ``name`` is still
  the literal string ``"Wire Transfer"``
  (``addons/payment/data/payment_provider_data.xml:501``), and ``name`` is a
  user-editable translatable Char
  (``addons/payment/models/payment_provider.py:32``), so it is reported as
  observed and never asserted.
* **FINDING, not a silent pass — empty PayPal REST credentials.** v15's
  PayPal integration had ``paypal_email_account``, ``paypal_seller_account``,
  ``paypal_pdt_token`` and ``paypal_use_ipn``
  (``D:/Projects/odoo15/addons/payment_paypal/models/payment_acquirer.py:
  17-24``); ``paypal_client_id``, ``paypal_client_secret`` and
  ``paypal_webhook_id`` **did not exist**, so an upgrade cannot have carried
  them and they must be re-entered from the PayPal developer dashboard.
  **Deliberate divergence from the implementation brief, recorded here so it
  is reviewable:** the brief called this a soft WARN rather than a failure.
  It is left as a real offender in the Expected-line-2 assertion, because the
  workbook says without qualification that a live provider's credential
  fields are populated, and an empty ``paypal_client_id`` on an *enabled*
  PayPal provider means checkout is broken today whatever its cause. Each
  such offender is logged with the v15 field list and the "re-enter from the
  dashboard" remedy attached, so the failure is triaged as a configuration
  task and not as a product defect.
* **FINDING — the module name changed too.** This test is registered against
  the workbook's module column ``payment_transfer``. That module does not
  exist in Odoo 19; it is ``payment_custom``
  (``addons/payment_custom/__manifest__.py:4``, "Payment Provider: Custom
  Payment Modes"), and unlike v15 it is **not** ``auto_install``, so an
  upgrade does not necessarily bring it along. Both names are probed and both
  states reported.
"""
from __future__ import annotations

import csv

from adapters.base import OdooRPCError
from framework.registry import test_case
from tests.fg07.common import (PROVIDER_CREDENTIAL_FIELDS,
                               PROVIDER_CUSTOM_CODE,
                               PROVIDER_CUSTOM_MODE_WIRE,
                               PROVIDER_LEGACY_CODE, WORKFLOW, WORKFLOW_NAME,
                               acting_company, company_ctx, fields_present,
                               finding, has_group, m2o_name, menu_by_xmlid,
                               module_state, observation, require_v19,
                               residual_manual_step, selection_labels, trace)

PROVIDERS_CSV = "TC-INV-010-providers.csv"
CREDENTIALS_CSV = "TC-INV-010-credentials.csv"

# The screen the workbook's step 1 opens:
# "Accounting > Configuration > Online Payments > Payment Providers".
# The leaf is account_payment.payment_provider_menu
# (addons/account_payment/views/account_payment_menus.xml:4-7) hanging under
# account.root_payment_menu, whose label IS "Online Payments" and which is
# gated on account.group_account_manager
# (addons/account/views/account_menuitem.xml:64).
PROVIDER_MENU_XMLID = "account_payment.payment_provider_menu"
PROVIDER_MENU_PATH = ("Accounting > Configuration > Online Payments > "
                      "Payment Providers")
ACCOUNTING_MANAGER_GROUP = "account.group_account_manager"

# The wire-transfer provider, before and after. The v19 record keeps the v15
# record's *xmlid stem* but on the new model; the v15 xmlid names the old
# payment.acquirer model and must NOT resolve on a v19 database.
TRANSFER_XMLID_V19 = "payment.payment_provider_transfer"
TRANSFER_XMLID_V15 = "payment.payment_acquirer_transfer"

# v15 module name -> v19 module name. Reported, never treated as "missing".
MODULE_RENAMED_IN_V19 = {"payment_transfer": "payment_custom"}
# Every module this case reports a state for: the engine, the menu's home,
# and the three provider implementations the workbook names.
MODULES_OF_INTEREST = ("payment", "account_payment", "payment_custom",
                       "payment_transfer", "payment_paypal",
                       "payment_authorize", "payment_stripe")

# Raw payment.provider.state values
# (addons/payment/models/payment_provider.py:41-46). Every comparison in this
# file is made on these; the LABELS ("Test Mode" vs "Test") are only ever
# printed, because comparing labels reports a translation as a defect.
STATE_LIVE = "enabled"
STATE_TEST = "test"
STATE_DISABLED = "disabled"

# code='none' is the default a provider row keeps until its own module's data
# file overwrites it (addons/payment/models/payment_provider.py:34-40 vs
# addons/payment_paypal/data/payment_provider_data.xml:5).
CODE_UNIMPLEMENTED = "none"

# The two providers the workbook's step 4 singles out ("the gallery's card
# provider and PayPal"), by the module column this case is registered against.
SPOTLIGHT_CODES = ("authorize", "paypal")

# PayPal credentials that DID NOT EXIST in v15 — an upgrade cannot have
# carried them (D:/Projects/odoo15/addons/payment_paypal/models/
# payment_acquirer.py:17-24 has only paypal_email_account,
# paypal_seller_account, paypal_pdt_token, paypal_use_ipn).
PAYPAL_FIELDS_NEW_IN_V19 = ("paypal_client_id", "paypal_client_secret",
                            "paypal_webhook_id")
PAYPAL_V15_FIELDS = ("paypal_email_account", "paypal_seller_account",
                     "paypal_pdt_token", "paypal_use_ipn")

# The wire-transfer provider has no API credential; its equivalent "did the
# configuration survive" field is the HTML instruction block customers are
# shown telling them which bank account to wire to
# (addons/payment/models/payment_provider.py:140;
# addons/payment_custom/models/payment_provider.py:45-60 rebuilds it). It is
# reported and, when empty on a live provider, raised as a FINDING — but it
# is deliberately NOT an offender in the Expected-line-2 credential
# assertion, because the workbook says "credential fields" and this is an
# instruction message, not a credential.
WIRE_TRANSFER_INSTRUCTION_FIELD = "pending_msg"

# Status vocabulary for a credential. "not readable" must never be conflated
# with "not set": the first is a fact about this session's groups, the second
# is a fact about the gallery's configuration, and only the second is a
# defect.
CRED_SET = "set"
CRED_EMPTY = "not set"
CRED_UNREADABLE = "not readable by this session"

NOT_ODOO_19 = (
    "This database does not expose the model 'payment.provider'. Odoo renamed "
    "'payment.acquirer' to 'payment.provider' in v17 and the workbook "
    "describes the v19 screen, so a database that still answers to "
    "payment.acquirer is not the upgrade target and every expectation in this "
    "case would report a version difference as a lost provider. Point the "
    "runner at the odoo19 environment (ODOO19_URL / ODOO19_DB in "
    "config/local.yaml)"
)

NO_PAYMENT_ENGINE = (
    "The 'payment' module is not installed on this database, so no "
    "payment.provider row exists at all and the Payment Providers screen the "
    "workbook opens does not exist. 'payment' is a dependency of "
    "'account_payment', which itself auto-installs alongside 'account' "
    "(addons/account_payment/__manifest__.py:8-9), so its absence means the "
    "accounting application itself did not come across — a far larger problem "
    "than a mis-configured provider, and the thing to fix first"
)

NOT_SETTINGS_USER = (
    "This session cannot read payment.provider. The model is granted to "
    "base.group_system ONLY — addons/payment/security/ir.model.access.csv:4 "
    "is the single ACL line for it ('payment_provider_system', "
    "base.group_system, read/write/create/unlink) and there is no "
    "base.group_user line. The workbook's precondition, 'You have the "
    "Administrator accounting group', is NOT enough in Odoo 19: "
    "account.group_account_manager opens the Online Payments MENU "
    "(addons/account/views/account_menuitem.xml:64) but not the records "
    "behind it. Give the runner user Settings / Administration access, or run "
    "this case as a user who has it, and re-run. This is a fact about the "
    "runner's credentials, not about the gallery's providers — do NOT report "
    "it as a lost provider"
)

NO_PROVIDER_MENU = (
    "The Payment Providers menu (" + PROVIDER_MENU_XMLID + ") does not "
    "resolve on this database, so the workbook's step 1 navigation "
    "'" + PROVIDER_MENU_PATH + "' has no destination. The menu is created by "
    "'account_payment' (addons/account_payment/views/"
    "account_payment_menus.xml:4-7), which auto-installs with 'account' — so "
    "either account_payment is missing or its views did not load. Until the "
    "menu is back, the gallery's accountant has no way to see provider "
    "configuration at all, which is itself the reportable finding"
)


NO_XMLID_ACCESS = (
    "This session cannot resolve XML ids. ir.model.data grants read to "
    "base.group_erp_manager only — base.group_user's line is 0,0,0,0 "
    "(odoo/addons/base/security/ir.model.access.csv:15,19). Every 'is this "
    "record still there?' question in this case is answered through an xmlid, "
    "and a refusal must NOT be reported as a deleted provider, so the case "
    "blocks instead. base.group_system implies base.group_erp_manager, so a "
    "runner user with Settings access — which this model needs anyway — "
    "resolves them fine; give the runner user Settings / Administration "
    "access and re-run"
)


def _ref(ctx, xmlid: str):
    """``rpc.ref``, where a refusal BLOCKS instead of reading as ``None``.

    Silently swallowing an AccessError here would turn "the runner may not
    read ir.model.data" into "the gallery's wire-transfer provider is gone" —
    the single most damaging misreport this case could make.
    """
    try:
        return ctx.adapter.rpc.ref(xmlid)
    except OdooRPCError as exc:
        ctx.blocked(f"{NO_XMLID_ACCESS} (resolving {xmlid!r} failed: {exc})")


def _label(row: dict) -> str:
    """How a provider is named in an offender list: the way it reads on
    screen, plus the technical code, because two rows can share a name."""
    return f"{row.get('name') or '(unnamed)'} [code={row.get('code') or ''}]"


def _credential_is_set(rpc, provider_id: int, field: str, context: dict) -> str:
    """``set`` / ``not set`` / ``not readable`` for one credential field.

    The question is answered by a DOMAIN, never by reading the value: Odoo
    turns ``('<char field>', '!=', False)`` into "IS NOT NULL AND != ''", so
    the database returns the id when the key is filled in and nothing when it
    is not. No secret crosses the wire, reaches this process, or can leak into
    the log or the CSV.
    """
    try:
        hit = rpc.search("payment.provider",
                         [("id", "=", provider_id), (field, "!=", False)],
                         limit=1, context=context)
    except OdooRPCError:
        # A field carrying groups='base.group_system' (paypal_client_secret,
        # authorize_transaction_key, stripe_secret_key, …) raises rather than
        # returning an empty set when the session may not see it.
        return CRED_UNREADABLE
    return CRED_SET if hit else CRED_EMPTY


@test_case(
    id="TEST-FG07-INV-010",
    name="The gallery's online payment providers are still configured",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module="payment_authorize, payment_paypal, payment_transfer",
    priority="P1",
    kind="DATA",
    order=709,
    description="Read-only inventory of every payment.provider on the acting "
                "company: the v19 transfer-to-Custom rename proven from the "
                "code selection and the surviving xmlid, every live "
                "provider's credential fields proven populated without a "
                "value ever crossing the wire, no live provider left with an "
                "uninstalled implementation, and no disabled provider left "
                "published. Creates, writes and enables nothing; the Novobi "
                "baseline tick-off is a residual manual step.",
    traceability=trace("TC-INV-010"))
def test_inv_010(ctx):
    rpc = ctx.adapter.rpc
    # Accumulators live outside the try: the evidence block runs from
    # `finally` and must never raise a NameError over a step that an earlier
    # assertion failure skipped — that would replace a real FAILED verdict
    # with an AUTOMATION_ERROR.
    provider_rows: list[dict] = []
    credential_rows: list[tuple] = []
    residual: list[str] = []

    with ctx.step("Precondition (workbook): Odoo 19, the Administrator "
                  "accounting group, and a readable Payment Providers screen"):
        require_v19(ctx)
        company = acting_company(ctx)
        context = company_ctx(company)
        ctx.log(f"acting company #{company['id']} {company['name']!r} — every "
                f"read below is pinned to it, because payment.provider "
                f"carries the global record rule "
                f"[('company_id','parent_of',company_ids)] "
                f"(addons/payment/security/payment_security.xml:6-10)")

        # The model, not the module: an upgrade that stopped short leaves the
        # v15 payment.acquirer behind, and every assertion here would then
        # report a version difference as a lost provider.
        if not rpc.model_exists("payment.provider"):
            legacy = rpc.model_exists("payment.acquirer")
            ctx.blocked(f"{NOT_ODOO_19} (payment.acquirer present on this "
                        f"database: {legacy})")

        # ir.module.module, never model_exists, is the installed-probe.
        states = {name: module_state(rpc, name) for name in MODULES_OF_INTEREST}
        for name in MODULES_OF_INTEREST:
            renamed = MODULE_RENAMED_IN_V19.get(name)
            suffix = (f" (renamed {renamed!r} in Odoo 19 — its absence here is "
                      f"EXPECTED)" if renamed else "")
            ctx.log(f"module {name!r}: "
                    f"{states[name] or 'no such module row'}{suffix}")
        if states.get("payment") != "installed":
            ctx.blocked(f"{NO_PAYMENT_ENGINE} (ir.module.module state for "
                        f"'payment': "
                        f"{states.get('payment') or 'no such module row'})")

        # has_access, NOT check_access: check_access is @api.private in v19
        # (odoo/orm/models.py:4099) and the RPC layer refuses it outright.
        try:
            may_read = bool(rpc.call("payment.provider", "has_access", [],
                                     "read"))
        except OdooRPCError as exc:
            may_read = False
            ctx.log(f"payment.provider.has_access('read') could not be called "
                    f"({exc}) — falling back to the real read below")
        # Reported side by side because the workbook's precondition names the
        # wrong group: the accounting-manager group opens the MENU, and only
        # base.group_system opens the RECORDS behind it.
        ctx.log(f"this session may read payment.provider: {may_read}; "
                f"has_group({ACCOUNTING_MANAGER_GROUP}) = "
                f"{has_group(ctx, ACCOUNTING_MANAGER_GROUP)} — the workbook's "
                f"stated precondition, which "
                f"addons/payment/security/ir.model.access.csv:4 shows is not "
                f"sufficient on its own")

        try:
            menu = menu_by_xmlid(ctx, PROVIDER_MENU_XMLID)
        except OdooRPCError as exc:
            menu = {}
            ctx.blocked(f"{NO_XMLID_ACCESS} (resolving "
                        f"{PROVIDER_MENU_XMLID!r} failed: {exc})")
        if not menu:
            ctx.blocked(NO_PROVIDER_MENU)
        ctx.log(f"step 1 destination: {PROVIDER_MENU_PATH} -> ir.ui.menu "
                f"#{menu['id']} {menu['name']!r} under "
                f"{menu['parent_name']!r} (active={menu['active']})")

    try:
        with ctx.step("Step 1 / Expected line 1: read the Payment Providers "
                      "list the way the screen does"):
            wanted = ["name", "code", "custom_mode", "state", "is_published",
                      "sequence", "module_id", "module_state", "company_id"]
            readable = fields_present(rpc, "payment.provider", wanted)
            if not readable:
                # fields_get returned nothing at all: the model is invisible
                # to this session. Blocking here, with the ACL cited, is the
                # difference between "your runner lacks a group" and the
                # false alarm "the gallery lost its providers".
                ctx.blocked(NOT_SETTINGS_USER)
            fields = [name for name in wanted if name in readable]
            missing_fields = [name for name in wanted if name not in readable]
            if missing_fields:
                ctx.log(f"payment.provider fields not visible to this "
                        f"session: {missing_fields} — reported, not read")

            # There is no `active` field on payment.provider in Odoo 19
            # (addons/payment/models/payment_provider.py declares none), so
            # there is no archived subset to miss and no active_test to pass.
            try:
                rows = rpc.search_read("payment.provider", [], fields,
                                       order="sequence, name",
                                       context=context)
            except OdooRPCError as exc:
                # An AccessError here is the workbook precondition being
                # wrong, not a product defect — BLOCK, never fail.
                ctx.blocked(f"{NOT_SETTINGS_USER} — the read itself was "
                            f"refused: {exc}")

            state_names = selection_labels(rpc, "payment.provider", "state")
            code_names = selection_labels(rpc, "payment.provider", "code")
            for row in rows:
                record = {
                    "id": row["id"],
                    "name": row.get("name") or "",
                    "code": row.get("code") or "",
                    "code_label": code_names.get(row.get("code") or "", ""),
                    "custom_mode": row.get("custom_mode") or "",
                    "state": row.get("state") or "",
                    "state_label": state_names.get(row.get("state") or "", ""),
                    "is_published": bool(row.get("is_published")),
                    "module": m2o_name(row.get("module_id")),
                    "module_state": row.get("module_state") or "",
                    "company": m2o_name(row.get("company_id")),
                }
                provider_rows.append(record)
                ctx.log(f"  {record['name']!r} code={record['code']!r} "
                        f"({record['code_label']}) "
                        f"state={record['state']!r} "
                        f"({record['state_label']}) "
                        f"published={record['is_published']} "
                        f"module={record['module']!r}/"
                        f"{record['module_state'] or '(not installed)'} "
                        f"company={record['company']!r}")
            ctx.log(f"{len(provider_rows)} payment provider(s) visible on "
                    f"{company['name']!r}")

            # A list with nothing in it is not "all present": the workbook's
            # baseline necessarily names at least the card provider and
            # PayPal, so an empty screen is the total-loss case.
            ctx.check_true(
                "The Payment Providers list is not empty — the workbook's "
                "baseline names at least a card provider and PayPal",
                bool(provider_rows),
                actual_desc=f"{len(provider_rows)} provider row(s) readable on "
                            f"company {company['name']!r}")

        with ctx.step("Step 5 / Expected line 1: the transfer -> Custom "
                      "rename, proven rather than assumed"):
            # The rename is stated three ways, each independently checkable,
            # so a half-finished migration cannot slip through on one of them.
            ctx.log(f"payment.provider.code selection: "
                    f"{sorted(code_names) or '(empty)'}")

            legacy_in_selection = ([PROVIDER_LEGACY_CODE]
                                   if PROVIDER_LEGACY_CODE in code_names
                                   else [])
            custom_installed = module_state(rpc, "payment_custom") == "installed"

            transfer_id_v19 = _ref(ctx, TRANSFER_XMLID_V19)
            transfer_id_v15 = _ref(ctx, TRANSFER_XMLID_V15)
            ctx.log(f"{TRANSFER_XMLID_V19} -> {transfer_id_v19}; "
                    f"{TRANSFER_XMLID_V15} (the v15 payment.acquirer xmlid) "
                    f"-> {transfer_id_v15}")

            wire_rows = [row for row in provider_rows
                         if row["code"] == PROVIDER_CUSTOM_CODE
                         and row["custom_mode"] == PROVIDER_CUSTOM_MODE_WIRE]
            transfer_row = next((row for row in provider_rows
                                 if row["id"] == transfer_id_v19), None)

            # Workbook step 5's trap, recorded FIRST and asserted in NEITHER
            # direction: the tester is told to look for "Custom" and the list
            # will not contain that word. It is logged ahead of every
            # assertion in this step on purpose — ctx.check raises, and an
            # expected-difference note that only survives a passing run is no
            # note at all.
            observed_names = [row["name"] for row in wire_rows] or (
                [transfer_row["name"]] if transfer_row else [])
            observation(
                ctx,
                f"workbook step 5 says 'look for a provider called Custom "
                f"before concluding it is gone'. In Odoo 19 only the CODE "
                f"became 'custom' (whose label is \"Custom\") — the record's "
                f"NAME is unchanged and this database shows it as "
                f"{observed_names or ['(no wire-transfer row found)']}. "
                f"addons/payment/data/payment_provider_data.xml:501 still "
                f"writes the literal name 'Wire Transfer', and name is a "
                f"user-editable translatable Char "
                f"(addons/payment/models/payment_provider.py:32), so the "
                f"label is reported, never asserted. Tick the baseline's "
                f"'Wire Transfer' line off against THIS row.")

            if not custom_installed:
                # Reported BEFORE the assertions below, never instead of
                # them: an uninstalled payment_custom is the explanation for
                # the failure that is about to be raised, not a reason to
                # withhold it. The workbook's Expected line 1 says the
                # provider is present "allowing for the transfer-to-Custom
                # rename", and a row that has fallen back to code 'none'
                # cannot take a wire transfer whatever the screen shows.
                custom_state = (module_state(rpc, "payment_custom")
                                or "no such module row")
                finding(ctx, f"'payment_custom' is not installed (state: "
                             f"{custom_state}). In Odoo 19 the v15 "
                             f"module 'payment_transfer' was RENAMED "
                             f"'payment_custom' "
                             f"(addons/payment_custom/__manifest__.py:4) and, "
                             f"unlike v15, it is NOT auto_install — so an "
                             f"upgrade does not bring it along by itself. The "
                             f"wire-transfer provider ROW still exists but "
                             f"keeps code 'none' and cannot process anything. "
                             f"Install 'payment_custom' and re-run: the "
                             f"assertions below WILL fail until you do, and "
                             f"that failure is 'the wire-transfer option does "
                             f"not work', not 'the row was deleted'.")
                residual.append(
                    f"'payment_custom' is not installed on this database "
                    f"(state: {custom_state}), so the gallery's wire-transfer "
                    f"provider has fallen back to code 'none'. Install the "
                    f"module — it is the Odoo 19 name for v15's "
                    f"'payment_transfer' — and re-run this case before "
                    f"reporting anything about the Wire Transfer line of the "
                    f"Novobi baseline.")

            # Asserted unconditionally. The value is contributed by
            # payment_custom's selection_add, so on a database without that
            # module the selection has no 'custom' — which is exactly the
            # state in which the gallery's wire-transfer provider does not
            # work, and the workbook's Expected line 1 must fail.
            ctx.check_true(
                "payment.provider.code offers 'custom', the Odoo 19 name "
                "for the provider the gallery knew as Wire Transfer "
                "(selection_add=[('custom', \"Custom\")], "
                "addons/payment_custom/models/payment_provider.py:17-18)",
                PROVIDER_CUSTOM_CODE in code_names,
                actual_desc=f"code selection = {sorted(code_names)}"
                            f"; payment_custom installed = {custom_installed}")

            # This holds whatever is installed: 'transfer' was deleted from
            # the selection outright, and a database still offering it has a
            # half-migrated field definition.
            ctx.check(
                "The obsolete 'transfer' provider code is gone from "
                "payment.provider.code — Odoo 19 replaced it with 'custom' "
                "(addons/payment_custom/models/payment_provider.py:17-18); a "
                "surviving 'transfer' value means the selection was not "
                "migrated",
                [], legacy_in_selection)

            ctx.check_true(
                "The gallery's wire-transfer provider RECORD survived the "
                "rename under its Odoo 19 xmlid "
                f"{TRANSFER_XMLID_V19} "
                "(addons/payment/data/payment_provider_data.xml:500-505, "
                "re-pointed to code=custom by "
                "addons/payment_custom/data/payment_provider_data.xml:4-15)",
                bool(transfer_id_v19),
                actual_desc=f"ir.model.data lookup returned "
                            f"{transfer_id_v19!r}; the v15 xmlid "
                            f"{TRANSFER_XMLID_V15} returned "
                            f"{transfer_id_v15!r}")

            # Also unconditional. "Present" in the workbook's sense means the
            # provider can still take a wire transfer; a surviving row that
            # has lost its code and its custom_mode is a shell.
            ctx.check_true(
                "That record is the Custom / Wire Transfer provider — "
                "code='custom' with custom_mode='wire_transfer' "
                "(addons/payment_custom/data/"
                "payment_provider_data.xml:5,9)",
                bool(transfer_row
                     and transfer_row["code"] == PROVIDER_CUSTOM_CODE
                     and transfer_row["custom_mode"]
                     == PROVIDER_CUSTOM_MODE_WIRE),
                actual_desc=(f"code={transfer_row['code']!r} "
                             f"custom_mode={transfer_row['custom_mode']!r} "
                             f"name={transfer_row['name']!r}"
                             if transfer_row else
                             "the xmlid resolved to no row visible on "
                             "this company"))

        with ctx.step("Steps 3-4 / Expected line 2: open each live provider "
                      "and check its credential fields are not empty"):
            live = [row for row in provider_rows if row["state"] == STATE_LIVE]
            testing = [row for row in provider_rows
                       if row["state"] == STATE_TEST]
            ctx.log(f"{len(live)} provider(s) in raw state {STATE_LIVE!r}, "
                    f"{len(testing)} in {STATE_TEST!r}, "
                    f"{len(provider_rows) - len(live) - len(testing)} in "
                    f"{STATE_DISABLED!r} or another state")

            # ONE fields_get for the union of every credential name, then
            # only the names it hands back are touched. Doing it per provider
            # would be N round trips for the same answer.
            all_credentials = sorted(
                {name for names in PROVIDER_CREDENTIAL_FIELDS.values()
                 for name in names} | {WIRE_TRANSFER_INSTRUCTION_FIELD})
            credential_readable = fields_present(rpc, "payment.provider",
                                                 all_credentials)
            hidden = [name for name in all_credentials
                      if name not in credential_readable]
            if hidden:
                ctx.log(f"credential fields not visible to this session "
                        f"(reported as {CRED_UNREADABLE!r}, never as empty): "
                        f"{hidden}")

            empty_on_live: list[str] = []
            unreadable_on_live: list[str] = []
            # Every provider is inventoried, live or not, so the CSV supports
            # the whole baseline tick-off; only the LIVE ones become offenders,
            # because that is what the workbook's line 2 is about.
            for row in provider_rows:
                names = list(PROVIDER_CREDENTIAL_FIELDS.get(row["code"], ()))
                if (row["code"] == PROVIDER_CUSTOM_CODE
                        and WIRE_TRANSFER_INSTRUCTION_FIELD
                        in credential_readable):
                    names.append(WIRE_TRANSFER_INSTRUCTION_FIELD)
                if not names:
                    credential_rows.append(
                        (row["name"], row["code"], row["state"], "",
                         "no credential field is defined for this provider "
                         "code in Odoo 19", ""))
                    continue
                for field in names:
                    if field not in credential_readable:
                        status = CRED_UNREADABLE
                    else:
                        status = _credential_is_set(rpc, row["id"], field,
                                                    context)
                    note = ""
                    if field in PAYPAL_FIELDS_NEW_IN_V19 and status == CRED_EMPTY:
                        note = ("new in v19 — no v15 equivalent existed, so "
                                "it must be re-entered by hand")
                    if field == WIRE_TRANSFER_INSTRUCTION_FIELD:
                        note = ("instruction message, not a credential — "
                                "reported, never an offender")
                    credential_rows.append((row["name"], row["code"],
                                            row["state"], field, status, note))
                    ctx.log(f"  {row['name']!r}.{field}: {status}"
                            + (f" ({note})" if note else ""))

                    if row["state"] != STATE_LIVE:
                        continue
                    if field == WIRE_TRANSFER_INSTRUCTION_FIELD:
                        if status == CRED_EMPTY:
                            finding(ctx,
                                    f"the live wire-transfer provider "
                                    f"{row['name']!r} has an empty "
                                    f"{WIRE_TRANSFER_INSTRUCTION_FIELD} — the "
                                    f"customer who chooses it is shown no "
                                    f"bank account to pay into "
                                    f"(addons/payment_custom/models/"
                                    f"payment_provider.py:45-60 rebuilds this "
                                    f"from the company's bank journals). Not "
                                    f"counted as a missing credential, but "
                                    f"the money will not arrive.")
                        continue
                    if status == CRED_EMPTY:
                        empty_on_live.append(f"{_label(row)} — {field}")
                        if field in PAYPAL_FIELDS_NEW_IN_V19:
                            finding(
                                ctx,
                                f"{_label(row)} is LIVE with an empty "
                                f"{field}. This field is new in Odoo 19: v15's "
                                f"PayPal integration carried only "
                                f"{list(PAYPAL_V15_FIELDS)} "
                                f"(D:/Projects/odoo15/addons/payment_paypal/"
                                f"models/payment_acquirer.py:17-24), so the "
                                f"upgrade had nothing to copy across and this "
                                f"is a re-entry task rather than a code "
                                f"defect — take the value from the PayPal "
                                f"developer dashboard "
                                f"(addons/payment_paypal/models/"
                                f"payment_provider.py:31,36,54). It is still "
                                f"counted as a failure of the workbook's "
                                f"Expected line 2, because a live PayPal "
                                f"provider without a client id cannot take a "
                                f"payment today.")
                    elif status == CRED_UNREADABLE:
                        unreadable_on_live.append(f"{_label(row)} — {field}")

            # Reported first and separately: an unreadable field is a fact
            # about the runner's groups, and lumping it in with an empty one
            # would blame the gallery for the platform's permissions.
            if unreadable_on_live:
                ctx.log(f"NOTE — {len(unreadable_on_live)} credential(s) on "
                        f"live providers could not be read by this session "
                        f"and are NOT counted as empty: "
                        f"{unreadable_on_live}. Re-run as a Settings user to "
                        f"close the gap.")
                residual.append(
                    "these credential fields on LIVE providers were not "
                    "readable by the runner and could not be classified: "
                    + "; ".join(unreadable_on_live)
                    + ". Open each provider in "
                    + PROVIDER_MENU_PATH
                    + " as a Settings user and confirm the field is filled "
                      "in (the value stays masked — you are only checking it "
                      "is not empty).")

            ctx.check(
                "Every payment provider that is LIVE (raw state 'enabled') "
                "has all of its credential fields filled in — the workbook's "
                "'its credential fields are populated'. Values were never "
                "read: each field was tested with the domain "
                "(field, '!=', False)",
                [], sorted(empty_on_live))

        with ctx.step("Step 6 / Expected line 3: no provider that should be "
                      "live is sitting in Test or Disabled"):
            # Which ones "should be" live needs the Novobi baseline, so what
            # is asserted here is the part that needs no baseline at all.
            by_state: dict[str, list[str]] = {}
            for row in provider_rows:
                by_state.setdefault(row["state"], []).append(_label(row))
            state_labels = selection_labels(rpc, "payment.provider", "state")
            for state in sorted(by_state):
                ctx.log(f"  state={state!r} ({state_labels.get(state, '')}): "
                        f"{by_state[state]}")

            # (a) A provider offered on the website while Disabled is upgrade
            #     damage: Odoo refuses to create that combination itself.
            published_while_disabled = sorted(
                _label(row) for row in provider_rows
                if row["is_published"] and row["state"] == STATE_DISABLED)
            ctx.check(
                "No provider is still published on the website while its "
                "state is Disabled — Odoo itself refuses that combination "
                "(action_toggle_is_published raises 'You cannot publish a "
                "disabled provider', addons/payment/models/"
                "payment_provider.py:537-539; and the form's own "
                "@api.onchange('state') at :273-279 unpublishes as soon as "
                "the state is edited on screen — which is why only a write "
                "that bypassed the form, i.e. the migration, can produce "
                "this), so a row in it means the shop still shows a payment "
                "button that cannot take money",
                [], published_while_disabled)

            # (b) A live provider whose module never installed shows as
            #     Enabled and fails at the moment a customer tries — exactly
            #     the silence the workbook's Business Purpose describes.
            live_without_module = sorted(
                f"{_label(row)} — module {row['module'] or '(none)'} "
                f"state {row['module_state'] or '(not installed)'}"
                for row in provider_rows
                if row["state"] in (STATE_LIVE, STATE_TEST)
                and (row["code"] == CODE_UNIMPLEMENTED
                     or (row["module_state"]
                         and row["module_state"] != "installed")))
            ctx.check(
                "Every provider that is Enabled or in Test Mode has its "
                "implementing module installed — code stays at the default "
                "'none' until the provider's own module data file sets it "
                "(addons/payment/models/payment_provider.py:34-40 vs "
                "addons/payment_paypal/data/payment_provider_data.xml:5), so "
                "a live provider with code 'none' or an uninstalled module "
                "looks configured on screen and fails when a customer tries",
                [], live_without_module)

            # (c) Non-vacuity. The workbook's Business Purpose is "Customers
            #     pay by card and PayPal"; a database where nothing is live
            #     means online payments are off for everyone, and this case
            #     must not pass by finding nothing to check.
            ctx.check_true(
                "At least one payment provider is LIVE — the workbook's "
                "Business Purpose is 'Customers pay by card and PayPal', so a "
                "database in which every provider sits in Test or Disabled "
                "means online payments are off for the whole gallery",
                bool([row for row in provider_rows
                      if row["state"] == STATE_LIVE]),
                actual_desc="; ".join(
                    f"{state}={len(labels)}"
                    for state, labels in sorted(by_state.items()))
                or "no provider rows at all")

        with ctx.step("Step 4: the gallery's card provider and PayPal, "
                      "reported for the baseline rather than guessed at"):
            # Deliberately NOT asserted. Deciding that Authorize.Net "should"
            # be live would be inventing the Novobi baseline, which this
            # platform must never do. The observed states are printed into the
            # residual note so the human's step is a comparison, not a re-run.
            spotlight = [row for row in provider_rows
                         if row["code"] in SPOTLIGHT_CODES]
            absent_spotlight = []
            for code in SPOTLIGHT_CODES:
                found = [row for row in spotlight if row["code"] == code]
                if not found:
                    absent_spotlight.append(code)
                    finding(ctx,
                            f"no payment.provider row carries code {code!r} on "
                            f"company {company['name']!r}. Odoo ships the row "
                            f"itself from addons/payment/data/"
                            f"payment_provider_data.xml (:158 Authorize.net, "
                            f":367 PayPal) and only the provider MODULE sets "
                            f"its code, so this almost always means the module "
                            f"is not installed rather than that the row was "
                            f"deleted — check the module states logged in the "
                            f"precondition step first.")
                    continue
                for row in found:
                    verdict = ("LIVE" if row["state"] == STATE_LIVE
                               else f"NOT live (state={row['state']!r})")
                    ctx.log(f"  workbook step 4 — {row['name']!r}: {verdict}")
                    if row["state"] != STATE_LIVE:
                        finding(ctx,
                                f"{_label(row)} — one of the two providers "
                                f"this case is registered against "
                                f"(payment_authorize / payment_paypal) — is "
                                f"in state {row['state']!r} "
                                f"({row['state_label']}), not Enabled. If the "
                                f"Novobi baseline says it should be live, "
                                f"this is the case's P1 failure; if the "
                                f"gallery retired it before the upgrade, it "
                                f"is correct. Only the baseline can tell "
                                f"them apart — do NOT switch it on to find "
                                f"out.")

            residual.append(
                "workbook step 4 — compare these observed states for the "
                "gallery's card provider and PayPal against the Novobi "
                "baseline: "
                + ("; ".join(f"{row['name']} (code={row['code']}) is "
                             f"{row['state']} / published="
                             f"{row['is_published']}"
                             for row in spotlight)
                   or "NEITHER an 'authorize' nor a 'paypal' provider row is "
                      "visible on this company")
                + ". The workbook's If It Fails is explicit: list each "
                  "provider with its baseline state and its v19 state, and do "
                  "NOT change a provider's state yourself — switching one "
                  "live with half-migrated credentials can take real customer "
                  "payments into a broken configuration.")

            # Asserted, not merely reported. WHICH state each should be in
            # needs the baseline; that they are THERE AT ALL does not — the
            # workbook's step 4 singles them out by name ("the gallery's card
            # provider and PayPal") and its module column names them
            # (payment_authorize / payment_paypal), so their absence is a
            # failure of Expected line 1 that needs no printout to judge. A
            # row whose code has fallen back to 'none' does not count as
            # present: its module is not installed and it cannot take money.
            ctx.check(
                "Both providers the workbook's step 4 singles out — the "
                "gallery's card provider (payment_authorize) and PayPal "
                "(payment_paypal) — are present as working payment.provider "
                "rows, i.e. carry their own provider code rather than the "
                "default 'none' (addons/payment/models/payment_provider.py:"
                "34-40 vs addons/payment_paypal/data/"
                "payment_provider_data.xml:5)",
                [], sorted(absent_spotlight))

        with ctx.step("Steps 2 and 6 / Expected lines 1 and 2: the baseline "
                      "tick-off, which only the Novobi list can settle"):
            residual.append(
                "tick every provider on the Novobi baseline off against "
                + PROVIDERS_CSV + ", which holds all "
                + str(len(provider_rows))
                + " provider(s) visible on company "
                + f"{company['name']!r} with their raw state, published flag, "
                  "module and module state. Two rules for that pass: (1) a "
                  "baseline line reading 'Wire Transfer' or 'transfer' is "
                  "matched by the row with code 'custom' / custom_mode "
                  "'wire_transfer' — the rename is not a missing provider; "
                  "(2) compare STATES on the raw values in the CSV "
                  "('enabled' / 'test' / 'disabled'), not on the on-screen "
                  "labels, because Odoo 19 shows 'Test Mode' where a v15 "
                  "baseline is likely to say 'Test'.")
            residual.append(
                "credential detail for that pass is in " + CREDENTIALS_CSV
                + ", one row per provider and field with status set / not "
                  "set / not readable. No credential VALUE appears in either "
                  "file, in this log, or anywhere in this platform: each "
                  "field was tested with the domain (field, '!=', False) so "
                  "the database, not the runner, held the secret.")
    finally:
        with ctx.step("Evidence: write the provider inventory and credential "
                      "status CSVs"):
            for path_name, header, rows in (
                (PROVIDERS_CSV,
                 ["provider", "code", "code_label", "custom_mode",
                  "state_raw", "state_label", "published", "module",
                  "module_state", "company"],
                 [[row["name"], row["code"], row["code_label"],
                   row["custom_mode"], row["state"], row["state_label"],
                   row["is_published"], row["module"], row["module_state"],
                   row["company"]] for row in provider_rows]),
                (CREDENTIALS_CSV,
                 ["provider", "code", "state_raw", "credential_field",
                  "status", "note"],
                 credential_rows),
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
            for note in residual:
                residual_manual_step(ctx, note)
            ctx.log("NOTHING WAS CREATED OR MODIFIED by this case — the "
                    "workbook's State After The Test is 'Nothing changed. Do "
                    "not enable or disable anything.', so no provider state, "
                    "no credential and no published flag was written, and no "
                    "sweep and no cleanup runs here either (a sweep is itself "
                    "a delete).")
