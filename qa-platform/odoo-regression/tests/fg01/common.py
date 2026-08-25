"""Shared fixtures and helpers for the FG-01 suite
(Art Catalogue & Product Master Data).

The workbook steps were written for isolated TransactionCase runs. This suite
executes them against a production clone (69k live products), so it applies
the four determinism rules proven on FG-04 — none of them weakens, inverts or
drops an expectation:

1. PER-EXECUTION FIXTURE NAMESPACE. ``sweep_fg01()`` mints a token; ``fx()``
   stamps it on every fixture *name* and on every *value* a test counts or
   matches by (artist strings, medium / category / style names, vendor
   values). ``fx_barcode()`` is the numeric equivalent for the Tile fixtures,
   which carry a global UNIQUE constraint and therefore cannot be namespaced
   with text. Why it is needed: on a production clone deletion frequently
   cannot succeed — ``sweep_products()`` archives a product it cannot unlink —
   so a name or value shared with an earlier run gets silently reused by an
   ensure-by-name fixture or inflates an "exactly N records" assertion.
   Workbook *data* values that are read back by record id (the 17-field
   catalogue create, the nine auction values, the copy() carry-over set) are
   deliberately NOT namespaced: those asserted values stay exactly the
   workbook's.
2. DEFENSIVE CLEANUP. ``cleanup_fg01()`` / ``unlink_quiet()`` run in the
   ``finally`` step and never raise. The runner classifies whatever leaves the
   test function, so a raising cleanup REPLACES the verdict and turns an
   intended FAIL or BLOCKED into ERROR.
3. COLLECTED ASSERTIONS. Multi-field verification builds a mismatch mapping
   and asserts it once (``ctx.check("… mismatches", {}, mismatches)``);
   ``ctx.check`` raises on the first mismatch, so a loop of per-field checks
   reports one broken field and never evaluates the rest.
4. NO VERSION BRANCHES IN TEST BODIES. Every v15/v19 API or URL difference
   lives in a helper here (``display_name``, ``view_arch``, ``record_url``,
   ``list_url``, ``is_v15`` / ``is_v19``) or in ``framework/fg_common.py``
   (``form_arch``, ``m2o_id``, ``reconcile``, ``http_session``). The
   remaining ``is_v19(ctx)`` guards in the reconciliation tests are the
   workbook's own "on the v15 clone… / on v19…" step split, not behaviour
   branches.
"""
from __future__ import annotations

import base64
import csv as _csv
import hashlib
import uuid
from collections import Counter

from framework.fg_common import (form_arch, http_session, m2o_id,  # noqa: F401 — re-exported
                                 make_trace, reconcile)
from framework.qa_fixtures import sweep_model, sweep_products
from pages import LoginPage

FEATURE = "FG-01 Art Catalogue & Product Master Data"
SOURCE = "MMG_v19_Test_Cases_Grouped_by_Feature_v3.0.xlsx / Automation Export"
MARK = "FG01"

# 1x1 red PNG
PNG_1PX = base64.b64encode(base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQ"
    "DwAEhQGAhKmMIQAAAABJRU5ErkJggg==")).decode()  # round-trip keeps it valid

trace = make_trace(FEATURE)


# ---------------------------------------------------------------------------
# Per-execution fixture namespace (FG-04 pattern, rule 1 of the module
# docstring)
# ---------------------------------------------------------------------------
_TOKEN = "init"


def fixture_token() -> str:
    return _TOKEN


def fx(name: str) -> str:
    """Namespace a fixture name/value for this execution.

    The MARK / "QA Test" prefix is preserved, so ``sweep_fg01``'s prefix
    searches and the reconciliation tests' QA_NAME_PATTERNS keep matching.
    """
    return f"{name} [{_TOKEN}]"


def fx_barcode(seq: int = 0) -> str:
    """Per-execution barcode (Tile) in the platform's 9001… QA range.

    barcode is a value matched by *globally*: mmg_stock puts a UNIQUE
    constraint on it (``product_product_barcode_uniq``) and
    ``_check_template_barcode_constraints`` rejects anything that is not
    digits, so ``fx()`` cannot be used. A hard-coded fixture barcode is
    re-created on every run, and a leftover product that the sweep could only
    archive keeps it — the next run's create then fails on a duplicate that
    has nothing to do with the behaviour under test. The digits are derived
    from this execution's token, so every run writes its own barcodes.
    """
    bucket = int(hashlib.sha1(_TOKEN.encode()).hexdigest()[:8], 16) % 100000
    return f"9001{bucket:05d}{seq:02d}"


def _quiet(problems: list, label: str, fn, *args, **kwargs):
    """Run one sweep/cleanup phase, recording instead of raising."""
    try:
        return fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 — a sweep must never raise
        problems.append(f"{label}: {exc}")
        return None


def sweep_fg01(rpc) -> list:
    """Open a fresh fixture namespace, then remove marker-scoped leftovers.

    Returns the list of phases that could not complete and never raises:
    deletion is best-effort by design (``sweep_products`` archives what it
    cannot unlink), and because the new namespace is unique, whatever survives
    can never collide with this execution's assertions.
    """
    global _TOKEN
    _TOKEN = uuid.uuid4().hex[:6]
    problems: list = []
    # purchase orders first (they reference products)
    po_ids = _quiet(problems, "purchase.order search", rpc.search,
                    "purchase.order",
                    [("partner_id.name", "like", f"{MARK}%")]) or []
    if po_ids:
        _quiet(problems, "purchase.order cancel", rpc.call,
               "purchase.order", "button_cancel", po_ids)
        _quiet(problems, "purchase.order unlink", rpc.unlink,
               "purchase.order", po_ids)
    _quiet(problems, "product sweep", sweep_products, rpc, MARK)
    for model, domain in (
            ("x.medium", [("x_name", "like", f"{MARK}%")]),
            ("x.medium", [("x_name", "like", "QA Test Medium%")]),
            ("product.color", [("name", "like", "QA Test%")]),
            ("product.origin", [("name", "like", "QA Test%")]),
            ("product.product.style", [("name", "like", "QA Test%")]),
            # TC-ART-017's ordering fixture: a prefix LIKE, so it finds both
            # this suite's namespaced rows and the un-namespaced leftovers of
            # earlier runs (the value itself is invented by this suite)
            ("product.product.style", [("name", "like", "AA First Style%")]),
            ("product.product.category", [("name", "like", "QA Test%")]),
            ("product.category", [("name", "like", f"{MARK} Web Categ%")]),
            ("res.partner", [("name", "like", f"{MARK} %"),
                             ("user_ids", "=", False)]),
    ):
        _quiet(problems, f"{model} sweep", sweep_model, rpc, model, domain)
    return problems


def cleanup_fg01(ctx, rpc) -> None:
    """Fixture cleanup for the ``finally`` step — NEVER raises.

    The runner classifies whatever exception leaves the test function, so an
    OdooRPCError raised here would REPLACE the verdict: an intended FAIL (a
    documented v15 baseline) or BLOCKED would be reported as ERROR and the
    finding would be lost. Every phase therefore runs through ``_quiet()`` and
    is reported with ``ctx.log()``.
    """
    problems = sweep_fg01(rpc)
    if problems:
        ctx.log("cleanup incomplete: " + "; ".join(problems)
                + " — fixtures are namespaced per execution, so leftovers "
                  "cannot affect another run")


def unlink_quiet(ctx, rpc, model: str, ids, cancel_method: str = "") -> bool:
    """Delete fixture records without ever raising (see ``cleanup_fg01``).

    Cancels first when the model needs it (an order/invoice/picking cannot be
    unlinked from a confirmed state), then unlinks the batch, then falls back
    record by record so one blocked record cannot strand the others.
    """
    ids = [i for i in (ids or []) if i]
    if not ids:
        return True
    if cancel_method:
        try:
            rpc.call(model, cancel_method, ids)
        except Exception as exc:  # noqa: BLE001 — cleanup must not raise
            ctx.log(f"cleanup: {model}.{cancel_method} refused: {exc}")
    try:
        rpc.unlink(model, ids)
        return True
    except Exception as exc:  # noqa: BLE001 — cleanup must not raise
        ctx.log(f"cleanup: batch unlink of {model} {ids} refused: {exc}")
    left = []
    for rec in ids:
        try:
            rpc.unlink(model, [rec])
        except Exception:  # noqa: BLE001 — cleanup must not raise
            left.append(rec)
    if left:
        ctx.log(f"cleanup incomplete: {model} {left} still present — "
                f"namespaced fixtures, so they cannot affect another run")
    return not left


def ensure_medium(rpc, name):
    """x.medium fixture, found-or-created by name.

    ``name`` must already be namespaced with ``fx()``: the medium name is a
    value the tests search and group by, and an ensure-by-name fixture would
    otherwise reuse an earlier run's leftover row.
    """
    found = rpc.search("x.medium", [("x_name", "=", name)], limit=1)
    return found[0] if found else rpc.create("x.medium", {"x_name": name})


# ---------------------------------------------------------------------------
# Version-dependent access (FG-04 pattern, rule 4: never inline in a test)
# ---------------------------------------------------------------------------
def is_v15(ctx) -> bool:
    """True on the v15 baseline clone."""
    return ctx.env.version == "15"


def is_v19(ctx) -> bool:
    """True on the migration target — guards the workbook's "on v19…" steps."""
    return not is_v15(ctx)


def display_name(ctx, rpc, model: str, rec_id: int) -> str:
    """Display name of one record.

    v15 exposes ``name_get()``; ``display_name`` is the canonical read from
    v16 on (``name_get`` was removed in v17).
    """
    if is_v15(ctx):
        return rpc.call(model, "name_get", [rec_id])[0][1]
    return rpc.read(model, [rec_id], ["display_name"])[0]["display_name"]


def view_arch(ctx, model: str, view_type: str = "form", view_id=None) -> str:
    """Served view architecture, version-agnostically.

    ``framework.fg_common.form_arch()`` covers a model's default view; this
    variant adds the explicit ``view_id`` the list-column case needs (v15
    ``fields_view_get`` / v16+ ``get_view``, where the ``tree`` view type was
    renamed ``list``).
    """
    if view_id is None:
        return form_arch(ctx, model, view_type)
    rpc = ctx.adapter.rpc
    if is_v15(ctx):
        return rpc.call(model, "fields_view_get", view_id=view_id,
                        view_type=view_type)["arch"]
    vt = "list" if view_type == "tree" else view_type
    return rpc.call(model, "get_view", view_id=view_id, view_type=vt)["arch"]


def record_url(ctx, model: str, rec_id: int) -> str:
    """URL of one record's form view. The v15 hash route is still honoured by
    the v17+ client, which redirects it to /odoo/<action>/<id>."""
    return f"{ctx.env.base_url}/web#id={rec_id}&model={model}&view_type=form"


def list_url(ctx, model: str, v19_path: str = "") -> str:
    """URL of a model's list view; ``v19_path`` is the v17+ router equivalent
    (the hash router no longer resolves a bare model on v19)."""
    if is_v19(ctx) and v19_path:
        return f"{ctx.env.base_url}{v19_path}"
    return f"{ctx.env.base_url}/web#model={model}&view_type=list"


def screenshot_evidence(ctx, name: str, url: str) -> bool:
    """Attach a rendered-page screenshot as EVIDENCE — never as a verdict.

    The two partially automated UI cases (TC-ART-002, TC-ART-023) assert on
    the served view architecture; the browser shot only documents the render.
    A Playwright/browser problem must therefore not replace those assertions'
    verdict with ERROR, so every failure is logged and reported as False.
    """
    try:
        page = ctx.browser_page()
        LoginPage(page, ctx.adapter).open().login(ctx.env.username,
                                                 ctx.env.password)
        page.goto(url)
        page.wait_for_timeout(4000)
        ctx.screenshot(name)
        return True
    except Exception as exc:  # noqa: BLE001 — evidence, not an assertion
        ctx.log(f"screenshot evidence unavailable ({name}): {exc}")
        return False


# ---------------------------------------------------------------------------
# QA self-pollution exclusion for the DATA_RECONCILIATION tests
# ---------------------------------------------------------------------------
# Why this exists (automation defect, not a product defect): every
# reconciliation count in this suite is a raw SQL count over a whole table,
# and raw SQL counts ARCHIVED rows that the ORM hides.
# framework/qa_fixtures.sweep_products() deliberately archives (active=False)
# any product it cannot unlink — a fixture referenced by a stock move, a
# purchase order or a channel listing can never be removed. The platform's
# own fixtures therefore inflate product_template / product_product, the
# x_categ_ids relation table, stock_quant and stock_valuation_layer
# permanently, and a baseline captured while such leftovers existed is a false
# PASS (observed on TC-DAT-013).
#
# Rule for this suite: every reconciliation query subtracts the QA footprint
# and LOGS raw / qa_excluded / residual, so the exclusion is auditable and
# nothing is hidden. Only the residual goes into a baseline.
#
# 'QA%' covers the framework's own markers ("QA AUTO Internal User",
# "QA AUTO PRODUCT (do not sell)", "QA-AUTO…", "QA Test …").
QA_NAME_PATTERNS = ("FG01%", "FG02%", "FG03%", "FG04%", "QA%")

# The workbook's numeric anchors are a snapshot of the SOURCE production
# database taken on this date. They are preconditions, not assertions about
# the migration — see anchor_or_blocked().
WORKBOOK_ANCHOR_DATE = "2026-08-13"


def _text_expr(ctx, table, column, alias=None):
    """SQL expression yielding a column's text value on both target versions.

    Translatable char/text columns (product_template.name) are plain varchar
    on Odoo 15 and jsonb from Odoo 16 on, so a bare LIKE would silently match
    nothing after the upgrade.
    """
    ref = f"{alias}.{column}" if alias else column
    dtype = ctx.sql.one(
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_name = %s AND column_name = %s", (table, column))
    if dtype == "jsonb":
        return (f"coalesce({ref}->>'en_US', {ref}->>'en_GB', {ref}::text)")
    return ref


def qa_name_pred(ctx, table, column="name", alias=None,
                 patterns=QA_NAME_PATTERNS):
    """Positive SQL predicate: TRUE for rows this platform's fixtures created.

    COALESCE-wrapped so it is never NULL: `NOT (pred)` must be a total
    partition, otherwise NULL-named rows would vanish from both sides of the
    raw/residual split.
    """
    expr = _text_expr(ctx, table, column, alias)
    ors = " OR ".join(f"{expr} LIKE '{p}'" for p in patterns)
    return f"COALESCE({ors}, FALSE)"


def qa_id_pred(column, ids):
    """Positive SQL predicate matching the given QA ids ('FALSE' when none)."""
    if not ids:
        return "FALSE"
    joined = ",".join(str(int(i)) for i in ids)
    return f"COALESCE({column} IN ({joined}), FALSE)"


class QaFootprint:
    """The product rows this platform's own fixtures created — archived ones
    included. Built with raw SQL precisely because the ORM hides the archived
    leftovers that inflate the SQL counts."""

    def __init__(self, ctx):
        self.template_pred = qa_name_pred(ctx, "product_template", "name")
        self.template_ids = [r[0] for r in ctx.sql.rows(
            f"SELECT id FROM product_template WHERE {self.template_pred}")]
        # product.product has no own name column (_inherits delegates it to
        # the template), so QA variants are identified through their template
        joined = qa_name_pred(ctx, "product_template", "name", alias="t")
        self.variant_ids = [r[0] for r in ctx.sql.rows(
            "SELECT p.id FROM product_product p "
            "JOIN product_template t ON t.id = p.product_tmpl_id "
            f"WHERE {joined}")]

    def template_pred_on(self, column="id"):
        return qa_id_pred(column, self.template_ids)

    def variant_pred_on(self, column="id"):
        return qa_id_pred(column, self.variant_ids)

    def log(self, ctx):
        ctx.log(f"QA footprint (archive-inclusive; name markers "
                f"{'/'.join(QA_NAME_PATTERNS)}): "
                f"{len(self.template_ids)} product templates and "
                f"{len(self.variant_ids)} variants were created by this "
                f"platform — excluded from every count below")


def qa_footprint(ctx):
    """Per-test cached footprint (one SQL probe per test execution)."""
    cached = getattr(ctx, "_fg01_qa_footprint", None)
    if cached is None:
        cached = QaFootprint(ctx)
        setattr(ctx, "_fg01_qa_footprint", cached)
    return cached


def qa_metric(ctx, key, table, count_expr, qa_pred, where=""):
    """One reconciliation count, QA fixtures excluded.

    Single table scan returning (raw, qa_excluded, residual); all three are
    logged, the residual is returned — it is the only value a baseline may
    contain.
    """
    tail = f" WHERE {where}" if where else ""
    raw, excluded, residual = ctx.sql.rows(
        f"SELECT count({count_expr}), "
        f"count({count_expr}) FILTER (WHERE {qa_pred}), "
        f"count({count_expr}) FILTER (WHERE NOT ({qa_pred})) "
        f"FROM {table}{tail}")[0]
    ctx.log(f"  {key}: raw={raw} qa_excluded={excluded} residual={residual}")
    return int(residual or 0)


def qa_orm_count(ctx, model, field, exclude_ids):
    """ORM fallback count for fields with no SQL column (m2m, non-stored
    related), made archive-inclusive and QA-excluding so it measures the same
    population as the raw-SQL branch."""
    rpc = ctx.adapter.rpc
    base = [(field, "!=", False), ("active", "in", [True, False])]
    domain = base + ([("id", "not in", list(exclude_ids))]
                     if exclude_ids else [])
    residual = rpc.call(model, "search_count", domain,
                        context={"active_test": False})
    raw = residual if not exclude_ids else rpc.call(
        model, "search_count", base, context={"active_test": False})
    ctx.log(f"  {model}.{field} (ORM): raw={raw} "
            f"qa_excluded={raw - residual} residual={residual}")
    return residual


def anchor_or_blocked(ctx, snapshot, anchors, note):
    """Assert the workbook's numeric anchors — BLOCKED, never FAILED, on a
    mismatch.

    The anchors describe the source production database as it stood on
    WORKBOOK_ANCHOR_DATE. That database keeps growing (measured 2026-08-21:
    the source copy itself holds 69,316 product templates and 14,001 x_medium
    references against the workbook's 69,201 / 13,972), so on a later clone
    the anchors cannot hold even with perfect QA exclusion. That is a
    precondition outside this test's control — exactly what BLOCKED means —
    whereas FAIL would assert a migration/product defect that does not exist.

    Call this AFTER reconcile(): reconcile() asserts anchors passed to it
    *before* persisting the baseline, so an anchor mismatch there would also
    destroy the v15→v19 diff the test actually exists for. Here the baseline
    is already on disk.
    """
    with ctx.step(f"Assert workbook anchor values "
                  f"({WORKBOOK_ANCHOR_DATE} source snapshot)"):
        mismatches = []
        for key, expected in sorted(anchors.items()):
            actual = snapshot.get(key)
            if actual == expected:
                ctx.check(f"anchor {key}", expected=expected, actual=actual)
            else:
                mismatches.append(f"{key}: workbook={expected!r}, "
                                  f"QA-excluded live value={actual!r}")
                ctx.log(f"ANCHOR MISMATCH — {mismatches[-1]}")
        if mismatches:
            ctx.blocked(
                "workbook anchors do not describe this database — "
                + "; ".join(mismatches)
                + f". {note} The clone is not the documented "
                f"{WORKBOOK_ANCHOR_DATE} baseline snapshot, so these anchors "
                "cannot hold; this is a stale precondition, not a migration "
                "defect. The v15 baseline was persisted before this step, so "
                "the v15→v19 reconciliation this TC exists for is unaffected.")


def csv_row_diff(path_a, path_b, label_a="v15", label_b="v19"):
    """Multiset symmetric difference between two CSV exports.

    Returns human-readable diff lines ([] when the row sets are identical).
    Row order is irrelevant; duplicate rows are counted.
    """
    def load(path):
        with open(path, newline="", encoding="utf-8") as fh:
            reader = _csv.reader(fh)
            header = next(reader, None)
            return header, Counter(tuple(row) for row in reader)

    head_a, rows_a = load(path_a)
    head_b, rows_b = load(path_b)
    lines = []
    if head_a != head_b:
        lines.append(f"header differs: {label_a}={head_a} {label_b}={head_b}")
    for row, n in sorted((rows_a - rows_b).items()):
        lines.append(f"-{label_a} only (x{n}): {','.join(row)}")
    for row, n in sorted((rows_b - rows_a).items()):
        lines.append(f"+{label_b} only (x{n}): {','.join(row)}")
    return lines


def gl_stock_balance(ctx, footprint=None):
    """(balance, [account codes]) of the stock valuation accounts.

    This is the TC-DAT-002 cross-check figure TC-DAT-008's expected result
    depends on. Read-only: the accounts are resolved through the ORM (the
    company-dependent property field moved from ir_property to a jsonb column
    across v15→v19, so SQL would not be version-safe), the balance with SQL.
    Lines booked on this platform's own QA products are excluded.
    """
    rpc = ctx.adapter.rpc
    field = "property_stock_valuation_account_id"
    if not rpc.field_exists("product.category", field):
        ctx.log(f"  product.category.{field} absent — no GL cross-check")
        return None, []
    account_ids = set()
    for company_id in rpc.search("res.company", []):
        for rec in rpc.call("product.category", "search_read", [],
                            fields=[field],
                            context={"allowed_company_ids": [company_id],
                                     "company_id": company_id}):
            account = m2o_id(rec.get(field))
            if account:
                account_ids.add(account)
    if not account_ids:
        ctx.log("  no stock valuation account configured — no GL cross-check")
        return None, []
    codes = sorted(str(rec.get("code") or rec["id"]) for rec in
                   rpc.read("account.account", sorted(account_ids), ["code"]))
    ids = ",".join(str(int(i)) for i in sorted(account_ids))
    where = f"m.state = 'posted' AND l.account_id IN ({ids})"
    raw = ctx.sql.one("SELECT round(sum(l.balance),2) FROM account_move_line l "
                      "JOIN account_move m ON m.id = l.move_id "
                      f"WHERE {where}")
    if footprint is not None:
        where += f" AND NOT ({footprint.variant_pred_on('l.product_id')})"
    balance = ctx.sql.one(
        "SELECT round(sum(l.balance),2) FROM account_move_line l "
        "JOIN account_move m ON m.id = l.move_id "
        f"WHERE {where}")
    ctx.log(f"  GL stock accounts {codes}: raw balance={raw} "
            f"residual balance={balance}")
    return balance, codes
