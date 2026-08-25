# FG-06 Report — Customer & Vendor Deposits

Generated 2026-08-19 09:42 by `scripts/gen_reports.py` from persisted execution results (`data/results.db`) and the workbook-synced registry. Expected results are the workbook's, verbatim.

## Counts

- Test cases: **23**
- Automated (covered by platform tests): **0** of 22 automatable
- Manual-only: **1**
- Currently BLOCKED (either environment): **0**
- Odoo 15: PASS 0 / FAIL 0 / BLOCKED 0 / SKIPPED 0 / not executed 23
- Odoo 19: PASS 0 / FAIL 0 / BLOCKED 0 / not executed 23

## Cross-version classification

| Classification | Count |
|---|---:|
| SAME_BEHAVIOR | 0 |
| REGRESSION_CANDIDATE | 0 |
| FIXED | 0 |
| SAME_FAILURE | 0 |
| BLOCKED | 0 |
| NOT_COMPARED | 23 |

> REGRESSION_CANDIDATE is not a confirmed regression until failure triage; BLOCKED reflects the missing local Odoo 19 environment (see docs/ENVIRONMENT_STATUS.md).

## Per test case

| TC | Title | Prio | Automation | v15 | v19 | Classification |
|---|---|---|---|---|---|---|
| TC-DEP-018 | Payment-widget QWeb override still renders | P2 | NOT_PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-DAT-019 | Partner fiscal positions and deposit-account properties intact | P0 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-DEP-002 | Deposit accounts configurable per company | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-DEP-003 | Deposit accounts configurable per partner (company-dependent property) | P0 | PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-DEP-015 | Deposit journals configurable per company | P2 | NOT_PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-DAT-016 | Deposit data intact | P0 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-DEP-007 | Deposit is applied to the invoice raised from the order | P0 | PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-DEP-008 | Link a deposit to a purchase order (vendor side) | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-DEP-010 | Reset a deposit payment to draft | P0 | PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-DEP-011 | Reset a deposit's journal entry to draft | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-DEP-012 | Deposit Order wizard — fixed amount with a currency | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-DEP-017 | Deposit larger than the invoice total | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-DEP-020 | Is a Deposit? flag preserved on all historical payments | P0 | PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-NEW-004 | Decide: account_partner_deposit vs native down payments 🔻 | P0 | MANUAL_ONLY | MANUAL | MANUAL | NOT_COMPARED |
| TC-DEP-001 | Record a customer payment as a deposit | P0 | PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-DEP-009 | Outstanding deposits visible on the contact | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-DEP-014 | Deposit balances reconcile in the GL after upgrade | P0 | PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-DEP-019 | Deposit on a channel order via payment mapping | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-DEP-004 | Take a deposit from a sales order (fixed amount) | P0 | PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-DEP-005 | Take a deposit as a percentage of the order | P0 | PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-DEP-013 | Cancel a deposit | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-DEP-016 | Multiple deposits on one order | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-DEP-006 | Deposit smart button opens the linked deposits | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
