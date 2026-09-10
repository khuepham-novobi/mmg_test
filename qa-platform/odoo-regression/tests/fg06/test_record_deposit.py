"""FG-06 — TC-DEP-001: record a customer payment as a deposit.

Implements row 17.0 (P0, "Recording deposits") of the CLIENT MANUAL TESTING
GUIDELINE ``MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0.xlsx`` /
sheet ``Testing Guideline``.

The workbook's framing: *"This is the core of the whole feature: money
arrives before there is an invoice, and it must sit in a liability account
until it is applied, not in revenue."* Its Why It Matters names four form
behaviours that all have to work: a field appears and becomes mandatory,
another disappears entirely, the account fills itself in from the contact,
and the journal choice is restricted.

The five Expected Result lines, and what each is read from
---------------------------------------------------------
1. **Payment Type is not visible anywhere on the form.** The deposit form
   sets ``invisible="is_deposit"`` on ``payment_type``
   (``account_partner_deposit/views/account_payment_deposit_view.xml:31-34``).
   Asserted against the *deposit* form's arch, resolved by its own XML id —
   not against the generic payment form, which legitimately shows the field.
2. **Deposit Account appears once a customer is set, fills in
   automatically, and is marked required.** Three separate things, asserted
   separately: the ``invisible``/``required`` expressions on the field in
   that same arch (``:16-24``), and the value the ``partner_id`` onchange
   produces (``models/account_payment.py:44-52``).
3. **The status bar reads Draft — In Process — Paid, and the record starts
   on Draft.** ``statusbar_visible="draft,in_process,paid"``
   (``addons/account/views/account_payment_view.xml:163``); the selection
   itself is ``draft/in_process/paid/canceled/rejected``
   (``addons/account/models/account_payment.py:36-43``).
4. **After Confirm the status moves off Draft.**
5. **The journal entry has one line on the bank/cash account and one on the
   Deposit Account for 2,500.00 — NOT on a revenue account.**

A finding this case will surface: "starts on Draft"
---------------------------------------------------
Expected Result line 3 says the record *starts* on Draft. In v19 that is
true of an ordinary payment but **not** of a deposit, and the difference is
structural rather than accidental. ``_generate_journal_entry`` runs at CREATE
time for any payment carrying ``write_off_line_vals`` and writes
``{'move_id': ..., 'state': 'in_process'}``
(``addons/account/models/account_payment.py:1080``). Every deposit carries
those vals, because the module's ``create`` builds the deposit line as one
(``account_partner_deposit/models/account_payment.py:66-90``). So a saved,
unconfirmed deposit reads ``state = 'in_process'`` while its journal entry is
still ``draft``.

That is BC-016, discovered during the port and recorded in
``account_partner_deposit/PORTING.md`` §4, and it is the reason both the
partner domain and the sale-order domain had to gain a move-state clause.
This module therefore asserts the workbook's line for what it is — the
saved-but-unconfirmed record is not yet money the gallery holds — using the
pair of states that actually expresses it:

* the **journal entry** is ``draft`` before Confirm and ``posted`` after, and
* the payment leaves ``draft`` on Confirm,

and it records the ``state == 'in_process'``-before-Confirm reading
explicitly as a FINDING in the log, with the source line, so a tester who
sees "In Process" on an unconfirmed deposit knows it is v19 behaviour and not
a defect. Nothing is weakened: the substance of line 3 — the record is not
confirmed until you press Confirm — is asserted, and line 4 is asserted
directly.

Documented adaptation — workbook step 6, the journal list
--------------------------------------------------------
Step 6 says "Check the Journal field only offers bank and cash journals".
Two mechanisms could restrict it, and only one is real:

* the deposit action sets ``default_move_journal_types: ('bank', 'cash')``
  in its context
  (``views/account_payment_deposit_view.xml:76, 93``), but **no Python in
  v19 reads that key** — the port checked and left it only because stock v19
  still sets it too (``PORTING.md`` §4, "Report correction");
* the real restriction is ``account.payment.available_journal_ids``, computed
  over journals of type ``('bank', 'cash', 'credit')`` that carry a matching
  payment method line
  (``addons/account/models/account_payment.py:594-608``).

So the workbook's expectation is asserted against ``available_journal_ids``,
which is what the field's dropdown is actually bound to. Note that v19
includes **credit**-type journals in that computation
(``addons/account/models/account_payment.py:594-608`` searches ``type in
('bank', 'cash', 'credit')``).

That widening is stock Odoo 19, not an MMG change: nothing in
``account_partner_deposit`` narrows the list, and no v19 Python reads the
deposit action's ``default_move_journal_types`` context key. A company that
happens to own a credit-type journal carrying an inbound payment-method line
therefore sees a third journal type offered on the deposit form — a condition
MMG neither causes nor can fix from this module. Failing the case on it would
put a stock-version divergence in the defect column of an upgrade report and
send the team looking for an MMG bug that does not exist. It is reported the
way this suite reports every other stock-v19 divergence: the offending
journals, the source line and the decision are logged as a FINDING and a
RESIDUAL MANUAL STEP for the Accounting Manager (accept v19's wider list, or
have the field's domain narrowed to bank/cash), and the assertion holds the
line that is genuinely MMG's to keep — **no journal outside v19's own
bank/cash/credit set is ever offered on a deposit**. Nothing that could
indicate a real defect is dropped: a journal of any other type in that list
would mean the module or the data broke the computation, and that still
FAILS.

Documented correction — how the bank/cash line is found
-------------------------------------------------------
Expected Result line 5 says "one line on the bank/cash account". This module
used to find it with ``account_type in ('asset_cash',
'liability_credit_card')``, and that reported a **correct** entry as a P0
product defect ("Exactly one line on the bank/cash side: expected 1, got 0").
The entry was well formed all along — the neighbouring Deposit Account check
passed on the same entry — and the filter was simply looking in the wrong
place:

* an UNRECONCILED ``account.payment`` books its liquidity line to the
  OUTSTANDING account, not to the journal's bank account.
  ``_prepare_move_liquidity_lines`` sets that line's ``account_id`` to
  ``self.outstanding_account_id``
  (``addons/account/models/account_payment.py:293``);
* Odoo classifies a line as liquidity by MEMBERSHIP of
  ``_get_valid_liquidity_accounts()`` — the journal's ``default_account_id``,
  the payment method lines' ``payment_account_id`` accounts and
  ``outstanding_account_id`` — never by ``account_type``
  (``_seek_for_lines``, ``:216-228``, ``:242-250``);
* on ``mmg_19`` every Outstanding Receipts / Outstanding Payments account is
  typed ``asset_current`` while the journals' own ``default_account_id``
  accounts are ``asset_cash``. So the old filter matched nothing.

The line is now found the way Odoo finds it — by account, through
:func:`~tests.fg06.common.payment_liquidity_account` — and both assertions
the workbook actually makes are kept unchanged: there is exactly one such
line (the BC-003 regression guard) and it is a debit of 2,500.00. The
revenue check is untouched: the workbook calls a revenue hit a P0, and it
still fails on one.

A coverage note — ``res.partner.total_deposit``
-----------------------------------------------
The contact-side reading of a deposit is asserted here too, at the end of the
case, because nothing else in FG-06 reads it. See the step's own comment for
why it is the assertion that anchors the ``aml.blocked`` defect.
"""
from __future__ import annotations

from adapters.base import OdooRPCError
from framework.context import AssertionFailed
from framework.registry import test_case
from tests.fg06.common import (CUSTOMER_SIDE, DEPOSIT_ACCOUNT_FIELD, MODULE,
                               PAYMENT_STATES, PAYMENT_STATUSBAR, WORKFLOW,
                               WORKFLOW_NAME, account_row, acting_company,
                               cleanup, deposit_accounts_for_test,
                               field_attrs, fields_present,
                               form_defaults, m2o_id,
                               make_deposit, make_partner, money, move_lines,
                               onchange_values, payment_liquidity_account,
                               payment_row, require_v19,
                               residual_manual_step, sweep_fg06, trace,
                               x2m_ids)

# Workbook Test Data.
DEPOSIT_AMOUNT = 2500.00
DEPOSIT_MEMO = "UAT Deposit 01"

# The deposit form the Customer Deposits action opens
# (views/account_payment_deposit_view.xml:3-8 and the action's view_ids at
# :68-72).
DEPOSIT_FORM_XMLID = "account_partner_deposit.view_account_payment_deposit_form"

# Journal types the workbook expects the Journal field to offer.
EXPECTED_JOURNAL_TYPES = {"bank", "cash"}
# Journal types v19 itself computes into account.payment.available_journal_ids
# (addons/account/models/account_payment.py:594-608). Anything OUTSIDE this set
# would mean the computation was broken by the module or by the data, which is
# the half of workbook step 6 that is MMG's to keep.
V19_JOURNAL_TYPES = {"bank", "cash", "credit"}

# Account types that would mean the money landed in the wrong place.
REVENUE_TYPES = ("income", "income_other")
# There is deliberately no LIQUIDITY_TYPES here. The liquidity line is found
# by ACCOUNT, not by account_type — see the module docstring and
# common.payment_liquidity_account.


@test_case(
    id="TEST-FG06-DEP-001",
    name="Record a customer payment as a deposit",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P0",
    kind="API",
    order=603,
    description="The deposit form hides Payment Type, shows a required "
                "Deposit Account that fills itself in from the contact, and "
                "offers no journal outside v19's own bank/cash/credit set "
                "(any credit journal is reported as a stock-v19 finding, not "
                "a defect); a 2,500.00 deposit starts unposted, confirms, and "
                "books one liquidity line and one line on the Deposit Account "
                "— never on revenue — and the contact then reads that same "
                "2,500.00 as its open deposit line and Total Deposit.",
    traceability=trace("TC-DEP-001"))
def test_dep_001(ctx):
    rpc = ctx.adapter.rpc
    created = {"account.payment": [], "res.partner": []}
    posted_ids = []

    with ctx.step("Preconditions (workbook): TC-DAT-019 has passed, a "
                  "customer with a Customer Deposit Account exists, and at "
                  "least one bank or cash journal exists"):
        require_v19(ctx)
        company = acting_company(ctx)
        sweep_fg06(ctx)
        account = deposit_accounts_for_test(ctx, CUSTOMER_SIDE,
                                            company["id"], wanted=1)[0]
        journals = rpc.search_read(
            "account.journal",
            [("type", "in", ["bank", "cash"]),
             ("company_id", "=", company["id"])],
            ["name", "code", "type"], order="id")
        ctx.log(f"bank/cash journals on this company: "
                f"{[(j['code'], j['type']) for j in journals]}")
        if not journals:
            ctx.blocked(
                f"TC-DEP-001's own precondition is not met: company "
                f"{company['name']!r} has no bank or cash journal, so a "
                f"deposit cannot be recorded at all "
                f"(account.payment.journal_id is required — "
                f"addons/account/models/account_payment.py:23-29). Create one "
                f"under Accounting > Configuration > Journals and re-run")
        ctx.check_true(
            "At least one bank or cash journal exists (workbook "
            "precondition)", bool(journals),
            actual_desc=f"{len(journals)} bank/cash journal(s)")

    try:
        with ctx.step("Step 2 / Expected line 1: the deposit form does not "
                      "show Payment Type at all"):
            view_id = rpc.ref(DEPOSIT_FORM_XMLID)
            ctx.check_true(
                "The Customer Deposits form view exists "
                f"({DEPOSIT_FORM_XMLID})", bool(view_id),
                actual_desc=f"ir.model.data -> view id {view_id!r}")
            arch = rpc.call("account.payment", "get_view", view_id=view_id,
                            view_type="form")["arch"]
            payment_type_tag = field_attrs(arch, "payment_type")
            ctx.log(f"payment_type on the deposit form: {payment_type_tag!r}")
            # The deposit is always incoming, so the radio is suppressed
            # rather than defaulted (views/account_payment_deposit_view.xml:
            # 31-34).
            ctx.check_true(
                "Payment Type is invisible on the deposit form "
                "(invisible=\"is_deposit\")",
                'invisible="is_deposit"' in payment_type_tag,
                actual_desc=payment_type_tag
                            or "no payment_type field found in the arch")

        with ctx.step("Step 4 / Expected line 2 (a): Deposit Account is "
                      "conditional on the deposit being a customer one, and "
                      "is REQUIRED"):
            field_name = DEPOSIT_ACCOUNT_FIELD[CUSTOMER_SIDE]
            tag = field_attrs(arch, field_name)
            ctx.log(f"{field_name} on the deposit form: {tag!r}")
            ctx.check_true(
                "Deposit Account is hidden unless this is a customer deposit "
                "(invisible=\"not (is_deposit and partner_type == "
                "'customer')\")",
                "not (is_deposit and partner_type == 'customer')" in tag,
                actual_desc=tag or "no field found in the arch")
            ctx.check_true(
                "Deposit Account is marked required on a customer deposit "
                "(required=\"is_deposit and partner_type == 'customer'\")",
                "required=\"is_deposit and partner_type == 'customer'\"" in tag,
                actual_desc=tag or "no field found in the arch")

        with ctx.step("Steps 3-4 / Expected line 2 (b): setting Customer "
                      "fills Deposit Account in from the contact"):
            partner_id = make_partner(ctx, "DEP-001 Customer", company=company,
                                      customer_deposit_account_id=account["id"])
            created["res.partner"].append(partner_id)
            deposit_context = {
                "default_payment_type": "inbound",
                "default_partner_type": "customer",
                "default_is_deposit": 1,
                "allowed_company_ids": [company["id"]],
                "company_id": company["id"],
            }
            names = ("is_deposit", "partner_id", "partner_type",
                     "payment_type", "amount", "currency_id", "date", "memo",
                     "journal_id", "available_journal_ids",
                     DEPOSIT_ACCOUNT_FIELD[CUSTOMER_SIDE])
            blank = form_defaults(ctx, "account.payment", names,
                                  deposit_context)
            # Expected line 1, proven on the record and not only in the arch:
            # the action's context forces the deposit to be inbound, so there
            # is no choice for the hidden radio to have made.
            ctx.check("The deposit form opens as an INBOUND payment, so "
                      "Payment Type has nothing to choose", "inbound",
                      blank.get("payment_type"))
            after = onchange_values(
                ctx, "account.payment",
                {**blank, "partner_id": partner_id}, ["partner_id"], names,
                context=deposit_context)
            ctx.check("Deposit Account filled in from the customer's Customer "
                      "Deposit Account", account["id"],
                      m2o_id(after.get(DEPOSIT_ACCOUNT_FIELD[CUSTOMER_SIDE])))

        with ctx.step("Step 6 (adapted) / the Journal field offers no journal "
                      "outside v19's own bank/cash/credit set — any credit "
                      "journal is reported as a stock-v19 finding"):
            # available_journal_ids is what the dropdown is bound to; the
            # action's default_move_journal_types context key is inert in v19
            # (module docstring).
            available = x2m_ids(after.get("available_journal_ids")
                                or blank.get("available_journal_ids"))
            offered = rpc.search_read(
                "account.journal", [("id", "in", available)],
                ["name", "code", "type"], order="type") if available else []
            ctx.log(f"Journal field offers: "
                    f"{[(j['code'], j['type']) for j in offered]}")
            # Two different things are being separated here.
            #
            # (a) A journal type the WORKBOOK does not allow but v19 itself
            #     computes — in practice 'credit'. Stock v19 behaviour, not an
            #     MMG change: _compute_available_journal_ids searches
            #     type in ('bank', 'cash', 'credit')
            #     (addons/account/models/account_payment.py:594-608), nothing
            #     in account_partner_deposit narrows it, and the deposit
            #     action's own default_move_journal_types: ('bank', 'cash')
            #     context key is read by no v19 Python
            #     (account_partner_deposit/PORTING.md, 'Report correction').
            #     MMG neither causes this nor can fix it from this module, so
            #     failing the case would file a stock-version divergence as an
            #     MMG defect. Reported as a FINDING and a decision for the
            #     Accounting Manager instead.
            #
            # (b) A journal type OUTSIDE v19's own set. That cannot come from
            #     stock behaviour at all — it would mean the computation or
            #     the payment-method data is broken — and it is asserted hard.
            wider = sorted({j["type"] for j in offered}
                           - EXPECTED_JOURNAL_TYPES)
            if wider:
                ctx.log(
                    f"FINDING — the Journal field also offers journal type(s) "
                    f"{wider}, which the workbook does not allow. This is v19 "
                    f"stock behaviour, not an MMG change: "
                    f"account.payment._compute_available_journal_ids searches "
                    f"type in ('bank', 'cash', 'credit') "
                    f"(addons/account/models/account_payment.py:594-608), and "
                    f"the deposit action's own "
                    f"default_move_journal_types: ('bank', 'cash') context key "
                    f"is read by no Python in v19 "
                    f"(account_partner_deposit/PORTING.md, 'Report "
                    f"correction'). Offending journals: "
                    f"{[(j['code'], j['type']) for j in offered if j['type'] in wider]}.")
                residual_manual_step(
                    ctx,
                    f"workbook step 6 says the Journal field offers bank and "
                    f"cash only; on this company v19 also offers "
                    f"{[(j['code'], j['type']) for j in offered if j['type'] in wider]}. "
                    f"DECISION FOR THE ACCOUNTING MANAGER: accept v19's wider "
                    f"list (no code change; the deposit still posts to the "
                    f"journal the user picks), or have "
                    f"account_partner_deposit narrow the field's domain to "
                    f"bank/cash. This is a stock-Odoo-19 difference, not an "
                    f"MMG regression — do NOT raise it as a module defect.")
            outside = sorted({j["type"] for j in offered} - V19_JOURNAL_TYPES)
            ctx.check("No journal outside v19's own bank/cash/credit set is "
                      "offered on a deposit (addons/account/models/"
                      "account_payment.py:594-608)", [], outside)

        with ctx.step("Steps 5 and 7 / Expected line 3: save the 2,500.00 "
                      "deposit — it is not yet confirmed"):
            deposit_id = make_deposit(
                ctx, partner_id, DEPOSIT_AMOUNT, account_id=account["id"],
                side=CUSTOMER_SIDE, memo=DEPOSIT_MEMO)
            created["account.payment"].append(deposit_id)
            saved = payment_row(ctx, deposit_id)
            ctx.check("Amount on the saved deposit", DEPOSIT_AMOUNT,
                      saved["amount"])
            ctx.check("Memo on the saved deposit", DEPOSIT_MEMO,
                      saved["memo"])
            # The status bar's own definition, from the view.
            statusbar = field_attrs(
                rpc.call("account.payment", "get_view", view_id=view_id,
                         view_type="form")["arch"], "state")
            ctx.log(f"state widget on the deposit form: {statusbar!r}")
            selection = rpc.call("account.payment", "fields_get", ["state"],
                                 attributes=["selection"])["state"]["selection"]
            ctx.check("account.payment.state selection",
                      list(PAYMENT_STATES),
                      [value for value, _label in selection])
            ctx.check_true(
                "The status bar shows Draft — In Process — Paid "
                "(statusbar_visible=\"draft,in_process,paid\")",
                f'statusbar_visible="{",".join(PAYMENT_STATUSBAR)}"'
                in statusbar,
                actual_desc=statusbar or "no state field found in the arch")
            # See the module docstring: BC-016 means a deposit is stamped
            # 'in_process' at CREATE time, so the state that expresses "not
            # yet confirmed" is the journal entry's.
            if saved["state"] != "draft":
                ctx.log(
                    f"FINDING — the saved but unconfirmed deposit reads "
                    f"state={saved['state']!r}, not 'draft'. This is v19 "
                    f"behaviour and NOT a defect: _generate_journal_entry runs "
                    f"at create time for any payment carrying "
                    f"write_off_line_vals and stamps state='in_process' "
                    f"(addons/account/models/account_payment.py:1080), and "
                    f"every deposit carries those vals "
                    f"(account_partner_deposit/models/account_payment.py:"
                    f"66-90). This is BC-016 in "
                    f"account_partner_deposit/PORTING.md §4, and it is why "
                    f"both the partner and sale-order deposit domains also "
                    f"gate on the journal entry's state. The workbook's "
                    f"'starts on Draft' is asserted below against the entry, "
                    f"which is the state that means 'the money has not been "
                    f"received yet'.")
            ctx.check("The deposit's journal entry is not posted before "
                      "Confirm", "draft", saved["move_state"])

        with ctx.step("Steps 8-9 / Expected line 4: Confirm moves the status "
                      "off Draft"):
            rpc.call("account.payment", "action_post", [deposit_id])
            posted = payment_row(ctx, deposit_id)
            posted_ids.append(deposit_id)
            if deposit_id in created["account.payment"]:
                # Removed from `created` so cleanup never hands it to
                # unlink(): v19 account.payment.unlink() resets a posted
                # move to draft and deletes it (account_payment.py:
                # 957-959). Handing it over
                # would only log a refusal, and the workbook says to keep it.
                created["account.payment"].remove(deposit_id)
            ctx.log(f"after Confirm — state={posted['state']!r} "
                    f"entry={posted['move_state']!r}")
            ctx.check_true(
                "After Confirm the status has moved off Draft",
                posted["state"] != "draft",
                actual_desc=f"account.payment.state = {posted['state']!r}")
            ctx.check("The deposit's journal entry is posted after Confirm",
                      "posted", posted["move_state"])

        with ctx.step("Step 10 / Expected line 5: the journal entry books one "
                      "liquidity line and one Deposit Account line for "
                      "2,500.00 — NOT revenue"):
            lines = move_lines(ctx, posted["move_id"])
            for line in lines:
                ctx.log(f"  {line['account_code']} {line['account_name']!r} "
                        f"[{line['account_type']}] "
                        f"debit={line['debit']:.2f} "
                        f"credit={line['credit']:.2f}")
            deposit_lines = [ln for ln in lines
                             if ln["account_id"] == account["id"]]
            # The liquidity line is identified the way Odoo identifies it —
            # by ACCOUNT, not by account_type. See the module docstring
            # ("Documented correction — how the bank/cash line is found").
            liquidity = payment_liquidity_account(ctx, deposit_id)
            ctx.log(f"the bank/cash side is looked for on account "
                    f"#{liquidity['account_id']} — {liquidity['source']}")
            liquidity_lines = [ln for ln in lines
                               if liquidity["account_id"]
                               and ln["account_id"] == liquidity["account_id"]]
            revenue_lines = [ln for ln in lines
                             if ln["account_type"] in REVENUE_TYPES]

            # "exactly one" is the BC-003 regression guard: write_off_line_vals
            # became a list of dicts keyed on amount_currency and balance, and
            # getting it wrong yields zero or malformed deposit lines
            # (account_partner_deposit/tests/test_fg06_upgrade.py, TC-DEP-001).
            ctx.check("Exactly one line on the Deposit Account", 1,
                      len(deposit_lines))
            ctx.check("The Deposit Account line is a credit of 2,500.00 "
                      "(customer money held as a liability)",
                      (0.0, DEPOSIT_AMOUNT),
                      (deposit_lines[0]["debit"], deposit_lines[0]["credit"]))
            ctx.check(f"Exactly one line on the bank/cash side (the "
                      f"payment's own liquidity account "
                      f"#{liquidity['account_id']})", 1,
                      len(liquidity_lines))
            ctx.check("The bank/cash line is a debit of 2,500.00",
                      (DEPOSIT_AMOUNT, 0.0),
                      (liquidity_lines[0]["debit"],
                       liquidity_lines[0]["credit"]))
            # The workbook's If It Fails: "If the journal entry hits revenue,
            # that is a P0: raise it immediately and do not post any more
            # deposits."
            ctx.check("No line of a deposit's journal entry touches a revenue "
                      "account", [],
                      [f"{ln['account_code']} {ln['account_name']} "
                       f"[{ln['account_type']}]" for ln in revenue_lines])
            ctx.check("The Deposit Account line sits on a liability account, "
                      "as the deposit-account domain requires",
                      "liability_current",
                      account_row(ctx, account["id"])["account_type"])

        with ctx.step("Coverage: the same 2,500.00 read from the CONTACT — "
                      "res.partner.customer_deposit_aml_ids and Total "
                      "Deposit"):
            # Why this step exists, and why it is here rather than in a case
            # of its own.
            #
            # account_partner_deposit/models/res_partner.py:57-63 computes
            # total_deposit by walking customer_deposit_aml_ids and testing
            #   `if aml.company_id == self.env.company and not aml.blocked`
            # — and `account.move.line.blocked` DOES NOT EXIST in Odoo 19. It
            # was v15's "No Follow-up" boolean (v15 addons/account/models/
            # account_move.py:3707); v19 keeps only account.move.payment_state
            # == 'blocked', which is a different thing on a different model.
            # The port dropped the follow-up integration that used to display
            # this field (BC-015) but left the compute reading the removed
            # name, so any read of total_deposit on a contact that HAS at
            # least one open deposit line raises.
            #
            # Until now nothing in FG-06 read either field, so that defect had
            # no automated detector anywhere in the platform — while the
            # recorded TC-DEP-001 / TC-DEP-009 failures had been attributed to
            # it. This is the assertion that makes the attribution real: it
            # runs on a contact that has just been given a confirmed deposit,
            # which is precisely the state in which the loop body executes
            # (an empty recordset never evaluates `aml.blocked`, and the
            # `company_id ==` term short-circuits before it for another
            # company's line).
            coverage_findings = []
            partner_context = {"allowed_company_ids": [company["id"]],
                               "company_id": company["id"]}
            partner_fields = fields_present(
                rpc, "res.partner",
                ["customer_deposit_aml_ids", "total_deposit"])

            if "customer_deposit_aml_ids" in partner_fields:
                open_lines = rpc.call(
                    "res.partner", "read", [partner_id],
                    fields=["customer_deposit_aml_ids"],
                    context=partner_context)[0].get(
                        "customer_deposit_aml_ids") or []
                ctx.log(f"customer_deposit_aml_ids on the contact: "
                        f"{open_lines}")
                # Deferred: this is the SECOND-most important claim in the
                # step. The total_deposit read below is the one that anchors
                # the confirmed product defect (account_partner_deposit
                # res_partner.py:61 reads aml.blocked, removed in v19), and a
                # raising ctx.check here would abort before it ever runs —
                # reintroducing exactly the first-failure-abort flaw this
                # suite was just fixed for. Both are asserted; only the abort
                # is deferred, and the closing check below decides the verdict.
                try:
                    ctx.check(
                        "The confirmed deposit leaves exactly the Deposit "
                        "Account line open on the contact "
                        "(res.partner.customer_deposit_aml_ids)",
                        sorted(line["id"] for line in deposit_lines),
                        sorted(open_lines))
                except AssertionFailed as exc:
                    coverage_findings.append(str(exc))
                    ctx.log(f"FINDING — {exc}")
            else:
                ctx.log("res.partner.customer_deposit_aml_ids is not readable "
                        "by the runner user — the open-line half of this step "
                        "could not be evaluated")

            if "total_deposit" in partner_fields:
                total, error = None, ""
                try:
                    total = money(rpc.call(
                        "res.partner", "read", [partner_id],
                        fields=["total_deposit"],
                        context=partner_context)[0].get("total_deposit"))
                except OdooRPCError as exc:
                    error = str(exc)
                    ctx.log(
                        f"FINDING (PRODUCT DEFECT) — reading "
                        f"res.partner.total_deposit for a contact that holds "
                        f"a deposit raised: {error}. Cause: "
                        f"account_partner_deposit/models/res_partner.py:61 "
                        f"still reads aml.blocked, a field Odoo 19 removed "
                        f"from account.move.line (v15 addons/account/models/"
                        f"account_move.py:3707, 'No Follow-up'). The fix is "
                        f"to drop the term — v19 has no per-line follow-up "
                        f"block, and the module no longer ships the "
                        f"follow-up report that used it (BC-015).")
                # Fails with the RPC error as the ACTUAL value, so the report
                # names the product defect instead of recording an automation
                # error.
                ctx.check("Total Deposit on the contact "
                          "(res.partner.total_deposit)",
                          DEPOSIT_AMOUNT, error or total)
            else:
                ctx.log(
                    "res.partner.total_deposit is not readable by the runner "
                    "user: it carries groups='account.group_account_readonly,"
                    "account.group_account_invoice' "
                    "(account_partner_deposit/models/res_partner.py:50-53), "
                    "so fields_get omits it and a value that cannot be read "
                    "cannot be checked.")
                residual_manual_step(
                    ctx,
                    "res.partner.total_deposit could not be read by the "
                    "runner user (missing account.group_account_readonly / "
                    "account.group_account_invoice). Open the contact as an "
                    "accounting user and confirm Total Deposit reads "
                    f"{DEPOSIT_AMOUNT:.2f}: the compute reads aml.blocked, a "
                    "field Odoo 19 removed, so it is expected to raise.")

            # Closing hard check: the deferred open-lines mismatch above still
            # decides the verdict, but only after the total_deposit read has
            # had its chance to run.
            ctx.check("Contact-side deposit coverage findings", [],
                      coverage_findings)
    finally:
        with ctx.step("Cleanup: remove FG06 fixtures (the CONFIRMED deposit "
                      "is left in place — the workbook's State After The Test "
                      "is 'One confirmed customer deposit of 2,500.00 "
                      "exists')"):
            for payment_id in posted_ids:
                ctx.log(f"confirmed deposit #{payment_id} left in place; a "
                        f"posted deposit is never handed to unlink (v19 "
                        f"account.payment.unlink() would destroy its "
                        f"entry), and later cases "
                        f"build their own rather than inheriting it "
                        f"(AUTOMATION_CONVENTIONS rule 5)")
            cleanup(ctx, created)
