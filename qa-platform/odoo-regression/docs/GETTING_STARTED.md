# Getting Started — running the QA platform at http://127.0.0.1:8000

Two processes are involved, and they are independent:

| Process | Port | What it is |
|---|---|---|
| **Odoo 15 QA target** | 8076 | the application under test, serving the `mmg_qa15` clone |
| **QA platform** | 8000 | this repo's test runner + web UI |

The QA platform can start without Odoo, but every test run will then report
`BLOCKED / ENVIRONMENT` (the preflight refuses to invent failures), so start
both.

---

## A. Already set up on this machine? Two commands.

```powershell
cd D:\Projects\mmg\qa-platform\odoo-regression
powershell -ExecutionPolicy Bypass -File .\scripts\start_platform.ps1
```

Then open **http://127.0.0.1:8000**.

The script is safe to re-run: it detects anything already listening and
leaves running processes (and in-flight test runs) alone. Both processes are
started **detached**, so they survive closing the terminal.

To stop:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\stop_platform.ps1 -All
```

(omit `-All` to stop only the QA platform and leave Odoo 15 up)

---

## B. First time on a fresh machine

### 1. Create the Python environment (Python 3.10+)

```powershell
cd D:\Projects\mmg\qa-platform\odoo-regression
python -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt
venv\Scripts\python.exe -m playwright install chromium
```

`playwright install` downloads a browser once (~120 MB) into
`%USERPROFILE%\AppData\Local\ms-playwright`; it is needed only for the UI
tests. Behind a corporate proxy set `HTTPS_PROXY` first.

### 2. Create a QA clone of the database — never test against a production copy

The suites write namespaced fixture data, so they need their own database.
From a PostgreSQL superuser session:

```sql
CREATE DATABASE mmg_qa15 TEMPLATE mmg STRATEGY FILE_COPY;
```

If the source database is large and the PostgreSQL data directory is short on
space, put the clone on another drive first:

```sql
CREATE TABLESPACE qa_regression LOCATION 'E:/pg_qa_tablespace';
CREATE DATABASE mmg_qa15 TEMPLATE mmg TABLESPACE qa_regression STRATEGY FILE_COPY;
```

The tablespace directory must exist and be writable by the PostgreSQL
service account (here `NT AUTHORITY\NetworkService`).

Then **neutralize the clone** so no automated job can reach the outside
world — this is what makes the clone safe to run against:

```sql
UPDATE ir_cron SET active = false;          -- no scheduled connector syncs
UPDATE ir_mail_server SET active = false;   -- no outbound mail
UPDATE fetchmail_server SET active = false;
UPDATE magento_instance SET active = false; -- no Magento traffic
UPDATE ecommerce_channel SET active = false;-- no Shopify traffic
```

Leave `base_automation` records **active** — the local ones (dollar-discount
conversion, legal-date transfers) are business logic under test, not
outbound integrations.

### 3. Point the runner at your targets

Copy the example and edit it (`config/local.yaml` is gitignored, so your
credentials stay local):

```powershell
copy config\local.yaml.example config\local.yaml
notepad config\local.yaml
```

Minimum for Odoo 15:

```yaml
env:
  ODOO15_URL: http://localhost:8076
  ODOO15_DB: mmg_qa15
  ODOO15_USERNAME: admin
  ODOO15_PASSWORD: <your admin password>
  # read-only PostgreSQL access for the data-reconciliation tests;
  # omit and those tests report BLOCKED instead of running
  ODOO15_PG_HOST: localhost
  ODOO15_PG_PORT: 5433
  ODOO15_PG_USER: <db user>
  ODOO15_PG_PASSWORD: <db password>
  HEADLESS: "true"        # false = watch UI tests in a real browser
```

Odoo 19 keys are the same with the `ODOO19_` prefix; until a v19 instance
exists, leave them commented out and v19 runs will honestly report BLOCKED.

### 4. Build the test-case registry from the Excel workbook

```powershell
venv\Scripts\python.exe scripts\sync_registry.py
```

This reads `MMG_v19_Test_Cases_Grouped_by_Feature_v3.0.xlsx` **read-only**
and writes `data/test_registry.json` (383 test cases, 303 in FG-01→FG-14).
Re-run it whenever the workbook changes; expected results are copied verbatim
and never modified by the platform.

### 5. Check both environments before running anything

```powershell
venv\Scripts\python.exe scripts\validate_env.py
```

Prints READY / NOT READY per environment plus the platform's own checks
(runner, registry, browser, screenshot storage) and writes
`data/env_validation.json`.

### 6. Start it

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_platform.ps1
```

Open **http://127.0.0.1:8000**.

---

## C. Using the page

1. **Feature Groups** (landing page) — FG-01 → FG-14 with test counts,
   automation coverage, and v15/v19 status rollups.
2. Pick a **TARGET** (Odoo 15, Odoo 19, or Compare 15 ↔ 19). The choice is
   remembered as you navigate.
3. Click a RUN button:
   - `▶ RUN FG-01 → FG-14` — the whole registered regression suite
   - `▶ RUN` on a feature row, or `▶ RUN FG-04` on the feature page
   - `▶ RUN TC-BLK-001` on a test-case page — a single case
   - `#/tests` — per-script runs, RUN SELECTED, RUN ALL
4. You land on the **live run page**: counters, progress, current step, and a
   streaming log. Refreshing replays the run from persisted events.
5. **DETAILS / EVIDENCE** on any execution shows every step, every assertion
   with expected vs actual, the execution log, screenshots, Playwright traces,
   and reconciliation CSVs.
6. **HISTORY** on a test case lists every execution it has ever had, per
   environment — click any one to see its evidence.
7. In Compare mode, the matrix classifies each case: `SAME_BEHAVIOR`,
   `REGRESSION_CANDIDATE` (needs failure triage before anyone calls it a
   regression), `FIXED`, `SAME_FAILURE`, `BLOCKED`.

Reports are regenerated from the same persisted rows with:

```powershell
venv\Scripts\python.exe scripts\gen_reports.py
```

---

## D. Adding or editing tests

Test scripts live in `tests/fgNN/test_*.py` and register themselves with the
`@test_case` decorator (see `docs/AUTOMATION_CONVENTIONS.md` and the FG-01
reference suite). After adding or editing one, pick it up without a restart:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/registry/reload
```

`wip/` holds partially built suites that are deliberately not registered;
moving a folder from `wip/` into `tests/` is all it takes to activate it.

---

## E. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Every test `BLOCKED`, reason "unreachable" | the Odoo target is not running — start it (section A) and check `artifacts/odoo15-server.log` |
| Data-reconciliation tests `BLOCKED`, reason "No PostgreSQL access configured" | add the `ODOO15_PG_*` keys to `config/local.yaml` |
| v19 tests `BLOCKED` | expected — no local Odoo 19 instance exists yet (see `docs/ENVIRONMENT_STATUS.md`) |
| Login fails | wrong `ODOO15_USERNAME` / `ODOO15_PASSWORD` in `config/local.yaml`, or the wrong `ODOO15_DB` |
| Runs stuck at RUNNING after a crash | restarting the platform closes them as `ERROR / INTERRUPTED` automatically |
| A UI test can't find an element | open the failure screenshot and `trace.zip` in the execution evidence; selector candidate lists live in `adapters/odoo15.py` / `odoo19.py` |
| Port 8000 already in use | something else is bound; stop it or set `RUNNER_PORT` in `config/local.yaml` |
