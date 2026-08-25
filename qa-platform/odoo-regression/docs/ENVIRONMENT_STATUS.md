# Environment Status — Odoo 15 / Odoo 19 / QA Platform

Validated 2026-08-18 with `scripts/validate_env.py` (machine-readable report:
`data/env_validation.json`). Re-run the script after any environment change.

## Verdicts

| Environment | Verdict | One-line reason |
|---|---|---|
| **Odoo 15 local** (`http://localhost:8076`, db `mmg`) | **NOT READY** | Server process is not running (connection refused); everything needed to start it is present |
| **Odoo 19 local** (`http://localhost:8019`, db `odoo19_test`) | **NOT READY** | No local Odoo 19 installation, no server, no v19 database exists |
| **QA platform** (`qa-platform/odoo-regression`) | **READY** | All platform checks pass |

## Odoo 15 — detail

| Check | Result | Evidence |
|---|---|---|
| Server reachable (`localhost:8076`) | ❌ | `ConnectionRefusedError (WinError 10061)` — no process listening |
| XML-RPC version / login / modules | ❌ (blocked) | Skipped — server down |
| PostgreSQL reachable (`localhost:5433`) | ✅ | TCP open; `psql` lists databases |
| Database `mmg` exists | ✅ | Present in `pg_database` |
| Odoo 15 source tree | ✅ | `D:\Projects\odoo15\odoo-bin`, `addons/`, `enterprise/` all present |
| Server config | ✅ | `D:\Projects\mmg\mmg.conf` (http_port 8076, addons include `psus-medicine-man-gallery` + `novobi-omni-addons`) |
| Python runtime | ✅ | `D:\Projects\mmg\venv` — Python 3.7.8 (correct era for Odoo 15) |
| Custom modules on disk | ✅ | 29 module folders in `psus-medicine-man-gallery` (mmg_*, avatax OCA, Emipro Magento, report_py3o, …) |

**To make READY:** start the local Odoo 15 (the QA runner does not start it):

```bash
D:/Projects/mmg/venv/Scripts/python.exe D:/Projects/odoo15/odoo-bin -c D:/Projects/mmg/mmg.conf
```

then re-run `python scripts/validate_env.py`.

**⚠ Data-safety warnings (must be resolved before test runs):**

1. `.env` currently points the runner at db **`mmg`** — a production-copy
   database. Platform tests write namespaced QA data; they must run against a
   **dedicated clone** (e.g. `mmg_qa15`), never the primary copy.
2. `mmg.conf` has `max_cron_threads = 2`. A production-copy DB contains live
   connector configuration (Shopify/Magento/AvaTax). Starting the server with
   crons enabled can fire real outbound syncs. For QA, start with
   `--max-cron-threads=0` (or neutralize connector credentials in the clone)
   and keep outbound mail disabled.

## Odoo 19 — detail

| Check | Result | Evidence |
|---|---|---|
| Server reachable (`localhost:8019`) | ❌ | Connection refused — nothing listening |
| Odoo 19 source tree | ❌ | Not found under `D:\Projects` (newest local core is `odoo-18.0`) |
| v19 database | ❌ | No candidate database on `localhost:5433` (found: mmg, nui, postgres, sadk, vb) |
| Migrated custom modules for v19 | ❌ (locally) | v19 work lives on the Odoo.sh `staging_19` branch, which is out of bounds for this automation phase |

**To make READY:**

1. Install Odoo 19 locally (source checkout or packaged) with a
   Python 3.10+ venv.
2. Create a v19 QA database (restore of the upgraded staging dump is ideal,
   with crons/mail/connector credentials neutralized).
3. Make the migrated MMG modules available in its addons path.
4. Point `.env` (`ODOO19_URL/DB/USERNAME/PASSWORD`) at it and re-run
   `python scripts/validate_env.py`.

## QA platform — detail

| Check | Result | Evidence |
|---|---|---|
| Test runner usable | ✅ | 5 automated tests discovered via the `@test_case` registry |
| Registry store | ✅ | 383 test cases loaded (303 in scope), 14 in-scope feature groups |
| Browser automation | ✅ | Playwright Chromium launches headless; screenshot written (`artifacts/env-validation-screenshot.png`) |
| Logs & evidence storage | ✅ | `artifacts/` writable; execution logs, screenshots, traces persisted per execution |
| Web UI | ✅ | Serves at `http://127.0.0.1:8000`; feature dashboard, test-case detail, execution evidence verified in a browser |
| Results DB | ✅ | SQLite WAL at `data/results.db`; schema migrated (adds `failure_class`) |

## Credentials note

Runner credentials live in `qa-platform/odoo-regression/.env` (not committed;
`.env.example` documents the shape). No secrets are reproduced in this
document.

---

## Addendum — 2026-08-19 (QA clone rebuild + baseline corrections)

### The QA clone was rebuilt

`mmg_qa15` developed a corrupt heap page (`product_template` block 0). It read
fine under a sequential scan but failed under parallel plans:

```
ERROR: invalid page in block 0 of relation "pg_tblspc/188792/.../144125"
```

Any result produced from it was therefore untrustworthy. The database was
dropped and re-cloned from `mmg` onto a **fresh tablespace**
(`qa_regression2` → `E:/pg_qa_tablespace2`) rather than reusing the suspect
files, then re-neutralized. Post-rebuild checks pass, including a forced
parallel scan (`debug_parallel_query=on`).

**Watch item:** the first clone attempt of `mmg` also failed on an unreadable
`pg_statistic` block, and this is the second page-level fault on the same
host. If a third appears, check the disks before trusting any run.

### Automations: only two are active in production

The production copy has **`[PZE] Calc Dollar Discount` and `[PZE] Inv Value`
INACTIVE**; only the two Legal-Date-Transfer automations run. An earlier clone
had all four force-enabled during setup, which did not reflect production —
the rebuilt clone mirrors it exactly.

This is not the same as "the discount feature is off": `mmg_automated_action`
converted that automation **into module Python code**
(`models/sale_order_line.py`, commented `# [PZE] Calc Dollar Discount`), so
the behaviour still runs on `write()`. The v15 implementation is:

```python
rec.discount = rec.x_discount * 100 / rec.price_unit if rec.price_unit else 0
```

i.e. divided by unit price only (no quantity), applied on `write()` but **not**
on `create()`, and with **no 100 % clamp** — all three of which the v19 port
changes. FG-03's expected v15 baseline outcomes follow from this.

### Workbook anchors are dated snapshots, not invariants

`TC-DAT-011` / `TC-STU-008` assert 69,201 product templates and 13,972
`x_medium` references. The **source production copy itself** now holds 69,316
and 14,001 — the anchors were captured 2026-08-13 and the database has grown
since. Verified on both `mmg` and the fresh clone:

| Metric | Workbook anchor | `mmg` (source) | `mmg_qa15` (clone) |
|---|---:|---:|---:|
| product templates | 69,201 | 69,316 | 69,316 |
| `x_medium` references | 13,972 | 14,001 | 14,001 |
| `x_medium` rows | 341 | 341 | 341 |

So those anchor failures are neither test defects nor QA-fixture pollution.
Reconciliation must compare **v15 ↔ v19** (its actual purpose) and report
anchor drift as information, not assert stale absolute counts.

### Transport changed to the web-client endpoint

The runner now calls `/web/dataset/call_kw` over an authenticated session
instead of the external `/jsonrpc` API, because the two differ in flush
semantics on v15 — see `docs/TEST_AUTOMATION_ARCHITECTURE.md` §5b and the
module docstring of `adapters/base.py`.

**Product finding (v15):** a `product.template` created through the external
API does **not** get the `mmg_stock` template→variant field mirror, while the
same create through the web client does (writes mirror on both paths).
Connector-created products would therefore silently miss variant-level art
fields.
