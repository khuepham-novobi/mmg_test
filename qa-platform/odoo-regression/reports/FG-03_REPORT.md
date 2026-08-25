# FG-03 Report — Sales Order Processing & Pricing

Generated 2026-08-19 09:42 by `scripts/gen_reports.py` from persisted execution results (`data/results.db`) and the workbook-synced registry. Expected results are the workbook's, verbatim.

## Counts

- Test cases: **27**
- Automated (covered by platform tests): **2** of 25 automatable
- Manual-only: **2**
- Currently BLOCKED (either environment): **0**
- Odoo 15: PASS 0 / FAIL 3 / BLOCKED 0 / SKIPPED 0 / not executed 24
- Odoo 19: PASS 0 / FAIL 0 / BLOCKED 0 / not executed 27

## Cross-version classification

| Classification | Count |
|---|---:|
| SAME_BEHAVIOR | 0 |
| REGRESSION_CANDIDATE | 0 |
| FIXED | 0 |
| SAME_FAILURE | 0 |
| BLOCKED | 0 |
| NOT_COMPARED | 27 |

> REGRESSION_CANDIDATE is not a confirmed regression until failure triage; BLOCKED reflects the missing local Odoo 19 environment (see docs/ENVIRONMENT_STATUS.md).

## Per test case

| TC | Title | Prio | Automation | v15 | v19 | Classification |
|---|---|---|---|---|---|---|
| TC-SAL-006 | Dollar discount converts to percentage (onchange) | P0 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-SAL-007 | Dollar discount converts on write (not just onchange) | P0 | AUTOMATED | ERROR | NOT_RUN | NOT_COMPARED |
| TC-SAL-008 | Dollar discount on a bulk line update does not recurse | P1 | MANUAL_ONLY | MANUAL | MANUAL | NOT_COMPARED |
| TC-SAL-019 | Order with a 100%-discounted line | P2 | NOT_PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-SAL-020 | Order line with qty 0 | P2 | NOT_PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-SAL-001 | Pick up at Store rewrites the delivery address | P0 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-SAL-002 | Un-ticking Pick up at Store | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-SAL-022 | Duplicate a sales order | P2 | NOT_PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-DAT-010 | Sale-order → invoice linkage intact | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-SAL-003 | Display Invoices on the order excludes cancelled | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-SAL-016 | Auto-invoice setting is per company | P2 | NOT_PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-SAL-013 | Auto-create invoice on confirm, single order | P0 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-SAL-014 | ⚠ Auto-create invoice on a MULTI-order confirm — suspected defect | P0 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-SAL-015 | Auto-create invoice disabled → no invoice on confirm | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-SAL-021 | Cancel a confirmed order that has an auto-created invoice | P1 | CANDIDATE | ERROR | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-NEW-001 | Decide: keep or retire mmg_sale_delivery_status 🔻 | P1 | MANUAL_ONLY | MANUAL | MANUAL | NOT_COMPARED |
| TC-SAL-004 | Delivery status derives from transfers | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-SAL-005 | Delivery status is groupable and filterable in the list | P2 | NOT_PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-SAL-009 | Order warning banner appears when a line has a warned product | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-SAL-010 | Warned-product pop-up lists every warned product with its message | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-SAL-012 | Banner clears when the warned line is removed | P2 | NOT_PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-SAL-011 | Warning fields settable at template level | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-STU-004 | sale.order.line.x_discount (Discount $) preserved and still drives dis | P0 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-DAT-009 | Sales order totals reconcile by year and state | P0 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-SAL-017 | Quotation → confirm → deliver → invoice → pay, happy path | P0 | AUTOMATED | ERROR | NOT_RUN | NOT_COMPARED |
| TC-SAL-018 | Credit note from a posted invoice | P1 | CANDIDATE | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |
| TC-SAL-023 | Sales order print (quotation PDF) | P2 | NOT_PLANNED | NOT_IMPLEMENTED | NOT_IMPLEMENTED | NOT_COMPARED |

## Failure notes (triage input)

- **TC-SAL-007** [Odoo 15 → ERROR / —] OdooRPCError: sale.order.create failed: - Product: QA AUTO PRODUCT (do not sell)
- **TC-SAL-021** [Odoo 15 → ERROR / —] OdooRPCError: sale.order.create failed: - Product: QA AUTO PRODUCT (do not sell)
- **TC-SAL-017** [Odoo 15 → ERROR / AUTOMATION_ERROR] TimeoutError: Locator.click: Timeout 30000ms exceeded.
Call log:
  - waiting for locator("button[type='submit']").first
    - locator resolved to <button type="submit" class="btn btn-primary btn-block">Log in</button>
  - attempting click action
    - waiting 
