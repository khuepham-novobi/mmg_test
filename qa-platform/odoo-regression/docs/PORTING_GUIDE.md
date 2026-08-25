# Porting Guide — reproduce this QA platform in another project

How to get from *"an Excel workbook full of test cases"* to *"a web page with
RUN buttons per test case"* in a new project, reusing everything built here —
plus an honest analysis of where the time went in this project and how the
new project avoids it.

The contract this guide assumes (same as this project ended up with):
**the AI writes the test code and documents; the human runs the tests.**

---

## 1. What is reusable as-is (copy, don't rebuild)

The platform core is application-agnostic — nothing in it knows about MMG.
Copy these folders unchanged (~4,100 lines total):

| Folder | Lines | What it is |
|---|---:|---|
| `framework/` | ~650 | test registry (`@test_case`), execution context (steps/assertions/evidence/Playwright), baselines, SQL tool, shared FG helpers, QA fixtures |
| `backend/` | ~1,130 | FastAPI app (runs/executions/registry/features API, SSE), runner (preflight, BLOCKED, failure classes, orphan reconciliation, one-run-per-target guard), SQLite store |
| `frontend/` | ~790 | the SPA: feature dashboard → feature page → test-case page, RUN buttons at suite/feature/TC level, live run view, evidence view, 15↔19 compare |
| `adapters/` | ~500 | version-agnostic Odoo access over `/web/dataset/call_kw` + per-version subclasses |
| `pages/` | ~220 | Playwright page objects with candidate-selector resolution |
| `scripts/` | ~790 | `sync_registry.py` (Excel→JSON), `gen_inventory_doc.py`, `gen_reports.py`, `validate_env.py`, `start/stop_platform.ps1` |

Also copy verbatim: `docs/AUTOMATION_CONVENTIONS.md` (the binding rules),
`docs/TEST_AUTOMATION_ARCHITECTURE.md` (how the pieces connect),
`docs/GETTING_STARTED.md` (setup), `config/environments.yaml`,
`config/local.yaml.example`, `requirements.txt`, `run_server.py`,
`.gitignore`.

Do **not** copy: `tests/fg*` (project-specific), `data/` (results/registry are
per-project), `artifacts/`, `venv/`, `wip/`.

## 2. What must be adapted per project (small, bounded)

1. **`scripts/sync_registry.py` header** — workbook filename, sheet names,
   column map, the in-scope group list, and the `_APPROACH_MAP` that turns
   your workbook's "automation approach" wording into the automation-type
   enum. ~30 lines.
2. **`adapters/odooXX.py`** — one subclass per target version: storable
   product values, cancel-flow quirks, URL schemes, UI selector map. Copy the
   existing 15/19 pair and adjust. ~80 lines each.
3. **`config/local.yaml`** — the machine's URLs/DBs/credentials (gitignored).
4. **`scripts/start_platform.ps1` parameters** — odoo-bin path, conf path,
   QA database name.

## 3. The Excel contract

`sync_registry.py` needs one sheet (here "Automation Export") with one row
per test case and these columns — rename in the script if yours differ:

```
tc_id (IMMUTABLE unique id)   group_id (FG-01…)     group_name
seq   title   user_story      feature_ref  feature_name  feature_category
priority  test_type  role     modules
preconditions  steps  expected_result      <- copied VERBATIM, never edited
v19_watch  suite  suite_name  execution_phase  related_features
automation_wave  automation_approach       source_notes
```

Plus a "Feature Groups Overview" sheet (`Group ID`, `Feature Group`,
`Business Purpose`, `Key Modules`, `Primary Roles`) for the dashboard cards.

Two invariants the whole design leans on:
* `tc_id` is immutable — every script, execution and report joins on it;
* `expected_result` is the workbook's, verbatim — the platform never edits
  it, and no assertion may be weakened to make a baseline version green.

## 4. Bring-up order for the new project

```
1. Copy the platform (section 1) + adapt (section 2).
2. python -m venv venv && pip install -r requirements.txt
   && python -m playwright install chromium            (one-time, ~10 min)
3. Create the QA database CLONE and neutralize it:
     CREATE DATABASE <x>_qa TEMPLATE <prod_copy> STRATEGY FILE_COPY;
     UPDATE ir_cron SET active=false;  UPDATE ir_mail_server SET active=false;
     UPDATE fetchmail_server SET active=false;
     -- deactivate every connector instance table your project has
   NEVER point the runner at the production copy itself: suites write
   namespaced fixtures, and starting a server on it can fire real
   connector/mail traffic.                              (~30 min for 11 GB)
4. python scripts/sync_registry.py     -> data/test_registry.json
5. python scripts/validate_env.py      -> READY / NOT READY per target
6. scripts/start_platform.ps1          -> http://127.0.0.1:8000 shows every
   feature group with counts BEFORE any test code exists (all NOT_IMPLEMENTED)
7. Generate test suites per feature group (section 5).
8. Human runs from the UI; AI reads results from data/results.db and fixes
   its own automation defects only — never the expected results.
```

Steps 1–6 are a day of mostly waiting (installs, clone copy). After step 6
the platform is fully operational with zero tests written.

## 5. Generating a suite (the part you asked about)

One feature group = one generation unit. Per FG, the AI must produce:

```
tests/fgNN/__init__.py
tests/fgNN/common.py            marker, per-execution fixture token, sweeps
tests/fgNN/test_*.py            @test_case functions, 1+ per workbook TC
reports/data/fgNN_feasibility.json   every TC: implemented|blocked_stub|not_implemented + reason
docs/FG-NN_AUTOMATION_PLAN.md   per-TC table: fixtures, assertions, EXPECTED
                                baseline OUTCOME, evidence
```

and finish with the compile check (imports only, executes nothing):

```
venv/Scripts/python.exe -c "from framework import registry; print(len(registry.discover()))"
```

The generation brief that works (distilled from what eventually produced
clean suites here — give this to the AI verbatim, per FG):

> Read `docs/AUTOMATION_CONVENTIONS.md`, one reference suite
> (`tests/fg04/`), and your FG's rows in `data/test_registry.json`.
> Verify every model/field/method you assert against the real application
> source before writing the assertion. Rules: per-execution fixture token
> (`fx()`) on every fixture name and every counted/matched value; cleanup in
> `finally` that can never raise; mismatch dicts asserted once, never
> assertion loops; no version branches in test bodies; snapshot+restore any
> config you flip; `ctx.blocked(<precise reason>)` for anything needing an
> absent external system, after asserting its offline half; the workbook is
> immutable — a baseline-version FAIL whose expectation describes the target
> version is correct, document it in the docstring
> ("EXPECTED vNN OUTCOME: …"). Write files and compile-check only — never
> start a server, run a suite, or touch a database.

## 6. Where the time actually went in THIS project (the bottleneck analysis)

Honest accounting. **Writing test code was never the bottleneck** — each
suite's code took roughly 20–35 agent-minutes to write. The elapsed days came
from five other places:

| # | Time sink | Share (rough) | One-time or avoidable? |
|---|---|---|---|
| 1 | **Building the platform itself** — registry, runner, execution model, UI, reports | ~1 session | One-time. You copy it now; cost ≈ 0 in the new project. |
| 2 | **Environment forensics** — cloning 11 GB, cron/mail/connector neutralization, a corrupt clone that had to be dropped and re-cloned, servers dying with sessions | large | Mostly one-time; the corruption was bad luck. The clone recipe + launcher scripts now exist. |
| 3 | **Execution-and-debug loops that I ran** — FG-01 alone was executed ~6 times at 15–25 min per run while diagnosing failures | the single largest controllable sink | **Yes — this is what your "I run it myself" contract removes.** |
| 4 | **Harness lessons learned the hard way** — three defects that each forced a rerun-and-rework cycle across already-written suites: (a) the RPC transport (`/jsonrpc` silently drops `cr.precommit` writes; the web endpoint doesn't), (b) fixture determinism on a live clone (archived leftovers inflate counts → the per-execution token), (c) cleanup exceptions replacing test verdicts | large | One-time. All three are now baked into `adapters/`, the conventions doc, and the reference suites. The new project inherits them for free. |
| 5 | **Multi-agent audits + session/usage-limit interruptions** — several agent fleets died mid-flight on usage limits and had to be relaunched; deep audits re-verified everything against source | moderate | Partially avoidable: keep ONE audit pass, generate during hours with headroom, and resumable workflows mitigate the rest. |

The key insight for the new project: items 1, 2 and 4 were the *cost of
discovering the right design*. That design is now written down. What remains
per suite is item 3 — and you are taking that on yourself — plus the
irreducible core of item 5 (one review pass).

## 7. The "write-only" contract, stated precisely

**AI does:** read workbook rows + application source → write suite files +
feasibility JSON + plan doc → compile-check → hand over. Per FG this is
20–40 minutes when the reference suite and conventions exist. No servers, no
runs, no databases.

**Human does:** click RUN in the UI (or POST `/api/runs`), read the results.

**The one honest caveat:** code that has never executed contains automation
bugs — this project's first FG-01 run had 12 errors, all mine (marshalling,
double-wrapped domains), none the product's. Static checks (compile + lint +
review) catch many but not all. So budget **one fix round-trip per suite**:
your first run is the validation run; the platform persists every failure
with step, error, expected/actual and evidence in `data/results.db`, so
handing results back is just "look at RUN-XXXX" — the AI reads the DB
directly and fixes only `AUTOMATION_ERROR`-class findings, never the
expected results. The failure-class field tells you at a glance which
failures are the AI's problem (`AUTOMATION_ERROR`), the environment's
(`ENVIRONMENT`/`BLOCKED`), or a real product finding (`ASSERTION`).

## 8. Realistic budget for the new project

| Phase | Elapsed |
|---|---|
| Copy + adapt platform, venv, clone DB, registry, validate | ~half a day, mostly waiting |
| Generate suites, per feature group | 20–40 min each; groups are independent, so parallel generation is bounded by review, not writing |
| Your first run per suite + one AI fix round-trip | your run time + ~15 min of fixes |
| Reports | `python scripts/gen_reports.py`, seconds |
