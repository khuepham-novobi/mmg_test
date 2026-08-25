# FG-10 Report — Shopify Storefront Integration

Generated 2026-08-19 09:42 by `scripts/gen_reports.py` from persisted execution results (`data/results.db`) and the workbook-synced registry. Expected results are the workbook's, verbatim.

## Counts

- Test cases: **33**
- Automated (covered by platform tests): **0** of 33 automatable
- Manual-only: **0**
- Currently BLOCKED (either environment): **0**
- Odoo 15: PASS 0 / FAIL 0 / BLOCKED 0 / SKIPPED 0 / not executed 33
- Odoo 19: PASS 0 / FAIL 0 / BLOCKED 0 / not executed 33

## Cross-version classification

| Classification | Count |
|---|---:|
| SAME_BEHAVIOR | 0 |
| REGRESSION_CANDIDATE | 0 |
| FIXED | 0 |
| SAME_FAILURE | 0 |
| BLOCKED | 0 |
| NOT_COMPARED | 33 |

> REGRESSION_CANDIDATE is not a confirmed regression until failure triage; BLOCKED reflects the missing local Odoo 19 environment (see docs/ENVIRONMENT_STATUS.md).

## Per test case

| TC | Title | Prio | Automation | v15 | v19 | Classification |
|---|---|---|---|---|---|---|
| TC-SHP-004 | Export art attributes to Shopify as metafields | P0 | PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-SHP-005 | Metafield comparison avoids redundant writes | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-SHP-006 | Metafield deletion when an attribute is cleared | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-SHP-019 | Product image upload → accept → thumbnail recompute | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-SHP-020 | Image download URL on channel images resolves | P2 | NOT_PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-SHP-024 | E-blast date carries between template and listing | P2 | NOT_PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-SHP-014 | Apply Collections and Tags in bulk (template level) | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-SHP-015 | Apply Collections and Tags in bulk (channel-listing level) | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-SHP-007 | Listing auto-unpublishes when stock reaches zero | P0 | PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-SHP-008 | Listing republishes when stock returns | P0 | PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-SHP-009 | Creating a sales order line triggers a Shopify stock update | P0 | PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-SHP-010 | Editing an order line quantity triggers a stock update | P0 | PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-SHP-011 | Deleting an order line triggers a stock update | P0 | PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-SHP-012 | Automatic inventory sync toggle per channel | P0 | PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-SHP-018 | The Shopify override of the export scheduler wins | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-SHP-017 | Exclude From Cart flag exports and bulk actions work | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-SHP-021 | SKU / default-code uniqueness enforced | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-SHP-022 | Default Store pre-selected in the export wizard | P2 | NOT_PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-SHP-023 | Stores field searchable on the product template | P2 | NOT_PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-SHP-013 | Per-listing success/failure chatter after an inventory sync | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-SHP-001 | Connect a Shopify store via OAuth | P0 | PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-SHP-002 | Disconnect a store | P2 | NOT_PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-SHP-033 | Shopify API version still supported | P0 | PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-SHP-003 | Import Shopify products, types, tags, collections and vendors | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-SHP-016 | Smart-collection rules parse and generate tags | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-SHP-026 | Import Shopify orders with fulfillment and payment status | P0 | PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-SHP-027 | Map Shopify locations to Odoo warehouses | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-SHP-028 | Process a Shopify return through the return wizard | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-SHP-029 | Post a fulfillment to Shopify from a picking | P0 | PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-SHP-030 | Post a fulfillment from a service picking | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-SHP-031 | Relation-field JS widget renders in collection rules | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-SHP-032 | ⚠ Verify each monkey patch actually took effect | P0 | PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-SHP-034 | Full Shopify order-to-cash regression | P0 | PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
