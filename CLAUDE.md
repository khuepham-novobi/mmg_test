# MMG QA Regression Platform — machine setup

This repo holds the MMG Odoo 15→19 upgrade regression platform: a FastAPI
runner + web UI that executes automated test suites against a target Odoo
instance and stores the evidence.

**Everything lives under `qa-platform/odoo-regression/`.** Treat that as the
project root for every command below.

> **If you are Claude setting this machine up: follow §1 → §5 in order.**
> §2 is the step git cannot do for you, and §4 is the one that tells you
> whether the tests will actually produce verdicts.

---

## 1. Install

Python **3.10+** required.

```powershell
cd qa-platform\odoo-regression
python -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt
```

`playwright install chromium` is only needed for UI suites. **FG-05 (AvaTax)
is API-only and never launches a browser** — skip it unless you plan to run
FG-01…FG-04.

---

## 2. Create the config — git does NOT bring it

`.gitignore` excludes every file that holds a target or a credential, on
purpose. After a clean clone you have the test code and **no way to reach a
database**. Create this one file:

```powershell
copy config\local.yaml.example config\local.yaml
```

Then edit `config/local.yaml` and fill in the `ODOO19_*` block. Read the
comments in that file — they are the real documentation. The three that
actually break runs:

1. **`ODOO19_URL` must match the port your v19 server listens on.**
   MMG's `mmg.conf` uses `http_port = 8076`. Get this wrong and every test
   reports `BLOCKED / ENVIRONMENT — Odoo 19 unreachable at <url>` in the
   runner's preflight, before a single test body executes. That is the
   platform refusing to invent a verdict, not a broken test.
2. **`ODOO19_USERNAME` is usually NOT `admin`.** On a restored production
   database `res.users` id 1 is `__system__` and **inactive**; the real
   administrator is a named person. Check first:
   `SELECT id, login, active FROM res_users WHERE id IN (1,2);`
3. **That user must be in `base.group_system`.**
   `res.company.avalara_api_id` / `avalara_api_key` carry
   `groups='base.group_system'`, so a lesser user never receives them.

Precedence is `config/local.yaml` > `.env` > `config/environments.yaml`
defaults. `local.yaml` always wins, so you do **not** need a `.env` at all —
and if a stale `.env` is lying around, `local.yaml` overrides it.

**Never commit `config/local.yaml` or `.env`.** They are gitignored; keep it
that way. Ask the user for credentials — do not invent or guess them, and do
not paste them into any tracked file, commit message, or documentation.

---

## 3. The Odoo 19 target

The suites write namespaced fixture data, so point them at a **dedicated
clone**, never the primary restore:

```sql
CREATE DATABASE mmg_qa19 TEMPLATE mmg_19 STRATEGY FILE_COPY;
```

Then neutralize the clone so nothing can reach the outside world:

```sql
UPDATE ir_cron SET active = false;
UPDATE ir_mail_server SET active = false;
UPDATE fetchmail_server SET active = false;
```

Start the server with crons off — a production restore holds live connector
configuration and cron threads can fire real outbound syncs:

```powershell
<v19-venv>\Scripts\python.exe <odoo19>\odoo-bin -c <conf> -d mmg_qa19 --max-cron-threads=0
```

---

## 4. Check readiness BEFORE running anything

```powershell
venv\Scripts\python.exe scripts\check_fg05_readiness.py
```

Read-only; creates nothing and never calls Avalara. It reports exactly what
will happen when you press Run: server reachable, credentials valid, user
rights, `Use AvaTax`, sandbox vs production, the AvaTax fiscal position, and
the supporting data each case needs. Exit 0 = ready.

**Known finding on the `mmg_19` restore (checked 2026-09-10):** `Use AvaTax`
is off, `Commit Transactions` is off, and **0 of 10 fiscal positions have
`Use AvaTax API` ticked** — including `Automatic Tax Mapping (AvaTax)`. With
that state TC-DAT-017 correctly **FAILS** and the other 13 **BLOCK**. That is
the workbook's GATE 3 finding, not a test defect: the AvaTax flags did not
survive the upgrade. Enabling them is a business decision — report it, and
ask the user before changing any company or fiscal-position configuration.

---

## 5. Run

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_platform.ps1
```

Open <http://127.0.0.1:8000>, set **TARGET = Odoo 19**, then either:

- `#/tests` — pick scripts, **RUN SELECTED**. Works with no Excel workbook.
- `#/feature/FG-05` — the workbook dashboard. Only populated if you ran
  `scripts/sync_registry.py`, which needs the Excel file (not in this repo).

Runs resolve from the **`@test_case` code registry**, not the workbook, so
the second is optional. After editing a test, reload without restarting:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/registry/reload
```

---

## Working on this repo

- Test suites live in `tests/fgNN/`. `docs/AUTOMATION_CONVENTIONS.md` is
  binding — read it before adding or changing a test.
- FG-05 specifics, including its safety model and the deviation it takes from
  convention rule 4, are in `docs/FG-05_MANUAL_GUIDELINE_SUITE.md`.
- Per-TC automation decisions are recorded in
  `reports/data/fgNN_feasibility.json`.
- Expected results come from the client workbook and are **immutable** —
  never weaken an assertion to make a test pass.
- `wip/` is gitignored: partially built suites that are deliberately not
  registered.
