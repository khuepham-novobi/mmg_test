"""FG-07 — TC-INV-006: Registering a payment offers the gallery's default journal.

Implements row 36.0 (P1, "Payments") of the CLIENT MANUAL TESTING GUIDELINE
``MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0.xlsx`` / sheet
``Testing Guideline``.

The workbook's framing: *"Almost every payment goes through the same account.
Setting it once as a default saves the accountant choosing it on every payment
and stops payments landing in the wrong journal."*

READ THIS FIRST, as the workbook's own *Why It Matters* column does: **the
behaviour deliberately changed.** In the gallery's Odoo 15 the company default
always won — ``mmg_default_payment_journal/wizards/account_payment_register.py:
7-13`` overrides ``_compute_journal_id``, calls ``super()`` and then
*unconditionally* writes ``rec.journal_id = rec.company_id.
payment_default_journal_id`` for every wizard whose company has one. Odoo 19's
own ``_compute_journal_id`` (``addons/account/wizard/account_payment_register.
py:503-519``) is layered instead: it *keeps* a journal the user already chose
(``:506-507`` ``continue``), then prefers the invoice's
``preferred_payment_method_line_id.journal_id`` (``:508-510``), and only then
falls back to ``_get_batch_journal``. A correct v19 port has to hang the
gallery default off that last, fallback rung — which is exactly what this case
measures.

The 4 Expected Result lines, and what each is read from
-------------------------------------------------------
1. **"Step 3: the pop-up offers Journal 1, the company default, already
   filled in."** — read from ``account.payment.register.journal_id`` on a
   wizard created with the Pay button's own context
   (``active_model='account.move'``, ``active_ids=[invoice]``), which is what
   ``tests/fg07/common.py::register_payment`` sends. The field is
   ``compute='_compute_journal_id', store=True, readonly=False,
   precompute=True`` (``addons/account/wizard/account_payment_register.py:
   34-38``), so the value is computed *at create time* and is genuinely "what
   the pop-up shows when it opens". Measured twice — once with the company
   default cleared, to learn Odoo's own unaided pick via ``_get_batch_journal``
   (``:212-234``, journals ordered by ``account.journal._order = 'sequence,
   type, code'``, ``addons/account/models/account_journal.py:45``), and once
   with the default set to a *different* journal — so a pass cannot be an
   accident of the two agreeing.
2. **"Step 6: your manual choice of Journal 2 was kept. The default did NOT
   overwrite it. This is the important half."** — read twice: from
   ``journal_id`` re-read after the wizard is edited again (exercising the
   keep-if-still-available ``continue`` at ``:506-507``), and from the real
   ``account.payment.journal_id`` that ``action_create_payments`` produces
   (``:1073``, where the payment is built with ``'journal_id': self.
   journal_id.id``). The second reading is the one the workbook's step 6
   literally describes — "Open the payment that was created and read its
   Journal".
3. **"Step 7: where the customer has their own preferred payment method, that
   wins over the company default."** — read from ``journal_id`` and
   ``payment_method_line_id`` on a wizard opened over an invoice whose
   ``preferred_payment_method_line_id`` is set. That field is computed from
   ``partner.property_inbound_payment_method_line_id`` on a sale document
   (``addons/account/models/account_move.py:1532-1539``) and depends only on
   ``('partner_id', 'company_id')`` (the ``@api.depends`` at ``:1532``) — it
   is ``store=True, readonly=False``
   (``:513-518``), so it does **not** recompute when the partner's preference
   is changed after the invoice exists. This case therefore sets the partner
   preference *before* creating the invoice; doing it the other way round
   produces a false failure. Measured twice again — with the company default
   cleared and with it set — because only the second reading proves the
   default is a *fallback* rather than a winner.
4. **"Note: the Default Payment Journal dropdown lists ALL journals, not only
   bank and cash. That is the same in the old system and is not a defect."** —
   read from ``res.config.settings.fields_get(['payment_default_journal_id'],
   ['domain'])``. In v15 the domain lives on ``res.company``
   (``mmg_default_payment_journal/models/res_company.py:7-8``,
   ``[('company_id','=',company_id),('type','in',('bank','cash'))]``) while the
   settings field is a bare ``related`` with no domain of its own
   (``models/res_config_settings.py:7-10``) — which is precisely why the
   dropdown is unrestricted. Recorded as an **OBSERVATION**, asserted in
   neither direction.

A port defect this case also catches, before it looks at any journal
--------------------------------------------------------------------
The v15 view patches the settings form with ``<xpath expr="//div[@id=
'invoicing_settings']" position="inside">``
(``mmg_default_payment_journal/views/res_config_settings_view.xml:9``). In
Odoo 19 that container is no longer a ``div``: it is
``<block title="Customer Invoices" id="invoicing_settings">``
(``addons/account/views/res_config_settings_views.xml:127``). The v15 xpath
cannot match it. So this case asserts, before anything else, that
``res.config.settings`` exposes the field *and* that the served settings form
arch actually contains it — an installed module whose control never reaches
the screen would otherwise read as "the accountant forgot to set it".

Documented adaptation — the setting is written on res.company, not through
the Settings wizard
--------------------------------------------------------------------------
The workbook's step 1 is "Accounting > Configuration > Settings … set it to
Journal 1 and save". ``res.config.settings.payment_default_journal_id`` is a
``related='company_id.payment_default_journal_id', readonly=False`` field
(``mmg_default_payment_journal/models/res_config_settings.py:7-10``), so
pressing Save writes exactly one thing: that value onto ``res.company``. This
case writes ``res.company`` directly. The saved end state is identical, and it
avoids instantiating a full ``res.config.settings`` record, whose ``execute()``
would re-save every other setting on the page — a company-wide side effect the
workbook never asks for.

**This case mutates a company-wide setting.** The workbook is emphatic
("CONFIRM THIS before closing the case — it is a company-wide setting and
every future payment reads it"), so the original value is snapshotted in the
precondition step, restored *and asserted* on the normal path, and restored
again — non-raising, and loudly logged as a FINDING if it did not take — from
the ``finally`` block, which runs even when an assertion above it has already
failed.

A finding this case will surface
--------------------------------
That the customer's own preferred payment method now outranks the company
default is a **deliberate v19 change**, not a regression: the workbook says so
("Brief the accounting team before they test this, or the change will be
reported as a defect"). The *affirmative* Expected Result line 3 is asserted,
because the workbook states it as an expectation and because a v15-shaped port
— an unconditional post-``super()`` override — is the one thing that would
break it. Alongside the assertion the measured precedence is also recorded via
``common.observation`` with the actual journal names, so whoever reads the run
can brief the accounting team with real values rather than a description.
Expected Result line 4 (the unrestricted dropdown) is an OBSERVATION only.
"""
from __future__ import annotations

import csv
import xml.etree.ElementTree as ET

from adapters.base import OdooRPCError
from framework.registry import test_case
from tests.fg07.common import (NO_DEFAULT_JOURNAL, WORKFLOW,
                               WORKFLOW_NAME, acting_company, cleanup,
                               company_ctx, confirm_payment_register,
                               fields_present, finding, m2o_id, m2o_name,
                               make_invoice, make_partner, make_product,
                               module_state, money, observation, payment_row,
                               register_payment, require_v19,
                               residual_manual_step, restore_company_value,
                               sweep_fg07, trace)

OFFERS_CSV = "TC-INV-006-payment-journal-offers.csv"
CSV_HEADER = ("workbook_step", "scenario", "company_default_journal",
              "customer_preferred_method", "journal_offered",
              "payment_method_offered", "verdict")

# The field the whole case turns on. Named on res.company by
# mmg_default_payment_journal/models/res_company.py:7 and mirrored onto
# res.config.settings as a related field by models/res_config_settings.py:7.
COMPANY_FIELD = "payment_default_journal_id"
MODULE_NAME = "mmg_default_payment_journal"

# Workbook step 1: "In the Invoicing app tab, find the Customer Invoices
# block". That block is <block title="Customer Invoices"
# id="invoicing_settings"> in Odoo 19
# (addons/account/views/res_config_settings_views.xml:127) — verified against
# the source, and the very element the v15 patch could not match because it
# aimed at //div[@id='invoicing_settings'].
SETTINGS_BLOCK_ID = "invoicing_settings"
SETTINGS_BLOCK_TITLE = "Customer Invoices"

# The journal types Odoo 19's payment-register wizard will ever offer
# (addons/account/wizard/account_payment_register.py:202-204). 'credit' is new
# in v19 — a v15-era expectation of exactly ('bank', 'cash') is wrong here and
# would report a correct system as broken.
WIZARD_JOURNAL_TYPES = ("bank", "cash", "credit")

# The workbook's own two names for the journals, kept so the log reads like
# the manual test the accountant is following.
JOURNAL_1 = "Journal 1 (the company default this case sets)"
JOURNAL_2 = "Journal 2 (the manual choice, and the customer's preference)"


def _journal_label(row: dict) -> str:
    """``CODE Name [type]`` — the way an accountant recognises a journal."""
    return (f"{row.get('code') or '??'} {row.get('name') or ''!r} "
            f"[{row.get('type') or '?'}]")


def _field_in_block(arch: str, block_id: str, field_name: str) -> tuple:
    """``(found, what_was_seen)`` for a field nested under ``id=block_id``.

    Substring-matching ``name="payment_default_journal_id"`` anywhere in the
    served arch is weaker than the workbook, whose step 1 sends the
    administrator to a named block: a field re-homed to some other block —
    or to another app's tab — passes a substring test and still leaves the
    accountant unable to find the control. Never raises; a parse failure is
    returned as a reading, because the arch is the product's output and a
    broken one is a finding rather than an automation fault.
    """
    if not arch:
        return False, "the Settings form arch could not be read"
    try:
        root = ET.fromstring(arch)
    except ET.ParseError as exc:
        return False, f"the Settings form arch would not parse ({exc})"
    blocks = [node for node in root.iter()
              if node.attrib.get("id") == block_id]
    if not blocks:
        return False, (f"the served arch carries no element with "
                       f"id={block_id!r} at all, so the Customer Invoices "
                       f"block the workbook names is not on this Settings "
                       f"page")
    for block in blocks:
        for node in block.iter("field"):
            if node.attrib.get("name") == field_name:
                return True, (f"<field name={field_name!r}> found inside "
                              f"<{block.tag} id={block_id!r} "
                              f"title={block.attrib.get('title')!r}>")
    elsewhere = [node.attrib.get("name") for node in root.iter("field")
                 if node.attrib.get("name") == field_name]
    return False, (
        f"<field name={field_name!r}> is "
        f"{'present elsewhere on the Settings page but NOT inside'  if elsewhere else 'not present at all, and in particular not inside'} "
        f"<{blocks[0].tag} id={block_id!r} "
        f"title={blocks[0].attrib.get('title')!r}>. The v15 patch aimed at "
        f"//div[@id='invoicing_settings'] "
        f"(mmg_default_payment_journal/views/res_config_settings_view.xml:9) "
        f"and Odoo 19 ships <block title=\"Customer Invoices\" "
        f"id=\"invoicing_settings\"> "
        f"(addons/account/views/res_config_settings_views.xml:127), so an "
        f"un-repointed xpath lands the control somewhere the workbook's step "
        f"1 never looks")


def _set_company_default(ctx, company: dict, journal_id) -> bool:
    """Write ``res.company.payment_default_journal_id``, never raising.

    Returns whether the write landed. See the module docstring for why this
    goes to ``res.company`` rather than through a ``res.config.settings``
    record: the settings field is a bare ``related`` and Save writes exactly
    this, while ``execute()`` would re-save the whole Settings page.
    """
    try:
        ctx.adapter.rpc.call("res.company", "write", [company["id"]],
                             {COMPANY_FIELD: journal_id or False},
                             context=company_ctx(company))
    except OdooRPCError as exc:
        ctx.log(f"could not write res.company.{COMPANY_FIELD} = "
                f"{journal_id!r} ({exc})")
        return False
    return True


def _read_company_default(ctx, company: dict):
    """The stored company default, or ``None`` when it cannot be read."""
    try:
        row = ctx.adapter.rpc.call("res.company", "read", [company["id"]],
                                   fields=[COMPANY_FIELD],
                                   context=company_ctx(company))[0]
    except (OdooRPCError, IndexError, KeyError) as exc:
        ctx.log(f"could not read res.company.{COMPANY_FIELD} ({exc})")
        return None
    return m2o_id(row.get(COMPANY_FIELD))


def _open_pay_popup(ctx, move_id: int, company: dict) -> dict:
    """Press **Pay** on one posted invoice and read the pop-up as it opens.

    Creating the wizard *is* opening the pop-up. ``journal_id`` is
    ``compute='_compute_journal_id', store=True, readonly=False,
    precompute=True`` (``addons/account/wizard/account_payment_register.py:
    34-38``). ``payment_method_line_id`` is
    ``compute='_compute_payment_method_line_id', store=True, readonly=False``
    and carries **no** ``precompute`` (``:120-124``) — but a *stored* compute
    is still evaluated during ``create()``, so both fields are resolved by the
    time ``create`` returns; ``precompute`` only moves ``journal_id``'s
    evaluation ahead of the INSERT itself. Reading them straight back is
    therefore genuinely "what the pop-up shows when it opens".

    Nothing here raises — a pop-up that refuses to open is a finding this case
    must *report*, not an AUTOMATION_ERROR that hides every other reading.
    """
    rpc = ctx.adapter.rpc
    blank = {"wizard_id": None, "journal_id": None, "journal": "",
             "method_line_id": None, "method_line": "", "available_ids": [],
             "payment_date": None, "error": ""}
    try:
        wizard_id = register_payment(ctx, [move_id], company=company)
    except OdooRPCError as exc:
        blank["error"] = f"the Pay pop-up would not open: {exc}"
        return blank
    try:
        row = rpc.call("account.payment.register", "read", [wizard_id],
                       fields=["journal_id", "payment_method_line_id",
                               "available_journal_ids", "payment_date",
                               "can_edit_wizard", "amount"],
                       context=company_ctx(company))[0]
    except (OdooRPCError, IndexError) as exc:
        blank["wizard_id"] = wizard_id
        blank["error"] = f"the pop-up opened but could not be read: {exc}"
        return blank
    return {
        "wizard_id": wizard_id,
        "journal_id": m2o_id(row.get("journal_id")),
        "journal": m2o_name(row.get("journal_id")),
        "method_line_id": m2o_id(row.get("payment_method_line_id")),
        "method_line": m2o_name(row.get("payment_method_line_id")),
        "available_ids": list(row.get("available_journal_ids") or []),
        "payment_date": row.get("payment_date"),
        "amount": money(row.get("amount")),
        "can_edit_wizard": bool(row.get("can_edit_wizard")),
        "error": "",
    }


def _discard_popup(ctx, popup: dict):
    """Workbook step 4 — "Close the pop-up without confirming".

    The wizard is a TransientModel and Odoo's own vacuum would remove it, but
    dropping it here keeps a long-lived QA database tidy. Never raises.
    """
    wizard_id = popup.get("wizard_id")
    if not wizard_id:
        return
    try:
        ctx.adapter.rpc.unlink("account.payment.register", [wizard_id])
    except OdooRPCError as exc:
        ctx.log(f"the abandoned pop-up record #{wizard_id} could not be "
                f"dropped ({exc}) — harmless, it is a TransientModel and "
                f"Odoo's vacuum will remove it")


@test_case(
    id="TEST-FG07-INV-006",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module="mmg_default_payment_journal",
    priority="P1",
    kind="API",
    order=707,
    name="Registering a payment offers the gallery's default journal",
    description="The Pay pop-up pre-fills the company's Default Payment "
                "Journal, a journal the accountant picks by hand survives to "
                "the created payment, and a customer's own preferred payment "
                "method outranks the company default — the deliberate v19 "
                "change. The company-wide setting is restored and the restore "
                "is asserted.",
    traceability=trace("TC-INV-006"))
def test_inv_006(ctx):
    rpc = ctx.adapter.rpc
    created = {"account.move": [], "res.partner": []}
    evidence: list[tuple] = []      # CSV rows — declared BEFORE the try
    residual: list[str] = []        # residual notes — declared BEFORE the try
    original_default = None         # snapshot for the workbook's restore
    restored_ok = False             # set once the try-path restore is asserted
    company: dict = {}

    with ctx.step("Precondition (workbook): an administrator who can edit "
                  "Accounting > Configuration > Settings, two bank or cash "
                  "journals, and a posted unpaid customer invoice"):
        require_v19(ctx)
        company = acting_company(ctx)
        ctx.log(f"acting company #{company['id']} {company['name']!r} — "
                f"currency {company['currency_name']}, chart_template="
                f"{company['chart_template']!r}")

        # PROBE, then BLOCK. The definitive probe is the FIELD, not the module
        # row: a v19 port may legitimately carry a different module name, and
        # conversely a module row in state 'to install' proves nothing about
        # what the registry currently holds. The module state is logged
        # alongside so the reader can tell "not ported" from "not installed".
        state = module_state(rpc, MODULE_NAME)
        ctx.log(f"ir.module.module state for {MODULE_NAME!r}: "
                f"{state or 'no such module row'}")
        if COMPANY_FIELD not in fields_present(rpc, "res.company",
                                               [COMPANY_FIELD]):
            ctx.blocked(f"{NO_DEFAULT_JOURNAL} (ir.module.module state for "
                        f"{MODULE_NAME!r}: {state or 'no such module row'})")

        sweep_fg07(ctx)

    try:
        with ctx.step("Step 1 / port check: the Default Payment Journal "
                      "control really exists on Accounting > Configuration > "
                      "Settings, in the Customer Invoices block"):
            # Half of a broken port looks exactly like an accountant who never
            # set the value, so this is asserted before any journal is read.
            settings_fields = fields_present(rpc, "res.config.settings",
                                             [COMPANY_FIELD])
            ctx.check_true(
                "Accounting > Configuration > Settings exposes Default "
                "Payment Journal (res.config.settings."
                f"{COMPANY_FIELD}, the related field the Save button writes "
                "onto res.company)",
                COMPANY_FIELD in settings_fields,
                actual_desc=(f"res.config.settings.fields_get did not return "
                             f"{COMPANY_FIELD!r} — the field is on res.company "
                             f"but never reached the Settings screen"
                             if COMPANY_FIELD not in settings_fields
                             else f"{COMPANY_FIELD} is readable on "
                                  f"res.config.settings"))

            # The v15 patch targets //div[@id='invoicing_settings']; v19 ships
            # <block title="Customer Invoices" id="invoicing_settings">
            # (addons/account/views/res_config_settings_views.xml:127). If the
            # xpath was not re-pointed, the field exists and the screen does
            # not show it.
            try:
                arch = rpc.call("res.config.settings", "get_view",
                                view_type="form",
                                context=company_ctx(company))["arch"]
            except (OdooRPCError, KeyError, TypeError) as exc:
                arch = ""
                ctx.log(f"could not fetch the res.config.settings form arch "
                        f"({exc})")
            ctx.check_true(
                "The served Settings form arch actually renders Default "
                "Payment Journal (the v15 patch aimed at "
                "//div[@id='invoicing_settings'], which in Odoo 19 is a "
                "<block>, not a <div>)",
                bool(arch) and f'name="{COMPANY_FIELD}"' in arch,
                actual_desc=(f'\'name="{COMPANY_FIELD}"\' absent from a '
                             f'{len(arch)}-character arch'
                             if arch else
                             "the Settings form arch could not be read"))
            # …and in the RIGHT PLACE. Workbook step 1 is "In the Invoicing
            # app tab, find the Customer Invoices block": a control that
            # exists on the page but not in that block is a control the
            # administrator following the workbook will not find, and it is
            # exactly what an un-repointed v15 xpath produces.
            in_block, where = _field_in_block(arch, SETTINGS_BLOCK_ID,
                                              COMPANY_FIELD)
            ctx.check_true(
                f"Default Payment Journal is rendered inside the "
                f"{SETTINGS_BLOCK_TITLE!r} block of Accounting > "
                f"Configuration > Settings — the block workbook step 1 sends "
                f"the administrator to (<block title=\"{SETTINGS_BLOCK_TITLE}\""
                f" id=\"{SETTINGS_BLOCK_ID}\">, "
                f"addons/account/views/res_config_settings_views.xml:127)",
                in_block, actual_desc=where)

            # Expected Result line 4 — OBSERVATION, asserted in neither
            # direction. The workbook says explicitly this is not a defect.
            try:
                spec = rpc.call("res.config.settings", "fields_get",
                                [COMPANY_FIELD],
                                attributes=["domain", "string", "relation"])
            except OdooRPCError:
                spec = {}
            domain_text = str((spec.get(COMPANY_FIELD) or {}).get("domain")
                              or "")
            all_journals = rpc.search("account.journal",
                                      [("company_id", "=", company["id"])])
            payable_journals = rpc.search(
                "account.journal",
                [("company_id", "=", company["id"]),
                 ("type", "in", list(WIZARD_JOURNAL_TYPES))])
            observation(
                ctx,
                f"the Default Payment Journal dropdown offers "
                f"{len(all_journals)} journal(s) for this company, of which "
                f"only {len(payable_journals)} are of a type a payment can "
                f"actually use {WIZARD_JOURNAL_TYPES}. The settings field "
                f"carries domain {domain_text or '(none)'} — in v15 the "
                f"bank/cash restriction sat on res.company "
                f"(mmg_default_payment_journal/models/res_company.py:7-8) and "
                f"never on the related settings field "
                f"(models/res_config_settings.py:7-10), so the unrestricted "
                f"list is identical to the old system. The workbook states "
                f"this is NOT a defect")

        with ctx.step("Step 1 (workbook): WRITE DOWN whatever Default Payment "
                      "Journal currently holds — it goes back at the end"):
            original_default = company.get("payment_default_journal_id")
            original_label = "(empty)"
            if original_default:
                rows = rpc.search_read("account.journal",
                                       [("id", "=", original_default)],
                                       ["name", "code", "type"])
                original_label = (_journal_label(rows[0]) if rows
                                  else f"#{original_default} (unreadable)")
            ctx.log(f"SNAPSHOT — res.company.{COMPANY_FIELD} was "
                    f"{original_label}. This is a COMPANY-WIDE setting: every "
                    f"future payment in this database reads it, so it is "
                    f"restored on the normal path AND again from the finally "
                    f"block")
            evidence.append(("Step 1", "value found before the test",
                             original_label, "", "", "", "snapshot"))

        with ctx.step("Steps 2-3 (measure): with NO company default, learn "
                      "what Odoo 19 offers on its own"):
            # A posted, unpaid invoice for a customer WITHOUT a preferred
            # payment method — otherwise the wizard would take the :508-510
            # preference branch and this reading would measure the wrong rung.
            partner_plain = make_partner(ctx, "INV-006 Plain Customer",
                                         company=company)
            created["res.partner"].append(partner_plain)
            product_id = make_product(ctx, "INV-006 Catalogue Piece", 1000.00)
            invoice_a = make_invoice(ctx, partner_plain,
                                     [(product_id, 1, 1000.00)],
                                     company=company)
            created["account.move"].append(invoice_a)
            rpc.call("account.move", "action_post", [invoice_a],
                     context=company_ctx(company))
            # Posted the instant this returns — drop it, because handing a
            # posted move to unlink() resets it to draft and destroys
            # accounting evidence.
            created["account.move"].remove(invoice_a)
            ctx.log(f"invoice A #{invoice_a} posted and unpaid — the "
                    f"workbook's 'posted, unpaid customer invoice'")

            _set_company_default(ctx, company, False)
            unaided = _open_pay_popup(ctx, invoice_a, company)
            ctx.check_true(
                "The Pay pop-up opens on a posted unpaid invoice",
                not unaided["error"] and bool(unaided["wizard_id"]),
                actual_desc=unaided["error"] or
                f"wizard #{unaided['wizard_id']} opened")
            journals = rpc.search_read(
                "account.journal",
                [("id", "in", unaided["available_ids"])],
                ["name", "code", "type", "sequence"],
                order="sequence, type, code",
                context=company_ctx(company))
            labels = {row["id"]: _journal_label(row) for row in journals}
            ctx.log(f"the pop-up's Journal dropdown offers "
                    f"{len(journals)} journal(s): "
                    f"{[labels[r['id']] for r in journals]}")
            # The workbook's precondition, checked as a precondition rather
            # than asserted: without two offerable journals there is no
            # "Journal 1" and "Journal 2" and the case cannot mean anything.
            if len(journals) < 2:
                ctx.blocked(
                    f"the workbook's precondition 'Two bank or cash journals "
                    f"exist. Call them Journal 1 and Journal 2' is not met: "
                    f"Odoo 19's payment-register wizard offers only "
                    f"{len(journals)} journal(s) for company "
                    f"#{company['id']} {company['name']!r} "
                    f"({[labels[r['id']] for r in journals]}). The wizard "
                    f"offers journals of type {WIZARD_JOURNAL_TYPES} that "
                    f"carry at least one inbound payment method line "
                    f"(addons/account/wizard/account_payment_register.py:"
                    f"202-208), so create a second bank or cash journal in "
                    f"Accounting > Configuration > Journals and re-run")

            odoo_pick = unaided["journal_id"]
            ctx.log(f"with NO company default, Odoo 19 picks "
                    f"{labels.get(odoo_pick, odoo_pick)} on its own "
                    f"(_get_batch_journal, account.journal._order = "
                    f"'sequence, type, code')")
            evidence.append(("Steps 2-3", "company default cleared", "(empty)",
                             "(none)", labels.get(odoo_pick, str(odoo_pick)),
                             unaided["method_line"], "baseline"))
            _discard_popup(ctx, unaided)

            # Journal 1 is deliberately NOT the journal Odoo would have picked
            # anyway, so that a pass proves the default was read rather than
            # that the two happened to agree.
            ordered = [row["id"] for row in journals]
            journal_1 = next((j for j in ordered if j != odoo_pick),
                             ordered[0])
            journal_2 = next((j for j in ordered if j != journal_1),
                             ordered[-1])
            ctx.log(f"{JOURNAL_1} = {labels[journal_1]}")
            ctx.log(f"{JOURNAL_2} = {labels[journal_2]}")
            ctx.check_true(
                "Journal 1 and Journal 2 are two DIFFERENT journals the Pay "
                "pop-up will accept (workbook Test Data), and Journal 1 is "
                "not the journal Odoo would have chosen unaided — so a pass "
                "on Expected line 1 cannot be a coincidence",
                journal_1 != journal_2 and journal_1 != odoo_pick,
                actual_desc=f"Journal 1 = {labels[journal_1]}, Journal 2 = "
                            f"{labels[journal_2]}, Odoo's unaided pick = "
                            f"{labels.get(odoo_pick, odoo_pick)}")

        with ctx.step("Step 1 then Step 3 / Expected line 1: set Default "
                      "Payment Journal to Journal 1 and save, then read the "
                      "Journal the pop-up offers BEFORE changing anything"):
            ctx.check_true(
                f"Default Payment Journal saved as Journal 1 "
                f"({labels[journal_1]}) on res.company",
                _set_company_default(ctx, company, journal_1),
                actual_desc=f"write of res.company.{COMPANY_FIELD} = "
                            f"#{journal_1} was refused")
            ctx.check("Default Payment Journal reads back as Journal 1 after "
                      "saving", journal_1,
                      _read_company_default(ctx, company))

            offered = _open_pay_popup(ctx, invoice_a, company)
            ctx.check_true("The Pay pop-up opens with the company default set",
                           not offered["error"],
                           actual_desc=offered["error"] or "opened")
            seen = labels.get(offered["journal_id"],
                              str(offered["journal_id"]))
            ctx.log(f"RESULT (workbook If It Fails, 1 of 3 — what was "
                    f"offered): the pop-up offers {seen}; Journal 1 is "
                    f"{labels[journal_1]}")
            evidence.append(
                ("Step 3", "company default = Journal 1, plain customer",
                 labels[journal_1], "(none)", seen, offered["method_line"],
                 "PASS" if offered["journal_id"] == journal_1 else "FAIL"))
            _discard_popup(ctx, offered)

            # EXPECTED RESULT LINE 1.
            ctx.check("The Pay pop-up offers the company's Default Payment "
                      "Journal, already filled in, before the accountant "
                      "changes anything (account.payment.register.journal_id "
                      "as the pop-up opens)",
                      journal_1, offered["journal_id"])

        with ctx.step("Steps 4-5 / Expected line 2: close the pop-up without "
                      "confirming, re-open it, change the Journal by hand to "
                      "Journal 2, and confirm the payment"):
            wizard = _open_pay_popup(ctx, invoice_a, company)
            ctx.check_true("The Pay pop-up re-opens for test B",
                           not wizard["error"],
                           actual_desc=wizard["error"] or "opened")
            try:
                rpc.call("account.payment.register", "write",
                         [wizard["wizard_id"]], {"journal_id": journal_2},
                         context=company_ctx(company))
                manual_write_error = ""
            except OdooRPCError as exc:
                manual_write_error = str(exc)
            ctx.check_true(
                f"The accountant can change the Journal by hand to Journal 2 "
                f"({labels[journal_2]}) — it is inside the pop-up's own "
                f"domain [('id','in',available_journal_ids)]",
                not manual_write_error,
                actual_desc=manual_write_error or "accepted")

            # Touch the pop-up once more before confirming, the way the real
            # form does when the accountant tabs through it, and re-read.
            #
            # BE HONEST ABOUT WHAT THIS PROVES. Odoo 19's _compute_journal_id
            # is @api.depends('available_journal_ids') (wizard:503) and
            # available_journal_ids is @api.depends('payment_type',
            # 'company_id', 'can_edit_wizard') (:495) — so writing
            # payment_date does NOT retrigger the compute. Neither would it on
            # a v15-shaped port, whose override carries
            # @api.depends('can_edit_wizard', 'company_id')
            # (mmg_default_payment_journal/wizards/
            # account_payment_register.py:7). What the re-read below therefore
            # establishes is the weaker, still-required fact that the
            # hand-picked journal SURVIVES a further edit of the pop-up — the
            # `continue` at wizard:506-507 is what keeps it there whenever the
            # compute does run. The reading that actually discriminates a good
            # port from a v15-shaped one is Expected line 1 (what the pop-up
            # offered before anything was touched) and Expected line 3 (the
            # customer preference), plus the created payment's own journal
            # asserted in the next step, which is what the workbook's step 6
            # literally says to open and read.
            try:
                rpc.call("account.payment.register", "write",
                         [wizard["wizard_id"]],
                         {"payment_date": wizard.get("payment_date")},
                         context=company_ctx(company))
            except OdooRPCError as exc:
                ctx.log(f"re-writing payment_date on the pop-up was refused "
                        f"({exc}) — the keep-my-choice check below still runs "
                        f"against the value as written")
            after = rpc.call("account.payment.register", "read",
                             [wizard["wizard_id"]],
                             fields=["journal_id", "payment_method_line_id"],
                             context=company_ctx(company))[0]
            kept = m2o_id(after.get("journal_id"))
            ctx.log(f"after a further edit the pop-up still shows "
                    f"{labels.get(kept, kept)}")
            evidence.append(
                ("Step 5", "manual choice, pop-up re-read before confirming",
                 labels[journal_1], "(none)", labels.get(kept, str(kept)),
                 m2o_name(after.get("payment_method_line_id")),
                 "PASS" if kept == journal_2 else "FAIL"))

            # EXPECTED RESULT LINE 2, first half — the pop-up itself.
            ctx.check("A journal the accountant chose by hand is still "
                      "showing after the pop-up is edited again — the company "
                      "default did not overwrite it "
                      "(_compute_journal_id keeps an available journal, "
                      "addons/account/wizard/account_payment_register.py:"
                      "506-507)", journal_2, kept)

            try:
                payment_ids = confirm_payment_register(
                    ctx, wizard["wizard_id"], [invoice_a], company=company)
                confirm_error = ""
            except OdooRPCError as exc:
                payment_ids, confirm_error = [], str(exc)
            ctx.check_true(
                "Confirming the pop-up creates exactly one payment for the "
                "one invoice",
                not confirm_error and len(payment_ids) == 1,
                actual_desc=confirm_error or
                f"action_create_payments returned {payment_ids}")

        with ctx.step("Step 6 / Expected line 2: open the payment that was "
                      "created and read its Journal — the important half"):
            payment = payment_row(ctx, payment_ids[0])
            ctx.log(f"payment {payment['name']!r} #{payment['id']} — "
                    f"state={payment['state']!r} "
                    f"amount={payment['amount']:.2f} {payment['currency']} "
                    f"journal={payment['journal']!r} "
                    f"method={payment['method_line']!r}")
            ctx.log(f"RESULT (workbook If It Fails, 2 of 3 — whether the "
                    f"manual choice survived): the created payment is in "
                    f"{payment['journal']!r}; Journal 2 is "
                    f"{labels[journal_2]}")
            evidence.append(
                ("Step 6", "the payment that was actually created",
                 labels[journal_1], "(none)",
                 labels.get(payment["journal_id"], payment["journal"]),
                 payment["method_line"],
                 "PASS" if payment["journal_id"] == journal_2 else "FAIL"))
            if payment["state"] == "posted":
                ctx.log(f"payment #{payment['id']} is POSTED — it is never "
                        f"handed to unlink(), and the workbook's State After "
                        f"The Test expects it to survive ('One invoice paid "
                        f"through Journal 2')")

            # EXPECTED RESULT LINE 2, second half — and the workbook's P1.
            # "A manual choice being overwritten is the serious failure."
            ctx.check("The payment that was created is in Journal 2, the "
                      "journal the accountant chose by hand — the company "
                      "default did NOT overwrite it (account.payment."
                      "journal_id, written from the wizard at "
                      "addons/account/wizard/account_payment_register.py:1073)",
                      journal_2, payment["journal_id"])

            invoice_after = rpc.call(
                "account.move", "read", [invoice_a],
                fields=["payment_state", "amount_residual", "amount_total"],
                context=company_ctx(company))[0]
            ctx.log(f"invoice A payment_state="
                    f"{invoice_after.get('payment_state')!r}, residual="
                    f"{money(invoice_after.get('amount_residual')):.2f} of "
                    f"{money(invoice_after.get('amount_total')):.2f}")
            # The workbook's State After The Test is "One invoice paid through
            # Journal 2" — so the payment must actually have settled the
            # invoice, not merely been created next to it.
            ctx.check("The invoice really was paid by that payment — nothing "
                      "is left outstanding (workbook State After The Test: "
                      "'One invoice paid through Journal 2')",
                      0.00, money(invoice_after.get("amount_residual")))

        with ctx.step("Step 7 / Expected line 3: a customer who has their own "
                      "preferred payment method — that preference wins over "
                      "the company default"):
            # ORDER MATTERS. account.move.preferred_payment_method_line_id is
            # store=True and depends only on ('partner_id', 'company_id')
            # (addons/account/models/account_move.py:513-518, 1533-1539), so a
            # preference written after the invoice exists never reaches it and
            # the case would report a false failure. The partner preference is
            # therefore set FIRST and the invoice created afterwards.
            method_lines = rpc.call(
                "account.journal", "read", [journal_2],
                fields=["inbound_payment_method_line_ids"],
                context=company_ctx(company))[0]
            line_ids = list(
                method_lines.get("inbound_payment_method_line_ids") or [])
            if not line_ids:
                ctx.blocked(
                    f"Journal 2 ({labels[journal_2]}) carries no inbound "
                    f"payment method line, so no customer can express a "
                    f"preference for it and the workbook's step 7 has no "
                    f"subject. This should be impossible — the payment "
                    f"register only offers journals filtered on "
                    f"inbound_payment_method_line_ids (addons/account/wizard/"
                    f"account_payment_register.py:206-207) — so treat it as a "
                    f"data problem on that journal")
            preferred_line = rpc.call(
                "account.payment.method.line", "read", [line_ids[0]],
                fields=["name", "code", "journal_id", "payment_type"],
                context=company_ctx(company))[0]
            preferred_line_id = preferred_line["id"]
            preferred_journal_id = m2o_id(preferred_line.get("journal_id"))
            preferred_label = (f"{preferred_line.get('name')!r} "
                               f"[{preferred_line.get('code')}] on "
                               f"{labels.get(preferred_journal_id, '?')}")
            ctx.log(f"the customer's preferred payment method will be "
                    f"{preferred_label}")

            partner_pref = make_partner(ctx, "INV-006 Preferred Method "
                                             "Customer", company=company)
            created["res.partner"].append(partner_pref)
            try:
                rpc.call("res.partner", "write", [partner_pref],
                         {"property_inbound_payment_method_line_id":
                          preferred_line_id},
                         context=company_ctx(company))
                pref_write_error = ""
            except OdooRPCError as exc:
                pref_write_error = str(exc)
            ctx.check_true(
                "The customer's Preferred Payment Method can be set on their "
                "contact record (res.partner."
                "property_inbound_payment_method_line_id, company_dependent, "
                "addons/account/models/partner.py:623-628)",
                not pref_write_error, actual_desc=pref_write_error or "set")
            stored_pref = m2o_id(rpc.call(
                "res.partner", "read", [partner_pref],
                fields=["property_inbound_payment_method_line_id"],
                context=company_ctx(company))[0].get(
                    "property_inbound_payment_method_line_id"))
            # company_dependent fields are stored as a jsonb dict keyed by
            # company id, so a value that does not read back for THIS company
            # would make every reading below meaningless.
            ctx.check("The contact's Preferred Payment Method reads back for "
                      "this company", preferred_line_id, stored_pref)

            invoice_b = make_invoice(ctx, partner_pref,
                                     [(product_id, 1, 1500.00)],
                                     company=company)
            created["account.move"].append(invoice_b)
            rpc.call("account.move", "action_post", [invoice_b],
                     context=company_ctx(company))
            created["account.move"].remove(invoice_b)   # posted — never unlink

            inherited = m2o_id(rpc.call(
                "account.move", "read", [invoice_b],
                fields=["preferred_payment_method_line_id"],
                context=company_ctx(company))[0].get(
                    "preferred_payment_method_line_id"))
            ctx.check("The invoice picked the customer's preferred payment "
                      "method up from the contact "
                      "(account.move.preferred_payment_method_line_id, "
                      "computed from partner."
                      "property_inbound_payment_method_line_id at "
                      "addons/account/models/account_move.py:1533-1539)",
                      preferred_line_id, inherited)

            # Reading 1 — company default CLEARED. Proves the preference on
            # its own drives the pop-up.
            _set_company_default(ctx, company, False)
            pref_only = _open_pay_popup(ctx, invoice_b, company)
            ctx.check_true("The Pay pop-up opens on the preferred-method "
                           "customer's invoice", not pref_only["error"],
                           actual_desc=pref_only["error"] or "opened")
            seen_pref_only = labels.get(pref_only["journal_id"],
                                        pref_only["journal"])
            evidence.append(
                ("Step 7a", "company default cleared, customer preference set",
                 "(empty)", preferred_label, seen_pref_only,
                 pref_only["method_line"],
                 "PASS" if pref_only["journal_id"] == preferred_journal_id
                 else "FAIL"))
            _discard_popup(ctx, pref_only)
            ctx.check("With no company default at all, the pop-up offers the "
                      "customer's own preferred journal",
                      preferred_journal_id, pref_only["journal_id"])

            # Reading 2 — company default set to Journal 1. THIS is Expected
            # line 3: the default must lose. A v15-shaped port (an
            # unconditional write of company_id.payment_default_journal_id
            # after super(), mmg_default_payment_journal/wizards/
            # account_payment_register.py:11-13) fails exactly here.
            _set_company_default(ctx, company, journal_1)
            with_default = _open_pay_popup(ctx, invoice_b, company)
            ctx.check_true("The Pay pop-up re-opens with the company default "
                           "restored to Journal 1",
                           not with_default["error"],
                           actual_desc=with_default["error"] or "opened")
            seen_with_default = labels.get(with_default["journal_id"],
                                           with_default["journal"])
            ctx.log(f"RESULT (workbook If It Fails, 3 of 3 — what happened "
                    f"with the customer preference): with the company default "
                    f"set to {labels[journal_1]} and the customer preferring "
                    f"{preferred_label}, the pop-up offers "
                    f"{seen_with_default} / method "
                    f"{with_default['method_line']!r}")
            evidence.append(
                ("Step 7b", "company default = Journal 1, customer preference "
                            "set", labels[journal_1], preferred_label,
                 seen_with_default, with_default["method_line"],
                 "PASS" if with_default["journal_id"] == preferred_journal_id
                 else "FAIL"))
            _discard_popup(ctx, with_default)

            # EXPECTED RESULT LINE 3.
            ctx.check("Where the customer has their own preferred payment "
                      "method, that wins over the company default — the "
                      "company default is a FALLBACK in Odoo 19 "
                      "(_compute_journal_id takes the preferred-method branch "
                      "at addons/account/wizard/account_payment_register.py:"
                      "508-510 before it ever reaches the fallback rung)",
                      preferred_journal_id, with_default["journal_id"])
            ctx.check("…and the Payment Method offered is the customer's own "
                      "preferred line, not the journal's first line "
                      "(_compute_payment_method_line_id:565-567)",
                      preferred_line_id, with_default["method_line_id"])

            # The workbook: "record what you saw so the accounting team can be
            # told". Asserted above because the workbook states it as an
            # expectation; ALSO recorded as an observation with the real names
            # so the briefing does not have to be written from a description.
            observation(
                ctx,
                f"DELIBERATE v19 CHANGE, not a defect — with the company "
                f"Default Payment Journal set to {labels[journal_1]}, "
                f"registering a payment for a customer whose contact carries "
                f"Preferred Payment Method {preferred_label} offers "
                f"{seen_with_default}, NOT the company default. In the "
                f"gallery's Odoo 15 the default always won "
                f"(mmg_default_payment_journal/wizards/"
                f"account_payment_register.py:11-13 rewrote journal_id "
                f"unconditionally after super()). Brief the accounting team "
                f"before they test this, or the change will be reported as a "
                f"defect")

        with ctx.step("State After The Test (workbook): put Default Payment "
                      "Journal back to the value written down in step 1 — "
                      "CONFIRM THIS before closing the case"):
            restore_company_value(ctx, company, COMPANY_FIELD,
                                  original_default)
            reread = _read_company_default(ctx, company)
            evidence.append(("State After The Test", "restore of the "
                             "company-wide setting", original_label, "",
                             "", "",
                             "PASS" if reread == original_default else "FAIL"))
            restored_ok = reread == original_default
            ctx.check("Default Payment Journal is back to the value written "
                      "down in step 1 — it is a company-wide setting and "
                      "every future payment reads it",
                      original_default, reread)

            residual.append(
                f"open Accounting > Configuration > Settings on the target "
                f"database and confirm with your own eyes that the Customer "
                f"Invoices block shows Default Payment Journal = "
                f"{original_label}. This case wrote the value onto "
                f"res.company directly, which is exactly what the Save button "
                f"writes (res.config.settings.{COMPANY_FIELD} is a bare "
                f"related field), but only a human can confirm the SCREEN "
                f"agrees with the database.")
            residual.append(
                f"brief the accounting team, using the figures in "
                f"{OFFERS_CSV}: with the company default at "
                f"{labels[journal_1]} a plain customer's payment is offered "
                f"{labels[journal_1]}, while a customer carrying Preferred "
                f"Payment Method {preferred_label} is offered "
                f"{seen_with_default}. The workbook says this change must be "
                f"explained BEFORE they test, or they will raise it as a "
                f"defect.")
            residual.append(
                f"the workbook's State After The Test leaves one invoice paid "
                f"through Journal 2. Invoice #{invoice_a} was paid by payment "
                f"{payment['name']!r} in {payment['journal']!r}, and invoice "
                f"#{invoice_b} for the preferred-method customer is left "
                f"POSTED AND UNPAID because step 7 only reads the pop-up and "
                f"never confirms it. Both are FG07-marked and both are posted, "
                f"so the platform will never delete them — remove them by hand "
                f"if this database is not a throwaway clone.")
    finally:
        with ctx.step("Evidence and restore: write the journal-offer table, "
                      "then make certain the company-wide setting is back"):
            path = ctx.artifacts_dir / OFFERS_CSV
            try:
                with path.open("w", newline="", encoding="utf-8") as handle:
                    writer = csv.writer(handle)
                    writer.writerow(CSV_HEADER)
                    writer.writerows(evidence)
                ctx.add_artifact(path, "log", OFFERS_CSV)
                ctx.log(f"wrote {len(evidence)} row(s) to {OFFERS_CSV}")
            except OSError as exc:
                ctx.log(f"could not write {OFFERS_CSV} ({exc}) — the figures "
                        f"above are still in this log")

            # The safety net. Nothing here may raise (a raise in finally
            # destroys the real FAILED/BLOCKED verdict), so the outcome is
            # LOGGED rather than asserted — the assertion lives on the normal
            # path above. When the try block failed before reaching it, this
            # is the only thing that puts the setting back.
            if company and not restored_ok:
                current = _read_company_default(ctx, company)
                if current == original_default:
                    ctx.log(f"res.company.{COMPANY_FIELD} is already back to "
                            f"{original_default!r} — nothing to restore")
                else:
                    restore_company_value(ctx, company, COMPANY_FIELD,
                                          original_default)
                    confirmed = _read_company_default(ctx, company)
                    if confirmed == original_default:
                        ctx.log(f"res.company.{COMPANY_FIELD} restored to "
                                f"{original_default!r} from the finally block")
                    else:
                        finding(ctx,
                                f"THE COMPANY-WIDE Default Payment Journal WAS "
                                f"NOT RESTORED. res.company.{COMPANY_FIELD} is "
                                f"now {confirmed!r} and the value this case "
                                f"found before it started was "
                                f"{original_default!r}. Every future payment "
                                f"in this database reads it — set it back by "
                                f"hand in Accounting > Configuration > "
                                f"Settings before anyone registers another "
                                f"payment")

            for note in residual:
                residual_manual_step(ctx, note)
            cleanup(ctx, created)
