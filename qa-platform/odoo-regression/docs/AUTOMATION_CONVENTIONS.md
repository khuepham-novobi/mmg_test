# FG Suite Automation Conventions (FG-01 … FG-14)

Binding conventions for every FG test suite in this platform. FG-01
(`tests/fg01/`) is the golden reference implementation — read it first.

## Hard rules

1. **Write only under `qa-platform/odoo-regression/tests/fgXX/`.** Never
   touch application source (`psus-medicine-man-gallery`, Odoo core),
   framework/backend/frontend files, other suites, or the Excel workbook.
2. **Excel expected results are immutable.** Assertions implement the
   workbook's expected result — never weakened, never inverted. A test that
   is expected to FAIL on v15 (because the expectation describes the v19
   target state) stays failing; that baseline FAIL classifies as FIXED when
   v19 passes.
3. **Never modify pre-existing business records.** Fixtures are created
   namespaced (marker prefix `FGXX`), swept at test start (idempotence) and
   cleaned in a `finally` step. Live-data checks are read-only.
4. **Never trigger outbound integrations.** Connector instances are
   deactivated in the QA clone: tests must not reactivate instances, enable
   crons, configure credentials, or call export/sync methods that hit
   external APIs. A test whose essence requires an external system calls
   `ctx.blocked("requires <X> sandbox — <detail>")` up front.
5. **Deterministic and repeatable.** Same result on every rerun; no
   time-dependent values, no dependence on other tests' fixtures, no
   reliance on record ids. Scope searches by marker so live data can't leak
   into "exactly N records" assertions (document such adaptations in the
   test docstring).

## Test shape

```python
from framework.registry import test_case
from framework.fg_common import make_trace, m2o_id, reconcile, form_arch, http_session
from framework.qa_fixtures import sweep_products, sweep_model, ensure_qa_user, rpc_as_qa_user

trace = make_trace("FG-03 Sales Order Processing & Pricing")

@test_case(
    id="TEST-FG03-SAL-006",            # TEST-FG<nn>-<workbook TC suffix>
    name="<workbook TC title>",
    workflow="FG-03",                   # exactly the feature group id
    workflow_name="Sales & Pricing",
    module="mmg_automated_action",     # workbook Module(s) column
    priority="P0",                      # workbook priority
    kind="API",                         # API | DATA | HYBRID
    order=306,                          # FG number × 100 + sequence
    description="one-line what is proven",
    traceability=trace("TC-SAL-006"))
def test_sal_006(ctx):
    rpc = ctx.adapter.rpc
    with ctx.step("..."):
        ctx.check("assertion name", expected=..., actual=...)
```

- `ctx.step(name)` per workbook step; `ctx.check(name, expected, actual)`
  records the assertion (raises on mismatch → FAILED). `ctx.check_true`,
  `ctx.skip(reason)` (SKIPPED), `ctx.blocked(reason)` (BLOCKED).
- `ctx.adapter.rpc` — XML-RPC: `search/search_read/read/create/write/unlink/
  read_group/call(model, method, *args, **kw)/ref(xmlid)/field_exists/
  model_exists`. m2o values read back as `[id, name]` → use `m2o_id()`.
- Each RPC call commits its own transaction → `cr.precommit` hooks fire per
  call; no `precommit.run()` needed. Cleanup must therefore always run
  (`finally:`).
- `ctx.sql` — read-only PostgreSQL (raises BLOCKED when unconfigured):
  `.one(q)`, `.rows(q)`, `.to_csv(q, path)`, `.column_exists(table, col)`.
- `reconcile(ctx, "TC-…", capture, anchors=...)` — DATA_RECONCILIATION
  pattern: v15 captures + persists baseline, v19 diffs against it.
- Errors: never raise bare AssertionError; let `ctx.check` fail, or wrap an
  expected RPC failure with try/except OdooRPCError and `ctx.check` the
  outcome, so the platform records expected/actual.

## Version-dependent behavior

- `ctx.env.version` is "15" or "19". The workbook's own steps split into
  "on the v15 clone…" vs "on v19…" — mirror that split; never skip an
  assertion just because it will fail on v15.
- v15 method/view differences go through `ctx.adapter` /
  `framework.fg_common` helpers (e.g. `form_arch`), never `if version`
  scattered in test bodies for UI selectors.

## Feasibility policy (this phase)

- Implement fully: everything ORM/SQL/HTTP-local against the v15 clone.
- Blocked stub (implement the test as `ctx.blocked(reason)` after its
  precondition probe): TCs whose essence needs an external sandbox
  (Shopify/Magento/AvaTax/queue-job runner) — P0/P1 only, with a precise
  reason string.
- Leave unimplemented (registry reports NOT_IMPLEMENTED): the rest.
- Per FG, record the decision per TC in
  `reports/data/fgXX_feasibility.json`:
  `{"TC-…": {"decision": "implemented|blocked_stub|not_implemented",
             "reason": "…", "test_id": "TEST-…"}}`.

## Environment facts (execution target)

- Odoo 15 = `mmg_qa15`, a neutralized production clone: 69,201 products,
  live catalogue/order/accounting data; crons OFF, mail OFF, Magento and
  e-commerce channel instances INACTIVE; queue-job runner not loaded.
- Odoo 19 does not exist locally yet → v19 runs are BLOCKED by the runner
  preflight automatically; write tests version-aware anyway.
- The four local base_automation records ([PZE] Calc Dollar Discount,
  [PZE] Inv Value, both Legal Date Transfers) are ACTIVE.
