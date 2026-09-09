"""FG-07 — TC-INV-004: An invoice paid by a cheque still in transit reads 'Paid'.

Implements row 35.0 (P2, "Payment status") of the CLIENT MANUAL TESTING
GUIDELINE ``MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0.xlsx`` /
sheet ``Testing Guideline``.

The workbook's framing: *"When a cheque has been banked but not yet cleared,
Odoo's own wording is 'In Payment'. The gallery's staff read that as unpaid
and chase the customer. The word must read 'Paid'."*

Why this case is not a one-line label check
-------------------------------------------
The word only appears once the invoice actually reaches the ``in_payment``
payment state, and reaching it needs three things to line up. All three were
read out of the Odoo 19 source rather than assumed, because getting any of
them wrong makes the case pass vacuously — a 'Paid' reading on an invoice
that went straight to ``paid`` proves nothing at all:

1. **The Enterprise module ``accountant`` must be installed.**
   ``account.move._get_invoice_in_payment_state`` returns ``'paid'`` in
   Community (``addons/account/models/account_move.py:7350-7354``) and is
   overridden to return ``'in_payment'`` only by
   ``enterprise-19.0/accountant/models/account_move.py:7-9``. Note this is
   **not** the module called ``account_accountant``, which in Odoo 19 is
   named "Invoicing" (``enterprise-19.0/account_accountant/__manifest__.py:4``)
   and carries none of that behaviour. The gate therefore probes
   ``ir.module.module`` for ``accountant`` — never ``model_exists``.
2. **The payment must route through an outstanding / transit account.** The
   outstanding account is the *payment method line's* ``payment_account_id``
   (``addons/account/models/account_payment.py:620-623``), not a property of
   the journal, so the workbook's "ask Novobi which journal to use" is
   resolved here by searching ``account.payment.method.line`` directly. Two
   configurations must be excluded or the invoice short-circuits to ``paid``:
   a method line whose ``payment_account_id`` equals the journal's own
   ``default_account_id`` forces ``is_matched = True``
   (``account_payment.py:489-492``), and an outstanding account of type
   ``asset_cash`` sends ``action_post`` straight to state ``paid``
   (``account_payment.py:1141``).
3. **The payment must stay unmatched.** ``_compute_payment_state`` only
   reaches the in-payment state when the residual is zero *and* not every
   reconciliation is matched (``account_move.py:1298-1302``).

The 4 Expected Result lines, and what each is read from
-------------------------------------------------------
1. **"Step 4: the ribbon on the invoice reads Paid. It does not read 'In
   Payment'."** — read from the ``web_ribbon`` widgets of
   ``account.view_move_form`` as ``get_view`` serves them (stock arch:
   ``addons/account/views/account_move_views.xml:918-940``). Odoo 19 ships
   **eight** ribbons there and the in-payment one is the *fourth*
   (``:927-928``, stock title ``"In Payment"``) — the v15 port relabelled it
   with ``//sheet/widget[@name='web_ribbon'][2]``
   (``psus-medicine-man-gallery/mmg_change_ui/views/account_move_views.xml:8-11``),
   and position ``[2]`` in v19 is the *second* "Sent" ribbon
   (``:922-924``). So this case selects the ribbon by the state it is gated
   on — an ``invisible`` expression carrying the quoted literal
   ``'in_payment'`` — never by position. (Substring matching on the bare word
   would be wrong too: ``status_in_payment != 'sent'`` on the second Sent
   ribbon contains it.)
2. **"Step 7: the Status column reads Paid."** — read from two places that
   must agree. The column itself is ``status_in_payment`` in
   ``account.view_invoice_tree``, labelled ``string="Status"`` with
   ``widget="badge"`` and ``optional="show"``
   (``account_move_views.xml:550-559``) — the v15 port's
   ``payment_state_clone`` column is not what v19 displays, so it is not what
   is read. The word itself is the field's own selection label
   (``account_move.py:613-621``, built from ``PAYMENT_STATE_SELECTION`` at
   ``:49-57`` where ``in_payment`` reads ``"In Payment"`` in stock). Every
   column the list labels "Status" is graded, whichever field backs it, so a
   port done either way is read the way the accountant reads it.
3. **"Step 8: a filter named 'In payment' still exists in the search panel.
   This is EXPECTED and is not a defect."** — read from
   ``account.view_account_invoice_filter``,
   ``<filter name="in_payment" string="In payment" …/>``
   (``account_move_views.xml:1730``). Asserted **positively**: the workbook
   lists it as an expected result, so its survival is graded, and it is
   additionally logged as an OBSERVATION so nobody raises it as a defect.
4. **"No blank value and no error anywhere."** — every entry of
   ``payment_state`` and ``status_in_payment`` must carry a non-empty label
   (including v19's new ``blocked`` state, ``account_move.py:55``), and the
   live invoice's Status must not read blank. The workbook's If It Fails
   column is explicit that a BLANK status outranks a wrong word and is a P1,
   and ``_compute_status_in_payment`` (``account_move.py:1327-1340``) falls
   back to ``move.state``, so a blank means the compute produced nothing at
   all. Every RPC in this case is wrapped, so an escaping error cannot be
   mistaken for a product fault.

Documented adaptation — the platform reads the arch, not the pixels
-------------------------------------------------------------------
Steps 4 and 7 are visual reads ("look at the ribbon … read its word"). This
case is registered as an API test and reads the same two things the browser
renders from: the view architecture ``get_view`` returns, and the record's
own stored value plus the field's selection label. What it cannot see is the
rendered screen — whether an OWL override, a CSS rule or a badge decoration
hides or restyles the ribbon after the arch is served. That last mile is
recorded as a RESIDUAL MANUAL STEP carrying the captured words, so the human
confirms pixels rather than re-deriving the values.

A finding this case will surface
--------------------------------
The search filter in the side panel still reads "In payment" while the
column, the badge and the ribbon read "Paid". The workbook says READ THIS
FIRST that this is a known cosmetic inconsistency and **not** a defect, so it
is asserted as an expected result *and* logged through
``common.observation`` — never raised. The second finding this case is built
to catch is the opposite of a label problem: the payment routing. If the
chosen method line sends the invoice straight to ``paid``, the case is
BLOCKED with the full configuration printed, because the workbook itself says
"with the wrong journal the invoice goes straight to Paid and this case
cannot be run" — reporting that as a FAILED relabelling would send the
gallery hunting for a bug in the wrong module.

Source trees these citations were read from: Odoo 19 Community
``D:/Projects/odoo-19.0/addons``, Odoo 19 Enterprise
``D:/Projects/odoo-19.0/enterprise-19.0``, MMG v15 custom modules
``D:/Projects/mmg/psus-medicine-man-gallery``.
"""
from __future__ import annotations

import csv
import xml.etree.ElementTree as ET

from adapters.base import OdooRPCError
from framework.registry import test_case
from tests.fg07.common import (MARK, NO_ACCOUNTANT, PAYMENT_STATE_IN_PAYMENT,
                               PAYMENT_STATE_PAID, STATUS_FIELD, WORKFLOW,
                               WORKFLOW_NAME, acting_company, cleanup,
                               company_ctx, confirm_payment_register,
                               fields_present, finding, m2o_id, m2o_name,
                               make_invoice, make_partner, make_product, money,
                               observation, payment_row, register_payment,
                               require_module, require_v19,
                               residual_manual_step, selection_labels,
                               sweep_fg07, trace)

SURFACE_CSV = "TC-INV-004-payment-status-surfaces.csv"
SURFACE_HEADER = ["surface", "read_from", "identifier", "value_read",
                  "workbook_expectation"]

# The two views the workbook's steps 4 and 7 look at, and the one step 8 looks
# at. Resolved by xmlid rather than by "the default view", so that a
# customisation that ships its own primary view cannot make the assertions
# read a view the user never sees.
FORM_VIEW_XMLID = "account.view_move_form"
LIST_VIEW_XMLID = "account.view_invoice_tree"
SEARCH_VIEW_XMLID = "account.view_account_invoice_filter"

# Workbook step 8 / Expected line 3, verbatim from
# addons/account/views/account_move_views.xml:1730.
IN_PAYMENT_FILTER_NAME = "in_payment"
IN_PAYMENT_FILTER_STRING = "In payment"

# The word the gallery's staff must see, and the word they must not.
WANTED_WORD = "Paid"
UNWANTED_WORD = "In Payment"

# Field names that can legitimately back the list's "Status" column: the v19
# one, the raw state, and the field the v15 port added
# (mmg_change_ui/models/account_move.py:7-14). All three are graded if the
# list actually shows them, because the accountant reads the column, not the
# field name behind it.
STATUS_COLUMN_FIELDS = (STATUS_FIELD, "payment_state", "payment_state_clone")
STATUS_COLUMN_LABEL = "Status"

# The fixture. One line, no tax, so the amount the Pay pop-up offers is
# exactly the amount the invoice shows and "leave the amount as the full
# invoice amount" is checkable rather than approximate.
FIXTURE_PRICE = 1000.00


def _guarded(ctx, label: str, func, *args, **kwargs) -> tuple:
    """Run one RPC and return ``(result, error_text)`` instead of raising.

    Expected Result line 4 is "no error anywhere", so an ``OdooRPCError``
    raised by a step the workbook actually asks the tester to perform (post
    the invoice, set the journal, confirm the payment) is a RESULT to be
    graded. Letting it escape would record AUTOMATION_ERROR, which reads as a
    broken test rather than as the product fault it would be.
    """
    try:
        return func(*args, **kwargs), ""
    except OdooRPCError as exc:
        ctx.log(f"{label} raised: {exc}")
        return None, f"{label}: {exc}"


# --------------------------------------------------------------- arch reading
def _view_arch(ctx, xmlid: str, view_type: str) -> str:
    """``get_view`` arch for one view, '' (with a log line) on any failure.

    ``get_view`` is public; ``fields_view_get`` was removed in v19. Returning
    '' rather than raising keeps a broken view a recorded assertion failure
    instead of an AUTOMATION_ERROR that reads as a broken test.
    """
    view_id = ctx.adapter.rpc.ref(xmlid)
    if not view_id:
        ctx.log(f"the view {xmlid!r} does not resolve on this database — the "
                f"assertions that read it will report an empty arch")
        return ""
    try:
        payload = ctx.adapter.rpc.call("account.move", "get_view", view_id,
                                       view_type) or {}
    except OdooRPCError as exc:
        ctx.log(f"could not fetch the {view_type} arch of {xmlid!r} ({exc})")
        return ""
    return payload.get("arch") or ""


def _root(ctx, arch: str, label: str):
    """Parse a view arch, returning ``None`` (and logging) if it will not."""
    if not arch:
        return None
    try:
        return ET.fromstring(arch)
    except ET.ParseError as exc:
        ctx.log(f"the {label} arch came back unparseable ({exc}) — the "
                f"assertions that read it will report nothing found")
        return None


def _ribbons(root) -> list[dict]:
    """Every ``web_ribbon`` widget in the form arch, in document order."""
    if root is None:
        return []
    return [dict(node.attrib)
            for node in root.iter("widget")
            if node.attrib.get("name") == "web_ribbon"]


def _ribbon_word(ribbon: dict) -> str:
    """The word a ribbon shows.

    Odoo's ``web_ribbon`` takes its text from ``title`` and falls back to
    ``text`` (the "Invoicing App Legacy" ribbon uses the latter,
    ``account_move_views.xml:937``), so both are read.
    """
    return (ribbon.get("title") or ribbon.get("text") or "").strip()


def _gates_on_in_payment(ribbon: dict) -> bool:
    """True when this ribbon is the one shown for the in-payment state.

    Matched on the QUOTED literal. A bare ``in_payment`` substring also
    matches ``status_in_payment != 'sent'`` on the second "Sent" ribbon
    (``account_move_views.xml:922-924``), which would grade the wrong widget.
    """
    expression = ribbon.get("invisible") or ribbon.get("attrs") or ""
    return ("'in_payment'" in expression) or ('"in_payment"' in expression)


def _hidden_column(attrib: dict) -> bool:
    """True when a list column is hard-hidden rather than merely optional.

    ``optional="hide"`` is NOT hidden — the workbook's step 6 is precisely
    "switch Status on", so an optional column is one the tester can show.
    """
    return (attrib.get("column_invisible") in ("1", "True", "true")
            or attrib.get("invisible") in ("1", "True", "true"))


def _status_columns(root) -> tuple[list[dict], list[dict]]:
    """``(graded, other_status_labelled)`` columns of the invoice list.

    Only the three payment-status fields are GRADED. A column merely labelled
    "Status" that is backed by something else — ``state``, say, whose labels
    are Draft/Posted/Cancelled — would fail a "reads Paid" assertion for a
    perfectly correct system, so it is returned separately and reported as a
    finding for a human instead of being graded.
    """
    if root is None:
        return [], []
    graded, other = [], []
    for node in root.iter("field"):
        attrib = dict(node.attrib)
        if _hidden_column(attrib):
            continue
        if (attrib.get("name") or "") in STATUS_COLUMN_FIELDS:
            graded.append(attrib)
        elif attrib.get("string") == STATUS_COLUMN_LABEL:
            other.append(attrib)
    return graded, other


def _search_filters(root) -> list[dict]:
    if root is None:
        return []
    return [dict(node.attrib) for node in root.iter("filter")]


# ------------------------------------------------------- transit discovery
def _transit_method_lines(ctx, company: dict) -> list[dict]:
    """Inbound payment method lines that really route through transit.

    This replaces the workbook's "Ask Novobi which journal to use". The
    outstanding account belongs to the METHOD LINE, not to the journal
    (``account_payment.py:620-623``), so the search is on
    ``account.payment.method.line`` and the two short-circuits that would send
    the invoice straight to ``paid`` are excluded:

    * ``payment_account_id.account_type == 'asset_cash'`` — ``action_post``
      sets the payment to ``paid`` outright (``account_payment.py:1141``);
      filtered in the domain.
    * ``payment_account_id == journal.default_account_id`` — forces
      ``is_matched = True``, so the invoice reconciles as fully matched and
      becomes ``paid`` (``account_payment.py:489-492``); filtered below,
      because ``default_account_id`` is a related field on the method line
      (``account_payment_method.py:122-124``) and comparing two fields is not
      expressible in a domain.
    """
    rpc = ctx.adapter.rpc
    domain = [
        ("payment_type", "=", "inbound"),
        ("journal_id.type", "in", ("bank", "cash", "credit")),
        ("journal_id.company_id", "=", company["id"]),
        ("payment_account_id", "!=", False),
        ("payment_account_id.account_type", "!=", "asset_cash"),
    ]
    try:
        rows = rpc.search_read(
            "account.payment.method.line", domain,
            ["name", "code", "journal_id", "payment_account_id",
             "default_account_id"],
            order="id", context=company_ctx(company))
    except OdooRPCError as exc:
        ctx.log(f"could not read account.payment.method.line ({exc})")
        return []
    candidates = []
    for row in rows:
        outstanding = m2o_id(row.get("payment_account_id"))
        journal_default = m2o_id(row.get("default_account_id"))
        if outstanding and outstanding == journal_default:
            ctx.log(f"method line #{row['id']} {row.get('name')!r} on "
                    f"{m2o_name(row.get('journal_id'))!r} discarded — its "
                    f"outstanding account IS the journal's own default "
                    f"account, which forces is_matched=True and would send "
                    f"the invoice straight to Paid "
                    f"(account_payment.py:489-492)")
            continue
        candidates.append({
            "id": row["id"],
            "name": row.get("name") or "",
            "code": row.get("code") or "",
            "journal_id": m2o_id(row.get("journal_id")),
            "journal": m2o_name(row.get("journal_id")),
            "account_id": outstanding,
            "account": m2o_name(row.get("payment_account_id")),
        })
    return candidates


NO_TRANSIT_JOURNAL = (
    "No inbound payment method line on this company routes through an "
    "outstanding / transit account, so no payment can ever leave an invoice "
    "In Payment and the workbook's own precondition for this case is not met "
    "(\"Ask Novobi which journal to use — with the wrong journal the invoice "
    "goes straight to Paid and this case cannot be run\"). What was looked "
    "for: an account.payment.method.line with payment_type='inbound' on a "
    "bank/cash/credit journal of this company, carrying a payment_account_id "
    "that is neither of account_type 'asset_cash' (action_post would set the "
    "payment to Paid outright, addons/account/models/account_payment.py:1141) "
    "nor equal to the journal's own default_account_id (that forces "
    "is_matched=True and the invoice reconciles as fully matched, :489-492). "
    "Configure Outstanding Receipts on a bank journal's payment method under "
    "Accounting > Configuration > Journals > (journal) > Incoming Payments, "
    "then re-run"
)


@test_case(
    id="TEST-FG07-INV-004",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module="mmg_change_ui",
    priority="P2",
    kind="API",
    order=706,
    name="An invoice paid by a cheque still in transit reads 'Paid'",
    description="An invoice whose payment routes through an outstanding / "
                "transit account really reaches payment_state 'in_payment', "
                "and every surface the gallery's staff read — the form "
                "ribbon, the invoice list's Status column and the field's own "
                "selection labels — says 'Paid' rather than 'In Payment', "
                "with no blank status anywhere, while the search panel's 'In "
                "payment' filter survives as the workbook expects.",
    traceability=trace("TC-INV-004"))
def test_inv_004(ctx):
    rpc = ctx.adapter.rpc
    created = {"account.payment": [], "account.move": [], "res.partner": []}
    evidence: list[tuple] = []          # CSV rows — declared BEFORE the try
    residual: list[str] = []            # residual notes — declared BEFORE

    with ctx.step("Precondition (workbook): a journal whose payment method "
                  "routes through an outstanding/transit account, and a "
                  "posted unpaid customer invoice"):
        require_v19(ctx)
        # THE gate. Without 'accountant' the in-payment state cannot occur at
        # all (_get_invoice_in_payment_state returns 'paid' in Community,
        # account_move.py:7350-7354) and every 'Paid' reading below would be
        # true for the wrong reason.
        require_module(ctx, "accountant", NO_ACCOUNTANT)
        company = acting_company(ctx)
        ctx.log(f"acting company #{company['id']} {company['name']!r} — "
                f"currency {company['currency_name']}")
        sweep_fg07(ctx)

        candidates = _transit_method_lines(ctx, company)
        for candidate in candidates:
            ctx.log(f"transit candidate: method line #{candidate['id']} "
                    f"{candidate['name']!r} on journal "
                    f"{candidate['journal']!r} -> outstanding account "
                    f"{candidate['account']!r}")
        if not candidates:
            ctx.blocked(NO_TRANSIT_JOURNAL)

    try:
        with ctx.step("Steps 1-3: open the posted unpaid invoice, click Pay, "
                      "set the Journal Novobi named and confirm the full "
                      "amount"):
            # Building the fixture is the platform's own work, not a step the
            # workbook grades: a failure here is an environment problem, so it
            # is reported as BLOCKED rather than as a defect in the wording.
            try:
                partner_id = make_partner(ctx, "Cheque In Transit Customer",
                                          company=company)
                created["res.partner"].append(partner_id)
                product_id = make_product(ctx, "Transit Test Piece",
                                          FIXTURE_PRICE)
                move_id = make_invoice(ctx, partner_id,
                                       [(product_id, 1, FIXTURE_PRICE)],
                                       company=company, post=False)
                created["account.move"].append(move_id)
            except OdooRPCError as exc:
                ctx.blocked(
                    f"the {MARK} fixture invoice could not be built on this "
                    f"database ({exc}), so there is no posted unpaid customer "
                    f"invoice to pay and the workbook's second precondition "
                    f"is not met. This is an environment problem, not a "
                    f"finding about the 'Paid' wording — check that the "
                    f"runner user may create contacts, products and customer "
                    f"invoices in company #{company['id']} "
                    f"{company['name']!r}")

            # Workbook step 1 is "open the POSTED unpaid invoice". Posting is
            # something the tester really does, so an error here is graded
            # against Expected line 4 ("no error anywhere") instead of being
            # allowed to escape as AUTOMATION_ERROR.
            _, post_error = _guarded(ctx, "account.move.action_post",
                                     rpc.call, "account.move", "action_post",
                                     [move_id], context=company_ctx(company))
            ctx.check("Posting the customer invoice raises no error "
                      "(workbook Expected: 'No blank value and no error "
                      "anywhere')", "", post_error)
            before = rpc.read("account.move", [move_id],
                              ["name", "state", "payment_state",
                               "amount_total", "amount_residual"])[0]
            if before.get("state") == "posted":
                # Rule: drop an id from `created` the moment it is posted.
                # cleanup() refuses posted moves anyway, but a posted invoice
                # must never even be offered to unlink() — v19 would take it
                # back to draft on the way.
                created["account.move"].remove(move_id)
            ctx.check("The fixture invoice is posted and unpaid before the "
                      "cheque is registered (workbook precondition: 'A "
                      "posted, unpaid customer invoice exists')",
                      ("posted", "not_paid"),
                      (before.get("state"), before.get("payment_state")))

            # The Pay pop-up. The wizard is created first with no values so
            # that available_journal_ids can be read from it — choosing a
            # journal the wizard does not offer would make the write silently
            # bounce back to the default and the case would test nothing.
            wizard_id, open_error = _guarded(
                ctx, "the Pay pop-up (account.payment.register)",
                register_payment, ctx, [move_id], {}, company=company)
            ctx.check("Clicking Pay in the invoice header opens the payment "
                      "pop-up without error (workbook step 2)", "", open_error)
            offered = rpc.read("account.payment.register", [wizard_id],
                               ["available_journal_ids", "amount",
                                "can_edit_wizard", "payment_type"])[0]
            offered_journals = set(offered.get("available_journal_ids") or [])
            usable = [c for c in candidates
                      if c["journal_id"] in offered_journals]
            ctx.check("The Pay pop-up offers at least one journal whose "
                      "payment method routes through an outstanding/transit "
                      "account (workbook Test Data: 'the one Novobi names as "
                      "routing through an outstanding account')",
                      True, bool(usable))
            chosen = usable[0]
            ctx.log(f"paying through journal {chosen['journal']!r} / method "
                    f"line {chosen['name']!r} (code {chosen['code']!r}) -> "
                    f"outstanding account {chosen['account']!r}")

            # Two writes, in this order: journal_id first, because
            # payment_method_line_id is a stored compute on it
            # (wizard/account_payment_register.py:120-129) and setting both at
            # once lets the compute overwrite the method line.
            write_errors = []
            for label, values in (
                    ("Journal", {"journal_id": chosen["journal_id"]}),
                    ("Payment Method",
                     {"payment_method_line_id": chosen["id"]})):
                _, error = _guarded(ctx, f"setting {label} on the Pay pop-up",
                                    rpc.write, "account.payment.register",
                                    [wizard_id], values)
                if error:
                    write_errors.append(error)
            ctx.check("Setting the Journal and the transit Payment Method in "
                      "the Pay pop-up raises no error (workbook step 3)",
                      [], write_errors)
            after = rpc.read("account.payment.register", [wizard_id],
                             ["journal_id", "payment_method_line_id",
                              "amount"])[0]
            ctx.check("The Journal set in the Pay pop-up stuck (workbook step "
                      "3)", chosen["journal_id"],
                      m2o_id(after.get("journal_id")))
            ctx.check("The transit payment method set in the Pay pop-up stuck "
                      "— without it the payment would use the journal's "
                      "default method and never reach the outstanding account",
                      chosen["id"], m2o_id(after.get("payment_method_line_id")))
            ctx.check("The Pay pop-up still offers the full invoice amount "
                      "(workbook step 3: 'Leave the amount as the full "
                      "invoice amount')",
                      money(before.get("amount_total")),
                      money(after.get("amount")))

            payment_ids, confirm_error = _guarded(
                ctx, "confirming the payment (action_create_payments)",
                confirm_payment_register, ctx, wizard_id, [move_id],
                company=company)
            ctx.check("Confirming the payment raises no error (workbook step "
                      "3: 'Confirm the payment'; Expected line 4: 'no error "
                      "anywhere')", "", confirm_error)
            payment_ids = payment_ids or []
            ctx.check("Confirming the pop-up created exactly one payment for "
                      "the one invoice", 1, len(payment_ids))
            created["account.payment"].extend(payment_ids)

        with ctx.step("Step 3 (continued): the cheque is banked but not "
                      "cleared — the invoice really is In Payment, so the "
                      "word this case grades is not a vacuous one"):
            payment = payment_row(ctx, payment_ids[0])
            if payment["state"] not in ("draft",):
                # Its journal entry posts with it; never offer it to unlink().
                created["account.payment"] = [
                    pid for pid in created["account.payment"]
                    if pid != payment["id"]]
            row = rpc.read("account.move", [move_id],
                           ["name", "state", "payment_state",
                            "amount_total", "amount_residual"])[0]
            residual_amount = money(row.get("amount_residual"))
            ctx.log(f"invoice {row.get('name')!r}: state={row.get('state')!r} "
                    f"payment_state={row.get('payment_state')!r} "
                    f"residual={residual_amount:.2f}; payment "
                    f"{payment['name']!r}: state={payment['state']!r} "
                    f"is_matched={payment['is_matched']}")
            evidence.append(("payment routing",
                             "account.move.payment_state + "
                             "account.payment.state/is_matched",
                             f"{row.get('name')} via {chosen['journal']}",
                             f"payment_state={row.get('payment_state')}, "
                             f"payment.state={payment['state']}, "
                             f"is_matched={payment['is_matched']}, "
                             f"residual={residual_amount:.2f}",
                             "payment_state must be 'in_payment' or the case "
                             "cannot be run (workbook Preconditions)"))

            if row.get("payment_state") != PAYMENT_STATE_IN_PAYMENT:
                # The workbook's own precondition, not a relabelling failure.
                # Reporting this as FAILED would send the gallery hunting for
                # a bug in mmg_change_ui when the fault is in the journal's
                # payment-method configuration.
                ctx.blocked(
                    f"The payment through journal {chosen['journal']!r} / "
                    f"method line {chosen['name']!r} (outstanding account "
                    f"{chosen['account']!r}) left invoice {row.get('name')!r} "
                    f"at payment_state="
                    f"{row.get('payment_state')!r}, not "
                    f"{PAYMENT_STATE_IN_PAYMENT!r} — account.payment state="
                    f"{payment['state']!r}, is_matched="
                    f"{payment['is_matched']}, residual="
                    f"{residual_amount:.2f}. The workbook says exactly this "
                    f"case: 'with the wrong journal the invoice goes straight "
                    f"to Paid and this case cannot be run'. Reading 'Paid' on "
                    f"an invoice that is genuinely "
                    f"{PAYMENT_STATE_PAID!r} would prove nothing about the "
                    f"relabelling, so this is reported as a precondition "
                    f"problem rather than as a defect in the wording. Fix the "
                    f"outstanding-account configuration on that payment "
                    f"method (Accounting > Configuration > Journals > "
                    f"(journal) > Incoming Payments) and re-run")

            ctx.check("The banked cheque has not cleared yet — the payment is "
                      "still in process (account.payment.state)",
                      "in_process", payment["state"])
            ctx.check("…and it is NOT matched, which is what keeps the "
                      "invoice at 'in_payment' rather than 'paid' "
                      "(account.payment.is_matched, "
                      "account_payment.py:489-497)",
                      False, payment["is_matched"])
            ctx.check("A full payment through the outstanding account leaves "
                      "nothing due on the invoice (amount_residual)",
                      money(0.0), residual_amount)

        with ctx.step("Steps 4-8 (evidence capture): read all four labelled "
                      "surfaces BEFORE grading any of them, so one bad word "
                      "does not hide the other three"):
            # ctx.check raises on the first mismatch. Capturing every reading
            # here — into the log and into the CSV written from `finally` —
            # means the tester sees all four words even when the run stops at
            # the first one.
            form_root = _root(ctx, _view_arch(ctx, FORM_VIEW_XMLID, "form"),
                              f"{FORM_VIEW_XMLID} form")
            list_root = _root(ctx, _view_arch(ctx, LIST_VIEW_XMLID, "list"),
                              f"{LIST_VIEW_XMLID} list")
            search_root = _root(ctx,
                                _view_arch(ctx, SEARCH_VIEW_XMLID, "search"),
                                f"{SEARCH_VIEW_XMLID} search")

            ribbons = _ribbons(form_root)
            ctx.log(f"{len(ribbons)} web_ribbon widget(s) on "
                    f"{FORM_VIEW_XMLID} (stock Odoo 19 ships 8, "
                    f"account_move_views.xml:918-940)")
            for index, ribbon in enumerate(ribbons):
                ctx.log(f"  ribbon[{index + 1}] {_ribbon_word(ribbon)!r} "
                        f"gated on {ribbon.get('invisible') or '(always)'!r}")
            in_payment_ribbons = [r for r in ribbons if _gates_on_in_payment(r)]
            ribbon_words = sorted({_ribbon_word(r) for r in in_payment_ribbons})
            evidence.append(("form ribbon", f"{FORM_VIEW_XMLID} (get_view)",
                             "web_ribbon gated on 'in_payment'",
                             ", ".join(ribbon_words) or "(none found)",
                             f"reads {WANTED_WORD!r}, not "
                             f"{UNWANTED_WORD!r}"))

            status_columns, other_status = _status_columns(list_root)
            for attrib in other_status:
                finding(ctx,
                        f"the invoice list carries another column labelled "
                        f"{STATUS_COLUMN_LABEL!r}, backed by field "
                        f"{attrib.get('name')!r}. It is reported rather than "
                        f"graded — its labels are not payment statuses, so "
                        f"'reads Paid' would be the wrong question — but two "
                        f"columns both headed 'Status' is exactly the kind of "
                        f"thing that makes the gallery's staff read the wrong "
                        f"one")
            readable = fields_present(rpc, "account.move",
                                      list(STATUS_COLUMN_FIELDS))
            column_names = []
            for attrib in status_columns:
                name = attrib.get("name") or ""
                if name in readable and name not in column_names:
                    column_names.append(name)
                ctx.log(f"  Status column candidate: field {name!r} "
                        f"string={attrib.get('string')!r} "
                        f"widget={attrib.get('widget')!r} "
                        f"optional={attrib.get('optional')!r}")
            column_words = {}
            live = rpc.read("account.move", [move_id], column_names)[0] \
                if column_names else {}
            for name in column_names:
                raw = live.get(name)
                label = selection_labels(rpc, "account.move", name).get(
                    str(raw), "") if raw else ""
                column_words[name] = label
                ctx.log(f"  the invoice's {name!r} reads {label!r} "
                        f"(raw value {raw!r})")
                evidence.append(("invoice list Status column",
                                 f"{LIST_VIEW_XMLID} + fields_get selection",
                                 name, f"{label} (raw {raw!r})",
                                 f"reads {WANTED_WORD!r}"))

            status_selection = selection_labels(rpc, "account.move",
                                                STATUS_FIELD)
            payment_selection = selection_labels(rpc, "account.move",
                                                 "payment_state")
            ctx.log(f"account.move.{STATUS_FIELD} selection: "
                    f"{status_selection}")
            ctx.log(f"account.move.payment_state selection: "
                    f"{payment_selection}")
            evidence.append(("selection label", f"fields_get {STATUS_FIELD}",
                             PAYMENT_STATE_IN_PAYMENT,
                             status_selection.get(PAYMENT_STATE_IN_PAYMENT,
                                                  "(no such value)"),
                             f"reads {WANTED_WORD!r}"))

            filters = _search_filters(search_root)
            in_payment_filter = next(
                (f for f in filters
                 if f.get("name") == IN_PAYMENT_FILTER_NAME), {})
            evidence.append(("search panel filter", SEARCH_VIEW_XMLID,
                             IN_PAYMENT_FILTER_NAME,
                             in_payment_filter.get("string", "(absent)"),
                             f"still reads {IN_PAYMENT_FILTER_STRING!r} — "
                             f"EXPECTED, not a defect"))

        with ctx.step("Step 4 / Expected line 1: the ribbon on the invoice "
                      "reads Paid — it does not read 'In Payment'"):
            # Reported as a list rather than as a boolean so a form carrying
            # more than one stale ribbon names every one of them.
            stale = [f"ribbon[{index + 1}] titled "
                     f"{_ribbon_word(ribbon)!r} gated on "
                     f"{ribbon.get('invisible') or '(always)'!r}"
                     for index, ribbon in enumerate(ribbons)
                     if _ribbon_word(ribbon) == UNWANTED_WORD]
            ctx.check(f"No ribbon on the customer invoice form still reads "
                      f"{UNWANTED_WORD!r} — the gallery's staff read that as "
                      f"unpaid and chase the customer",
                      [], stale)
            # The positive half. Selecting by the gating expression rather
            # than by position is what makes this survive v19's re-ordering:
            # the v15 port pinned //sheet/widget[@name='web_ribbon'][2], and
            # [2] in v19 is the second 'Sent' ribbon.
            ctx.check(f"The ribbon Odoo shows while the cheque is still in "
                      f"transit is titled {WANTED_WORD!r} (the web_ribbon "
                      f"whose invisible expression is gated on "
                      f"payment_state 'in_payment')",
                      [WANTED_WORD], ribbon_words)

        with ctx.step("Steps 5-7 / Expected line 2: the Status column on the "
                      "invoice list reads Paid"):
            # Workbook step 6 is "if there is no Status column, switch it on",
            # so the column existing at all is part of the expectation.
            ctx.check_true(
                f"The invoice list still offers a Status column "
                f"({LIST_VIEW_XMLID} carries {STATUS_FIELD} as "
                f"string=\"Status\" widget=\"badge\" optional=\"show\", "
                f"account_move_views.xml:550-559)",
                bool(column_names),
                actual_desc=(f"Status-like columns found in the list arch: "
                             f"{[a.get('name') for a in status_columns]}; "
                             f"readable on account.move: {column_names}"))
            # …and the column must actually be HEADED "Status". Asserting only
            # that some payment-status field is in the arch is weaker than the
            # workbook: steps 6 and 7 tell the accountant to switch on the
            # column called Status and read it, and a column backed by
            # payment_state with no string= of its own heads "Payment Status"
            # instead. Stock Odoo 19 spells it out —
            # <field name="status_in_payment" string="Status" widget="badge"
            # optional="show"> (account_move_views.xml:550-559) — so a port
            # that dropped the label is a real finding, not a naming quibble.
            headed_status = [attrib.get("name") for attrib in status_columns
                             if (attrib.get("string")
                                 or "") == STATUS_COLUMN_LABEL]
            ctx.check_true(
                f"…and that column is headed {STATUS_COLUMN_LABEL!r} on the "
                f"invoice list — the heading workbook step 6 tells the tester "
                f"to switch on and step 7 tells them to read",
                bool(headed_status),
                actual_desc=(
                    f"columns headed {STATUS_COLUMN_LABEL!r}: "
                    f"{headed_status}; every payment-status column the list "
                    f"arch carries, as (field, heading): "
                    f"{[(a.get('name'), a.get('string')) for a in status_columns]}"))
            # Grade every column the list labels Status, whichever field backs
            # it: a port that reintroduced the v15 payment_state_clone column
            # must read 'Paid' too, and one that left the raw payment_state on
            # screen is exactly the defect this case exists to catch.
            wrong = [f"the {name!r} column reads "
                     f"{column_words[name]!r}"
                     for name in column_names
                     if column_words[name] != WANTED_WORD]
            ctx.check(f"Every Status column on the invoice list reads "
                      f"{WANTED_WORD!r} for an invoice paid by a cheque still "
                      f"in transit", [], wrong)
            # The metadata behind the column, asserted separately because the
            # workbook grades the word and the badge separately and because a
            # label that is right only in the list arch would still be wrong
            # in the kanban, the chatter and every export.
            ctx.check(f"account.move.{STATUS_FIELD} labels the in-payment "
                      f"state {WANTED_WORD!r} (fields_get selection — the one "
                      f"string the v19 list, badge and exports all read)",
                      WANTED_WORD,
                      status_selection.get(PAYMENT_STATE_IN_PAYMENT))

        with ctx.step("Expected line 4: no blank value and no error anywhere "
                      "— a BLANK status is a P1, worse than a wrong word"):
            # _compute_status_in_payment falls back to move.state
            # (account_move.py:1327-1340), so a blank means the compute
            # produced nothing at all. v19 also added a 'blocked' state
            # (account_move.py:55) that a v15-era relabelling would not have
            # given a label to — which is precisely how a blank appears.
            blank = []
            for field_name, selection in ((STATUS_FIELD, status_selection),
                                          ("payment_state",
                                           payment_selection)):
                blank.extend(f"account.move.{field_name} value {value!r} has "
                             f"no label"
                             for value, label in selection.items()
                             if not (label or "").strip())
                if not selection:
                    blank.append(f"account.move.{field_name} returned no "
                                 f"selection at all")
            ctx.check("Every payment status an invoice can hold carries a "
                      "non-blank label, including Odoo 19's new 'blocked' "
                      "state", [], blank)
            empty_columns = [name for name in column_names
                             if not (column_words[name] or "").strip()]
            ctx.check("The Status column on this invoice is not blank "
                      "(workbook If It Fails: 'a BLANK status is more serious "
                      "than the wrong word: raise a blank one as a P1')",
                      [], empty_columns)

        with ctx.step("Step 8 / Expected line 3: a filter named 'In payment' "
                      "still exists in the search panel — EXPECTED, and not "
                      "a defect"):
            # A POSITIVE assertion: the workbook lists the filter's survival
            # as an expected result, so it is graded. It is ALSO logged as an
            # observation, because the workbook's If It Fails column says
            # that if this is the tester's only finding the case is a pass.
            ctx.check(f"The invoice search panel still offers a filter named "
                      f"{IN_PAYMENT_FILTER_STRING!r} "
                      f"({SEARCH_VIEW_XMLID}, filter name="
                      f"{IN_PAYMENT_FILTER_NAME!r})",
                      IN_PAYMENT_FILTER_STRING,
                      in_payment_filter.get("string"))
            observation(ctx,
                        f"the search filter in the side panel still reads "
                        f"{IN_PAYMENT_FILTER_STRING!r} while the column, the "
                        f"badge and the ribbon read {WANTED_WORD!r}. Only the "
                        f"column, the badge and the ribbon were relabelled. "
                        f"The workbook marks this READ THIS FIRST: it is a "
                        f"known cosmetic inconsistency and NOT a defect — "
                        f"'If your only finding is the In payment search "
                        f"filter, close the case as a pass.' Source: "
                        f"addons/account/views/account_move_views.xml:1730")
            if len(ribbons) != 8:
                finding(ctx,
                        f"the customer invoice form carries {len(ribbons)} "
                        f"web_ribbon widget(s); stock Odoo 19 ships 8 "
                        f"(account_move_views.xml:918-940). Not a pass/fail "
                        f"question for this case, but worth knowing: the v15 "
                        f"relabelling pinned the ribbon by POSITION "
                        f"(//sheet/widget[@name='web_ribbon'][2], "
                        f"mmg_change_ui/views/account_move_views.xml:8-11), "
                        f"and any further change to the ribbon count moves "
                        f"whatever a positional xpath points at")

            residual.append(
                f"confirm on screen what this case read from the view "
                f"architecture. Open invoice {row.get('name')} (paid through "
                f"journal {chosen['journal']!r} via method line "
                f"{chosen['name']!r}, outstanding account "
                f"{chosen['account']!r}; payment_state="
                f"{row.get('payment_state')!r}, residual "
                f"{residual_amount:.2f}) and check three pixels the platform "
                f"cannot see: (1) the ribbon in the top right corner actually "
                f"renders the word "
                f"{(ribbon_words[0] if ribbon_words else '(none)')!r} — an "
                f"OWL or CSS override could hide or restyle it after the arch "
                f"is served; (2) the Status badge on the invoice list row "
                f"renders "
                f"{', '.join(repr(column_words[n]) for n in column_names) or '(no column)'} "
                f"in green rather than red, since the decoration is a "
                f"separate attribute from the word; (3) the search panel "
                f"still lists "
                f"{in_payment_filter.get('string', '(absent)')!r}, which is "
                f"EXPECTED. Do not raise item (3).")
    finally:
        with ctx.step("Evidence: write the four labelled surfaces, then "
                      "remove FG07 fixtures"):
            path = ctx.artifacts_dir / SURFACE_CSV
            try:
                with path.open("w", newline="", encoding="utf-8") as handle:
                    writer = csv.writer(handle)
                    writer.writerow(SURFACE_HEADER)
                    writer.writerows(evidence)
                ctx.add_artifact(path, "log", SURFACE_CSV)
                ctx.log(f"wrote {len(evidence)} surface reading(s) to "
                        f"{SURFACE_CSV}")
            except OSError as exc:
                ctx.log(f"could not write {SURFACE_CSV} ({exc}) — the "
                        f"readings above are still in this log")
            for note in residual:
                residual_manual_step(ctx, note)
            ctx.log(f"workbook State After The Test is 'One invoice paid "
                    f"through the transit journal', so the posted invoice and "
                    f"its payment are LEFT IN PLACE by design — cleanup "
                    f"refuses posted accounting records. Only the unposted "
                    f"leftovers and the {MARK}-marked contact/product are "
                    f"removed.")
            cleanup(ctx, created)
