"""FG-05 — Tax on quotations: TC-TAX-007, TC-TAX-008, TC-TAX-009.

Source of truth: the CLIENT MANUAL TESTING GUIDELINE
``MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0.xlsx``, sheet
``Testing Guideline``, rows 5.0–7.0. Every Expected Result line below is
implemented as its own ``ctx.check`` / ``ctx.check_true``, verbatim.

What the three cases prove
--------------------------
* **TC-TAX-007** — a quotation whose *delivery* contact has no zip, state or
  country is refused, the refusal names that contact (not the invoicing
  partner), no tax is calculated, and once the contact's address is completed
  the document gets past the guard. The behaviour is
  ``mmg_account_avatax_enhancement``'s
  ``account.external.tax.mixin._check_partner_shipping_address()``; stock
  Odoo 19 validates only ``partner_id`` and, on ``sale.order``, leaves
  ``perform_address_validation`` at ``None`` so it validates nothing at all
  before invoicing (module README §1–2).
* **TC-TAX-008** — Compute Taxes on a quotation returns a non-zero tax, the
  Total is the arithmetic sum of Untaxed + Taxes, and Avalara Code is filled.
* **TC-TAX-009** — the same document taxed against Phoenix AZ and then
  Missoula MT returns two different figures, the Montana one materially
  lower, with the Total recalculated to match.

Guard timing — why TC-TAX-007 accepts two moments
-------------------------------------------------
The guard is an ``@api.constrains`` on ``partner_id`` / ``fiscal_position_id``
/ ``partner_shipping_id``. On Odoo 19 a constraint fires on the create or
write that touches a trigger field, so it fires on the **save that sets the
Delivery Address** — i.e. before the workbook's step 7 (Compute Taxes). The
test therefore attempts the save first: if the save is refused, that IS the
guard, and the message is asserted there; only if the save goes through is
Compute Taxes pressed and the refusal asserted on the button instead — and
that fallback press is itself gated on the sandbox (see adaptation 1), because
on v19 ``_get_external_taxes`` never calls ``_check_address``, so a press
cannot raise the address error and would only reach Avalara. Either timing
satisfies the workbook, and the log records which one fired.

Documented adaptations
----------------------
1. **TC-TAX-007 runs without Avalara credentials — on purpose, and without
   calling Avalara at all in that case.** It calls :func:`require_v19` and
   deliberately does NOT call ``require_sandbox``: the guard is an
   ``@api.constrains`` that raises before anything is sent to Avalara, and
   the client guideline says this is the one FG-05 case that "can be run
   while you are still waiting for Avalara credentials". Blocking it on
   credentials would destroy its value.

   The *button*, however, is not credential-free.
   ``button_external_tax_calculation``
   (``account_external_tax/models/account_external_tax_mixin.py:175``) runs
   ``_get_and_set_external_taxes_on_eligible_records`` ->
   ``account_avatax/models/account_external_tax_mixin.py:308 _get_client``,
   which builds ``AvataxClient(environment=company.avalara_environment)``
   (line 320) and files a ``create_transaction``. Nothing on that path
   consults ``avalara_environment``, so on a production-pointed company the
   press files a REAL tax document — and ``_press_compute_taxes`` re-issues
   the identical call inside :func:`_server_error_message` on failure, so it
   would be two. TC-TAX-007 therefore reads the company configuration with
   :func:`~tests.fg05.common.company_avatax_config` and presses Compute Taxes
   only when :func:`_sandbox_ready` holds — the same condition
   ``require_sandbox`` enforces, applied per press instead of as a BLOCK.
   Workbook steps 1-9 need no credentials and always run in full.

   Its step-10 expectation is branched the way the workbook branches it:
   *with* a usable sandbox the workbook requires that "Compute Taxes now
   succeeds", so the test asserts success (a non-address failure such as
   ``UserError("The Avalara Tax Code is required for ...")`` from
   ``account_avatax/models/account_external_tax_mixin.py:90-95`` is a FAIL,
   not a pass) and then checks the recomputed totals; *without* one the press
   is not made at all, and the workbook's "that is still a pass ... because
   the address guard let it through" is asserted from step 9's re-save — the
   same ``@api.constrains`` that refused the document at step 8 now accepts
   the completed delivery contact. Nothing is weakened: the credential-free
   branch asserts the only thing the workbook claims for it.
2. **Cross-test independence.** The workbook chains TC-TAX-009 onto
   TC-TAX-008's saved quotation. The platform forbids depending on another
   test's fixtures, so TC-TAX-009 builds its own equivalent quotation (same
   one line, 2,000.00 x 1) and its own two delivery contacts under one
   customer. The business assertion is unchanged.
3. **Quotations go through the shared helper.** :func:`_make_quotation` is a
   thin wrapper over ``common.make_quotation`` that adds the ship-to id to
   the log line. (It was briefly a full local copy: the shared helper cleared
   the line taxes with ``tax_id``, the field Odoo 18 renamed to ``tax_ids`` on
   ``sale.order.line`` — ``addons/sale/models/sale_order_line.py``:
   ``tax_ids = fields.Many2many``, with no ``tax_id`` surviving on the model
   in 19.0 — so its ``create`` raised "Invalid field" on the v19 target. The
   shared helper has since been corrected and the copy removed.)
4. **Full server error text.** ``adapters.base.OdooRPC.call`` reports only
   ``splitlines()[-1]`` of a server error, which throws away the first line
   of the guard's two-line ``ValidationError`` — exactly the sentence
   TC-TAX-007 is about. :func:`_server_error_message` re-issues the identical
   call through the public ``framework.fg_common.http_session`` helper and
   reads ``error.data.message`` untouched. Nothing in the framework is
   modified, and the repeat is safe because the raised constraint rolled its
   transaction back. The helper itself now lives in
   ``tests.fg05.common.server_error_message`` — TC-TAX-017 asserts the
   readability of the same untruncated text.
5. **"Materially lower" is quantified.** TC-TAX-009's second expectation is
   asserted as *Montana < Arizona* AND *Montana at most half of Arizona*.
   Arizona's state rate alone is 5.6 % and Montana levies no state sales tax,
   so the half-of margin is comfortably inside the real gap while still
   refusing to pass on a one-cent difference.
6. **The warehouse shipFrom precondition is a GATE, not an assertion.** On
   ``sale.order`` — and only there — Odoo 19 Enterprise sends a *line-level*
   ``shipFrom`` built from the line's warehouse address, and it builds an
   empty one rather than skipping it when the warehouse has no address
   (``account_avatax_stock/models/account_external_tax_mixin.py:32-35`` plus
   the dead ``_fields`` guard in
   ``account_avatax/models/account_external_tax_mixin.py:108-121``; see
   :data:`~tests.fg05.common.ODOO_SHIPFROM_DEFECT`). Avalara then rejects the
   whole ``CreateTransaction`` with *"Unknown country name or code (FALSE)"*
   and the quotation gets **no tax figure at all**, so every quotation
   expectation becomes unevaluable — the case is not wrong, the document
   simply never came back. :func:`~tests.fg05.common.
   require_warehouse_shipfrom` is therefore called on the quotation before any
   Compute Taxes press that the case's verdict depends on, and reports BLOCKED
   naming the warehouse, exactly what is missing, the Inventory remedy and the
   two Odoo defects. Nothing is weakened: no assertion changed, and the gate
   is a precondition probe of the same kind as ``require_sandbox``. It is
   applied only where a warehouse is genuinely involved — the invoice cases in
   this suite never call it, because ``account_avatax_stock`` leaves an
   invoice line's warehouse ``None`` unless its stock moves resolve to exactly
   one shipping address (``account_avatax_stock/models/account_move.py:10-15``).

Safety
------
Every record is created through the ``FG05``-marked fixture helpers, swept
before each test and removed in a ``finally`` block. Pre-existing business
records — the AvaTax fiscal position, the chart of accounts, real customers —
are read-only. TC-TAX-008 and TC-TAX-009 are gated by ``require_sandbox``, so
they never reach a production Avalara account. TC-TAX-007 cannot use that gate
— it must stay runnable credential-free — so it gates each individual Compute
Taxes press on the same sandbox condition (:func:`_sandbox_ready`) and simply
does not press otherwise. No test in this module can reach a non-sandbox
Avalara account by any path.
"""
from __future__ import annotations

from adapters.base import OdooRPCError
from framework.fg_common import m2o_id
from framework.registry import test_case
from tests.fg05.common import (ADDRESS_INCOMPLETE, ADDRESS_MISSOULA_MT,
                               ADDRESS_PHOENIX_AZ, MODULE, WORKFLOW,
                               WORKFLOW_NAME, address_values, cleanup,
                               company_avatax_config, compute_taxes,
                               doc_totals, make_partner, make_product,
                               make_quotation,
                               require_avatax_fiscal_position,
                               require_sandbox, require_v19,
                               require_warehouse_shipfrom, server_error_message,
                               sweep_fg05, trace, warehouse_shipfrom_probe)

# First line of the refusal raised by
# mmg_account_avatax_enhancement/models/account_external_tax_mixin.py
# (_check_partner_shipping_address), followed by one
# "- <name> (ID: <id>) on <records>" line per incomplete partner.
ADDRESS_GUARD_HEADER = ("The following customer(s) need to have a zip, state "
                        "and country when using Avatax:")


# ----------------------------------------------------------------- helpers
def _sandbox_ready(config: dict) -> bool:
    """True only when pressing Compute Taxes would reach the Avalara SANDBOX.

    ``button_external_tax_calculation`` is NOT credential-free. On v19 it is
    ``account_external_tax/models/account_external_tax_mixin.py:175`` ->
    ``_get_and_set_external_taxes_on_eligible_records`` ->
    ``account_avatax/models/account_external_tax_mixin.py:308 _get_client``,
    which builds ``AvataxClient(environment=company.avalara_environment)``
    (line 320) from whatever credentials the company holds and then files a
    ``create_transaction``. Nothing on that path refuses a company pointed at
    ``production``, so a press on a production-configured database files a
    REAL tax document — which ``tests/fg05/common.py`` (module docstring,
    safety rule 1) says must never happen.

    TC-TAX-007 must stay runnable without credentials, so it cannot use
    ``require_sandbox`` (that BLOCKS the whole case). It applies the same
    condition here, per press, and simply does not press when it is not met.

    ``api_id`` / ``api_key`` read ``not set`` both when the credential is
    absent and when the runner user cannot read it (both fields carry
    ``groups='base.group_system'`` — ``account_avatax/models/res_company.py``).
    Unreadable is therefore treated as unsafe, never as "there is nothing to
    call".
    """
    return (config.get("environment") == "sandbox"
            and config.get("api_id") == "set"
            and config.get("api_key") == "set")


def _server_error_message(ctx, model: str, method: str, *args) -> str:
    """The FULL text of a server error, not the last line the adapter kept.

    ``adapters.base.OdooRPC.call`` keeps only ``splitlines()[-1]`` of a server
    error, so a multi-line ``ValidationError`` reaches the test with its first
    line already gone. TC-TAX-007's Expected Result is about that first line.

    The implementation is shared with TC-TAX-017, which needs the same
    untruncated text for its step-6 readability assertion — see
    :func:`tests.fg05.common.server_error_message` for how the call is
    re-issued and why repeating an ALREADY-FAILED call writes nothing.
    """
    return server_error_message(ctx, model, method, *args)


def _press_compute_taxes(ctx, model: str, record_id: int) -> str:
    """Press the workbook's 'Compute Taxes' button below the order lines.

    Goes through ``tests.fg05.common.compute_taxes`` — v19's
    ``button_external_tax_calculation`` (sale_external_tax/views/
    sale_order_views.xml, string="Compute Taxes"). Returns ``""`` when the
    server accepted the call, otherwise the full error message.
    """
    try:
        compute_taxes(ctx, model, record_id)
        return ""
    except OdooRPCError as exc:
        return _server_error_message(
            ctx, model, "button_external_tax_calculation",
            [record_id]) or str(exc)


def _save(ctx, model: str, record_id: int, values: dict) -> str:
    """Save one field change the way the form's Save button does.

    Returns ``""`` when the save went through, otherwise the full refusal —
    which is where the ``@api.constrains`` address guard surfaces on v19.
    """
    try:
        ctx.adapter.rpc.write(model, [record_id], values)
        return ""
    except OdooRPCError as exc:
        return _server_error_message(ctx, model, "write",
                                     [record_id], values) or str(exc)


def _make_quotation(ctx, partner_id: int, lines, *, fiscal_position_id: int,
                    shipping_partner_id: int) -> int:
    """One draft quotation. ``lines`` is ``[(product_id, qty, price), ...]``.

    Delegates to ``tests.fg05.common.make_quotation`` (which clears the
    Odoo-side line taxes, so the only tax on the document is the one Avalara
    returns) and adds the ship-to id to the log line, because every FG-05
    quotation expectation turns on the delivery address.
    """
    order_id = make_quotation(ctx, partner_id, lines,
                              fiscal_position_id=fiscal_position_id,
                              shipping_partner_id=shipping_partner_id)
    ctx.log(f"draft quotation #{order_id} for partner #{partner_id}, "
            f"ship-to #{shipping_partner_id}")
    return order_id


def _shipping_partner(ctx, order_id: int):
    """The quotation's Delivery Address, as an id."""
    data = ctx.adapter.rpc.read("sale.order", [order_id],
                                ["partner_shipping_id"])[0]
    return m2o_id(data["partner_shipping_id"])


def _address_parts(ctx, partner_id: int) -> dict:
    """zip / state / country of one partner — the three fields the guard reads."""
    return ctx.adapter.rpc.read("res.partner", [partner_id],
                                ["zip", "state_id", "country_id"])[0]


def _complete(parts: dict) -> bool:
    return bool(parts.get("zip") and parts.get("state_id")
                and parts.get("country_id"))


def _describe(parts: dict) -> str:
    return (f"zip={parts.get('zip')!r} state={parts.get('state_id')} "
            f"country={parts.get('country_id')}")


# ------------------------------------------------------------- TC-TAX-007
@test_case(
    id="TEST-FG05-TAX-007",
    name="An incomplete DELIVERY address is refused on a quotation",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P0",
    kind="API",
    order=504,
    description="mmg_account_avatax_enhancement._check_partner_shipping_address "
                "refuses a quotation whose DELIVERY contact has no zip/state/"
                "country, names that contact and not the invoicing partner, "
                "leaves the tax at zero, and lets the document through once "
                "the address is completed. Needs no Avalara credentials.",
    traceability=trace("TC-TAX-007"))
def test_tax_007(ctx):
    rpc = ctx.adapter.rpc
    created = {"sale.order": [], "product.product": [], "res.partner": []}
    with ctx.step("Precondition: Odoo 19 — NO Avalara credentials required, "
                  "the guard fires before anything is sent to Avalara"):
        # Deliberately require_v19 only, never require_sandbox: the client
        # guideline calls this the one FG-05 case that can be run while the
        # Avalara credentials are still being waited for. Gating it on the
        # sandbox would turn its whole value into a permanent BLOCKED.
        require_v19(ctx)
        # The GUARD is credential-free; the BUTTON is not. Read the company's
        # AvaTax configuration (credentials as set/not-set only) so each
        # Compute Taxes press below can be gated on the sandbox individually —
        # see _sandbox_ready(). Without this the case would file a real
        # transaction against a production Avalara account.
        config = company_avatax_config(ctx)
        sandbox_ready = _sandbox_ready(config)
        ctx.log(f"AvaTax config — environment={config['environment']!r} "
                f"api_id={config['api_id']} api_key={config['api_key']} "
                f"-> Compute Taxes "
                f"{'WILL' if sandbox_ready else 'will NOT'} be pressed by "
                f"TC-TAX-007 in this run. The address guard needs no "
                f"credentials, but button_external_tax_calculation reaches "
                f"AvataxClient(environment=<the company's>) and files a real "
                f"CreateTransaction on a non-sandbox account.")
        fp_id, fp = require_avatax_fiscal_position(ctx)
        ctx.log(f"AvaTax fiscal position #{fp_id} {fp['name']!r} — "
                f"sale.order._get_avatax_service_params sets "
                f"perform_address_validation from fiscal_position_id.is_avatax "
                f"(mmg_account_avatax_enhancement/models/sale_order.py); stock "
                f"v19 leaves it None and validates no quotation at all")
        sweep_fg05(ctx)
    try:
        with ctx.step("Test Data: customer with a COMPLETE invoicing address, "
                      "plus a delivery contact whose Zip Code, State and "
                      "Country are deliberately EMPTY"):
            customer_id = make_partner(ctx, "Tax Address Test 007",
                                       ADDRESS_PHOENIX_AZ,
                                       fiscal_position_id=fp_id)
            created["res.partner"].append(customer_id)
            delivery_id = make_partner(ctx, "Delivery Incomplete 007",
                                       ADDRESS_INCOMPLETE,
                                       parent_id=customer_id,
                                       partner_type="delivery")
            # child first: unlinked before its parent
            created["res.partner"].insert(0, delivery_id)
            product_id = make_product(ctx, "Quotation Art 007", 2000.00)
            created["product.product"].append(product_id)

        with ctx.step("Control (workbook 'If It Fails'): it is the DELIVERY "
                      "address that was blanked, not the INVOICING one"):
            invoicing_before = _address_parts(ctx, customer_id)
            ctx.check_true(
                "the invoicing partner has a complete zip / state / country",
                _complete(invoicing_before),
                actual_desc=f"invoicing partner #{customer_id}: "
                            f"{_describe(invoicing_before)}")
            shipping_before = _address_parts(ctx, delivery_id)
            ctx.check_true(
                "the DELIVERY contact has no zip, no state and no country",
                not shipping_before["zip"] and not shipping_before["state_id"]
                and not shipping_before["country_id"],
                actual_desc=f"delivery contact #{delivery_id}: "
                            f"{_describe(shipping_before)}")

        with ctx.step("Workbook steps 1-3 and 5-6: new quotation for the "
                      "customer on the AvaTax fiscal position, one product "
                      "line, saved with a complete ship-to so the document "
                      "itself exists"):
            order_id = _make_quotation(ctx, customer_id,
                                       [(product_id, 1, 2000.00)],
                                       fiscal_position_id=fp_id,
                                       shipping_partner_id=customer_id)
            created["sale.order"].append(order_id)
            opening = doc_totals(ctx, "sale.order", order_id)
            ctx.check("the quotation is saved and draft", "draft",
                      opening["state"])
            ctx.check("Untaxed Amount on the saved quotation", 2000.00,
                      opening["untaxed"])
            # Read (do not gate) the line-level shipFrom situation now, so the
            # two Compute Taxes presses below can each decide whether pressing
            # can produce anything meaningful. Steps 1-9 are unaffected: the
            # address guard under test is an @api.constrains that never
            # reaches Avalara, so a broken warehouse cannot change their
            # verdict. See module docstring adaptation 6.
            shipfrom = warehouse_shipfrom_probe(ctx, order_id)
            ctx.log(f"shipFrom probe — applicable={shipfrom['applicable']} "
                    f"ok={shipfrom['ok']} ({shipfrom['note']}); "
                    + (" | ".join(f"#{w['id']} {w['name']!r}: {w['verdict']}"
                                  for w in shipfrom["warehouses"])
                       or "no warehouse on any line"))

        with ctx.step("Workbook steps 4 and 6: set the Delivery Address to "
                      "the incomplete contact and save"):
            # The guard is @api.constrains('partner_id', 'fiscal_position_id',
            # 'partner_shipping_id'), so on v19 it fires on the very write
            # that sets partner_shipping_id — BEFORE the workbook's step 7.
            # Both timings are accepted: the save is attempted first, and only
            # if it goes through is Compute Taxes pressed below.
            refusal = _save(ctx, "sale.order", order_id,
                            {"partner_shipping_id": delivery_id})
            fired_on = ("the save (@api.constrains on partner_shipping_id)"
                        if refusal else "")

        with ctx.step("Workbook steps 7-8: click Compute Taxes and read the "
                      "error pop-up in full"):
            press_note = ""
            # Two independent reasons this fallback press may be skipped. It is
            # deliberately NOT a ctx.blocked() either way: reaching this branch
            # at all means the @api.constrains address guard did not fire on
            # the save, which is the serious failure the workbook names, and it
            # must stay a FAILED verdict rather than be masked by a
            # precondition block. Skipping the press costs nothing: on v19
            # _get_external_taxes never calls _check_address (it is only an
            # @api.constrains), so the press could not raise the address error
            # under test in any case.
            skip_reasons = []
            if not sandbox_ready:
                skip_reasons.append(
                    f"this company is not sandbox-configured (environment="
                    f"{config['environment']!r}, api_id={config['api_id']}, "
                    f"api_key={config['api_key']}) and the press would be a "
                    f"live Avalara CreateTransaction")
            if shipfrom["applicable"] and not shipfrom["ok"]:
                skip_reasons.append(
                    f"the warehouse this quotation ships from cannot produce a "
                    f"shipFrom address ({shipfrom['gap']}), so the press could "
                    f"only return Avalara's 'Unknown country name or code "
                    f"(FALSE)'")
            if not refusal:
                if skip_reasons:
                    press_note = (
                        "; Compute Taxes was NOT pressed — "
                        + "; and ".join(skip_reasons)
                        + ". It could not have produced the address error "
                          "anyway: on v19 _check_address is only an "
                          "@api.constrains and _get_external_taxes never calls "
                          "it (account_avatax/models/"
                          "account_external_tax_mixin.py), so a save that went "
                          "through IS the guard failing to fire")
                    ctx.log(press_note.lstrip("; "))
                else:
                    refusal = _press_compute_taxes(ctx, "sale.order", order_id)
                    fired_on = ("Compute Taxes "
                                "(button_external_tax_calculation)"
                                if refusal else "")
            ctx.log(f"address guard fired on: "
                    f"{fired_on or 'NOTHING — nothing was refused'}")
            ctx.log("note: a child contact's display_name embeds its parent's "
                    "name, so the invoicing partner's NAME can legitimately "
                    "appear inside the delivery contact's label. Identity is "
                    "therefore asserted on the '(ID: <n>)' token the guard "
                    "prints, which is unambiguous.")
            ctx.check_true(
                "Step 8: the system refuses to continue with the AvaTax "
                "ship-to address error",
                ADDRESS_GUARD_HEADER in refusal,
                actual_desc=refusal or ("no error was raised — the quotation "
                                        "was accepted with an incomplete "
                                        "delivery address (the serious "
                                        "failure the workbook names)"
                                        + press_note))
            names_delivery = f"(ID: {delivery_id})" in refusal
            names_invoicing = f"(ID: {customer_id})" in refusal
            ctx.check_true(
                "Step 8: the error names the INCOMPLETE DELIVERY contact and "
                "not the invoicing partner",
                names_delivery and not names_invoicing,
                actual_desc=f"delivery contact #{delivery_id} named: "
                            f"{names_delivery}; invoicing partner "
                            f"#{customer_id} named: {names_invoicing}; full "
                            f"message: {refusal}")
            after_refusal = doc_totals(ctx, "sale.order", order_id)
            ctx.check("Step 8: no tax was calculated", 0.00,
                      after_refusal["tax"])
            ctx.check("Step 8: the quotation is untouched and still draft",
                      "draft", after_refusal["state"])
            ctx.check("Step 8: the untaxed amount is untouched too", 2000.00,
                      after_refusal["untaxed"])

        with ctx.step("Workbook step 9: open the delivery contact, fill in "
                      "Zip Code, State and Country, and save"):
            rpc.write("res.partner", [delivery_id],
                      address_values(rpc, ADDRESS_PHOENIX_AZ))
            shipping_after = _address_parts(ctx, delivery_id)
            ctx.check_true(
                "the delivery contact now has zip, state and country",
                _complete(shipping_after),
                actual_desc=f"delivery contact #{delivery_id}: "
                            f"{_describe(shipping_after)}")
            invoicing_after = _address_parts(ctx, customer_id)
            ctx.check_true(
                "control: the invoicing partner was never the record under "
                "test — its address is unchanged and still complete",
                _complete(invoicing_after)
                and invoicing_after["zip"] == invoicing_before["zip"]
                and invoicing_after["state_id"] == invoicing_before["state_id"]
                and (invoicing_after["country_id"]
                     == invoicing_before["country_id"]),
                actual_desc=f"before: {_describe(invoicing_before)} / after: "
                            f"{_describe(invoicing_after)}")
            save_again = _save(ctx, "sale.order", order_id,
                               {"partner_shipping_id": delivery_id})
            ctx.check_true(
                "the completed delivery contact now saves on the quotation — "
                "the address guard no longer fires",
                ADDRESS_GUARD_HEADER not in save_again,
                actual_desc=save_again or "saved with no error")
            ctx.check("the quotation's Delivery Address is the completed "
                      "contact", delivery_id, _shipping_partner(ctx, order_id))

        with ctx.step("Workbook step 10: click Compute Taxes again — the "
                      "address guard must let it through. The workbook's own "
                      "Expected Result branches here on whether sandbox "
                      "credentials exist, and so does this step"):
            if sandbox_ready:
                # Before pressing: the workbook's step-10 expectation is
                # "Compute Taxes now succeeds", and on this database it cannot
                # — not because the address guard failed, but because Odoo
                # builds an empty line-level shipFrom from a warehouse with no
                # address and Avalara refuses the whole document. That is a
                # precondition of the press, not a verdict on the guard, so it
                # BLOCKS with the warehouse named rather than FAILING on
                # Avalara's cryptic text. Steps 1-9 above have already been
                # asserted in full and stay in the evidence.
                require_warehouse_shipfrom(
                    ctx, order_id,
                    "workbook step 10 — pressing Compute Taxes on the "
                    "quotation once the delivery contact's address is "
                    "complete, and reading the recomputed totals")
                # Sandbox branch of the workbook: "Compute Taxes now
                # succeeds". Anything else is a failure, INCLUDING a
                # non-address error — e.g. the UserError "The Avalara Tax Code
                # is required for <product> (#<id>)" that
                # account_avatax/models/account_external_tax_mixin.py:90-95
                # raises for a product with no avatax_category_id. Asserting
                # only "not the address error" would report PASS while
                # Compute Taxes is in fact broken on this document.
                outcome = _press_compute_taxes(ctx, "sale.order", order_id)
                ctx.check_true(
                    "Step 10: with the address complete, Compute Taxes now "
                    "succeeds",
                    not outcome,
                    actual_desc=outcome or "Compute Taxes returned without an "
                                           "error")
                computed = doc_totals(ctx, "sale.order", order_id)
                ctx.log(f"Compute Taxes succeeded: untaxed="
                        f"{computed['untaxed']:.2f} tax={computed['tax']:.2f} "
                        f"total={computed['total']:.2f}")
                # No separate "not the address error" check here: the success
                # assertion above already subsumes it (it only passes when
                # outcome is empty), and an assertion that cannot fail is
                # noise in the evidence rather than coverage.
                ctx.check("Step 10: the Untaxed Amount is unchanged by "
                          "Compute Taxes", 2000.00, computed["untaxed"])
                ctx.check("Step 10: Total equals Untaxed Amount plus Taxes",
                          round(computed["untaxed"] + computed["tax"], 2),
                          computed["total"])
                ctx.check("Step 10: the quotation is still a draft quotation",
                          "draft", computed["state"])
            else:
                # No-credentials branch of the workbook. The button is NOT
                # pressed: see _sandbox_ready() — an unreadable credential
                # reads the same as an absent one, so a press here could be a
                # live production call. The workbook counts this branch a PASS
                # "because the address guard let it through", and that is
                # exactly what step 9's re-save proves, credential-free: the
                # same @api.constrains that refused the document at step 8 now
                # accepts the completed delivery contact.
                ctx.log("no-credentials branch of the workbook step 10: "
                        "Compute Taxes was NOT pressed (environment="
                        f"{config['environment']!r}, api_id="
                        f"{config['api_id']}, api_key={config['api_key']}). "
                        "The workbook accepts a CONNECTION error here as a "
                        "PASS because the address guard let the document "
                        "through; the guard's release is asserted below from "
                        "step 9's save instead of from a live Avalara call. "
                        "TC-TAX-008 proves the call itself, under "
                        "require_sandbox.")
                ctx.check_true(
                    "Step 10: with the address complete, the document gets "
                    "PAST the address guard — it is no longer refused",
                    ADDRESS_GUARD_HEADER not in save_again,
                    actual_desc=save_again or "the completed delivery contact "
                                              "saved on the quotation with no "
                                              "address error")
    finally:
        with ctx.step("Cleanup: remove FG05 fixtures"):
            cleanup(ctx, created)


# ------------------------------------------------------------- TC-TAX-008
@test_case(
    id="TEST-FG05-TAX-008",
    name="Tax can be previewed on a quotation before it goes to the customer",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P0",
    kind="API",
    order=505,
    description="Compute Taxes on a 2,000.00 quotation with a complete US "
                "delivery address returns a non-zero tax, a Total that is "
                "arithmetically Untaxed + Taxes, a populated Avalara Code, "
                "and no error banner.",
    traceability=trace("TC-TAX-008"))
def test_tax_008(ctx):
    created = {"sale.order": [], "product.product": [], "res.partner": []}
    with ctx.step("Precondition: Odoo 19 with a usable Avalara SANDBOX"):
        require_sandbox(ctx, "computing tax on a quotation before it is sent "
                             "to the customer (TC-TAX-008 step 5)")
        fp_id, fp = require_avatax_fiscal_position(ctx)
        ctx.log(f"AvaTax fiscal position #{fp_id} {fp['name']!r}")
        sweep_fg05(ctx)
    try:
        with ctx.step("Test Data: customer with the AvaTax fiscal position, a "
                      "complete US delivery contact, and one 2,000.00 art "
                      "item"):
            customer_id = make_partner(ctx, "Quotation Customer 008",
                                       ADDRESS_PHOENIX_AZ,
                                       fiscal_position_id=fp_id)
            created["res.partner"].append(customer_id)
            delivery_id = make_partner(ctx, "Delivery Complete 008",
                                       ADDRESS_PHOENIX_AZ,
                                       parent_id=customer_id,
                                       partner_type="delivery")
            created["res.partner"].insert(0, delivery_id)
            product_id = make_product(ctx, "Quotation Art 008", 2000.00)
            created["product.product"].append(product_id)

        with ctx.step("Workbook step 2: confirm the Delivery Address is "
                      "complete and the Fiscal Position is the AvaTax one"):
            shipping = _address_parts(ctx, delivery_id)
            ctx.check_true("the delivery contact has a complete US address",
                           _complete(shipping),
                           actual_desc=f"delivery contact #{delivery_id}: "
                                       f"{_describe(shipping)}")

        with ctx.step("Workbook steps 1, 3 and 4: new quotation, one line "
                      "(product, quantity 1, price 2,000.00), save"):
            order_id = _make_quotation(ctx, customer_id,
                                       [(product_id, 1, 2000.00)],
                                       fiscal_position_id=fp_id,
                                       shipping_partner_id=delivery_id)
            created["sale.order"].append(order_id)
            ctx.check("the quotation's Delivery Address is the complete "
                      "contact", delivery_id, _shipping_partner(ctx, order_id))
            before = doc_totals(ctx, "sale.order", order_id)
            ctx.check("Untaxed Amount before Compute Taxes", 2000.00,
                      before["untaxed"])
            ctx.check("no tax on the quotation before Compute Taxes", 0.00,
                      before["tax"])

        with ctx.step("Precondition of workbook step 5: the warehouse this "
                      "quotation ships from must be able to produce a "
                      "shipFrom address for Avalara"):
            require_warehouse_shipfrom(
                ctx, order_id,
                "workbook step 5 — Compute Taxes on the quotation, and the "
                "non-zero Taxes figure, Total and Avalara Code steps 6-7 read "
                "from it")

        with ctx.step("Workbook step 5: click Compute Taxes below the order "
                      "lines"):
            error = _press_compute_taxes(ctx, "sale.order", order_id)
            ctx.check_true(
                "No error banner appears",
                not error,
                actual_desc=error or "Compute Taxes returned without an error")

        with ctx.step("Workbook step 6: read the totals block — Untaxed "
                      "Amount, Taxes, Total"):
            totals = doc_totals(ctx, "sale.order", order_id)
            ctx.log(f"totals block — untaxed={totals['untaxed']:.2f} "
                    f"taxes={totals['tax']:.2f} total={totals['total']:.2f}")
            ctx.check("Untaxed Amount", 2000.00, totals["untaxed"])
            ctx.check_true(
                "Taxes shows a non-zero figure appropriate to the delivery "
                "address",
                totals["tax"] > 0.0,
                actual_desc=f"Taxes = {totals['tax']:.2f} on a 2,000.00 "
                            f"delivery to Phoenix AZ 85004")
            ctx.check("Total equals Untaxed Amount plus Taxes",
                      round(totals["untaxed"] + totals["tax"], 2),
                      totals["total"])

        with ctx.step("Workbook step 7: open the Other Info tab and read "
                      "Avalara Code"):
            ctx.check_true(
                "Avalara Code on Other Info is filled in",
                bool(totals["avalara_code"].strip()),
                actual_desc=f"avatax_unique_code = "
                            f"{totals['avalara_code']!r}")
            ctx.log("note: avatax_unique_code is computed by Odoo as "
                    "'<model description> <id>' (account_avatax/models/"
                    "account_avatax_unique_code.py) and sent to Avalara as "
                    "the transaction code — the expectation is that the field "
                    "is populated, not that Avalara wrote it.")
            ctx.check("the quotation is still a draft quotation", "draft",
                      totals["state"])
    finally:
        with ctx.step("Cleanup: remove FG05 fixtures"):
            cleanup(ctx, created)


# ------------------------------------------------------------- TC-TAX-009
@test_case(
    id="TEST-FG05-TAX-009",
    name="Changing the delivery address changes the tax",
    workflow=WORKFLOW,
    workflow_name=WORKFLOW_NAME,
    module=MODULE,
    priority="P0",
    kind="API",
    order=506,
    description="The same quotation taxed against Phoenix AZ and then "
                "Missoula MT returns two different Taxes figures, the Montana "
                "one materially lower (no state sales tax), with the Total "
                "recalculated to Untaxed + the new Taxes.",
    traceability=trace("TC-TAX-009"))
def test_tax_009(ctx):
    created = {"sale.order": [], "product.product": [], "res.partner": []}
    with ctx.step("Precondition: Odoo 19 with a usable Avalara SANDBOX"):
        require_sandbox(ctx, "comparing the tax Avalara returns for an "
                             "Arizona delivery against a Montana one "
                             "(TC-TAX-009 steps 2 and 5)")
        fp_id, fp = require_avatax_fiscal_position(ctx)
        ctx.log(f"AvaTax fiscal position #{fp_id} {fp['name']!r}")
        sweep_fg05(ctx)
    try:
        with ctx.step("Test Data: one customer with TWO complete US delivery "
                      "contacts — A = Phoenix AZ 85004, B = Missoula MT "
                      "59802"):
            customer_id = make_partner(ctx, "Quotation Customer 009",
                                       ADDRESS_PHOENIX_AZ,
                                       fiscal_position_id=fp_id)
            created["res.partner"].append(customer_id)
            delivery_a = make_partner(ctx, "Delivery A Phoenix AZ 009",
                                      ADDRESS_PHOENIX_AZ,
                                      parent_id=customer_id,
                                      partner_type="delivery")
            created["res.partner"].insert(0, delivery_a)
            delivery_b = make_partner(ctx, "Delivery B Missoula MT 009",
                                      ADDRESS_MISSOULA_MT,
                                      parent_id=customer_id,
                                      partner_type="delivery")
            created["res.partner"].insert(0, delivery_b)
            product_id = make_product(ctx, "Quotation Art 009", 2000.00)
            created["product.product"].append(product_id)
            for label, partner_id in (("A (Phoenix AZ)", delivery_a),
                                      ("B (Missoula MT)", delivery_b)):
                parts = _address_parts(ctx, partner_id)
                ctx.check_true(f"delivery address {label} is complete",
                               _complete(parts),
                               actual_desc=f"contact #{partner_id}: "
                                           f"{_describe(parts)}")

        with ctx.step("Documented adaptation of workbook step 1: this case "
                      "builds its own quotation (same one line, 2,000.00 x 1) "
                      "instead of reusing TC-TAX-008's — the platform forbids "
                      "depending on another test's fixtures"):
            order_id = _make_quotation(ctx, customer_id,
                                       [(product_id, 1, 2000.00)],
                                       fiscal_position_id=fp_id,
                                       shipping_partner_id=delivery_a)
            created["sale.order"].append(order_id)

        with ctx.step("Precondition of workbook steps 2 and 5: the warehouse "
                      "this quotation ships from must be able to produce a "
                      "shipFrom address for Avalara"):
            require_warehouse_shipfrom(
                ctx, order_id,
                "workbook steps 2 and 5 — Compute Taxes against the Arizona "
                "delivery and then against the Montana one, so the two "
                "figures can be compared")

        with ctx.step("Workbook step 2: Delivery Address = A (Phoenix AZ), "
                      "save, then click Compute Taxes"):
            ctx.check("Delivery Address is contact A", delivery_a,
                      _shipping_partner(ctx, order_id))
            error_a = _press_compute_taxes(ctx, "sale.order", order_id)
            ctx.check_true(
                "Compute Taxes on the Arizona delivery raised no error",
                not error_a,
                actual_desc=error_a or "Compute Taxes returned without an "
                                       "error")

        with ctx.step("Workbook step 3: WRITE DOWN the Taxes figure and the "
                      "Total from the totals block"):
            arizona = doc_totals(ctx, "sale.order", order_id)
            ctx.log(f"ARIZONA — untaxed={arizona['untaxed']:.2f} "
                    f"taxes={arizona['tax']:.2f} "
                    f"total={arizona['total']:.2f}")
            ctx.check("Arizona Untaxed Amount", 2000.00, arizona["untaxed"])
            ctx.check_true(
                "the Arizona quotation carries a non-zero tax to compare "
                "against",
                arizona["tax"] > 0.0,
                actual_desc=f"Arizona Taxes = {arizona['tax']:.2f}")

        with ctx.step("Workbook step 4: change the Delivery Address to B "
                      "(Missoula MT) and save"):
            refusal = _save(ctx, "sale.order", order_id,
                            {"partner_shipping_id": delivery_b})
            ctx.check_true(
                "the Montana delivery contact saves on the quotation",
                not refusal,
                actual_desc=refusal or "saved with no error")
            ctx.check("Delivery Address is now contact B", delivery_b,
                      _shipping_partner(ctx, order_id))
            on_save = doc_totals(ctx, "sale.order", order_id)
            ctx.log(f"workbook 'If It Fails' observation — Taxes after the "
                    f"address change but BEFORE pressing Compute Taxes again: "
                    f"{on_save['tax']:.2f} (Arizona figure was "
                    f"{arizona['tax']:.2f}). If the figure only moves after a "
                    f"manual re-press, the workbook still counts the case as "
                    f"a pass but the sales team must press the button after "
                    f"every address change.")

        with ctx.step("Workbook step 5: click Compute Taxes again"):
            error_b = _press_compute_taxes(ctx, "sale.order", order_id)
            ctx.check_true(
                "Compute Taxes on the Montana delivery raised no error",
                not error_b,
                actual_desc=error_b or "Compute Taxes returned without an "
                                       "error")

        with ctx.step("Workbook steps 6-7: read the new Taxes figure and "
                      "Total and compare against step 3"):
            montana = doc_totals(ctx, "sale.order", order_id)
            ctx.log(f"MONTANA — untaxed={montana['untaxed']:.2f} "
                    f"taxes={montana['tax']:.2f} "
                    f"total={montana['total']:.2f}")
            ctx.check_true(
                "the Taxes figure CHANGED between step 3 and step 6 — it did "
                "not stay the same",
                montana["tax"] != arizona["tax"],
                actual_desc=f"Arizona Taxes {arizona['tax']:.2f} -> Montana "
                            f"Taxes {montana['tax']:.2f}")
            ctx.check_true(
                "the Montana figure is materially LOWER than the Arizona "
                "figure (Montana charges no state sales tax)",
                (montana["tax"] < arizona["tax"]
                 and montana["tax"] <= arizona["tax"] / 2.0),
                actual_desc=f"Arizona {arizona['tax']:.2f} vs Montana "
                            f"{montana['tax']:.2f}; 'materially lower' is "
                            f"read as at most half the Arizona figure "
                            f"(<= {arizona['tax'] / 2.0:.2f}) — Arizona's "
                            f"state rate alone is 5.6 %")
            ctx.check("Untaxed Amount is unchanged by the address change",
                      2000.00, montana["untaxed"])
            ctx.check("Total equals Untaxed Amount plus the NEW Taxes figure",
                      round(montana["untaxed"] + montana["tax"], 2),
                      montana["total"])
            ctx.check_true(
                "the Total was recalculated too — it is not still the Arizona "
                "total",
                montana["total"] != arizona["total"],
                actual_desc=f"Arizona Total {arizona['total']:.2f} -> Montana "
                            f"Total {montana['total']:.2f}")
            ctx.check("the quotation now carries delivery address B",
                      delivery_b, _shipping_partner(ctx, order_id))
    finally:
        with ctx.step("Cleanup: remove FG05 fixtures"):
            cleanup(ctx, created)
