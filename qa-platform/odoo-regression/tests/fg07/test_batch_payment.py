"""FG-07 — TC-INV-008: paying several invoices at once behaves correctly.

Implements row 37.0 (P1, "Payments") of the CLIENT MANUAL TESTING GUIDELINE
``MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0.xlsx`` / sheet
``Testing Guideline``.

The workbook's framing: *"The gallery banks a cheque run and settles many
invoices together. This must produce the right payments against the right
invoices, and not one merged payment that is impossible to reconcile
later."* And its warning: *"It is a bulk operation, and bulk operations are
where an upgrade breaks quietly — you get a plausible-looking result with the
wrong number of records underneath."*

The 3 Expected Result lines, and what each is read from
-------------------------------------------------------
1. **"Both invoices A and B end up fully paid, with Amount Due 0.00."** —
   read from ``account.move.amount_residual`` (the field the Amount Due
   column renders) and ``account.move.payment_state`` /
   ``status_in_payment``, after
   ``account.payment.register.action_create_payments``
   (``addons/account/wizard/account_payment_register.py:1308-1332``). The
   HARD figure is Amount Due 0.00; the status is asserted as "settled"
   (``paid`` or ``in_payment``) with the raw value printed, because a bank
   journal that carries an Outstanding Receipts account legitimately parks
   the invoice at ``in_payment`` until the bank statement is reconciled —
   that distinction is TC-INV-004's subject, not this case's, and it is
   logged here as an OBSERVATION rather than raised.

2. **"The payments in the Payments list add up to 3,000.00 and are correctly
   attributed to Customer 1."** — read from ``account.payment`` rows found
   the way the Payments list finds them (a search on ``partner_id`` scoped
   to the acting company), then ``amount`` summed and ``partner_id``
   compared. The *number* of payments is read two ways so that a wrong count
   cannot hide behind a right total: once BEFORE confirming, from the
   wizard's own ``total_payments_amount``
   (``…/account_payment_register.py:168``, computed at
   ``:398-426`` — ``len(batches)`` when Group Payments is ticked, otherwise
   ``len(_get_total_amounts_to_pay(batches)['lines'])``), and once AFTER, by
   counting the ids ``action_create_payments`` hands back in its act_window
   (``:1322-1331``).

3. **"Step 7: selecting invoices for two DIFFERENT customers either creates
   a separate payment per customer or is refused with a readable message. It
   must not merge two customers' money into one payment."** — this is the P0
   half. ``default_get`` refuses exactly four things and a second customer is
   NOT one of them: different companies (``:976-977``), a branch the user
   cannot reach (``:978-979``), mixed inbound/outbound (``:980-981``) and a
   blocked invoice (``:982-983``). So the wizard is expected to OPEN, and the
   case asserts the workbook's own disjunction — offered *or* refused with a
   readable message — and then proves the P0 on the records themselves: no
   ``account.payment`` carries 4,500.00 (the sum of both customers'
   invoices), the payments' distinct ``partner_id`` count equals the number
   of distinct customers, and each customer's payments total exactly that
   customer's own invoices.

How the pop-up is read WITHOUT confirming it
--------------------------------------------
Workbook step 3 is "read what the pop-up offers: one payment or two, and for
what amount" — a read, before any money moves. The wizard is a
``TransientModel``, so creating one and reading it is side-effect free
(``…/account_payment_register.py:12-15``); nothing is written to the ledger
until ``action_create_payments`` runs. Six fields answer step 3 exactly:

* ``can_edit_wizard`` — True for one batch, False for several
  (``:435-454``); on the multi-customer selection Odoo also blanks
  ``partner_id`` (``:446``), which is the machine-readable form of "this
  pop-up covers more than one customer".
* ``can_group_payments`` (``:456-469``) — whether the "Group Payments"
  option is offered at all. This is the workbook's *"If it offers a grouping
  option, note the wording"*.
* ``group_payment`` (``:482-488``) — its default. For A+B the compute is
  ``len(batches[0]['lines'].move_id) == 1`` (``:486``), which is False for
  two invoices, so Odoo 19 defaults a same-customer multi-invoice batch to
  **two separate payments**, not one merged one.
* ``amount`` (``:740-748``) — 3,000.00 for A+B.
* ``total_payments_amount`` (``:422``) — the count the pop-up itself is
  about to produce. This is the side-effect-free oracle for the workbook's
  "one payment or two".

``batches`` is deliberately NEVER read: it is ``fields.Binary`` holding live
recordsets (``:62``) and does not survive JSON serialisation.

Documented adaptation — four fixture sets instead of one re-tickable list
-------------------------------------------------------------------------
The workbook's step 7 says "repeat from step 1 but tick all THREE invoices".
On a screen the tester can re-tick; over RPC an invoice that has already been
paid is dropped by ``default_get``'s residual filter (``:958-975``) and the
wizard then refuses with "There's nothing left to pay". So the case builds
four independent, marker-named sets of the workbook's own Test Data
(A=1,000.00 / B=2,000.00 for Customer 1, C=1,500.00 for Customer 2) and runs
one scenario against each:

  * set 1 — A+B, Group Payments left at its default  -> expect 2 payments;
  * set 2 — A+B, Group Payments ticked               -> expect 1 of 3,000.00;
  * set 3 — A+B+C, default                           -> expect 3 payments;
  * set 4 — A+B+C, Group Payments ticked             -> expect 2, one per
    customer (3,000.00 and 1,500.00) — never one of 4,500.00.

Sets 2 and 4 are the half of step 3 the workbook asks about but does not
confirm ("if it offers a grouping option, note the wording"); running them
turns "the option exists" into "the option does what it says".

A finding this case will surface
--------------------------------
If the target journal routes through an Outstanding Receipts account, invoices
A and B will read **In Payment** rather than **Paid** even though Amount Due
is 0.00. That is expected Odoo 19 behaviour and is recorded through
``observation()`` — asserted in neither direction here, because the workbook
line this case owns is "Amount Due 0.00" and the wording itself belongs to
TC-INV-004.

Residual manual step
--------------------
The on-screen WORDING of the grouping option (workbook step 3, "note the
wording") is a rendered label. What is captured automatically is the field's
own ``string`` and ``help`` out of ``fields_get`` plus every number the
pop-up would show; the one-line visual confirmation is printed as a RESIDUAL
MANUAL STEP with those captured values in it, never dropped.

Sources read for this module
----------------------------
* ``D:/Projects/odoo-19.0/addons/account/wizard/account_payment_register.py``
* ``D:/Projects/mmg/psus-medicine-man-gallery/mmg_default_payment_journal/``
  ``wizards/account_payment_register.py:11-13`` — the MMG override that
  forces ``journal_id`` to the company default. It changes WHICH journal the
  pop-up offers, never how many payments it makes, so this case probes it and
  reports its absence as a finding instead of blocking on it.
"""
from __future__ import annotations

import csv

from adapters.base import OdooRPCError
from framework.registry import test_case
from tests.fg07.common import (MARK, WORKFLOW, WORKFLOW_NAME, NO_DEFAULT_JOURNAL,
                               acting_company, cleanup, company_ctx,
                               confirm_payment_register, fields_present,
                               finding, m2o_id, m2o_name, make_invoice,
                               make_partner, make_product, module_installed,
                               money, move_row, observation, payment_row,
                               register_payment, require_module, require_v19,
                               residual_manual_step, sweep_fg07, trace)

WIZARD = "account.payment.register"

POPUP_CSV = "TC-INV-008-pay-popup.csv"
PAYMENTS_CSV = "TC-INV-008-payments.csv"
INVOICES_CSV = "TC-INV-008-invoice-settlement.csv"

# The workbook's Test Data, to the cent.
AMOUNT_A = 1000.00
AMOUNT_B = 2000.00
AMOUNT_C = 1500.00
TOTAL_C1 = AMOUNT_A + AMOUNT_B          # 3,000.00 — Expected Result line 2
TOTAL_BOTH = TOTAL_C1 + AMOUNT_C        # 4,500.00 — the merge that is a P0

# Everything the pop-up shows that answers "one payment or two, and for what
# amount". 'batches' is NOT here and must never be added: it is
# fields.Binary holding account.move.line recordsets
# (addons/account/wizard/account_payment_register.py:62) and reading it over
# JSON-RPC fails with a serialisation error that looks like a product defect.
POPUP_FIELDS = ("can_edit_wizard", "can_group_payments", "group_payment",
                "partner_id", "amount", "total_payments_amount", "journal_id",
                "currency_id", "payment_date", "payment_type",
                "installments_mode", "communication")

# An invoice whose Amount Due is 0.00 reads one of these two. 'paid' is a
# journal with no outstanding account; 'in_payment' is one that parks the
# money in Outstanding Receipts until the bank statement is reconciled. Both
# satisfy the workbook's "fully paid, with Amount Due 0.00"; which one is
# shown is TC-INV-004's question.
SETTLED_STATES = ("paid", "in_payment")

# account.payment.state in v19 is a five-value selection — draft, in_process,
# paid, canceled, rejected (addons/account/models/account_payment.py:36-49) —
# and _compute_state (:454-467) leaves a freshly registered payment at
# 'in_process' for as long as its liquidity line sits in a reconcilable
# Outstanding Receipts account with no bank statement against it. So 'paid'
# is NOT the state a correct system shows here; both of these mean the money
# is really in the ledger, and only draft/canceled/rejected would mean it is
# not.
PAYMENT_LIVE_STATES = ("in_process", "paid")

NO_ACCOUNT_MODULE = (
    "'account' (Invoicing) is not installed on this database, so "
    "account.payment.register — the 'Pay' pop-up this whole case is about — "
    "does not exist and no invoice can be settled. Nothing in FG-07 can run "
    "against this database; install Invoicing and re-run the suite from "
    "TC-SMK-015"
)

NO_BANK_JOURNAL = (
    "The acting company has no journal of type bank, cash or credit, so the "
    "Pay pop-up has nothing to offer in its Journal field "
    "(account.payment.register._compute_available_journal_ids, "
    "addons/account/wizard/account_payment_register.py:495-501) and "
    "confirming it would fail on a missing journal rather than on anything "
    "this case is testing. Create or unarchive the gallery's bank journal "
    "under Accounting > Configuration > Journals first — its absence is "
    "itself a migration finding, because the v15 database certainly had one"
)


def _popup(ctx, wizard_id: int) -> dict:
    """Read the Pay pop-up as the tester reads it in workbook step 3.

    Field-by-field rather than a blanket ``read()``: ``fields_get`` is asked
    first so that a field the acting user cannot see is reported as absent
    instead of blowing the read up, and so ``batches`` can never creep in.
    """
    rpc = ctx.adapter.rpc
    readable = [name for name in POPUP_FIELDS
                if name in fields_present(rpc, WIZARD, POPUP_FIELDS)]
    row = rpc.read(WIZARD, [wizard_id], readable)[0]
    return {
        "id": wizard_id,
        "can_edit_wizard": bool(row.get("can_edit_wizard")),
        "can_group_payments": bool(row.get("can_group_payments")),
        "group_payment": bool(row.get("group_payment")),
        "partner_id": m2o_id(row.get("partner_id")),
        "partner": m2o_name(row.get("partner_id")),
        "amount": money(row.get("amount")),
        "total_payments_amount": int(row.get("total_payments_amount") or 0),
        "journal": m2o_name(row.get("journal_id")),
        "currency": m2o_name(row.get("currency_id")),
        "payment_date": row.get("payment_date") or "",
        "payment_type": row.get("payment_type") or "",
        "installments_mode": row.get("installments_mode") or "",
        "communication": row.get("communication") or "",
        "missing_fields": [name for name in POPUP_FIELDS
                           if name not in readable],
    }


def _log_popup(ctx, scenario: str, popup: dict, evidence: list):
    ctx.log(f"[{scenario}] Pay pop-up — "
            f"editable={popup['can_edit_wizard']} "
            f"customer={popup['partner']!r} "
            f"amount={popup['amount']:.2f} {popup['currency']} "
            f"journal={popup['journal']!r} "
            f"grouping offered={popup['can_group_payments']} "
            f"Group Payments ticked={popup['group_payment']} "
            f"-> it will create {popup['total_payments_amount']} payment(s)")
    if popup["missing_fields"]:
        ctx.log(f"[{scenario}] pop-up fields this user cannot read: "
                f"{popup['missing_fields']}")
    evidence.append([scenario, popup["can_edit_wizard"],
                     popup["can_group_payments"], popup["group_payment"],
                     popup["partner"], f"{popup['amount']:.2f}",
                     popup["total_payments_amount"], popup["journal"],
                     popup["installments_mode"], popup["communication"]])


@test_case(
    id="TEST-FG07-INV-008",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module="mmg_default_payment_journal",
    priority="P1",
    kind="API",
    order=708,
    name="Paying several invoices at once behaves correctly",
    description="Proves the Pay pop-up over several invoices creates the "
                "right NUMBER of payments for the right amounts against the "
                "right customers, leaves Amount Due at 0.00, and never merges "
                "two customers' money into one payment.",
    traceability=trace("TC-INV-008"))
def test_inv_008(ctx):
    rpc = ctx.adapter.rpc

    # Declared before the try: the evidence block runs from `finally` and must
    # never hit a NameError over a step an earlier assertion failure skipped —
    # that would replace a real FAILED verdict with an AUTOMATION_ERROR.
    created = {"account.move": [], "product.product": [], "res.partner": []}
    popup_rows: list[list] = []
    payment_rows: list[list] = []
    invoice_rows: list[list] = []
    residual: list[str] = []

    def _post_fixture(partner_id: int, product_id: int, amount: float,
                      label: str, company: dict) -> int:
        """One posted, unpaid FG07 customer invoice for the given amount.

        Created draft and tracked in ``created`` for exactly as long as it is
        deletable; the id is dropped the moment ``action_post`` succeeds,
        because handing a posted account.move to unlink() is forbidden.
        """
        move_id = make_invoice(ctx, partner_id,
                               [(product_id, 1, amount)],
                               company=company,
                               origin=f"{MARK} {label}")
        created["account.move"].append(move_id)
        try:
            rpc.call("account.move", "action_post", [move_id],
                     context=company_ctx(company))
        except OdooRPCError as exc:
            # A fixture that will not post is an environment fact, not a
            # crash: report it as a failed assertion so the run reads FAILED
            # with a diagnosable message rather than AUTOMATION_ERROR.
            ctx.check_true(
                f"Fixture invoice {label} ({amount:,.2f}) posts, as the "
                f"workbook's precondition 'three posted, unpaid customer "
                f"invoices exist' requires",
                False, actual_desc=f"action_post refused: {exc}")
        else:
            created["account.move"].remove(move_id)
        row = move_row(ctx, move_id)
        ctx.check(f"Fixture invoice {label} is posted and unpaid at "
                  f"{amount:,.2f}",
                  ("posted", money(amount)),
                  (row.get("state"), money(row.get("amount_residual"))))
        return move_id

    def _settlement(scenario: str, label: str, move_id: int) -> dict:
        """Amount Due + status off one invoice, as workbook step 5 reads it."""
        row = move_row(ctx, move_id)
        state = row.get("payment_state") or ""
        shown = row.get("status_in_payment") or state
        ctx.log(f"[{scenario}] invoice {label} {row.get('name')!r} — "
                f"Total {row['amount_total']:.2f}, Amount Due "
                f"{row['amount_residual']:.2f}, payment_state={state!r}, "
                f"shown as {shown!r}")
        invoice_rows.append([scenario, label, row.get("name") or "",
                             m2o_name(row.get("partner_id")),
                             f"{row['amount_total']:.2f}",
                             f"{row['amount_residual']:.2f}", state, shown])
        return {"label": label, "residual": row["amount_residual"],
                "state": state, "shown": shown,
                "name": row.get("name") or ""}

    def _payments(scenario: str, payment_ids) -> list[dict]:
        rows = []
        for payment_id in payment_ids:
            row = payment_row(ctx, payment_id)
            rows.append(row)
            ctx.log(f"[{scenario}] payment {row['name']!r} — "
                    f"{row['amount']:.2f} {row['currency']} for "
                    f"{row['partner']!r} through {row['journal']!r} "
                    f"(state={row['state']!r}, matched={row['is_matched']})")
            payment_rows.append([scenario, row["name"], row["partner"],
                                 f"{row['amount']:.2f}", row["currency"],
                                 row["journal"], row["state"],
                                 row["is_matched"]])
        return rows

    with ctx.step("Precondition (workbook): TC-INV-006 has passed, and three "
                  "posted, unpaid customer invoices exist — two for the SAME "
                  "customer and one for a different customer"):
        require_v19(ctx)
        require_module(ctx, "account", NO_ACCOUNT_MODULE)
        company = acting_company(ctx)
        ctx.log(f"acting company #{company['id']} {company['name']!r} — "
                f"currency {company['currency_name']}")

        # The Pay pop-up needs somewhere to put the money. Probing this here
        # keeps a missing journal from surfacing as an obscure failure inside
        # action_create_payments three steps later.
        journals = rpc.search_read(
            "account.journal",
            [("company_id", "=", company["id"]),
             ("type", "in", ("bank", "cash", "credit"))],
            ["name", "code", "type"], limit=25)
        if not journals:
            ctx.blocked(NO_BANK_JOURNAL)
        ctx.log(f"{len(journals)} payment journal(s) available: "
                + ", ".join(f"{j['code']} {j['name']!r} ({j['type']})"
                            for j in journals))

        # The workbook's precondition is "TC-INV-006 has passed", i.e. the MMG
        # default-payment-journal override is live. It changes WHICH journal
        # the pop-up preselects (mmg_default_payment_journal/wizards/
        # account_payment_register.py:11-13), never how many payments are
        # made, so its absence is reported and the case continues — blocking
        # here would hide a core batch-payment regression behind a missing
        # custom module.
        if module_installed(rpc, "mmg_default_payment_journal"):
            ctx.log("module 'mmg_default_payment_journal': installed — the "
                    "pop-up's Journal comes from the company default, as "
                    "TC-INV-006 checks")
        else:
            finding(ctx, f"the workbook's precondition 'TC-INV-006 has "
                         f"passed' cannot hold on this database: "
                         f"{NO_DEFAULT_JOURNAL}. TC-INV-008 continues anyway "
                         f"— the number and attribution of the payments is "
                         f"core Odoo behaviour and is what this case proves")

        sweep_fg07(ctx)

    try:
        with ctx.step("Test Data (workbook): Invoice A 1,000.00 and Invoice B "
                      "2,000.00 for Customer 1, Invoice C 1,500.00 for "
                      "Customer 2"):
            partner_c1 = make_partner(ctx, "Customer 1 (batch pay)",
                                      company=company)
            partner_c2 = make_partner(ctx, "Customer 2 (batch pay)",
                                      company=company)
            created["res.partner"].extend([partner_c1, partner_c2])
            # One tax-free product; every figure the workbook quotes is set
            # per line as price_unit, so the invoice totals are exactly
            # 1,000.00 / 2,000.00 / 1,500.00 with no tax to round.
            product_id = make_product(ctx, "Batch Payment Item", AMOUNT_A)
            created["product.product"].append(product_id)

            move_a = _post_fixture(partner_c1, product_id, AMOUNT_A,
                                   "Invoice A set 1", company)
            move_b = _post_fixture(partner_c1, product_id, AMOUNT_B,
                                   "Invoice B set 1", company)
            ctx.log(f"set 1 — A #{move_a} 1,000.00 and B #{move_b} 2,000.00, "
                    f"both for {MARK} Customer 1 (batch pay)")

        with ctx.step("Steps 1-3: tick invoices A and B, click Pay, and read "
                      "what the pop-up offers — one payment or two, and for "
                      "what amount"):
            # Creating the wizard IS clicking Pay: account.payment.register is
            # a TransientModel and nothing reaches the ledger until
            # action_create_payments runs, so every figure below is read
            # before any money moves.
            wizard_1 = register_payment(ctx, [move_a, move_b],
                                        company=company)
            popup_1 = _popup(ctx, wizard_1)
            _log_popup(ctx, "set 1 — A+B, as offered", popup_1, popup_rows)

            ctx.check_true(
                "The Pay pop-up opens editable for a single customer's "
                "invoices (can_edit_wizard, set when the selection forms one "
                "batch — account_payment_register.py:435-439)",
                popup_1["can_edit_wizard"],
                actual_desc=f"can_edit_wizard={popup_1['can_edit_wizard']}")
            ctx.check("The pop-up names Customer 1 as the customer being paid",
                      partner_c1, popup_1["partner_id"])
            ctx.check("The pop-up offers the full 3,000.00 of invoices A and "
                      "B (Amount)",
                      money(TOTAL_C1), popup_1["amount"])
            ctx.check_true(
                "The pop-up offers the grouping option the workbook asks us "
                "to note (can_group_payments — "
                "account_payment_register.py:456-469)",
                popup_1["can_group_payments"],
                actual_desc=f"can_group_payments="
                            f"{popup_1['can_group_payments']}")
            # This is the crux of workbook step 3. Odoo 19's default for a
            # multi-INVOICE batch is NOT grouped: _compute_group_payment is
            # len(batches[0]['lines'].move_id) == 1 (:486), which is False
            # here, so the pop-up is about to make two payments.
            ctx.check_true(
                "Group Payments is NOT ticked by default for two separate "
                "invoices, so the pop-up will settle each invoice with its "
                "own payment rather than one merged 3,000.00",
                not popup_1["group_payment"],
                actual_desc=f"group_payment={popup_1['group_payment']}")
            ctx.check("The pop-up itself says it will create 2 payments "
                      "(total_payments_amount — the count read BEFORE "
                      "confirming, account_payment_register.py:422)",
                      2, popup_1["total_payments_amount"])

            # The wording half of step 3, captured from the field definition
            # so the human step is a glance, not a re-run.
            spec = {}
            try:
                spec = rpc.call(WIZARD, "fields_get", ["group_payment"],
                                attributes=["string", "help"]) or {}
            except OdooRPCError as exc:
                ctx.log(f"could not read the Group Payments label ({exc})")
            label = (spec.get("group_payment") or {}).get("string") or ""
            help_text = (spec.get("group_payment") or {}).get("help") or ""
            ctx.log(f"grouping option label: {label!r} — help: {help_text!r}")
            residual.append(
                f"workbook step 3 asks you to NOTE THE WORDING of the "
                f"grouping option. What the platform can read is the field "
                f"definition: label {label!r}, help {help_text!r}, offered="
                f"{popup_1['can_group_payments']}, ticked by default="
                f"{popup_1['group_payment']}. Open Accounting > Customers > "
                f"Invoices, tick two invoices for one customer, press Pay, "
                f"and confirm the checkbox on screen reads {label!r} and sits "
                f"above an amount of {popup_1['amount']:,.2f} "
                f"{popup_1['currency']} — then this line is ticked off.")

        with ctx.step("Steps 4-5 / Expected line 1: confirm the payment, then "
                      "open invoice A and invoice B and read Amount Due and "
                      "status"):
            paid_ids_1 = confirm_payment_register(ctx, wizard_1,
                                                  [move_a, move_b],
                                                  company=company)
            ctx.check_true(
                "Confirming the pop-up returns the payments it created, so "
                "the count below is Odoo's own answer and not a search that "
                "might catch someone else's payment",
                bool(paid_ids_1),
                actual_desc=f"action_create_payments returned "
                            f"{len(paid_ids_1)} payment id(s): {paid_ids_1}")
            rows_1 = _payments("set 1 — A+B, as offered", paid_ids_1)
            # The count the pop-up promised in step 3, now measured against
            # what it actually made. A bulk operation that promises two and
            # delivers one is precisely the quiet break the workbook's Why It
            # Matters column describes.
            ctx.check("Confirming created the 2 payments the pop-up said it "
                      "would create in step 3",
                      popup_1["total_payments_amount"], len(rows_1))

            # Expected line 1. amount_residual is the Amount Due column; it is
            # the figure the workbook states, so it is the hard assertion.
            settled = [_settlement("set 1 — A+B, as offered", "A", move_a),
                       _settlement("set 1 — A+B, as offered", "B", move_b)]
            still_due = [f"{s['label']} ({s['name']}) still shows Amount Due "
                         f"{s['residual']:.2f}"
                         for s in settled if money(s["residual"]) != 0.00]
            ctx.check("Both invoices A and B end up fully paid, with Amount "
                      "Due 0.00", [], still_due)
            not_settled = [f"{s['label']} ({s['name']}) reads "
                           f"payment_state={s['state']!r}"
                           for s in settled
                           if s["state"] not in SETTLED_STATES]
            ctx.check("Both invoices A and B read as settled — 'Paid', or "
                      "'In Payment' while the receipt is still in transit",
                      [], not_settled)
            in_payment = [s for s in settled if s["state"] == "in_payment"]
            if in_payment:
                observation(ctx, f"invoice(s) "
                                 f"{', '.join(s['name'] for s in in_payment)} "
                                 f"read 'In Payment' rather than 'Paid' even "
                                 f"though Amount Due is 0.00. That is Odoo 19 "
                                 f"behaving correctly for a journal with an "
                                 f"Outstanding Receipts account — the money "
                                 f"is booked but the bank statement is not "
                                 f"reconciled yet. The wording itself is "
                                 f"TC-INV-004's question; this case asserts "
                                 f"Amount Due, which is 0.00")

        with ctx.step("Step 6 / Expected line 2: go to Accounting > Customers "
                      "> Payments, find the payment(s) just created, and note "
                      "how many there are and their amounts"):
            # The Payments list, read the way the list reads it: a search on
            # the customer, scoped to the acting company. Customer 1 is an
            # FG07 fixture created a few seconds ago, so this population is
            # exactly the payments this step is about — no live-data leak.
            listed_ids = rpc.search(
                "account.payment",
                [("partner_id", "=", partner_c1),
                 ("company_id", "=", company["id"])])
            listed = [payment_row(ctx, pid) for pid in listed_ids]
            for row in listed:
                ctx.log(f"Payments list — {row['name']!r} {row['amount']:.2f} "
                        f"{row['currency']} for {row['partner']!r}")

            ctx.check("The Payments list holds 2 payments for Customer 1 — "
                      "one per invoice, which is what the pop-up said it "
                      "would create",
                      2, len(listed))
            ctx.check("The two payments are for 1,000.00 and 2,000.00 — "
                      "invoice A and invoice B settled separately, not one "
                      "merged record",
                      [money(AMOUNT_A), money(AMOUNT_B)],
                      sorted(row["amount"] for row in listed))
            ctx.check("The payments in the Payments list add up to 3,000.00",
                      money(TOTAL_C1),
                      money(sum(row["amount"] for row in listed)))
            misattributed = [
                f"{row['name']} ({row['amount']:.2f}) is attributed to "
                f"{row['partner']!r}"
                for row in listed if row["partner_id"] != partner_c1]
            ctx.check("Every payment is correctly attributed to Customer 1",
                      [], misattributed)
            # THE ABOVE CANNOT FAIL ON ITS OWN. `listed` came out of a search
            # already filtered on partner_id = Customer 1, so re-checking the
            # partner of its rows re-states the domain. The workbook's
            # "correctly attributed to Customer 1" is a real question and needs
            # the two populations compared: the payments action_create_payments
            # says it made, and the payments Customer 1's Payments list shows.
            # A payment booked against the wrong customer disappears from the
            # list and shows up here as a missing id.
            ctx.check("The payments the pop-up created ARE the payments on "
                      "Customer 1's Payments list — none of the 3,000.00 was "
                      "booked against anybody else, and nothing else is "
                      "sitting on her list",
                      sorted(paid_ids_1), sorted(listed_ids))
            wrong_partner = [
                f"{row['name']} ({row['amount']:.2f}) was created against "
                f"{row['partner']!r}"
                for row in rows_1 if row["partner_id"] != partner_c1]
            ctx.check("…and each payment action_create_payments returned "
                      "names Customer 1 as its customer "
                      "(account.payment.partner_id, read off the created "
                      "records rather than off a search that presumes it)",
                      [], wrong_partner)
            # A payment whose journal entry never posted is money that looks
            # banked on the list and is not in the ledger — the "plausible
            # result with the wrong records underneath" the workbook warns of.
            # 'in_process' counts as live: it is what a payment reads while
            # the receipt sits in Outstanding Receipts awaiting the bank
            # statement (account_payment.py:454-467). Demanding 'paid' here
            # would fail a correct system.
            not_live = [f"{row['name']} is in state {row['state']!r}"
                        for row in listed
                        if row["state"] not in PAYMENT_LIVE_STATES]
            ctx.check("Both payments are live in the ledger — none is left in "
                      "Draft, Canceled or Rejected, which would mean the "
                      "3,000.00 was never really banked",
                      [], not_live)

        with ctx.step("Step 3 continued / Expected line 1: the grouping "
                      "option the pop-up offers really does produce ONE "
                      "payment of 3,000.00 (a second, untouched pair of "
                      "invoices)"):
            # The workbook says to note the grouping option; noting that it
            # exists is weaker than proving it works, and a bulk operation
            # that silently ignores the tick is exactly the quiet upgrade
            # break this case is written to catch.
            move_a2 = _post_fixture(partner_c1, product_id, AMOUNT_A,
                                    "Invoice A set 2", company)
            move_b2 = _post_fixture(partner_c1, product_id, AMOUNT_B,
                                    "Invoice B set 2", company)
            # group_payment is store=True, readonly=False
            # (account_payment_register.py:25-27), so a value supplied in
            # create() wins over its compute — this is the ticked checkbox.
            wizard_2 = register_payment(ctx, [move_a2, move_b2],
                                        {"group_payment": True},
                                        company=company)
            popup_2 = _popup(ctx, wizard_2)
            _log_popup(ctx, "set 2 — A+B, Group Payments ticked", popup_2,
                       popup_rows)
            ctx.check("With Group Payments ticked the pop-up says it will "
                      "create 1 payment",
                      1, popup_2["total_payments_amount"])

            paid_ids_2 = confirm_payment_register(ctx, wizard_2,
                                                  [move_a2, move_b2],
                                                  company=company)
            rows_2 = _payments("set 2 — A+B, Group Payments ticked",
                               paid_ids_2)
            ctx.check("Ticking Group Payments produces exactly one payment",
                      1, len(rows_2))
            ctx.check("That one payment is for the whole 3,000.00 and is "
                      "attributed to Customer 1",
                      (money(TOTAL_C1), partner_c1),
                      (money(sum(row["amount"] for row in rows_2)),
                       rows_2[0]["partner_id"] if rows_2 else None))
            grouped_due = [
                f"{s['label']} ({s['name']}) still shows Amount Due "
                f"{s['residual']:.2f}"
                for s in (_settlement("set 2 — A+B, Group Payments ticked",
                                      "A", move_a2),
                          _settlement("set 2 — A+B, Group Payments ticked",
                                      "B", move_b2))
                if money(s["residual"]) != 0.00]
            ctx.check("The single grouped payment still leaves both invoices "
                      "with Amount Due 0.00", [], grouped_due)

        with ctx.step("Step 7 / Expected line 3: repeat from step 1 but tick "
                      "all THREE invoices, including Customer 2's, and read "
                      "what the pop-up says"):
            move_a3 = _post_fixture(partner_c1, product_id, AMOUNT_A,
                                    "Invoice A set 3", company)
            move_b3 = _post_fixture(partner_c1, product_id, AMOUNT_B,
                                    "Invoice B set 3", company)
            move_c3 = _post_fixture(partner_c2, product_id, AMOUNT_C,
                                    "Invoice C set 3", company)

            # The workbook allows either branch — offered, or refused with a
            # readable message. Reading the v19 source says it will be
            # offered: default_get's only hard stops are different companies
            # (:976-977), an unreachable branch (:978-979), mixed
            # inbound/outbound (:980-981) and a blocked invoice (:982-983).
            # A refusal is therefore caught, not allowed to escape as an
            # AUTOMATION_ERROR, and judged on the readability of its message.
            wizard_3 = None
            refusal = ""
            offered_without_a_single_customer = False
            try:
                wizard_3 = register_payment(ctx, [move_a3, move_b3, move_c3],
                                            company=company)
            except OdooRPCError as exc:
                refusal = str(exc).strip()

            if refusal:
                ctx.log(f"the Pay pop-up REFUSED the two-customer selection: "
                        f"{refusal}")
                popup_rows.append(["set 3 — A+B+C, refused", "", "", "", "",
                                   "", "", "", "", refusal[:200]])
                # A refusal is a legitimate branch of Expected line 3, but
                # only if a gallery accountant can act on what it says.
                ctx.check_true(
                    "The refusal is a readable message an accountant can act "
                    "on, not a traceback",
                    len(refusal) >= 20 and "Traceback" not in refusal,
                    actual_desc=f"{len(refusal)} character(s): {refusal[:300]}")
                finding(ctx, f"Odoo 19 source says the two-customer selection "
                             f"should OPEN — account.payment.register."
                             f"default_get refuses only different companies, "
                             f"unreachable branches, mixed inbound/outbound "
                             f"and blocked invoices "
                             f"(addons/account/wizard/"
                             f"account_payment_register.py:976-983), and "
                             f"there is no partner check. This database "
                             f"refused it with {refusal!r}. The workbook "
                             f"accepts a refusal, so this case does not fail "
                             f"on it, but somebody has added a restriction "
                             f"and Novobi should know which module did")
                residual.append(
                    "the two-customer selection was REFUSED on this database, "
                    "so the workbook's 'a separate payment per customer' "
                    "branch could not be exercised. Read the message quoted "
                    "above and confirm with the gallery that refusing a "
                    "mixed-customer cheque run is acceptable for their "
                    "process — the workbook allows it, but it changes how "
                    "they bank a cheque run.")
            else:
                popup_3 = _popup(ctx, wizard_3)
                offered_without_a_single_customer = not popup_3["partner_id"]
                _log_popup(ctx, "set 3 — A+B+C, as offered", popup_3,
                           popup_rows)
                # The machine-readable signature of "this pop-up spans more
                # than one customer": Odoo blanks partner_id and locks the
                # wizard (account_payment_register.py:441-454).
                ctx.check_true(
                    "The pop-up does NOT present the three invoices as one "
                    "editable customer payment — it locks itself because the "
                    "selection spans more than one batch (can_edit_wizard "
                    "False, :454)",
                    not popup_3["can_edit_wizard"],
                    actual_desc=f"can_edit_wizard="
                                f"{popup_3['can_edit_wizard']}")
                ctx.check("The pop-up names NO single customer, which is how "
                          "it says 'this covers more than one' (partner_id "
                          "blanked at :446)",
                          None, popup_3["partner_id"])
                ctx.check("The pop-up says it will create 3 payments — one "
                          "per invoice, so no customer's money is pooled",
                          3, popup_3["total_payments_amount"])
                # The wizard's own Amount field does add up to 4,500.00 here.
                # That is a display total across two locked batches, NOT a
                # merged payment, and saying so in the log stops a tester
                # reporting it as the P0.
                ctx.log(f"[set 3] the pop-up's Amount reads "
                        f"{popup_3['amount']:.2f} — that is the total of both "
                        f"customers' invoices shown on a LOCKED wizard, not a "
                        f"single payment; the payments themselves are checked "
                        f"in the next step")

            ctx.check_true(
                "Selecting invoices for two DIFFERENT customers is either "
                "offered as a multi-customer batch or refused with a readable "
                "message — never silently accepted as one customer's payment",
                bool(refusal) or offered_without_a_single_customer,
                actual_desc=("refused: " + refusal[:200]) if refusal
                            else "offered, with no single customer named on "
                                 "the pop-up")

        with ctx.step("Step 7 / Expected line 3 (the P0): confirming the "
                      "two-customer selection must not merge two customers' "
                      "money into one payment"):
            if refusal:
                ctx.log("the pop-up refused the two-customer selection, so "
                        "there is nothing to confirm and no payment could "
                        "have been merged. Expected line 3 is satisfied by "
                        "the refusal branch; the merge check below is not "
                        "skipped silently — it is inapplicable, and the "
                        "reason is on the line above")
            else:
                paid_ids_3 = confirm_payment_register(
                    ctx, wizard_3, [move_a3, move_b3, move_c3],
                    company=company)
                rows_3 = _payments("set 3 — A+B+C, as offered", paid_ids_3)

                ctx.check("Confirming three invoices for two customers "
                          "creates 3 payments — one per invoice",
                          3, len(rows_3))
                # THE P0. Two customers' money in one record is the failure
                # this case exists to find, and it is asserted three ways so
                # that a failure names the offending payment.
                merged = [f"{row['name']} carries {row['amount']:.2f}, which "
                          f"is BOTH customers' invoices"
                          for row in rows_3
                          if money(row["amount"]) == money(TOTAL_BOTH)]
                ctx.check("No single payment carries 4,500.00 — the sum of "
                          "both customers' invoices (P0 if it does)",
                          [], merged)
                ctx.check("The payments are spread across exactly 2 distinct "
                          "customers, one per customer in the selection",
                          2, len({row["partner_id"] for row in rows_3}))
                by_partner = {}
                for row in rows_3:
                    by_partner[row["partner_id"]] = money(
                        by_partner.get(row["partner_id"], 0.0) + row["amount"])
                ctx.check("Customer 1's payments total 3,000.00 and Customer "
                          "2's total 1,500.00 — neither customer's money has "
                          "moved to the other",
                          {partner_c1: money(TOTAL_C1),
                           partner_c2: money(AMOUNT_C)},
                          by_partner)
                stray = [f"{row['name']} ({row['amount']:.2f}) is attributed "
                         f"to {row['partner']!r}"
                         for row in rows_3
                         if row["partner_id"] not in (partner_c1, partner_c2)]
                ctx.check("Every payment belongs to one of the two customers "
                          "actually selected", [], stray)

                due = [f"{s['label']} ({s['name']}) still shows Amount Due "
                       f"{s['residual']:.2f}"
                       for s in (_settlement("set 3 — A+B+C, as offered", "A",
                                             move_a3),
                                 _settlement("set 3 — A+B+C, as offered", "B",
                                             move_b3),
                                 _settlement("set 3 — A+B+C, as offered", "C",
                                             move_c3))
                       if money(s["residual"]) != 0.00]
                ctx.check("All three invoices end with Amount Due 0.00, each "
                          "settled by its own customer's payment", [], due)

        with ctx.step("Step 7 / Expected line 3 with Group Payments ticked: "
                      "one payment PER CUSTOMER, never one merged payment"):
            if refusal:
                ctx.log("skipped for the same reason as the previous step: "
                        "this database refuses a two-customer selection "
                        "outright, so grouping it is not reachable")
            else:
                # The strictest reading of Expected line 3 — "creates a
                # separate payment per customer". Grouping is precisely the
                # setting under which a naive implementation would pool the
                # two customers, so this is where a merge would actually
                # happen if it ever did.
                move_a4 = _post_fixture(partner_c1, product_id, AMOUNT_A,
                                        "Invoice A set 4", company)
                move_b4 = _post_fixture(partner_c1, product_id, AMOUNT_B,
                                        "Invoice B set 4", company)
                move_c4 = _post_fixture(partner_c2, product_id, AMOUNT_C,
                                        "Invoice C set 4", company)
                wizard_4 = register_payment(ctx,
                                            [move_a4, move_b4, move_c4],
                                            {"group_payment": True},
                                            company=company)
                popup_4 = _popup(ctx, wizard_4)
                _log_popup(ctx, "set 4 — A+B+C, Group Payments ticked",
                           popup_4, popup_rows)
                ctx.check("With Group Payments ticked over two customers the "
                          "pop-up says it will create 2 payments — one per "
                          "customer, not one for 4,500.00",
                          2, popup_4["total_payments_amount"])

                paid_ids_4 = confirm_payment_register(
                    ctx, wizard_4, [move_a4, move_b4, move_c4],
                    company=company)
                rows_4 = _payments("set 4 — A+B+C, Group Payments ticked",
                                   paid_ids_4)
                ctx.check("Grouping across two customers creates exactly 2 "
                          "payments", 2, len(rows_4))
                merged_4 = [f"{row['name']} carries {row['amount']:.2f}"
                            for row in rows_4
                            if money(row["amount"]) == money(TOTAL_BOTH)]
                ctx.check("Even with Group Payments ticked, no payment "
                          "carries 4,500.00 — the two customers' money is "
                          "never pooled (P0 if it is)", [], merged_4)
                grouped_by_partner = {}
                for row in rows_4:
                    grouped_by_partner[row["partner_id"]] = money(
                        grouped_by_partner.get(row["partner_id"], 0.0)
                        + row["amount"])
                ctx.check("The grouped run produces one 3,000.00 payment for "
                          "Customer 1 and one 1,500.00 payment for Customer 2",
                          {partner_c1: money(TOTAL_C1),
                           partner_c2: money(AMOUNT_C)},
                          grouped_by_partner)
                due_4 = [f"{s['label']} ({s['name']}) still shows Amount Due "
                         f"{s['residual']:.2f}"
                         for s in (_settlement(
                                       "set 4 — A+B+C, Group Payments ticked",
                                       "A", move_a4),
                                   _settlement(
                                       "set 4 — A+B+C, Group Payments ticked",
                                       "B", move_b4),
                                   _settlement(
                                       "set 4 — A+B+C, Group Payments ticked",
                                       "C", move_c4))
                         if money(s["residual"]) != 0.00]
                ctx.check("All three invoices in the grouped run end with "
                          "Amount Due 0.00", [], due_4)

        with ctx.step("State After The Test (workbook): invoices A and B are "
                      "paid; invoice C may or may not be"):
            # Stated rather than asserted: the workbook itself leaves C's
            # fate open, so an assertion either way would be inventing an
            # expectation the workbook declined to make.
            ctx.log("this case leaves POSTED invoices and POSTED payments "
                    "behind by design — accounting evidence is never deleted, "
                    "and cleanup() refuses posted records. Everything it left "
                    "is named with the "
                    + MARK + " marker and listed in the CSV artifacts")
    finally:
        with ctx.step("Evidence: write the pop-up, payment and settlement "
                      "CSVs, then remove what can safely be removed"):
            for name, header, rows in (
                (POPUP_CSV,
                 ["scenario", "can_edit_wizard", "can_group_payments",
                  "group_payment", "customer", "amount",
                  "payments_it_will_create", "journal", "installments_mode",
                  "memo"],
                 popup_rows),
                (PAYMENTS_CSV,
                 ["scenario", "payment", "customer", "amount", "currency",
                  "journal", "state", "is_matched"],
                 payment_rows),
                (INVOICES_CSV,
                 ["scenario", "invoice_label", "invoice", "customer",
                  "total", "amount_due", "payment_state", "status_shown"],
                 invoice_rows),
            ):
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
            cleanup(ctx, created)
