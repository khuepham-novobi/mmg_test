# FG-02 Automation Plan — Certificates of Authenticity & Label Printing

Source: `MMG_v19_Test_Cases_Grouped_by_Feature_v3.0.xlsx`, feature group
FG-02, **13 test cases** (TC-LBL-001…011, TC-SMK-011, TC-NEW-005). Expected
results are the workbook's, verbatim — never modified, weakened or inverted
here. Implementation: `tests/fg02/common.py`, `tests/fg02/test_certificates.py`
(TC-LBL-001…007), `tests/fg02/test_labels.py` (TC-LBL-008…011, TC-SMK-011).

Quality bar: the FG-04 reference suite (`tests/fg04/`). Every point of its
pattern is applied here — see "FG-04 checklist compliance" below.

## Execution strategy

- **Transport.** Business logic runs through `/web/dataset/call_kw` on an
  authenticated web session (`adapters/base.py`), i.e. the platform drives
  Odoo the way the web client does. Each RPC call commits its own
  transaction, so `cr.precommit` hooks fire per call — mmg_stock's
  template↔variant sync mirror (`product.level.data.sync.mixin`, which owns
  `x_artist / x_medium / x_height / x_width / x_date`) persists on create,
  which is exactly what the label fixtures depend on.
- **Target DB.** `mmg_qa15` — a neutralized clone of a production copy
  (69,316 product templates, real orders/partners/invoices). Crons OFF, mail
  OFF, connector instances INACTIVE, **LibreOffice / py3o runtime not
  available on the host**. `mmg` itself is never written.
- **This suite is deliberately blocked-stub-heavy.** FG-02 *is* document
  rendering: the two certificates are py3o-native ODT, the five Avery
  formats are DOCX produced by an ODT→DOCX conversion that needs the
  LibreOffice binary. The render entry points
  (`ir.actions.report._render_py3o`, `py3o.report._get_template_fallback`,
  `product.template._get_product_template_certificate_report_path`) are
  underscore-private and therefore not callable over any RPC transport, and
  the conversion runtime is absent on this host. Every test therefore
  **asserts its full offline half first** (report records, template paths,
  wizard routing, slot helpers, ORM helpers, fixture data) and only then
  calls `ctx.blocked(reason)` for the rendered/visual half. No test blocks
  before asserting what it can assert.
- **Determinism (per-execution fixture namespace).** `sweep_fg02()` mints a
  fresh 6-hex token and `fx()` stamps it onto every fixture identifier and
  every free-text value a test matches by: product names, SKUs, `x_artist`,
  `x.medium` names, provenance text, partner names. This is required even
  though no FG-02 assertion counts records:
  `mmg_multichannel_shopify.check_unique_sku` is a live constraint over
  *active* products (a leftover a previous run could only archive is still
  active), `ensure_medium()` resolves `x.medium` **by name**, and the slot
  assertions compare wizard output against fixture values. Structural
  workbook literals stay literal (`x_date` 1948/1950, the 10.5 x 8.0
  dimensions, prices) — the chooser branches on x_date being empty vs set
  and the workbook quotes the resulting description line verbatim.
- **Teardown may never replace a verdict.** Every FG-02 test ends in
  `ctx.blocked()`. A raising cleanup would *replace* the propagating
  `BlockedTest` and `backend/runner.py` would classify the execution as
  ERROR / AUTOMATION_ERROR. `sweep_fg02()` never raises (it returns the
  problems it hit), `cleanup_fg02()` logs them, orders/invoices are
  cancelled or reset to draft before unlink, and every phase falls back
  record-by-record so one undeletable row cannot strand the rest.
- **Layout-wizard guard.** `report_action()` diverts to "Configure your
  document layout" when the caller is an admin and
  `res.company.external_report_layout_id` is unset — the state of this
  clone. Core gates that diversion on `discard_logo_check`, so every call
  that reaches `report_action` passes `REPORT_CTX`. Environment guard only:
  it makes the wizard return the action the workbook describes; it changes
  nothing that is asserted about that action.
- **Fixture sales configuration.** All fixture products are created with
  `invoice_policy='order'`, and TC-LBL-007 additionally snapshots and clears
  `res.company.auto_create_invoice_after_confirming_so` for the duration of
  its confirmation step (restored in the `finally`). Rationale under
  "Fixture defects fixed after RUN-5C016D16".
- **Collected assertions.** Related comparisons are gathered into one
  mismatch dict (or one expected/observed dict pair) and asserted once, so
  the first difference cannot abort the comparison and destroy the evidence
  for the rest. No test loops `ctx.check` over many fields.
- **v19.** No local Odoo 19 exists yet; v19 runs are BLOCKED by the runner
  preflight. Tests are written version-aware anyway (the only version split
  in this suite is the `sale.order.line` tax field name, `tax_id` on v15 vs
  `tax_ids` on v19).
- **Evidence.** Every execution persists steps, assertions
  (expected/actual), the execution log and — for BLOCKED verdicts — a reason
  string that names the missing runtime, the record ids and the exact manual
  verification left to a human (fixture token included, so the records can
  still be identified after the run).

## Fixture defects fixed after RUN-5C016D16

Run RUN-5C016D16 (10 BLOCKED as designed, 1 FAIL, 1 ERROR) exposed two
**fixture** defects — neither was a product finding, and neither assertion
was weakened to resolve it:

1. **TEST-FG02-LBL-007 → ERROR / AUTOMATION_ERROR** at "Confirm old and
   latest…": `sale.order.action_confirm` raised sale's nothing-to-invoice
   `UserError` ("…modify invoicing policy from 'delivered quantities' to
   'ordered quantities'"). Cause: `mmg_sale_auto_create_invoice` calls
   `_create_invoices()` from `action_confirm()` whenever
   `res.company.auto_create_invoice_after_confirming_so` is set, and the
   fixture products inherited the clone's `ir.default` invoicing policy
   ('delivery') with nothing delivered. Fix: every FG-02 fixture product now
   pins `invoice_policy='order'` (Ordered quantities / Prepaid — the value
   the error message itself names), and TC-LBL-007 snapshots + clears the
   company auto-invoice flag around its confirmation step so the TC exercises
   `get_purchase_info_based_on_sol`, not the clone's chart-of-accounts state.
   Cleanup also sweeps marker-scoped customer invoices now, in case any other
   module invoices on confirm.
2. **TEST-FG02-LBL-008 → FAILED / ASSERTION**: "slot 0 lst_price is a
   formatted currency amount … got formatted: '$0.0'". Cause: the fixture had
   no price. `novobi-omni-addons/multichannel_manage_price` redefines
   `product.product.lst_price` to read the stored `variant_price` field
   instead of `list_price + price_extra`, so a fixture created with
   `list_price` alone still formats as `$0.0`. Fix: label fixtures carry a
   distinct non-zero price written to **both** `list_price` and `lst_price`
   (the inverse writes `variant_price` here and `list_price` on a stock
   database), exactly as TC-LBL-008's own precondition asks ("35
   product.product records with distinct default_code, name, lst_price, …").
   The assertion is now explicit about its intent: the slot value must equal
   the fixture's own price rendered the way
   `digest.digest._format_currency_amount` renders it (currency symbol +
   the float's `str()`, read from the product's own currency record), and a
   separate fixture-precondition check fails loudly if the price is ever zero
   again.

## Per-test plan

Type: `RPC` = ORM over the authenticated web session. All twelve automated
FG-02 tests are **blocked stubs with a fully asserted offline half** — the
"Core assertions" column is what actually executes and is expected to pass on
v15 before the blocked verdict is recorded.

| TC | Test id | Type | Fixtures / data | Core assertions (offline half) | Expected v15 outcome | Why blocked | Evidence |
|---|---|---|---|---|---|---|---|
| TC-LBL-001 | TEST-FG02-LBL-001 | RPC | 1 `x.medium` + 1 full-data variant (artist, medium, 30.0 x 40.0, date 1948, provenance, PNG) | `mmg_report.product_certificate` is py3o/odt on `product.product` with fallback `report/certificate.odt`; all 7 certificate data fields read back (collected dict); `image_1024` derived; company-block source readable | BLOCKED — offline half passes | `_render_py3o` is private + v15 visual baseline comparison is manual | steps, assertion table, log, blocked reason naming the record id and the blocks to check |
| TC-LBL-002 | TEST-FG02-LBL-002 | RPC | variant with x_date **and** provenance | chooser inputs on the variant (collected dict); template report record py3o/odt/`report/template_certificate.odt`/model `product.template` | BLOCKED — offline half passes | chooser + `_get_template_fallback` are private; ODT byte comparison is server-side | steps, assertions, log, blocked reason naming template id + expected chooser return |
| TC-LBL-003 | TEST-FG02-LBL-003 | RPC | variant with provenance, x_date empty | same as TC-LBL-002 for the no-date input state; expected path `…_no_date.odt` recorded | BLOCKED — offline half passes | same private chooser / rendering limit | steps, assertions, log, blocked reason |
| TC-LBL-004 | TEST-FG02-LBL-004 | RPC | variant with x_date, provenance empty | same for the no-provenance state; expected path `…_no_provenance.odt` | BLOCKED — offline half passes | same private chooser / rendering limit | steps, assertions, log, blocked reason |
| TC-LBL-005 | TEST-FG02-LBL-005 | RPC | bare variant (neither x_date nor provenance) | same for the neither state; expected path `…_no_date_no_provenance.odt` | BLOCKED — offline half passes | same private chooser / rendering limit | steps, assertions, log, blocked reason |
| TC-LBL-006 | TEST-FG02-LBL-006 | RPC | full-data variant (x_date + provenance) | template report record: model `product.template`, report_name `product.template.certificate`, py3o/odt, Print-menu binding = `product.model_product_template` (collected dict) | BLOCKED — offline half passes | `_render_py3o` + the template-form download / variant-parity comparison | steps, assertions, log, blocked reason naming the template id |
| TC-LBL-007 | TEST-FG02-LBL-007 | RPC | 1 service variant (`invoice_policy='order'`), 3 namespaced buyers, 3 sale orders (900 / 1500 / 9999 decoy with the newest id); company auto-invoice flag snapshotted + cleared | decoy cancelled and the other two confirmed (`sale`/`done`, one collected check); `get_purchase_info_based_on_sol` == `('2025-06-30', <latest buyer>, 1500.0)` as one tuple assertion; never-sold == `('', '', 0.0)` | BLOCKED — offline half passes (was ERROR in RUN-5C016D16, fixture fixed) | only the printed last-sale block needs the render | steps, assertions, log incl. order ids and the config snapshot, blocked reason |
| TC-LBL-008 | TEST-FG02-LBL-008 | RPC | 1 `x.medium` + 35 variants with distinct name/SKU/price/artist and label data (date 1950, 10.5 x 8.0) | `digest` installed; 35 fixtures; action == avery.label.60 + py3o (one dict check); sampled slots 0/17/34 follow `product_ids` order; slots 35/59 == `''`; slot 0 artist, price as a formatted currency amount and description line (collected dict) + non-zero-price precondition | BLOCKED — offline half passes (was FAILED in RUN-5C016D16, fixture fixed) | pagination (30+5), slot geometry and the v15 page-by-page baseline are the rendered DOCX | steps, assertions, log, blocked reason naming wizard id + fixture token |
| TC-LBL-009 | TEST-FG02-LBL-009 | RPC | 1 `x.medium` + a pool of 125 variants; 65/95/125 selections; one empty wizard | collected count→format routing for 65/95/125 (report_name + report_type + first slot past the selection) asserted in one check; empty selection → avery.label.120; the 60/90/120 report records are py3o/docx with `report/60.odt`,`/90.odt`,`/120.odt` (collected dict) | BLOCKED — offline half passes | per-page slot counts, page breaks, fill order and the v15 baseline are the rendered DOCX | steps, assertions, log with the three wizard ids, blocked reason |
| TC-LBL-010 | TEST-FG02-LBL-010 | RPC | 1 `x.medium` + 8 variants | backtag action == avery.label.6 + py3o (one dict check); `get_page_groups() == [0, 1]`; `check_list_data_6(1,1,'name')` == 8th product and `(1,2)` == `''` (collected dict); `check_label_description_6(0,0)` == the fixture description line | BLOCKED — offline half passes | the rendered 2-page DOCX (6 + 2 tags, 4 blank slots) | steps, assertions, log, blocked reason naming the wizard id |
| TC-LBL-011 | TEST-FG02-LBL-011 | RPC | 1 template with 1 variant + 2 standalone variants | all four print server actions: state `code`, binding model, `binding_view_types` `list,form`, code calls the matching method (one collected dict); all four entry points: report_name + report_type + the wizard's `product_ids` (one collected expected/observed assertion), each wizard identified by an id watermark | BLOCKED — offline half passes | the Action-menu download serves rendered py3o output | steps, assertions, log with wizard ids per entry point, blocked reason |
| TC-SMK-011 | TEST-FG02-SMK-011 | RPC | 1 variant + 1 wizard | `mmg_stock` / `mmg_report` / `report_py3o` all `installed` (one dict check); `mmg_stock.avery_label_30_report` is py3o/docx with report_name avery.label.30 (collected dict); wizard action routes to avery.label.30 / py3o (one dict check); engine state (`lo_bin_path`, `is_py3o_report_not_available`) probed and logged | BLOCKED — offline half passes | **precondition unmet on this host**: LibreOffice runtime absent, so workbook steps 1–2 (boot-log scan), 4 (`lo_bin_path` non-empty) and 6–7 (real ODT→DOCX render, `b'PK'` check) cannot run — reason quotes the observed engine values and the fix | steps, assertions, log with the observed engine state, blocked reason |
| TC-NEW-005 | — | MANUAL | decision log | none (business decision gate: accept the LibreOffice SPOF with a monitoring plan, or log a QWeb migration as backlog) | n/a — not implemented | manual decision gate, no automatable behaviour | written decision in `mmg.md` section 0 referencing TC-SMK-011 as the canary |

## Coverage summary

Reconciled 1:1 with `reports/data/fg02_feasibility.json`:

- **implemented (full pass/fail verdict): 0.** FG-02's essence is rendered
  output; no TC in this feature group can reach a non-blocked verdict on a
  host without the py3o/LibreOffice runtime, and the private render entry
  points are unreachable over RPC by design.
- **blocked_stub: 12** — TC-LBL-001…011 and TC-SMK-011. Each asserts its
  full offline half first (report records, template paths, chooser inputs,
  wizard routing, slot helpers, ORM helpers, fixture data) and then blocks
  with a precise reason. 11 of the 12 block on the rendering/visual half;
  TC-SMK-011 blocks on the workbook's own LibreOffice precondition and
  records the observed engine state.
- **not_implemented: 1** — TC-NEW-005 (MANUAL_ONLY in the workbook: a
  business decision gate).
- Total: 13 of 13 workbook TCs accounted for.
- Expected v15 run shape after these fixes: **12 BLOCKED / 0 FAILED / 0
  ERROR**. FG-02 carries no assertion that describes a v19-only behaviour,
  so — unlike FG-04 — it has no documented v15 baseline FAIL. The FAIL and
  the ERROR of RUN-5C016D16 were both fixture defects and are fixed above; if
  either reappears it is a real finding, not a known baseline.
- What flips to a real verdict on v19: install LibreOffice on the v19 host
  (report_py3o `external_dependencies: deb libreoffice`, or point
  `py3o.conversion_command` at the binary) and TC-SMK-011's blocked half
  becomes executable; the remaining eleven need the rendered-document
  comparison, which stays a documented manual verification driven by the
  BLOCKED reason strings this suite emits.

## FG-04 checklist compliance

| # | FG-04 pattern item | FG-02 status |
|---|---|---|
| 1 | Per-execution fixture namespace, `fx()` on every fixture name and matched value | Applied — token minted in `sweep_fg02()`, exposed as `fx()` / `fixture_token()`; names, SKUs, artists, medium names, provenance, partner names namespaced; structural literals documented as deliberate exceptions |
| 2 | Defensive cleanup that can never raise | Applied — `sweep_fg02()` returns problems instead of raising, `cleanup_fg02()` logs them under an outer guard, cancel/reset-to-draft before unlink, record-by-record fallback (`_unlink_one_by_one`) |
| 3 | Collected assertions, never a `ctx.check` loop over many fields | Applied — mismatch dicts (`note_mismatch`, `collect_report_record`) and expected/observed dict pairs; the LBL-009 routing loop and the LBL-011 entry-point probes are asserted once each |
| 4 | No inline version branches in test bodies | Applied — only the `tax_id`/`tax_ids` field-name split inside TC-LBL-007's `make_order` helper; view/report access goes through `framework/fg_common.py` and `tests/fg02/common.py` helpers |
| 5 | Snapshot + restore any company/config flag a test flips | Applied — TC-LBL-007 is the only test that flips config (`auto_create_invoice_after_confirming_so`) via `suspend_auto_invoice()`; the restore callable runs in `cleanup_fg02(restore=…)` and is a no-op when the field is absent or was already off |
| 6 | Precise `ctx.blocked(reason)` | Applied — a shared "why" (private render entry points + absent LibreOffice) plus, per stub, the exact manual verification with record ids, wizard ids and the fixture token; TC-SMK-011's reason quotes the observed `lo_bin_path` / `is_py3o_report_not_available` and names the fix |
| 7 | Workbook immutable | Respected — `data/test_registry.json` read-only (via a scratch script); no assertion weakened, inverted or deleted; the two RUN-5C016D16 failures were fixed in the fixtures, and TC-LBL-008's price assertion became *stricter* (exact formatted amount + a non-zero-price precondition) |
| 8 | Every test docstring states its expected v15 outcome and why | Applied — each test function carries an "Expected v15 outcome: BLOCKED" docstring with the reason; both module docstrings state the suite-wide expectation and that FG-02 has no documented v15 FAIL |
