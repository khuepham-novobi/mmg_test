# QA Platform — Current Architecture

Updated 2026-08-18. Scope of this document: `qa-platform/odoo-regression` as it
exists after the FG-01→FG-14 foundation work. Application source
(`psus-medicine-man-gallery`, Odoo core) is untouched by this platform.

## 1. Overview

```
Web UI (frontend/, static SPA, no build step)
   │  REST + Server-Sent Events
FastAPI backend (backend/app.py)
   ├── test-case registry  ── data/test_registry.json ◄── scripts/sync_registry.py ◄── Excel workbook (READ-ONLY source of truth)
   ├── execution engine (backend/runner.py, worker threads)
   └── results store — SQLite WAL (backend/store.py → data/results.db)
        │
tests/ (@test_case registry)  →  framework/ (context: steps, assertions,
        │                          artifacts, logs, Playwright lifecycle)
pages/ (Playwright page objects, version-agnostic)
        │
adapters/base.py  ◄─►  adapters/odoo15.py / adapters/odoo19.py
(XML-RPC business ops + per-version selector maps / URL schemes / model diffs)
        │
   Odoo 15 (localhost:8076)          Odoo 19 (localhost:8019)
```

## 2. Execution model

| Concept | Implementation | Notes |
|---|---|---|
| **TestCase** | `test_cases` table (SQLite), one row per workbook TC | Immutable `test_case_id` (e.g. `TC-SAL-017`). Populated from `data/test_registry.json` at backend startup; regenerated from the Excel workbook by `scripts/sync_registry.py`. `expected_result`, `steps`, `preconditions`, `title` are **verbatim from Excel and never modified by the platform**. |
| **TestExecution** | `results` table, one row per test per run | Stores: execution_id (`RES-…`), run_id, platform test id, status, started/finished/duration, error, failed_step, expected, actual, skip_reason, **failure_class**, traceability (workbook `tc_ids`). Children: `steps`, `assertions`, `artifacts` (screenshots, Playwright traces, execution log, video). Environment + Odoo version come from the parent run. |
| **TestRun** | `runs` table (`RUN-…`) | environment (odoo15/odoo19), mode (single/compare), group_id for 15↔19 comparisons, counters, status. `events` table is the append-only run log driving SSE live view + replay. |

### Registry fields (Step 4 minimum + extensions)

`test_case_id, feature_id, feature_name, title, description (user story),
preconditions, steps, expected_result, priority, test_type, role, modules,
suite, execution_phase, v19_watch, automation_wave, automation_approach,
automation_type, automation_status, automated_test_ids, related_test_ids,
source_workbook, source_sheet, source_row, test_execution_row`.

`v15_status`, `v19_status` and `last_execution_id` are **computed** on read by
joining the latest persisted execution per environment (via the traceability
`tc_ids` on each result) — they are never stored, so they cannot drift from
the evidence.

### Statuses

| Layer | Values |
|---|---|
| Execution (DB, internal) | QUEUED, RUNNING, PASSED, FAILED, ERROR, SKIPPED, BLOCKED |
| Execution (API/UI, canonical) | PASS, FAIL, BLOCKED, ERROR, SKIPPED, NOT_RUN, RUNNING |
| Test case per environment | canonical execution status, or NOT_RUN (automated, no run yet), NOT_IMPLEMENTED (automatable, no automation yet), MANUAL (not automatable) |
| failure_class | ASSERTION (product-defect candidate), AUTOMATION_ERROR, ENVIRONMENT, BLOCKED, NONE |

`ctx.skip(reason)` → SKIPPED; `ctx.blocked(reason)` → BLOCKED (precondition
outside the test's control); `ctx.check(...)` mismatch → FAILED/ASSERTION;
any other exception → ERROR (classified ENVIRONMENT when connection-level).

## 3. Backend API

| Endpoint | Purpose |
|---|---|
| `GET /api/features` | FG-01→FG-14 rollup: totals, priorities, automation types/statuses, coverage %, v15/v19 status counts (`?all=true` adds FG-15..FG-20) |
| `GET /api/testcases?feature=FG-xx` | Registry list with computed v15/v19 status + last_execution_id |
| `GET /api/testcases/{tc_id}` | Full test-case detail + complete execution history |
| `GET /api/tests` | Registered automated platform tests (`@test_case`) + latest status per environment |
| `POST /api/runs` · `GET /api/runs[/{id}]` · `POST /api/runs/{id}/cancel` | Run lifecycle (environment: odoo15 / odoo19 / both=compare) |
| `GET /api/runs/{id}/events` | SSE live stream with full replay |
| `GET /api/results/{id}` | Execution detail: steps, assertions, artifacts, log |
| `GET /api/artifacts/{id}` | Evidence download (screenshot/trace/log/video) |
| `GET /api/compare/{group}` | 15↔19 matrix + regression flags |

## 4. Web UI (frontend/, hash-routed SPA)

| Route | View |
|---|---|
| `#/` | **Feature dashboard**: FG-01→FG-14, test count per feature, priorities, automation coverage bar, v15/v19 PASS/FAIL/BLOCKED/ERROR rollups |
| `#/feature/FG-xx` | Test cases of one group with automation type/status and v15/v19 chips |
| `#/testcase/TC-…` | Full registry record (verbatim steps/expected), automation info, execution history with evidence links |
| `#/tests` | Automated test runner (select tests, pick environment, run) |
| `#/run/RUN-…` | Live execution: counters, progress, per-step SSE log |
| `#/result/RES-…` | Execution detail: steps, assertions, screenshots, trace, log, Excel traceability |
| `#/compare/CMP-…` | Odoo 15 ↔ 19 side-by-side with ⚠ REGRESSION flags |
| `#/runs` | Run history |

## 5. Scripts

| Script | Purpose |
|---|---|
| `scripts/sync_registry.py` | Excel → `data/test_registry.json` (read-only on the workbook; deterministic automation classification; fails on duplicate TC ids) |
| `scripts/gen_inventory_doc.py` | Registry JSON → `docs/TEST_INVENTORY.md` |
| `scripts/validate_env.py` | Environment + platform validation → `data/env_validation.json` (basis of `docs/ENVIRONMENT_STATUS.md`) |

## 6. Evidence & artifacts

Per execution, under `artifacts/<RUN>/<TEST>/`: `execution.log` (always),
failure screenshot (always on FAIL/ERROR/BLOCKED), success screenshot
(`SCREENSHOT_ON_SUCCESS=true`), Playwright `trace.zip`
(`TRACE=retain-on-failure`), optional video. All are registered in the
`artifacts` table and served via `/api/artifacts/{id}`.

## 7. Safety properties

- The Excel workbook is **never written**; sync is one-way into the platform.
- Expected results are verbatim copies; executions record `expected` vs
  `actual` separately and never touch the registry row.
- The runner only creates namespaced QA data (`QA-AUTO` marker) through the
  same interfaces a user would use; it never deletes or modifies existing
  business records.
- Production and `staging_19` are out of bounds; targets are local instances
  configured in `.env` / `config/environments.yaml`.

## 8. Known gaps / next steps

- Only 5 automated platform tests exist (3 workbook TCs covered). Wave-1
  (50 PLANNED TCs) is the next automation batch.
- `PYTHON_UNIT` / `TOUR` / `HTTP_CASE` classifications run inside the Odoo
  test runner; the platform currently orchestrates UI (Playwright) + API
  (XML-RPC) kinds. An `odoo-bin --test-tags` adapter is future work.
- v15 executions in the DB predate this work and errored because the local
  Odoo 15 was down (see `docs/ENVIRONMENT_STATUS.md`).
