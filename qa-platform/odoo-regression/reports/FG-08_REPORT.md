# FG-08 Report — E-commerce Channel Management

Generated 2026-08-19 09:42 by `scripts/gen_reports.py` from persisted execution results (`data/results.db`) and the workbook-synced registry. Expected results are the workbook's, verbatim.

## Counts

- Test cases: **13**
- Automated (covered by platform tests): **0** of 13 automatable
- Manual-only: **0**
- Currently BLOCKED (either environment): **0**
- Odoo 15: PASS 0 / FAIL 0 / BLOCKED 0 / SKIPPED 0 / not executed 13
- Odoo 19: PASS 0 / FAIL 0 / BLOCKED 0 / not executed 13

## Cross-version classification

| Classification | Count |
|---|---:|
| SAME_BEHAVIOR | 0 |
| REGRESSION_CANDIDATE | 0 |
| FIXED | 0 |
| SAME_FAILURE | 0 |
| BLOCKED | 0 |
| NOT_COMPARED | 13 |

> REGRESSION_CANDIDATE is not a confirmed regression until failure triage; BLOCKED reflects the missing local Odoo 19 environment (see docs/ENVIRONMENT_STATUS.md).

## Per test case

| TC | Title | Prio | Automation | v15 | v19 | Classification |
|---|---|---|---|---|---|---|
| TC-CHN-004 | Debug logging captures request/response | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-CHN-001 | Existing channel configuration intact and the channel connects | P0 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-CHN-003 | Safe mode prevents writes to the live store | P0 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-CHN-005 | Channel sync state and last-sync timestamps preserved | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-CHN-006 | Unit and currency alignment refreshes from the platform | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-DAT-015 | Channel configuration and credentials intact | P0 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-CHN-002 | Create a new channel through the onboarding flow | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-CHN-007 | Channel customer mirror matches Odoo partners | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-CHN-008 | Shipping-address matching on partners | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-CHN-009 | Failed jobs with transient DB errors are requeued on schedule | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-CHN-010 | Scheduled inventory-quantity refresh runs | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-CHN-011 | Channel dashboard kanban with activity graph renders | P2 | NOT_PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-CHN-012 | Per-channel dynamic order menus still created | P2 | NOT_PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
