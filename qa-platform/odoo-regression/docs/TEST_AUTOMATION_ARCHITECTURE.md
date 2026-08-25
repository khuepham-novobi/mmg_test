# Test Automation Architecture

How a test case in the Excel workbook becomes a **reusable automated test**
that the QA platform can execute, on demand, against Odoo 15 or Odoo 19, any
number of times — today, tomorrow, and after every Claude session has ended.

Nothing in this pipeline depends on Claude, an agent, or a chat session. The
only runtime actors are: the **QA platform server** (FastAPI + static SPA),
the **test scripts on disk**, and the **target Odoo instance**.

## 0. The flow

```
Excel workbook (source of truth, read-only)
   │   scripts/sync_registry.py
   ▼
data/test_registry.json  ──loaded at server start──►  SQLite table test_cases
   │                                                    (Test Case Definition)
   │  traceability: tc_ids
   ▼
tests/fgNN/test_*.py  @test_case(...)      ◄── the reusable Automated Test Script
   │   framework/registry.py:discover()
   ▼
Registered Test (in-memory registry, rebuilt from disk on every start/reload)
   │
   ▼
QA Web UI  ──[RUN]──►  POST /api/runs  ──►  RunExecutor thread
                                              │  creates TestRun (RUN-…) and
                                              │  one TestExecution (RES-…) per test
                                              ▼
                                        script executes against the chosen env
                                              │  steps, assertions, logs,
                                              │  screenshots, traces, baselines
                                              ▼
                                    SQLite (data/results.db) + artifacts/
                                              │
                                              ▼
                              Web UI: live SSE, then permanent history
```

## 1. Where test scripts live

```
qa-platform/odoo-regression/
├── tests/
│   ├── fg01/            FG-01 golden suite (35 tests)
│   │   ├── common.py    suite fixtures/markers
│   │   └── test_*.py    @test_case functions
│   ├── fg02/            FG-02 suite (12 tests)
│   ├── fg04/            FG-04 suite (16 tests)
│   └── sales/           earlier MVP smoke/sales tests (5)
├── framework/           registry, execution context, shared FG helpers
├── adapters/            odoo15 / odoo19 differences (JSON-RPC, selectors, URLs)
├── pages/               Playwright page objects (UI tests)
├── scripts/             sync_registry.py, validate_env.py, gen_reports.py
├── data/results.db      execution history (SQLite, WAL)
├── data/test_registry.json   workbook-derived test-case definitions
├── data/baselines/      v15 baselines for DATA_RECONCILIATION comparisons
└── artifacts/<RUN>/<TEST>/    evidence: logs, screenshots, traces, CSVs
```

Test scripts are **ordinary files committed in the repo**. They are not
generated at run time and not held in any session state. `wip/` holds
partially built suites (FG-03, FG-05, FG-07, FG-08, FG-13, FG-14) that are
deliberately *not* registered yet — moving a folder from `wip/` to `tests/`
is all it takes to register it.

## 2. How a Test Case maps to a script

Two separate objects, joined by the immutable workbook id:

| | Test Case Definition | Automated Test Script |
|---|---|---|
| What | the workbook's intent | the executable automation |
| Id | `TC-BLK-001` (immutable, from Excel) | `TEST-FG04-BLK-001` |
| Lives in | `test_cases` table, from `data/test_registry.json` | `tests/fg04/test_assign_customer_taxes.py` |
| Owns | title, preconditions, steps, **expected_result (verbatim)**, priority | fixtures, steps, assertions, cleanup |
| Changed by | editing the Excel workbook, then re-running the sync | editing the script |

The join is declared **in the script**, via the decorator:

```python
@test_case(
    id="TEST-FG04-BLK-001",
    name="Assign Customer Taxes to selected templates",
    workflow="FG-04",                      # ← feature group
    priority="P0", kind="API", order=400,
    traceability=trace("TC-BLK-001"))      # ← workbook test case id
def test_blk_001(ctx):
    ...
```

`scripts/sync_registry.py` reads those traceability blocks back out of the
live registry and stores the mapping on each test case as
`automated_test_ids`, which is what drives the UI's RUN button and the
"automated / automatable" coverage numbers. One workbook TC may be covered by
several scripts, and one script may cover several TCs.

## 3. How the web UI invokes the script

Every RUN button in the UI performs the same single call:

```
POST /api/runs
{ "environment": "odoo15" | "odoo19" | "both",
  "test_ids":      ["TEST-FG04-BLK-001"],   // one script
  "test_case_ids": ["TC-BLK-001"],          // by workbook id
  "features":      ["FG-04"],               // a whole feature group
  "scope":         "in_scope",              // FG-01 → FG-14
  "label":         "FG-04 suite" }
```

Any combination resolves through `_resolve_selection()` to a list of
registered tests. The backend then starts a `RunExecutor` worker thread which
calls each registered function with a fresh `TestContext`. The UI never sends
code, never sends a file path, and cannot execute anything that is not
registered.

Buttons available:

- **Feature dashboard** (`#/`) — `▶ RUN FG-01 → FG-14` and a `▶ RUN` per feature row.
- **Feature page** (`#/feature/FG-04`) — `▶ RUN FG-04`, plus per test case `▶ RUN` and `HISTORY`.
- **Test case page** (`#/testcase/TC-BLK-001`) — `▶ RUN TC-BLK-001` and the full execution history.
- **Automated tests page** (`#/tests`) — per script RUN, RUN SELECTED, RUN ALL.

New or edited scripts are picked up by restarting the server, or without a
restart via `POST /api/registry/reload` (re-imports `tests/` from disk and
re-syncs the registry).

## 4. How execution ids are created

- **TestRun** — one per RUN click: `RUN-` + 8 hex chars, created by
  `Store.create_run()` with environment, mode (`single` / `compare`),
  comparison `group_id` (`CMP-…`) when running both versions, label, start
  time and counters.
- **TestExecution** — one per test per run: `RES-` + 10 hex chars, created by
  `Store.create_result()` *before* execution starts (so the UI can show the
  queued list), then updated with status, timings and outcome.

Each TestExecution row stores: `run_id`, platform `test_id`, workbook
traceability, status, `started_at` / `finished_at` / `duration_ms`,
`expected`, `actual`, `error`, `failed_step`, `skip_reason` and
`failure_class` (`ASSERTION` / `AUTOMATION_ERROR` / `ENVIRONMENT` /
`BLOCKED` / `INTERRUPTED` / `NONE`), plus child rows for **steps**,
**assertions** (expected vs actual per assertion), and **artifacts**.

An execution is never the test: deleting `data/results.db` loses history but
not a single test; deleting a script loses the automation but not its
history.

## 5. Where history is stored

- `data/results.db` (SQLite, WAL): `runs`, `results`, `steps`, `assertions`,
  `artifacts`, `events` (append-only run log powering SSE replay), plus the
  definition tables `test_cases` / `feature_groups`.
- `artifacts/<RUN-ID>/<TEST-ID>/`: `execution.log` always, failure/success
  screenshots, Playwright `trace.zip`, reconciliation CSVs — each registered
  in the `artifacts` table and served by `GET /api/artifacts/{id}`.
- `data/baselines/`: v15 snapshots for cross-version data reconciliation.

History is unbounded and append-only: each rerun adds a TestRun and new
TestExecutions, so a test case page shows every run ever made, per
environment. If the server is killed mid-run, the next start calls
`Store.reconcile_orphans()`, which closes the abandoned executions as
`ERROR / INTERRUPTED` rather than leaving them RUNNING forever.

## 5b. What source code is actually under test

The test scripts contain **no application code and no copy of it**. They drive
a *running Odoo server* over JSON-RPC, so the code under test is whatever that
server process loaded — never something this repo vendors.

For the v15 target, that is decided by `D:\Projects\mmg\mmg.conf`
(`addons_path`, in load order):

| # | Path | Contains |
|---|---|---|
| 1 | `D:\Projects\odoo15\enterprise` | Odoo 15 Enterprise core |
| 2 | `D:\Projects\odoo15\addons` | Odoo 15 Community core |
| 3 | `D:\Projects\mmg\psus-medicine-man-gallery` | the MMG custom modules — `mmg_stock`, `mmg_sale`, `mmg_account`, `mmg_automated_action`, `mmg_report`, the FG-04 wizards, `report_py3o`, the AvaTax OCA modules, the Emipro Magento stack |
| 4 | `…\psus-medicine-man-gallery\novobi-omni-addons` | the omnichannel / e-commerce connector layer |

…plus the **database**, which decides which of those modules are actually
installed and at which version. Verified on `mmg_qa15`: `mmg_stock` 15.0.1,
`mmg_sale` 15.0.0, `mmg_account` 15.0.0, `mmg_automated_action` 15.0.1.0,
`mmg_report` 15.0.1, `report_py3o` 15.0.1, and the four FG-04 wizard modules
(`mmg_sale_assign_customer_taxes`, `mmg_sale_assign_fiscal_position`,
`mmg_assign_product_category`, `mmg_assign_website_extra_category`,
`mmg_sale_update_customer_type`) at 15.0.1 — all `installed`.

Consequences worth being explicit about:

- A v15 run measures the **v15 code baseline**, not the v19 port. The
  workbook's expected results frequently describe the v19 target state, so a
  v15 FAIL there is the documented baseline (it becomes `FIXED` when v19
  passes) — never something to "fix" by weakening an assertion.
- The v19 module source (`mmg_19-custom/…`, referenced throughout the
  workbook) is **not present on this machine**, and no local Odoo 19 instance
  exists. That is exactly why every v19 execution records
  `BLOCKED / ENVIRONMENT`.
- Changing what is under test means changing the *server's* addons path or
  database — never the test scripts. QA does not edit `mmg.conf`; it selects a
  database and points the runner at the instance.

## 6. How v15 / v19 environments are selected

`config/environments.yaml` declares both targets; all values come from `.env`
(never committed, never printed):

```yaml
odoo15: {version: "15", base_url: ${ODOO15_URL}, db: ${ODOO15_DB}, …,
         pg_host: ${ODOO15_PG_HOST}, …}
odoo19: {version: "19", base_url: ${ODOO19_URL}, db: ${ODOO19_DB}, …}
```

The environment is chosen **per run**, in the UI's TARGET selector (remembered
across views) or by the `environment` field of the API call — `odoo15`,
`odoo19`, or `both`. The same script runs against either version:
version-specific behavior lives in `adapters/odoo15.py` / `adapters/odoo19.py`
and in `ctx.env.version` branches that mirror the workbook's own
"on the v15 clone… / on v19…" steps.

`both` creates two TestRuns sharing a `CMP-…` group, executed back to back,
and `GET /api/compare/{group_id}` classifies each test case:
`SAME_BEHAVIOR`, `REGRESSION_CANDIDATE` (never called a regression before
failure triage), `FIXED`, `SAME_FAILURE`, `BLOCKED`, `NOT_COMPARED`.

Before executing, every run performs a **preflight** against the target. If
the instance is unreachable, all its executions are recorded `BLOCKED` with
`failure_class=ENVIRONMENT` — never a misleading FAIL.

## 7. How tests can be rerun indefinitely

Reruns are a first-class requirement, enforced by convention in every suite
(`docs/AUTOMATION_CONVENTIONS.md`):

1. **Namespaced fixtures** — every record a test creates is marked (`FG01…`,
   `FG04…`, QA barcodes in the `9001…` range).
2. **Sweep before, clean after** — each test deletes its own leftovers at the
   start and cleans up in a `finally` step, so run *n+1* starts from the same
   state as run *n*.
3. **Pre-existing business records are never modified** — live-data checks are
   read-only; reconciliation tests only `SELECT`.
4. **Config changes are snapshotted and restored** in `finally`.
5. **No cross-test dependencies and no reliance on record ids** — marker-scoped
   searches keep "exactly N records" assertions deterministic against a
   69,201-product production clone.
6. **Idempotent target** — v15 runs execute against `mmg_qa15`, a neutralized
   clone (crons off, mail off, connector instances inactive). The original
   `mmg` database is never written.

The same run started from the UI today, tomorrow, or from CI produces a new
execution id and comparable results.

## 8. Operating the platform (no Claude required)

```bash
cd D:/Projects/mmg/qa-platform/odoo-regression
venv/Scripts/python.exe run_server.py      # http://localhost:8000
```

The Odoo 15 target must be running (it is a separate process):

```bash
D:/Projects/mmg/venv/Scripts/python.exe D:/Projects/odoo15/odoo-bin -c D:/Projects/mmg/mmg.conf -d mmg_qa15 --db-filter=^mmg_qa15$ --max-cron-threads=0
```

Then: open the page, pick a TARGET, click RUN on a suite, a feature, or a
single test case. `scripts/validate_env.py` re-checks both environments;
`scripts/gen_reports.py` regenerates the markdown reports from the same
persisted rows the UI reads.
