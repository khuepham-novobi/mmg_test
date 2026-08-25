# FG-04 Automation Plan — Bulk Data Maintenance Wizards (Determinism Reference)

Source: `MMG_v19_Test_Cases_Grouped_by_Feature_v3.0.xlsx` → `data/test_registry.json`,
feature `FG-04`, **18 test cases** (`TC-BLK-001` … `TC-BLK-018`).
Expected results are the workbook's, verbatim — never modified here.

Suite: `tests/fg04/` (`common.py`, `test_assign_customer_taxes.py`,
`test_assign_fiscal_position.py`, `test_assign_categories.py`,
`test_update_customer_type.py`, `test_cross_wizard.py`).
Modules under test: `mmg_sale_assign_customer_taxes`,
`mmg_sale_assign_fiscal_position`, `mmg_assign_product_category`,
`mmg_assign_website_extra_category`, `mmg_sale_update_customer_type`.

FG-04 is the platform's **determinism reference suite**: it is the suite where
two identical reruns first disagreed, and the fixes that made it repeatable
(per-execution fixture namespace, defensive cleanup, version splits in
`common.py`) are the pattern the other FG suites are held to.

---

## 1. Execution strategy

- **Transport.** All 16 implemented tests are `kind="API"`: the runner drives
  `/web/dataset/call_kw` over an authenticated web session
  (`adapters/base.py`), not in-Odoo `TransactionCase` files — writing test
  files into `psus-medicine-man-gallery` (application source) is out of
  bounds for this phase. Each call commits its own transaction, so
  `cr.precommit` hooks fire per call (this is what makes the `mmg_stock`
  stored compute `website_extra_categories` observable straight after the
  wizard write in TC-BLK-009), and it is also why cleanup must always run in
  a `finally` step — there is no transaction rollback to fall back on.
  Domains are passed as **one positional list of tuples**
  (`rpc.call(model, "search_count", DOMAIN)`); m2o values read back as
  `[id, name]` and go through `m2o_id()`.
  Two workbook cases specify other harnesses and are implemented as
  documented adaptations: TC-BLK-017 (`HTTP_CASE`) uses the same `call_kw`
  endpoint with a second, non-privileged session; TC-BLK-013 (`TOUR`) asserts
  the `ir.actions.act_window` binding records that render the Action menu,
  because this platform phase has no browser tour runner.

- **Per-execution fixture namespace — the reason this suite is repeatable.**
  `tests/fg04/common.py` mints a token per execution in `sweep_fg04()`
  (`uuid4().hex[:6]`) and exposes it through `fixture_token()` / `fx(name)`.
  Every fixture name **and every value the tests count or match by** is
  wrapped in `fx()`: tax names, category names, fiscal-position names, the
  `x_type` marker strings (`FG04-SEL-OLD`, `FG04-SEL-TYPE`, `FG04-ATTRIB`,
  `FG04-Orig`) and the `BLKFILTER` search prefix
  (`("name", "like", f"{MARK} BLKFILTER%[{fixture_token()}]")`).

  *Why:* the target is `mmg_qa15`, a neutralized clone of a production copy
  (69,316 product templates, real orders/partners/invoices). On such a
  database deletion frequently **cannot** succeed — a product referenced by
  stock moves or channel listings is archived instead of unlinked
  (`framework/qa_fixtures.sweep_products` falls back to `active=False`), and a
  `product.category` / `account.tax` still referenced by that archived record
  cannot be unlinked at all. With fixtures reused by name, the leftovers of
  an earlier run were counted by the very assertions that define these tests:
  `search_count([("taxes_id","in",[new_tax])])` returned **10 where 5 was
  expected** because the previous run's five templates still carried the
  same-named tax, and the reference-fixture sweep produced **foreign-key
  violations** when it tried to remove a category/tax that an archived
  product still pointed at. Results therefore differed between two identical
  reruns. A unique namespace per execution makes each run self-contained
  regardless of what survived: whatever the sweep fails to remove belongs to
  a *different* token and can never satisfy this run's domains.

  Reference fixtures use an **ensure-by-name** pattern inside the namespace
  (`ensure_sale_tax`, `ensure_category`, `ensure_fiscal_position`): a leftover
  from a crashed run of *this* execution is reused, never duplicated.

- **Cleanup discipline.** Every test that writes data cleans up in a
  `finally:` step calling `sweep_fg04(rpc)`. The sweep is **best-effort by
  construction** — `sweep_products` archives what it cannot unlink and
  `sweep_model` swallows `OdooRPCError` — so cleanup never raises. That is
  deliberate: a raising cleanup would *replace* the verdict and turn an
  intended FAIL/BLOCKED into ERROR, destroying the baseline evidence. The
  same rule covers the restore paths (TC-BLK-007 wraps the user
  `company_ids` restore in `try/except`).

- **Snapshot + restore for every flipped config flag.** TC-BLK-002
  snapshots `res.company.account_sale_tax_id`, writes it **only if the
  company has no default**, and restores the original in `finally` (guarded
  by a `wrote_company` flag). TC-BLK-007 snapshots the acting user's
  `company_ids` and restores the exact original list. The FG-04 second
  company is a *reused* fixture, never deleted: company creation on a
  stock-enabled clone also creates warehouse data, so deletion is unsafe.

- **No inline version branches.** The v15/v19 splits live in `common.py`:
  `customer_type_method(ctx)` returns `update` on v15 and
  `action_update_customer_type` on v19 (the DW-006 rename of the method that
  shadowed `BaseModel.update()`), and `run_assign_product_categ()` drives the
  v19 select→confirm gate where the version exposes one and applies directly
  where it does not. Shared helpers (`m2o_id`, `make_trace`, `reconcile`) come
  from `framework/fg_common.py`.

- **Collected assertions.** Multi-record checks record one assertion per
  record (each with its own expected/actual) rather than aborting a loop of
  field comparisons, and the ACL matrix check in TC-BLK-017 accumulates an
  `offenders` list and asserts it once
  (`ctx.check("ACL offenders …", [], offenders)`) so a single bad ACL row does
  not hide the rest of the matrix.

- **Immutable workbook expectations.** Three cases implement expectations that
  describe the **v19 target state**; they FAIL on the v15 baseline and that
  FAIL *is* the documented baseline (they classify as `FIXED` when v19
  passes). No assertion is weakened, inverted or deleted to make v15 green,
  and every test docstring states its expected v15 outcome and why.

- **Confirmed deterministic result.** The suite was executed twice against
  `mmg_qa15`, back to back, with identical outcome both times:
  **12 PASS / 3 FAIL / 0 ERROR / 1 BLOCKED** (16 implemented tests; the same
  three FAILs with the same assertion messages, the same BLOCKED reason).
  Runs are serialized by the backend — `POST /api/runs` returns HTTP 409 if a
  run is already active on the target — because two concurrent runs sweep each
  other's fixtures mid-flight.

- **Evidence.** Every execution persists steps, assertions (expected vs
  actual), the execution log, and a traceback on error; the log carries the
  deliberate non-assertions (the TC-BLK-005 TC-DAT-019 sign-off gate, the
  TC-BLK-018 audit-trail gap, the attributed non-FG-04 seventh Action-menu
  entry). Reports are regenerated from the same rows into
  `reports/FG-04_REPORT.md`.

---

## 2. Per-test plan

Ordered by execution order (`order=400…415`), the two unimplemented cases
last. Type = automation type executed this phase: `RPC` = ORM over the
authenticated `call_kw` session; `RPC×2` = plus a second session
authenticated as another user; `RPC(meta)` = registry/ACL/binding records
instead of a browser.

| TC | Test id | Type | Fixtures / data | Core assertions | Expected v15 | Evidence |
|---|---|---|---|---|---|---|
| TC-BLK-001 | TEST-FG04-BLK-001 | RPC | `fx` old/new sale taxes; 10 `TaxTmpl` templates + 1 `TaxCtrl` control on the old tax | pre-run baseline per template; picker domain contains `type_tax_use`/`sale`; after `assign()` each template's `taxes_id == [new]` (clear-then-link **replace**); control keeps old tax; global `search_count(new tax) == 10` | PASS | 10 baseline + 10 post assertions, domain string, counts |
| TC-BLK-002 | TEST-FG04-BLK-002 | RPC | acting company; `fx` default sale tax only if the company has none | `create({})` pre-fills `taxes_id` with `env.company.account_sale_tax_id` | PASS | log of the snapshotted company value; restore step |
| TC-BLK-003 | TEST-FG04-BLK-003 | RPC | `fx` old tax; 3 `TaxGuard` templates | `taxes_id` cleared on the wizard; `assign()` raises UserError containing `Missing Customer Taxes.`; all 3 templates keep the old tax (no write) | PASS | error message captured as actual; 3 unchanged assertions |
| TC-BLK-004 | TEST-FG04-BLK-004 | RPC | 5 `TaxVar` templates + 1 control, their variants resolved | 5 variants resolved; `product_ids` branch of `assign()` replaces `taxes_id` on each; control variant unchanged; `search_count(new tax) == 5` on `product.product` | PASS | per-variant assertions + count |
| TC-BLK-005 | TEST-FG04-BLK-005 | RPC | `fx` Avatax + old positions; 10 partners (5 preset / 5 empty) + 1 control | starting positions are mixed (2 distinct); after `assign()` all 10 read the Avatax position in the acting company; control keeps its position; `search_count(position) == 10` | PASS | 10 per-partner assertions; log line for the TC-DAT-019 sign-off gate |
| TC-BLK-006 | TEST-FG04-BLK-006 | RPC | `fx` old position; 3 `FP Guard` partners | wizard `fiscal_position_id` empty; `assign()` raises UserError containing `Missing Fiscal Position.`; all 3 partners unchanged | PASS | error message + 3 unchanged assertions |
| TC-BLK-007 | TEST-FG04-BLK-007 | RPC | company A (acting) + reused `FG04 Test Company B`; company-scoped FP-A / FP-B; one shared partner | company-B preset reads FP-B; wizard run with `allowed_company_ids=[A]`; A reads FP-A; **B still reads FP-B** (no cross-company leak) | **BLOCKED** — the runner user cannot create company B (see §3) | `ctx.blocked` reason naming the missing right; user `company_ids` snapshot/restore |
| TC-BLK-008 | TEST-FG04-BLK-008 | RPC | `fx` old/new categories; 5 products + 1 control on the old category; selection via context `active_model`/`active_ids` | `wizard.state == 'select'`; direct `action_assign_product_categ()` raises UserError and writes nothing; `action_show_confirmation()` → `state == 'confirm'` and `confirm_message` names the category and the count `5`; gated apply replaces `categ_id` on exactly the 5; control unchanged | **FAIL** — v15 has no confirmation gate (v19 target expectation) | first-mismatch assertion records the missing `state` field verbatim |
| TC-BLK-009 | TEST-FG04-BLK-009 | RPC | `fx` existing + 2 new categories; 5 products + 1 control on `x_categ_ids = [existing]` | the 2 categories are **added** (`existing ∪ new1 ∪ new2`) on all 5; stored `website_extra_categories` equals the comma-joined display names of the full set on all 5; control untouched; empty pick raises UserError `Missing Website Extra Category.` and writes nothing | **FAIL** — only at the final guard: v15 is a silent no-op (v19 target expectation) | 5 set assertions + 5 compute-text assertions pass; before/after dict proves the no-op wrote nothing |
| TC-BLK-010 | TEST-FG04-BLK-010 | RPC | 5 `CustType` partners + 1 control | precondition `res.partner.x_type` exists (TC-STU-003); after the version-resolved button method all 5 carry `x_type == 'Wholesale'`; marker-scoped count `== 5`; control unchanged | PASS | precondition assertion, 5 field assertions, count |
| TC-BLK-012 | TEST-FG04-BLK-012 | RPC | 2 `TypeReq` partners with `x_type = fx("FG04-Orig")` | wizard `create()` without a value is rejected (required field at flush); `fields_get` reports `new_customer_type.required == True` (the UI blocking indicator derives from it); no partner written | PASS | rejection message; `fields_get` value; 2 unchanged assertions |
| TC-BLK-013 | TEST-FG04-BLK-013 | RPC(meta) | none (read-only registry) | the 5 wizards bind exactly the expected models (taxes → template **and** variant, FP → partner, categ → variant, web categ → variant, type → partner); every binding targets `list` views; **total binding count == 6**; the workbook's seventh entry attributed to the `mmg_stock` print server actions; negative checks (no wizard on a wrong model) | PASS | per-binding assertions; log lines attributing the print actions |
| TC-BLK-015 | TEST-FG04-BLK-015 | RPC | per wizard: 3 selected + 1 **identical-valued** control (templates/partners/products, all `fx`-named values) | for all five wizards: every selected record carries the new value; the control outside the selection is unchanged; `search_count(new value)` equals exactly 3 | PASS | 5 wizard step groups, each with per-record assertions + count |
| TC-BLK-016 | TEST-FG04-BLK-016 | RPC | 120 `fx`-named `BLKFILTER` templates (> one 80-row page) + 2 non-matching controls | the filtered domain resolves 120 ids (what the "Select all 120" banner feeds into `active_ids`); after `assign()` count of filtered templates carrying the tax `== 120`; rows 80..119 asserted individually; controls keep the old tax; global count `== 120` (nothing outside the filter) | PASS | 120-id count, 40 beyond-page assertions, control assertions |
| TC-BLK-017 | TEST-FG04-BLK-017 | RPC×2 (+meta) | plain internal user (`base.group_user` only, `framework.qa_fixtures`); dedicated FG-04 manager user (`common.ensure_fg04_manager`, credential constant in `common.py` — not reproduced here); 1 template, 1 partner, `fx` tax + position | plain user is denied `create` on the tax wizard and on the fiscal-position wizard (AccessError over `call_kw`); every binding `act_window` carries the matrix manager group in `groups_id`; no `ir.model.access` row with an empty group or `base.group_user` full CRUD (collected `offenders` list); positive control: the manager user runs both wizards successfully | **FAIL** — v15 leaves the wizards open to `base.group_user` (v19 ACL matrix, decision 3) — **security-relevant finding**, see §3 | denial attempts recorded with the actual outcome (`created — no access error`); ACL offender list; positive-control assertions |
| TC-BLK-018 | TEST-FG04-BLK-018 | RPC×2 | FG-04 manager user (id ≠ setup user); 3 `AttribTax` templates, 2 `AttribType` partners | manager differs from the setup user; the wizard's own server-side `create_date` is the "before" clock; every written template has `write_uid == manager` and `write_date >= before` and carries the new tax; same spot-check for Update Customer Type on 2 partners | PASS | pre-run `write_uid`/`write_date` log lines; per-record assertions; log line recording the audit-trail gap |
| TC-BLK-011 | — (not implemented) | n/a | needs a database where `res.partner` has **no** `x_type` field | field-missing guard raises UserError `Can not find the Customer Type field.` and writes nothing | n/a | see §4 |
| TC-BLK-014 | — (not implemented) | n/a | 1,000-record timed run at production worker limits with a manually recorded v15 wall-clock baseline | each wizard completes without a worker timeout; all 1,000 records written; wall clock ≤ v15 baseline | n/a (workbook `MANUAL` / `MANUAL_ONLY`) | see §4 |

---

## 3. Documented v15 baseline outcomes

Three FAILs and one BLOCKED are the **expected, correct** result of this suite
on v15. None of them is a defect in the automation.

| TC | v15 | Recorded assertion (from `reports/FG-04_REPORT.md`) | Cause |
|---|---|---|---|
| TC-BLK-008 | FAIL | `wizard.state`: expected `'select'`, got `"field 'state' missing — this wizard has no confirmation flow (v15 behaviour)"` | **No confirmation gate in v15.** `assign.product.categ.wizard` has no `state` / `action_show_confirmation` / `confirm_message`: the apply writes `categ_id` immediately, with no gate and no undo, on a field that drives stock valuation accounts. The two-state gate is the v19 port's fix; the workbook expectation describes it, so the v15 run documents its absence. The remaining steps (replace semantics on exactly the selection, control untouched) are asserted after the gate assertions. |
| TC-BLK-009 | FAIL | `empty pick raised UserError 'Missing Website Extra Category.'`: expected `True`, got `'no error raised'` | **No empty-pick guard in v15.** The add-semantics half passes: the two categories are added on top of `x_categ_ids` on all 5 products and the stored `website_extra_categories` compute refreshes correctly. Only the final guard step fails — a wizard created with no `product_categ_ids` is a **silent no-op** in v15 instead of raising. The before/after dict in the same step proves the no-op wrote nothing, so the failure is precisely scoped to the missing user-facing error. |
| TC-BLK-017 | FAIL | `assign.customer.taxes.wizard create denied (AccessError)`: expected `True`, got `'created — no access error'` | **Security-relevant finding.** A plain internal user (`base.group_user` only, no accounting group) **can create the customer-taxes wizard** on the v15 baseline — the wizards are not restricted to the manager groups the confirmed FG-04 ACL matrix requires, and the binding `act_window` records carry no restricting `groups_id`, so the Action-menu entries are not hidden either. Product tax configuration directly determines invoiced tax, and the fiscal position selects the tax engine for every future document of a customer. Treat this as a live-environment exposure to raise with the accountable owner, not merely as a v19 porting task: it is a *current* v15 privilege gap, and the v19 ACL matrix is the fix. The positive control (manager user runs both wizards) passes, which confirms the denial assertions fail because the restriction is absent — not because the probe is wrong. |
| TC-BLK-007 | BLOCKED | `ctx.blocked(...)` — "The runner user cannot create the second company this multi-company case needs (…)" | **Environment limitation, not a product defect.** The case needs a second company; the runner user lacks the rights to create one on the QA clone (`res.company` create is refused), and the suite refuses to invent a FAIL for an environment gap. Unblock by granting the runner user `base.group_multi_company` / Settings rights on `mmg_qa15`, **or** by pre-creating a company named `FG04 Test Company B` — the test reuses an existing one by name (company deletion is unsafe on a stock-enabled clone, so the fixture is reused across runs, never dropped). |

---

## 4. Coverage summary (reconciled with `reports/data/fg04_feasibility.json`)

| Decision | Count | Test cases |
|---|---:|---|
| `implemented` | **16** | TC-BLK-001…010, 012, 013, 015, 016, 017, 018 |
| `blocked_stub` | 0 | — |
| `not_implemented` | **2** | TC-BLK-011, TC-BLK-014 |
| **Total** | **18** | workbook FG-04 |

- **16 implemented** covers every automatable case in the feature group
  (17 automatable minus TC-BLK-011, whose precondition is unattainable here).
  One of the 16 reports BLOCKED at runtime for an environment reason
  (TC-BLK-007, §3) — the implementation exists and runs the moment the right
  is granted.
- **TC-BLK-011 — `not_implemented`.** P2. The guard requires a database where
  `res.partner` has **no** `x_type` field. The production clone carries the
  data-bearing Studio field; removing it would drop the column and destroy
  live data, which the hard rule "never modify pre-existing records"
  forbids. It needs a dedicated CI database (the module's own
  `TestUpdateCustomerTypeMissingField` class) — not this shared clone.
- **TC-BLK-014 — `not_implemented`.** Workbook `automation_type = MANUAL`,
  `automation_status = MANUAL_ONLY`: a 1,000-record timed run at production
  worker limits, compared against a manually recorded v15 wall-clock
  baseline, with live worker-log monitoring. Not automatable offline, and a
  1,000-record fixture write burst is unsuitable for the shared neutralized
  clone. The ORM-level equivalent (batched write over a large filtered
  domain) is covered by TC-BLK-016 at 120 records.
- **Odoo 19:** all 16 report BLOCKED until a local v19 environment exists
  (`docs/ENVIRONMENT_STATUS.md`). The three v15 baseline FAILs classify as
  `FIXED` the moment the v19 port passes them.

---

## 5. How to run

The user drives runs from the web UI at **http://127.0.0.1:8000** (start both
processes with `scripts\start_platform.ps1` — see `docs/GETTING_STARTED.md`).
Pick the **TARGET** (Odoo 15 / Odoo 19 / Compare) first; the choice is
remembered while navigating.

| What | Where |
|---|---|
| Whole FG-04 suite, from the feature list | Feature Groups landing page (`#/`) → the FG-04 row's `▶ RUN` button |
| Whole FG-04 suite, from the feature page | `#/feature/FG-04` → `▶ RUN FG-04` |
| One test case, from the feature page | `#/feature/FG-04` → the TC row's `▶ RUN` button |
| One test case, from its own page | `#/testcase/TC-BLK-001` → `▶ RUN TC-BLK-001` |
| One platform test script | `#/tests` → tick it → `▶ RUN SELECTED` (or `▶ RUN ALL`) |
| Everything registered | `#/` → `▶ RUN FG-01 → FG-14` |

Equivalent API calls (`POST /api/runs`, `environment` = `odoo15` | `odoo19` |
`both`):

```powershell
# whole FG-04 suite on Odoo 15  (the feature-row / feature-page RUN button)
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/runs `
  -ContentType application/json `
  -Body '{"environment":"odoo15","features":["FG-04"],"label":"FG-04 suite"}'

# one workbook test case  (the RUN TC-… button)
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/runs `
  -ContentType application/json `
  -Body '{"environment":"odoo15","test_case_ids":["TC-BLK-001"]}'

# one platform test script  (the #/tests RUN SELECTED button)
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/runs `
  -ContentType application/json `
  -Body '{"environment":"odoo15","test_ids":["TEST-FG04-BLK-017"]}'
```

The response carries `run_ids`; the live run page streams
`GET /api/runs/{run_id}/events` (SSE, replayed from persisted events on
refresh) and `POST /api/runs/{run_id}/cancel` stops it.

Notes:

- **One run at a time per target.** A second `POST /api/runs` while a run is
  active on the same environment returns **409** with the active run id —
  concurrent runs sweep each other's fixtures.
- After editing a test file, pick it up without restarting:
  `POST /api/registry/reload`.
- `environment: "both"` runs v15 then v19 as one compare group and fills the
  comparison matrix; with no local v19 the v19 half reports BLOCKED honestly.
- Regenerate `reports/FG-04_REPORT.md` from the persisted rows with
  `venv\Scripts\python.exe scripts\gen_reports.py`.
