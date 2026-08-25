"""Shared fixtures and helpers for the FG-03 suite
(Sales Order Processing & Pricing).

Live-DB determinism adaptations (documented, not assertion-weakening):

* **Per-execution fixture namespace** — `sweep_fg03()` mints a token and
  `fx()` stamps it on every fixture name AND on every value a test matches
  by content (warning messages, attribute values). This is the pattern that
  made FG-04 and FG-01 reproducible: on a production clone a fixture that a
  confirmed order / picking / posted invoice references can never be
  unlinked, so `sweep_products()` archives it instead. Reused-by-name
  fixtures therefore accumulate across runs, and for FG-03 the consequence
  was worse than a drifting count: a reused STORABLE product carried the
  previous run's stock moves, so its `virtual_available` went negative and
  `mmg_magento2_ept_inherit.sale.order._check_positive_quantity()` refused
  the next order create outright ("You cannot create order with no stock
  available product: - Product: QA AUTO PRODUCT (do not sell)" — the failure
  that retired the legacy tests/sales suite). A unique namespace per execution
  makes every run self-contained regardless of what survived; delivery
  fixtures are additionally consumables (next point), which removes the
  availability check from the picture altogether.

* **Delivery-flow fixtures are consumables, never storables** (`type='consu'`,
  `make_deliverable`). A `type='product'` fixture is unusable on this clone:
  `mmg_magento2_ept_inherit.sale.order.create()` calls
  `_export_order_line_stock_to_magento()` for every line whose product type is
  `'product'`, which runs `product.export_stock_to_magento()` ->
  `update_magento_product()`. That helper raises
  `UserError('Internal reference is required for magento synchronization')`
  for a product without `default_code`, and when a `default_code` IS present it
  creates connector records and can walk into
  `product.category.export_category_to_magento()`, i.e. an outbound Magento
  API call — forbidden by AUTOMATION_CONVENTIONS hard rule 4. Consumables are
  excluded from that filter *and* from `_check_positive_quantity()` (both test
  `product_id.type == 'product'`), while `sale_stock` still launches the stock
  rule and computes `qty_delivered` from stock moves for `consu` lines, so the
  whole pending/partial/full delivery flow of TC-SAL-004/-005/-017 is
  reproduced without stock reservation. Fixture products additionally set
  `stock_export_to_magento = False` where the field exists (belt and braces).

* Marker-scoped searches — "search all orders with delivery_status = 'full'"
  style steps are scoped to this execution's fixture ids, so the clone's
  ~43k live orders cannot leak into exactly-N assertions.

* **A mid-test loss of the Odoo server can only ever be ENVIRONMENT.**
  `attempt()` deliberately swallows `OdooRPCError` so a refusal the workbook
  cares about is recorded as the *actual value* of an assertion — but a
  transport failure (server killed, connection refused/reset, session
  re-authentication failing) is not a refusal by the product. Recording it as
  an actual value would turn a dead server into a misleading FAIL, exactly the
  way run RUN-937DC32E lost TEST-FG03-SAL-019/-020 to "web session
  authentication failed: connection refused". `raise_if_transport_lost()`
  therefore re-raises those as `ServerUnreachable` (a `ConnectionError`), which
  `backend/runner.py` classifies as `failure_class = "ENVIRONMENT"`.

* The company-scoped `auto_create_invoice_after_confirming_so` flag is
  snapshotted and restored in a `finally` step by every test that flips it.

* Whole-table reconciliation queries subtract this platform's own fixture
  partners (`QA_PARTNER_SQL`) so reruns cannot drift a baseline.

Cleanup is deliberately defensive: a raising cleanup inside `finally`
replaces the test's verdict, turning an intended FAIL/BLOCKED into ERROR.
`sweep_fg03()` therefore swallows every RPC error and reports what it could
not remove through the optional `log` callback; marker-named cancelled
records are left behind rather than raising. Order matters and mirrors the
sale flow: payments -> invoices/credit notes -> pickings (cancel) -> orders
(cancel, then unlink record by record) -> products -> attributes -> partners.

Preconditions that are outside the product under test are probed and turned
into a precise `ctx.blocked(...)`, never into a FAIL: a missing module field
(`require_field`), a missing payment journal, a missing wkhtmltopdf, and
AvaTax's forced address validation (`avatax_confirm_probe` — with
`force_address_validation` on, `account_avatax_sale_oca.action_confirm()`
returns `partner.button_avatax_validate_address()`, an outbound AvaTax call,
*instead* of confirming the order).

Version notes mirrored from the workbook's own v15/v19 split:

* `sale.order.line.x_discount` is a Studio field on v15 and a coded Float in
  the v19 port. `x_discount_type()` logs what the target database actually
  declares, because a Char declaration changes the *failure mode* of the
  conversion (string arithmetic raises instead of returning a percentage) —
  see the module docstring of `test_discount.py`.
* `delivery_status` is the custom `mmg_sale_delivery_status` stored compute
  on v15 (pending/partial/full/False) and the native `sale_stock` field on
  v19, which adds `started`.
* v15 has no order-level warning *text*: `mmg_sale_warning_extend` exposes
  `is_show_warning_msg_box` plus the warned-product popup action. The
  workbook asserts the v19 native `sale_warning_text` banner; the v15
  observables are recorded as evidence next to the expected v19 value.
"""
from __future__ import annotations

import uuid

from adapters.base import OdooRPCError
from framework.fg_common import (form_arch, http_session, m2o_id,  # noqa: F401 — re-exported
                                 make_trace, reconcile)
from framework.qa_fixtures import sweep_model, sweep_products

FEATURE = "FG-03 Sales Order Processing & Pricing"
MARK = "FG03"
AUTO_FLAG = "auto_create_invoice_after_confirming_so"

trace = make_trace(FEATURE)

# SQL predicate selecting the partners this platform's fixtures created (any
# suite marker "FGnn " or the framework's QA-AUTO ref). res.partner.name is
# not a translated field, so it stays a plain varchar column on both target
# versions and a regex predicate is version-safe here.
QA_PARTNER_SQL = ("(SELECT id FROM res_partner "
                  "WHERE name ~ '^FG[0-9]{2} ' OR ref = 'QA-AUTO')")


# ---------------------------------------------------------------------------
# Per-execution fixture namespace
# ---------------------------------------------------------------------------
_TOKEN = "init"


def fixture_token() -> str:
    return _TOKEN


def fx(name: str) -> str:
    """Namespace a fixture name/value for this execution: 'FG03 Artwork' ->
    'FG03 Artwork [a1b2c3]'. The MARK prefix is preserved so the sweeps and
    the QA_PARTNER_SQL predicate keep matching."""
    return f"{name} [{_TOKEN}]"


def label(text: str) -> str:
    """Marker-prefixed, namespaced fixture name."""
    return fx(f"{MARK} {text}")


# ---------------------------------------------------------------------------
# Assertion collection
# ---------------------------------------------------------------------------
class Checks:
    """Collect the workbook's expected/actual pairs and assert them once.

    `ctx.check` raises on the first mismatch, so a test whose second workbook
    step is an expected v15 FAIL would hide every later observation —
    including the ones that pass and prove the v15 behaviour. Observations are
    therefore recorded here (and logged as they happen); `assert_all()` then
    re-emits every matching observation as its own passing assertion and
    asserts the complete mismatch dict in one go. Expectations are unchanged:
    any mismatch still fails the test.
    """

    def __init__(self, ctx):
        self.ctx = ctx
        self._order: list[str] = []
        self._pairs: dict[str, tuple] = {}

    def record(self, name, expected, actual) -> bool:
        if name not in self._pairs:
            self._order.append(name)
        self._pairs[name] = (expected, actual)
        ok = expected == actual
        self.ctx.log(f"{'OK  ' if ok else 'DIFF'} {name}: "
                     f"expected={expected!r} actual={actual!r}")
        return ok

    def mismatches(self) -> dict:
        return {name: {"expected": exp, "actual": act}
                for name in self._order
                for exp, act in [self._pairs[name]] if exp != act}

    def assert_all(self, name="mismatches vs the workbook's expected result"):
        for key in self._order:
            expected, actual = self._pairs[key]
            if expected == actual:
                self.ctx.check(key, expected, actual)
        self.ctx.check(name, {}, self.mismatches())


def sql_rows_optional(ctx, query, note):
    """Read-only SQL for *supplementary evidence* steps.

    `ctx.sql` marks the whole test BLOCKED when the environment has no pg_*
    configuration — correct for a DATA_RECONCILIATION test whose verdict IS
    the query, wrong for a functional test that merely records a baseline
    query alongside its ORM assertions. Returns None (and logs why) instead
    of changing the verdict.
    """
    if not (getattr(ctx.env, "pg_host", None)
            and getattr(ctx.env, "pg_user", None)):
        ctx.log(f"{note}: no PostgreSQL access configured for environment "
                f"'{ctx.env.key}' — evidence query skipped")
        return None
    try:
        return ctx.sql.rows(query)
    except Exception as exc:                      # noqa: BLE001 — evidence only
        ctx.log(f"{note}: query failed ({exc})")
        return None


class ServerUnreachable(ConnectionError):
    """The Odoo server (or its session endpoint) went away mid-test.

    Subclasses ConnectionError on purpose: `backend/runner.py` classifies
    ConnectionError/OSError/TimeoutError as `failure_class = "ENVIRONMENT"`,
    so a killed server can never be reported as a product FAIL.
    """


# `adapters.base` wraps transport failures in OdooRPCError
# ("<model>.<method> failed: <urlopen error …>", "web session authentication
# failed: …"), which is indistinguishable from a business refusal at the type
# level — these substrings are how the two are told apart.
_TRANSPORT_MARKERS = (
    "urlopen error", "winerror", "web session authentication failed",
    "connection refused", "actively refused", "connection reset",
    "connection aborted", "remote end closed connection",
    "server closed the connection", "timed out", "timeout",
    "bad gateway", "service unavailable", "gateway time-out",
    "temporary failure in name resolution", "no route to host",
)


def transport_lost(message) -> bool:
    text = str(message).lower()
    return any(marker in text for marker in _TRANSPORT_MARKERS)


def raise_if_transport_lost(exc):
    """Re-raise a transport-level failure as ServerUnreachable (-> ENVIRONMENT).

    Called from every place that would otherwise swallow an OdooRPCError and
    record its message as an assertion's actual value.
    """
    if transport_lost(exc):
        raise ServerUnreachable(str(exc)) from exc


def attempt(func, *args, **kwargs):
    """Run an RPC call the workbook may or may not expect to raise.

    Returns (ok, value) on success and (False, "<error message>") when the
    server *refuses*, so the outcome can be recorded as evidence instead of
    aborting the test with an unrecorded traceback.

    A transport failure is NOT a refusal: it is re-raised as
    `ServerUnreachable` so the run reports ENVIRONMENT instead of a misleading
    FAIL built from a connection-error string.
    """
    try:
        return True, func(*args, **kwargs)
    except OdooRPCError as exc:
        raise_if_transport_lost(exc)
        return False, str(exc)


# ---------------------------------------------------------------------------
# Company / configuration
# ---------------------------------------------------------------------------
def company_id(rpc) -> int:
    return m2o_id(rpc.read("res.users", [rpc.uid], ["company_id"])[0]
                  ["company_id"])


def company_partner(rpc, cid=None) -> int:
    cid = cid or company_id(rpc)
    return m2o_id(rpc.read("res.company", [cid], ["partner_id"])[0]
                  ["partner_id"])


def get_auto_invoice_flag(rpc, cid) -> bool:
    return bool(rpc.read("res.company", [cid], [AUTO_FLAG])[0][AUTO_FLAG])


def set_auto_invoice_flag(rpc, cid, value) -> None:
    rpc.write("res.company", [cid], {AUTO_FLAG: bool(value)})


def restore_auto_invoice_flag(ctx, rpc, cid, value) -> None:
    """Never let the restore raise — it runs inside `finally`."""
    try:
        set_auto_invoice_flag(rpc, cid, value)
    except Exception as exc:                    # noqa: BLE001 — see docstring
        ctx.log(f"cleanup incomplete: could not restore {AUTO_FLAG}="
                f"{value!r} on company {cid}: {exc}")


def x_discount_type(rpc) -> str:
    """The declared type of sale.order.line.x_discount ('float' in the v19
    port, whatever the Studio layer left behind on v15), or 'absent'."""
    try:
        info = rpc.call("sale.order.line", "fields_get", ["x_discount"],
                        attributes=["type"])
    except OdooRPCError as exc:
        raise_if_transport_lost(exc)
        return f"unreadable ({exc})"
    if "x_discount" not in info:
        return "absent"
    return info["x_discount"].get("type") or "unknown"


# ---------------------------------------------------------------------------
# Preconditions (BLOCKED, never FAILED)
# ---------------------------------------------------------------------------
def require_field(ctx, rpc, model, field, module, purpose) -> None:
    """A missing module field is a missing precondition, not a defect.

    The workbook lists the owning module as a precondition of every TC here,
    so the absence of its field blocks the execution with a reason that names
    what is missing and what would unblock it — reporting FAIL would claim the
    product broke a behaviour it never had a chance to run.
    """
    if not rpc.field_exists(model, field):
        ctx.blocked(
            f"{model}.{field} does not exist on this database — {purpose} "
            f"cannot be exercised. Install/upgrade {module} on "
            f"'{ctx.env.key}' (db {ctx.env.db}) and re-run; on v19 the field "
            "is expected to come from the ported module of the same name.")


def avatax_confirm_probe(ctx, rpc) -> str:
    """Probe the AvaTax configuration that sale.order.action_confirm() reads.

    `account_avatax_sale_oca.sale.order.action_confirm()` calls
    `company.get_avatax_config_company()` — an `avalara.salestax` row with
    `disable_tax_calculation = False` — and, when that config carries
    `force_address_validation`, RETURNS `partner.button_avatax_validate_address()`
    instead of confirming: an outbound AvaTax call (hard rule 4) plus an order
    that silently stays in 'draft', which would surface as a misleading FAIL on
    every confirm assertion in this suite. Blocked with a precise reason in that
    case; otherwise the config state is logged as evidence and returned.

    Tax *computation* itself is gated per order by
    `fiscal_position_id.is_avatax`; FG-03 fixture partners are created without a
    fiscal position, so `avalara_compute_taxes()` never calls out for them.
    """
    if not rpc.model_exists("avalara.salestax"):
        note = "no avalara.salestax model on this database (AvaTax not installed)"
        ctx.log(f"AvaTax confirm probe: {note}")
        return note
    fields = ["company_id", "disable_tax_calculation"]
    if rpc.field_exists("avalara.salestax", "force_address_validation"):
        fields.append("force_address_validation")
    ok, rows = attempt(rpc.search_read, "avalara.salestax",
                       [("disable_tax_calculation", "=", False)], fields)
    if not ok:
        ctx.log(f"AvaTax confirm probe: config unreadable ({rows}) — "
                "continuing, confirm assertions record what actually happens")
        return f"unreadable ({rows})"
    active = [r for r in rows if r.get("force_address_validation")]
    if active:
        ctx.blocked(
            "AvaTax force_address_validation is enabled on "
            f"avalara.salestax {[r['id'] for r in active]} "
            f"({[r['company_id'] for r in active]}): "
            "account_avatax_sale_oca.sale.order.action_confirm() would call "
            "the AvaTax address-validation API and return that action instead "
            "of confirming the order, so every confirm assertion in this test "
            "would be a false failure and the run would hit an external "
            "service. Unblock by clearing force_address_validation (or setting "
            "disable_tax_calculation) on the QA clone's AvaTax configuration, "
            "or by running this TC on an AvaTax sandbox.")
    note = (f"{len(rows)} enabled avalara.salestax config(s), none forcing "
            "address validation")
    ctx.log(f"AvaTax confirm probe: {note}")
    return note


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
_MAGENTO_STOCK_FLAG = None      # cached per process: field present or not


def _no_magento_export_vals(rpc) -> dict:
    """Opt fixture products out of the Magento stock mirror.

    `mmg_magento2_ept_inherit` adds product.template.stock_export_to_magento
    with default True. Consumable fixtures never reach the export path anyway
    (it filters on `type == 'product'`), but a fixture that is explicitly
    opted out cannot reach it even if a future test needs a storable.
    """
    global _MAGENTO_STOCK_FLAG
    if _MAGENTO_STOCK_FLAG is None:
        try:
            _MAGENTO_STOCK_FLAG = rpc.field_exists("product.template",
                                                   "stock_export_to_magento")
        except Exception:                       # noqa: BLE001 — probe only
            _MAGENTO_STOCK_FLAG = False
    return {"stock_export_to_magento": False} if _MAGENTO_STOCK_FLAG else {}


def make_partner(rpc, text, **vals) -> int:
    """A fresh, namespaced customer for this execution."""
    base = {"name": label(text),
            "street": "100 QA Test Street", "city": "Tucson",
            "state_id": False, "zip": "85701",
            "comment": "FG-03 QA fixture (odoo-regression). Safe to delete."}
    base.update(vals)
    return rpc.create("res.partner", base)


def make_template(rpc, text, price=500.0, product_type="service",
                  **vals) -> int:
    """A fresh, namespaced product template.

    `product_type` is 'service' (no transfers, the default) or 'consu' (real
    delivery transfers). It is deliberately NEVER 'product': see the module
    docstring — a storable fixture drags every order create into
    mmg_magento2_ept_inherit's Magento mirror and its positive-availability
    check.
    """
    base = {"name": label(text), "list_price": price, "sale_ok": True,
            # zero taxes keeps the workbook's totals deterministic whatever
            # the clone's default tax configuration is
            "taxes_id": [(6, 0, [])],
            "invoice_policy": "order",
            "type": product_type}
    base.update(_no_magento_export_vals(rpc))
    base.update(vals)
    return rpc.create("product.template", base)


def variants_of(rpc, tmpl_id) -> list:
    return rpc.search("product.product",
                      [("product_tmpl_id", "=", tmpl_id)], order="id")


def make_product(rpc, text, price=500.0, product_type="service",
                 **vals) -> int:
    """Template + variant; returns the variant id (what order lines use)."""
    tmpl = make_template(rpc, text, price, product_type, **vals)
    variants = variants_of(rpc, tmpl)
    return variants[0]


def make_deliverable(rpc, text, price=100.0, **vals) -> int:
    """A fixture product that produces real delivery transfers.

    Consumable (`type='consu'`), not storable, and the choice is not
    cosmetic — see the module docstring: `sale_stock` launches the stock rule
    and computes `qty_delivered` from stock moves for `consu` lines exactly as
    for `product` lines, so pending/partial/full delivery is reproduced, while
    the product stays outside both `_check_positive_quantity()` and the
    Magento stock export (both filter on `type == 'product'`). No quant is
    needed: consumables are always available, so no run can leave a fixture
    product with a negative `virtual_available` for the next one.
    """
    return make_product(rpc, text, price, product_type="consu", **vals)


def multi_step_warehouse(rpc, cid):
    """An existing warehouse whose outgoing route has more than one step, or
    None. Read-only on purpose: reaching the native 'started' delivery state
    needs a pick+ship route, and re-configuring a live warehouse's
    delivery_steps rewrites its stock rules and locations — too invasive for
    a pre-existing business record on the shared clone."""
    rows = rpc.search_read("stock.warehouse",
                           [("company_id", "=", cid),
                            ("delivery_steps", "!=", "ship_only")],
                           ["name", "delivery_steps"], limit=1,
                           order="sequence,id")
    return rows[0] if rows else None


def picking_codes(rpc, picking_ids) -> dict:
    """{picking_id: picking_type code} — 'internal' identifies the PICK step
    of a multi-step delivery, 'outgoing' the customer delivery."""
    rows = rpc.search_read("stock.picking", [("id", "in", picking_ids)],
                           ["picking_type_id"])
    type_ids = sorted({m2o_id(r["picking_type_id"]) for r in rows
                       if r["picking_type_id"]})
    codes = {}
    if type_ids:
        codes = {r["id"]: r["code"] for r in rpc.search_read(
            "stock.picking.type", [("id", "in", type_ids)], ["code"])}
    return {r["id"]: codes.get(m2o_id(r["picking_type_id"])) for r in rows}


def order_origin() -> str:
    """The namespaced `origin` every FG-03 fixture order carries, so an order
    created directly with rpc.create is as traceable as one from
    make_order()."""
    return fx(MARK)


def make_order(rpc, partner_id, lines=(), **vals) -> int:
    """lines: iterable of (product_id, qty, price_unit[, extra_line_vals])."""
    order_lines = []
    for line in lines:
        product_id, qty, price = line[0], line[1], line[2]
        extra = line[3] if len(line) > 3 else {}
        name = rpc.read("product.product", [product_id],
                        ["display_name"])[0]["display_name"]
        line_vals = {"product_id": product_id, "name": name,
                     "product_uom_qty": qty, "price_unit": price}
        line_vals.update(extra)
        order_lines.append((0, 0, line_vals))
    base = {"partner_id": partner_id, "origin": order_origin()}
    if order_lines:
        base["order_line"] = order_lines
    base.update(vals)
    return rpc.create("sale.order", base)


def add_line(rpc, order_id, product_id, qty=1.0, price=None, **extra) -> int:
    data = rpc.read("product.product", [product_id],
                    ["display_name", "lst_price"])[0]
    vals = {"order_id": order_id, "product_id": product_id,
            "name": data["display_name"], "product_uom_qty": qty,
            "price_unit": data["lst_price"] if price is None else price}
    vals.update(extra)
    return rpc.create("sale.order.line", vals)


def order_lines(rpc, order_id, fields):
    return rpc.search_read("sale.order.line", [("order_id", "=", order_id)],
                           fields, order="id")


def line_state(rpc, line_id, fields=("discount", "x_discount")) -> dict:
    return rpc.read("sale.order.line", [line_id], list(fields))[0]


def rounded(value, digits=2):
    """Round a numeric field for comparison; pass anything else through so a
    non-numeric actual (e.g. a Char x_discount, or an error string) is
    recorded verbatim as evidence."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return value
    return round(float(value), digits)


# ---------------------------------------------------------------------------
# Order-to-cash operations
# ---------------------------------------------------------------------------
def invoice_or_block(ctx, rpc, order_id, label_text):
    """`invoice_order()` for a step whose fixture it is, not its subject.

    Returns the new move id, or blocks with the server's own reason: an
    accounting precondition (closed period, missing journal, no rights) must
    not be reported as a defect in the field under test, and reading `[0]` off
    an empty list would surface it as an unrecorded ERROR instead.
    """
    ok, moves = attempt(invoice_order, rpc, order_id)
    if ok and moves:
        return moves[0]
    ctx.blocked(
        f"could not create {label_text} from order {order_id} through "
        "sale.advance.payment.inv — "
        f"{moves if not ok else 'the wizard created no move'}. This is an "
        "accounting precondition of the TC (invoiceable line, open period, "
        "invoicing rights), not a defect in the behaviour under test.")


def invoice_order(rpc, order_id) -> list:
    """'Create Invoice' button equivalent (sale.advance.payment.inv, regular
    invoice). `_create_invoices` is private and cannot be called over the web
    endpoint, so the wizard is the public path. Returns the new move ids."""
    before = rpc.read("sale.order", [order_id],
                      ["invoice_ids"])[0]["invoice_ids"]
    wiz_ctx = {"active_model": "sale.order", "active_ids": [order_id],
               "active_id": order_id}
    wiz = rpc.call("sale.advance.payment.inv", "create",
                   {"advance_payment_method": "delivered"}, context=wiz_ctx)
    rpc.call("sale.advance.payment.inv", "create_invoices", [wiz],
             context=wiz_ctx)
    after = rpc.read("sale.order", [order_id],
                     ["invoice_ids"])[0]["invoice_ids"]
    return [i for i in after if i not in before]


def reverse_invoice(rpc, move_id, reason) -> list:
    """Credit note through the account.move.reversal wizard (the UI's Credit
    Note button). Returns the new move ids."""
    journal = m2o_id(rpc.read("account.move", [move_id],
                              ["journal_id"])[0]["journal_id"])
    wiz_ctx = {"active_model": "account.move", "active_ids": [move_id],
               "active_id": move_id}
    wiz = rpc.call("account.move.reversal", "create",
                   {"move_ids": [(6, 0, [move_id])],
                    "refund_method": "refund",
                    "reason": reason,
                    "journal_id": journal},
                   context=wiz_ctx)
    rpc.call("account.move.reversal", "reverse_moves", [wiz], context=wiz_ctx)
    return rpc.read("account.move.reversal", [wiz],
                    ["new_move_ids"])[0]["new_move_ids"]


def payment_journal(rpc, cid):
    rows = rpc.search("account.journal",
                      [("company_id", "=", cid),
                       ("type", "in", ["bank", "cash"])],
                      limit=1, order="sequence,id")
    return rows[0] if rows else None


def register_payment(rpc, move_id):
    """Register a full payment on a posted invoice through the
    account.payment.register wizard (the UI's Register Payment button)."""
    wiz_ctx = {"active_model": "account.move", "active_ids": [move_id],
               "active_id": move_id, "dont_redirect_to_payments": True}
    wiz = rpc.call("account.payment.register", "create", {}, context=wiz_ctx)
    return rpc.call("account.payment.register", "action_create_payments",
                    [wiz], context=wiz_ctx)


def pickings_of(rpc, order_id) -> list:
    return rpc.read("sale.order", [order_id],
                    ["picking_ids"])[0]["picking_ids"]


def validate_picking(rpc, picking_id, done_qty_by_product=None):
    """Write stock.move.quantity_done, then button_validate, resolving the
    immediate-transfer / backorder wizards the v15 flow returns."""
    moves = rpc.search_read(
        "stock.move",
        [("picking_id", "=", picking_id),
         ("state", "not in", ["done", "cancel"])],
        ["id", "product_id", "product_uom_qty"])
    for move in moves:
        qty = move["product_uom_qty"]
        if done_qty_by_product is not None:
            qty = done_qty_by_product.get(m2o_id(move["product_id"]), 0.0)
        rpc.write("stock.move", [move["id"]], {"quantity_done": qty})
    res = rpc.call("stock.picking", "button_validate", [picking_id])
    if isinstance(res, dict) and res.get("res_model") in (
            "stock.backorder.confirmation", "stock.immediate.transfer"):
        wiz_model = res["res_model"]
        wiz_ctx = dict(res.get("context") or {})
        wiz = rpc.call(wiz_model, "create", {}, context=wiz_ctx)
        rpc.call(wiz_model, "process", [wiz], context=wiz_ctx)
    return res


def cancel_order_flow(rpc, order_ids):
    """Cancel through whatever flow the version exposes.

    v15 `action_cancel` returns the sale.order.cancel wizard when a draft
    invoice exists; the wizard's own action_cancel re-runs the cancellation
    with `disable_cancel_warning`. Returns (raised, detail, wizard_seen).
    """
    ok, res = attempt(rpc.call, "sale.order", "action_cancel", order_ids)
    if not ok:
        return True, res, False
    if isinstance(res, dict) and res.get("res_model") == "sale.order.cancel":
        wiz_ctx = dict(res.get("context") or {})
        ok, wiz = attempt(rpc.call, "sale.order.cancel", "create", {},
                          context=wiz_ctx)
        if not ok:
            return True, wiz, True
        ok, detail = attempt(rpc.call, "sale.order.cancel", "action_cancel",
                             [wiz], context=wiz_ctx)
        return (not ok), (detail if not ok else ""), True
    return False, "", False


# ---------------------------------------------------------------------------
# Reports (HTTP evidence)
# ---------------------------------------------------------------------------
def report_response(ctx, converter, report_name, res_id):
    """Fetch a QWeb report the way the browser does
    (/report/<converter>/<report>/<id>) over an authenticated web session.
    Returns (status, payload_bytes).

    An HTTP error status is a real result and is returned as-is (a 500 from the
    report engine is a finding). A socket-level failure is not: it is raised as
    ServerUnreachable so a dead server reports ENVIRONMENT instead of
    "expected HTTP 200, got 0".
    """
    import urllib.error
    try:
        opener = http_session(ctx.env)
    except Exception as exc:                    # noqa: BLE001 — see docstring
        raise ServerUnreachable(f"report session could not be opened: "
                                f"{exc}") from exc
    url = f"{ctx.env.base_url}/report/{converter}/{report_name}/{res_id}"
    try:
        with opener.open(url, timeout=300) as res:
            return getattr(res, "status", res.getcode()), res.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()[:4000]
    except OSError as exc:
        raise ServerUnreachable(f"{url} unreachable: {exc}") from exc


# ---------------------------------------------------------------------------
# v15 warning-banner observables
# ---------------------------------------------------------------------------
def warned_products_v15(rpc, order_id):
    """The v15 equivalent of the v19 banner list: the product ids the
    warned-product popup action (mmg_sale_warning_extend) would show."""
    ok, action = attempt(rpc.call, "sale.order",
                         "action_open_order_lines_warning_message", [order_id])
    if not ok:
        return action, []
    ids = []
    for clause in (action or {}).get("domain") or []:
        if isinstance(clause, (list, tuple)) and len(clause) == 3 \
                and clause[0] == "id" and clause[1] == "in":
            ids = list(clause[2])
    return action, sorted(ids)


def banner_text(rpc, order_id):
    """The v19 native order-level warning banner, or None when the field does
    not exist on the target version (v15: mmg_sale_warning_extend never
    declared an order-level text field — FG-03 decision #2 replaces the popup
    with the native banner)."""
    if not rpc.field_exists("sale.order", "sale_warning_text"):
        return None
    return rpc.read("sale.order", [order_id],
                    ["sale_warning_text"])[0]["sale_warning_text"]


# ---------------------------------------------------------------------------
# Sweep
# ---------------------------------------------------------------------------
def _noop(_message):
    pass


def _unlink_best_effort(rpc, model, ids, log, context=None, note=""):
    """Unlink a batch, then retry record by record.

    A single undeletable record (a posted-once move, an order whose cancel
    was refused) would otherwise make the whole batch unlink fail and leave
    every sibling behind.
    """
    if not ids:
        return
    try:
        rpc.call(model, "unlink", list(ids), context=context or {})
        return
    except Exception:                           # noqa: BLE001 — see docstring
        pass
    left = []
    for record_id in ids:
        try:
            rpc.call(model, "unlink", [record_id], context=context or {})
        except Exception:                       # noqa: BLE001 — see docstring
            left.append(record_id)
    if left:
        log(f"cleanup: {note or model} left in place (marker-named, "
            f"cancelled): {left}")


def _sweep_payments(rpc, log):
    rows = rpc.search_read(
        "account.payment", [("partner_id.name", "like", f"{MARK} %")],
        ["state", "move_id"])
    move_ids = []
    for row in rows:
        try:
            if row["state"] == "posted":
                rpc.call("account.payment", "action_draft", [row["id"]])
            rpc.call("account.payment", "action_cancel", [row["id"]])
        except Exception as exc:
            log(f"cleanup incomplete: payment {row['id']}: {exc}")
        if row["move_id"]:
            move_ids.append(m2o_id(row["move_id"]))
    _cancel_unlink_moves(rpc, move_ids, log)


def _cancel_unlink_moves(rpc, move_ids, log):
    if not move_ids:
        return
    rows = rpc.search_read("account.move", [("id", "in", move_ids)],
                           ["state"])
    posted = [r["id"] for r in rows if r["state"] == "posted"]
    if posted:
        try:
            rpc.call("account.move", "button_draft", posted)
        except Exception as exc:
            log(f"cleanup incomplete: reset to draft {posted}: {exc}")
    todo = [r["id"] for r in rows if r["state"] != "cancel"]
    if todo:
        try:
            rpc.call("account.move", "button_cancel", todo)
        except Exception as exc:
            log(f"cleanup incomplete: cancel moves {todo}: {exc}")
    # posted-once moves cannot be deleted at all: whatever survives stays
    # behind cancelled and marker-named, which is the documented outcome
    _unlink_best_effort(rpc, "account.move", [r["id"] for r in rows], log,
                        context={"force_delete": True},
                        note="account.move")


def sweep_fg03(rpc, log=_noop):
    """Open a fresh fixture namespace, then remove marker-scoped leftovers.

    Order matters and mirrors the sale flow: payments -> invoices/credit
    notes -> pickings -> orders -> products -> partners. Every step is
    best-effort; nothing here may raise, because this runs both at test start
    and inside `finally`.
    """
    global _TOKEN
    _TOKEN = uuid.uuid4().hex[:6]

    try:
        _sweep_payments(rpc, log)
    except Exception as exc:
        log(f"cleanup incomplete: payments sweep: {exc}")

    try:
        inv_ids = rpc.search("account.move",
                             [("partner_id.name", "like", f"{MARK} %"),
                              ("move_type", "in",
                               ["out_invoice", "out_refund"])])
        _cancel_unlink_moves(rpc, inv_ids, log)
    except Exception as exc:
        log(f"cleanup incomplete: invoice sweep: {exc}")

    order_ids = []
    try:
        order_ids = rpc.search("sale.order",
                               [("partner_id.name", "like", f"{MARK} %")])
    except Exception as exc:
        log(f"cleanup incomplete: order search: {exc}")
    if order_ids:
        try:
            picks = rpc.search("stock.picking",
                               [("sale_id", "in", order_ids),
                                ("state", "not in", ["done", "cancel"])])
            if picks:
                rpc.call("stock.picking", "action_cancel", picks)
        except Exception as exc:
            log(f"cleanup incomplete: picking cancel: {exc}")
        for oid in order_ids:
            try:
                rpc.call("sale.order", "action_cancel", [oid],
                         context={"disable_cancel_warning": True})
            except Exception:
                pass
        _unlink_best_effort(rpc, "sale.order", order_ids, log,
                            note="sale.order")

    try:
        sweep_products(rpc, MARK)
        sweep_model(rpc, "product.attribute.value",
                    [("name", "like", f"{MARK} %")])
        sweep_model(rpc, "product.attribute", [("name", "like", f"{MARK} %")])
        sweep_model(rpc, "res.partner", [("name", "like", f"{MARK} %"),
                                         ("user_ids", "=", False)])
    except Exception as exc:
        log(f"cleanup incomplete: master-data sweep: {exc}")
