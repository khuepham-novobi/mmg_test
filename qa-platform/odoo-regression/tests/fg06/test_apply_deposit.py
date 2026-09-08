"""FG-06 — applying a deposit to an invoice, and which deposits are offered.

Implements two rows of the CLIENT MANUAL TESTING GUIDELINE
``MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0.xlsx`` / sheet
``Testing Guideline``:

* **TC-DEP-007** (row 22.0, P0, "Applying deposits") — "A deposit is applied
  to the invoice raised from the order". The workbook marks it READ THIS
  FIRST: *"This is the moment the money moves from a liability to settling a
  real invoice. If it does not work, the customer is asked to pay twice and
  the deposit sits on the balance sheet for ever."*
* **TC-DEP-009** (row 23.0, P1) — "A customer's unused deposits are offered
  on their next invoice". Also READ THIS FIRST, because the rule for which
  deposits count changed in v19: *"This case is specifically checking that
  the list is neither empty nor over-full."*

A real divergence between the workbook's STEPS and the v19 code
---------------------------------------------------------------
This needs stating plainly, because it changes how TC-DEP-007 must be run —
and it is a finding for the client, not a test defect.

The workbook's steps are: Create Invoice, Confirm, **then** expand
Outstanding credits and click the 3,000.00 deposit to apply it (steps 3-5).
On v19 with ``sale_partner_deposit`` installed, the deposit is **already
applied** by the time Confirm returns:

    account.move.action_post()                      # sale_partner_deposit/
      -> for each out_invoice:                      #   models/account_move.py:7-17
           deposits = invoice.invoice_line_ids
                        .mapped('sale_line_ids.order_id.deposit_ids')
           self._reconcile_deposit(deposits, invoice)
      -> invoice.js_assign_outstanding_line(deposit_line.id)
                                                    # account_partner_deposit/
                                                    #   models/account_move.py:245-262

and once applied, the deposit line no longer satisfies the panel's own domain
— which requires ``('reconciled', '=', False)`` and a non-zero residual
(``account_partner_deposit/models/account_move.py:41-50``). The panel is also
empty before Confirm, because the override returns early unless
``move.state == 'posted'`` (``:32-37``). So on the order-linked path there is
**no moment at which the panel offers that deposit**, and the workbook's
steps 3-5 cannot be performed in the order written.

The workbook's *outcomes* are unaffected and are all asserted: 7,000.00 still
due on a 10,000.00 invoice, a partial payment status, and a journal entry
that releases the deposit liability rather than adding revenue.

Expected Result line 1 — "the deposit appears in Outstanding credits for
3,000.00" — is a statement about the panel, so it is asserted where the panel
is genuinely reachable: on a deposit the auto-application does not consume,
using the workbook's own figures (a 3,000.00 deposit against a 10,000.00
invoice leaving 7,000.00). That is the same code path the workbook's step 5
clicks — ``js_assign_outstanding_line`` — reached the way a tester reaches it
when the deposit was taken on the accounting screen rather than against the
order. Both scenarios are run, and the divergence is logged as a FINDING with
its source lines so the client can correct the workbook's step order rather
than raise a defect against working code.

The word "Deposit" in the panel — an instruction, not an expectation
--------------------------------------------------------------------
The workbook says the entries are labelled with the journal and payment
method and *"do NOT say the word 'Deposit'. That is expected in Odoo 19 and is
not a defect"*, and its If It Fails adds *"If the only thing wrong is the
missing word 'Deposit', that is not a defect — close the case as a pass and
note the observation."* That is guidance to the tester, not a result to
verify, so this module does **not** assert the absence of the word: doing so
would turn a non-requirement into a failure mode, and a memo containing
"Deposit" would fail it spuriously. It is recorded as an observation with the
reason (decision D3-a: the legacy ``t-extend``/``t-jquery`` QWeb override
that stamped the label was not ported, because that inheritance was removed
in Odoo 16 and the v19 OWL popover has no such slot —
``account_partner_deposit/__manifest__.py:34-41``).

What IS asserted about the payload is the v19 OWL contract: the keys the
component reads must all be present (``currency_id``, ``date``,
``account_payment_id``, ``move_id``, ``move_ref``). That is the BC-006
regression guard — the port dropped the dead ``position`` and ``digits`` keys
and added ``move_ref`` — and a missing key means a panel that renders wrongly
or not at all.

TC-DEP-009 and BC-016
---------------------
The workbook's step 5 says to create a second deposit and *"SAVE it and leave
it in Draft — do not Confirm it"*, then check it is not offered. In v19 a
deposit is stamped ``state = 'in_process'`` the moment it is created, because
``_generate_journal_entry`` runs at create time for any payment carrying
``write_off_line_vals`` (``addons/account/models/account_payment.py:1080``)
and every deposit carries them. A state-only filter would therefore offer
money that was never received. The panel's domain gates on
``('parent_state', '=', 'posted')`` — the journal entry, not the payment —
which is what makes the workbook's expectation hold. That is BC-016
(``account_partner_deposit/PORTING.md`` §4), and this case is its acceptance
test: the log records both states of the unconfirmed deposit so a reader can
see why it is excluded.
"""
from __future__ import annotations

from framework.registry import test_case
from tests.fg06.common import (CUSTOMER_SIDE, MODULE, MODULE_SALE,
                               OPTION_FIXED, PAYMENT_STATE_PARTIAL, WORKFLOW,
                               WORKFLOW_NAME, acting_company, apply_outstanding_credit,
                               cleanup, deposit_accounts_for_test,
                               deposit_popup_state, invoice_from_order,
                               invoice_totals, make_deposit, make_invoice,
                               make_order, make_partner, make_product, money,
                               move_lines, open_make_deposit_wizard,
                               order_totals, payment_row, require_sale_deposit,
                               require_v19, run_make_deposit_wizard,
                               outstanding_credits, sweep_fg06, trace,
                               validate_deposit_popup)

# Workbook Test Data for TC-DEP-007: order 10,000.00, deposit 3,000.00,
# leaving 7,000.00 due.
ORDER_TOTAL, DEPOSIT = 10000.00, 3000.00
REMAINING = money(ORDER_TOTAL - DEPOSIT)

# Workbook Test Data for TC-DEP-009.
DEP009_DEPOSIT, DEP009_INVOICE, DEP009_DRAFT = 2500.00, 4000.00, 1000.00

# The keys the v19 OWL component reads out of the widget payload
# (addons/account/static/src/components/account_payment_field/
# account_payment_field.js), and which the port had to keep in step (BC-006).
OWL_CONTRACT_KEYS = {"currency_id", "date", "account_payment_id", "move_id",
                     "move_ref", "amount", "id"}

REVENUE_TYPES = ("income", "income_other")
DEPOSIT_ENTRY_REF = "Deposit to Payment"


def _log_panel(ctx, label: str, entries: list):
    ctx.log(f"{label}: {len(entries)} entr(ies)")
    for entry in entries:
        ctx.log(f"    line #{entry['line_id']} {entry['amount']:.2f} "
                f"label={entry['journal_name']!r} "
                f"ref={entry['move_ref']!r} "
                f"payment=#{entry['payment_id']} date={entry['date']}")


def _assert_owl_contract(ctx, entries: list):
    """Every panel entry must carry the keys the OWL component reads."""
    missing = []
    for entry in entries:
        absent = sorted(OWL_CONTRACT_KEYS - set(entry["keys"]))
        if absent:
            missing.append(f"line #{entry['line_id']}: {absent}")
    ctx.check("Every Outstanding credits entry carries the keys the v19 "
              "payment widget reads (BC-006 regression guard)", [], missing)


@test_case(
    id="TEST-FG06-DEP-007",
    name="A deposit is applied to the invoice raised from the order",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE_SALE,
    priority="P0",
    kind="API",
    order=609,
    description="Invoicing a 10,000.00 order that carries a 3,000.00 deposit "
                "leaves 7,000.00 due with a partial payment status and a "
                "journal entry that releases the deposit liability instead of "
                "adding revenue; the deposit stops showing as fully "
                "available. The Outstanding credits panel itself is asserted "
                "on a deposit the automatic application does not consume, "
                "because posting an invoice raised from the order applies its "
                "deposits before the panel is ever offered.",
    traceability=trace("TC-DEP-007"))
def test_dep_007(ctx):
    rpc = ctx.adapter.rpc
    created = {"account.move": [], "sale.order": [], "account.payment": [],
               "product.product": [], "res.partner": []}

    with ctx.step("Preconditions (workbook): TC-DEP-004 has passed — an "
                  "order of 10,000.00 carrying a 3,000.00 deposit — and "
                  "invoices can be posted"):
        require_sale_deposit(ctx)
        company = acting_company(ctx)
        sweep_fg06(ctx)
        account = deposit_accounts_for_test(ctx, CUSTOMER_SIDE,
                                            company["id"], wanted=1)[0]
        partner_id = make_partner(ctx, "DEP-007 Customer", company=company,
                                  customer_deposit_account_id=account["id"])
        created["res.partner"].append(partner_id)
        product_id = make_product(ctx, "DEP-007 Art Item", ORDER_TOTAL)
        created["product.product"].append(product_id)
        order_id = make_order(ctx, partner_id, [(product_id, 1, ORDER_TOTAL)],
                              confirm=True)
        created["sale.order"].append(order_id)

        wizard_action = open_make_deposit_wizard(ctx, order_id)
        payment_action = run_make_deposit_wizard(
            ctx, order_id, OPTION_FIXED, DEPOSIT,
            dict(wizard_action.get("context") or {}))
        popup = deposit_popup_state(ctx, payment_action)
        deposit_id, error = validate_deposit_popup(
            ctx, popup, side=CUSTOMER_SIDE, account_id=account["id"])
        ctx.check_true("The 3,000.00 deposit was taken against the order",
                       bool(deposit_id) and not error,
                       actual_desc=error or f"deposit #{deposit_id}")
        before = order_totals(ctx, order_id)
        ctx.check("Total Deposit on the order before invoicing", DEPOSIT,
                  before["deposit_total"])

    try:
        with ctx.step("Step 1: Create Invoice > Regular invoice"):
            invoice_id = invoice_from_order(ctx, order_id)
            ctx.check_true("An invoice was raised from the order",
                           bool(invoice_id),
                           actual_desc=f"invoice id {invoice_id!r}")
            draft = invoice_totals(ctx, invoice_id)
            ctx.log(f"draft invoice {draft['name']} — "
                    f"total={draft['amount_total']:.2f} "
                    f"state={draft['state']!r}")
            ctx.check("The invoice is raised for the full order amount",
                      ORDER_TOTAL, draft["amount_total"])
            ctx.check("…and starts in Draft", "draft", draft["state"])
            # Recorded because it is the reason the workbook's steps 3-5
            # cannot run in the order written: the panel is suppressed on a
            # draft move (account_partner_deposit/models/account_move.py:
            # 32-37).
            _log_panel(ctx, "Outstanding credits on the DRAFT invoice",
                       outstanding_credits(ctx, invoice_id))

        with ctx.step("Step 2: Confirm the invoice — and see the deposit "
                      "applied automatically"):
            rpc.call("account.move", "action_post", [invoice_id])
            posted = invoice_totals(ctx, invoice_id)
            ctx.log(f"posted invoice {posted['name']} — "
                    f"Amount Due={posted['amount_residual']:.2f} "
                    f"payment_state={posted['payment_state']!r}")
            ctx.check("The invoice posted", "posted", posted["state"])
            panel_after_post = outstanding_credits(ctx, invoice_id)
            _log_panel(ctx, "Outstanding credits immediately after Confirm",
                       panel_after_post)
            still_offered = [e for e in panel_after_post
                             if e["payment_id"] == deposit_id]
            if not still_offered:
                ctx.log(
                    "FINDING — the 3,000.00 deposit is NOT in the Outstanding "
                    "credits panel after Confirm, because it was already "
                    "APPLIED by Confirm itself. "
                    "sale_partner_deposit.account_move.action_post collects "
                    "invoice_line_ids.sale_line_ids.order_id.deposit_ids and "
                    "calls _reconcile_deposit, which calls "
                    "js_assign_outstanding_line for each "
                    "(sale_partner_deposit/models/account_move.py:7-17, "
                    "account_partner_deposit/models/account_move.py:245-262). "
                    "Once applied, the deposit line fails the panel's own "
                    "domain, which requires reconciled = False and a non-zero "
                    "residual (account_partner_deposit/models/account_move.py:"
                    "41-50); and before Confirm the panel is suppressed "
                    "entirely because the override returns early unless the "
                    "move is posted (:32-37). So on an invoice raised FROM "
                    "THE ORDER there is no moment at which the panel offers "
                    "that deposit, and the workbook's steps 3-5 ('expand "
                    "Outstanding credits ... click it to apply it') cannot be "
                    "performed in the order written. This is working code "
                    "meeting a workbook written against the manual path — the "
                    "step order needs correcting, NOT a defect. The panel's "
                    "own behaviour is asserted in the second half of this "
                    "test, on a deposit this automatic application does not "
                    "consume.")

        with ctx.step("Steps 6 / Expected lines 2-3: Amount Due is reduced by "
                      "3,000.00 and the status is a PARTIAL payment"):
            ctx.check("Amount Due on the 10,000.00 invoice after the "
                      "3,000.00 deposit", REMAINING,
                      posted["amount_residual"])
            ctx.check("The invoice's payment status is a partial payment, not "
                      "fully paid", PAYMENT_STATE_PARTIAL,
                      posted["payment_state"])

        with ctx.step("Step 7 / Expected line 5: the journal entry releases "
                      "the deposit liability rather than adding revenue"):
            row = payment_row(ctx, deposit_id)
            ctx.check_true(
                "An intermediate 'Deposit to Payment' entry was created and "
                "linked to the deposit",
                len(row["deposit_ids"]) == 1,
                actual_desc=f"account.payment.deposit_ids = "
                            f"{row['deposit_ids']}")
            entry_id = row["deposit_ids"][0]
            entry = rpc.read("account.move", [entry_id],
                             ["name", "ref", "state", "journal_id",
                              "is_deposit", "move_type"])[0]
            ctx.log(f"intermediate entry {entry.get('name')!r} "
                    f"ref={entry.get('ref')!r} state={entry.get('state')!r} "
                    f"journal={entry.get('journal_id')} "
                    f"is_deposit={entry.get('is_deposit')}")
            ctx.check("The intermediate entry is posted (BC-010: action_post, "
                      "not the v15 post())", "posted", entry.get("state"))
            ctx.check("…and is flagged as a deposit entry", True,
                      bool(entry.get("is_deposit")))
            ctx.check("…and carries the module's own reference",
                      DEPOSIT_ENTRY_REF, entry.get("ref"))
            if company["customer_deposit_journal_id"]:
                # DW-006: an unset company deposit journal falls back to a
                # general journal instead of raising a NOT NULL violation, so
                # this is only asserted when the company has one configured.
                ctx.check("…in the company's Customer Deposit journal",
                          company["customer_deposit_journal_id"],
                          (entry.get("journal_id") or [None])[0]
                          if isinstance(entry.get("journal_id"),
                                        (list, tuple))
                          else entry.get("journal_id"))
            lines = move_lines(ctx, entry_id)
            for line in lines:
                ctx.log(f"    {line['account_code']} "
                        f"{line['account_name']!r} "
                        f"[{line['account_type']}] "
                        f"debit={line['debit']:.2f} "
                        f"credit={line['credit']:.2f}")
            ctx.check("The intermediate entry debits the Deposit Account "
                      "(releasing the liability) for 3,000.00", DEPOSIT,
                      money(sum(ln["debit"] for ln in lines
                                if ln["account_id"] == account["id"])))
            ctx.check("…and credits the receivable, not a revenue account",
                      [],
                      [f"{ln['account_code']} {ln['account_name']} "
                       f"[{ln['account_type']}]" for ln in lines
                       if ln["account_type"] in REVENUE_TYPES])
            ctx.check("…with a receivable leg of 3,000.00", DEPOSIT,
                      money(sum(ln["credit"] for ln in lines
                                if ln["account_type"] == "asset_receivable")))

        with ctx.step("Step 8: the deposit no longer shows as fully "
                      "available"):
            deposit_lines = [ln for ln in move_lines(ctx, row["move_id"])
                             if ln["account_id"] == account["id"]]
            ctx.check("Exactly one deposit-account line on the deposit's own "
                      "entry", 1, len(deposit_lines))
            consumed = deposit_lines[0]
            ctx.log(f"deposit line #{consumed['id']} — "
                    f"reconciled={consumed['reconciled']} "
                    f"residual={consumed['amount_residual']:.2f}")
            ctx.check_true(
                "The deposit is no longer fully available (its line is "
                "reconciled, or its residual is zero)",
                consumed["reconciled"] or consumed["amount_residual"] == 0.0,
                actual_desc=f"reconciled={consumed['reconciled']}, "
                            f"amount_residual="
                            f"{consumed['amount_residual']:.2f}")

        with ctx.step("Expected lines 1 and 4, on the path where the panel is "
                      "reachable: a 3,000.00 deposit IS offered in "
                      "Outstanding credits, and applying it leaves 7,000.00"):
            # Same figures as the workbook, same code path as its step 5
            # (js_assign_outstanding_line) — reached the way a tester reaches
            # it when the deposit was taken on the accounting screen rather
            # than against the order, which is the only way the panel is ever
            # offered. See the module docstring.
            manual_partner_id = make_partner(
                ctx, "DEP-007 Panel Customer", company=company,
                customer_deposit_account_id=account["id"])
            created["res.partner"].append(manual_partner_id)
            manual_deposit_id = make_deposit(
                ctx, manual_partner_id, DEPOSIT, account_id=account["id"],
                side=CUSTOMER_SIDE, post=True, memo="UAT panel deposit")
            manual_invoice_id = make_invoice(
                ctx, manual_partner_id, [(product_id, 1, ORDER_TOTAL)],
                post=True)
            entries = outstanding_credits(ctx, manual_invoice_id)
            _log_panel(ctx, "Outstanding credits on the manual invoice",
                       entries)
            offered = [e for e in entries
                       if e["payment_id"] == manual_deposit_id]
            ctx.check("The deposit is offered in Outstanding credits", 1,
                      len(offered))
            ctx.check("…for 3,000.00", DEPOSIT, offered[0]["amount"])
            _assert_owl_contract(ctx, entries)
            # The workbook's own instruction, recorded rather than asserted —
            # see the module docstring for why.
            ctx.log(
                f"OBSERVATION (workbook: NOT a defect) — the panel labels its "
                f"entries with the journal and payment method, not with the "
                f"word 'Deposit'. Labels seen: "
                f"{[e['journal_name'] for e in entries]}. Decision D3-a: the "
                f"legacy t-extend/t-jquery QWeb override that stamped the "
                f"'Deposit' label was deliberately not ported, because that "
                f"inheritance was removed in Odoo 16 and the v19 OWL popover "
                f"has no such slot (account_partner_deposit/__manifest__.py:"
                f"34-41). The workbook says to close the case as a pass and "
                f"note the observation, which is what this line is.")

            before_apply = invoice_totals(ctx, manual_invoice_id)
            ctx.check("The manual invoice starts fully due", ORDER_TOTAL,
                      before_apply["amount_residual"])
            apply_outstanding_credit(ctx, manual_invoice_id,
                                     offered[0]["line_id"])
            after_apply = invoice_totals(ctx, manual_invoice_id)
            ctx.log(f"after clicking the deposit — Amount Due="
                    f"{after_apply['amount_residual']:.2f} "
                    f"payment_state={after_apply['payment_state']!r}")
            ctx.check("Clicking the deposit reduces Amount Due by 3,000.00, "
                      "leaving 7,000.00 on a 10,000.00 invoice", REMAINING,
                      after_apply["amount_residual"])
            ctx.check("…and the payment status is a partial payment",
                      PAYMENT_STATE_PARTIAL, after_apply["payment_state"])
            ctx.check_true(
                "The applied deposit is no longer offered in the panel",
                not [e for e in outstanding_credits(ctx, manual_invoice_id)
                     if e["payment_id"] == manual_deposit_id],
                actual_desc="the panel no longer lists it")
    finally:
        with ctx.step("Cleanup: remove FG06 fixtures (the part-paid invoice "
                      "and its deposit stay — the workbook's State After The "
                      "Test is 'An invoice part-paid by a deposit, with "
                      "7,000.00 still due')"):
            for key in ("account.move", "account.payment"):
                if created.get(key):
                    ctx.log(f"{key} fixtures {created[key]} left in place: a "
                            f"posted move or payment cannot be unlinked")
                    created[key] = []
            cleanup(ctx, created)


@test_case(
    id="TEST-FG06-DEP-009",
    name="A customer's unused deposits are offered on their next invoice",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P1",
    kind="API",
    order=610,
    description="A confirmed 2,500.00 deposit is offered on the customer's "
                "next 4,000.00 invoice; a second deposit that was saved but "
                "not confirmed is NOT offered, because the panel gates on the "
                "journal entry rather than the payment state (BC-016); and no "
                "other customer's deposit appears in either check.",
    traceability=trace("TC-DEP-009"))
def test_dep_009(ctx):
    created = {"account.move": [], "account.payment": [],
               "product.product": [], "res.partner": []}

    with ctx.step("Preconditions (workbook): TC-DEP-001 has passed — one "
                  "confirmed 2,500.00 deposit for a customer with no other "
                  "outstanding balance"):
        require_v19(ctx)
        company = acting_company(ctx)
        sweep_fg06(ctx)
        account = deposit_accounts_for_test(ctx, CUSTOMER_SIDE,
                                            company["id"], wanted=1)[0]
        partner_id = make_partner(ctx, "DEP-009 Customer", company=company,
                                  customer_deposit_account_id=account["id"])
        created["res.partner"].append(partner_id)
        product_id = make_product(ctx, "DEP-009 Art Item", DEP009_INVOICE)
        created["product.product"].append(product_id)
        confirmed_id = make_deposit(
            ctx, partner_id, DEP009_DEPOSIT, account_id=account["id"],
            side=CUSTOMER_SIDE, post=True, memo="UAT DEP-009 confirmed")
        confirmed = payment_row(ctx, confirmed_id)
        ctx.check_true(
            "The 2,500.00 deposit is confirmed (its journal entry is posted)",
            confirmed["move_state"] == "posted",
            actual_desc=f"payment state={confirmed['state']!r}, entry "
                        f"state={confirmed['move_state']!r}")
        # "That customer has NO other outstanding balance, so the picture is
        # clean" — a fresh FG06 contact, asserted rather than assumed.
        other_moves = ctx.adapter.rpc.search(
            "account.move",
            [("partner_id", "=", partner_id), ("state", "=", "posted"),
             ("move_type", "in", ("out_invoice", "out_refund"))])
        ctx.check("The customer has no other posted invoice, so the panel "
                  "picture is clean", [], other_moves)

        # The workbook's last Expected Result line needs a second customer to
        # be meaningful: "No deposit belonging to a different customer appears
        # in either check."
        other_partner_id = make_partner(
            ctx, "DEP-009 Other Customer", company=company,
            customer_deposit_account_id=account["id"])
        created["res.partner"].append(other_partner_id)
        other_deposit_id = make_deposit(
            ctx, other_partner_id, 9999.00, account_id=account["id"],
            side=CUSTOMER_SIDE, post=True, memo="UAT DEP-009 other customer")

    try:
        with ctx.step("Steps 1-2: a new 4,000.00 invoice for that customer, "
                      "saved and confirmed"):
            invoice_id = make_invoice(ctx, partner_id,
                                     [(product_id, 1, DEP009_INVOICE)],
                                     post=True)
            posted = invoice_totals(ctx, invoice_id)
            ctx.log(f"invoice {posted['name']} — "
                    f"total={posted['amount_total']:.2f} "
                    f"Amount Due={posted['amount_residual']:.2f} "
                    f"state={posted['state']!r}")
            ctx.check("The invoice posted", "posted", posted["state"])
            ctx.check("The invoice total", DEP009_INVOICE,
                      posted["amount_total"])
            # A standalone invoice has no sale order behind it, so
            # sale_partner_deposit's auto-application cannot fire and the
            # panel is genuinely offered — which is what this case needs.
            ctx.check("The invoice is still fully due, so the deposit has "
                      "not been auto-applied", DEP009_INVOICE,
                      posted["amount_residual"])

        with ctx.step("Steps 3-4 / Expected line 1: the confirmed 2,500.00 "
                      "deposit is listed — the panel is not empty"):
            entries = outstanding_credits(ctx, invoice_id)
            _log_panel(ctx, "Outstanding credits, first check", entries)
            mine = [e for e in entries if e["payment_id"] == confirmed_id]
            # The workbook's If It Fails: "An empty panel when a confirmed
            # deposit exists is a P0 — raise it immediately."
            ctx.check_true(
                "The Outstanding credits panel is not empty",
                bool(entries),
                actual_desc=f"{len(entries)} entr(ies) offered")
            ctx.check("The confirmed 2,500.00 deposit is listed exactly once",
                      1, len(mine))
            ctx.check("…for 2,500.00", DEP009_DEPOSIT, mine[0]["amount"])
            _assert_owl_contract(ctx, entries)

        with ctx.step("Expected line 3 (first check): no other customer's "
                      "deposit appears"):
            ctx.check(f"The other customer's 9,999.00 deposit "
                      f"(#{other_deposit_id}) is not offered on this "
                      f"customer's invoice", [],
                      [e["line_id"] for e in entries
                       if e["payment_id"] == other_deposit_id])

        with ctx.step("Step 5: create a SECOND deposit of 1,000.00, saved but "
                      "NOT confirmed"):
            draft_id = make_deposit(
                ctx, partner_id, DEP009_DRAFT, account_id=account["id"],
                side=CUSTOMER_SIDE, post=False, memo="UAT DEP-009 draft")
            created["account.payment"].append(draft_id)
            draft = payment_row(ctx, draft_id)
            ctx.log(f"unconfirmed deposit #{draft_id} — payment "
                    f"state={draft['state']!r}, journal entry "
                    f"state={draft['move_state']!r}")
            # BC-016 made visible: the payment already reads 'in_process'
            # while its entry is still draft, which is exactly why the panel
            # has to gate on the entry.
            ctx.check("The unconfirmed deposit's journal entry is NOT posted",
                      "draft", draft["move_state"])
            if draft["state"] != "draft":
                ctx.log(
                    f"NOTE — the unconfirmed deposit reads payment "
                    f"state={draft['state']!r}, not 'draft'. That is v19 "
                    f"behaviour (BC-016): _generate_journal_entry runs at "
                    f"create time for any payment carrying "
                    f"write_off_line_vals and stamps 'in_process' "
                    f"(addons/account/models/account_payment.py:1080). It is "
                    f"the reason the panel's domain gates on "
                    f"parent_state = 'posted' rather than on the payment "
                    f"state (account_partner_deposit/models/account_move.py:"
                    f"41-50); filtering on the payment state alone would "
                    f"offer money that was never received.")

        with ctx.step("Steps 6-7 / Expected line 2: the DRAFT 1,000.00 "
                      "deposit does NOT appear — only confirmed money may be "
                      "offered"):
            again = outstanding_credits(ctx, invoice_id)
            _log_panel(ctx, "Outstanding credits, second check", again)
            ctx.check("The unconfirmed 1,000.00 deposit is not offered", [],
                      [e["line_id"] for e in again
                       if e["payment_id"] == draft_id])
            # "the list is neither empty nor over-full" — both halves.
            ctx.check("The confirmed deposit is still offered after the draft "
                      "one was added", 1,
                      len([e for e in again
                           if e["payment_id"] == confirmed_id]))
            ctx.check("The panel offers no more entries than before",
                      len(entries), len(again))

        with ctx.step("Expected line 3 (second check): still no other "
                      "customer's deposit"):
            ctx.check(f"The other customer's deposit (#{other_deposit_id}) is "
                      f"still not offered", [],
                      [e["line_id"] for e in again
                       if e["payment_id"] == other_deposit_id])
    finally:
        with ctx.step("Cleanup: remove FG06 fixtures"):
            # The workbook's State After The Test is "One posted 4,000.00
            # invoice with a deposit available against it, and one draft
            # 1,000.00 deposit. Leave both." The posted invoice and the
            # confirmed deposit cannot be unlinked and do stay. The DRAFT
            # deposit is deliberately swept: AUTOMATION_CONVENTIONS rule 3
            # requires each run to start from the same state, and rule 5
            # forbids a later case from depending on it — so the end state is
            # reproduced by whichever case needs it, never inherited.
            ctx.log("the posted 4,000.00 invoice and the confirmed 2,500.00 "
                    "deposit stay in place (neither can be unlinked); the "
                    "DRAFT 1,000.00 deposit is swept so this case is "
                    "repeatable, and no later case inherits it")
            created["account.move"] = []
            cleanup(ctx, created)
