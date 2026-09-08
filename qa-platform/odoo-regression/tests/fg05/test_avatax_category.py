"""FG-05 — AvaTax product categories: TC-TAX-014 and TC-TAX-016.

TC-TAX-014  The AvaTax category on a product category drives the tax
            treatment: switching the category's ``avatax_category_id`` between
            two codes Avalara treats differently moves the Taxes figure on an
            otherwise identical draft invoice.
TC-TAX-016  One invoice mixing a taxable line (1,000.00) and an exempt /
            zero-rated line (500.00) taxes only the taxable line.

Both cases turn on ``product.avatax.category`` codes. The resolution path
Avalara actually uses is ``product.product._get_avatax_category_id()`` — the
product's own code, else the template's, else
``product.category._get_avatax_category_id()`` walking ``parent_id`` upwards
(account_avatax/models/product.py:29-57) — and the resolved ``code`` is sent
as the line's ``taxCode``
(account_avatax/models/account_external_tax_mixin.py:88-104). A product with
no resolvable category makes that method raise
``The Avalara Tax Code is required for ...``, so every FG05 product here is
created inside an FG05 product category that carries a code.

Documented adaptations
----------------------
1. **TC-TAX-014 never mutates a live product category.** The workbook has the
   tester change the AvaTax code on the Internal Category of a real art item
   and put it back at step 7, and its own If It Fails column calls that the
   biggest risk in the case: "Leaving a test category code on a live product
   category mis-taxes everything in it." This test creates an FG05 product
   category and an FG05 product inside it and switches *that* category's code,
   which exercises the identical resolution path and identical Avalara request
   with none of the blast radius. The restore discipline is kept in full: the
   original value is captured, restored in ``finally:``, and the restore is
   recorded as an assertion so a failed restore is visible rather than silent.
2. **TC-TAX-016 does not reuse "the rate you saw in TC-TAX-001".** The
   platform forbids depending on another test's fixtures or figures, so the
   expected tax on the 1,000.00 line is established in-test by a control
   invoice — same customer, same ship-to, same fiscal position, same day,
   containing ONLY the taxable line. See the comment on that step for why a
   control document beats multiplying a rate by 1,000.00. The control also
   carries over the property the broken chain used to supply: TC-TAX-016
   requires TC-TAX-001 to have passed, and TC-TAX-001's Expected Result
   asserts a NON-ZERO tax on the same 1,000.00 line, so the control's tax
   being non-zero is asserted before its figure is compared against the mixed
   invoice's.
3. **Neither test hard-codes an AvaTax code pair.** Both read
   ``product.avatax.category`` on the target database and pick two codes with
   genuinely different treatments, preferring the general taxable code and the
   non-taxable code that ship with ``account_avatax`` (3,483 rows in
   ``data/product.avatax.category.csv``). Both codes are logged on every run so
   triage can tell a bad data choice from a defect — the distinction both
   workbook rows make in their If It Fails column. Fewer than two codes on the
   database is BLOCKED, not FAILED.
"""
from __future__ import annotations

from adapters.base import OdooRPCError
from framework.registry import test_case
from tests.fg05.common import (ADDRESS_PHOENIX_AZ, MODULE, WORKFLOW,
                               WORKFLOW_NAME, cleanup, compute_taxes,
                               doc_totals, make_invoice, make_partner,
                               make_product, make_product_category,
                               move_tax_lines, require_avatax_fiscal_position,
                               require_sandbox, sweep_fg05, trace)

AVATAX_CATEGORY = "product.avatax.category"

# Codes preferred for the "taxable" side of the pair, best first. All three
# ship with account_avatax and are taxable wherever a sales tax exists:
#   P0000000  Tangible personal property (tpp)          — the general good
#   O9999999  Temporary unmapped other sku - taxable default
#   FR999999  Temporary unmapped freight sku - taxable default
TAXABLE_CODE_PREFERENCE = ["P0000000", "O9999999", "FR999999"]

# Codes preferred for the "exempt / zero-rated" side, best first:
#   NT        Non-taxable product
#   ON030000  Non-taxable transaction
EXEMPT_CODE_PREFERENCE = ["NT", "ON030000"]

TAXCODE_PORTAL = "https://taxcode.avatax.avalara.com/"


def _no_codes_block(detail: str) -> str:
    """BLOCKED reason when the database cannot supply the code pair."""
    return (
        f"this case needs two AvaTax category codes that Avalara treats "
        f"differently, and {detail}. The workbook precondition is explicit: "
        f"'You know two AvaTax category codes that Avalara treats "
        f"differently. Novobi supplies these; taxcode.avatax.avalara.com "
        f"lists them.' Load the account_avatax product.avatax.category data "
        f"(3,483 codes ship with the module), or ask Novobi for the pair "
        f"agreed for the gallery and look both up on {TAXCODE_PORTAL}, then "
        f"re-run. This is a setup gap, not a product defect"
    )


def _m2o_id(value):
    """Many2one values read back as ``[id, display_name]``."""
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    return value or None


def _category_by_code(rpc, code: str):
    found = rpc.search_read(AVATAX_CATEGORY, [("code", "=", code)],
                            ["code", "description"], limit=1)
    return found[0] if found else None


def _first_available(rpc, preference: list):
    for code in preference:
        found = _category_by_code(rpc, code)
        if found:
            return found
    return None


def _pick_contrasting_categories(ctx):
    """Two ``product.avatax.category`` records with different treatments.

    Returns ``(taxable, exempt, contrast_known)``. ``contrast_known`` is True
    only when both records came from the preference lists above, i.e. when the
    difference in treatment is a documented property of the codes rather than
    an assumption about two arbitrary rows. Callers log it either way; the
    workbook's expectation is never softened because of it.
    """
    rpc = ctx.adapter.rpc
    if not rpc.model_exists(AVATAX_CATEGORY):
        ctx.blocked(_no_codes_block(
            f"the model {AVATAX_CATEGORY} does not exist on this database "
            f"(Odoo Enterprise account_avatax is not installed)"))

    taxable = _first_available(rpc, TAXABLE_CODE_PREFERENCE)
    exempt = _first_available(rpc, EXEMPT_CODE_PREFERENCE)
    if taxable and exempt and taxable["id"] != exempt["id"]:
        return taxable, exempt, True

    # Neither preferred pair is loaded. Fall back to the two lowest codes on
    # the database so the case still runs, and tell the caller the contrast is
    # unverified so it can say so in evidence.
    fallback = rpc.search_read(AVATAX_CATEGORY, [], ["code", "description"],
                               order="code", limit=2)
    if len(fallback) < 2:
        ctx.blocked(_no_codes_block(
            f"only {len(fallback)} AvaTax category code(s) exist on this "
            f"database"))
    return fallback[0], fallback[1], False


def _describe(category: dict) -> str:
    return f"{category['code']!r} ({category.get('description') or ''})"


def _compute_taxes_guarded(ctx, model: str, record_id: int) -> str:
    """Click Compute Taxes; return the error text instead of raising.

    The workbook expectation "No error at either step" / "No error banner" is
    an assertion in its own right, so the failure has to reach ``ctx.check``
    with an expected-vs-actual pair rather than escaping as an exception.
    """
    try:
        compute_taxes(ctx, model, record_id)
        return ""
    except OdooRPCError as exc:
        return str(exc)


def _log_tax_lines(ctx, move_id: int, label: str):
    """Workbook step: open the Journal Entry and read the tax lines.

    A customer invoice IS its journal entry in v19, and the tax journal items
    (``account.move.line`` with ``tax_line_id`` set) exist while the move is
    still draft, so the smart button's content is readable without posting.
    """
    lines = move_tax_lines(ctx, move_id)
    if not lines:
        ctx.log(f"[journal entry] {label} invoice #{move_id}: no tax journal "
                f"item — Avalara returned no tax for this document")
        return lines
    for line in lines:
        ctx.log(f"[journal entry] {label} invoice #{move_id}: "
                f"{line['tax_name']!r} on account {line['account']!r} "
                f"balance {line['balance']:.2f}")
    return lines


@test_case(
    id="TEST-FG05-TAX-014",
    name="The AvaTax category on a product category drives the tax treatment",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P1",
    kind="API",
    order=510,
    description="Switching a product category's avatax_category_id between "
                "two codes Avalara treats differently moves the Taxes figure "
                "on the same draft invoice; the original code is restored and "
                "the restore is asserted.",
    traceability=trace("TC-TAX-014"))
def test_tax_014(ctx):
    rpc = ctx.adapter.rpc
    created = {"account.move": [], "product.product": [],
               "product.category": [], "res.partner": []}
    categ_id = None
    original_code_id = None

    with ctx.step("Precondition: Odoo 19 with a usable Avalara SANDBOX"):
        require_sandbox(ctx, "recomputing tax on one draft invoice after the "
                             "product category's AvaTax code changes")
        fp_id, fiscal_position = require_avatax_fiscal_position(ctx)
        ctx.log(f"AvaTax fiscal position #{fp_id} "
                f"{fiscal_position['name']!r}")
        sweep_fg05(ctx)

    with ctx.step("Precondition: two AvaTax category codes Avalara treats "
                  "differently"):
        code_a, code_b, contrast_known = _pick_contrasting_categories(ctx)
        # Logged before anything is computed: the workbook's If It Fails
        # column says an unmoved figure may be a data choice (two codes taxed
        # the same in that state) rather than a defect, and triage can only
        # tell them apart with both codes in front of it.
        ctx.log(f"[data choice] AvaTax code A (step 2 original) = "
                f"{_describe(code_a)}; code B (step 4 replacement) = "
                f"{_describe(code_b)}; ship-to = Phoenix AZ 85004. Both codes "
                f"are listed on {TAXCODE_PORTAL}")
        if not contrast_known:
            ctx.log(f"[data choice] WARNING — neither preferred pair "
                    f"(taxable {TAXABLE_CODE_PREFERENCE} / exempt "
                    f"{EXEMPT_CODE_PREFERENCE}) is loaded on this database, "
                    f"so the two codes above were taken arbitrarily and their "
                    f"treatments are NOT known to differ. If the Taxes figure "
                    f"does not move, check these two codes with Novobi "
                    f"before raising a defect")

    try:
        with ctx.step("Steps 1-2 (workbook, adapted): an FG05 product "
                      "category carrying code A, an FG05 product inside it, "
                      "and the customer"):
            # ADAPTATION: an FG05 category instead of a live one. See the
            # module docstring — the workbook's own If It Fails column names
            # a test code left on a live category as the case's biggest risk.
            categ_id = make_product_category(
                ctx, "TAX-014 Category", avatax_category_id=code_a["id"])
            created["product.category"].append(categ_id)
            read_back = rpc.read("product.category", [categ_id],
                                 ["name", "avatax_category_id"])[0]
            original_code_id = _m2o_id(read_back["avatax_category_id"])
            ctx.check("Step 2 — the product category's AvaTax Category reads "
                      "code A", code_a["id"], original_code_id)
            ctx.log(f"fixture product category #{categ_id} "
                    f"{read_back['name']!r} — original AvaTax Category "
                    f"written down: {_describe(code_a)}")

            product_id = make_product(ctx, "TAX-014 Item", 1000.00,
                                      categ_id=categ_id)
            created["product.product"].append(product_id)
            partner_id = make_partner(ctx, "TAX-014 Customer",
                                      ADDRESS_PHOENIX_AZ,
                                      fiscal_position_id=fp_id)
            created["res.partner"].append(partner_id)

        with ctx.step("Step 3 (workbook): invoice with one line @ 1,000.00, "
                      "Compute Taxes, write the Taxes figure down"):
            move_id = make_invoice(ctx, partner_id, [(product_id, 1, 1000.00)],
                                   fiscal_position_id=fp_id)
            created["account.move"].append(move_id)
            error_first = _compute_taxes_guarded(ctx, "account.move", move_id)
            ctx.check("Step 3 — Compute Taxes raised no error", "",
                      error_first)
            first = doc_totals(ctx, "account.move", move_id)
            ctx.check("Step 3 — Untaxed Amount", 1000.00, first["untaxed"])
            ctx.log(f"Taxes with code {code_a['code']!r}: "
                    f"{first['tax']:.2f} (total {first['total']:.2f})")

        with ctx.step("Step 4 (workbook, adapted): change the FG05 product "
                      "category's AvaTax Category to code B"):
            rpc.write("product.category", [categ_id],
                      {"avatax_category_id": code_b["id"]})
            switched = rpc.read("product.category", [categ_id],
                                ["avatax_category_id"])[0]
            ctx.check("Step 4 — the product category now carries code B",
                      code_b["id"], _m2o_id(switched["avatax_category_id"]))

        with ctx.step("Step 5 (workbook): Compute Taxes again on the same "
                      "still-draft invoice"):
            ctx.check("Step 5 — the invoice is still in draft", "draft",
                      doc_totals(ctx, "account.move", move_id)["state"])
            error_second = _compute_taxes_guarded(ctx, "account.move", move_id)
            ctx.check("Step 5 — Compute Taxes raised no error", "",
                      error_second)
            second = doc_totals(ctx, "account.move", move_id)
            ctx.log(f"Taxes with code {code_b['code']!r}: "
                    f"{second['tax']:.2f} (total {second['total']:.2f})")

        with ctx.step("Step 6 (workbook): read the new Taxes figure and "
                      "compare"):
            ctx.check("Step 6 — Untaxed Amount is unchanged, only the tax "
                      "treatment moved", 1000.00, second["untaxed"])
            ctx.log(f"[result] code {code_a['code']!r} -> Taxes "
                    f"{first['tax']:.2f} | code {code_b['code']!r} -> Taxes "
                    f"{second['tax']:.2f} on the same 1,000.00 line to "
                    f"Phoenix AZ 85004")
            ctx.check_true(
                "Step 6 — the Taxes figure changed between the first and the "
                "second Compute Taxes, because Avalara treated the goods "
                "differently",
                first["tax"] != second["tax"],
                actual_desc=(f"{code_a['code']} -> {first['tax']:.2f}; "
                             f"{code_b['code']} -> {second['tax']:.2f}"))
    finally:
        try:
            with ctx.step("Step 7 (workbook): put the product category's "
                          "AvaTax Category back to its original value"):
                if categ_id and original_code_id:
                    restore_error = ""
                    try:
                        rpc.write("product.category", [categ_id],
                                  {"avatax_category_id": original_code_id})
                    except OdooRPCError as exc:
                        restore_error = str(exc)
                    if restore_error:
                        ctx.log(f"[restore] write failed: {restore_error}")
                    final = rpc.read("product.category", [categ_id],
                                     ["avatax_category_id"])[0]
                    ctx.check(
                        "Step 7 — after the restore the category carries its "
                        "original AvaTax code again", original_code_id,
                        _m2o_id(final["avatax_category_id"]))
                else:
                    ctx.log("[restore] the FG05 product category was never "
                            "created, so there is nothing to restore — no "
                            "live category was touched at any point")
        finally:
            with ctx.step("Cleanup: remove FG05 fixtures"):
                cleanup(ctx, created)


@test_case(
    id="TEST-FG05-TAX-016",
    name="One invoice mixing taxable and exempt items taxes only the taxable lines",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P1",
    kind="API",
    order=512,
    description="An invoice of a 1,000.00 taxable line plus a 500.00 exempt "
                "line reads Untaxed 1,500.00 and carries only the tax a "
                "control invoice of the taxable line alone produces.",
    traceability=trace("TC-TAX-016"))
def test_tax_016(ctx):
    created = {"account.move": [], "product.product": [],
               "product.category": [], "res.partner": []}

    with ctx.step("Precondition: Odoo 19 with a usable Avalara SANDBOX"):
        require_sandbox(ctx, "taxing one invoice that mixes a taxable line "
                             "and an exempt / zero-rated line")
        fp_id, fiscal_position = require_avatax_fiscal_position(ctx)
        ctx.log(f"AvaTax fiscal position #{fp_id} "
                f"{fiscal_position['name']!r}")
        sweep_fg05(ctx)

    with ctx.step("Precondition: one taxable and one exempt / zero-rated "
                  "AvaTax category code"):
        taxable, exempt, contrast_known = _pick_contrasting_categories(ctx)
        ctx.log(f"[data choice] taxable line code = {_describe(taxable)}; "
                f"exempt / zero-rated line code = {_describe(exempt)}; "
                f"ship-to = Phoenix AZ 85004. Both codes are listed on "
                f"{TAXCODE_PORTAL}")
        if not contrast_known:
            ctx.log(f"[data choice] WARNING — neither preferred pair "
                    f"(taxable {TAXABLE_CODE_PREFERENCE} / exempt "
                    f"{EXEMPT_CODE_PREFERENCE}) is loaded on this database, "
                    f"so the 'exempt' code above is not known to be exempt. "
                    f"The workbook's If It Fails column calls that a data "
                    f"choice problem and not a defect — confirm the codes "
                    f"with Novobi before raising one")

    try:
        with ctx.step("Setup: two FG05 product categories carrying the two "
                      "codes, one FG05 product in each, and the customer"):
            taxable_categ = make_product_category(
                ctx, "TAX-016 Taxable Category",
                avatax_category_id=taxable["id"])
            exempt_categ = make_product_category(
                ctx, "TAX-016 Exempt Category",
                avatax_category_id=exempt["id"])
            created["product.category"].extend([taxable_categ, exempt_categ])
            ctx.check_true(
                "the two FG05 product categories carry the two different "
                "AvaTax codes",
                taxable["id"] != exempt["id"],
                actual_desc=(f"category #{taxable_categ} -> "
                             f"{taxable['code']}; category #{exempt_categ} -> "
                             f"{exempt['code']}"))

            taxable_product = make_product(ctx, "TAX-016 Taxable Item",
                                           1000.00, categ_id=taxable_categ)
            exempt_product = make_product(ctx, "TAX-016 Exempt Item", 500.00,
                                          categ_id=exempt_categ)
            created["product.product"].extend([taxable_product,
                                               exempt_product])
            partner_id = make_partner(ctx, "TAX-016 Customer",
                                      ADDRESS_PHOENIX_AZ,
                                      fiscal_position_id=fp_id)
            created["res.partner"].append(partner_id)

        with ctx.step("Steps 1-2 (workbook): create the invoice with BOTH "
                      "lines — taxable 1,000.00 and exempt 500.00"):
            mixed_id = make_invoice(ctx, partner_id,
                                    [(taxable_product, 1, 1000.00),
                                     (exempt_product, 1, 500.00)],
                                    fiscal_position_id=fp_id)
            created["account.move"].append(mixed_id)

        with ctx.step("Step 3 (workbook): save, then click Compute Taxes"):
            mixed_error = _compute_taxes_guarded(ctx, "account.move", mixed_id)
            ctx.check("Step 3 — Compute Taxes raised no error banner", "",
                      mixed_error)

        with ctx.step("Step 4 (workbook): read the totals block — Untaxed "
                      "Amount, Taxes, Total"):
            mixed = doc_totals(ctx, "account.move", mixed_id)
            ctx.log(f"mixed invoice #{mixed_id}: untaxed "
                    f"{mixed['untaxed']:.2f}, taxes {mixed['tax']:.2f}, "
                    f"total {mixed['total']:.2f}")
            ctx.check("Step 4 — Untaxed Amount is 1,500.00", 1500.00,
                      mixed["untaxed"])

        with ctx.step("Step 5 (workbook): open the Journal Entry and read "
                      "the tax lines"):
            _log_tax_lines(ctx, mixed_id, "mixed")

        with ctx.step("Step 6 (workbook, adapted): control invoice — the "
                      "SAME customer and ship-to, the taxable 1,000.00 line "
                      "ONLY"):
            # ADAPTATION + why a control document rather than "rate x 1000":
            # Avalara returns a per-jurisdiction breakdown (state, county,
            # city, special districts), each rounded on its own, and some
            # jurisdictions add a flat per-transaction fee rather than a
            # percentage — MMG's _extract_tax_values_from_avatax_detail keeps
            # both forms ("... (5.6000 %)" and "... ($ 0.2700)"). Reducing
            # that to a single rate and multiplying by 1,000.00 reproduces
            # neither the rounding nor the flat components, so the comparison
            # would only ever be approximate. A second invoice that differs
            # from the first in exactly one respect — the exempt line is
            # absent — isolates that line's contribution exactly, with no
            # assumption about rates at all. Same partner record, same
            # fiscal position, same day (invoice_date is left unset on both,
            # so Avalara dates both with today), so the ship-to jurisdiction
            # and the rate table are identical for the two documents.
            control_id = make_invoice(ctx, partner_id,
                                      [(taxable_product, 1, 1000.00)],
                                      fiscal_position_id=fp_id)
            created["account.move"].append(control_id)
            control_error = _compute_taxes_guarded(ctx, "account.move",
                                                   control_id)
            ctx.check("Step 6 — Compute Taxes on the control invoice raised "
                      "no error", "", control_error)
            control = doc_totals(ctx, "account.move", control_id)
            ctx.check("Step 6 — the control invoice carries the taxable line "
                      "alone", 1000.00, control["untaxed"])
            _log_tax_lines(ctx, control_id, "control")
            ctx.log(f"[control] tax on the 1,000.00 {taxable['code']} line "
                    f"alone = {control['tax']:.2f}")
            if control["tax"] == 0.00:
                ctx.log(f"[data choice] the control invoice was taxed 0.00, so "
                        f"code {taxable['code']!r} is not taxable at Phoenix "
                        f"AZ 85004. Confirm the pair with Novobi against "
                        f"{TAXCODE_PORTAL} — note the workbook's If It Fails "
                        f"column excuses a wrongly-chosen EXEMPT code as a "
                        f"data choice, NOT a non-taxable code on the taxable "
                        f"line")
            # Asserted BEFORE step 7 is trusted. The workbook establishes this
            # figure by a chain — TC-TAX-016's Preconditions require TC-TAX-001
            # to have passed, and step 6 says "Work out, from the rate you saw
            # in TC-TAX-001, what the tax on 1,000.00 alone should be" — and
            # TC-TAX-001's Expected Result asserts "at least one tax line with
            # a non-zero amount" on that same 1,000.00 line. The in-test control
            # invoice replaces the chained figure, so it has to carry that
            # non-zero property over: at 0.00 both of step 7's comparisons pass
            # vacuously (control 0.00 == mixed 0.00, and 1,500.00 + 0.00 ==
            # 1,500.00) while proving nothing about per-line taxation. Same
            # treatment TC-TAX-013 gives its taxable control invoice — "a zero
            # on BOTH means AvaTax is not calculating at all".
            ctx.check_true(
                "Step 6 — the control invoice's tax on the taxable 1,000.00 "
                "line is NON-ZERO, so the step 7 comparison can tell 'only "
                "the taxable line was taxed' from 'nothing was taxed at all'",
                control["tax"] != 0.00,
                actual_desc=(
                    f"control invoice #{control_id} Taxes = "
                    f"{control['tax']:.2f} on an untaxed "
                    f"{control['untaxed']:.2f} (total "
                    f"{control['total']:.2f}); taxable line AvaTax code = "
                    f"{taxable['code']}, exempt / zero-rated line AvaTax code "
                    f"= {exempt['code']}; ship-to = "
                    f"{ADDRESS_PHOENIX_AZ['street']}, "
                    f"{ADDRESS_PHOENIX_AZ['city']} "
                    f"{ADDRESS_PHOENIX_AZ['state_code']} "
                    f"{ADDRESS_PHOENIX_AZ['zip']}"))

        with ctx.step("Step 7 (workbook): compare the mixed invoice's Taxes "
                      "against the tax on the 1,000.00 line alone"):
            ctx.check("Step 7 — Taxes correspond to tax on the 1,000.00 line "
                      "ONLY, not on 1,500.00", control["tax"], mixed["tax"])
            ctx.check("Step 4 — Total is 1,500.00 plus that tax",
                      round(1500.00 + control["tax"], 2), mixed["total"])
    finally:
        with ctx.step("Cleanup: remove FG05 fixtures"):
            cleanup(ctx, created)
