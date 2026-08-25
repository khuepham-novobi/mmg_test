# FG-01 Automation Plan — Art Catalogue & Product Master Data

Source: `MMG_v19_Test_Cases_Grouped_by_Feature_v3.0.xlsx`, 36 test cases.
Expected results are the workbook's, verbatim — never modified here.

Suite: `tests/fg01/` (35 registered tests + `common.py`).
Per-TC feasibility record: `reports/data/fg01_feasibility.json`.

## Execution strategy

- **Transport.** Business-logic tests run through the web client's own
  endpoint, `/web/dataset/call_kw`, over an authenticated session
  (`adapters/base.py`) — not as in-Odoo `TransactionCase` files, because
  writing test files into `psus-medicine-man-gallery` (application source) is
  out of bounds for this phase. Each RPC call commits its own transaction, so
  `cr.precommit` hooks (the template↔variant sync mixin) fire at the end of
  every call — no explicit `env.cr.precommit.run()` needed, and the mirror
  persists on `create()` as well as on `write()`.
- **Target DB.** v15 executions run against **`mmg_qa15`** — a PostgreSQL
  clone of the local production-copy `mmg`, created on the `qa_regression`
  tablespace (E:). The clone is neutralized (crons, mail servers, connector
  instances disabled) and the server runs with `--max-cron-threads=0`.
  The `mmg` database itself is never written.
- **DATA_RECONCILIATION pattern.** On v15 the test captures the baseline
  (counts/CSV via direct SQL), stores it under `data/baselines/`, attaches
  it as an execution artifact, and asserts the workbook's v15 anchors.
  On v19 the same test loads the stored baseline and diffs. No v19 → the
  v19 half is BLOCKED, honestly reported.
- **v15-expected failures.** Several workbook expectations describe the
  **v19 target state** (formalized fields, DW-fixes). Running the same
  logical assertions on v15 documents the baseline: a v15 FAIL on those is
  *expected* and becomes `FIXED` when v19 passes. Assertions are never
  weakened, inverted or removed to make v15 green.
- **Evidence.** Every execution persists: steps, assertions
  (expected/actual), execution log, traceback on error; screenshots for the
  two partially automated UI cases; baseline CSVs for reconciliation tests;
  Playwright trace on UI failure.

## Determinism rules (FG-04 parity)

The suite follows the four rules proven on FG-04, which turned
non-deterministic reruns into identical ones. They are implemented in
`tests/fg01/common.py` and documented in its module docstring; none of them
changes what is asserted.

1. **Per-execution fixture namespace.** `sweep_fg01()` mints a token; `fx()`
   stamps it on every fixture *name* and on every *value* a test counts or
   matches by (artist strings, medium / category / style names, vendor
   values). `fx_barcode()` is the numeric equivalent for the Tile fixtures —
   barcode is UNIQUE database-wide and digits-only, so it cannot be
   namespaced with text. Why it is required: on a production clone deletion
   frequently cannot succeed (`sweep_products()` archives a product it cannot
   unlink), so a name or value shared with an earlier run gets reused by an
   ensure-by-name fixture or inflates an "exactly N records" assertion.
   Workbook *data* values read back by record id (the 17-field catalogue
   create, the nine auction values, the `copy()` carry-over set) stay exactly
   the workbook's, un-namespaced — as do live anchors (`x.medium == 341`,
   "exactly one White", "exactly one Acoma").
2. **Defensive cleanup.** `cleanup_fg01()`, `unlink_quiet()` and
   `_remove_quant()` run in a `finally` step and never raise. The runner
   classifies whatever exception leaves the test function, so a raising
   cleanup would REPLACE the verdict and report a documented FAIL or BLOCKED
   as ERROR. Orders are cancelled before unlink, then unlinked record by
   record; whatever survives is logged as `cleanup incomplete: …`.
3. **Collected assertions.** Multi-field verification builds a mismatch
   mapping and asserts it once (`ctx.check("… mismatches", {}, mismatches)`).
   `ctx.check` raises on the first mismatch, so a loop of per-field checks
   reported one broken field and destroyed the evidence for the rest
   (observed on TC-ART-001: 1 of 14 sync fields evaluated).
4. **No version branches in test bodies.** Every v15/v19 API or URL
   difference lives in a helper: `framework/fg_common.py` (`form_arch`,
   `m2o_id`, `reconcile`, `http_session`) or `tests/fg01/common.py`
   (`display_name` for `name_get` vs `display_name`, `view_arch` for
   `fields_view_get` vs `get_view`, `record_url` / `list_url`,
   `is_v15` / `is_v19`). The only remaining `is_v19(ctx)` guards are the
   workbook's own "on the v15 clone… / on v19…" step split in the
   reconciliation tests.

Two further rules apply:

- **Snapshot + restore.** TC-ART-010 is the only case that writes on a
  pre-existing record — the platform's own QA internal user — and it
  snapshots both `x_main_phone` values and restores them in the defensive
  `finally` step.
- **Precise BLOCKED.** `anchor_or_blocked()` reports a stale workbook anchor
  as BLOCKED with the measured values and what would unblock it, never as
  FAIL (which would assert a migration defect that does not exist), and it
  runs *after* the baseline is persisted so the v15→v19 diff survives.
- **Evidence is never a verdict.** `screenshot_evidence()` swallows browser
  problems and logs them, so a Playwright failure cannot turn TC-ART-002's or
  TC-ART-023's documented FAIL into an ERROR.

## Per-test plan

Type = automation type executed this phase. `SQL` = direct PostgreSQL
(reconciliation); `RPC` = ORM over `call_kw`; `RPC+HTTP` = ORM + authenticated
HTTP; `ARCH+SHOT` = view-architecture assertions + screenshot evidence
(partial automation of a UI/tour case).

| TC | Test id | Type | Fixtures / data | Core assertions | Expected v15 |
|---|---|---|---|---|---|
| TC-NEW-007 | — | MANUAL | decision log | written decision (b) on record | MANUAL (not implemented) |
| TC-STU-009 | TEST-FG01-STU-009 | SQL | none (read-only) | v15: template `x_inventory_value`/`x_invenory_value` all-zero (hard anchors); variant non-zero counts captured for QC; v19: fields absent from registry & schema | PASS |
| TC-ART-001 | TEST-FG01-ART-001 | RPC | 1 x.medium, full 17-field template create | every field reads back; 14 sync-listed variant fields mirror; template-only fields have no independent variant storage | PASS |
| TC-ART-002 | TEST-FG01-ART-002 | ARCH+SHOT | populated live art item | 32 code-declared mmg_stock fields in the served template arch; `barcode` labelled "Tile"; code-placed variant field; then the v19-formalized groups (x_image_1..47 + 4 variant fields) | FAIL — v19-formalized groups (documented baseline) |
| TC-ART-014 | TEST-FG01-ART-014 | RPC | QA internal user | `x.medium` count == 341; CRUD as admin; plain-user CRUD (ACL decision #4) | PASS |
| TC-ART-015 | TEST-FG01-ART-015 | RPC | — | 10 seed colours resolve by XML id; exactly one "White"; CRUD round-trip | PASS |
| TC-ART-016 | TEST-FG01-ART-016 | RPC | — | seed origins resolve by XML id; exactly one "Acoma"; CRUD round-trip | PASS |
| TC-ART-017 | TEST-FG01-ART-017 | RPC | QA user | style CRUD; `_order = 'name'`; plain-user CRUD | PASS |
| TC-ART-018 | TEST-FG01-ART-018 | RPC | 1 category + linked template | CRUD; m2o resolves; referenced unlink raises-or-nulls consistently; clean unlink once unreferenced; plain-user CRUD | PASS |
| TC-ART-019 | TEST-FG01-ART-019 | RPC | 3 templates (2 namespaced artists + none) | ilike match on template and variant; empty-artist filter; read_group counts | PASS |
| TC-ART-020 | TEST-FG01-ART-020 | RPC | 2 mediums, 3 templates | m2o filter; relation name-search; read_group 2/1; variant parity | PASS |
| TC-ART-021 | TEST-FG01-ART-021 | RPC | 2 categories, 4 templates | read_group 3/1 on template and variant | PASS |
| TC-ART-023 | TEST-FG01-ART-023 | ARCH+SHOT | live list arch | contributing views logged by priority; relative order of the columns present; none statically invisible; categ_id hidden; `default_order`/`multi_edit`; then column presence | FAIL — priority-640 Studio view drops `barcode` (documented baseline) |
| TC-ART-024 | TEST-FG01-ART-024 | RPC | 20-row `load()` matrix, per-execution barcodes | 0 error messages, 20 ids; collected spot-check of 3 rows + variant sync; non-numeric Tile row rejected | PASS |
| TC-ART-025 | TEST-FG01-ART-025 | RPC | 20 live templates (QA fixtures excluded) | all art fields declared & exportable; `export_data` returns 20 complete rows; sampled `x_artist` populated | PASS |
| TC-ART-026 | TEST-FG01-ART-026 | RPC | 1 template + variant with Tile | archive cascades to the variant; values/barcode survive the round-trip | PASS |
| TC-DAT-011 | TEST-FG01-DAT-011 | SQL | read-only | per-field populated counts on template + variant, QA footprint excluded, raw/qa/residual logged; baseline persisted; then the workbook anchors | BLOCKED — anchors are a 2026-08-13 source snapshot (69,201/13,972 vs 69,316/14,001 today) |
| TC-DAT-012 | TEST-FG01-DAT-012 | SQL+RPC | read-only | 6 reference-table counts; `x_medium == 341`; no duplicated seed names | PASS |
| TC-STU-008 | TEST-FG01-STU-008 | SQL | read-only | rows/refs captured; Studio duplicate unreferenced (0 rel fields, 0 views); then the workbook anchors | BLOCKED — `template_refs` anchor 13,972 vs 14,001 today |
| TC-STU-014 | TEST-FG01-STU-014 | SQL+RPC | read-only + 5 sampled variants | 4 populated counts (SQL or archive-inclusive ORM); x_image binaries decode | PASS |
| TC-ART-011 | TEST-FG01-ART-011 | RPC | 1 template | 9 auction values persist; 6 sync-listed mirror onto the variant | PASS |
| TC-ART-007 | TEST-FG01-ART-007 | RPC | 2 product.category (namespaced) | stored compute matches after add and after partial removal; clears on last removal | FAIL — DW-005 stale stored value (documented baseline) |
| TC-ART-013 | TEST-FG01-ART-013 | RPC+HTTP | 1 template + PNG fixture | write path stores the image; `image_1920_download` mirrors it; authenticated `/web/image` returns the bytes; unauthenticated result recorded; create-path expectation asserted last | FAIL — image_1920 in `create()` values is dropped on v15 (genuine finding) |
| TC-DAT-013 | TEST-FG01-DAT-013 | SQL+RPC | read-only + 20 sampled variants | relation rows + populated compute (QA excluded); 20-record recompute diff empty; DW-005 stale set counted separately | PASS |
| TC-ART-003 | TEST-FG01-ART-003 | RPC | 2 mediums | sync both directions on create and write; batched create; non-sync field has no independent variant storage | PASS |
| TC-ART-004 | TEST-FG01-ART-004 | RPC+SQL | throwaway products, per-execution Tile | non-numeric Tile rejected (template + variant); numeric saves; duplicate rejected; `product_product_barcode_uniq` in pg_constraint | PASS |
| TC-ART-005 | TEST-FG01-ART-005 | RPC | source variant with barcode + 12 carry-over fields | duplicate has empty barcode and carries the values (collected); multi-record copy zips per record | FAIL — v15 `copy()` is singleton-only, DW-004 is the v19 fix |
| TC-ART-008 | TEST-FG01-ART-008 | RPC | 3 + 1 products | activate/deactivate touch exactly the selection; server-action bindings (collected); control `write_date` unchanged | PASS |
| TC-ART-006 | TEST-FG01-ART-006 | RPC | consigned product + quant | `quant.x_vendor` resolves; searchable; rendered in the quant search view; then groupable | FAIL — non-stored related field is not groupable on v15 (v19 target) |
| TC-ART-012 | TEST-FG01-ART-012 | RPC | vendor + consigned product + PO | variant menu inactive; PO form arch parses; consignment fields readable from the PO line product (collected) | PASS |
| TC-ART-022 | TEST-FG01-ART-022 | RPC | 1 variant | cost/consignment persist, mirror to the template, come back via `search_read` | PASS |
| TC-ART-009 | TEST-FG01-ART-009 | RPC | 1 partner | membership date persists; `copy=False` honoured; field in the served partner arch after the `vat` anchor | PASS |
| TC-ART-010 | TEST-FG01-ART-010 | RPC | QA internal user (snapshot + restore) | single code declaration on res.partner; **no** shadow declaration on res.users; partner and user never diverge | FAIL — confirmed product defect (`mmg_stock/models/res_users.py:9`), must NOT be auto-scored FIXED |
| TC-STU-005 | TEST-FG01-STU-005 | SQL+RPC | read-only | 47 template counts with anchors 6,221/603/20/0; 47 variant counts via ORM; variant mirror spot-check | PASS |
| TC-DAT-007 | TEST-FG01-DAT-007 | SQL | read-only | per product/location qty + reserved CSV and per-product totals (QA excluded); baseline non-trivial; v19: row-level diff | PASS |
| TC-DAT-008 | TEST-FG01-DAT-008 | SQL | read-only | SVL value/qty/rows + GL stock-account balance + SVL−GL delta in one snapshot | PASS |

## Baseline outcome (v15)

Expected steady-state on the neutralized clone: **26 PASS / 7 FAIL / 2
BLOCKED / 0 ERROR** across the 35 automated tests.

- The 7 FAILs are the documented baselines listed above. Five describe the
  v19 target state (TC-ART-002, TC-ART-023, TC-ART-005/DW-004,
  TC-ART-007/DW-005, TC-ART-006) and classify as `FIXED` when v19 passes.
  Two are genuine findings that a v19 run must be read against carefully:
  TC-ART-013 (image dropped when supplied in `create()` values) and
  TC-ART-010 — a **confirmed product defect** in the shared `mmg_stock`
  branch that will not self-heal on v19 and must not be auto-scored FIXED.
- The 2 BLOCKED are the stale workbook anchors (TC-DAT-011, TC-STU-008).
  Unblocking them needs either a clone taken on the workbook's snapshot date
  or refreshed anchor values — a workbook decision, out of scope here.

Reference run before the parity work: **RUN-700517E4** (25 PASS / 9 FAIL /
0 ERROR / 2 BLOCKED, one of the 9 being the retired legacy `TEST-SALES-001`).
TC-ART-001 and TC-ART-003 have since been corrected to assert delegation-aware
"template-only"/"non-sync" facts, so they are expected PASS now.

## Coverage summary

- **Automated this phase: 35 of 36** (33 full + TC-ART-002 / TC-ART-023
  partial — arch-level assertions + screenshots; per-field browser tick-off
  remains listed as residual manual verification).
- **Manual: 1** — TC-NEW-007 (business decision gate), recorded as
  `not_implemented` in `reports/data/fg01_feasibility.json`.
- v19 executions are BLOCKED until a local Odoo 19 environment exists
  (see `docs/ENVIRONMENT_STATUS.md`); reconciliation baselines are captured
  on v15 now so the v19 side can diff the moment it comes up.
