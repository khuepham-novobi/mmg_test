# Odoo Regression Test Runner — MVP

A real, executable cross-version test platform for the MMG Odoo 15 → 19
migration. One test architecture, two targets: your local **Odoo 15** and
**Odoo 19**. Web UI to pick tests, watch live execution, drill into steps /
assertions / screenshots, and compare 15 ↔ 19 side by side.

Every test traces back to the Excel knowledge base
(`MMG_v19_Test_Cases_Grouped_by_Feature_v3.0.xlsx`) via workbook TC ids.
The full workbook (FG-01…FG-20, 383 test cases) is synced read-only into a
test-case registry (`scripts/sync_registry.py` → `data/test_registry.json` →
SQLite `test_cases`); the dashboard landing page shows the FG-01→FG-14 scope
(303 test cases) with automation coverage and per-version execution status.
See `docs/TEST_INVENTORY.md`, `docs/CURRENT_ARCHITECTURE.md` and
`docs/ENVIRONMENT_STATUS.md`.

---

**Architecture:** see `docs/TEST_AUTOMATION_ARCHITECTURE.md` — how a workbook
test case becomes a registered, rerunnable automated test, where execution
history lives, and how the UI's RUN buttons invoke it. Test scripts live in
`tests/fgNN/` and persist in the repo; executions (`RUN-…` / `RES-…`) persist
in `data/results.db` with evidence under `artifacts/`.

## 1. Quick start (Windows)

**Already set up?** Two commands, then open http://127.0.0.1:8000:

```powershell
cd D:\Projects\mmg\qa-platform\odoo-regression
powershell -ExecutionPolicy Bypass -File .\scripts\start_platform.ps1
```

That starts the Odoo 15 QA target (port 8076, crons disabled) and the QA
platform (port 8000), both detached so they survive closing the terminal;
re-running it leaves anything already up alone. Stop with
`.\scripts\stop_platform.ps1 -All`.

**First time on a machine:** follow `docs/GETTING_STARTED.md` — it covers the
venv, the Playwright browser, cloning and neutralizing a QA database,
`config/local.yaml`, building the registry, and validating both environments.

Prerequisites: Python 3.10+ on PATH, your local Odoo 15 and/or Odoo 19
running, and a **test database** (never production).

Machine-local targets and the read-only PostgreSQL credentials used by the
data-reconciliation tests go in `config/local.yaml` (gitignored — copy
`config/local.yaml.example`). With that in place `python run_server.py`
needs no environment variables.

```powershell
cd D:\Projects\mmg\qa-platform\odoo-regression

python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium        # one-time browser download

copy .env.example .env
notepad .env                       # ← point it at YOUR Odoo instances (next section)

python run_server.py
```

Then open **http://localhost:8000** in your browser.

To **watch the real browser execute the workflow**, set this in `.env`
before starting the server:

```
HEADLESS=false
SLOWMO=400        # optional: slow each action down (ms) so it's easy to follow
```

With `HEADLESS=false`, clicking **RUN** on a UI test opens a real Chromium
window that logs into Odoo, opens Sales, creates the quotation, saves it —
while the dashboard shows live step-by-step progress. `HEADLESS=true` is for
CI / unattended runs.

## 2. Point it at your Odoo instances (`.env`)

```
# Odoo 15 — your local instance. Note: mmg.conf uses http_port = 8076
ODOO15_URL=http://localhost:8076
ODOO15_DB=<your v15 TEST database name>
ODOO15_USERNAME=admin
ODOO15_PASSWORD=<password>

# Odoo 19
ODOO19_URL=http://localhost:8019
ODOO19_DB=<your v19 TEST database name>
ODOO19_USERNAME=admin
ODOO19_PASSWORD=<password>
```

The user needs Sales access rights (admin works). The runner connects via
XML-RPC (`/xmlrpc/2`) and via the normal web login page for UI tests — the
same way a human uses the system.

**Database safety:** run only against clones/test databases. The tests
create their own namespaced data (customer "QA AUTO CUSTOMER", product
`QA-AUTO-PROD-001`, quotations tagged `QA-AUTO …` in *Source Document*) and
are repeatable — but they still write. The platform never deletes or
modifies existing business records.

## 3. Using the UI

0. **Features** (`#/`, landing page) — FG-01→FG-14 with test counts,
   priorities, automation coverage and v15/v19 status rollups. Click a group
   for its test cases; click a test case for the full workbook record
   (verbatim steps / expected result) and its execution history with
   evidence. The automated-test runner lives under **Automated tests**
   (`#/tests`).
1. **Environment** — pick `Odoo 15`, `Odoo 19`, or `Compare Odoo 15 ↔ Odoo 19`.
2. Tick tests → **RUN SELECTED**, or **RUN ALL**, or per-test **RUN**.
3. You are taken to the live run page: totals, passed/failed/skipped/running/
   pending, progress bar, current test + current step, and a live event log
   (real Server-Sent Events from the execution engine — nothing simulated).
4. Click **DETAILS** on any test: every step with duration, every assertion
   with expected/actual, screenshots (on failure always; on success when
   `SCREENSHOT_ON_SUCCESS=true`), the execution log, a Playwright trace zip
   on failure (`TRACE=retain-on-failure`), and the Excel traceability block.
5. In Compare mode both runs execute back-to-back (15 then 19) and the
   comparison matrix shows per-test statuses side by side; a test that
   passes on 15 and fails on 19 is flagged **⚠ REGRESSION**.

## 4. The 5 MVP tests (from the Excel workbook)

| Test | Kind | Workbook trace | What it proves |
|---|---|---|---|
| TEST-SMOKE-001 Login & Sales app opens | UI | TC-SMK-003 | The instance is usable at all |
| TEST-SALES-001 Create quotation | UI | TC-SAL-017, TC-ART-001 | Order-to-Cash leg 1 through the real browser, verified in the DB via RPC |
| TEST-SALES-002 Confirm quotation → sales order | API | TC-SAL-017 | O2C leg 2: state=sale, totals stable, delivery spawned |
| TEST-SALES-003 Cancel quotation before confirmation | API | gap found in discovery (rel. TC-SAL-021) | Clean cancel: no invoice, no delivery |
| TEST-SALES-004 MMG dollar discount on write | API | TC-SAL-007 | MMG's x_discount conversion; **auto-SKIPs** (with reason) where the MMG field doesn't exist |

## 5. Architecture (small, but the real shape)

```
Web UI (frontend/, no build step)  ──REST+SSE──  FastAPI (backend/app.py)
                                                     │
                                     execution engine (backend/runner.py)
                                     results store — SQLite (backend/store.py)
                                                     │
                              tests/  →  framework/ (registry, context, steps,
                                          assertions, artifacts, test data)
                                                     │
                                     pages/ (Playwright Page Objects,
                                             version-agnostic)
                                                     │
                        adapters/odoo15.py   ◄──►   adapters/odoo19.py
                        (selector maps, nav URLs, model differences)
                                                     │
                              Odoo 15 (:8076)   /   Odoo 19 (:8019)
```

Principles: tests describe **business behavior** and contain no selectors and
no version conditionals; page objects resolve logical elements through
per-version **candidate selector lists**; genuinely version-specific things
live only in the adapters (v15 `type='product'` vs v19 `type='consu' +
is_storable`; v15 `#menu_id` hash nav resolved by XML id vs v19 `/odoo/sales`;
v19 cancel-wizard bypass). Business assertions go through XML-RPC, so a UI
test's pass/fail is decided by database truth, not by pixels.

**Playwright over Selenium**: auto-waiting kills most flakiness, built-in
tracing/screenshots/video, one pip package with bundled browsers (no driver
management on Windows), context isolation per test, and a first-class sync
Python API. Selenium's remaining advantage (exotic browsers/legacy grids) is
irrelevant here.

**SSE over WebSocket** for live progress: updates flow one way, EventSource
auto-reconnects, and events are persisted first then streamed — refresh a run
page and it replays history, then continues live. Nothing in the UI is faked;
every number is a `SELECT` over the engine's persisted results.

## 6. Adding a test (no dashboard changes needed)

Create `tests/<area>/test_something.py`:

```python
from framework.registry import test_case

@test_case(id="TEST-SALES-005", name="…", workflow="WF-O2C-GALLERY",
           module="Sales", priority="P0", kind="API", order=60,
           traceability={"tc_ids": ["TC-…"], "feature": "…", "user_story": "…"})
def test_something(ctx):
    with ctx.step("Do a business thing"):
        ...  # ctx.adapter.<business action>  /  page objects for UI
    ctx.check("Business outcome", expected="sale", actual=state)
```

It appears in the UI automatically (the registry discovers `tests/`).
Reusable business actions belong in `adapters/base.py`; version differences
in the version adapters; UI interactions in `pages/`.

## 7. Troubleshooting

- **Login test fails immediately** → check `.env` URL/DB/credentials; the
  step-1 RPC ping tells you if the server is unreachable vs auth failure.
- **A UI step can't find an element** → open the failure screenshot and
  `trace.zip` in the test details. Selector maps live in
  `adapters/odoo15.py` / `odoo19.py` — each element takes a list of
  candidates; add the right one for your database's view variant. That is
  the single expected tuning point on first contact with a customized DB.
- **Multi-database server** → the login URL pins `?db=`, and XML-RPC always
  names the DB explicitly; make sure `ODOO15_DB` is exact.
- **Corporate proxy breaks `playwright install`** → set `HTTPS_PROXY` or
  download once on another network; browsers cache in `%USERPROFILE%\AppData\Local\ms-playwright`.

## 8. Validated against a real Odoo before delivery

This exact code was executed in the build sandbox against a live Odoo 19.0
(community, `sale_management` + `stock`): 4 passed, 1 skipped (the MMG
x_discount test — correctly, the field doesn't exist on vanilla 19), 0
errors. The UI-created quotation S00001 (QA AUTO CUSTOMER, 2 × $150 = $300,
state draft) was verified in PostgreSQL, and the failure path was exercised
by running Compare mode with an unreachable Odoo 15 (5 real ERRORs recorded,
run completed, matrix rendered). Odoo 15 selectors follow the same defensive
candidate-list design but have not met a live v15 in the sandbox — first run
on your machine may need a selector added; failure screenshots + traces make
that a minutes-level fix.

## 9. What comes next (per the approved Phase-1 plan)

5 tests → the full WF-O2C-GALLERY scenario set → deposits / Shopify (replay
mode) / inventory sync → v15 golden baselines + semantic comparison YAML →
workflow coverage KPIs on the dashboard. The result model (runs → results →
steps/assertions/artifacts) and the registry already carry workflow ids and
Excel traceability, so scaling is additive — no rework of this MVP.
