# FG-03 Automation Plan — Sales Order Processing & Pricing

Source: `MMG_v19_Test_Cases_Grouped_by_Feature_v3.0.xlsx` → `data/test_registry.json`,
feature `FG-03`, **27 test cases**. Expected results are the workbook's,
verbatim — never modified here.

Suite: `tests/fg03/` (`common.py`, `test_discount.py`,
`test_pickup_invoices.py`, `test_auto_invoice.py`,
`test_delivery_warnings.py`, `test_o2c_regression.py`) — **25 registered
tests**, `TEST-FG03-SAL-001…023`, `TEST-FG03-STU-004`, `TEST-FG03-DAT-009`,
`TEST-FG03-DAT-010`, execution order `300…324`.

Modules under test: `mmg_sale`, `mmg_automated_action` (+ the Studio
`x_discount` layer), `mmg_sale_auto_create_invoice`,
`mmg_sale_delivery_status`, `mmg_sale_warning_extend`, plus core `sale` /
`account` for the order-to-cash and reconciliation cases.

FG-03 is held to the determinism bar set by **FG-04** (`tests/fg04/`, proven
repeatable: 12 PASS / 3 FAIL / 0 ERROR / 1 BLOCKED on two identical reruns).
Every point of that pattern — per-execution fixture namespace, defensive
cleanup, collected assertions, no inline version branches, snapshot/restore of
config flags, precise BLOCKED reasons, immutable workbook expectations,
expected-v15-outcome docstrings — is implemented here, with two additions FG-03
needed for the sales flow (consumable delivery fixtures, and a transport-loss
guard). Both are explained below.

---

## 1. Execution strategy

- **Transport.** The runner drives `/web/dataset/call_kw` over an
  authenticated web session (`adapters/base.py`), the same path a browser
  takes — not in-Odoo `TransactionCase` files, since writing test files into
  `psus-medicine-man-gallery` (application source) is out of bounds for this
  phase. Each call commits its own transaction, so `cr.precommit` hooks fire
  per call and there is no rollback to fall back on: **cleanup must always run
  in a `finally` step.** Domains are passed as one positional list of tuples
  (`rpc.call(model, "search_count", DOMAIN)`); m2o values read back as
  `[id, name]` and go through `m2o_id()`. Two cases need more than the ORM:
  TC-SAL-023 fetches the report over the authenticated HTTP session
  (`_render_qweb_pdf` returns bytes that cannot cross the JSON-RPC boundary),
  and the three reconciliation captures use read-only PostgreSQL.

- **Per-execution fixture namespace.** `tests/fg03/common.py` mints a token in
  `sweep_fg03()` (`uuid4().hex[:6]`) and exposes `fixture_token()` / `fx()` /
  `label()`. Every fixture name **and every value a test matches by content**
  carries it: customer names, product names, product attributes and their
  values, order `origin`, and every warning message the banner assertions
  search for (`fx("Message one")`, `fx("Fragile artwork …")`,
  `fx("Template-level warning")`, `fx("Handle with care")`).

  *Why:* the target is `mmg_qa15`, a neutralized clone of a production copy
  (69,316 product templates, ~43k real orders, real partners and invoices). On
  such a database deletion frequently **cannot** succeed: a product referenced
  by a confirmed order, a stock move or a posted invoice is archived instead of
  unlinked (`framework/qa_fixtures.sweep_products` falls back to
  `active=False`), and a posted-once `account.move` can never be deleted at
  all. Fixtures reused by name therefore accumulate across runs — and for a
  sales suite that is worse than a drifting count: the retired legacy
  `tests/sales` suite died exactly there, with
  `ValidationError: You cannot create order with no stock available product:
  - Product: QA AUTO PRODUCT (do not sell)`, because the previous run's stock
  moves had driven the reused product's `virtual_available` negative and
  `mmg_magento2_ept_inherit.sale.order._check_positive_quantity()` refuses the
  next order create outright. A unique namespace per execution makes every run
  self-contained regardless of what survived.

- **Delivery fixtures are consumables, never storables — and it is a
  correctness decision, not a shortcut.** `make_deliverable()` creates
  `type='consu'` products. A `type='product'` fixture is unusable on this
  clone: `mmg_magento2_ept_inherit.sale.order.create()` calls
  `_export_order_line_stock_to_magento()` for every line whose product type is
  `'product'`, which runs `product.export_stock_to_magento()` →
  `update_magento_product()`. That helper raises
  `UserError('Internal reference is required for magento synchronization')`
  for a product without `default_code`; give the fixture a `default_code` and
  it instead creates `magento.product.product` records and can walk into
  `product.category.export_category_to_magento()`, which issues a real
  Magento REST call — forbidden by AUTOMATION_CONVENTIONS hard rule 4 (never
  trigger outbound integrations). Consumables are excluded from that filter
  **and** from `_check_positive_quantity()` (both test
  `product_id.type == 'product'`), while `sale_stock` still launches the stock
  rule and still computes `qty_delivered` from stock moves for `consu` lines —
  so pending → partial (with backorder) → full → all-cancelled is reproduced
  faithfully, without stock reservation and without any run being able to leave
  a fixture in a state that breaks the next one. Fixture templates additionally
  set `stock_export_to_magento = False` where the field exists. The workbook's
  "storable product with on-hand stock" precondition is met in substance
  (transfers exist and are validated); the difference is recorded here and in
  `reports/data/fg03_feasibility.json`.

- **Collected assertions.** `ctx.check` raises on the first mismatch, which for
  this suite would be fatal to the evidence: most FG-03 tests fail their
  *second* step by design (the v19 discount formula, the missing banner field)
  and everything after it — whether delivery, invoicing, payment and the
  copy/report behaviour work at all on the baseline — would never be observed.
  Every functional test therefore records observations through
  `common.Checks.record()` (each one logged as it happens, `OK` / `DIFF`) and
  ends with `checks.assert_all()`, which re-emits every matching observation as
  its own passing assertion and then asserts the complete mismatch dict once:
  `ctx.check("mismatches vs the workbook's expected result", {}, {...})`.
  Expectations are unchanged — any mismatch still fails the test.

- **Defensive cleanup, in sale-flow order.** `sweep_fg03(rpc, ctx.log)` runs at
  test start (opening the new namespace) and again in a `finally` step. A
  raising cleanup would *replace* the verdict and turn an intended FAIL or
  BLOCKED into ERROR, so nothing in it may raise: payments (draft → cancel) →
  invoices and credit notes (`button_draft` → `button_cancel` → unlink with
  `force_delete`) → pickings (`action_cancel`) → orders (`action_cancel` with
  `disable_cancel_warning`, then unlink batch-then-record-by-record) →
  products → product attributes/values → partners. Every step is wrapped, and
  what cannot be removed is reported through `ctx.log` as
  `cleanup incomplete: …` and left behind cancelled and marker-named. The same
  rule applies to `restore_auto_invoice_flag()`.

- **Snapshot + restore of every config flag a test flips.** The only
  company-scoped setting FG-03 touches is
  `res.company.auto_create_invoice_after_confirming_so`. All 13 tests that
  confirm an order read it first (`get_auto_invoice_flag`), set the value the
  workbook prescribes, and restore the snapshot in the `finally` step
  (`restore_auto_invoice_flag`, which swallows its own failure and logs it).
  No test writes to any other pre-existing record.

- **No inline version branches.** Version-dependent access lives in
  `framework/fg_common.py` (`form_arch`, `m2o_id`, `reconcile`,
  `http_session`, `make_trace`) or in `tests/fg03/common.py`
  (`x_discount_type`, `banner_text`, `warned_products_v15`,
  `cancel_order_flow`, `validate_picking`, `picking_codes`). Test bodies read
  observables and assert the workbook's expectation; `ctx.env.version` appears
  only in log lines.

- **Preconditions are BLOCKED, never FAILED.** A missing module field
  (`require_field` → "install/upgrade `<module>` on `<env>`"), no bank/cash
  journal for the payment leg, a missing wkhtmltopdf, an unbuildable fixture
  (TC-SAL-021 points at TEST-FG03-SAL-013), an invoice that cannot be created
  or posted on this database (`invoice_or_block`), and the pure-onchange /
  performance cases (TC-SAL-006 / TC-SAL-008) all report BLOCKED with a reason
  that names what is missing and what would unblock it. One probe is also a
  safety gate: `avatax_confirm_probe()` reads the `avalara.salestax` config
  that `account_avatax_sale_oca.sale.order.action_confirm()` consults and
  blocks if `force_address_validation` is on, because that path *returns*
  `partner.button_avatax_validate_address()` — an outbound AvaTax call — and
  leaves the order in 'draft', which would surface as a false FAIL on every
  confirm assertion in this suite. (Tax *computation* is gated per order by
  `fiscal_position_id.is_avatax`; FG-03 fixture partners are created without a
  fiscal position, so nothing calls out for them.)

- **A mid-test loss of the server can only ever be ENVIRONMENT.** Run
  RUN-937DC32E lost TEST-FG03-SAL-019 and -020 to
  `web session authentication failed: connection refused` after the Odoo
  process was killed mid-run. `attempt()` deliberately swallows `OdooRPCError`
  so a *product refusal* can be recorded as the actual value of an
  assertion — but a transport failure is not a refusal, and recording it as a
  value would produce a misleading FAIL. `raise_if_transport_lost()` now
  re-raises those (urlopen/WinError/connection refused/reset/timeout/session
  authentication) as `ServerUnreachable(ConnectionError)`, which
  `backend/runner.py` classifies as `failure_class = "ENVIRONMENT"`. The same
  guard covers `x_discount_type()` and `report_response()` (whose HTTP *status
  codes* are still returned as real results — a 500 from the report engine is a
  finding, a dead socket is not).

- **Immutable workbook expectations.** 15 of the 25 tests are expected to FAIL
  on v15 because their expectation describes the **v19 target state** (the
  fixed discount formula, the native warning banner, the native 'started'
  delivery state, the BC-001 batch fixes, the coded `x_discount` field). Those
  FAILs *are* the documented baseline and classify as `FIXED` when v19 passes.
  No assertion is weakened, inverted or deleted to make v15 green, and every
  test docstring states its expected v15 outcome and why. See §3.

- **Evidence.** Every execution persists steps, assertions (expected vs
  actual), the execution log and a traceback on error; reconciliation tests
  attach their baseline JSON under `data/baselines/`. Deliberate
  non-assertions are logged, not asserted: the v15 warned-product popup ids
  (mapping evidence for TC-NEW-001), the TC-SAL-014 historical duplicate hunt,
  the AvaTax jurisdiction step owned by TC-TAX-009, and the manual UI
  walkthroughs (list column/filter/group-by, invoice tag click-through,
  Print ▸ Quotation).

---

## 2. Per-test plan

Ordered by execution order (`order=300…324`), the two unimplemented cases
last. Type: `RPC` = ORM over the authenticated `call_kw` session;
`RPC+HTTP` = plus the report endpoints over an authenticated web session;
`SQL+RPC` = read-only PostgreSQL baseline plus ORM assertions;
`SQL` = read-only reconciliation only; `probe+BLOCKED` = precondition probe
then a precise blocked reason.

| TC | Test id | Type | Fixtures / data | Core assertions | Expected v15 | Evidence |
|---|---|---|---|---|---|---|
| TC-SAL-006 | TEST-FG03-SAL-006 | probe+BLOCKED | none | `sale.order.line.x_discount` exists; the onchange path itself is not reachable | **BLOCKED** — `new()` + `_onchange_x_discount()` on an UNSAVED virtual record has no representation over `call_kw` | declared field type logged; blocked reason names the TransactionCase requirement and points at SAL-007 |
| TC-SAL-007 | TEST-FG03-SAL-007 | RPC | `fx` customer, product at 500.00, empty draft order | discount 10.00 after create; 5.00 after qty→4; 10.00 after price→250; a line with falsy `x_discount` keeps its manual 7.00; identical rewrite stable; `x_discount` preserved | **FAIL** — no create hook (0.00 where 10.00 is expected) and `price_unit`-only denominator (20.00 / 40.00) | 6 collected observations + one mismatch dict (confirmed by RUN-937DC32E) |
| TC-SAL-008 | TEST-FG03-SAL-008 | probe+BLOCKED | none | field probe only | **BLOCKED** — workbook `PERF` / `MANUAL_ONLY`: wall-clock threshold + live server-log watch, and a 500-line write burst is unsafe on the shared clone | blocked reason; correctness half covered by SAL-007's idempotence step |
| TC-SAL-019 | TEST-FG03-SAL-019 | RPC | `fx` customer + product 500.00; 3 edge-case lines; auto-invoice flag snapshotted OFF | exactly-discounted line → 100.00 / subtotal 0.00; over-discount clamped at 100.00; zero-price line 0.0 without ZeroDivisionError; order still confirms | **FAIL** — lines are created (workbook's own step), and v15 has no create hook, no clamp, no qty in the denominator | 5 observations; AvaTax probe; flag restore step |
| TC-SAL-020 | TEST-FG03-SAL-020 | RPC | `fx` customer + product 500.00; one qty-0 line | qty 0 → discount 0.0, no exception; after qty→2 the conversion resumes at 5.00 | **FAIL** — second half only: v15 computes 10.00 (qty not in the denominator); the qty-0 pass is incidental (no create hook ran) | 2 observations + mismatch dict |
| TC-STU-004 | TEST-FG03-STU-004 | SQL+RPC | read-only baseline (populated `x_discount` rows + 20 ordered samples, QA fixtures excluded); then `fx` customer/product/order | baseline captured and persisted FIRST; `x_discount` type 'float'; exactly one `ir.model.fields` row in state 'base'; write → discount 10.00; both halves persist | **FAIL** — Studio field on v15 (`state='manual'`) and the write path yields 20.00 | baseline artifact + registry rows logged; type assertion may pass, ownership assertion is the finding |
| TC-SAL-001 | TEST-FG03-SAL-001 | RPC | `fx` customer (own address) + company partner; `fx` product | write path and create path rewrite `partner_shipping_id` to the company partner; batch create rewrites ONLY the flagged record | **FAIL** — step 3 only: the v15 stack is single-vals throughout (mechanism [UNVERIFIED], outcome recorded verbatim); BC-001 is the v19 fix | 4 observations; AvaTax jurisdiction step logged (owned by TC-TAX-009) |
| TC-SAL-002 | TEST-FG03-SAL-002 | RPC | `fx` pick-up order (shipping already the gallery) | un-ticking does NOT restore the customer address (one-way); a manual correction afterwards persists | PASS | records the documented one-way baseline v19 must match |
| TC-SAL-022 | TEST-FG03-SAL-022 | RPC | confirmed `fx` pick-up order, qty 2 × 500 with `x_discount` 100 written (not created); flag OFF | copy is 'draft'; copied line carries `x_discount` 100.0 and discount 10.00; flag+address agree; cleared flag lets the address be corrected; confirmed copy total equals the original | **FAIL** — copied discount: v15 stored 20.00, so the copy carries 20.00 | 6 observations; fixture line state logged |
| TC-SAL-003 | TEST-FG03-SAL-003 | RPC | confirmed `fx` order; invoice A posted, B draft, C cancelled, R = posted credit note | `display_invoice_ids == {A, B, R}`; cancelled C excluded but still in native `invoice_ids` | PASS | id sets logged; invoicing/posting refusals BLOCK with the server's message |
| TC-DAT-010 | TEST-FG03-DAT-010 | SQL+RPC | read-only (QA fixtures excluded) | relation verified before it is queried (`fields_get` + information_schema on `sale_order_line_invoice_rel`); link-row count and `invoice_status` distribution captured/diffed; ORM spot check on the 20 lowest-id invoiced orders | PASS (captures the baseline) | baseline artifact; per-order diff dict asserted once |
| TC-SAL-013 | TEST-FG03-SAL-013 | RPC | flag snapshotted ON; one invoiceable `fx` order | state 'sale'; exactly one invoice, state 'draft'; `action_confirm` returns a window action with `res_model == 'account.move'` | PASS | returned action logged; flag restore step |
| TC-SAL-014 | TEST-FG03-SAL-014 | SQL+RPC | flag ON; 3 orders for 3 distinct `fx` customers; then 3 orders for one customer | batch confirm completes; every order 'sale' with exactly 1 invoice, 3 distinct in total; same-partner batch → exactly 1 merged invoice shared by all three | **FAIL** — the suspected defect, confirmed: the batch confirm is refused and the orders stay draft (which override refuses first is [UNVERIFIED]) | server message recorded as the actual value; read-only historical duplicate hunt logged (degrades to a log line without PostgreSQL) |
| TC-SAL-015 | TEST-FG03-SAL-015 | RPC | flag snapshotted OFF; one invoiceable `fx` order | state 'sale'; no invoice; `invoice_status == 'to invoice'`; no `account.move` redirect | PASS | returned result logged; flag restore step |
| TC-SAL-021 | TEST-FG03-SAL-021 | RPC | flag ON; confirmed order + its auto-created draft invoice (the SAL-013 flow); then 2 more | order reaches 'cancel' through the `sale.order.cancel` wizard; the invoice still exists **in state 'draft'**; multi-order cancel completes without traceback | **FAIL** — twice: v15 `_action_cancel()` button-cancels the draft invoice ('cancel', not 'draft'), and the multi-order wizard hits `{'default_order_id': self.id}` → "Expected singleton" | both outcomes recorded verbatim; fixture probe BLOCKS (pointing at SAL-013) if the fixture cannot be built |
| TC-SAL-004 | TEST-FG03-SAL-004 | RPC | 2 consumable `fx` products; flag OFF; read-only probe for an existing pick+ship warehouse | pending after confirm; partial after a backorder-creating partial validation; full after the backorder; **no status** when every transfer is cancelled; 'started' after the pick step of a two-step delivery | **FAIL** — last step only: the v15 selection has no 'started' value at all | 5 observations; delivery_status selection logged; TC-NEW-001 mapping row logged |
| TC-SAL-005 | TEST-FG03-SAL-005 | RPC | 4 `fx` orders driven to pending / partial / full / all-cancelled | `search([('delivery_status','=','full')])` returns exactly the full order; `read_group` gives one bucket per populated state with count 1 each | PASS | both queries scoped to this execution's fixture ids (the clone holds ~43k live orders); reached states logged; UI walkthrough manual |
| TC-SAL-009 | TEST-FG03-SAL-009 | RPC | `fx` warned product ('warning' + `fx` message) and an unwarned one | `sale_warning_text` names the product and carries its message; an order with only unwarned products shows no banner | **FAIL** — v15 has no order-level banner field (the retired module only has `is_show_warning_msg_box` + a popup) | field absence recorded as the actual value; v15 popup ids and flag logged as mapping evidence |
| TC-SAL-010 | TEST-FG03-SAL-010 | RPC | P1/P2 warned with distinct `fx` messages, P3 unwarned | the banner lists exactly P1 and P2, each with its own message, and never mentions P3 | **FAIL** — same cause; the "P3 absent" half passes | 5 observations; retired popup product ids logged |
| TC-SAL-012 | TEST-FG03-SAL-012 | RPC | order with exactly one warned `fx` line | banner present, empty after removing the line, present again after re-adding | **FAIL** — same cause (the middle assertion passes trivially) | documented limit: the v15 missing-`@api.depends` refresh bug is only observable in a live form, every RPC call recomputes |
| TC-SAL-011 | TEST-FG03-SAL-011 | RPC | `fx` template with 2 variants (attribute + values namespaced); flag OFF | the template warning reaches both variants; switching to 'block' makes `action_confirm` raise a UserError naming the product and leaves the order 'draft'; a fresh template defaults to 'no-message' | **FAIL** — banner absent (as SAL-009) **and** v15 core only warns through an onchange, so the confirm succeeds; the 'no-message' default passes | confirm outcome recorded verbatim; 2 variants asserted; AvaTax probe |
| TC-SAL-017 | TEST-FG03-SAL-017 | RPC | consumable `fx` product at 500.00, flag ON, payment journal probed | discount 10.00 / untaxed 900.00; one auto-created draft invoice; delivery_status pending → full; `qty_delivered` 2.0; invoice posted at 900.00; `invoice_status` 'invoiced'; payment_state paid/in_payment; posted invoice in `display_invoice_ids`; totals agree | **FAIL** — on the money only (v15: 20.00 / 800.00); the whole rest of the chain passes | 12 observations across the chain; BLOCKED instead when no bank/cash journal exists |
| TC-SAL-018 | TEST-FG03-SAL-018 | RPC | confirmed `fx` order with a POSTED invoice; flag OFF | reversal produces a posted `out_refund` linked by `reversed_entry_id`; `invoice_status` falls back to 'to invoice'; both documents in `display_invoice_ids` | PASS | standard-Odoo baseline recorded; posting/reversal refusals BLOCK or are recorded, never raised |
| TC-SAL-023 | TEST-FG03-SAL-023 | RPC+HTTP | confirmed `fx` order with a converted dollar discount; flag OFF | `/report/pdf/sale.report_saleorder/<id>` → HTTP 200 and a `%PDF-` payload; `/report/html/...` text contains the order name, the product, the converted **10.00** and the order total | **FAIL** — one assertion: the Disc.% column renders 20.00 on v15 (BLOCKED if wkhtmltopdf is absent) | HTTP statuses + payload sizes logged; Print ▸ Quotation step manual |
| TC-DAT-009 | TEST-FG03-DAT-009 | SQL | read-only (QA fixture partners excluded) | per (year, mapped state): order count, `amount_untaxed`, `amount_tax`, `amount_total`; v15 'sale'+'done' merged at capture time (v19 has no separate 'done' state) | PASS (captures the baseline) | baseline artifact; the workbook's ~43,117-order volume logged as context, never asserted |
| TC-SAL-016 | — (not implemented) | n/a | needs a SECOND company with its own invoiceable order | each order honours its own company's flag; a change in one company never leaks | n/a | see §4 |
| TC-NEW-001 | — (not implemented) | n/a | decision gate (Sales Manager + upgrade architect) | written mapping table + follow-up list; RETIRE confirmed 2026-08-12 | n/a (workbook `MANUAL` / `MANUAL_ONLY`) | consumes TEST-FG03-SAL-004's logged mapping rows |

---

## 3. Documented v15 baseline outcomes — read this before triaging the first run

On the v15 clone this suite is expected to report **8 PASS / 15 FAIL /
2 BLOCKED / 0 ERROR**. **None of the 15 FAILs is a defect in the automation**,
and only some of them are defects in the product: most are the workbook's v19
target expectations asserted against the v15 baseline on purpose, which is what
makes them classify as `FIXED` when the v19 port passes. They fall into six
families.

| Family | Tests | Why it fails on v15 | Reading |
|---|---|---|---|
| **Discount formula (the big one)** | SAL-007, SAL-019, SAL-020, SAL-022, SAL-017, SAL-023, STU-004 | Verified v15 code (`mmg_automated_action/models/sale_order_line.py`): `discount = x_discount * 100 / price_unit if price_unit else 0`, applied from `write()` and the onchange **only**. So: no `create()` hook (a line created with `x_discount` keeps discount 0.00), the **unit price** is the denominator (quantity ignored), and there is no 100 % clamp. The workbook encodes the v19 fix (FG-03 decision #4b): `x_discount * 100 / (price_unit * qty)`, clamped at 100, applied from create as well. | **Intentional v19 change, not a regression.** Historical confirmed orders/invoices are NOT recomputed by the port — only new writes use the fixed formula. TEST-FG03-SAL-007's mismatch dict (`discount after create: expected 10.0 actual 0.0`, …) was already recorded by RUN-937DC32E and is the correct baseline. |
| **Warning banner replaced** | SAL-009, SAL-010, SAL-012, SAL-011 (banner half) | `mmg_sale_warning_extend` never declared an order-level warning **text**: it adds `is_show_warning_msg_box` (a compute with no `@api.depends` — the v15 refresh bug) plus `action_open_order_lines_warning_message`, a modal listing the warned products. FG-03 decision #2 retires the module in favour of core's `sale.order.sale_warning_text` banner, which the workbook asserts. | The tests record `sale_warning_text absent on this version` as the actual value and log the v15 observables (flag + popup product ids) next to it. Asserting the v15 popup instead would make both versions pass and hide the replacement — deliberately not done. |
| **Delivery status: native 'started'** | SAL-004 (last step) | v15's `mmg_sale_delivery_status` is a stored compute over picking states with three values (pending/partial/full, plus False when every transfer is cancelled). The native v19 field adds `started` (a picking done, nothing delivered) and requires `qty_delivered` for `partial`. | Module retired 2026-08-12 (decision #1). The first four steps PASS and are the v15 half of the TC-NEW-001 mapping table; the 'started' row is recorded either as the observed value on a two-step warehouse or as "no multi-step warehouse configured" (re-configuring a live warehouse's `delivery_steps` would rewrite its stock rules — out of bounds for a fixture). |
| **Auto-invoice batch defect (BC-001)** | SAL-014 | `action_confirm` loops `for rec in self` but calls `self._create_invoices()` on the whole recordset inside the loop. The batch confirm is refused and the orders stay draft. Which override refuses first is [UNVERIFIED] — `sale._create_invoices()` raising `_nothing_to_invoice_error()` on the second pass, or `account_avatax_sale_oca.action_confirm()` reading `self.company_id` on a multi-record recordset ("Expected singleton"). | **A real v15 defect**, confirmed and fixed in v19 (BC-001). The single-order path (SAL-013) and the disabled path (SAL-015) PASS, which is what proves the defect is specific to batch confirmation. The historical duplicate hunt in the same test lists orders carrying more than one non-cancelled customer invoice for pre-go-live reconciliation. |
| **Cancel leaves the invoice cancelled** | SAL-021 | v15 `sale.order._action_cancel()` calls `inv.button_cancel()` on the draft invoices before setting the order to 'cancel', so the auto-created invoice ends in state 'cancel' where the workbook requires 'draft'. The multi-order variant additionally hits `{'default_order_id': self.id}` → "Expected singleton". | **A real v15 behaviour to flag to accounting** (the TC exists to record it as the contract). The order does reach 'cancel' and the invoice is never deleted or posted — those assertions pass. |
| **Single-vals `create` overrides** | SAL-001 (step 3) | `mmg_sale.sale.order.create` is `@api.model def create(self, vals)`; `'is_pickup_at_store' in vals` is False for a *list* of vals, and `mmg_magento2_ept_inherit.sale.order.create` (also `@api.model`) calls `res._check_positive_quantity()`, whose `ensure_one()` raises on a 2-record result. Whether Odoo 15 core wraps a method named `create` per record is [UNVERIFIED] here — the core tree is not part of this workspace — so the test asserts the workbook expectation and records the actual outcome instead of a mechanism. | BC-001 makes the v19 override `@api.model_create_multi`. Steps 1-2 (write path, create path) PASS, so a failure here is scoped precisely to the import/API batch path — the one that drives the AvaTax jurisdiction of a pick-up order. |

The two **BLOCKED** results are also correct, not gaps to be "fixed" in the
automation:

| TC | Blocked reason (abridged) |
|---|---|
| TC-SAL-006 | The TC's essence is `sale.order.line.new({...})` + `_onchange_x_discount()` asserted on an **unsaved virtual record**. `/web/dataset/call_kw` has no representation for one (the web client's onchange RPC returns a value dict, not a record, and cannot host `new()`). It runs as an Odoo `TransactionCase` only; the shared conversion path is covered by TEST-FG03-SAL-007. Faking it through a saved record would test a different code path and is refused. |
| TC-SAL-008 | Workbook `PERF` / `MANUAL_ONLY`: the verdict is a wall-clock comparison (v19 ≤ v15 × 1.2) around one timed 500-line bulk write plus a live server-log watch for `RecursionError` / `MemoryError` / nested `UPDATE sale_order_line` cascades. Neither the timing threshold nor log access exists in this runner, and a 500-line write burst on the shared production clone is not a safe automated step. |

Two further outcomes are environment-dependent and are reported honestly
rather than as product verdicts: TC-SAL-023 turns BLOCKED if wkhtmltopdf is
unavailable, and the three reconciliation captures (TC-DAT-009, TC-DAT-010,
TC-STU-004) turn BLOCKED without read-only PostgreSQL access. Anything that
loses the Odoo server mid-test reports **ERROR / ENVIRONMENT**, never FAIL —
this is exactly what happened to TEST-FG03-SAL-019/-020 in RUN-937DC32E, and
the transport-loss guard (§1) makes that classification structural instead of
accidental.

---

## 4. Coverage summary (reconciled with `reports/data/fg03_feasibility.json`)

| Decision | Count | Test cases |
|---|---:|---|
| `implemented` | **23** | TC-SAL-001, -002, -003, -004, -005, -007, -009, -010, -011, -012, -013, -014, -015, -017, -018, -019, -020, -021, -022, -023, TC-STU-004, TC-DAT-009, TC-DAT-010 |
| `blocked_stub` | **2** | TC-SAL-006, TC-SAL-008 |
| `not_implemented` | **2** | TC-SAL-016, TC-NEW-001 |
| **Total** | **27** | workbook FG-03 |

- **25 registered tests** cover every automatable case in the feature group.
  Expected v15 distribution: **8 PASS** (TC-SAL-002, -003, -005, -013, -015,
  -018, TC-DAT-009, TC-DAT-010), **15 FAIL** (all documented in §3),
  **2 BLOCKED** (TC-SAL-006, TC-SAL-008), **0 ERROR**.
- **TC-SAL-016 — `not_implemented`.** P2 / workbook `NOT_PLANNED`. Its essence
  needs a SECOND company with its own invoiceable order. On this neutralized
  production clone that means creating a `res.company`, which (a) cannot be
  swept — v15 `res.company` has no `active` flag and unlink is refused once the
  warehouse, sequences and journals created with it are referenced, leaving a
  permanent fixture in the QA database — and (b) requires adding that company
  to the runner user's allowed companies, i.e. modifying a pre-existing record.
  Both break the suite's fixture rules. Re-home it on a disposable
  multi-company sandbox, or run it manually as the workbook plans. The
  company-scoping of the flag is exercised indirectly by TEST-FG03-SAL-013 /
  -015, which snapshot and restore the flag of the order's own company.
- **TC-NEW-001 — `not_implemented`.** A decision gate, not a test: the
  keep-vs-retire decision for `mmg_sale_delivery_status` (already taken
  2026-08-12, FG-03 decision #1) is validated against staged data by a Sales
  Manager plus the upgrade architect, who produce the written mapping table and
  the follow-up list (saved filters, reports, user briefing on 'Started'). The
  workbook classifies it `MANUAL` / `MANUAL_ONLY`. Its empirical input is
  produced by TEST-FG03-SAL-004, which logs a mapping row for every delivery
  state it reaches.
- **Odoo 19:** all 25 report BLOCKED until a local v19 environment exists
  (`docs/ENVIRONMENT_STATUS.md`); the runner's preflight does that
  automatically. The 15 v15 baseline FAILs classify as `FIXED` the moment the
  v19 port passes them, and the three reconciliation baselines are captured on
  v15 now so the v19 side can diff immediately.

---

## 5. How to run

The user drives runs from the web UI at **http://127.0.0.1:8000** (start both
processes with `scripts\start_platform.ps1` — see `docs/GETTING_STARTED.md`).
Pick the **TARGET** (Odoo 15 / Odoo 19 / Compare) first; the choice is
remembered while navigating. Runs are serialized by the backend
(`POST /api/runs` returns HTTP 409 while a run is active on the target),
because two concurrent runs would sweep each other's fixtures mid-flight.

| What | Where |
|---|---|
| Whole FG-03 suite, from the feature list | Feature Groups landing page (`#/`) → the FG-03 row's `▶ RUN` button |
| Whole FG-03 suite, from the feature page | `#/feature/FG-03` → `▶ RUN FG-03` |
| One test case, from the feature page | `#/feature/FG-03` → the TC row's `▶ RUN` button |
| One test case, from its own page | `#/testcase/TC-SAL-007` → `▶ RUN TC-SAL-007` |
| One platform test script | `#/tests` → tick it → `▶ RUN SELECTED` |
| Everything registered | `#/` → `▶ RUN FG-01 → FG-14` |

Equivalent API calls (`environment` = `odoo15` | `odoo19` | `both`):

```powershell
# whole FG-03 suite on Odoo 15
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/runs `
  -ContentType application/json `
  -Body '{"environment":"odoo15","features":["FG-03"],"label":"FG-03 suite"}'

# one workbook test case
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/runs `
  -ContentType application/json `
  -Body '{"environment":"odoo15","test_ids":["TEST-FG03-SAL-007"],"label":"SAL-007"}'
```

**Suggested first run order.** TEST-FG03-SAL-013 before TEST-FG03-SAL-021 (the
latter needs the former's flow as its fixture and otherwise BLOCKS pointing at
it), and the three reconciliation tests (TC-DAT-009, TC-DAT-010, TC-STU-004)
early enough that their v15 baselines exist before the v19 environment comes
up. Everything else is order-independent: each test sweeps its own namespace at
start and cleans up in a `finally` step, and no test depends on another's
fixtures.
