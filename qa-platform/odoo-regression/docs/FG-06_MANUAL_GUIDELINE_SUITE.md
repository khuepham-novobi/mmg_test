# FG-06 — Customer & Vendor Deposits (client manual testing guideline)

Automates all 15 FG-06 cases from
`MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0.xlsx`, sheet
**Testing Guideline**, rows 15–29. Source: that workbook, plus a
field-by-field read of the MMG v19 modules `account_partner_deposit` and
`sale_partner_deposit` on branch `staging_19` (both `19.0.1.0.0`), their two
`PORTING.md` files, and the Odoo 19 source at `D:\Projects\odoo-19.0`.

Code: `tests/fg06/`. Feasibility record: `reports/data/fg06_feasibility.json`.

---

## 1. What is registered

| # | TC | Test id | Prio | Kind | Module |
|---|---|---|---|---|---|
| 1 | TC-DAT-019 | `TEST-FG06-DAT-019` | P0 | DATA | `account_partner_deposit` |
| 2 | TC-DAT-016 | `TEST-FG06-DAT-016` | P0 | DATA | `account_partner_deposit` |
| 3 | TC-DEP-003 | `TEST-FG06-DEP-003` | P0 | API | `account_partner_deposit` |
| 4 | TC-DEP-001 | `TEST-FG06-DEP-001` | P0 | API | `account_partner_deposit` |
| 5 | TC-DEP-004 | `TEST-FG06-DEP-004` | P0 | API | `sale_partner_deposit` |
| 6 | TC-DEP-005 | `TEST-FG06-DEP-005` | P0 | API | `sale_partner_deposit` |
| 7 | TC-DEP-012 | `TEST-FG06-DEP-012` | P1 | API | `sale_partner_deposit` |
| 8 | TC-DEP-016 | `TEST-FG06-DEP-016` | P1 | API | `sale_partner_deposit` |
| 9 | TC-DEP-006 | `TEST-FG06-DEP-006` | P1 | API | `sale_partner_deposit` |
| 10 | TC-DEP-007 | `TEST-FG06-DEP-007` | P0 | API | `sale_partner_deposit` |
| 11 | TC-DEP-009 | `TEST-FG06-DEP-009` | P1 | API | `account_partner_deposit` |
| 12 | TC-DEP-010 | `TEST-FG06-DEP-010` | P0 | API | `account_partner_deposit` |
| 13 | TC-DEP-011 | `TEST-FG06-DEP-011` | P1 | API | `sale_partner_deposit` |
| 14 | TC-DEP-013 | `TEST-FG06-DEP-013` | P1 | API | `sale_partner_deposit` |
| 15 | TC-DEP-017 | `TEST-FG06-DEP-017` | P1 | API | `sale_partner_deposit` |

**Nothing needs a browser.** Every case is `API` or `DATA`, so no Playwright
instance is launched and a full FG-06 run is light on the machine.

### Run order

The registry `order` values (600–614) reproduce the workbook's own
`Order of Testing` sequence exactly — step 1.0 for the two data cases, then
step 4.0's explicit ordering, which is **not** the sheet's row order:

```
600 TC-DAT-019   ← "Run this before any other FG-06 case"
601 TC-DAT-016
602 TC-DEP-003
603 TC-DEP-001
604 TC-DEP-004
605 TC-DEP-005
606 TC-DEP-012
607 TC-DEP-016
608 TC-DEP-006   ← after TC-DEP-016, before TC-DEP-017
609 TC-DEP-007
610 TC-DEP-009
611 TC-DEP-010   ← GATE 4
612 TC-DEP-011
613 TC-DEP-013
614 TC-DEP-017   ← LAST
```

Pressing **▶ RUN FG-06** runs them in that order. Each test is nonetheless
self-contained (see §3), so running one on its own is equally valid.

---

## 2. Safety — read before the first run

1. **Nothing here reaches an external system.** FG-06 is entirely local, so
   `AUTOMATION_CONVENTIONS` rule 4 needs no deviation for this suite — unlike
   FG-05, which had to be run against the Avalara sandbox.
2. **All fixtures are namespaced `FG06`** and swept before and after each
   test. No pre-existing business record is modified. TC-DAT-016 and
   TC-DAT-019 create and write nothing at all.
3. **A confirmed deposit is never handed to `unlink()`.** This is the one
   genuinely dangerous operation in the group. In v19
   `account.payment.unlink()` calls `button_draft()` on the journal entry and
   *then* unlinks it
   (`addons/account/models/account_payment.py:957-959`), so the posted-move
   guard on `account.move.line` never fires and a confirmed deposit would be
   destroyed together with its entry — precisely the data loss FG-06 exists to
   detect. Two independent defences:
   - `sweep_fg06` sweeps deposits by their **journal entry's** state and
     excludes anything posted **in the domain**, rather than attempting and
     logging a failure;
   - `cleanup()` re-checks and refuses posted deposits even if a caller
     forgets to remove them.
4. **The entry state, not the payment state, is what "confirmed" means.**
   A deposit reads `state = 'in_process'` from the moment it is created,
   because `_generate_journal_entry` runs at create time for any payment
   carrying `write_off_line_vals`
   (`addons/account/models/account_payment.py:1080`) and every deposit
   carries them. That is **BC-016**. A sweep keyed on the payment state would
   both miss remnants and, if broadened, delete real money.
5. **Some records are left behind on purpose.** The workbook's *State After
   The Test* column expects several confirmed deposits and posted invoices to
   survive. Every assertion is therefore scoped to ids captured in-test,
   never to a count of all FG06 records. The single exception is TC-DAT-016,
   which is a whole-population count by design — and it reports the FG06
   fixture share separately and subtracts it, so the baseline comparison is
   not inflated by the suite's own leftovers.

---

## 3. Prerequisites

The suite is **Odoo 19 only**. On any other target every case reports BLOCKED
with a reason, by design — the v19 deposit surface differs from v15's in ways
these expectations read directly (payment states, JSONB company-dependent
fields, and the cancellation behaviour).

### 3.1 Point the runner at v19

`config/local.yaml` currently has the v19 block commented out. Add:

```yaml
env:
  ODOO19_URL: http://localhost:8076
  ODOO19_DB: mmg_qa19
  ODOO19_USERNAME: admin
  ODOO19_PASSWORD: <admin password>
```

`ODOO19_PG_*` is **not** needed — this suite uses no SQL. That is deliberate:
`ctx.sql` reports BLOCKED when `pg_*` is unconfigured, and everything FG-06
needs is reachable over RPC, including the company-dependent deposit accounts
(see §5).

### 3.2 Use a clone, not the restore itself

Thirteen of the fifteen cases write namespaced fixture data, so the suite
needs its own database:

```sql
CREATE DATABASE mmg_qa19 TEMPLATE mmg_19 STRATEGY FILE_COPY;
```

Then neutralize it the same way `mmg_qa15` was — crons, mail and connector
instances off (see `docs/GETTING_STARTED.md` §B.2).

### 3.3 Modules

Both must be installed, or every case BLOCKS with an install instruction:

- `account_partner_deposit` 19.0.1.0.0 — probed via `account.payment.is_deposit`
- `sale_partner_deposit` 19.0.1.0.0 — probed via `sale.order.deposit_total`
  and the `order.make.deposit` model

### 3.4 What each case needs from the data

| Need | Cases | If absent |
|---|---|---|
| A bank or cash journal | TC-DEP-001 | BLOCKED with the remedy |
| Two eligible customer-deposit accounts | TC-DEP-003 | An `FG06`-marked one is created; which happened is logged |
| A second active currency **with a usable rate** | TC-DEP-012 | BLOCKED — the workbook's own precondition |
| At least one real (non-fixture) deposit | TC-DAT-016 step 7 | Recorded as a residual manual step |

---

## 4. Running it

```powershell
cd D:\Projects\mmg\mmg_test\qa-platform\odoo-regression
powershell -ExecutionPolicy Bypass -File .\scripts\start_platform.ps1
```

Then at **http://127.0.0.1:8000**:

1. Set **TARGET** to **Odoo 19**.
2. Go to `#/feature/FG-06` and press **▶ RUN FG-06**, or `#/tests` to pick
   individual scripts.
3. Evidence per execution: every step, every assertion with expected vs
   actual, the execution log, and the CSV artifacts below.

If the platform is already running, pick the new tests up without a restart:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/registry/reload
```

### Artifacts to open first

| File | From | Why |
|---|---|---|
| `TC-DAT-019-deposit-account-inventory.csv` | TC-DAT-019 | Every contact-level deposit-account override, with a verdict — tick off against the Novobi printout |
| `TC-DAT-016-deposit-population.csv` | TC-DAT-016 | Counts and totals per currency, the FG06 fixture share, and the baseline-comparable figures |
| `TC-DAT-016-three-deposits.csv` | TC-DAT-016 | The three real deposits opened field by field |

Both TC-DAT CSVs are written from a `finally` block, so they exist even when
an assertion fails — which is when they are most useful.

---

## 5. How this suite proves things the obvious way cannot

Three mechanics are worth knowing before reading a failure, because in each
case the naive approach silently measures the wrong thing.

### 5.1 "The field fills itself in from the contact" is asserted, not simulated

`@api.onchange` methods do **not** fire on `create()` / `write()` over RPC.
But `onchange(values, field_names, fields_spec)` is a public method
implemented in the `web` addon (`addons/web/models/models.py:1973`) and is
exactly what a form view calls. So:

- `form_defaults()` — empty `field_names`, the "record created from scratch"
  path (`models.py:2019-2031`) — reproduces **opening a form** under a given
  context, which is how the *Make a Deposit* payment pop-up's initial Amount,
  Currency and Deposit Account are read;
- `onchange_values()` reproduces **editing one field**, which is how
  "set Customer and watch Deposit Account fill in" is checked.

This is why "read the Amount before you validate" is a real assertion on the
figure the pop-up would display, rather than a re-derivation of the
arithmetic.

Conversely, `make_deposit()` always passes the deposit account explicitly,
because `create` raises `ValidationError('Deposit account has not been set')`
without it (`account_partner_deposit/models/account_payment.py:60-64`) and the
onchange that normally supplies it cannot run there.

### 5.2 "Does this contact carry its OWN deposit account?"

Every obvious approach is wrong:

| Approach | Why it fails |
|---|---|
| `read()` the field | Returns the **effective** value, silently falling back to the company default — a contact that lost its override looks like it still has one |
| Search `('field', '!=', False)` | `Field._field_to_sql` resolves a company-dependent field to `COALESCE(<jsonb>, <fallback>)` (`odoo/orm/fields.py:1218-1219`), so it matches **every** partner once a default exists |
| `ir.default._get_model_defaults()` | Private; Odoo refuses private methods over RPC |

The answer follows from `Field.convert_to_column`, which stores **None**
whenever the value written equals the company fallback
(`odoo/orm/fields.py:1000-1005`). An override equal to the default is not
stored at all, so the two states are observationally identical, and:

> a contact carries its own account **⟺** its effective value differs from
> the company fallback

which *is* expressible as a domain: `(field, '!=', fallback_id)`. The fallback
is read from the `ir.default` rows directly, which is where
`res_company.create_or_update_deposit_property` writes it
(`account_partner_deposit/models/res_company.py:171-177`). No SQL needed.

### 5.3 The Outstanding credits panel

`invoice_outstanding_credits_debits_widget` is a computed `fields.Binary`
whose value is the payload dict the OWL component reads
(`addons/account/models/account_move.py:498-502`); the MMG override appends
the deposit entries (`account_partner_deposit/models/account_move.py:16-97`).
Reading the field over RPC returns that dict — the same thing the browser
gets — and each RPC call is its own transaction, so the compute is always
fresh and no cache invalidation is needed.

---

## 6. Findings this suite is built to surface

These are **not** test defects. Each is a divergence between the workbook and
the shipped v19 code, found while writing the assertions, with its source
line. Brief the tester on them before the session.

| # | Case | Finding |
|---|---|---|
| 1 | **TC-DEP-007** | The workbook's steps 3–5 cannot be performed in the order written. Posting an invoice raised from an order **auto-applies** that order's deposits (`sale_partner_deposit/models/account_move.py:7-17`), and an applied deposit fails the panel's own domain, while a draft invoice suppresses the panel entirely. So the panel never offers that deposit on the order-linked path. All the workbook's *outcomes* are asserted; line 1 (the panel) is asserted on a deposit the auto-application does not consume. **The workbook's step order needs correcting.** |
| 2 | **TC-DEP-001** | Expected Result line 3 says the deposit "starts on Draft". In v19 a saved unconfirmed deposit reads `in_process` (BC-016). The substance is asserted against the journal entry's state; the reading is logged with its source. |
| 3 | **TC-DEP-001** | Step 6 says the Journal field offers only bank and cash journals. v19 computes `available_journal_ids` over `('bank','cash','credit')` (`addons/account/models/account_payment.py:593-608`), and the action's `default_move_journal_types` key is read by no Python in v19. On a database with a credit-type journal this **fails correctly**; the log names the offenders and the decision for the Accounting Manager. |
| 4 | **TC-DEP-013** | Decision **D5-a** needs re-taking. The workbook says the deposit "detaches from the order"; v15 did that with `(5, 0, 0)`, but the 18.0 branch this port came from removed the override and ships a test asserting the links are **kept** (`sale_partner_deposit/PORTING.md` §4). The workbook also says a retained link is agreed behaviour and not a defect, so the attachment is recorded as an observation and asserted in neither direction. |
| 5 | **TC-DEP-016** | The percentage base. The code takes it on `order.amount_total` (`wizard/order_make_deposit.py:44`). The workbook asks for both figures to be reported and says not to assume a defect; both are logged whichever is seen. |
| 6 | **TC-DEP-017** | Validate is two requests — the deposit row is created and committed, then `action_post` (where the guard lives) rolls back only itself. A browser behaves the same, saving via `web_save` before calling the footer button. So a refused attempt can leave an **unposted** remnant. A **posted** one fails the assertion (the guard did not stop the money); an unposted one is reported as a separate data-hygiene finding, because no journal entry and therefore no liability stands behind it. |
| 7 | **TC-DEP-011** | Re-confirming the reset invoice re-runs the automatic application, so Amount Due may read 7,000.00 rather than the workbook's 10,000.00. Both shapes are handled, and in the 7,000.00 case the test still asserts the deposit is applied and **not also** offered — i.e. no double count. |

Findings 1, 4 and 6 are worth a workbook amendment; 3 is a decision for the
Accounting Manager; 5 is the report Novobi asked for.

---

## 7. What still needs a human

| TC | Manual step | Why |
|---|---|---|
| TC-DAT-019 | Tick the captured overrides off against the Novobi printout | The platform does not hold the printout. Only it says which contacts *should* carry a value; the inventory and a per-row verdict are in the CSV |
| TC-DAT-019 | Judge a zero vendor-side count | A database may legitimately have no vendor deposits. If the printout lists any, a zero is a P0 migration failure of the whole vendor half (MS-001) |
| TC-DAT-016 | Compare the four numbers against the Novobi baseline | Same reason. Both figures already exclude the FG06 fixture share; the per-currency breakdown is in the CSV so a total that moved while a count matched can be attributed |
| TC-DAT-016 | Judge a missing non-fixture deposit population | If the baseline lists deposits and the database holds none outside this suite's fixtures, that is the migration failure the case exists to find |
| TC-DEP-012 | Confirm the exchange rate is the one expected for today | A 1:1 company-currency amount is legal but is also what a *missing* rate looks like (`_get_conversion_rate` falls back to 1.0). The latest rate date found is printed |

All are printed into the execution log as **RESIDUAL MANUAL STEP** or
**NOTE**, never silently dropped.

---

## 8. Relationship to the module's own unit tests

`account_partner_deposit/tests/` and `sale_partner_deposit/tests/` on
`staging_19` carry TC-tagged acceptance tests written by the port
(`test_fg06_upgrade.py` in each). They run inside the Odoo test runner, which
this platform does not orchestrate (`docs/CURRENT_ARCHITECTURE.md` §8), and
they cover a different, overlapping set: TC-DEP-001, 003, 007, 010, 017 plus
TC-DEP-021/022/023/024, which are port-time additions with no row in the
client workbook.

The two are complementary rather than duplicated:

- the module tests assert **in-process ORM** behaviour with full control over
  the transaction (they can monkey-patch a method, force a withholding line,
  create a second company);
- this suite asserts what a **client tester following the workbook** gets
  through the web endpoint — including the form arch, the wizard, the pop-up's
  initial values, and the divergences in §6, none of which an in-process test
  would notice.

Where both cover a case the assertions agree; where they differ, this suite
follows the workbook and records the difference.
