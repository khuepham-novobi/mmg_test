# FG-04 Report — Bulk Data Maintenance Wizards

Generated 2026-08-19 09:42 by `scripts/gen_reports.py` from persisted execution results (`data/results.db`) and the workbook-synced registry. Expected results are the workbook's, verbatim.

## Counts

- Test cases: **18**
- Automated (covered by platform tests): **16** of 17 automatable
- Manual-only: **1**
- Currently BLOCKED (either environment): **16**
- Odoo 15: PASS 12 / FAIL 3 / BLOCKED 1 / SKIPPED 0 / not executed 2
- Odoo 19: PASS 0 / FAIL 0 / BLOCKED 16 / not executed 2

## Cross-version classification

| Classification | Count |
|---|---:|
| SAME_BEHAVIOR | 0 |
| REGRESSION_CANDIDATE | 0 |
| FIXED | 0 |
| SAME_FAILURE | 0 |
| BLOCKED | 16 |
| NOT_COMPARED | 2 |

> REGRESSION_CANDIDATE is not a confirmed regression until failure triage; BLOCKED reflects the missing local Odoo 19 environment (see docs/ENVIRONMENT_STATUS.md).

## Per test case

| TC | Title | Prio | Automation | v15 | v19 | Classification |
|---|---|---|---|---|---|---|
| TC-BLK-008 | Assign Product Category replaces categ_id | P1 | AUTOMATED | FAIL | BLOCKED | BLOCKED |
| TC-BLK-009 | Assign Website Extra Category adds to the set and recomputes | P1 | AUTOMATED | FAIL | BLOCKED | BLOCKED |
| TC-BLK-001 | Assign Customer Taxes to selected templates | P0 | AUTOMATED | PASS | BLOCKED | BLOCKED |
| TC-BLK-002 | Assign Customer Taxes defaults to the company sale tax | P1 | AUTOMATED | PASS | BLOCKED | BLOCKED |
| TC-BLK-004 | Assign Customer Taxes works from the variant list too | P2 | AUTOMATED | PASS | BLOCKED | BLOCKED |
| TC-BLK-017 | ACL: a non-privileged user cannot run the tax/fiscal wizards | P1 | AUTOMATED | FAIL | BLOCKED | BLOCKED |
| TC-BLK-003 | Assign Customer Taxes blocks an empty selection | P1 | AUTOMATED | PASS | BLOCKED | BLOCKED |
| TC-BLK-005 | Assign Fiscal Position to selected partners | P0 | AUTOMATED | PASS | BLOCKED | BLOCKED |
| TC-BLK-007 | Assign Fiscal Position in a multi-company context | P2 | AUTOMATED | BLOCKED | BLOCKED | BLOCKED |
| TC-BLK-006 | Assign Fiscal Position blocks an empty selection | P1 | AUTOMATED | PASS | BLOCKED | BLOCKED |
| TC-BLK-010 | Update Customer Type writes x_type | P1 | AUTOMATED | PASS | BLOCKED | BLOCKED |
| TC-BLK-011 | Update Customer Type surfaces the field-missing guard | P2 | NOT_PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-BLK-012 | Update Customer Type requires a value | P3 | AUTOMATED | PASS | BLOCKED | BLOCKED |
| TC-BLK-013 | Each wizard's menu/Action entry appears on the right list view | P1 | AUTOMATED | PASS | BLOCKED | BLOCKED |
| TC-BLK-014 | Bulk wizard on 1,000 selected records | P1 | MANUAL_ONLY | MANUAL | MANUAL | NOT_COMPARED |
| TC-BLK-015 | Bulk wizard respects the current selection only | P0 | AUTOMATED | PASS | BLOCKED | BLOCKED |
| TC-BLK-016 | Bulk wizard with "select all" across a filtered domain | P1 | AUTOMATED | PASS | BLOCKED | BLOCKED |
| TC-BLK-018 | Wizard writes are attributable | P2 | AUTOMATED | PASS | BLOCKED | BLOCKED |

## Failure notes (triage input)

- **TC-BLK-008** [Odoo 15 → FAIL / ASSERTION] wizard.state: expected 'select', got "field 'state' missing — this wizard has no confirmation flow (v15 behaviour)"
- **TC-BLK-009** [Odoo 15 → FAIL / ASSERTION] empty pick raised UserError 'Missing Website Extra Category.': expected True, got 'no error raised'
- **TC-BLK-017** [Odoo 15 → FAIL / ASSERTION] assign.customer.taxes.wizard create denied (AccessError): expected True, got 'created — no access error'

## Feasibility decisions

implemented 16 · blocked_stub 0 · not_implemented 2 (details: `reports/data/fg04_feasibility.json`)
