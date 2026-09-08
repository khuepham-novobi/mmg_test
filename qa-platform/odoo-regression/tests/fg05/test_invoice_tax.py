"""FG-05 — the customer-invoice tax chain: TC-TAX-001, TC-TAX-002, TC-TAX-003.

These three rows are the core of FG-05 and are all P0. TC-TAX-001 proves an
invoice can get its tax from Avalara at all. TC-TAX-002 is **GATE 3**, the
acceptance test for the whole FG-05 rebuild: the tax must be posted per taxing
authority rather than as one rolled-up figure, read from the JOURNAL ENTRY
because that is where the split either exists or does not. TC-TAX-003 proves a
second invoice to the same city reuses the ``account.tax`` records the first
one created instead of duplicating them.

All three are live Avalara calls and therefore run behind
:func:`tests.fg05.common.require_sandbox`, which BLOCKS (never fails, never
proceeds) unless the target company is pointed at the Avalara **sandbox** with
readable credentials.

Documented adaptation — cross-test independence
-----------------------------------------------
The workbook chains these rows: TC-TAX-002 step 1 says "create and confirm an
invoice exactly as in TC-TAX-001", and TC-TAX-003's precondition is
"TC-TAX-002 has passed and its invoice is posted". The platform forbids one
test depending on another test's fixtures (AUTOMATION_CONVENTIONS rule 5), so
each test builds its own equivalent starting state: TC-TAX-002 creates and
posts its own Phoenix invoice, and TC-TAX-003 creates and posts BOTH invoices
it compares (1,000.00 first, then 500.00) inside itself — that case genuinely
needs two documents, and both are its own. The business assertions are
unchanged from the workbook.

Documented adaptation — posted invoices are never cleaned up
-----------------------------------------------------------
Odoo forbids deleting a posted move, and the workbook agrees with that:
TC-TAX-002's "State After The Test" says to leave the posted sandbox invoice
in place, and TC-TAX-003's says "Leave both". Posted FG05 sandbox invoices
therefore ACCUMULATE by design. No posted move id is put into the
``cleanup()`` dict expecting removal; ``sweep_fg05()`` clears only
draft/cancelled leftovers, and every assertion here is scoped to ids captured
in-test, never to a count of all FG05 records. The Avalara sandbox
transactions those invoices filed likewise stay — nothing in this suite voids
an Avalara document (see the module README's TC-TAX-012 correction).

Documented adaptation — where the tax NAME is read from
-------------------------------------------------------
TC-TAX-002's naming expectation is asserted against ``account.tax.name``, read
by id for the taxes carried by the journal items, not against the journal
item's many2one display string. ``account.tax._compute_display_name``
(v19 ``addons/account/models/account_tax.py``) appends a country-code suffix
such as " (US)" whenever the tax's country differs from the company's fiscal
country, which would break the ``… [AZ] (5.6000 %)`` shape for a display
reason and report a naming defect that is not one. The line COUNT and the
AMOUNTS still come from ``move_tax_lines()`` — the journal entry, exactly as
the workbook requires.

Residual manual verification
----------------------------
TC-TAX-001's "…that matches the rate for the customer's address", and
TC-TAX-003's "if the new records differ from the old only by rate, that is a
rate change at Avalara and is not a defect", can only be settled against
Avalara's own breakdown in the sandbox portal, which this platform cannot
reach. Everything provable from Odoo is asserted with real checks; the
residual portal step is logged together with the document's Avalara Code so a
human can look the transaction up.
"""
from __future__ import annotations

from adapters.base import OdooRPCError
from framework.registry import test_case
from tests.fg05.common import (ADDRESS_PHOENIX_AZ, ADDRESS_TUCSON_AZ,
                               AUTHORITY_CODE_RE, JURISDICTION_TAX_NAME_RE,
                               MODULE, WORKFLOW, WORKFLOW_NAME, account_code,
                               cleanup, compute_taxes, doc_totals,
                               make_invoice, make_partner, make_product,
                               move_tax_lines,
                               require_avatax_fiscal_position,
                               require_sandbox, sweep_fg05, trace)

# The workbook's "no error banner" wording: the button either returns or it
# raises. An expected-to-be-clean RPC failure is captured and asserted rather
# than propagated, so the platform records expected-vs-actual instead of an
# opaque error.
CLEAN = "button returned without an error"


# --------------------------------------------------------------- helpers
def _compute_taxes_guarded(ctx, move_id) -> str:
    """Click **Compute Taxes**; return the error text, ``""`` when clean."""
    try:
        compute_taxes(ctx, "account.move", move_id)
    except OdooRPCError as exc:
        return str(exc)
    return ""


def _avatax_log_evidence(ctx, what: str):
    """The evidence TC-TAX-001's "If It Fails" column asks for.

    The workbook says: "click Start logging for 30 minutes in the AvaTax
    settings block, repeat the test, and click Show logs — attach what you
    see there to the defect. Without the log the cause is usually
    unguessable."

    This suite must NOT arm that logging itself: ``res.config.settings
    .avatax_log()`` calls ``_enable_external_tax_logging``, which writes the
    ``account_avatax.log.end.date`` ``ir.config_parameter``
    (``account_external_tax/models/account_external_tax_mixin.py:179-184``) —
    a persistent side effect on a shared database that a regression run has
    no business leaving behind.

    So it does the two things it legitimately can: read back any Avatax rows
    that are ALREADY there (the request logger writes plain ``ir.logging``
    records; the shipped "Avalara Logging" action filters them with
    ``[('name','in',['Avatax','Avatax US'])]`` —
    ``account_avatax/views/res_config_settings_views.xml:16-21``), and print
    the exact manual procedure as a residual step so the gap is visible in
    the report rather than silent.
    """
    rows = []
    try:
        rows = ctx.adapter.rpc.search_read(
            "ir.logging", [("name", "in", ["Avatax", "Avatax US"])],
            ["create_date", "func", "line", "message"],
            order="id desc", limit=20)
    except OdooRPCError as exc:
        ctx.log(f"could not read ir.logging for Avatax rows ({exc})")
    if rows:
        ctx.log(f"AvaTax request log — {len(rows)} most recent row(s) "
                f"already captured on this database:")
        for row in reversed(rows):
            ctx.log(f"  [{row.get('create_date')}] "
                    f"{row.get('func') or ''}:{row.get('line') or ''} "
                    f"{(row.get('message') or '')[:800]}")
    else:
        ctx.log("AvaTax request log — no ir.logging rows named 'Avatax' / "
                "'Avatax US' exist, which means request logging was not "
                "armed when this ran.")
    ctx.log(
        f"RESIDUAL MANUAL STEP ({what}) — the workbook's If-It-Fails column "
        f"requires the AvaTax request log with the defect, and this platform "
        f"deliberately does not arm it (doing so writes the "
        f"'account_avatax.log.end.date' system parameter and would leave "
        f"logging on for 30 minutes on a shared database). To capture it by "
        f"hand: Accounting > Configuration > Settings > Taxes > AvaTax > "
        f"'Start logging for 30 minutes', re-run this case, then 'Show logs' "
        f"(Avalara Logging — ir.logging filtered to name in "
        f"['Avatax','Avatax US']) and attach what you see to the defect.")


def _confirm_guarded(ctx, move_id) -> str:
    """Click **Confirm**; return the error text, ``""`` when the post went
    through. ``account.move.action_post`` recomputes and re-files the Avalara
    transaction under the invoice name, so a rejected move stays draft — which
    the caller then sees as a ``state`` mismatch, with the message logged."""
    try:
        ctx.adapter.rpc.call("account.move", "action_post", [move_id])
    except OdooRPCError as exc:
        return str(exc)
    return ""


def _tax_records(ctx, tax_ids) -> dict:
    """``name`` / ``amount`` / ``amount_type`` of the taxes on some tax lines.

    Keyed by ``account.tax`` id. ``name`` is the stored field, deliberately
    not the many2one display string (see the module docstring).
    """
    ids = sorted({tax_id for tax_id in tax_ids if tax_id})
    if not ids:
        return {}
    rows = ctx.adapter.rpc.read("account.tax", ids,
                                ["name", "amount", "amount_type"])
    return {row["id"]: row for row in rows}


def _tax_names(lines, taxes) -> list:
    """Tax name per journal-entry tax line, in line order."""
    return [(taxes.get(line["tax_id"]) or {}).get("name") or line["tax_name"]
            for line in lines]


def _log_tax_lines(ctx, label, lines, taxes):
    """Workbook TC-TAX-002 step 4: account code, tax name and amount, one
    evidence line each — recorded before any assertion so the log is usable
    even when the first check fails."""
    codes = {}
    for line in lines:
        account_id = line["account_id"]
        if account_id and account_id not in codes:
            codes[account_id] = account_code(ctx, account_id)
    for line, name in zip(lines, _tax_names(lines, taxes)):
        tax = taxes.get(line["tax_id"]) or {}
        ctx.log(f"{label} tax line — account "
                f"{codes.get(line['account_id']) or '?'} "
                f"({line['account']}) | {name!r} | "
                f"amount={tax.get('amount')} "
                f"amount_type={tax.get('amount_type')} | "
                f"balance {line['balance']}")


def _authority_tax_names(ctx, codes, *, include_archived) -> dict:
    """Repeat the workbook's "type ``[AZ]`` in the Taxes search box" count.

    Returns ``{authority code: sorted list of matching account.tax names}``.

    ``include_archived=True`` runs the search with ``active_test=False``.
    That is not decoration: ``account_avatax`` reuses an existing tax by name
    through ``account_external_tax``'s
    ``_process_external_taxes(company, base_lines, 'name')`` and never passes
    ``search_archived_taxes``; the default ``False`` makes that lookup run
    with ``active_test=True``
    (``account_external_tax/models/account_external_tax_mixin.py`` line 136),
    so an ARCHIVED namesake cannot be reused and a duplicate would be created
    beside it. The active-only count is what the tester sees in the Taxes
    list; the count including archived rows is what proves nothing new was
    created at all. Both are asserted.
    """
    rpc = ctx.adapter.rpc
    found = {}
    for code in codes:
        needle = f"[{code}]"
        rows = rpc.search_read(
            "account.tax", [("name", "like", needle)], ["name"],
            context={"active_test": not include_archived})
        # Odoo's 'like' wraps the value in %…% and SQL LIKE gives '[' and ']'
        # no special meaning, so this is the substring search the tester
        # types. '_' and '%' inside a jurisdiction code WOULD be wildcards
        # though, so the rows are re-filtered on the literal substring in
        # Python before being counted.
        found[code] = sorted(row["name"] for row in rows
                             if needle in (row["name"] or ""))
    return found


def _phoenix_invoice(ctx, fp_id, customer_id, delivery_id, product_id, price):
    """Create → **Compute Taxes** → **Confirm** one invoice, then read it.

    Returns the move id, the error text of each button (empty when clean), the
    totals block, the journal-entry tax lines, the ``account.tax`` records
    behind them, and their names.
    """
    move_id = make_invoice(ctx, customer_id, [(product_id, 1, price)],
                           fiscal_position_id=fp_id,
                           shipping_partner_id=delivery_id)
    compute_error = _compute_taxes_guarded(ctx, move_id)
    if compute_error:
        ctx.log(f"Compute Taxes on invoice #{move_id} raised: {compute_error}")
    post_error = _confirm_guarded(ctx, move_id)
    if post_error:
        ctx.log(f"Confirm on invoice #{move_id} raised: {post_error}")

    totals = doc_totals(ctx, "account.move", move_id)
    lines = move_tax_lines(ctx, move_id)
    taxes = _tax_records(ctx, [line["tax_id"] for line in lines])
    ctx.log(f"invoice #{move_id} @ {price:.2f} — untaxed {totals['untaxed']}, "
            f"tax {totals['tax']}, total {totals['total']}, "
            f"state {totals['state']}, Avalara Code "
            f"{totals['avalara_code']!r}")
    return {"move_id": move_id, "compute_error": compute_error,
            "post_error": post_error, "totals": totals, "lines": lines,
            "taxes": taxes, "names": _tax_names(lines, taxes)}


# ----------------------------------------------------------- TC-TAX-001
@test_case(
    id="TEST-FG05-TAX-001",
    name="Tax is calculated on a customer invoice through AvaTax",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P0",
    kind="API",
    order=501,
    description="Compute Taxes on a 1,000.00 draft customer invoice returns "
                "without an error, leaves Untaxed 1,000.00 with at least one "
                "non-zero tax line and a populated Avalara Code, and Confirm "
                "posts it.",
    traceability=trace("TC-TAX-001"))
def test_tax_001(ctx):
    created = {"product.product": [], "res.partner": []}
    with ctx.step("Precondition: Odoo 19 with a usable Avalara SANDBOX and an "
                  "AvaTax fiscal position"):
        require_sandbox(ctx, "computing tax on a customer invoice")
        fp_id, fp = require_avatax_fiscal_position(ctx)
        ctx.log(f"AvaTax fiscal position #{fp_id} {fp['name']!r}")
        sweep_fg05(ctx)
    try:
        with ctx.step("Workbook steps 1-4: new draft invoice for a customer "
                      "with a complete US address and the AvaTax fiscal "
                      "position; one line — product, quantity 1, price "
                      "1,000.00 — then Save"):
            partner_id = make_partner(ctx, "TAX-001 Customer",
                                      ADDRESS_PHOENIX_AZ,
                                      fiscal_position_id=fp_id)
            created["res.partner"].append(partner_id)
            product_id = make_product(ctx, "TAX-001 Art Item", 1000.00)
            created["product.product"].append(product_id)
            move_id = make_invoice(ctx, partner_id, [(product_id, 1, 1000.00)],
                                   fiscal_position_id=fp_id)
            drafted = doc_totals(ctx, "account.move", move_id)
            ctx.check("invoice stays in Draft after Save", "draft",
                      drafted["state"])

        with ctx.step("Workbook step 5: click Compute Taxes"):
            compute_error = _compute_taxes_guarded(ctx, move_id)
            if compute_error:
                # Capture what the workbook's If-It-Fails column asks for
                # BEFORE the assertion raises and ends the step.
                _avatax_log_evidence(ctx, "Compute Taxes failed")
            ctx.check_true("Compute Taxes completes with no error banner",
                           not compute_error,
                           actual_desc=compute_error or CLEAN)

        with ctx.step("Workbook step 6: read the totals block — Untaxed "
                      "Amount, the tax line(s), Total"):
            totals = doc_totals(ctx, "account.move", move_id)
            lines = move_tax_lines(ctx, move_id)
            taxes = _tax_records(ctx, [line["tax_id"] for line in lines])
            _log_tax_lines(ctx, f"invoice #{move_id}", lines, taxes)
            ctx.log(f"totals block — untaxed {totals['untaxed']}, tax "
                    f"{totals['tax']}, total {totals['total']}")
            ctx.check("Untaxed Amount", 1000.00, totals["untaxed"])
            non_zero = [line for line in lines if line["balance"]]
            ctx.check_true(
                "at least one tax line with a non-zero amount",
                bool(non_zero) and totals["tax"] != 0.0,
                actual_desc=f"{len(lines)} tax line(s), {len(non_zero)} with a "
                            f"non-zero amount; amount_tax {totals['tax']}; "
                            f"names {_tax_names(lines, taxes)}")
            # The other half of this workbook line — "…that matches the rate
            # for the customer's address" — is only settleable against
            # Avalara's own breakdown, which lives in the sandbox portal this
            # platform cannot reach. It is logged, not silently dropped; the
            # per-authority split it implies is asserted by TC-TAX-002.
            effective = (round(totals["tax"] / totals["untaxed"] * 100, 4)
                         if totals["untaxed"] else 0.0)
            ctx.log(f"MANUAL RESIDUAL — effective rate {effective} % for "
                    f"{ADDRESS_PHOENIX_AZ['city']}, "
                    f"{ADDRESS_PHOENIX_AZ['state_code']} "
                    f"{ADDRESS_PHOENIX_AZ['zip']}. Confirm it against "
                    f"Avalara's own breakdown in the SANDBOX portal, looking "
                    f"the document up by its Avalara Code.")

        with ctx.step("Workbook step 7: open Other Info and read Avalara "
                      "Code"):
            # avatax_unique_code is computed by the account.avatax.unique.code
            # mixin as "<model description> <id>" — Odoo mints it, Avalara
            # only echoes it back — so the provable expectation is that it is
            # populated, which is also what makes the transaction findable in
            # the portal.
            ctx.log("Avalara Code is account.move.avatax_unique_code "
                    "(computed, not stored) — this asserts it is filled in, "
                    "and it is the transaction code to search the Avalara "
                    "sandbox portal with")
            ctx.check_true("Avalara Code on Other Info is filled in with a "
                           "value", bool(totals["avalara_code"]),
                           actual_desc=f"avatax_unique_code="
                                       f"{totals['avalara_code']!r}")

        with ctx.step("Workbook step 8: click Confirm"):
            post_error = _confirm_guarded(ctx, move_id)
            if post_error:
                ctx.log(f"Confirm raised: {post_error}")
            posted = doc_totals(ctx, "account.move", move_id)
            ctx.check("Confirm posts the invoice; its status becomes Posted",
                      "posted", posted["state"])
            ctx.log(f"posted invoice #{move_id} left in the sandbox by design "
                    f"(workbook: 'One posted sandbox invoice exists')")
    finally:
        with ctx.step("Cleanup: remove FG05 fixtures (the posted invoice "
                      "cannot be deleted and stays by design)"):
            cleanup(ctx, created)


# ----------------------------------------------------------- TC-TAX-002
@test_case(
    id="TEST-FG05-TAX-002",
    name="Tax is posted per taxing authority, not as one lumped amount",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P0",
    kind="API",
    order=502,
    description="GATE 3: the journal entry of a Phoenix AZ invoice carries "
                "MORE THAN ONE tax line, those lines add up exactly to the "
                "invoice's tax total, and every tax name is "
                "'<name> [<authority code>] (<rate>)'.",
    traceability=trace("TC-TAX-002"))
def test_tax_002(ctx):
    created = {"product.product": [], "res.partner": []}
    with ctx.step("Precondition: Odoo 19 with a usable Avalara SANDBOX and an "
                  "AvaTax fiscal position"):
        require_sandbox(ctx, "proving Avalara's per-jurisdiction split reaches "
                             "the journal entry as separate tax lines")
        fp_id, fp = require_avatax_fiscal_position(ctx)
        ctx.log(f"AvaTax fiscal position #{fp_id} {fp['name']!r}")
        ctx.log("workbook precondition: reading the journal entry needs "
                "account.move.line read access ('Show Accounting Features - "
                "Readonly'); a rights problem surfaces here as an RPC error, "
                "never as a missing split")
        ctx.log("the delivery address is deliberately multi-jurisdiction "
                "(Phoenix AZ) — a rural address may genuinely have a single "
                "authority and would make this case look like a failure")
        sweep_fg05(ctx)
    try:
        with ctx.step("Workbook step 1: an invoice as in TC-TAX-001, but "
                      "delivered to 1 E Washington St, Phoenix, AZ 85004 — "
                      "created, Compute Taxes, Confirm"):
            customer_id = make_partner(ctx, "TAX-002 Customer",
                                       ADDRESS_TUCSON_AZ,
                                       fiscal_position_id=fp_id)
            created["res.partner"].append(customer_id)
            delivery_id = make_partner(ctx, "TAX-002 Delivery Phoenix",
                                       ADDRESS_PHOENIX_AZ,
                                       parent_id=customer_id,
                                       partner_type="delivery")
            created["res.partner"].append(delivery_id)
            product_id = make_product(ctx, "TAX-002 Art Item", 1000.00)
            created["product.product"].append(product_id)
            invoice = _phoenix_invoice(ctx, fp_id, customer_id, delivery_id,
                                       product_id, 1000.00)
            ctx.check_true("Compute Taxes completes with no error banner",
                           not invoice["compute_error"],
                           actual_desc=invoice["compute_error"] or CLEAN)
            ctx.check("invoice status after Confirm", "posted",
                      invoice["totals"]["state"])
            ctx.log(f"MANUAL RESIDUAL — Avalara Code "
                    f"{invoice['totals']['avalara_code']!r}: look the document "
                    f"up in the Avalara SANDBOX portal to compare Avalara's "
                    f"own per-authority breakdown against the lines below")

        with ctx.step("Workbook steps 2-4: open the Journal Entry and write "
                      "down the account code, tax name and amount of every "
                      "line that carries a tax"):
            lines = invoice["lines"]
            taxes = invoice["taxes"]
            names = invoice["names"]
            _log_tax_lines(ctx, f"invoice #{invoice['move_id']}", lines, taxes)
            # Expectation 1 of 3 — the reason the custom AvaTax work exists.
            ctx.check_true(
                "MORE THAN ONE tax line on the journal entry, one per taxing "
                "authority (a single rolled-up line is a FAIL even when the "
                "amount is right)",
                len(lines) > 1,
                actual_desc=f"{len(lines)} tax line(s) on move "
                            f"#{invoice['move_id']}: {names}")

        with ctx.step("Workbook step 5: add up the tax amounts and compare "
                      "them against the tax figure on the invoice's totals "
                      "block"):
            # account.move.line.balance is debit - credit, and a customer
            # invoice CREDITS its tax accounts, so every tax line's balance is
            # negative while account.move.amount_tax is reported positive.
            # The sign is reconciled once, here, by negating the journal sum —
            # not with abs() per line, because abs() would swallow a
            # wrongly-signed tax line instead of surfacing it as a mismatch.
            journal_total = round(-sum(line["balance"] for line in lines), 2)
            ctx.log(f"journal-entry tax lines sum to {journal_total} "
                    f"(balances negated once: credits on an out_invoice); "
                    f"invoice amount_tax reads {invoice['totals']['tax']}")
            # Expectation 2 of 3 — both sides already rounded to 2dp.
            ctx.check("the tax amounts add up exactly to the tax total shown "
                      "on the invoice", invoice["totals"]["tax"],
                      journal_total)

        with ctx.step("Workbook step 6: look at the shape of each tax name"):
            offenders = [name for name in names
                         if not JURISDICTION_TAX_NAME_RE.match(name or "")]
            # Expectation 3 of 3 — 'AZ STATE 5.6%' (stock v19 naming) has no
            # square-bracketed authority code and is a FAIL by the workbook.
            ctx.check_true(
                "every tax name is '<name> [<authority code>] (<rate>)' — a "
                "name with no square-bracketed code is a FAIL",
                not offenders,
                actual_desc=(f"{len(offenders)} of {len(names)} name(s) do "
                             f"not match: {offenders}") if offenders
                else f"all {len(names)} name(s) match: {names}")
            ctx.log("posted invoice left in the sandbox by design (workbook: "
                    "'Leave it in place')")
    finally:
        with ctx.step("Cleanup: remove FG05 fixtures (the posted invoice "
                      "cannot be deleted and stays by design)"):
            cleanup(ctx, created)


# ----------------------------------------------------------- TC-TAX-003
@test_case(
    id="TEST-FG05-TAX-003",
    name="A second invoice to the same place reuses the same tax records",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P0",
    kind="API",
    order=503,
    description="A second Phoenix AZ invoice at 500.00 creates no new "
                "account.tax record for any authority code, reuses the same "
                "tax names, and carries about half the tax of the 1,000.00 "
                "invoice.",
    traceability=trace("TC-TAX-003"))
def test_tax_003(ctx):
    created = {"product.product": [], "res.partner": []}
    with ctx.step("Precondition: Odoo 19 with a usable Avalara SANDBOX and an "
                  "AvaTax fiscal position"):
        require_sandbox(ctx, "proving a second invoice to the same city "
                             "reuses the account.tax records the first one "
                             "created instead of duplicating them")
        fp_id, fp = require_avatax_fiscal_position(ctx)
        ctx.log(f"AvaTax fiscal position #{fp_id} {fp['name']!r}")
        sweep_fg05(ctx)
    try:
        with ctx.step("Rebuild TC-TAX-002's precondition inside this test: a "
                      "first posted invoice of 1,000.00 x 1 to the Phoenix "
                      "delivery address"):
            customer_id = make_partner(ctx, "TAX-003 Customer",
                                       ADDRESS_TUCSON_AZ,
                                       fiscal_position_id=fp_id)
            created["res.partner"].append(customer_id)
            delivery_id = make_partner(ctx, "TAX-003 Delivery Phoenix",
                                       ADDRESS_PHOENIX_AZ,
                                       parent_id=customer_id,
                                       partner_type="delivery")
            created["res.partner"].append(delivery_id)
            # The SAME product on both invoices: same AvaTax category, so the
            # rates Avalara applies are the same and only the base differs —
            # which is precisely the workbook's "a different amount,
            # deliberately".
            product_id = make_product(ctx, "TAX-003 Art Item", 1000.00)
            created["product.product"].append(product_id)
            first = _phoenix_invoice(ctx, fp_id, customer_id, delivery_id,
                                     product_id, 1000.00)
            _log_tax_lines(ctx, f"first invoice #{first['move_id']}",
                           first["lines"], first["taxes"])
            ctx.check_true(
                "the first invoice computed its tax and posted (this case's "
                "starting state)",
                not first["compute_error"]
                and first["totals"]["state"] == "posted"
                and bool(first["lines"]),
                actual_desc=f"compute error "
                            f"{first['compute_error'] or CLEAN!r}; post error "
                            f"{first['post_error'] or CLEAN!r}; state "
                            f"{first['totals']['state']}; "
                            f"{len(first['lines'])} tax line(s); tax "
                            f"{first['totals']['tax']}")

        with ctx.step("Workbook step 1: search the Taxes list for the "
                      "bracketed authority code(s) of the first invoice's tax "
                      "names and write the number of records down"):
            codes = sorted({code for name in first["names"]
                            for code in AUTHORITY_CODE_RE.findall(name or "")})
            ctx.check_true("the first invoice's tax names carry a bracketed "
                           "authority code to search on",
                           bool(codes),
                           actual_desc=f"codes {codes} extracted from "
                                       f"{first['names']}")
            before_all = _authority_tax_names(ctx, codes,
                                              include_archived=True)
            before_active = _authority_tax_names(ctx, codes,
                                                 include_archived=False)
            for code in codes:
                ctx.log(f"[{code}] before the second invoice: "
                        f"{len(before_active[code])} active / "
                        f"{len(before_all[code])} including archived — "
                        f"{before_active[code]}")

        with ctx.step("Workbook steps 2-4: a second invoice to the SAME "
                      "customer and the SAME Phoenix delivery address, one "
                      "line 500.00 x 1 — Save, Compute Taxes, Confirm"):
            second = _phoenix_invoice(ctx, fp_id, customer_id, delivery_id,
                                      product_id, 500.00)
            _log_tax_lines(ctx, f"second invoice #{second['move_id']}",
                           second["lines"], second["taxes"])
            ctx.check_true("Compute Taxes on the second invoice completes "
                           "with no error banner",
                           not second["compute_error"],
                           actual_desc=second["compute_error"] or CLEAN)
            ctx.check("second invoice status after Confirm", "posted",
                      second["totals"]["state"])

        with ctx.step("Workbook steps 5-6: repeat the Taxes search and "
                      "compare the number of records against step 1"):
            after_all = _authority_tax_names(ctx, codes, include_archived=True)
            after_active = _authority_tax_names(ctx, codes,
                                                include_archived=False)
            for code in codes:
                appeared = sorted(set(after_all[code]) - set(before_all[code]))
                if appeared:
                    # Workbook "If It Fails": list the records that appeared,
                    # so a rate change at Avalara can be told apart from a
                    # duplication defect without a rerun.
                    ctx.log(f"[{code}] NEW account.tax record(s) after the "
                            f"second invoice: {appeared}")
            for code in codes:
                # Expectation 1 of 3, asserted twice per authority code: the
                # active count is what the tester reads off the Taxes list,
                # the archived-inclusive count is what proves nothing was
                # created at all (see _authority_tax_names).
                ctx.check(f"account.tax records matching [{code}] — active, "
                          f"as the Taxes list shows them",
                          len(before_active[code]), len(after_active[code]))
                ctx.check(f"account.tax records matching [{code}] — including "
                          f"archived records",
                          len(before_all[code]), len(after_all[code]))

        with ctx.step("Workbook expectation: the second invoice's tax lines "
                      "use the same tax names as the first invoice's"):
            # Expectation 2 of 3. Sets, not lists: the workbook compares the
            # names used, and journal-item ORDER carries no meaning.
            ctx.check("tax names used by the second invoice",
                      sorted(set(first["names"])),
                      sorted(set(second["names"])))

        with ctx.step("Workbook expectation: the tax amount on the second "
                      "invoice is about half the first one's, because the "
                      "amount is half and the rates are the same"):
            first_tax = first["totals"]["tax"]
            second_tax = second["totals"]["tax"]
            half = round(first_tax / 2, 2)
            # Expectation 3 of 3, as proportionality with a tolerance — never
            # as an exact figure, because no exact figure was asked of
            # Avalara. Two things stop half-the-base from meaning
            # exactly-half-the-tax, and BOTH are measured on the first
            # invoice rather than guessed:
            #   * a flat per-transaction fee (account.tax.amount_type ==
            #     'fixed', e.g. "AZ RETAIL DELIVERY FEE [AZ] ($ 0.2700)")
            #     does not scale with the base: it contributes the same F to
            #     both invoices, so second_tax - first_tax/2 is exactly F/2;
            #   * each jurisdiction's amount is rounded to the currency's two
            #     decimals independently, so allow one cent per tax line.
            # tolerance = F/2 + 0.01 x (number of tax lines). With no flat
            # fee — the usual case — that collapses to a few cents.
            flat = round(sum(abs(line["balance"]) for line in first["lines"]
                             if (first["taxes"].get(line["tax_id"]) or {})
                             .get("amount_type") == "fixed"), 2)
            tolerance = round(flat / 2 + 0.01 * max(len(first["lines"]), 1), 2)
            deviation = round(abs(second_tax - half), 2)
            ctx.check_true(
                "the second invoice's tax is about half the first invoice's",
                bool(first_tax) and deviation <= tolerance,
                actual_desc=f"first invoice tax {first_tax} on a base of "
                            f"1000.00, second {second_tax} on 500.00; half of "
                            f"the first is {half}, deviation {deviation} "
                            f"against a tolerance of {tolerance} "
                            f"(non-scaling flat fees {flat} on the first "
                            f"invoice, {len(first['lines'])} tax line(s) x "
                            f"0.01 rounding)")
            ctx.log("both posted invoices left in the sandbox by design "
                    "(workbook: 'Leave both')")
    finally:
        with ctx.step("Cleanup: remove FG05 fixtures (the two posted invoices "
                      "cannot be deleted and stay by design)"):
            cleanup(ctx, created)
