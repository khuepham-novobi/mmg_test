# FG-05 — AvaTax suite (client manual testing guideline)

Automates all 14 FG-05 cases from
`MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0.xlsx`, sheet
**Testing Guideline**, rows 1–14. Source: that workbook, plus a field-by-field
read of Odoo Enterprise 19 `account_avatax` and the MMG override on branch
`staging_19`.

Code: `tests/fg05/`. Feasibility record: `reports/data/fg05_feasibility.json`.

---

## 1. What is registered

| # | TC | Test id | Prio | Needs sandbox? |
|---|---|---|---|---|
| 1 | TC-DAT-017 | `TEST-FG05-DAT-017` | P0 | No (only step 3) |
| 2 | TC-TAX-001 | `TEST-FG05-TAX-001` | P0 | Yes |
| 3 | TC-TAX-002 | `TEST-FG05-TAX-002` | P0 | Yes |
| 4 | TC-TAX-003 | `TEST-FG05-TAX-003` | P0 | Yes |
| 5 | TC-TAX-007 | `TEST-FG05-TAX-007` | P0 | **No** |
| 6 | TC-TAX-008 | `TEST-FG05-TAX-008` | P0 | Yes |
| 7 | TC-TAX-009 | `TEST-FG05-TAX-009` | P0 | Yes |
| 8 | TC-TAX-010 | `TEST-FG05-TAX-010` | P0 | Yes |
| 9 | TC-TAX-011 | `TEST-FG05-TAX-011` | P0 | Yes |
| 10 | TC-TAX-013 | `TEST-FG05-TAX-013` | P0 | Yes |
| 11 | TC-TAX-014 | `TEST-FG05-TAX-014` | P1 | Yes |
| 12 | TC-TAX-015 | `TEST-FG05-TAX-015` | P1 | Yes |
| 13 | TC-TAX-016 | `TEST-FG05-TAX-016` | P1 | Yes |
| 14 | TC-TAX-017 | `TEST-FG05-TAX-017` | P1 | Yes |

Run order matches the workbook's own (`Order of Testing`, step 3.0):
TC-DAT-017 first, TC-TAX-017 last. The registry `order` values (500–513)
already produce that sequence.

---

## 2. Safety — read before the first run

1. **Sandbox only — checked against the host Avalara will actually use.**
   Every case that calls Avalara passes `require_sandbox()` first. It BLOCKS
   unless `Use AvaTax` is on, both credentials read as set, and the resolved
   Avalara host is provably the sandbox.

   "Resolved" matters. `avalara_environment` is `required` with
   `default='sandbox'`, so *every* company reads `sandbox` until someone
   changes it — including one never configured for AvaTax. And `_get_client`
   does not use the acting company's environment: it walks `parent_id` via
   `_find_avatax_credentials_company` until it finds a company holding both
   credentials, then uses **that** company's environment. A subsidiary with no
   credentials therefore resolves to a parent that may hold **production**
   ones. `avatax_client_target()` in `tests/fg05/common.py` reproduces that
   walk, and anything it cannot prove is treated as unsafe.
2. **Credential values never reach evidence.** They are recorded as
   `set` / `not set`, or as a SHA-256 fingerprint (TC-TAX-017).
3. **Deleting an AvaTax invoice calls Avalara — and the delete then fails.**
   `account.move.unlink()` runs `_void_external_taxes()` *before*
   `super().unlink()`, which for a posted move is refused by
   `_unlink_except_posted`. Odoo rolls back the database; it cannot roll back
   the HTTP void. So posted ids are never handed to teardown, and sweep and
   cleanup skip AvaTax-flagged drafts unless the resolved host is provably the
   sandbox. Both are also scoped to the one company the guard verified, since
   the platform sends no `allowed_company_ids` and the record rule would
   otherwise return a sibling company's records. Quotations are safe
   (`sale_external_tax` does not override `unlink`).
4. **TC-TAX-017 overwrites the API KEY on purpose.** It refuses to write
   unless it can first read the key back (an unrestorable key is never
   overwritten), restores in a `finally:` block, and asserts the restore. It
   also BLOCKS if the key already reads as the invalid string, which means an
   earlier run did not restore.
5. **All fixtures are namespaced `FG05`.** No pre-existing business record is
   modified. TC-TAX-014 does not touch a live product category (the workbook
   does — see the feasibility record).

---

## 3. Prerequisites

The suite is **Odoo 19 only**. On any other target every case reports BLOCKED
with a reason, by design.

### 3.1 Point the runner at v19

Add to `config/local.yaml` (not committed):

```yaml
env:
  ODOO19_URL: http://localhost:8076
  ODOO19_DB: mmg_qa19
  ODOO19_USERNAME: admin
  ODOO19_PASSWORD: <admin password>
```

`ODOO19_PG_*` is **not** needed — this suite uses no SQL.

### 3.2 Use a clone, not the restore itself

The suite writes namespaced fixture data, so it needs its own database:

```sql
CREATE DATABASE mmg_qa19 TEMPLATE mmg_19 STRATEGY FILE_COPY;
```

Then neutralize it the same way `mmg_qa15` was (crons, mail, connector
instances off — see `docs/GETTING_STARTED.md` §B.2). Leave the AvaTax
credentials in place, but **confirm Environment reads Sandbox**.

---

## 4. Environment findings — checked 2026-09-08 against `mmg_19`

These are database facts, not test defects. Two of them will stop the suite.

| Check | Result |
|---|---|
| `account_avatax` 19.0.1.0 | installed |
| `account_avatax_sale` 19.0.1.0 | installed |
| `mmg_account_avatax_enhancement` 19.0.1.0.0 | installed |
| `avalara_environment` | `sandbox` ✅ |
| `avalara_api_id` / `avalara_api_key` | both set ✅ |
| `product.avatax.category` rows | 3,483 ✅ |
| `avatax.exemption` rows | 18 ✅ |
| Partners with an exemption | 11 ✅ |
| `account.tax` with v15 bracketed naming | 636 ✅ |
| **Fiscal positions with `is_avatax = true`** | **0 ❌** |
| **`setting_account_avatax` (Use AvaTax)** | **empty ❌** |
| `avalara_commit` (Commit Transactions) | false ⚠️ |

**Consequences, in the order you will hit them:**

1. `Use AvaTax` is not ticked and no fiscal position has `Use AvaTax API`
   ticked — including id 14, `Automatic Tax Mapping (AvaTax)`. This is exactly
   what TC-DAT-017 exists to catch, and it is the workbook's GATE 3.
   **TC-DAT-017 will FAIL and the other 13 will BLOCK** until it is fixed.
2. `Commit Transactions` is off, so **TC-TAX-011 will BLOCK** — its own
   precondition requires it on.

Nothing else in the AvaTax configuration is missing: the credentials,
categories, exemptions and the 636 migrated jurisdiction taxes all came
across, which is why the naming decision (D1-a) reuses them rather than
creating a second generation.

---

## 5. Running it

```powershell
cd D:\Projects\mmg\mmg_test\qa-platform\odoo-regression
powershell -ExecutionPolicy Bypass -File .\scripts\start_platform.ps1
```

Then at **http://127.0.0.1:8000**:

1. Set **TARGET** to **Odoo 19**.
2. Go to `#/feature/FG-05` and press **▶ RUN FG-05**, or `#/tests` to pick
   individual scripts.
3. Evidence per execution: every step, every assertion with expected vs
   actual, and the execution log (which carries the AvaTax inventory,
   the jurisdiction tax names, and any RESIDUAL MANUAL STEP notes).

If the platform is already running, pick the new tests up without a restart:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/registry/reload
```

---

## 6. What still needs a human

| TC | Manual step | Why |
|---|---|---|
| TC-DAT-017 | Tick the captured inventory off against the Novobi printout | The platform does not hold the printout; the inventory is logged and written to a CSV artifact |
| TC-TAX-011 | Look the transaction up in the Avalara sandbox portal | The proof is outside Odoo; the log prints both Avalara Codes and both tax figures so it is a lookup, not a re-run |

Both are printed into the execution log as **RESIDUAL MANUAL STEP**, not
silently dropped.

---

## 7. Relationship to `wip/fg05/`

`wip/fg05/` targets the **v15** AvaTax surface (`account_avatax` OCA fork,
`_map_avatax`, `button_update_avatax`) and is 16 blocked stubs. It is not
discovered by the registry and is left untouched. Four of its cases no longer
apply on v19: TC-TAX-004/005/006 guarded a mapping step that was deleted, and
TC-TAX-012's premise is wrong in both versions — see
`mmg_account_avatax_enhancement/README.md` on branch `staging_19`.
