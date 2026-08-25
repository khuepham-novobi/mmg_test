# FG-02 Report — Certificates of Authenticity & Label Printing

Generated 2026-08-19 09:42 by `scripts/gen_reports.py` from persisted execution results (`data/results.db`) and the workbook-synced registry. Expected results are the workbook's, verbatim.

## Counts

- Test cases: **13**
- Automated (covered by platform tests): **12** of 12 automatable
- Manual-only: **1**
- Currently BLOCKED (either environment): **4**
- Odoo 15: PASS 0 / FAIL 8 / BLOCKED 4 / SKIPPED 0 / not executed 1
- Odoo 19: PASS 0 / FAIL 0 / BLOCKED 0 / not executed 13

## Cross-version classification

| Classification | Count |
|---|---:|
| SAME_BEHAVIOR | 0 |
| REGRESSION_CANDIDATE | 0 |
| FIXED | 0 |
| SAME_FAILURE | 0 |
| BLOCKED | 4 |
| NOT_COMPARED | 9 |

> REGRESSION_CANDIDATE is not a confirmed regression until failure triage; BLOCKED reflects the missing local Odoo 19 environment (see docs/ENVIRONMENT_STATUS.md).

## Per test case

| TC | Title | Prio | Automation | v15 | v19 | Classification |
|---|---|---|---|---|---|---|
| TC-LBL-001 | Certificate of authenticity prints for a variant | P0 | AUTOMATED | BLOCKED | NOT_RUN | BLOCKED |
| TC-LBL-002 | Certificate template fallback — full provenance and date | P0 | AUTOMATED | BLOCKED | NOT_RUN | BLOCKED |
| TC-LBL-003 | Certificate template fallback — no date | P0 | AUTOMATED | BLOCKED | NOT_RUN | BLOCKED |
| TC-LBL-004 | Certificate template fallback — no provenance | P0 | AUTOMATED | BLOCKED | NOT_RUN | BLOCKED |
| TC-LBL-005 | Certificate template fallback — neither date nor provenance | P0 | AUTOMATED | ERROR | NOT_RUN | NOT_COMPARED |
| TC-LBL-006 | Certificate prints from the template (not just the variant) | P1 | AUTOMATED | ERROR | NOT_RUN | NOT_COMPARED |
| TC-NEW-005 | Record the LibreOffice single point of failure | P2 | MANUAL_ONLY | MANUAL | MANUAL | NOT_COMPARED |
| TC-SMK-011 | Certificate / label rendering pipeline alive | P0 | AUTOMATED | ERROR | NOT_RUN | NOT_COMPARED |
| TC-LBL-007 | Certificate cites the most recent confirmed sale | P1 | AUTOMATED | ERROR | NOT_RUN | NOT_COMPARED |
| TC-LBL-008 | Avery 30-per-page labels | P0 | AUTOMATED | ERROR | NOT_RUN | NOT_COMPARED |
| TC-LBL-009 | Avery 60 / 90 / 120-per-page labels | P1 | AUTOMATED | ERROR | NOT_RUN | NOT_COMPARED |
| TC-LBL-010 | 6-up Backtag prints | P1 | AUTOMATED | ERROR | NOT_RUN | NOT_COMPARED |
| TC-LBL-011 | Label printing works from both template and variant lists | P1 | AUTOMATED | ERROR | NOT_RUN | NOT_COMPARED |

## Failure notes (triage input)

- **TC-LBL-005** [Odoo 15 → ERROR / INTERRUPTED] Interrupted — the runner process stopped before this execution finished. Re-run the test.
- **TC-LBL-006** [Odoo 15 → ERROR / INTERRUPTED] Interrupted — the runner process stopped before this execution finished. Re-run the test.
- **TC-SMK-011** [Odoo 15 → ERROR / INTERRUPTED] Interrupted — the runner process stopped before this execution finished. Re-run the test.
- **TC-LBL-007** [Odoo 15 → ERROR / INTERRUPTED] Interrupted — the runner process stopped before this execution finished. Re-run the test.
- **TC-LBL-008** [Odoo 15 → ERROR / INTERRUPTED] Interrupted — the runner process stopped before this execution finished. Re-run the test.
- **TC-LBL-009** [Odoo 15 → ERROR / INTERRUPTED] Interrupted — the runner process stopped before this execution finished. Re-run the test.
- **TC-LBL-010** [Odoo 15 → ERROR / INTERRUPTED] Interrupted — the runner process stopped before this execution finished. Re-run the test.
- **TC-LBL-011** [Odoo 15 → ERROR / INTERRUPTED] Interrupted — the runner process stopped before this execution finished. Re-run the test.

## Feasibility decisions

implemented 0 · blocked_stub 12 · not_implemented 1 (details: `reports/data/fg02_feasibility.json`)
