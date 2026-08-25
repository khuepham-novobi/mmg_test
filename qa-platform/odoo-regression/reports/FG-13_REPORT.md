# FG-13 Report — Background Job Platform (Queue Jobs)

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
| TC-DAT-020 | Queue job history and channel configuration intact | P2 | NOT_PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-JOB-001 | Runner executes a job end to end | P0 | PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-JOB-002 | Failed job is visible and requeueable | P0 | PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-JOB-007 | Identity key prevents duplicate pending jobs | P0 | PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-SMK-010 | Queue job runner reachable and processing | P0 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-JOB-005 | Channel capacity limits are honoured | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-JOB-006 | Per-method retry policy applied | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-JOB-003 | Requeue a batch of failed jobs | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-JOB-004 | Force stuck jobs to done | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-JOB-013 | Garbage collector reclaims stuck jobs | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-JOB-014 | Autovacuum prunes old job records | P2 | NOT_PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-JOB-015 | Job chatter and activity assignment work | P2 | NOT_PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-JOB-016 | Job manager group restricts cancel/requeue | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-JOB-017 | Multi-company record rule isolates jobs | P2 | NOT_PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-JOB-008 | Identity override supersedes a stale pending job | P0 | PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-JOB-009 | Superseded job explains itself | P2 | NOT_PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-JOB-010 | Postgres lock contention becomes a postponed retry, not a failure | P0 | PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-JOB-012 | runjob route state locking works | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-JOB-018 | Test-mode passthrough works for automated tests | P2 | NOT_PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-JOB-011 | Job executes with the context it was enqueued in | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
