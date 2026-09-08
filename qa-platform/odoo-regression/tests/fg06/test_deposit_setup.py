"""FG-06 — deposit-account setup: the contact fields and their integrity.

Implements two rows of the CLIENT MANUAL TESTING GUIDELINE
``MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0.xlsx`` / sheet
``Testing Guideline``:

* **TC-DAT-019** (row 16.0, P0, "Deposit setup") — "Deposit accounts on
  contacts survived the upgrade". The workbook marks this READ THIS FIRST
  and says to run it *before any other FG-06 case*, because a blank Deposit
  Account raises no error — it just posts the next deposit to the wrong
  account. Read-only: creates nothing, writes nothing.
* **TC-DEP-003** (row 18.0, P0, "Deposit setup") — "Set a deposit account on
  a contact and have it used". Proves the field survives a reload, that a
  new deposit pre-fills from it, that changing it changes the next deposit,
  and that the customer and vendor sides never cross over.

Why these two are the gate for the whole group
----------------------------------------------
Both per-partner deposit accounts are ``company_dependent=True``
(``account_partner_deposit/models/res_partner.py:6-28``). In Odoo 19 that is
no longer an ``ir.property`` row: the value is stored **as a jsonb dict keyed
by company id on the model's own table** (``odoo/orm/fields.py:127-129,
783``). The v15 → v19 migration of those rows is MS-001, a Phase-2 data
script that lives outside the module (``account_partner_deposit/PORTING.md``
§6), and the PORTING.md states plainly: *"TC-DEP-003 cannot pass in
production without it."* So TC-DAT-019 is the case that catches a migration
that did not run.

How "did this contact keep its own account?" is answered without SQL
-------------------------------------------------------------------
This is the one genuinely subtle thing in the suite, and it is worth stating
because the obvious approaches are all wrong:

* ``read()`` returns the **effective** value, which silently falls back to
  the company default — so a contact that lost its override reads as though
  it still has one.
* A search for ``('property_account_customer_deposit_id', '!=', False)``
  matches **every** partner once a company default exists, because
  ``Field._field_to_sql`` for a company-dependent field resolves to
  ``COALESCE(<jsonb> -> <company>, <fallback>)``
  (``odoo/orm/fields.py:1218-1219``).
* The fallback itself comes from ``ir.default._get_model_defaults()``
  (``odoo/orm/fields.py:794-801``), a **private** method, which Odoo refuses
  to expose over RPC.

The answer used here follows from ``Field.convert_to_column``, which stores
**None** whenever the value written equals the company fallback
(``odoo/orm/fields.py:1000-1005``). An override that equals the default is
therefore not stored at all, which makes the two states identical in every
observable respect. So:

    a contact carries its OWN account  <=>  its effective value differs
                                            from the company fallback

and that is expressible as a plain domain — ``(field, '!=', fallback_id)`` —
evaluated against the same COALESCE expression. The fallback is read from
the ``ir.default`` rows directly (``tests/fg06/common.py::
company_default_deposit_account``), which is where
``res_company.create_or_update_deposit_property`` writes it
(``account_partner_deposit/models/res_company.py:171-177``). No SQL, no
private method, no guess.

Documented adaptation — the Novobi printout (TC-DAT-019)
--------------------------------------------------------
The workbook's Test Data is "Use the Novobi printout … Check at least ten
contacts, including any with a VENDOR deposit account". The platform does not
hold that printout and must not invent one. The adaptation mirrors FG-05's
TC-DAT-017:

* assert every integrity invariant that does **not** need the printout — the
  fields exist and are readable, the Invoicing tab really carries them, the
  company default is set on both sides, and **every** contact-level override
  in the database resolves to an account that exists, is not deprecated,
  carries ``reconcile = True`` and has the account type the field's own
  domain demands. A migrated jsonb value pointing at a missing, archived or
  wrong-type account is exactly the failure the case exists to catch, and it
  is caught here for the whole population rather than for ten samples;
* capture the FULL inventory of contact-level overrides into the execution
  log and into a CSV artifact (``TC-DAT-019-deposit-account-inventory.csv``)
  so the human ticks it off against the printout, and name the remaining
  comparison as a RESIDUAL MANUAL STEP. The evidence step runs from a
  ``finally`` block, so the inventory is produced even when an assertion
  fails — which is exactly when the tester needs it.

The workbook's "no field that should hold a value is blank" cannot be
asserted without the printout — only the printout says which *should*. What
is asserted instead is the strictly stronger, printout-free half: nothing
that does hold a value holds a broken one, and the two sides are counted
separately because the workbook says the vendor half "is the half most often
missed".
"""
from __future__ import annotations

import csv

from adapters.base import OdooRPCError
from framework.registry import test_case
from tests.fg06.common import (CUSTOMER_SIDE, DEPOSIT_ACCOUNT_FIELD,
                               DEPOSIT_ACCOUNT_TYPE, MARK, MODULE, VENDOR_SIDE,
                               WORKFLOW, WORKFLOW_NAME, account_row,
                               acting_company, cleanup,
                               company_default_deposit_account,
                               deposit_accounts_for_test, fields_present,
                               form_defaults, m2o_id, make_deposit,
                               make_partner, onchange_values,
                               partner_deposit_account, payment_row,
                               require_v19, residual_manual_step,
                               set_partner_deposit_account, sweep_fg06, trace)

INVENTORY_CSV = "TC-DAT-019-deposit-account-inventory.csv"

# Rows echoed into the execution log / captured into the CSV per side.
LOG_SAMPLE = 25
CSV_LIMIT = 2000

# The two fields, in the order the Invoicing tab shows them
# (account_partner_deposit/views/res_partner_view.xml:8-11 inserts them after
# property_account_payable_id, inside the "General" group of the "Invoicing"
# page — addons/account/views/partner_view.xml:210-224).
SIDES = (CUSTOMER_SIDE, VENDOR_SIDE)
SIDE_LABEL = {CUSTOMER_SIDE: "Customer Deposit Account",
              VENDOR_SIDE: "Vendor Deposit Account"}


def _partner_form_arch(ctx) -> str:
    """The res.partner form arch as v19 serves it (``get_view``).

    v15's ``fields_view_get`` was removed; ``framework.fg_common.form_arch``
    handles the split, but this suite is v19-only so the v19 call is made
    directly and any failure is reported rather than swallowed.
    """
    return ctx.adapter.rpc.call("res.partner", "get_view",
                                view_type="form")["arch"]


def _override_partners(ctx, side: str, company: dict, fallback: dict) -> list:
    """Every contact carrying its OWN deposit account for this company.

    See the module docstring for why ``!= fallback_id`` is the correct — and
    the only RPC-expressible — formulation.
    """
    field_name = DEPOSIT_ACCOUNT_FIELD[side]
    fallback_id = fallback.get("id") or False
    return ctx.adapter.rpc.call(
        "res.partner", "search_read",
        [(field_name, "!=", fallback_id)],
        fields=["display_name", field_name, "is_company", "parent_id",
                "active"],
        order="id",
        context={"allowed_company_ids": [company["id"]],
                 "company_id": company["id"], "active_test": False})


@test_case(
    id="TEST-FG06-DAT-019",
    name="Deposit accounts on contacts survived the upgrade",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P0",
    kind="DATA",
    order=600,
    description="Read-only FG-06 setup gate: both company_dependent deposit "
                "account fields exist and are readable, the Invoicing tab "
                "carries them, the company-level default is set on both "
                "sides, and every contact-level override in the database "
                "resolves to an account that exists, is not deprecated, is "
                "reconcilable and has the right account type. Creates "
                "nothing.",
    traceability=trace("TC-DAT-019"))
def test_dat_019(ctx):
    rpc = ctx.adapter.rpc
    evidence = []      # (side, partner, account code/name, verdict) -> CSV
    residual = []

    with ctx.step("Precondition (workbook): Odoo 19 with "
                  "account_partner_deposit installed, and the Invoicing tab "
                  "visible on a contact"):
        require_v19(ctx)
        company = acting_company(ctx)
        ctx.log(f"acting company #{company['id']} {company['name']!r} — "
                f"currency {company['currency_name']}, chart_template="
                f"{company['chart_template']!r}")
        present = fields_present(rpc, "res.partner",
                                 list(DEPOSIT_ACCOUNT_FIELD.values()))
        ctx.check("Both deposit-account fields are readable on res.partner",
                  [], [f for f in DEPOSIT_ACCOUNT_FIELD.values()
                       if f not in present])

    try:
        with ctx.step("Workbook steps 1-2: the Invoicing tab, General group, "
                      "really carries both fields"):
            # The workbook's navigation path IS part of the expectation: a
            # value that survived the upgrade but has no screen cannot be
            # ticked off against the printout.
            try:
                arch = _partner_form_arch(ctx)
            except OdooRPCError as exc:
                arch = ""
                ctx.log(f"could not fetch the res.partner form arch ({exc})")
            missing_in_view = [f for f in DEPOSIT_ACCOUNT_FIELD.values()
                               if f'name="{f}"' not in arch]
            ctx.check_true(
                "The contact form shows Customer Deposit Account and Vendor "
                "Deposit Account (account_partner_deposit."
                "view_partner_deposit_form, inserted after "
                "property_account_payable_id in the Invoicing tab's General "
                "group)",
                not missing_in_view and bool(arch),
                actual_desc=(f"fields absent from the combined form arch: "
                             f"{missing_in_view}" if arch
                             else "the form arch could not be read"))

        with ctx.step("Workbook step 5 (adapted): the company-level default "
                      "behind both fields is set"):
            # If MS-001 never ran, every contact silently falls back to this
            # value. An unset default plus a lost override means the next
            # deposit has no account at all and create() raises
            # 'Deposit account has not been set'
            # (account_partner_deposit/models/account_payment.py:60-64).
            defaults = {}
            for side in SIDES:
                defaults[side] = company_default_deposit_account(
                    ctx, side, company["id"])
                row = defaults[side]
                ctx.log(f"company default for {SIDE_LABEL[side]}: "
                        f"{(row.get('code') or '(none)')} "
                        f"{row.get('name') or ''!r} "
                        f"(ir.default scope company="
                        f"{row.get('scope_company_id')})")
                evidence.append((side, "(company default)",
                                 row.get("code") or "",
                                 row.get("name") or "",
                                 "set" if row.get("id") else "NOT SET"))
            for side in SIDES:
                ctx.check_true(
                    f"A company-level default exists for {SIDE_LABEL[side]} "
                    f"(ir.default on res.partner."
                    f"{DEPOSIT_ACCOUNT_FIELD[side]})",
                    bool(defaults[side].get("id")),
                    actual_desc=(f"ir.default row for company "
                                 f"#{company['id']}: "
                                 f"{defaults[side].get('code') or 'ABSENT'}"))

        with ctx.step("Workbook steps 3-4 (adapted to the whole population): "
                      "every contact-level override resolves to a usable "
                      "account"):
            broken = []
            counts = {}
            for side in SIDES:
                field_name = DEPOSIT_ACCOUNT_FIELD[side]
                wanted_type = DEPOSIT_ACCOUNT_TYPE[side]
                rows = _override_partners(ctx, side, company, defaults[side])
                counts[side] = len(rows)
                fixtures = sum(1 for r in rows
                               if (r.get("display_name") or "").startswith(
                                   f"{MARK} "))
                ctx.log(f"{SIDE_LABEL[side]}: {len(rows)} contact(s) carry "
                        f"their own account (of which {fixtures} are FG06 "
                        f"test fixtures)")
                seen_accounts = {}
                for index, row in enumerate(rows):
                    account_id = m2o_id(row.get(field_name))
                    if account_id not in seen_accounts:
                        seen_accounts[account_id] = account_row(ctx,
                                                                account_id)
                    account = seen_accounts[account_id]
                    problems = []
                    if not account.get("id"):
                        problems.append("the account no longer exists")
                    else:
                        if account.get("deprecated"):
                            problems.append("the account is deprecated")
                        if not account.get("reconcile"):
                            problems.append("reconcile is off, so the "
                                            "deposit could never be applied")
                        if account.get("account_type") != wanted_type:
                            problems.append(
                                f"account_type is "
                                f"{account.get('account_type')!r}, not "
                                f"{wanted_type!r}, so the field's own domain "
                                f"rejects it")
                    verdict = "; ".join(problems) or "ok"
                    if problems:
                        broken.append(
                            f"{SIDE_LABEL[side]} on "
                            f"{row.get('display_name')!r} (partner "
                            f"#{row['id']}) -> account "
                            f"{account.get('code') or account_id}: {verdict}")
                    if index < LOG_SAMPLE:
                        ctx.log(f"  {row.get('display_name')!r} -> "
                                f"{account.get('code', '')} "
                                f"{account.get('name', '')!r} [{verdict}]")
                    if len(evidence) < CSV_LIMIT:
                        evidence.append((side, row.get("display_name") or "",
                                         account.get("code", ""),
                                         account.get("name", ""), verdict))
                if len(rows) > LOG_SAMPLE:
                    ctx.log(f"  … {len(rows) - LOG_SAMPLE} more in "
                            f"{INVENTORY_CSV}")

            # THE assertion of this case: nothing that holds a value holds a
            # broken one. Reported as a list so the evidence names every
            # offender rather than only the first.
            ctx.check("Every contact-level deposit-account override resolves "
                      "to an existing, non-deprecated, reconcilable account "
                      "of the right type", [], broken)

        with ctx.step("Workbook Test Data: the VENDOR side — 'the half most "
                      "often missed'"):
            # Not an assertion that a number is non-zero: a database may
            # legitimately have no vendor deposits at all, and failing that
            # would be inventing a requirement the workbook does not state.
            # It IS recorded, loudly, because a zero here against a printout
            # that lists vendor accounts is the finding.
            ctx.log(f"override counts — customer side: "
                    f"{counts[CUSTOMER_SIDE]}, vendor side: "
                    f"{counts[VENDOR_SIDE]}")
            if not counts[VENDOR_SIDE]:
                residual.append(
                    "NO contact in this database carries its own Vendor "
                    "Deposit Account. If the Novobi printout lists ANY "
                    "vendor deposit account, that is a migration failure of "
                    "the whole vendor half (MS-001) and must be raised as a "
                    "P0 — the workbook calls this 'the half most often "
                    "missed'. If the printout lists none, this is correct "
                    "and the case passes.")
            residual.append(
                f"tick the {counts[CUSTOMER_SIDE]} customer-side and "
                f"{counts[VENDOR_SIDE]} vendor-side override(s) in "
                f"{INVENTORY_CSV} off against the Novobi printout, contact by "
                f"contact and code by code. The platform does not hold the "
                f"printout, so 'the same account code it had in the old "
                f"system' and 'no field that should hold a value is blank' "
                f"are the two lines only a human can settle. Separate the "
                f"two failure shapes the workbook names: 'the contact lost "
                f"its link' (the contact now falls back to the company "
                f"default, so it is absent from the CSV) versus 'the account "
                f"no longer exists' (it is in the CSV with a verdict other "
                f"than ok). Do NOT re-type any value — hand-typing hides the "
                f"size of the problem and the migration would need re-running "
                f"anyway.")
    finally:
        with ctx.step("Evidence: write the deposit-account inventory for the "
                      "printout tick-off"):
            path = ctx.artifacts_dir / INVENTORY_CSV
            try:
                with path.open("w", newline="", encoding="utf-8") as handle:
                    writer = csv.writer(handle)
                    writer.writerow(["side", "contact", "account_code",
                                     "account_name", "verdict"])
                    writer.writerows(evidence)
                ctx.add_artifact(path, "log", INVENTORY_CSV)
                ctx.log(f"wrote {len(evidence)} inventory row(s) to "
                        f"{INVENTORY_CSV}")
            except OSError as exc:
                ctx.log(f"could not write {INVENTORY_CSV} ({exc}) — the "
                        f"inventory above is still in this log")
            for note in residual:
                residual_manual_step(ctx, note)
            ctx.log("NOTHING WAS CREATED OR MODIFIED by this case — the "
                    "workbook's State After The Test is 'Nothing changed. Do "
                    "not correct any value in this case.', so no sweep and no "
                    "cleanup runs here either (a sweep is itself a delete).")


@test_case(
    id="TEST-FG06-DEP-003",
    name="Set a deposit account on a contact and have it used",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P0",
    kind="API",
    order=602,
    description="A contact's Customer Deposit Account survives a reload, a "
                "new deposit pre-fills from it, changing it changes the next "
                "deposit, and a vendor deposit pre-fills the VENDOR account "
                "— the two sides never cross over.",
    traceability=trace("TC-DEP-003"))
def test_dep_003(ctx):
    created = {"account.payment": [], "res.partner": []}
    with ctx.step("Precondition (workbook): two liability accounts suitable "
                  "for customer deposits, and an editable contact"):
        require_v19(ctx)
        company = acting_company(ctx)
        sweep_fg06(ctx)
        # Workbook Test Data: "Account A and Account B: two different
        # customer-deposit liability accounts". Real ones are used where the
        # database has two; see common.deposit_accounts_for_test.
        customer_accounts = deposit_accounts_for_test(
            ctx, CUSTOMER_SIDE, company["id"], wanted=2)
        vendor_accounts = deposit_accounts_for_test(
            ctx, VENDOR_SIDE, company["id"], wanted=1)
        account_a, account_b = customer_accounts[0], customer_accounts[1]
        vendor_account = vendor_accounts[0]
        ctx.check_true(
            "Account A and Account B are two DIFFERENT customer-deposit "
            "accounts (workbook Test Data)",
            account_a["id"] != account_b["id"],
            actual_desc=f"A = {account_a['code']} {account_a['name']!r}, "
                        f"B = {account_b['code']} {account_b['name']!r}")
        ctx.log(f"vendor account = {vendor_account['code']} "
                f"{vendor_account['name']!r} "
                f"({DEPOSIT_ACCOUNT_TYPE[VENDOR_SIDE]})")

    try:
        with ctx.step("Steps 1-2: create 'UAT Deposit Contact' as a Company "
                      "and set Customer Deposit Account to Account A"):
            partner_id = make_partner(ctx, "UAT Deposit Contact",
                                      company=company, is_company=True)
            created["res.partner"].append(partner_id)
            set_partner_deposit_account(ctx, partner_id, CUSTOMER_SIDE,
                                        account_a["id"], company["id"])

        with ctx.step("Step 3 / Expected line 1: reload the contact — "
                      "Account A is still there, it did not silently drop"):
            # This is the company_dependent jsonb round-trip. Each RPC call is
            # its own transaction, so this read genuinely goes back to the
            # database rather than to a warm cache — which is what "reload the
            # page" means.
            stored = partner_deposit_account(ctx, partner_id, CUSTOMER_SIDE,
                                             company["id"])
            ctx.check("Customer Deposit Account on the contact after a reload",
                      account_a["id"], stored.get("id"))

        with ctx.step("Steps 4-5 / Expected line 2: a new customer deposit "
                      "pre-fills Deposit Account with Account A"):
            # The workbook's step is "Customer Deposits > New, set Customer".
            # That is the deposit action's context plus the partner_id
            # onchange — account_partner_deposit.account_payment.
            # _update_default_deposit_account (models/account_payment.py:44-52),
            # which is what fills the field on screen. It does NOT run on a
            # create() over RPC, so it is exercised here through the same
            # onchange call the form view makes.
            deposit_context = {
                "default_payment_type": "inbound",
                "default_partner_type": "customer",
                "default_is_deposit": 1,
                "allowed_company_ids": [company["id"]],
                "company_id": company["id"],
            }
            names = ("is_deposit", "partner_id", "partner_type",
                     "payment_type", "amount", "currency_id", "journal_id",
                     "property_account_customer_deposit_id",
                     "property_account_vendor_deposit_id")
            blank = form_defaults(ctx, "account.payment", names,
                                  deposit_context)
            after_a = onchange_values(
                ctx, "account.payment",
                {**blank, "partner_id": partner_id}, ["partner_id"], names,
                context=deposit_context)
            filled_a = m2o_id(
                after_a.get("property_account_customer_deposit_id"))
            ctx.check("Deposit Account pre-filled on a new customer deposit "
                      "after setting Customer (the partner_id onchange)",
                      account_a["id"], filled_a)

        with ctx.step("Steps 6-8 / Expected line 3: change the contact to "
                      "Account B — the next deposit pre-fills with B"):
            set_partner_deposit_account(ctx, partner_id, CUSTOMER_SIDE,
                                        account_b["id"], company["id"])
            reread = partner_deposit_account(ctx, partner_id, CUSTOMER_SIDE,
                                            company["id"])
            ctx.check("Customer Deposit Account on the contact after the "
                      "change", account_b["id"], reread.get("id"))
            after_b = onchange_values(
                ctx, "account.payment",
                {**blank, "partner_id": partner_id}, ["partner_id"], names,
                context=deposit_context)
            ctx.check("Deposit Account pre-filled on a new customer deposit "
                      "after the change", account_b["id"],
                      m2o_id(after_b.get(
                          "property_account_customer_deposit_id")))

        with ctx.step("Steps 9-10 / Expected line 4: a VENDOR deposit "
                      "pre-fills the VENDOR account — the two sides must not "
                      "cross over"):
            set_partner_deposit_account(ctx, partner_id, VENDOR_SIDE,
                                        vendor_account["id"], company["id"])
            vendor_context = {
                "default_payment_type": "outbound",
                "default_partner_type": "supplier",
                "default_is_deposit": 1,
                "allowed_company_ids": [company["id"]],
                "company_id": company["id"],
            }
            vendor_blank = form_defaults(ctx, "account.payment", names,
                                        vendor_context)
            vendor_after = onchange_values(
                ctx, "account.payment",
                {**vendor_blank, "partner_id": partner_id}, ["partner_id"],
                names, context=vendor_context)
            filled_vendor = m2o_id(
                vendor_after.get("property_account_vendor_deposit_id"))
            crossed = m2o_id(
                vendor_after.get("property_account_customer_deposit_id"))
            ctx.check("Deposit Account on a new VENDOR deposit is the vendor "
                      "account", vendor_account["id"], filled_vendor)
            # The workbook's If It Fails calls this the most serious version
            # and a P0: the customer account on a vendor deposit posts vendor
            # prepayments into a customer liability account. The onchange
            # branches on partner_type (models/account_payment.py:48-51), so
            # the customer field must stay untouched on the supplier side.
            ctx.check("The CUSTOMER deposit account is not applied to a "
                      "vendor deposit (the two sides are separate fields and "
                      "must not cross over)", None, crossed)

        with ctx.step("Expected line 4, proven end to end: a real vendor "
                      "deposit books to the vendor account"):
            # The onchange above proves the screen; this proves the posting.
            # Without it, a correct pre-fill that the create path then ignores
            # would still pass.
            vendor_deposit_id = make_deposit(
                ctx, partner_id, 100.00, account_id=vendor_account["id"],
                side=VENDOR_SIDE)
            created["account.payment"].append(vendor_deposit_id)
            row = payment_row(ctx, vendor_deposit_id)
            ctx.check("The vendor deposit carries the vendor deposit account",
                      vendor_account["id"], row["vendor_deposit_account_id"])
            ctx.check("…and no customer deposit account", None,
                      row["customer_deposit_account_id"])
            ctx.log("workbook State After The Test says to KEEP 'UAT Deposit "
                    "Contact' with Account B and a vendor deposit account. "
                    "The platform forbids depending on another test's "
                    "fixtures (AUTOMATION_CONVENTIONS rule 5), so every later "
                    "FG-06 case builds its own contact and this one is swept "
                    "— the end state is reproduced, never inherited.")
    finally:
        with ctx.step("Cleanup: remove FG06 fixtures"):
            cleanup(ctx, created)
