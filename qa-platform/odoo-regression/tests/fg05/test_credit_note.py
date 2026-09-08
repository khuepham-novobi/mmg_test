"""FG-05 — TC-TAX-015: a credit note books its tax to the AvaTax Refund Account.

What this proves (workbook Expected Result, four lines, four assertions)
-----------------------------------------------------------------------
1. The source invoice's journal-entry tax line sits on the fiscal position's
   **Avatax Invoice Account**.
2. The credit note's tax line sits on the **Avatax Refund Account**, and that
   is a DIFFERENT account — both the code match and the inequality are
   asserted.
3. The credit note's tax amount equals the invoice's tax amount.
4. The credit note appears in Accounting > Customers > Credit Notes
   (``move_type == 'out_refund'`` and posted).

Why it matters (workbook Business Purpose): tax on a refund must land on a
different account from tax on a sale, so the two never net off invisibly in
the tax return. The fiscal position holds one account per direction —
``account_avatax/models/account_external_tax_mixin.py`` lines 187/191 put
``avatax_invoice_account_id`` on the tax's ``invoice_repartition_line_ids``
and ``avatax_refund_account_id`` on its ``refund_repartition_line_ids``, so
the direction of the move alone decides where the tax posts.

Documented adaptation — the cross-test dependency is broken
-----------------------------------------------------------
The workbook's preconditions say "TC-TAX-001 has passed and its invoice is
posted", and its Test Data is "the posted invoice from TC-TAX-001". The
platform forbids depending on another test's fixtures (authoring brief,
"Cross-test dependencies"), so this test **builds and posts its own
equivalent of that invoice** inside itself, using TC-TAX-001's own test data
(a US customer with a complete Phoenix AZ address carrying the AvaTax fiscal
position, one stock-art line, quantity 1, price 1,000.00). The business
assertions below are unchanged from the workbook.

Documented adaptation — the two-account precondition is a gate, not a failure
-----------------------------------------------------------------------------
The workbook precondition is explicit: the Avatax Invoice Account and the
Avatax Refund Account "must be DIFFERENT codes for this test to mean
anything", and its If-It-Fails column says that when both documents use the
same account and the fiscal position does not actually hold two different
accounts, "the defect is in the setup and belongs to TC-DAT-017, not here".
This test therefore reports BLOCKED (never FAILED) when either account is
missing or the two resolve to the same account, naming TC-DAT-017 as the
owner of that setup gap.

Sign convention on the tax amount
---------------------------------
``account.move.amount_tax`` is ``direction_sign * total_tax_currency``
(``addons/account/models/account_move.py::_compute_amount``), and
``direction_sign`` is -1 for ``out_invoice`` but +1 for ``out_refund``
(``_compute_direction_sign``) — while the tax journal items themselves flip
from credit to debit between the two moves. On top of that,
``account_avatax``'s ``_extract_tax_values_from_avatax_detail`` multiplies
Avalara's per-jurisdiction amount by -1 for a ``ReturnInvoice``. MMG's
``mmg_account_avatax_enhancement/models/account_move.py::_check_avatax_tax_total``
(branch ``staging_19``) mirrors exactly that: it flips the Avalara total for
``out_refund``/``in_refund`` before comparing. The workbook's expectation is
about magnitude, so the equality below compares absolute values and the raw
signed figures are logged as evidence.

State after the test — and why teardown must NOT delete the two moves
---------------------------------------------------------------------
One posted invoice and one posted credit note fully reversing it — exactly
the state the workbook's "State After The Test" column describes. Leaving
them in place is required twice over: Odoo refuses the delete, and the
attempt would already have cost two live Avalara VOID calls.

**The delete fails.** ``account.move.unlink()``
(``addons/account/models/account_move.py`` line 4077) enters with
``dynamic_unlink=True`` but **not** ``force_delete``, then calls
``self.line_ids.unlink()``. That trips the ``@api.ondelete`` hook
``account.move.line._unlink_except_posted``
(``addons/account/models/account_move_line.py`` lines 1954-1960), which raises
``UserError("You can't delete a posted journal item...")`` for every non-zero
line of a posted move. ``dynamic_unlink`` only bypasses the *other* hook,
``_prevent_automatic_line_deletion`` (line 1962).

**But the void has already gone out.** ``account_external_tax``'s override
(``account_external_tax/models/account_move.py`` lines 15-17) runs
``self._filtered_external_tax_moves()._void_external_taxes()`` BEFORE
``super().unlink()``, and ``account_avatax`` implements that hook as
``_change_avatax_state('void')`` -> ``client.void_transaction()``. Odoo rolls
the database transaction back; it cannot roll back an HTTP call. Handing a
posted move to ``cleanup`` would therefore leave the invoice alive in Odoo
with its Avalara transaction VOIDED — Odoo and Avalara silently out of sync —
while the teardown log reports the refusal as a harmless "posted documents
cannot be deleted".

Each move id is therefore held in ``created`` only while the move is still a
draft, so a failure before posting is still cleaned up, and is dropped from
``created`` the moment its posted state has been asserted. ``sweep_fg05``
leaves them alone for the same reason: it only sweeps moves whose ``state``
is ``draft`` or ``cancel``. The partner and product fixtures are removed as
usual.
"""
from __future__ import annotations

from framework.registry import test_case
from tests.fg05.common import (ADDRESS_PHOENIX_AZ, MODULE, WORKFLOW,
                               WORKFLOW_NAME, account_code, cleanup,
                               compute_taxes, doc_totals, make_invoice,
                               make_partner, make_product, move_tax_lines,
                               require_avatax_fiscal_position, require_sandbox,
                               sweep_fg05, trace)

# TC-TAX-001 test data, reproduced here because this test builds its own
# source invoice instead of reusing TC-TAX-001's (see module docstring).
SOURCE_PRICE = 1000.00
SOURCE_QTY = 1


def _m2o_id(value):
    """A many2one reads back over RPC as ``[id, display_name]`` (or False)."""
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    return value or None


@test_case(
    id="TEST-FG05-TAX-015",
    name="A credit note books its tax to the AvaTax Refund Account",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P1",
    kind="API",
    order=511,
    description="A full credit note of an AvaTax invoice posts its tax to the "
                "fiscal position's Avatax Refund Account — a different account "
                "from the Avatax Invoice Account the invoice used — for the "
                "same tax amount.",
    traceability=trace("TC-TAX-015"))
def test_tax_015(ctx):
    rpc = ctx.adapter.rpc
    created = {"account.move": [], "product.product": [], "res.partner": []}

    with ctx.step("Precondition: Odoo 19 on the Avalara SANDBOX, and an "
                  "AvaTax fiscal position holding two DIFFERENT accounts"):
        require_sandbox(ctx, "computing tax on a customer invoice and on the "
                             "credit note that reverses it")
        fp_id, fp = require_avatax_fiscal_position(ctx)
        invoice_account_id = _m2o_id(fp.get("avatax_invoice_account_id"))
        refund_account_id = _m2o_id(fp.get("avatax_refund_account_id"))
        setup_owner = (
            "The fiscal position's two AvaTax accounts are the setup TC-DAT-017 "
            "verifies (its step 5: 'open the Avatax tab and tick off Avatax "
            "Invoice Account and Avatax Refund Account against the printout'). "
            "TC-TAX-015 cannot distinguish a refund posted to the wrong account "
            "from a fiscal position that never held two accounts, so per its own "
            "If-It-Fails column this is TC-DAT-017's defect, not this case's.")
        if not invoice_account_id or not refund_account_id:
            missing = []
            if not invoice_account_id:
                missing.append("Avatax Invoice Account "
                               "(account.fiscal.position.avatax_invoice_account_id)")
            if not refund_account_id:
                missing.append("Avatax Refund Account "
                               "(account.fiscal.position.avatax_refund_account_id)")
            ctx.blocked(
                f"fiscal position #{fp_id} {fp.get('name')!r} has no "
                f"{' and no '.join(missing)}. Without it the AvaTax tax "
                f"repartition line carries no account and the tax falls back to "
                f"the base line's account, so 'the credit note's tax line sits "
                f"on the Avatax Refund Account' cannot be evaluated. "
                f"{setup_owner}")
        invoice_code = account_code(ctx, invoice_account_id)
        refund_code = account_code(ctx, refund_account_id)
        if invoice_account_id == refund_account_id or invoice_code == refund_code:
            ctx.blocked(
                f"fiscal position #{fp_id} {fp.get('name')!r} points both AvaTax "
                f"accounts at the same account: Avatax Invoice Account "
                f"#{invoice_account_id} code {invoice_code!r}, Avatax Refund "
                f"Account #{refund_account_id} code {refund_code!r}. The "
                f"workbook precondition requires DIFFERENT codes 'for this test "
                f"to mean anything' — with one account the invoice and the "
                f"credit note necessarily agree and the assertion proves "
                f"nothing. {setup_owner}")
        ctx.log(f"fiscal position #{fp_id} {fp.get('name')!r} — "
                f"Avatax Invoice Account #{invoice_account_id} code "
                f"{invoice_code!r}, Avatax Refund Account #{refund_account_id} "
                f"code {refund_code!r}")
        sweep_fg05(ctx)

    try:
        with ctx.step("Precondition (documented adaptation): build and post "
                      "this test's own equivalent of the TC-TAX-001 invoice"):
            partner_id = make_partner(ctx, "TAX-015 Credit Note Customer",
                                      ADDRESS_PHOENIX_AZ,
                                      fiscal_position_id=fp_id)
            created["res.partner"].append(partner_id)
            product_id = make_product(ctx, "TAX-015 Art Item", SOURCE_PRICE)
            created["product.product"].append(product_id)
            invoice_id = make_invoice(
                ctx, partner_id, [(product_id, SOURCE_QTY, SOURCE_PRICE)],
                fiscal_position_id=fp_id)
            # Tracked for teardown only while it is a draft — see the module
            # docstring: unlinking a POSTED move fails in Odoo 19, but only
            # after account_external_tax has already sent the Avalara VOID,
            # which cannot be rolled back.
            created["account.move"].append(invoice_id)
            compute_taxes(ctx, "account.move", invoice_id)
            rpc.call("account.move", "action_post", [invoice_id])
            invoice_totals = doc_totals(ctx, "account.move", invoice_id)
            # Stop tracking the move the INSTANT posting is proven, with no
            # other assertion in between. A failure of any later check would
            # otherwise propagate to the outer finally: with the id still in
            # ``created``, and cleanup would call unlink() on a posted move —
            # which sends the Avalara void BEFORE the delete is refused
            # (see the module docstring).
            ctx.check("source invoice is posted", "posted",
                      invoice_totals["state"])
            created["account.move"].remove(invoice_id)
            ctx.check("source invoice Untaxed Amount (TC-TAX-001 test data)",
                      round(SOURCE_PRICE * SOURCE_QTY, 2),
                      invoice_totals["untaxed"])
            ctx.check_true(
                "source invoice carries a non-zero AvaTax tax",
                invoice_totals["tax"] != 0,
                actual_desc=f"amount_tax={invoice_totals['tax']} "
                            f"amount_total={invoice_totals['total']} "
                            f"Avalara Code={invoice_totals['avalara_code']!r}")

        with ctx.step("Step 1 (workbook): open the posted invoice's Journal "
                      "Entry and read the account code on its tax line"):
            invoice_tax_lines = move_tax_lines(ctx, invoice_id)
            ctx.check_true(
                "the posted invoice has at least one tax journal item",
                bool(invoice_tax_lines),
                actual_desc=f"{len(invoice_tax_lines)} tax line(s): "
                            f"{[(line['tax_name'], line['account'], line['balance']) for line in invoice_tax_lines]}")
            invoice_line_account_ids = {line["account_id"]
                                        for line in invoice_tax_lines}
            invoice_line_codes = sorted(
                {account_code(ctx, account_id)
                 for account_id in invoice_line_account_ids})
            # Expected Result 1 — a multi-jurisdiction address (Phoenix AZ)
            # produces several tax lines, but every one of them must sit on the
            # single Avatax Invoice Account, so the distinct set is compared.
            ctx.check("invoice tax line account code(s) = Avatax Invoice "
                      "Account", [invoice_code], invoice_line_codes)

        with ctx.step("Step 2 (workbook): click Credit Note in the header, "
                      "choose a FULL credit and confirm"):
            action = rpc.call("account.move", "action_reverse", [invoice_id])
            ctx.check("Credit Note opens the account.move.reversal wizard",
                      "account.move.reversal",
                      (action or {}).get("res_model"))
            # account.move.reversal.default_get reads active_model/active_ids
            # to fill move_ids and the required company_id
            # (addons/account/wizard/account_move_reversal.py:66-82); move_ids
            # is passed as well so the wizard is well-formed either way.
            wizard_id = rpc.call(
                "account.move.reversal", "create",
                {"move_ids": [(6, 0, [invoice_id])]},
                context={"active_model": "account.move",
                         "active_id": invoice_id,
                         "active_ids": [invoice_id]})
            # The wizard's own footer buttons: "Reverse" = refund_moves()
            # (a full credit note, reverse_moves(is_modify=False)) and
            # "Reverse and Create Invoice" = modify_moves(), which would also
            # raise a replacement draft invoice. The workbook's "full credit"
            # is refund_moves()
            # (addons/account/wizard/account_move_reversal_view.xml).
            reversal_action = rpc.call("account.move.reversal",
                                       "refund_moves", [wizard_id])
            credit_note_id = None
            if isinstance(reversal_action, dict):
                credit_note_id = reversal_action.get("res_id")
            if not credit_note_id:
                # reverse_moves() also stores the result on the wizard
                # (self.new_move_ids = moves_to_redirect, line 153).
                wizard = rpc.read("account.move.reversal", [wizard_id],
                                  ["new_move_ids"])[0]
                new_moves = wizard.get("new_move_ids") or []
                credit_note_id = new_moves[0] if new_moves else None
            ctx.check_true("the full credit produced exactly one credit note",
                           bool(credit_note_id),
                           actual_desc=f"credit note id={credit_note_id!r} "
                                       f"(wizard #{wizard_id})")
            # Draft at this point, so tracked for teardown; dropped again as
            # soon as Step 3 has asserted it posted.
            created["account.move"].insert(0, credit_note_id)

        with ctx.step("Step 3 (workbook): click Compute Taxes on the credit "
                      "note if the tax figure is not already there, then "
                      "Confirm"):
            credit_before = doc_totals(ctx, "account.move", credit_note_id)
            ctx.check("credit note reverses the FULL untaxed amount",
                      abs(invoice_totals["untaxed"]),
                      abs(credit_before["untaxed"]))
            if not credit_before["tax"]:
                ctx.log("credit note had no tax figure yet — clicking Compute "
                        "Taxes (button_external_tax_calculation)")
                compute_taxes(ctx, "account.move", credit_note_id)
            else:
                ctx.log(f"credit note already carried a tax figure "
                        f"({credit_before['tax']}) — Compute Taxes skipped, as "
                        f"the workbook step allows")
            rpc.call("account.move", "action_post", [credit_note_id])
            credit_totals = doc_totals(ctx, "account.move", credit_note_id)
            ctx.check("credit note is posted", "posted",
                      credit_totals["state"])
            # Posted and asserted — stop tracking it, for the same two reasons
            # as the source invoice above.
            created["account.move"].remove(credit_note_id)

        with ctx.step("Step 4-6 (workbook): open the posted credit note's "
                      "Journal Entry, read the account code on its tax line "
                      "and compare it with the Avatax Refund Account"):
            credit_tax_lines = move_tax_lines(ctx, credit_note_id)
            ctx.check_true(
                "the posted credit note has at least one tax journal item",
                bool(credit_tax_lines),
                actual_desc=f"{len(credit_tax_lines)} tax line(s): "
                            f"{[(line['tax_name'], line['account'], line['balance']) for line in credit_tax_lines]}")
            credit_line_account_ids = {line["account_id"]
                                       for line in credit_tax_lines}
            credit_line_codes = sorted(
                {account_code(ctx, account_id)
                 for account_id in credit_line_account_ids})
            # Expected Result 2, first half — the code match.
            ctx.check("credit note tax line account code(s) = Avatax Refund "
                      "Account", [refund_code], credit_line_codes)
            # Expected Result 2, second half — "a DIFFERENT account". Asserted
            # on the account ids as well as the codes, so two distinct accounts
            # sharing a code would not pass as one.
            ctx.check_true(
                "credit note tax account differs from the invoice tax account",
                credit_line_account_ids.isdisjoint(invoice_line_account_ids)
                and credit_line_codes != invoice_line_codes,
                actual_desc=f"invoice tax account(s) "
                            f"{sorted(invoice_line_account_ids)} code(s) "
                            f"{invoice_line_codes} vs credit note "
                            f"{sorted(credit_line_account_ids)} code(s) "
                            f"{credit_line_codes}")

        with ctx.step("Expected Result (workbook): the credit note's tax "
                      "amount equals the invoice's tax amount"):
            # The two moves carry opposite signs by construction — the invoice's
            # tax journal items are credits and the credit note's are debits,
            # account.move.direction_sign is -1 for out_invoice and +1 for
            # out_refund, and account_avatax multiplies Avalara's per-
            # jurisdiction amount by -1 for a ReturnInvoice. MMG's
            # mmg_account_avatax_enhancement/models/account_move.py::
            # _check_avatax_tax_total (staging_19) flips the Avalara total the
            # same way for out_refund/in_refund before comparing it with
            # amount_tax. The workbook's expectation is about magnitude, so
            # absolute values are compared and the signed figures are evidence.
            ctx.log(f"signed figures — invoice amount_tax="
                    f"{invoice_totals['tax']}, credit note amount_tax="
                    f"{credit_totals['tax']}; invoice tax line balances="
                    f"{[line['balance'] for line in invoice_tax_lines]}, "
                    f"credit note tax line balances="
                    f"{[line['balance'] for line in credit_tax_lines]}")
            ctx.check("credit note tax amount equals the invoice's "
                      "(absolute value)",
                      abs(invoice_totals["tax"]), abs(credit_totals["tax"]))

        with ctx.step("Expected Result (workbook): the credit note appears in "
                      "Accounting > Customers > Credit Notes"):
            data = rpc.read("account.move", [credit_note_id],
                            ["name", "move_type", "state",
                             "reversed_entry_id"])[0]
            ctx.check("credit note move_type", "out_refund",
                      data["move_type"])
            ctx.check("credit note state", "posted", data["state"])
            ctx.check("credit note reverses the source invoice", invoice_id,
                      _m2o_id(data["reversed_entry_id"]))
            # The Credit Notes menu action is account.action_move_out_refund_type:
            # domain [('move_type','in',['out_invoice','out_refund'])] with the
            # search filter 'out_refund' ([('move_type','=','out_refund')])
            # applied by default (addons/account/views/account_move_views.xml
            # lines 2167-2175 and 1720-1722). Scoped to this test's own id so
            # live data cannot leak into the assertion.
            listed = rpc.search("account.move",
                                [("id", "=", credit_note_id),
                                 ("move_type", "in",
                                  ["out_invoice", "out_refund"]),
                                 ("move_type", "=", "out_refund")])
            ctx.check_true(
                "the credit note is returned by the Credit Notes list domain",
                listed == [credit_note_id],
                actual_desc=f"credit note {data['name']!r} (id "
                            f"{credit_note_id}) — Credit Notes list returns "
                            f"{listed}")
    finally:
        with ctx.step("Cleanup: remove the FG05 partner/product fixtures and "
                      "any move still in draft. Both posted moves are kept on "
                      "purpose — the workbook's State After The Test requires "
                      "them, and deleting them would fire a live Avalara VOID "
                      "(Odoo 19 would otherwise allow the delete)"):
            cleanup(ctx, created)
