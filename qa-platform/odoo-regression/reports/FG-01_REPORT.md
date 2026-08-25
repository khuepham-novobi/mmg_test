# FG-01 Report — Art Catalogue & Product Master Data

Generated 2026-08-19 09:42 by `scripts/gen_reports.py` from persisted execution results (`data/results.db`) and the workbook-synced registry. Expected results are the workbook's, verbatim.

## Counts

- Test cases: **36**
- Automated (covered by platform tests): **35** of 35 automatable
- Manual-only: **1**
- Currently BLOCKED (either environment): **35**
- Odoo 15: PASS 21 / FAIL 14 / BLOCKED 0 / SKIPPED 0 / not executed 1
- Odoo 19: PASS 0 / FAIL 0 / BLOCKED 35 / not executed 1

## Cross-version classification

| Classification | Count |
|---|---:|
| SAME_BEHAVIOR | 0 |
| REGRESSION_CANDIDATE | 0 |
| FIXED | 0 |
| SAME_FAILURE | 0 |
| BLOCKED | 35 |
| NOT_COMPARED | 1 |

> REGRESSION_CANDIDATE is not a confirmed regression until failure triage; BLOCKED reflects the missing local Odoo 19 environment (see docs/ENVIRONMENT_STATUS.md).

## Per test case

| TC | Title | Prio | Automation | v15 | v19 | Classification |
|---|---|---|---|---|---|---|
| TC-NEW-007 | Decide: fix or retire the inventory-value feature | P1 | MANUAL_ONLY | MANUAL | MANUAL | NOT_COMPARED |
| TC-STU-009 | ⚠ Decision: the inventory-value feature has never worked | P1 | AUTOMATED | PASS | BLOCKED | BLOCKED |
| TC-ART-001 | Create an art item with the full catalogue record | P0 | AUTOMATED | FAIL | BLOCKED | BLOCKED |
| TC-ART-002 | All ~35 art fields are visible and editable after upgrade | P0 | AUTOMATED | FAIL | BLOCKED | BLOCKED |
| TC-ART-014 | Medium reference records list/form CRUD | P2 | AUTOMATED | PASS | BLOCKED | BLOCKED |
| TC-ART-015 | Product Colour reference CRUD + seed data present | P3 | AUTOMATED | PASS | BLOCKED | BLOCKED |
| TC-ART-016 | Product Origin reference CRUD + seed data present | P3 | AUTOMATED | PASS | BLOCKED | BLOCKED |
| TC-ART-017 | Product Style reference CRUD | P3 | AUTOMATED | PASS | BLOCKED | BLOCKED |
| TC-ART-018 | Product (art) Category reference CRUD | P3 | AUTOMATED | PASS | BLOCKED | BLOCKED |
| TC-ART-019 | Search/filter products by Artist | P1 | AUTOMATED | FAIL | BLOCKED | BLOCKED |
| TC-ART-020 | Search/filter products by Medium | P1 | AUTOMATED | FAIL | BLOCKED | BLOCKED |
| TC-ART-021 | Group products by art Category | P2 | AUTOMATED | FAIL | BLOCKED | BLOCKED |
| TC-ART-023 | Product list view custom columns intact | P2 | AUTOMATED | FAIL | BLOCKED | BLOCKED |
| TC-ART-024 | Import 20 art items via base_import with art fields | P1 | AUTOMATED | PASS | BLOCKED | BLOCKED |
| TC-ART-025 | Export 20 art items to XLSX with art fields | P2 | AUTOMATED | PASS | BLOCKED | BLOCKED |
| TC-ART-026 | Archive / unarchive an art item | P2 | AUTOMATED | PASS | BLOCKED | BLOCKED |
| TC-DAT-011 | All ~35 mmg_stock art fields preserved with data | P0 | AUTOMATED | FAIL | BLOCKED | BLOCKED |
| TC-DAT-012 | Reference catalogues preserved | P1 | AUTOMATED | PASS | BLOCKED | BLOCKED |
| TC-STU-008 | Studio manual model x_medium vs code model x.medium — retire the dupli | P1 | AUTOMATED | FAIL | BLOCKED | BLOCKED |
| TC-STU-014 | product.product.x_desc, x_image, x_length, x_studio_shipping preserved | P2 | AUTOMATED | PASS | BLOCKED | BLOCKED |
| TC-ART-011 | Auction data capture | P1 | AUTOMATED | PASS | BLOCKED | BLOCKED |
| TC-ART-007 | Website extra categories compute correctly | P1 | AUTOMATED | FAIL | BLOCKED | BLOCKED |
| TC-ART-013 | Image download field usable for channel export | P2 | AUTOMATED | PASS | BLOCKED | BLOCKED |
| TC-DAT-013 | website_extra_categories and x_categ_ids preserved | P1 | AUTOMATED | PASS | BLOCKED | BLOCKED |
| TC-ART-003 | Template ↔ variant field synchronisation still works | P0 | AUTOMATED | FAIL | BLOCKED | BLOCKED |
| TC-ART-004 | Numeric-barcode constraint enforced on template and variant | P1 | AUTOMATED | PASS | BLOCKED | BLOCKED |
| TC-ART-005 | Duplicating an art item does not clone the barcode | P1 | AUTOMATED | FAIL | BLOCKED | BLOCKED |
| TC-ART-008 | Exclude-from-cart bulk activate / deactivate | P1 | AUTOMATED | PASS | BLOCKED | BLOCKED |
| TC-ART-006 | Vendor visible on stock quants | P1 | AUTOMATED | FAIL | BLOCKED | BLOCKED |
| TC-ART-012 | Purchase views retain the art/consignment context | P2 | AUTOMATED | FAIL | BLOCKED | BLOCKED |
| TC-ART-022 | Gallery Cost and Consignment % editable and stored | P1 | AUTOMATED | PASS | BLOCKED | BLOCKED |
| TC-ART-009 | Museum-membership purchase date on a contact | P2 | AUTOMATED | PASS | BLOCKED | BLOCKED |
| TC-ART-010 | Main Phone on partner and user | P2 | AUTOMATED | FAIL | BLOCKED | BLOCKED |
| TC-STU-005 | Studio image-URL gallery (x_image_1 … x_image_47) preserved | P1 | AUTOMATED | PASS | BLOCKED | BLOCKED |
| TC-DAT-007 | Stock on-hand quantities match per product/location | P0 | AUTOMATED | PASS | BLOCKED | BLOCKED |
| TC-DAT-008 | Inventory valuation matches | P0 | AUTOMATED | PASS | BLOCKED | BLOCKED |

## Failure notes (triage input)

- **TC-ART-001** [Odoo 15 → FAIL / ASSERTION] variant.x_artist: expected 'Maynard Dixon', got False
- **TC-ART-002** [Odoo 15 → FAIL / ASSERTION] missing template form fields (must be empty): expected [], got ['x_image_1', 'x_image_2', 'x_image_3', 'x_image_4', 'x_image_5', 'x_image_6', 'x_image_7', 'x_image_8', 'x_image_9', 'x_image_10', 'x_image_11', 'x_image_12', 'x_image_13', 'x_image_14', 'x_image_
- **TC-ART-019** [Odoo 15 → FAIL / ASSERTION] variant ilike match (template ids): expected [188212], got []
- **TC-ART-020** [Odoo 15 → FAIL / ASSERTION] variant oil filter (template ids): expected [188220, 188221], got []
- **TC-ART-021** [Odoo 15 → FAIL / ASSERTION] product.product group counts: expected [(68, 3), (69, 1)], got []
- **TC-ART-023** [Odoo 15 → FAIL / ASSERTION] missing list columns (must be empty): expected [], got ['barcode']
- **TC-DAT-011** [Odoo 15 → FAIL / ASSERTION] anchor product_template.__total: expected 69201, got 69316
- **TC-STU-008** [Odoo 15 → FAIL / ASSERTION] anchor template_refs: expected 13972, got 14001
- **TC-ART-007** [Odoo 15 → FAIL / ASSERTION] compute cleared to falsy on last removal: expected False, got 'FG01 Web Categ 1'
- **TC-ART-003** [Odoo 15 → FAIL / ASSERTION] variant.x_artist: expected 'FG01-Dixon', got False
- **TC-ART-005** [Odoo 15 → FAIL / ASSERTION] multi-record duplicate works, values zipped: expected ['FG01-MultiA', 'FG01-MultiB'], got 'copy() failed on multi-record set: product.product.copy failed: Expected singleton: product.product(192738, 192739)'
- **TC-ART-006** [Odoo 15 → FAIL / ASSERTION] quants groupable by x_vendor (read_group): expected True, got "not groupable: stock.quant.read_group failed: Field stock.quant.x_vendor is not a stored field, only stored fields (regular or many2many) are valid for the 'groupby' parameter"
- **TC-ART-012** [Odoo 15 → FAIL / ASSERTION] x_vendor: expected 'Consignor A', got False
- **TC-ART-010** [Odoo 15 → FAIL / ASSERTION] user.x_main_phone: expected '520-555-0100', got False
