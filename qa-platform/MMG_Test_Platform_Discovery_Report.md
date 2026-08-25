# MMG Odoo 15 → 19 — Cross-Version Workflow Regression Platform
## Phase 1 Deliverable: Discovery & Analysis Report

| Field | Value |
|---|---|
| Date | 2026-08-14 |
| Input analyzed | `MMG_v19_Test_Cases_Grouped_by_Feature_v2.0.xlsx` (5 sheets, 383 test cases) |
| Supporting context | `migration_assessment.md` (2026-07-29), `psus-medicine-man-gallery` addons tree, `mmg.conf` |
| Scope of this document | **Discovery only — no code.** Workbook analysis → coverage → gaps → workflow discovery → workflow map → MVP → proposed architecture |
| Next step | Your approval of §8 (MVP) and §9 (architecture), then implementation begins per §10 |

---

## 0. Executive Summary

Your workbook is an unusually strong starting point: 383 test cases, zero duplicate IDs, a flat machine-readable automation sheet, per-test automation wave/approach recommendations, and 107 features each resolved to user stories. It is emphatically **not** a "click button A, expect B" catalog — many tests already encode business outcomes ("the deposit liability is relieved", "tax posts per jurisdiction"). What it lacks is the **connective tissue**: only 2 of 383 tests are true end-to-end workflow tests (`TC-SAL-017`, `TC-SHP-034`), and the single most important one — `TC-SAL-017`, the gallery order-to-cash happy path — has **no steps written at all**. It is a placeholder.

The discovery below turns the 383 atomic tests into **11 business workflows** covering 5 cross-module value chains. 262 of the 383 tests (68%) slot into these workflows as steps, scenario variants, or outcome assertions; the remainder are migration one-offs (30), cross-version data assertions (53 — which become the platform's semantic-comparison backbone), smoke checks, security checks, UI widget checks, and performance benchmarks — each with a distinct role in the platform rather than being "workflow tests".

The recommended MVP protects the four workflows where money and stock actually move — **Gallery Order-to-Cash**, **Shopify Order-to-Cash**, **Deposit Lifecycle**, and **Inventory Sync** — plus the **Data-Integrity Comparison Backbone** (the 42 baseline-comparison tests the workbook already flags). This aligns almost exactly with the workbook's own "Wave 1 — automate now" selection (50 P0 tests in TAX/DEP/SHP/FUL/ORD/JOB), so the MVP is grounded in your own prioritization, not invented.

One system-level fact shapes everything: **Magento is being retired before the upgrade** (FG-17, `TC-NEW-006` — "execution, not decision"). The platform therefore targets the *surviving* system: Shopify + Novobi omni-addons + Avatax + deposits + the art catalogue. No Magento workflow tests will be built.

---

## 1. Workbook Analysis

### 1.1 Structure

The workbook is internally consistent and traceable. Verified programmatically:

```text
Sheet                     Rows   Role
─────────────────────────────────────────────────────────────────────
Read Me                     20   Methodology, phase model, automation conventions
Feature Groups Overview   20+1   FG-01..FG-20 + a live totals row (formulas)
Test Execution             383   THE manual-test sheet (24 columns)
User Story Coverage        107   Feature → user story → TC count
Automation Export          383   Flat snake_case mirror of Test Execution
                                 + automation_wave, automation_approach,
                                 related_features, source_notes
```

Cross-sheet consistency (all verified by script, not assumed):

```text
TC IDs unique .......................... 383/383, no duplicates
Test Execution ↔ Automation Export ..... identical ID sets, identical row order
Feature Groups totals row .............. matches sum of TC rows exactly
tc_id as stable key .................... confirmed (workbook's own convention)
```

### 1.2 Test Inventory

```text
Feature groups                20        Test cases                    383
Features (in scope)          107        User-story statements         187
Modules referenced            71        Named business roles           23
Test suites (ID prefixes)     23        Estimated atomic steps       ~584
Execution status             383 × Not Run (no run history yet)
```

Priorities and types:

```text
P0: 141   P1: 166   P2: 69   P3: 7

FUNC: 197   INTEG: 54   DATA: 49   UI: 20
SMOKE: 18   SEC: 18     REGR: 16   PERF: 11
```

Automation columns (the workbook's own assessment, which I adopt):

```text
Wave 1 — automate now      50   (P0 in TAX, SHP, DEP, FUL, ORD, JOB)
Wave 2 — candidate        219
Manual                    114   (decision gates, one-off migration tasks,
                                 perf/security reviews, visual checks)

automation_approach:
  Odoo Python test (TransactionCase) ............ 194
  Integration test vs sandbox / mocked API ....... 54
  SQL / ORM baseline comparison (v15 vs v19) ..... 42
  Odoo tour test (HttpCase / browser_js) ......... 20
  One-off migration task on the v15 clone ........ 20
  HttpCase endpoint tests + security review ...... 18
  CI boot & install check ........................ 14
  Performance harness / timed run ................ 11
  Decision gate — not automatable ................ 10
```

### 1.3 Relationship Model (as found)

```text
Feature Group (FG-01..20)
      ↓ 1:n
Feature (# 1..119, or EE/OOTB, or range, or "—")
      ↓ 1:1..n
User Story ("As a <role>, I can …, so that …")   ← 187 statements
      ↓ 1:n
Test Case (TC-<SUITE>-<NNN>)                     ← 383, stable key
      ↓ n:m (via free text)
Related TCs (53 tests reference other TCs)
Related features (44 tests carry related_features)
```

Feature-reference quality: 310 tests point at a single feature #, 29 at `EE / OOTB` (standard-Odoo regression), 24 at `—` (cross-cutting technical), 20 at ranges/multi-feature. So 81% of tests have a precise feature link; the rest are legitimately cross-cutting rather than broken links.

### 1.4 Duplicates

**No duplicate or near-duplicate test cases exist** (title-signature analysis found zero collisions; the pairs that look similar are intentionally distinct, e.g. `TC-SAL-006` vs `TC-SAL-007` test the same conversion via *onchange* vs *write* — different code paths). What does exist is **parameterization opportunity** — families that should become one automated test with a data table:

| Family | Tests | Automation shape |
|---|---|---|
| Certificate fallback matrix | TC-LBL-002..005 | 1 test × 4 provenance/date combinations |
| Avery label sizes | TC-LBL-008, 009 | 1 test × {30, 60, 90, 120}/page |
| Inventory-sync exclusions | TC-FUL-005..007 | 1 test × {product, variant, category} |
| Order import modes | TC-ORD-008..010 | 1 test × {date range, ID list, status} |
| Stock-update triggers | TC-SHP-009..011 | 1 test × {create, edit, delete} order line |
| Bulk-wizard guards | TC-BLK-003, 006, 012 | 1 test × wizard × empty-selection guard |

Curiously, the only true "duplicates" found are **in the system itself, not the test plan** — and the tests track them: duplicate Studio model `x_medium` vs code model `x.medium` (TC-STU-008), the misspelled duplicate field `x_invenory_value` (TC-STU-009), duplicate legal-date fields (TC-LEG-009).

### 1.5 Data-Quality Findings

| Finding | Count | Impact |
|---|---|---|
| Tests with **no Steps** | 36 | Mostly self-evident CRUD (ART reference data) — but includes `TC-SAL-017`, the O2C happy path, and `TC-SAL-018/021` (credit note, cancel). The most important E2E tests are the least specified. |
| Tests with no Expected Result | 1 | `TC-NEW-006` (Magento retirement — execution task) |
| Tests with no Preconditions | 332 | Acceptable for manual execution; **not** acceptable as automation input — preconditions must come from the workflow model (each step's state feeds the next) |
| Features with **0 test cases** | 4 | #9 invoice print template, #52 fulfillment log access, #54 variant price on template, #62 order dashboard shortcuts (see §4.1) |
| `v19 Watch` annotations | 85 | Excellent migration-risk metadata — these become **cross-version comparison rules** (§9.5) |
| Result columns | all "Not Run" | No execution history — the v15 baseline run does not exist yet. The platform's first milestone (§8) is exactly this. |

---

## 2. What the System Actually Is (grounding for workflow discovery)

Workflows below are inferred from the workbook **plus** the actual codebase (`psus-medicine-man-gallery`) and `migration_assessment.md` — not copied from generic Odoo. Medicine Man Gallery is an **art gallery** running Odoo 15 Enterprise with:

| Business capability | Modules (the surviving, post-Magento set) | Scale (from the workbook's own perf tests) |
|---|---|---|
| Art catalogue: ~35 custom fields (artist, medium, provenance, edition, auction data, consignment %) | `mmg_stock`, Odoo Studio layer, `mmg_automated_action` | 69,201 product templates |
| Certificates of authenticity + Avery labels/backtags | `mmg_report`, `report_py3o` (LibreOffice pipeline) | 4 ODT templates, 5 label formats |
| Gallery sales: dollar-discount field, pick-up-at-store, warnings, auto-invoice-on-confirm | `mmg_sale*`, `mmg_sale_auto_create_invoice`, Studio `x_discount` | 43,117 sales orders |
| US sales tax per jurisdiction | `account_avatax_oca` + `account_avatax_sale_oca` + `mmg_account_avatax_enhancement` (full override of tax-line mapping, zero tests today) | compliance-critical |
| Customer/vendor deposits (high-value art) | `account_partner_deposit`, `sale_partner_deposit` | GL-reconciled liability |
| Invoicing & payments, MMG invoice layout, default payment journal, "In Payment"→"Paid" relabel | `mmg_account`, `mmg_change_invoice_template`, `mmg_default_payment_journal`, `mmg_change_ui` | 109,218 account moves |
| Shopify storefront: listings, metafields (art attributes!), orders, fulfillment, inventory | `multichannel_*`, `omni_*` (Novobi omni-addons), `mmg_multichannel_shopify` | 17,868 listings |
| Order automation: process rules confirm/invoice/pay by channel status | `multichannel_order` process rules | operations backbone |
| Async platform + audit | `queue_job` (OCA) + `queue_job_enhancement`, `omni_log` | all channel I/O is queued |
| Legal-date compliance | Automated actions 663/664 (Legal Sale/Invoice Date) | audit-relevant |

Context that constrains the platform design: custom code has **near-zero existing automated tests** (4 of 29 top-level custom modules have any test files; the 12 omni-addons have none) — so the workflow platform is the *only* safety net; the migration path is **4 hops** (15→16→17→18→19), so tests must be cheap to re-run per hop; and the Magento/`saas_*`/`medicinemangallery_customization` stack is **decommissioned before upgrade** (FG-17 gates everything — after decoupling, ART/LBL/SHP suites must be re-run, per TC-DEC-003/004).

---

## 3. Existing Coverage

### 3.1 By feature group (from the workbook, verified)

| Group | Name | TCs | P0 | Wave 1 | Wave 2 | Manual | Reading |
|---|---|--:|--:|--:|--:|--:|---|
| FG-01 | Art Catalogue & Product Master Data | 36 | 6 | 0 | 21 | 15 | Broad CRUD/field coverage; heavy Studio-preservation load |
| FG-02 | Certificates & Label Printing | 13 | 7 | 0 | 12 | 1 | Fallback matrix fully enumerated — best-designed group |
| FG-03 | Sales Order Processing & Pricing | 27 | 8 | 0 | 18 | 9 | Strong atomic coverage; E2E anchor is an empty placeholder |
| FG-04 | Bulk Data Maintenance Wizards | 18 | 3 | 0 | 12 | 6 | Complete per-wizard grid incl. guards + ACL |
| FG-05 | Tax — Avalara AvaTax | 20 | 14 | 13 | 7 | 0 | Highest P0 density; posting guards well covered |
| FG-06 | Customer & Vendor Deposits | 23 | 11 | 8 | 12 | 3 | Near-complete lifecycle; vendor side thinner |
| FG-07 | Invoicing, Payments & Accounting Docs | 25 | 7 | 0 | 16 | 9 | Half is cross-version data assertions (right idea) |
| FG-08 | E-commerce Channel Management | 13 | 3 | 0 | 11 | 2 | Config/onboarding/safe-mode covered |
| FG-09 | Product Listings & Channel Catalogue | 24 | 6 | 0 | 19 | 5 | Import/export/merge covered atomically |
| FG-10 | Shopify Storefront Integration | 33 | 13 | 13 | 15 | 5 | Largest suite; has the one real E2E (TC-SHP-034) |
| FG-11 | Omnichannel Order Processing | 23 | 6 | 5 | 15 | 3 | Process-rule engine well covered |
| FG-12 | Fulfillment & Inventory Sync | 18 | 6 | 6 | 11 | 1 | Delta/bulk/caps/exclusions covered |
| FG-13 | Background Job Platform | 20 | 6 | 5 | 9 | 6 | Infrastructure — strongest "platform" suite |
| FG-14 | Integration Monitoring & Logging | 10 | 4 | 0 | 8 | 2 | Recovery actions covered |
| FG-15 | UI Widgets & Client Framework | 12 | 2 | 0 | 4 | 8 | OWL2 rewrite risk → mostly tours/manual |
| FG-16 | Studio Layer & Legal Dates | 17 | 7 | 0 | 4 | 13 | Data preservation + 5 open decisions |
| FG-17 | Decommissioning & Legacy Cleanup | 15 | 14 | 0 | 0 | 15 | One-off migration gates — correctly all manual |
| FG-18 | Platform Migration & Smoke | 15 | 8 | 0 | 13 | 2 | Becomes the CI boot/smoke stage |
| FG-19 | Security & Access Control | 13 | 8 | 0 | 12 | 1 | Maps to the assessment's live security findings |
| FG-20 | Performance & Volume | 8 | 2 | 0 | 0 | 8 | Benchmarks with real production volumes |

### 3.2 Test-level classification (PART 7 of your brief)

Rule-based classification of all 383 tests (suite + type + automation_approach), before per-test curation:

```text
Atomic functional (reusable action / assertion candidates) ... 179
Workflow steps / E2E scenario components (INTEG + REGR) ......  69
Cross-version data assertions (semantic-compare backbone) ....  53
Migration gates & one-offs (DEC/LEG/NEW, not regression) .....  30
UI widget checks (OWL2 risk surface) .........................  20
Security checks ..............................................  18
Smoke / environment checks ...................................  14
```

Implications, per your MOST IMPORTANT PRINCIPLE: only ~250 tests belong in the *workflow* regression suite at all. The 30 migration gates are a **checklist app**, not tests. The 53 data assertions are the **comparison engine's rule set**. The 18 security tests are a **fixed post-upgrade gate**. Nothing gets blindly converted into UI clicks.

### 3.3 What is already covered well

Covered and reusable as-is: the Avatax posting guard set (block on mismatch, unmappable line, multi-account distribution, incomplete address); the deposit money-lifecycle (record → apply → relieve liability → GL reconcile); the process-rule engine matrix (status → confirm/invoice/pay, first-match-wins); inventory-sync shaping (percentage, caps, exclusions, delta-by-stock-move); certificate fallback matrix; queue-job failure semantics (identity key, retry policy, lock-contention → postponed); the migration DAT baseline set (trial balance, aging, order totals by year/state, stock on hand, valuation).

---

## 4. Coverage Gaps

### 4.1 User-story gaps (workbook's own signal: 0 primary TCs)

| Feature # | Module | Feature | Assessment |
|---|---|---|---|
| 9 | mmg_change_invoice_template | customer invoice print template | Real gap only on paper — TC-INV-001..003 exercise the layout but are keyed to feature #8. Fix the trace link, add one template-selection test |
| 52 | multichannel_fulfillment | inventory-export log access | Genuine small gap — add 1 test (log created per export, linked from listing) |
| 54 | multichannel_manage_price | variant price on template view | Genuine small gap — add 1 test (price propagation template↔variant) |
| 62 | multichannel_order | dashboard, import/shipment log shortcuts | Low-risk UI shortcut — fold into the UIX tour |

### 4.2 Structural gaps (what the workbook cannot see about itself)

**G1 — The E2E anchors are placeholders.** `TC-SAL-017` (Quotation → confirm → deliver → invoice → pay) has no steps, no preconditions, no role. `TC-SHP-034` has one line of steps. These two ARE the migration-critical workflows; today they carry ~1% of the specification weight they need. This is the single largest gap and the core of Phase-2 work.

**G2 — Assertions stop at the module boundary.** Atomic tests verify their own module's outcome but almost never the downstream ledger/stock effect. Examples: `TC-SAL-013` (auto-invoice created) never asserts the invoice *posts and the GL entry balances*; `TC-SHP-029` (fulfillment posts to Shopify) never asserts the Odoo picking's `done` quantities reconcile with the pushed payload; only `TC-DEP-014` and the DAT suite reach the GL. Workflow tests must add the cross-module outcome assertions (order.state, picking.state+qty, move.state+jurisdiction lines, payment reconciliation, stock quant delta, listing publish state) after *every* scenario.

**G3 — No idempotency / duplicate-import scenario.** The #1 real-world channel failure mode — the same Shopify order imported twice (webhook retry, manual + cron overlap) — has no test. `TC-JOB-007` (identity key) covers the mechanism, not the business behavior (no duplicate SO, no double invoice).

**G4 — Partial-everything is missing.** No partial delivery, no partial invoice, no partial refund, no split fulfillment across scenarios in FG-03/FG-10/FG-11/FG-12. For an art gallery selling one-off pieces this is *less* central than in wholesale — but multi-line Shopify orders make partial fulfillment a real path.

**G5 — Payment-provider failure paths.** `TC-INV-010` checks providers migrate; nothing tests a failed/declined payment transaction's effect on order/invoice state.

**G6 — Concurrency & races.** Only `TC-FUL-010` (in-progress marker) and `TC-JOB-010` (lock contention) touch it. Missing: simultaneous stock-consuming order + inventory sync (oversell window), double-click on Confirm with auto-invoice enabled (the suspected defect in `TC-SAL-014` makes this more likely to matter).

**G7 — The 36 step-less tests** (§1.5) need steps authored before or during automation — 13 of them are P0/P1 REGR tests in the O2C chain.

**G8 — Trace-link hygiene.** 4 features with 0 TCs (§4.1); 76 tests with non-single feature refs are fine, but the feature-#9 case shows at least one mis-keyed link. One normalization pass fixes this.

### 4.3 Missing scenario classes (summarized; per-workflow detail in §5)

```text
Scenario class          Status across the suite
──────────────────────────────────────────────────────────────
Happy path              ⚠  exists atomically, E2E anchors unspecified (G1)
Alternative paths       ✅ unusually good (cancel ×2 modes, replacement,
                            return wizard, reset-to-draft, requeue…)
Negative paths          ✅ good (posting guards, empty-selection guards,
                            missing product, API outage, invalid ranges)
Boundary                ⚠  some (100% discount, qty 0, deposit > invoice,
                            min/max caps) — missing zero-stock publish edge,
                            same-day legal dates, tax rounding at $0.005
Permissions             ⚠  SEC suite is strong on endpoints/groups;
                            missing per-workflow role walk-throughs
Multi-company           ⚠  scattered (SAL-016, BLK-007, JOB-017, DEP-002/15)
Multi-currency          ⚠  only DEP-012; system is USD-centric — confirm scope
Exception & recovery    ✅ LOG/JOB suites cover this well
Data integrity          ✅ DAT suite is the backbone (by design)
Concurrency             ❌ G6
Idempotency             ❌ G3
Partial flows           ❌ G4
```

---

## 5. Workflow Discovery — the Workflow Catalog

Method: TC titles/steps/preconditions were mined for entity chains (order → picking → invoice → payment), state transitions ("confirm", "post", "validate", "reconcile"), `related_features` links, cross-TC references (53 found), role sequences, and the module dependency graph from the codebase. Result: **11 workflows** — 8 business, 3 platform. 262 of 383 tests (68%) participate in at least one workflow (tests can serve several: e.g. TC-TAX-010 is a step-assertion in both O2C workflows).

Coverage % below = (covered + 0.5·partial) / applicable scenario slots for that workflow, from the per-workflow grids. Detail level: full spec for the four MVP workflows; condensed for the rest (full YAML for all 11 in the companion catalog file).

### WF-O2C-GALLERY — Gallery Direct Sale, Order to Cash 【P0 — MVP】

```yaml
workflow_id: WF-O2C-GALLERY
business_domain: Sales → Inventory → Tax → Accounting → Documents
business_goal: >
  A gallery salesperson sells an art piece (in gallery or by phone),
  the item ships or is picked up, tax is computed per US jurisdiction via
  Avalara, the invoice is issued (auto-created on confirm), payment is
  registered and reconciled, legal dates are stamped for compliance, and
  a certificate of authenticity can be printed citing this sale.
actors: [Gallery Salesperson, Inventory Manager, Accountant, Gallery Manager]
starting_state: Customer exists or is created; art item in stock (qty 1 typical)
ending_state: >
  sale.order=sale & fully delivered/invoiced · stock.picking=done ·
  account.move=posted with per-jurisdiction tax lines · payment reconciled
  (payment_state in_payment/paid) · Avalara transaction committed ·
  Legal Sale/Invoice Dates stamped · certificate cites this sale
steps:  # each step maps to existing TCs (traceability preserved)
  - create_or_select_customer          # (fiscal position, avatax exempt status)
  - create_quotation                   # TC-SAL-017
  - add_art_item_line                  # unique piece, qty 1
  - apply_dollar_discount              # TC-SAL-006/007/008, TC-STU-004 (x_discount)
  - set_delivery_or_pickup             # TC-SAL-001/002 (Pick up at Store)
  - preview_avatax                     # TC-TAX-008
  - confirm_order                      # → auto-invoice TC-SAL-013/014/015/016
  - validate_delivery                  # → Legal Sale Date TC-LEG-005
  - create_or_verify_invoice           # TC-TAX-010 carry-over, TC-LEG-006
  - post_invoice                       # TC-TAX-011 commit, TC-TAX-002/003 jurisdiction lines
  - register_payment                   # TC-INV-006 default journal, TC-INV-008 multi
  - print_certificate                  # TC-LBL-007 (cites most recent confirmed sale)
assertions:
  - order.state == sale; delivery_status == delivered (TC-SAL-004)
  - picking.state == done; product qty decremented; quant vendor visible (TC-ART-006)
  - invoice posted; tax lines per jurisdiction == Avalara summary (TC-TAX-002/004)
  - payment reconciled; payment_state mapping v19-reviewed (TC-DAT-006/TC-INV-005)
  - GL: receivable cleared, tax payable per jurisdiction account
  - legal_sale_date == delivery completion date; legal_invoice_date propagated
related_existing_tests: 53 TCs (23 P0) across SAL/TAX/INV/LEG/LBL/STU/DAT suites
coverage: 72%   priority: P0   risk: highest (revenue + tax compliance + 4-hop drift)
automation_potential: HIGH — pure Odoo RPC; Avalara sandbox or recorded-replay
```

Scenario grid (existing ✓ / partial ⚠ / missing ❌):

| Scenario | Status | Evidence / what to add |
|---|---|---|
| Happy path E2E | ⚠ | TC-SAL-017 exists but **step-less** — specify & automate first |
| Dollar discount (onchange, write, bulk) | ✓ | TC-SAL-006/007/008 + boundary TC-SAL-019/020 |
| Pick up at store | ✓ | TC-SAL-001/002 |
| Auto-invoice on/off/per-company | ✓ | TC-SAL-013/015/016 |
| Multi-order confirm (suspected defect) | ✓ | TC-SAL-014 — keep as known-bug scenario (§9.6) |
| Tax preview / recompute / carry-over / commit / void | ✓ | TC-TAX-008/009/010/011/012 |
| Posting guards (mismatch, unmapped, multi-account) | ✓ | TC-TAX-004/005/006 |
| Exempt customer; mixed lines | ✓ | TC-TAX-013/016 |
| Avalara outage → graceful failure | ✓ | TC-TAX-017 |
| Cancel confirmed order (with auto-invoice) | ✓ | TC-SAL-021 (step-less) |
| Credit note + refund tax account | ✓ | TC-SAL-018 + TC-TAX-015 |
| Legal dates (incl. posted-invoice rewrite question) | ✓ | TC-LEG-005/006/007 (007 = open business question) |
| Certificate cites the sale | ✓ | TC-LBL-007 |
| Partial delivery / partial invoice | ❌ | add scenarios (multi-line, qty>1) |
| Payment failure / decline | ❌ | add (provider tx failed → order/invoice state) |
| Concurrent confirm double-click | ❌ | add (pairs with TC-SAL-014) |
| Permissions walk-through (salesperson can't post) | ❌ | add role-boundary scenario |
| Multi-currency | ❌ | confirm with business — likely out of scope (USD) |

### WF-O2C-SHOPIFY — Shopify Order Import to Cash & Sync-Back 【P0 — MVP】

```yaml
workflow_id: WF-O2C-SHOPIFY
business_domain: Shopify → Orders → Payments/Deposits → Tax → Fulfillment → Inventory → Shopify
business_goal: >
  A paid Shopify order enters Odoo automatically, process rules confirm /
  invoice / register payment per channel status, the pickings are fulfilled
  and posted back to Shopify with tracking, inventory decrements and the
  listing unpublishes at zero stock — with every hop queued, logged, and
  recoverable.
actors: [E-commerce Manager, Operations Manager, Warehouse Operator, Accountant, Integration Admin]
starting_state: Connected Shopify store (or replay fixture); listed product with stock
ending_state: >
  sale.order=sale w/ channel refs & gateway transactions · invoice posted &
  paid via mapped journal/deposit account · picking done · fulfillment posted
  to channel w/ tracking · channel qty decremented · listing state correct ·
  queue jobs done · omni_log clean
steps:
  - place_or_inject_channel_order        # dev store or recorded payload
  - import_orders                        # TC-SHP-026, TC-ORD-001 (lines: tax/ship/discount/fees)
  - resolve_customer                     # TC-ORD-014 guest/default, TC-CHN-007/008 mirror
  - apply_order_defaults                 # TC-ORD-015 prefix/team/salesperson, TC-ORD-016
  - run_process_rules                    # TC-ORD-002/003/004 confirm/invoice/pay, first-match
  - map_payment_gateway                  # TC-ORD-005 journal/method/deposit, TC-DEP-019
  - fulfill_picking                      # TC-SHP-029 / TC-SHP-030 (service)
  - export_fulfillment                   # TC-FUL-013/014/015 tracking, change-detection
  - sync_inventory_back                  # TC-SHP-009..012 triggers, TC-SHP-007/008 (un)publish
  - verify_status_roundtrip              # TC-ORD-017/018 store/payment/shipping status
assertions:
  - one SO per channel order (idempotent re-import — NEW, G3)
  - amounts: channel total == SO total == invoice total (± tax config, TC-SHP-025)
  - only rule-matching orders progressed, exactly as far as the rule allows
  - queue.job all done (TEST_QUEUE_JOB_NO_DELAY in CI); omni_log has no unresolved failures
  - stock decremented once; listing published state matches stock
related_existing_tests: 46 TCs (16 P0) across SHP/ORD/FUL/DEP/CHN/JOB/DAT
coverage: 78%   priority: P0   risk: highest operational (order intake = revenue)
automation_potential: HIGH via replay-mode (recorded API cassettes); MEDIUM live-sandbox
```

Scenario grid:

| Scenario | Status | Evidence / what to add |
|---|---|---|
| Happy path E2E | ✓ | TC-SHP-034 (steps exist; needs assertion depth) |
| Import modes (range / IDs / status) | ✓ | TC-ORD-008/009/010 (parameterize) |
| Line fidelity (taxes, shipping, discounts, fees) | ✓ | TC-ORD-001 |
| Process-rule matrix + sequence | ✓ | TC-ORD-002/003/004, TC-DAT-018 |
| Gateway → journal / deposit mapping | ✓ | TC-ORD-005, TC-DEP-019 |
| Settlement report import | ✓ | TC-ORD-006/007 |
| Guest customer; address update; missing product | ✓ | TC-ORD-014/021/022 |
| Cancel online order (±credit note, email) | ✓ | TC-ORD-011/012 |
| Replacement order | ✓ | TC-ORD-013 |
| Return via wizard | ✓ | TC-SHP-028 |
| Fulfillment export + change detection + service picking | ✓ | TC-FUL-013/014, TC-SHP-029/030 |
| Stock triggers & (un)publish | ✓ | TC-SHP-007..012 |
| Location→warehouse mapping | ✓ | TC-SHP-027 |
| OAuth connect / API version | ✓ | TC-SHP-001/033, TC-SEC-001 |
| **Duplicate import (idempotency)** | ❌ | add — top real-world failure (G3) |
| Partial fulfillment (multi-line split) | ❌ | add (G4) |
| Refund flows through to Avalara void | ❌ | add (channel credit note → TC-TAX-012 behavior) |
| Oversell race (order vs sync) | ❌ | add later (G6, hard) |
| Failed import recovery E2E | ⚠ | pieces exist (LOG-002/004, CHN-009) — chain them |

### WF-DEPOSIT — Customer/Vendor Deposit Lifecycle 【P0 — MVP】

```yaml
workflow_id: WF-DEPOSIT
business_domain: Sales/Purchase → Payments → Accounting (liability)
business_goal: >
  The gallery takes a deposit on a high-value piece (fixed or % of order,
  sometimes via a channel payment gateway), tracks it as a liability,
  applies it to the eventual invoice, bills the balance, and the GL
  reconciles — including cancel/reset paths.
steps: record_deposit (or from SO fixed/% wizard, or channel-mapped) →
       verify_outstanding_on_contact → create_invoice_from_order →
       apply_deposit → bill_balance → verify_gl_liability_relieved
alt_paths: cancel_deposit · reset_payment/JE_to_draft · multiple_deposits ·
           deposit > invoice total · vendor-side deposit on PO
related_existing_tests: 22 TCs (10 P0) — DEP suite + TC-DAT-016/019
coverage: 79%   priority: P0
risk: high — money held in liability; native-down-payment convergence
      decision pending (TC-NEW-004 🔻, v19 has native down payments)
automation_potential: VERY HIGH — pure accounting, fully deterministic, no
                      external APIs; ideal first TransactionCase conversions
missing: [refund deposit to customer, vendor deposit full E2E to bill,
          permissions (who may cancel), multi-currency beyond DEP-012]
```

### WF-INVSYNC — Stock Change → Channel Quantity 【P0 — MVP】

```yaml
workflow_id: WF-INVSYNC
business_domain: Inventory → Queue Jobs → Channel (Shopify)
business_goal: >
  Any stock change (sale, receipt, adjustment) reaches the storefront
  correctly shaped (sync %, min/max caps, exclusions) and on time (delta
  cron, bulk sync) — the anti-oversell workflow for one-of-a-kind art.
steps: configure_channel_sync (warehouse, %, caps, exclusions) →
       move_stock → run_delta_sync → verify_pushed_qty_and_timestamp →
       bulk_sync_with_lock → verify_listing_publish_state
related_existing_tests: 19 TCs (7 P0) — TC-FUL-001..012 + TC-SHP-012/013/018,
                        TC-PIM-012/013/015, TC-CHN-010 (+ JOB infra via WF-JOBS)
coverage: 74%   priority: P0
risk: high — silent overselling / stale storefront stock
automation_potential: HIGH in replay mode (assert computed payload);
                      queue-job semantics already test-supported (TC-JOB-018)
missing: [zero/negative boundary, multi-warehouse aggregation,
          concurrent sync vs order race (G6), FTP delivery in CI (mock FTPS)]
```

### The remaining 7 workflows (condensed)

| Workflow | Chain | Existing TCs | Cov. | Pri | Notes |
|---|---|--:|--:|---|---|
| WF-PIM-PUBLISH — Art item → listing → storefront | ART master data → categories → images → listing map → price → export (metafields!) → publish | 33 | 75% | P1 | No E2E anchor test exists — author one. Metafield compare/delete already covered (TC-SHP-004/005/006) |
| WF-CATALOG — Art-catalogue master-data maintenance | create/import → ~35 fields → template↔variant sync → barcode rules → reference data → archive | 26 | 88% | P1 | Mostly atomic by nature; barcode + variant-sync are the workflow-ish parts. 69k-record scale → PERF-001 |
| WF-CERT — Certificates & labels after sale | sold item → certificate (4-way fallback) → Avery labels/backtags | 13 | 90% | P1 | Business-critical documents; py3o→v19 strategy pending (LibreOffice SPOF, TC-NEW-005). Render-assert via PDF text extraction |
| WF-RECOVERY — Failed integration op → recovery | op fails → omni_log entry w/ payload → inspect → re-import/re-export/batch → resolve; queue requeue/GC | 16 | 82% | P1 | Chain exists piecewise; author 1 E2E: kill API mid-order-import → recover → order completes intact |
| WF-BULK — Bulk maintenance wizards | select records → wizard (taxes/fiscal position/categories/customer type) → guarded bulk write → audit | 18 | 88% | P2 | Self-contained; cheap TransactionCase wins; ACL + 1,000-record perf covered |
| WF-CHANNEL-OPS — Channel onboarding & health | connect (OAuth) → configure → safe mode → monitor crons → dashboards → disconnect | 12 | 84% | P2 | Safe mode (TC-CHN-003) is a **platform prerequisite** — see §9.8 |
| WF-JOBS — Async job backbone | enqueue → channels/capacity → run → fail → retry policy → identity dedupe → GC | 20 | 92% | P1* | *Not business-visible but everything Shopify rides on it; OCA rebase on v19 makes parity checks cheap and vital |

### Platform suites (not workflows — different execution semantics)

| Suite | Tests | Platform role |
|---|---|---|
| DATA-INTEGRITY (DAT + data-typed STU/INV/DEP/CHN…) | 53 | **Semantic-comparison backbone** — §9.5. Run once per migrated DB, not per workflow |
| SMOKE (SMK + CI boot checks) | 18 | Stage-0 gate of every run: boot, installability, menus, assets, endpoints |
| SECURITY (SEC + HttpCase endpoint checks) | 18 | Post-upgrade gate; doubles as remediation verification for the assessment's §6 findings (auth-bypass, `verify=False`, open webhooks) |
| PERF (8) | 8 | Nightly benchmark vs v15 timing baseline at production volumes |
| MIGRATION GATES (DEC/LEG/NEW + one-offs) | 30 | Tracked as a runbook checklist in the dashboard, never "automated" |

---

## 6. Core Workflow Map (cross-module)

```text
                     ┌────────────────────────────────────────────────┐
                     │        ART CATALOGUE (69,201 items)            │
                     │  WF-CATALOG: fields · variants · barcodes ·    │
                     │  consignment/vendor cost · images · categories │
                     └───────┬───────────────────────────┬────────────┘
                             │ WF-PIM-PUBLISH            │ in-gallery sale
                             ▼                           ▼
        ┌────────────────────────────┐      ┌─────────────────────────────┐
        │  CHANNEL LISTING (17,868)  │      │  GALLERY QUOTATION           │
        │  map · price · metafields  │      │  $ discount · pickup/ship    │
        │  publish/unpublish         │      │  warnings · deposit taken    │
        └───────┬──────────▲─────────┘      └──────────┬──────────────────┘
                │          │ WF-INVSYNC                │ WF-O2C-GALLERY
   WF-O2C-      │          │ (qty, caps,               ▼
   SHOPIFY      ▼          │  exclusions)   ┌─────────────────────────────┐
        ┌──────────────┐   │                │ CONFIRM → AUTO-INVOICE      │
        │ SHOPIFY ORDER│   │                │ AVATAX preview→commit       │
        │ import·rules │   │                │ per-jurisdiction lines      │
        │ confirm/inv/ │   │                └──────────┬──────────────────┘
        │ pay·gateway→ │   │                           │
        │ journal+dep  │   │                           ▼
        └──────┬───────┘   │                ┌─────────────────────────────┐
               ▼           │                │ DELIVERY (legal sale date)  │
        ┌──────────────┐   │                │ → INVOICE (legal inv date)  │
        │ FULFILLMENT  │───┘                │ → POST → PAYMENT → RECONCILE│
        │ pick·ship·   │  stock moves       │ → deposit applied (WF-DEP)  │
        │ tracking→    │                    └──────────┬──────────────────┘
        │ channel      │                               │
        └──────┬───────┘                               ▼
               │                            ┌─────────────────────────────┐
               └──────────────────────────▶ │ ACCOUNTING (109,218 moves)  │
                                            │ GL · tax payable by juris-  │
                                            │ diction · deposits · aging  │
                                            └──────────┬──────────────────┘
                                                       │ after sale
                                                       ▼
                                            ┌─────────────────────────────┐
                                            │ CERTIFICATE OF AUTHENTICITY │
                                            │ + labels (WF-CERT, py3o)    │
                                            └─────────────────────────────┘

   Riding under everything:   WF-JOBS (queue_job) · WF-RECOVERY (omni_log)
   WF-CHANNEL-OPS (config/safe-mode) · WF-BULK (mass maintenance)
   Cross-version backbone:    DATA-INTEGRITY suite (v15 baseline ↔ v19)
```

Two chains cross the most module boundaries and therefore carry the most migration risk: **Gallery O2C** (Sales → Studio field → Avatax → Inventory → automated-action legal dates → Accounting → py3o documents — 7 subsystems, 4 of which change shape between v15 and v19) and **Shopify O2C** (channel API → queue jobs → orders → payments/deposits → fulfillment → inventory → channel API — a full round trip through the OWL2-rewrite and OCA-rebase surface).

---

## 7. Workflow Coverage Report

```text
WORKFLOW COVERAGE (existing atomic coverage folded into workflow view)

Workflow                          TCs   P0   Coverage   Priority
─────────────────────────────────────────────────────────────────
WF-JOBS       Queue backbone       20    6      92%        P1*
WF-CERT       Certificates         13    7      90%        P1
WF-CATALOG    Art master data      26    3      88%        P1
WF-BULK       Bulk wizards         18    3      88%        P2
WF-CHANNEL-OPS Channel config      12    5      84%        P2
WF-RECOVERY   Failure recovery     16    7      82%        P1
WF-DEPOSIT    Deposits             22   10      79%        P0 ◀ MVP
WF-O2C-SHOPIFY Shopify O2C         46   16      78%        P0 ◀ MVP
WF-PIM-PUBLISH Listing publish     33    7      75%        P1
WF-INVSYNC    Inventory sync       19    7      74%        P0 ◀ MVP
WF-O2C-GALLERY Gallery O2C         53   23      72%        P0 ◀ MVP
─────────────────────────────────────────────────────────────────
Platform suites: DATA-INTEGRITY 53 · SMOKE 18 · SEC 18 · PERF 8
Migration gates (checklist, not tests): 30
```

Read this table the right way round: the four **lowest-coverage** workflows are also the four **highest-risk** ones — coverage is inversely correlated with risk today, which is exactly why they are the MVP. The percentages measure *scenario-slot* coverage (happy/alt/negative/boundary/permission/…), not test counts; the biggest single deduction everywhere is the unspecified E2E happy path (G1) and the missing cross-module outcome assertions (G2).

Missing-scenario summary for the MVP four (from §5 grids):

```text
WF-O2C-GALLERY   ❌ partial delivery/invoice   ❌ payment failure
                 ❌ concurrent confirm         ❌ role walk-through   ⚠ E2E steps
WF-O2C-SHOPIFY   ❌ duplicate import           ❌ partial fulfillment
                 ❌ refund→Avalara void        ❌ oversell race       ⚠ recovery chain
WF-DEPOSIT       ❌ deposit refund             ❌ vendor E2E
                 ❌ cancel permissions         ⚠ multi-currency
WF-INVSYNC       ❌ zero/negative boundary     ❌ multi-warehouse
                 ❌ concurrent sync race       ⚠ FTPS in CI (mock)
```

---

## 8. Recommended MVP

**Scope: 4 workflows + 1 backbone + 1 gate — full pipeline, both versions.**

| # | Item | Why this one | Scenarios (target) |
|---|---|---|---|
| 1 | **WF-O2C-GALLERY** | Revenue + tax compliance + the largest cross-module span (7 subsystems); contains the suspected v15 defect (TC-SAL-014) and 3 open business decisions | 12 scenarios: happy, discount, pickup, deposit-applied, exempt, guard-block, cancel, credit-note, no-auto-invoice, multi-order-confirm, outage, partial-delivery (new) |
| 2 | **WF-O2C-SHOPIFY** | Order intake for the storefront; rides every high-risk migration surface (OWL2, OCA rebases, queue jobs) | 10 scenarios: happy (SHP-034), rule-matrix ×3, guest, cancel ×2, return, missing-product, duplicate-import (new) |
| 3 | **WF-DEPOSIT** | Money held as liability; fully deterministic (no external APIs) → fastest to stabilize; feeds scenarios into #1 | 8 scenarios: record, from-SO fixed/%, apply, multiple, larger-than-invoice, cancel, reset-to-draft |
| 4 | **WF-INVSYNC** | Anti-oversell for one-of-a-kind inventory; exercises queue platform under test mode | 7 scenarios: delta, caps, exclusions ×3 (parameterized), bulk+lock, publish-state |
| 5 | **DATA-INTEGRITY backbone** | The workbook's 42 baseline-comparison tests become the comparison engine's first rule set (trial balance, aging, totals by year/state, stock on hand, valuation, deposit balances) | runs per migrated DB |
| 6 | **SMOKE gate** | The 14 CI-boot checks (SMK) become stage 0 of every run | runs always |

Deliberately **excluded from MVP** (and why): WF-CERT (py3o strategy is an open decision — TC-NEW-005/TC-NEW-009-adjacent; automate after the v19 rendering approach is chosen), WF-PIM-PUBLISH (needs its E2E anchor authored first; second wave), UI widget tours (wait until the OWL2 rewrites land, else you test code that is about to be replaced), PERF (needs stable v19 environment to be meaningful), migration gates (checklist app, Phase-2 dashboard feature).

MVP definition of done = your PART 34, verbatim: select environment (v15 / v19 / compare), pick workflows, RUN, watch live progress, drill into a failure down to step + expected/actual + both versions' results + Excel traceability. Concretely: **37 scenarios × 2 versions, comparison view, <20 min wall-clock in replay mode.**

---

## 9. Proposed Architecture

### 9.1 Decision drivers

The stack is chosen for: deterministic re-runs during a 4-hop migration (replay-first, sandbox-second); one behavior spec running against two Odoo versions (adapter pattern); business-outcome assertions over UI assertions (RPC-first, Playwright only where the UI *is* the feature); a Windows-friendly local dev story (your instances run on Windows, e.g. port 8076) with Docker as an option, not a requirement; and long-term maintainability by an Odoo-skilled team (Python everywhere; the only JS is the dashboard).

### 9.2 Stack

| Layer | Choice | Why (and why not the alternatives) |
|---|---|---|
| Test engine | **pytest** + custom workflow runner plugin | Fixtures/params/marks map 1:1 to scenarios/waves/suites; `--lf` gives failed-only rerun free; xdist later. Robot/Behave add ceremony without power |
| Odoo access | **XML-RPC (`xmlrpc/2`)** for both 15 & 19 + thin JSON-2 option for 19 | XML-RPC is the one API that is bit-identical across 15..19 — the adapter absorbs *model* drift, not *transport* drift. odoorpc as convenience wrapper |
| Business layer | Plain Python `BusinessActions` + per-version `OdooAdapter` | Your PART 10 diagram, literally. No framework — a protocol class and two implementations |
| UI automation | **Playwright** (Python), *only* for: login/menu smoke, JS-console-error sweep (TC-UIX-011), certificate/label PDF spot-render | Everything else is faster & stabler via RPC. Odoo-native tours (20 TCs) stay in-Odoo, triggered by the runner via `odoo-bin --test-tags`, results harvested |
| External APIs | **Replay-first**: recorded Shopify/Avalara cassettes served by a local mock (VCR-style), `--live-sandbox` flag for nightly runs against dev store + AvaTax sandbox | Determinism during migration > realism; the sandbox run stays for API-drift detection (TC-SHP-033's concern) |
| Queue jobs | `TEST_QUEUE_JOB_NO_DELAY=1` in CI (workbook's own recommendation, supported by TC-JOB-018); poll-with-timeout helper for live mode | |
| Results store | **PostgreSQL** (you already run it) — runs, scenarios, steps, assertions, artifacts, baselines, classifications | SQLite would work for MVP but Postgres removes a migration later; you have DBA muscle in-house |
| Backend | **FastAPI** + WebSocket (live progress) + worker subprocess running pytest with a JSONL event stream | Celery/Redis deferred — one runner host is enough for 37 scenarios; the event protocol is designed so a queue can slot in later without API change |
| Dashboard | **React + Vite SPA** served by FastAPI | Matches PART 13–16 interactivity (tree drill-down, live updates, side-by-side diff). Streamlit can't do this cleanly; Next.js SSR is pointless for an internal tool |
| Reporting | Self-contained HTML report per run + JSON export; Allure optional later | Your failure-UI spec (PART 15) is richer than Allure's model — native rendering first |
| CI/CD | **GitHub Actions** (repo already on GitHub): nightly matrix {odoo15, odoo19} × {replay}, weekly {live-sandbox}, on-demand via dashboard | |

### 9.3 Component architecture

```text
                        WEB DASHBOARD (React)
        run picker · live progress · compare view · failure drill-down
        workflow catalog · baseline approvals · migration-gate checklist
                              │ REST + WebSocket
                              ▼
                        FASTAPI BACKEND
      run planner · queue · result collector · comparison engine ·
      baseline store · classification · traceability (Excel-linked)
                              │ spawns / streams
                              ▼
                    WORKFLOW RUNNER (pytest)
        scenario = YAML spec → steps → BusinessActions calls
                              │
                 ┌────────────┴────────────┐
                 ▼                         ▼
        OdooAdapter15                OdooAdapter19
        (xmlrpc :8015/8076)          (xmlrpc :8019)
                 │                         │
                 ▼                         ▼
        Odoo 15 + test DB           Odoo 19 + test DB
        (clone, neutralized)        (migrated clone, neutralized)
                 │                         │
                 └────────► MOCK EDGE ◄────┘
              Shopify/Avalara replay server (or live sandbox)

   Side channels: odoo-bin --test-tags (native tours/TransactionCase) ·
   psql (DATA-INTEGRITY SQL assertions) · Playwright (UI spot checks)
```

### 9.4 The version adapter — where v15/v19 differences live

One workflow spec, two adapters. Known differences the adapter layer must absorb (from the assessment §5 + workbook v19 Watch column — 85 annotations pre-identify these):

| Difference | v15 | v19 | Adapter treatment |
|---|---|---|---|
| Sale order states | `sale.order.state` incl. legacy values | states/labels drift (TC-LBL-007 watch) | `normalize_order_state()` |
| Payment state values | `payment_state` mapping | reviewed per TC-INV-005 | explicit map table, not passthrough |
| Invoice send flow | Send & Print legacy | consolidated wizard (v17+) | `send_invoice()` per-version implementation |
| Down payments | `account_partner_deposit` custom | native down payments exist (TC-NEW-004 decision) | deposit actions isolated behind `DepositActions` so the implementation can swap |
| Tree/List views, OWL2, `attrs` | old widgets | rewritten | irrelevant to RPC layer; Playwright smoke only |
| `_sql_constraints` → `models.Constraint` | old | new | assertion on *behavior* (barcode rejection), not on constraint metadata |
| Studio fields `x_*` | present | must survive migration | adapter exposes them via field-existence probe, so a missing field = test failure with a precise message |
| Queue job API | OCA 15 | OCA 19 rebase | `JobsActions` (enqueue/wait/assert) per version |

Rule: **workflow specs never mention a version.** If a spec needs an `if version == …`, that difference gets promoted into the adapter or into an explicit expected-difference record (§9.6) — never inline.

### 9.5 Semantic comparison & golden baseline

Each scenario run produces a **Business Outcome Document** (BOD) — the semantic result, no technical IDs:

```json
{
  "workflow": "WF-O2C-GALLERY", "scenario": "happy_path",
  "order":    {"state": "sale", "amount_total": 12500.00, "discount_total": 500.00},
  "delivery": {"state": "done", "qty_delivered": 1, "legal_sale_date": "<stamped>"},
  "invoice":  {"state": "posted", "amount_total": 12500.00,
               "tax_lines": [{"jurisdiction": "AZ-STATE", "amount": 562.50},
                              {"jurisdiction": "AZ-PIMA",  "amount": 125.00}],
               "legal_invoice_date": "<propagated>"},
  "payment":  {"state": "reconciled", "journal": "BANK-DEFAULT"},
  "gl":       {"receivable_open": 0.00, "tax_payable_by_account": {"231000": 687.50}},
  "stock":    {"on_hand_delta": -1},
  "avalara":  {"committed": true, "total_matches_odoo": true}
}
```

Comparison config is explicit YAML per workflow — every ignored field is a visible decision (your PART 17 requirement):

```yaml
comparison:
  order.amount_total:   {type: numeric, tolerance: 0.01}
  invoice.tax_lines:    {type: set, key: jurisdiction, tolerance: 0.01}
  delivery.legal_sale_date: {type: semantic, rule: equals_delivery_done_date}
  "*.id":               {type: ignore, reason: technical identity differs by design}
  payment.journal:      {type: exact}
```

v15 runs produce **candidate baselines**; a human **approves** them in the dashboard (nothing is golden by default). v19 runs compare against approved baselines → every difference gets classified.

### 9.6 Difference classification (PART 19)

Every v15↔v19 mismatch lands in a queue with exactly one resolution, recorded with author + reason + date:

```text
REGRESSION            → defect on v19; blocks the gate
EXPECTED VERSION DIFFERENCE → rule added to comparison config (visible, versioned)
INTENTIONAL CHANGE    → baseline superseded by an approved v19 baseline
KNOWN BUG (v15)       → baseline annotated; v19 *fixing* it is not a regression
                        (pre-seeded: TC-SAL-014 multi-order auto-invoice,
                         TC-STU-009 inventory-value never worked,
                         TC-LEG-007 posted-invoice legal-date rewrite question)
TEST DEFECT / FLAKY   → quarantine lane, fix the test, re-run
UNKNOWN               → stays red; cannot be dismissed silently
```

### 9.7 Execution engine

Your PART 23 pipeline, concretely: dashboard/API request → planner expands {environments × workflows × scenarios} into a run plan (persisted) → per-environment worker executes scenarios (xdist-parallel where scenarios are data-isolated; serial inside a scenario) → every step emits `step_started/passed/failed` JSONL → collector persists + broadcasts via WebSocket → comparison engine joins the two environment runs → report. Supported controls: retry-on-flake (marked steps only), timeout per step & scenario, cancel run, rerun-failed-only, suite/workflow/scenario/version selection.

### 9.8 Environment & data safety (PART 12)

```text
Production DB ──(clone)──► mmg15_test_template ──(createdb -T / restore)──►
per-run DB → NEUTRALIZE → run → destroy (or keep on failure for autopsy)
```

Neutralization is a scripted, **verified** step and the run aborts if any check fails: outgoing mail servers disabled + `mail.catchall` voided; all channel crons paused; **Safe Mode ON for every `ecommerce.channel`** (the system's own write-guard, TC-CHN-003 — the platform asserts it before any Shopify-touching scenario in replay mode); Avalara pointed at sandbox creds or mock URL; payment providers in test mode; FTP endpoints remapped to the mock. Test records are namespaced (`QA-<run_id>` prefixes on `client_order_ref`/`default_code`) so scenario isolation and cleanup are queryable — and BODs are computed from records the run itself created, never from historical data. The DATA-INTEGRITY suite is the exception by design: it runs read-only against the freshly-migrated clone pair.

Never runs against production; the platform refuses to start against a DB not flagged `qa_environment=true` in `ir.config_parameter` (belt and braces).

### 9.9 Traceability (PART 26)

The Excel is imported once into the results DB (and re-importable idempotently — `tc_id` is the key, exactly as the workbook intends). Every scenario/step carries `tc_ids[]`; every run result therefore answers: result → step → scenario → workflow → TC → feature → user story → feature group. The dashboard renders this chain on every failure, and coverage rollups (workflow %, feature %, user-story %) come from the same joins — your PART 30 KPIs with Workflow Coverage as the headline.

### 9.10 Where each workbook `automation_approach` lands

| Workbook approach (count) | Platform lane |
|---|---|
| TransactionCase (194) | Odoo-native tests generated per convention (`test_TC_TAX_002_…`), run via `odoo-bin --test-tags`, harvested into the same results DB — CI-per-hop safety net |
| Sandbox/mocked integration (54) | Workflow runner scenarios (replay/live modes) |
| SQL/ORM baseline comparison (42) | DATA-INTEGRITY suite inside the comparison engine |
| HttpCase tours (20) | Odoo-native, triggered post-OWL2-rewrite |
| Endpoint/security (18) | HttpCase + platform smoke stage |
| CI boot (14) | Stage-0 smoke gate |
| One-offs (20) + decision gates (10) | Dashboard checklist (tracked, never automated) |
| Perf harness (11) | Nightly benchmark lane vs v15 timing baseline |

---

## 10. After Your Approval — Delivery Order (maps to your PART 36)

| Step | Work | Output |
|---|---|---|
| 1 | Normalize Excel → results DB (`tc`, `feature`, `story`, `group`, links) + fix the 4 trace gaps (§4.1) | queryable knowledge base |
| 2 | Author the workflow catalog as versioned YAML (11 workflows; MVP 4 fully specified — includes writing the missing steps for TC-SAL-017 and friends) | `catalog/*.yaml` |
| 3 | Build `BusinessActions` + `OdooAdapter15`; neutralization scripts; replay mock edge | actions library |
| 4 | Automate MVP scenarios (37) on v15 | green v15 suite |
| 5 | Stabilize → produce candidate baselines → **you approve** | Golden Baseline v15 |
| 6 | `OdooAdapter19` + comparison engine + classification queue | cross-version core |
| 7 | FastAPI backend + React dashboard (run, live progress, compare, drill-down, checklist) | the PART 34 experience |
| 8 | CI wiring (nightly matrix, per-hop runs during migration) | continuous gate |
| 9 | Expand: PIM-PUBLISH & CERT & RECOVERY workflows, TransactionCase generation for Wave 2, perf lane | scale-out |

Open questions to settle during step 1–2 (they shape scenarios, all already flagged in the workbook): TC-NEW-004 deposits vs native down payments; TC-NEW-009/TC-LEG-007 legal-date reimplementation & rewrite semantics; TC-NEW-005 py3o vs QWeb for certificates; TC-NEW-001 keep/retire `mmg_sale_delivery_status`; TC-NEW-007/TC-STU-009 inventory-value fix-or-drop; multi-currency in scope or not.

---

## Appendix A — TC → Workflow mapping

Machine-readable mapping shipped alongside this report (`workflow_catalog.yaml` — 11 workflows, every `related_existing_tests` list enumerated per workflow, MVP scenarios drafted). Numbers in this report were computed from the workbook by script; the analysis dataset (`workbook.json`) is preserved in the session workspace for the normalization step.

## Sources

- `MMG_v19_Test_Cases_Grouped_by_Feature_v2.0.xlsx` (uploaded, 2026-08-06 generation) — all counts, TC/feature/story data
- [migration_assessment.md](computer://D:/Projects/mmg/migration_assessment.md) — module inventory, complexity/risk, §5 compatibility, §10 regression strategy
- [psus-medicine-man-gallery](computer://D:/Projects/mmg/psus-medicine-man-gallery) addons tree + [mmg.conf](computer://D:/Projects/mmg/mmg.conf) — module list, local instance shape (secrets redacted)
