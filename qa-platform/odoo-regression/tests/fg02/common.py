"""Shared fixtures and helpers for the FG-02 suite
(Certificates of Authenticity & Label Printing).

Offline scope of this suite (documented adaptation, not assertion-weakening):
py3o/LibreOffice document *rendering* cannot be verified from the QA host —
the py3o engine renders server-side and the labels additionally need the
LibreOffice binary for the ODT→DOCX conversion. Every rendering-dependent TC
therefore asserts all offline-checkable preconditions (ir.actions.report
records, report_type / py3o_filetype / py3o_template_fallback paths, wizard
action routing and slot helpers, data fields feeding the report on marker
fixtures) and then calls ctx.blocked() for the visual half.

The mmg_report path-chooser methods
(product.template._get_product_template_certificate_report_path and
py3o.report._get_template_fallback) are underscore-private and thus not
callable over the external RPC API — their direct assertions are part of the
blocked manual/visual step; the chooser *inputs* (x_date / description_sale
state on the fixture variant) are asserted here instead.

Four invariants this module enforces for the whole suite
-------------------------------------------------------

1. **Teardown never replaces a verdict.** Every test here ends in a
   ctx.blocked() verdict. A cleanup that raises while BlockedTest is
   propagating out of the try-block *replaces* that exception, and
   backend/runner.py then classifies the execution as ERROR /
   AUTOMATION_ERROR instead of BLOCKED (it maps BlockedTest → BLOCKED,
   AssertionFailed → FAILED and anything else → ERROR). sweep_fg02()
   therefore never raises — it returns the problems it hit — and
   cleanup_fg02() reports them through ctx.log only. Orders and invoices are
   cancelled/reset before unlink, and every phase falls back
   record-by-record so one undeletable row cannot strand the rest.

2. **Every call that reaches report_action carries the layout guard.**
   ir.actions.report.report_action() diverts to the "Configure your document
   layout" wizard instead of returning the report action whenever the caller
   is an admin, config is True and res.company.external_report_layout_id is
   unset — the state of this neutralized clone. Core gates that diversion on
   the context flag 'discard_logo_check', so every rpc.call that reaches
   report_action (the two wizard action methods and the four print entry
   points) passes REPORT_CTX. This is an environment guard: it makes the
   wizard return the action the workbook describes; it does not change what
   is asserted about that action.

3. **Per-execution fixture namespace.** sweep_fg02() mints a fresh token and
   fx() stamps it onto every fixture identifier *and* onto every free-text
   value a test matches by: product names, SKUs (default_code), x_artist
   values, x.medium names, the provenance text and partner names. Why it is
   needed even though no assertion in this suite counts records:
   * `mmg_multichannel_shopify.product.product.check_unique_sku` is a real
     constraint over *active* products — a leftover FG02 variant that a
     previous run could only archive is reactivated by nothing, but any run
     that reuses its SKU while it is still active fails at create;
   * ensure_medium() resolves x.medium **by name**, so without the token it
     silently reuses (and mutates the meaning of) a previous run's record;
   * the slot assertions compare the wizard's output against fixture values
     (artist, medium name, description line). With the token, such an
     assertion can only ever be satisfied by a record *this* execution
     created — the FG-04 determinism rule.
   Structural workbook literals stay literal: x_date ('1948' / '1950'), the
   10.5 x 8.0 dimensions and the prices. The certificate chooser branches on
   x_date being empty or set, the description formula renders the dimensions
   with %g, and the workbook quotes the resulting line verbatim
   ('1950 * <medium> * 10.5 x 8') — a token inside those values would
   misrepresent the field's content instead of protecting anything.

4. **Fixture products carry an explicit sales configuration.** Every fixture
   product is created with invoice_policy='order' (Ordered quantities /
   Prepaid). Without it the fixtures inherit this clone's ir.default
   ('delivery'), and because `mmg_sale_auto_create_invoice` calls
   `_create_invoices()` from `sale.order.action_confirm()` whenever
   res.company.auto_create_invoice_after_confirming_so is set, confirming a
   fixture order raised sale's nothing-to-invoice UserError ("…modify
   invoicing policy from 'delivered quantities' to 'ordered quantities'") —
   observed as TEST-FG02-LBL-007 / AUTOMATION_ERROR in RUN-5C016D16. The
   fixture's invoicing policy is not what any FG-02 TC is about, so it is
   pinned instead of being left to the environment. TC-LBL-007 additionally
   snapshots and clears the company auto-invoice flag for the duration of
   the confirmation step (suspend_auto_invoice/restore_auto_invoice), so the
   order confirmation the TC needs does not drag the clone's
   chart-of-accounts state into the test path.
   Label fixtures also carry a real non-zero price (list_price *and*
   lst_price): `novobi-omni-addons/multichannel_manage_price` redefines
   product.product.lst_price to read the stored `variant_price` field
   instead of list_price + price_extra, so a fixture created with list_price
   alone renders as '$0.0' on the label — observed as TEST-FG02-LBL-008 /
   ASSERTION in RUN-5C016D16. The workbook's own precondition for TC-LBL-008
   asks for "35 product.product records with distinct default_code, name,
   lst_price, …", so the price is fixture data, not a weakened assertion.
"""
from __future__ import annotations

import base64
import uuid

from framework.fg_common import (form_arch, http_session, m2o_id,  # noqa: F401 — re-exported
                                 make_trace, reconcile)
from framework.qa_fixtures import sweep_model, sweep_products

FEATURE = "FG-02 Certificates of Authenticity & Label Printing"
MARK = "FG02"

# Invariant 2 — see the module docstring. Passed as the `context` kwarg, which
# call_kw applies with with_context(), so the flag reaches report_action
# through env.context on the wizard/product recordset.
REPORT_CTX = {"discard_logo_check": True}

# Invariant 4 — pinned sales configuration for every fixture product.
INVOICE_POLICY = "order"

# The shared *why* behind every blocked half of this suite. Call sites append
# the specific verification that is left to a human, via render_blocked().
RENDER_BLOCKED = (
    "py3o/LibreOffice rendering is not verifiable from the QA host: the "
    "render and template-chooser entry points (ir.actions.report."
    "_render_py3o, py3o.report._get_template_fallback, product.template."
    "_get_product_template_certificate_report_path) are underscore-private "
    "and not callable over RPC, and the LibreOffice runtime the DOCX labels "
    "need for the ODT→DOCX conversion is not installed on this host. Manual "
    "verification required")

# 1x1 red PNG (valid base64 payload for image_1920)
PNG_1PX = base64.b64encode(base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQ"
    "DwAEhQGAhKmMIQAAAABJRU5ErkJggg==")).decode()

trace = make_trace(FEATURE)

LABEL_WIZARD = "access.avery.label.wizard"

# mmg_sale_auto_create_invoice's company switch (TC-LBL-007, invariant 4)
AUTO_INVOICE_FLAG = "auto_create_invoice_after_confirming_so"

CERT_VARIANT_XMLID = "mmg_report.product_certificate"
CERT_TEMPLATE_XMLID = "mmg_report.product_template_certificate"

# the four template-level ODTs of the conditional-layout feature
FULL_TEMPLATE_PATH = "report/template_certificate.odt"
NO_DATE_PATH = "report/template_certificate_no_date.odt"
NO_PROVENANCE_PATH = "report/template_certificate_no_provenance.odt"
NO_DATE_NO_PROVENANCE_PATH = "report/template_certificate_no_date_no_provenance.odt"


# ------------------------------------------------- fixture namespace (inv. 3)
_TOKEN = "init"


def fixture_token() -> str:
    return _TOKEN


def fx(name: str) -> str:
    """Namespace a fixture identifier for this execution:
    'FG02 Watercolor' → 'FG02 Watercolor [a1b2c3]'. The MARK prefix is
    preserved, so every marker-prefix sweep and search keeps working."""
    return f"{name} [{_TOKEN}]"


def _new_token() -> str:
    global _TOKEN
    _TOKEN = uuid.uuid4().hex[:6]
    return _TOKEN


# --------------------------------------------------------------- verdicts
def render_blocked(what: str) -> str:
    """Precise, actionable BLOCKED reason for one rendering-dependent half:
    the shared limitation plus the exact verification a human must perform."""
    return f"{RENDER_BLOCKED}: {what}."


def libreoffice_blocked(report_data: dict) -> str:
    """TC-SMK-011's host-tooling half — a BLOCKED reason that names the
    missing runtime, the observed engine state and the fix.

    Why BLOCKED rather than FAILED: "LibreOffice installed on the host
    (report_py3o external_dependencies: deb libreoffice)" is a stated
    *precondition* of TC-SMK-011, and report_py3o's _compute_lo_bin_path only
    reports whether the host has the binary on PATH — it is not MMG product
    behaviour. The platform's own Odoo log carries report_py3o's
    _register_hook warning at every restart, so the precondition is known
    unmet on this host. The workbook expectation (lo_bin_path non-empty, a
    valid DOCX that opens) is untouched and still has to be met on the v19
    host; it simply cannot be exercised from here.
    """
    return (
        "LibreOffice runtime missing on the Odoo host — report_py3o's "
        "_compute_lo_bin_path resolves no 'libreoffice' binary on PATH and "
        "the ir.config_parameter 'py3o.conversion_command' is unset, so every "
        "non-native (docx) py3o report reports is_py3o_report_not_available "
        "and this server logs report_py3o's \"The libreoffice runtime is "
        "required to genereate the py3o report ...\" warning at each restart. "
        "Observed on mmg_stock.avery_label_30_report: lo_bin_path="
        f"{report_data.get('lo_bin_path')!r}, is_py3o_report_not_available="
        f"{report_data.get('is_py3o_report_not_available')!r}. TC-SMK-011 "
        "steps 1-2 (the odoo-bin -u boot-log scan), 4 (lo_bin_path non-empty) "
        "and 6-7 (the real ODT→DOCX _render_py3o run and the b'PK' DOCX "
        "check) need LibreOffice installed on the Odoo host, or "
        "py3o.conversion_command pointed at the binary; then re-run this "
        "test.")


# ------------------------------------------------------- sweep / teardown
def _unlink_one_by_one(rpc, model, ids):
    """Unlink `ids` in one call, falling back record-by-record so a single
    undeletable row cannot strand the rest (invariant 1). Raises a summary
    RuntimeError for whatever survived — the caller phase turns that into a
    logged 'cleanup incomplete' line, never into a verdict."""
    try:
        rpc.unlink(model, ids)
        return
    except Exception:  # noqa: BLE001 — fall back to one call per record
        pass
    survivors = []
    for rid in ids:
        try:
            rpc.unlink(model, [rid])
        except Exception as exc:  # noqa: BLE001 — invariant 1
            survivors.append(f"{rid} ({type(exc).__name__})")
    if survivors:
        raise RuntimeError(f"{model} not removed: {', '.join(survivors)}")


def _sweep_invoices(rpc):
    """Marker-scoped customer invoices first: the company's
    auto-invoice-on-confirm option (mmg_sale_auto_create_invoice) can create
    a draft invoice for a fixture order, and that invoice references the
    fixture products and partners. Reset to draft before unlink."""
    ids = rpc.search("account.move",
                     [("partner_id.name", "like", f"{MARK} %"),
                      ("move_type", "in", ["out_invoice", "out_refund"])])
    if not ids:
        return
    try:
        rpc.call("account.move", "button_draft", ids)
    except Exception:  # noqa: BLE001 — already draft
        pass
    _unlink_one_by_one(rpc, "account.move", ids)


def _sweep_sale_orders(rpc):
    """Marker-scoped sale orders — they reference the fixture products and
    partners. Cancel with the confirmation-wizard guard, then unlink (a
    confirmed order refuses unlink until it is cancelled)."""
    so_ids = rpc.search("sale.order",
                        [("partner_id.name", "like", f"{MARK} %")])
    if not so_ids:
        return
    try:
        rpc.call("sale.order", "action_cancel", so_ids,
                 context={"disable_cancel_warning": True})
    except Exception:  # noqa: BLE001 — a draft order needs no cancel
        pass
    _unlink_one_by_one(rpc, "sale.order", so_ids)


def sweep_fg02(rpc) -> list[str]:
    """Open a fresh fixture namespace, then remove marker-scoped leftovers.

    Best-effort by contract: this function NEVER raises (invariant 1). It
    returns a list of "<phase>: <error>" strings for whatever it could not
    clean, so the caller can log them. Deletion legitimately fails on a
    production clone — a product referenced by stock moves or channel
    listings is archived by sweep_products instead of removed — and because
    the new namespace (invariant 3) is unique, anything that survives can
    never collide with this execution's fixtures or assertions.
    """
    _new_token()
    problems: list[str] = []
    phases = (
        ("invoices", lambda: _sweep_invoices(rpc)),
        ("sale orders", lambda: _sweep_sale_orders(rpc)),
        ("products", lambda: sweep_products(rpc, MARK)),
        ("x.medium", lambda: sweep_model(rpc, "x.medium",
                                         [("x_name", "like", f"{MARK}%")])),
        ("res.partner", lambda: sweep_model(rpc, "res.partner",
                                            [("name", "like", f"{MARK} %"),
                                             ("user_ids", "=", False)])),
    )
    for label, phase in phases:
        try:
            phase()
        except Exception as exc:  # noqa: BLE001 — invariant 1
            problems.append(f"{label}: {type(exc).__name__}: {exc}")
    return problems


def prepare_fg02(ctx, rpc):
    """Start-of-test step: open this execution's fixture namespace and sweep
    previous leftovers. Leftovers that could not be removed are logged, not
    raised — the marker plus the fresh token keep them out of every
    assertion."""
    with ctx.step("Open the fixture namespace and sweep previous FG-02 "
                  "fixtures"):
        for problem in sweep_fg02(rpc):
            ctx.log(f"sweep incomplete — {problem}")
        ctx.log(f"fixture namespace for this execution: [{fixture_token()}]")


def unlink_wizards(rpc, wizard_ids):
    """Remove the access.avery.label.wizard rows *this execution* created.

    Only these ids: the transient table is shared with every other session on
    the clone, so a blanket sweep of the model is out of bounds.
    """
    ids = [wid for wid in dict.fromkeys(wizard_ids or ()) if wid]
    if ids:
        _unlink_one_by_one(rpc, LABEL_WIZARD, ids)


def cleanup_fg02(ctx, rpc, wizard_ids=(), restore=()):
    """Teardown that can never replace the test's verdict (invariant 1).

    Called from every test's `finally:`. `restore` holds zero or more
    no-argument callables (config restores) run before the sweep; each phase
    reports through ctx.log, and the outer guard covers the step-recording
    machinery itself, so nothing can escape into a propagating BlockedTest /
    AssertionFailed and turn a documented verdict into ERROR /
    AUTOMATION_ERROR.
    """
    try:
        with ctx.step("Restore configuration and cleanup fixtures"):
            for restore_one in restore or ():
                try:
                    restore_one()
                except Exception as exc:  # noqa: BLE001 — invariant 1
                    ctx.log(f"cleanup incomplete — config restore: "
                            f"{type(exc).__name__}: {exc}")
            try:
                unlink_wizards(rpc, wizard_ids)
            except Exception as exc:  # noqa: BLE001 — invariant 1
                ctx.log(f"cleanup incomplete — label wizards: "
                        f"{type(exc).__name__}: {exc}")
            for problem in sweep_fg02(rpc):
                ctx.log(f"cleanup incomplete — {problem}")
    except Exception:  # noqa: BLE001 — not even the recorder may mask a verdict
        pass


# ------------------------------------------------------- company config
def acting_company(rpc) -> int:
    return m2o_id(rpc.read("res.users", [rpc.uid], ["company_id"])[0]
                  ["company_id"])


def suspend_auto_invoice(ctx, rpc):
    """Snapshot res.company.<AUTO_INVOICE_FLAG> and clear it (invariant 4).

    Returns a no-argument restore callable for cleanup_fg02(restore=...);
    the callable is a no-op when the field is absent (module not installed)
    or the flag was already off.

    Why a test may switch this off: mmg_sale_auto_create_invoice calls
    sale.order._create_invoices() from action_confirm(). TC-LBL-007 needs
    confirmed orders; the invoice that option creates is not part of any
    FG-02 expected result, but it drags the clone's chart-of-accounts state
    (income accounts, journals, Avatax fiscal positions) into the test path
    and left an orphan draft invoice behind. The flag is restored to its
    snapshot value in the finally step.
    """
    if not rpc.field_exists("res.company", AUTO_INVOICE_FLAG):
        ctx.log(f"res.company.{AUTO_INVOICE_FLAG} absent — "
                "mmg_sale_auto_create_invoice not installed, nothing to "
                "suspend")
        return lambda: None
    company_id = acting_company(rpc)
    original = rpc.read("res.company", [company_id],
                        [AUTO_INVOICE_FLAG])[0][AUTO_INVOICE_FLAG]
    ctx.log(f"company {company_id} {AUTO_INVOICE_FLAG} = {original!r} "
            "(snapshot)")
    if not original:
        return lambda: None
    rpc.write("res.company", [company_id], {AUTO_INVOICE_FLAG: False})
    ctx.log(f"{AUTO_INVOICE_FLAG} cleared for the duration of this test")

    def restore():
        rpc.write("res.company", [company_id], {AUTO_INVOICE_FLAG: original})

    return restore


# --------------------------------------------------------------- fixtures
def ensure_medium(rpc, name):
    """Resolve (or create) the x.medium fixture. `name` must already be
    namespaced by the caller with fx() — this helper searches by name, so a
    bare name would silently reuse a previous run's record (invariant 3)."""
    found = rpc.search("x.medium", [("x_name", "=", name)], limit=1)
    return found[0] if found else rpc.create("x.medium", {"x_name": name})


def product_vals(name, **extra) -> dict:
    """Fixture vals for one product: the namespaced name plus the pinned
    invoicing policy every FG-02 fixture carries (invariant 4)."""
    vals = {"name": name, "invoice_policy": INVOICE_POLICY}
    vals.update(extra)
    return vals


def make_product(rpc, label, **extra):
    """Create one FG-02 fixture variant from a bare label.

    Returns (id, name) — the namespaced name is what the blocked-step
    instructions quote, so the human verifier can find the exact record.
    """
    name = fx(f"{MARK} {label}")
    return rpc.create("product.product", product_vals(name, **extra)), name


def label_name(prefix: str, index: int) -> str:
    """Fixture name make_label_products writes for the 1-based `index`."""
    return fx(f"{MARK} {prefix} {index:03d}")


def label_code(prefix: str, index: int) -> str:
    """Fixture default_code (SKU) for the 1-based `index`. Namespaced: the
    SKU is under mmg_multichannel_shopify's active-scoped unique-SKU
    constraint (invariant 3)."""
    return fx(f"{MARK}-{prefix}-{index:03d}")


def label_artist(prefix: str, index: int) -> str:
    """Fixture x_artist for the 1-based `index` — the value the wizard's slot
    helper must return for that product's label."""
    return fx(f"{MARK} {prefix} Artist {index:03d}")


def label_price(index: int, price_base: float = 100.0) -> float:
    """Fixture list price for the 1-based `index` (distinct per product, as
    TC-LBL-008's precondition asks). Non-zero on purpose: the label prints a
    formatted currency amount (invariant 4)."""
    return price_base + index


# label-data constants shared by every label fixture — literal workbook
# content (invariant 3), quoted by the expected description line
LABEL_DATE = "1950"
LABEL_HEIGHT = 10.5
LABEL_WIDTH = 8.0


def make_label_products(rpc, count, prefix, medium_id, price_base=100.0):
    """Batch-create `count` FG02 variants with distinct label data
    (name, default_code, list_price/lst_price, x_artist, x_date, x_medium,
    x_height, x_width) — the fixture TC-LBL-008..010 ask for.

    Both list_price and lst_price are written: on this database
    multichannel_manage_price redefines product.product.lst_price to read the
    stored variant_price, so list_price alone leaves the *label's* price at
    0.0 (invariant 4). Writing lst_price goes through its inverse, which sets
    variant_price here and list_price - price_extra on a stock database, so
    the fixture is correct on both.
    """
    vals_list = []
    for i in range(1, count + 1):
        price = label_price(i, price_base)
        vals_list.append(product_vals(
            label_name(prefix, i),
            default_code=label_code(prefix, i),
            list_price=price,
            lst_price=price,
            x_artist=label_artist(prefix, i),
            x_date=LABEL_DATE,
            x_medium=medium_id,
            x_height=LABEL_HEIGHT,
            x_width=LABEL_WIDTH,
        ))
    return rpc.create("product.product", vals_list)


def label_wizard(rpc, product_ids):
    """Create an access.avery.label.wizard over the given variants."""
    return rpc.create(LABEL_WIZARD, {"product_ids": [(6, 0, product_ids)]})


def newest_wizard_id(rpc) -> int:
    """Id watermark, taken immediately BEFORE a print entry point is called,
    so the wizard *this* execution created can be identified with
    ('id', '>', watermark).

    The globally newest wizard is not a safe proxy on a shared clone:
    access.avery.label.wizard is a transient table other sessions and the
    vacuum also write to.
    """
    found = rpc.search(LABEL_WIZARD, [], order="id desc", limit=1)
    return found[0] if found else 0


# ------------------------------------------------------------- assertions
def collect_report_record(ctx, xmlid, expects, mismatches) -> int | None:
    """Read the ir.actions.report record behind `xmlid` and record every
    field that differs into `mismatches` (m2o values compared by id).

    Collected-assertion pattern: the caller asserts the whole dict once
    (`ctx.check("report record mismatches", {}, mismatches)`), so one wrong
    field cannot abort the comparison and destroy the evidence for the rest.
    Returns the record id, or None when the XML id does not resolve.
    """
    rpc = ctx.adapter.rpc
    rid = rpc.ref(xmlid)
    if not rid:
        mismatches[f"{xmlid} (record)"] = {"expected": "resolves to a record",
                                           "actual": None}
        return None
    data = rpc.read("ir.actions.report", [rid], list(expects.keys()))[0]
    for field, expected in expects.items():
        actual = data[field]
        if isinstance(actual, (list, tuple)):
            actual = m2o_id(actual)
        if actual != expected:
            mismatches[f"{xmlid}.{field}"] = {"expected": expected,
                                              "actual": actual}
    ctx.log(f"{xmlid} → ir.actions.report id {rid}: {data}")
    return rid


def note_mismatch(mismatches, name, expected, actual):
    """Record `name` in `mismatches` when expected != actual (no-op when they
    match) — the collected-assertion building block used across this suite."""
    if expected != actual:
        mismatches[name] = {"expected": expected, "actual": actual}


def expected_description(date, medium_name, height, width):
    """Mirror of the wizard's check_label_description formula:
    'x_date * medium * height x width', falsy parts omitted,
    floats rendered with %g."""
    parts = []
    if date:
        parts.append(str(date))
    if medium_name:
        parts.append(medium_name)
    dims = []
    if height:
        dims.append("%g" % height)
    if width:
        dims.append("%g" % width)
    if dims:
        parts.append(" x ".join(dims))
    return " * ".join(parts)


def label_description(medium_name):
    """The description line every label fixture must render, built from the
    fixture's own literal data (LABEL_DATE / LABEL_HEIGHT / LABEL_WIDTH)."""
    return expected_description(LABEL_DATE, medium_name,
                                LABEL_HEIGHT, LABEL_WIDTH)


def price_label(rpc, product_id):
    """(amount, formatted) for the lst_price slot value of one fixture.

    check_list_data() formats a float lst_price through
    digest.digest._format_currency_amount(value, product.currency_id), which
    on v15 concatenates the bare currency symbol with the float's own str()
    — '$101.0': no thousands separator and no rounding. Mirrored here from
    the product's *own* currency record (so the expectation holds under any
    company currency) and from the price read back off the fixture, so the
    assertion is about the formatting the label applies, not about a float
    literal.
    """
    row = rpc.read("product.product", [product_id],
                   ["lst_price", "currency_id"])[0]
    amount = row["lst_price"]
    currency = rpc.read("res.currency", [m2o_id(row["currency_id"])],
                        ["symbol", "position"])[0]
    symbol = currency["symbol"] or ""
    formatted = (f"{symbol}{amount}" if currency["position"] == "before"
                 else f"{amount}{symbol}")
    return amount, formatted
