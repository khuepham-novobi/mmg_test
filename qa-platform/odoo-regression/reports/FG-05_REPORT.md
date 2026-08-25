# FG-05 Report — Tax Computation — Avalara AvaTax

Generated 2026-08-19 09:42 by `scripts/gen_reports.py` from persisted execution results (`data/results.db`) and the workbook-synced registry. Expected results are the workbook's, verbatim.

## Counts

- Test cases: **20**
- Automated (covered by platform tests): **0** of 20 automatable
- Manual-only: **0**
- Currently BLOCKED (either environment): **0**
- Odoo 15: PASS 0 / FAIL 0 / BLOCKED 0 / SKIPPED 0 / not executed 20
- Odoo 19: PASS 0 / FAIL 0 / BLOCKED 0 / not executed 20

## Cross-version classification

| Classification | Count |
|---|---:|
| SAME_BEHAVIOR | 0 |
| REGRESSION_CANDIDATE | 0 |
| FIXED | 0 |
| SAME_FAILURE | 0 |
| BLOCKED | 0 |
| NOT_COMPARED | 20 |

> REGRESSION_CANDIDATE is not a confirmed regression until failure triage; BLOCKED reflects the missing local Odoo 19 environment (see docs/ENVIRONMENT_STATUS.md).

## Per test case

| TC | Title | Prio | Automation | v15 | v19 | Classification |
|---|---|---|---|---|---|---|
| TC-DAT-017 | Avatax configuration intact | P0 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-TAX-002 | Tax posts per jurisdiction and account, not as one rolled-up amount | P0 | PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-TAX-003 | Per-jurisdiction taxes are reused, not duplicated | P0 | PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-TAX-016 | Multi-line invoice with mixed taxable and exempt products | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-TAX-018 | Historical Avatax invoices remain unchanged after upgrade | P0 | PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-TAX-004 | Posting is blocked when the Odoo tax total ≠ Avalara's summary | P0 | PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-TAX-005 | Guard error when a tax line cannot be mapped and the amount is non-zer | P0 | PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-TAX-006 | Guard error when a tax distribution has multiple accounts | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-TAX-007 | Ship-to (delivery) address completeness is validated, not the invoicin | P0 | PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-SHP-025 | Avatax values prepared when exporting to Shopify | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-TAX-001 | Tax computed on an invoice with an Avatax fiscal position | P0 | PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-TAX-008 | Tax preview on a quotation before sending | P0 | PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-TAX-009 | Tax recomputes when the delivery address changes | P0 | PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-TAX-010 | Order-to-invoice tax carry-over | P0 | PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-TAX-011 | Posting an invoice commits the transaction to Avalara | P0 | PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-TAX-012 | Cancelling an invoice voids the Avalara transaction | P0 | PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-TAX-013 | Exempt customer is charged no tax | P0 | PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-TAX-014 | Avatax category on product category drives the tax code | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-TAX-015 | Credit note tax uses the AvaTax Refund Account | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-TAX-017 | Avalara service unavailable — graceful failure | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
