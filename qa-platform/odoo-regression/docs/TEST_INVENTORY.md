# Test Inventory — FG-01 → FG-14

Generated 2026-08-18 09:57 by `scripts/gen_inventory_doc.py`.

**Source of truth:** `D:\Projects\mmg\MMG_v19_Test_Cases_Grouped_by_Feature_v3.0.xlsx`, sheet **Automation Export** (read-only — the platform never writes to the workbook).

Full capture of every test case — including **preconditions, steps and the verbatim expected result** — lives in `data/test_registry.json` (regenerate with `python scripts/sync_registry.py`) and is browsable per test case in the web UI (`#/testcase/<TC-ID>`). Expected results are imported verbatim and are never modified by the platform.

## Summary

| Feature group | Name | Test cases | P0 | P1 | P2 | P3 |
|---|---|---:|---:|---:|---:|---:|
| FG-01 | Art Catalogue & Product Master Data | 36 | 6 | 16 | 10 | 4 |
| FG-02 | Certificates of Authenticity & Label Printing | 13 | 7 | 5 | 1 | 0 |
| FG-03 | Sales Order Processing & Pricing | 27 | 8 | 12 | 7 | 0 |
| FG-04 | Bulk Data Maintenance Wizards | 18 | 3 | 10 | 4 | 1 |
| FG-05 | Tax Computation — Avalara AvaTax | 20 | 14 | 6 | 0 | 0 |
| FG-06 | Customer & Vendor Deposits | 23 | 11 | 10 | 2 | 0 |
| FG-07 | Invoicing, Payments & Accounting Documents | 25 | 7 | 10 | 7 | 1 |
| FG-08 | E-commerce Channel Management | 13 | 3 | 8 | 2 | 0 |
| FG-09 | Product Listings & Channel Catalogue (PIM) | 24 | 6 | 13 | 5 | 0 |
| FG-10 | Shopify Storefront Integration | 33 | 13 | 15 | 5 | 0 |
| FG-11 | Omnichannel Order Processing | 23 | 6 | 14 | 3 | 0 |
| FG-12 | Fulfillment & Inventory Sync | 18 | 6 | 11 | 1 | 0 |
| FG-13 | Background Job Platform (Queue Jobs) | 20 | 6 | 8 | 6 | 0 |
| FG-14 | Integration Monitoring & Logging | 10 | 4 | 5 | 1 | 0 |
| **Total** | | **303** | **100** | **143** | **54** | **6** |

### Automation classification (Step 3)

Derived deterministically from the workbook `automation_approach` column (mapping in `scripts/sync_registry.py::_APPROACH_MAP`):

| automation_type | Count | Meaning |
|---|---:|---|
| PYTHON_UNIT | 193 | Odoo `TransactionCase` test inside the Odoo test runner |
| ORM_INTEGRATION | 3 | `odoo-bin` install/upgrade + registry & log checks |
| API | 54 | Connector integration test vs sandbox / mocked API (`TEST_QUEUE_JOB_NO_DELAY=1`) |
| UI | 0 | Playwright browser workflow driven by this platform |
| HTTP_CASE | 5 | Odoo `HttpCase` endpoint test (+ manual security review) |
| TOUR | 8 | Odoo tour (`HttpCase` / `browser_js`) |
| HOOT | 0 | Odoo 17+ JS unit test (none in FG-01..14 scope) |
| DATA_RECONCILIATION | 31 | SQL/ORM comparison — v15 baseline vs v19 |
| MANUAL | 9 | Human execution required (decision gates, perf baselines, one-off checks) |
| NOT_APPLICABLE | 0 | Not applicable to the v19 scope |

### Automation status

| automation_status | Count | Meaning |
|---|---:|---|
| AUTOMATED | 3 | Covered by a registered platform test today |
| PLANNED | 50 | Workbook Wave 1 — automate now |
| CANDIDATE | 183 | Workbook Wave 2 — candidate |
| NOT_PLANNED | 58 | Automatable type but workbook says manual for now |
| MANUAL_ONLY | 9 | Not automatable (decision gates, perf baselines) |

---

## FG-01 — Art Catalogue & Product Master Data (36 test cases)

> Managing the art item master record for 69,201 products: artist, medium, dimensions, edition, provenance, auction data, reference catalogues, barcode integrity, template/variant sync, vendor & consignment cost data, Studio image gallery, and the (broken) inventory-value feature.
>
> **Key modules:** mmg_stock, mmg_automated_action, Odoo Studio · **Roles:** Art Cataloguer, Inventory Manager, Gallery Manager

| TC ID | Title | Prio | Type | Automation | Status | Src row |
|---|---|---|---|---|---|---:|
| TC-NEW-007 | Decide: fix or retire the inventory-value feature | P1 | FUNC | MANUAL | MANUAL_ONLY | 2 |
| TC-STU-009 | ⚠ Decision: the inventory-value feature has never worked | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 3 |
| TC-ART-001 | Create an art item with the full catalogue record | P0 | FUNC | PYTHON_UNIT | AUTOMATED | 4 |
| TC-ART-002 | All ~35 art fields are visible and editable after upgrade | P0 | UI | TOUR | CANDIDATE | 5 |
| TC-ART-014 | Medium reference records list/form CRUD | P2 | FUNC | PYTHON_UNIT | NOT_PLANNED | 6 |
| TC-ART-015 | Product Colour reference CRUD + seed data present | P3 | FUNC | PYTHON_UNIT | NOT_PLANNED | 7 |
| TC-ART-016 | Product Origin reference CRUD + seed data present | P3 | FUNC | PYTHON_UNIT | NOT_PLANNED | 8 |
| TC-ART-017 | Product Style reference CRUD | P3 | FUNC | PYTHON_UNIT | NOT_PLANNED | 9 |
| TC-ART-018 | Product (art) Category reference CRUD | P3 | FUNC | PYTHON_UNIT | NOT_PLANNED | 10 |
| TC-ART-019 | Search/filter products by Artist | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 11 |
| TC-ART-020 | Search/filter products by Medium | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 12 |
| TC-ART-021 | Group products by art Category | P2 | FUNC | PYTHON_UNIT | NOT_PLANNED | 13 |
| TC-ART-023 | Product list view custom columns intact | P2 | UI | TOUR | NOT_PLANNED | 14 |
| TC-ART-024 | Import 20 art items via base_import with art fields | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 15 |
| TC-ART-025 | Export 20 art items to XLSX with art fields | P2 | FUNC | PYTHON_UNIT | NOT_PLANNED | 16 |
| TC-ART-026 | Archive / unarchive an art item | P2 | REGR | PYTHON_UNIT | NOT_PLANNED | 17 |
| TC-DAT-011 | All ~35 mmg_stock art fields preserved with data | P0 | DATA | DATA_RECONCILIATION | CANDIDATE | 18 |
| TC-DAT-012 | Reference catalogues preserved | P1 | DATA | DATA_RECONCILIATION | CANDIDATE | 19 |
| TC-STU-008 | Studio manual model x_medium vs code model x.medium — retire the duplicate | P1 | DATA | DATA_RECONCILIATION | CANDIDATE | 20 |
| TC-STU-014 | product.product.x_desc, x_image, x_length, x_studio_shipping preserved | P2 | DATA | DATA_RECONCILIATION | NOT_PLANNED | 21 |
| TC-ART-011 | Auction data capture | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 22 |
| TC-ART-007 | Website extra categories compute correctly | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 23 |
| TC-ART-013 | Image download field usable for channel export | P2 | FUNC | PYTHON_UNIT | NOT_PLANNED | 24 |
| TC-DAT-013 | website_extra_categories and x_categ_ids preserved | P1 | DATA | DATA_RECONCILIATION | CANDIDATE | 25 |
| TC-ART-003 | Template ↔ variant field synchronisation still works | P0 | FUNC | PYTHON_UNIT | CANDIDATE | 26 |
| TC-ART-004 | Numeric-barcode constraint enforced on template and variant | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 27 |
| TC-ART-005 | Duplicating an art item does not clone the barcode | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 28 |
| TC-ART-008 | Exclude-from-cart bulk activate / deactivate | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 29 |
| TC-ART-006 | Vendor visible on stock quants | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 30 |
| TC-ART-012 | Purchase views retain the art/consignment context | P2 | FUNC | PYTHON_UNIT | NOT_PLANNED | 31 |
| TC-ART-022 | Gallery Cost and Consignment % editable and stored | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 32 |
| TC-ART-009 | Museum-membership purchase date on a contact | P2 | FUNC | PYTHON_UNIT | NOT_PLANNED | 33 |
| TC-ART-010 | Main Phone on partner and user | P2 | FUNC | PYTHON_UNIT | NOT_PLANNED | 34 |
| TC-STU-005 | Studio image-URL gallery (x_image_1 … x_image_47) preserved | P1 | DATA | DATA_RECONCILIATION | CANDIDATE | 35 |
| TC-DAT-007 | Stock on-hand quantities match per product/location | P0 | DATA | DATA_RECONCILIATION | CANDIDATE | 36 |
| TC-DAT-008 | Inventory valuation matches | P0 | DATA | DATA_RECONCILIATION | CANDIDATE | 37 |

## FG-02 — Certificates of Authenticity & Label Printing (13 test cases)

> Printing certificates of authenticity and Avery labels / backtags through the py3o + LibreOffice pipeline. Business-critical gallery documents — single point of failure if LibreOffice is absent.
>
> **Key modules:** mmg_report, mmg_stock, report_py3o (OCA engine) · **Roles:** Gallery Manager, Art Cataloguer

| TC ID | Title | Prio | Type | Automation | Status | Src row |
|---|---|---|---|---|---|---:|
| TC-LBL-001 | Certificate of authenticity prints for a variant | P0 | FUNC | PYTHON_UNIT | CANDIDATE | 38 |
| TC-LBL-002 | Certificate template fallback — full provenance and date | P0 | FUNC | PYTHON_UNIT | CANDIDATE | 39 |
| TC-LBL-003 | Certificate template fallback — no date | P0 | FUNC | PYTHON_UNIT | CANDIDATE | 40 |
| TC-LBL-004 | Certificate template fallback — no provenance | P0 | FUNC | PYTHON_UNIT | CANDIDATE | 41 |
| TC-LBL-005 | Certificate template fallback — neither date nor provenance | P0 | FUNC | PYTHON_UNIT | CANDIDATE | 42 |
| TC-LBL-006 | Certificate prints from the template (not just the variant) | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 43 |
| TC-NEW-005 | Record the LibreOffice single point of failure | P2 | FUNC | MANUAL | MANUAL_ONLY | 44 |
| TC-SMK-011 | Certificate / label rendering pipeline alive | P0 | SMOKE | ORM_INTEGRATION | CANDIDATE | 45 |
| TC-LBL-007 | Certificate cites the most recent confirmed sale | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 46 |
| TC-LBL-008 | Avery 30-per-page labels | P0 | FUNC | PYTHON_UNIT | CANDIDATE | 47 |
| TC-LBL-009 | Avery 60 / 90 / 120-per-page labels | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 48 |
| TC-LBL-010 | 6-up Backtag prints | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 49 |
| TC-LBL-011 | Label printing works from both template and variant lists | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 50 |

## FG-03 — Sales Order Processing & Pricing (27 test cases)

> The gallery sales order lifecycle: pick-up-at-store, dollar-to-percentage discount conversion, order warning banners, delivery status visibility, auto-invoice on confirm, and the order-to-cash happy path.
>
> **Key modules:** mmg_sale, mmg_sale_delivery_status, mmg_automated_action, mmg_sale_warning_extend, mmg_sale_auto_create_invoice, Studio (x_discount) · **Roles:** Gallery Salesperson, Sales Rep, Sales Manager

| TC ID | Title | Prio | Type | Automation | Status | Src row |
|---|---|---|---|---|---|---:|
| TC-SAL-006 | Dollar discount converts to percentage (onchange) | P0 | FUNC | PYTHON_UNIT | CANDIDATE | 51 |
| TC-SAL-007 | Dollar discount converts on write (not just onchange) | P0 | FUNC | PYTHON_UNIT | AUTOMATED | 52 |
| TC-SAL-008 | Dollar discount on a bulk line update does not recurse | P1 | PERF | MANUAL | MANUAL_ONLY | 53 |
| TC-SAL-019 | Order with a 100%-discounted line | P2 | REGR | PYTHON_UNIT | NOT_PLANNED | 54 |
| TC-SAL-020 | Order line with qty 0 | P2 | REGR | PYTHON_UNIT | NOT_PLANNED | 55 |
| TC-SAL-001 | Pick up at Store rewrites the delivery address | P0 | FUNC | PYTHON_UNIT | CANDIDATE | 56 |
| TC-SAL-002 | Un-ticking Pick up at Store | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 57 |
| TC-SAL-022 | Duplicate a sales order | P2 | REGR | PYTHON_UNIT | NOT_PLANNED | 58 |
| TC-DAT-010 | Sale-order → invoice linkage intact | P1 | DATA | DATA_RECONCILIATION | CANDIDATE | 59 |
| TC-SAL-003 | Display Invoices on the order excludes cancelled | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 60 |
| TC-SAL-016 | Auto-invoice setting is per company | P2 | FUNC | PYTHON_UNIT | NOT_PLANNED | 61 |
| TC-SAL-013 | Auto-create invoice on confirm, single order | P0 | FUNC | PYTHON_UNIT | CANDIDATE | 62 |
| TC-SAL-014 | ⚠ Auto-create invoice on a MULTI-order confirm — suspected defect | P0 | FUNC | PYTHON_UNIT | CANDIDATE | 63 |
| TC-SAL-015 | Auto-create invoice disabled → no invoice on confirm | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 64 |
| TC-SAL-021 | Cancel a confirmed order that has an auto-created invoice | P1 | REGR | PYTHON_UNIT | CANDIDATE | 65 |
| TC-NEW-001 | Decide: keep or retire mmg_sale_delivery_status 🔻 | P1 | FUNC | MANUAL | MANUAL_ONLY | 66 |
| TC-SAL-004 | Delivery status derives from transfers | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 67 |
| TC-SAL-005 | Delivery status is groupable and filterable in the list | P2 | FUNC | PYTHON_UNIT | NOT_PLANNED | 68 |
| TC-SAL-009 | Order warning banner appears when a line has a warned product | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 69 |
| TC-SAL-010 | Warned-product pop-up lists every warned product with its message | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 70 |
| TC-SAL-012 | Banner clears when the warned line is removed | P2 | FUNC | PYTHON_UNIT | NOT_PLANNED | 71 |
| TC-SAL-011 | Warning fields settable at template level | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 72 |
| TC-STU-004 | sale.order.line.x_discount (Discount $) preserved and still drives discount | P0 | FUNC | PYTHON_UNIT | CANDIDATE | 73 |
| TC-DAT-009 | Sales order totals reconcile by year and state | P0 | DATA | DATA_RECONCILIATION | CANDIDATE | 74 |
| TC-SAL-017 | Quotation → confirm → deliver → invoice → pay, happy path | P0 | REGR | PYTHON_UNIT | AUTOMATED | 75 |
| TC-SAL-018 | Credit note from a posted invoice | P1 | REGR | PYTHON_UNIT | CANDIDATE | 76 |
| TC-SAL-023 | Sales order print (quotation PDF) | P2 | FUNC | PYTHON_UNIT | NOT_PLANNED | 77 |

## FG-04 — Bulk Data Maintenance Wizards (18 test cases)

> One-shot bulk updates on many products/partners at once: customer taxes, fiscal positions, internal product category, website extra categories, and customer type.
>
> **Key modules:** mmg_sale_assign_customer_taxes, mmg_sale_assign_fiscal_position, mmg_assign_product_category, mmg_assign_website_extra_category, mmg_sale_update_customer_type · **Roles:** Accountant, Inventory Manager, E-commerce Manager, Sales Manager

| TC ID | Title | Prio | Type | Automation | Status | Src row |
|---|---|---|---|---|---|---:|
| TC-BLK-008 | Assign Product Category replaces categ_id | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 78 |
| TC-BLK-009 | Assign Website Extra Category adds to the set and recomputes | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 79 |
| TC-BLK-001 | Assign Customer Taxes to selected templates | P0 | FUNC | PYTHON_UNIT | CANDIDATE | 80 |
| TC-BLK-002 | Assign Customer Taxes defaults to the company sale tax | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 81 |
| TC-BLK-004 | Assign Customer Taxes works from the variant list too | P2 | FUNC | PYTHON_UNIT | NOT_PLANNED | 82 |
| TC-BLK-017 | ACL: a non-privileged user cannot run the tax/fiscal wizards | P1 | SEC | HTTP_CASE | CANDIDATE | 83 |
| TC-BLK-003 | Assign Customer Taxes blocks an empty selection | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 84 |
| TC-BLK-005 | Assign Fiscal Position to selected partners | P0 | FUNC | PYTHON_UNIT | CANDIDATE | 85 |
| TC-BLK-007 | Assign Fiscal Position in a multi-company context | P2 | SEC | HTTP_CASE | NOT_PLANNED | 86 |
| TC-BLK-006 | Assign Fiscal Position blocks an empty selection | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 87 |
| TC-BLK-010 | Update Customer Type writes x_type | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 88 |
| TC-BLK-011 | Update Customer Type surfaces the field-missing guard | P2 | FUNC | PYTHON_UNIT | NOT_PLANNED | 89 |
| TC-BLK-012 | Update Customer Type requires a value | P3 | FUNC | PYTHON_UNIT | NOT_PLANNED | 90 |
| TC-BLK-013 | Each wizard's menu/Action entry appears on the right list view | P1 | UI | TOUR | CANDIDATE | 91 |
| TC-BLK-014 | Bulk wizard on 1,000 selected records | P1 | PERF | MANUAL | MANUAL_ONLY | 92 |
| TC-BLK-015 | Bulk wizard respects the current selection only | P0 | FUNC | PYTHON_UNIT | CANDIDATE | 93 |
| TC-BLK-016 | Bulk wizard with "select all" across a filtered domain | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 94 |
| TC-BLK-018 | Wizard writes are attributable | P2 | FUNC | PYTHON_UNIT | NOT_PLANNED | 95 |

## FG-05 — Tax Computation — Avalara AvaTax (20 test cases)

> Sales tax via Avalara: jurisdiction-level tax posting, total-reconciliation and unmapped-line guards, ship-to address validation, order → invoice tax lifecycle, exemptions and refunds. HIGHEST-RISK area: the MMG enhancement must be re-implemented against the reworked v19 external-tax framework.
>
> **Key modules:** account_avatax (EE), account_avatax_sale (EE), mmg_account_avatax_enhancement, mmg_multichannel_shopify (Avatax prep) · **Roles:** Accountant, Controller, Tax Accountant

| TC ID | Title | Prio | Type | Automation | Status | Src row |
|---|---|---|---|---|---|---:|
| TC-DAT-017 | Avatax configuration intact | P0 | DATA | DATA_RECONCILIATION | CANDIDATE | 96 |
| TC-TAX-002 | Tax posts per jurisdiction and account, not as one rolled-up amount | P0 | INTEG | API | PLANNED | 97 |
| TC-TAX-003 | Per-jurisdiction taxes are reused, not duplicated | P0 | FUNC | PYTHON_UNIT | PLANNED | 98 |
| TC-TAX-016 | Multi-line invoice with mixed taxable and exempt products | P1 | INTEG | API | CANDIDATE | 99 |
| TC-TAX-018 | Historical Avatax invoices remain unchanged after upgrade | P0 | DATA | DATA_RECONCILIATION | PLANNED | 100 |
| TC-TAX-004 | Posting is blocked when the Odoo tax total ≠ Avalara's summary | P0 | FUNC | PYTHON_UNIT | PLANNED | 101 |
| TC-TAX-005 | Guard error when a tax line cannot be mapped and the amount is non-zero | P0 | FUNC | PYTHON_UNIT | PLANNED | 102 |
| TC-TAX-006 | Guard error when a tax distribution has multiple accounts | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 103 |
| TC-TAX-007 | Ship-to (delivery) address completeness is validated, not the invoicing address | P0 | FUNC | PYTHON_UNIT | PLANNED | 104 |
| TC-SHP-025 | Avatax values prepared when exporting to Shopify | P1 | INTEG | API | CANDIDATE | 105 |
| TC-TAX-001 | Tax computed on an invoice with an Avatax fiscal position | P0 | INTEG | API | PLANNED | 106 |
| TC-TAX-008 | Tax preview on a quotation before sending | P0 | INTEG | API | PLANNED | 107 |
| TC-TAX-009 | Tax recomputes when the delivery address changes | P0 | FUNC | PYTHON_UNIT | PLANNED | 108 |
| TC-TAX-010 | Order-to-invoice tax carry-over | P0 | INTEG | API | PLANNED | 109 |
| TC-TAX-011 | Posting an invoice commits the transaction to Avalara | P0 | INTEG | API | PLANNED | 110 |
| TC-TAX-012 | Cancelling an invoice voids the Avalara transaction | P0 | INTEG | API | PLANNED | 111 |
| TC-TAX-013 | Exempt customer is charged no tax | P0 | INTEG | API | PLANNED | 112 |
| TC-TAX-014 | Avatax category on product category drives the tax code | P1 | INTEG | API | CANDIDATE | 113 |
| TC-TAX-015 | Credit note tax uses the AvaTax Refund Account | P1 | INTEG | API | CANDIDATE | 114 |
| TC-TAX-017 | Avalara service unavailable — graceful failure | P1 | INTEG | API | CANDIDATE | 115 |

## FG-06 — Customer & Vendor Deposits (23 test cases)

> Taking and applying deposits for artwork: record a payment as a deposit, link it to a sale/purchase order, apply it to the invoice, and keep deposit balances reconciled in the GL.
>
> **Key modules:** account_partner_deposit, sale_partner_deposit · **Roles:** Gallery Salesperson, Accountant, Controller

| TC ID | Title | Prio | Type | Automation | Status | Src row |
|---|---|---|---|---|---|---:|
| TC-DEP-018 | Payment-widget QWeb override still renders | P2 | UI | TOUR | NOT_PLANNED | 116 |
| TC-DAT-019 | Partner fiscal positions and deposit-account properties intact | P0 | DATA | DATA_RECONCILIATION | CANDIDATE | 117 |
| TC-DEP-002 | Deposit accounts configurable per company | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 118 |
| TC-DEP-003 | Deposit accounts configurable per partner (company-dependent property) | P0 | FUNC | PYTHON_UNIT | PLANNED | 119 |
| TC-DEP-015 | Deposit journals configurable per company | P2 | FUNC | PYTHON_UNIT | NOT_PLANNED | 120 |
| TC-DAT-016 | Deposit data intact | P0 | DATA | DATA_RECONCILIATION | CANDIDATE | 121 |
| TC-DEP-007 | Deposit is applied to the invoice raised from the order | P0 | FUNC | PYTHON_UNIT | PLANNED | 122 |
| TC-DEP-008 | Link a deposit to a purchase order (vendor side) | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 123 |
| TC-DEP-010 | Reset a deposit payment to draft | P0 | FUNC | PYTHON_UNIT | PLANNED | 124 |
| TC-DEP-011 | Reset a deposit's journal entry to draft | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 125 |
| TC-DEP-012 | Deposit Order wizard — fixed amount with a currency | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 126 |
| TC-DEP-017 | Deposit larger than the invoice total | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 127 |
| TC-DEP-020 | Is a Deposit? flag preserved on all historical payments | P0 | DATA | DATA_RECONCILIATION | PLANNED | 128 |
| TC-NEW-004 | Decide: account_partner_deposit vs native down payments 🔻 | P0 | FUNC | MANUAL | MANUAL_ONLY | 129 |
| TC-DEP-001 | Record a customer payment as a deposit | P0 | FUNC | PYTHON_UNIT | PLANNED | 130 |
| TC-DEP-009 | Outstanding deposits visible on the contact | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 131 |
| TC-DEP-014 | Deposit balances reconcile in the GL after upgrade | P0 | DATA | DATA_RECONCILIATION | PLANNED | 132 |
| TC-DEP-019 | Deposit on a channel order via payment mapping | P1 | INTEG | API | CANDIDATE | 133 |
| TC-DEP-004 | Take a deposit from a sales order (fixed amount) | P0 | FUNC | PYTHON_UNIT | PLANNED | 134 |
| TC-DEP-005 | Take a deposit as a percentage of the order | P0 | FUNC | PYTHON_UNIT | PLANNED | 135 |
| TC-DEP-013 | Cancel a deposit | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 136 |
| TC-DEP-016 | Multiple deposits on one order | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 137 |
| TC-DEP-006 | Deposit smart button opens the linked deposits | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 138 |

## FG-07 — Invoicing, Payments & Accounting Documents (25 test cases)

> MMG's invoice PDF layout, simplified payment status, default payment journal, payment providers (Authorize.net / PayPal), EDI, enterprise accounting reports, and post-upgrade financial data integrity (trial balance, aging, reconciliation).
>
> **Key modules:** mmg_account, mmg_change_invoice_template, mmg_change_ui, mmg_default_payment_journal, payment_*, account_edi*, account_reports · **Roles:** Accountant, Accounting Manager, Controller

| TC ID | Title | Prio | Type | Automation | Status | Src row |
|---|---|---|---|---|---|---:|
| TC-INV-001 | Customer invoice PDF renders with MMG's layout | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 139 |
| TC-INV-002 | Invoice PDF — multi-page and column alignment | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 140 |
| TC-INV-003 | Invoice PDF shows jurisdiction-level tax lines | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 141 |
| TC-NEW-003 | Consolidate mmg_account and mmg_change_invoice_template | P1 | FUNC | MANUAL | MANUAL_ONLY | 142 |
| TC-DAT-006 | Payment states preserved | P0 | DATA | DATA_RECONCILIATION | CANDIDATE | 143 |
| TC-INV-004 | Simplified payment status shows "In Payment" as "Paid" | P2 | FUNC | PYTHON_UNIT | NOT_PLANNED | 144 |
| TC-INV-005 | Payment-state mapping reviewed against v19 values | P0 | DATA | DATA_RECONCILIATION | CANDIDATE | 145 |
| TC-NEW-002 | Decide: keep or retire mmg_change_ui payment-status relabelling 🔻 | P2 | FUNC | MANUAL | MANUAL_ONLY | 146 |
| TC-INV-007 | Default payment journal setting is restricted to bank/cash journals of the company | P2 | FUNC | PYTHON_UNIT | NOT_PLANNED | 147 |
| TC-INV-009 | Default payment journal per company | P2 | FUNC | PYTHON_UNIT | NOT_PLANNED | 148 |
| TC-INV-006 | Register Payment defaults to the configured journal | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 149 |
| TC-INV-008 | Register Payment on multiple invoices at once | P1 | REGR | PYTHON_UNIT | CANDIDATE | 150 |
| TC-DAT-002 | Trial balance is identical | P0 | DATA | DATA_RECONCILIATION | CANDIDATE | 151 |
| TC-DAT-003 | Invoice totals reconcile by year and type | P0 | DATA | DATA_RECONCILIATION | CANDIDATE | 152 |
| TC-DAT-004 | Open receivables / payables aging matches | P0 | DATA | DATA_RECONCILIATION | CANDIDATE | 153 |
| TC-DAT-005 | Reconciliation state preserved | P0 | DATA | DATA_RECONCILIATION | CANDIDATE | 154 |
| TC-INV-010 | Payment providers migrate | P1 | REGR | PYTHON_UNIT | CANDIDATE | 155 |
| TC-INV-011 | Historical payment transactions preserved | P1 | DATA | DATA_RECONCILIATION | CANDIDATE | 156 |
| TC-INV-012 | EDI documents preserved and the framework still functions | P1 | REGR | PYTHON_UNIT | CANDIDATE | 157 |
| TC-INV-013 | Follow-up / dunning levels preserved | P2 | REGR | PYTHON_UNIT | NOT_PLANNED | 158 |
| TC-INV-014 | Enterprise accounting reports run | P1 | REGR | PYTHON_UNIT | CANDIDATE | 159 |
| TC-INV-015 | 1099 reporting still available | P2 | REGR | PYTHON_UNIT | NOT_PLANNED | 160 |
| TC-INV-016 | Automatic transfers still configured | P2 | REGR | PYTHON_UNIT | NOT_PLANNED | 161 |
| TC-INV-017 | Invoice digitisation / predictive bills still function | P3 | REGR | PYTHON_UNIT | NOT_PLANNED | 162 |
| TC-SMK-015 | Company, chart of accounts and fiscal settings unchanged | P0 | DATA | DATA_RECONCILIATION | CANDIDATE | 163 |

## FG-08 — E-commerce Channel Management (13 test cases)

> Setting up and operating a sales channel: credentials, API version, connection test, safe mode, channel customer mirror, scheduled requeue/refresh, and the channel dashboard.
>
> **Key modules:** omni_manage_channel, omni_base · **Roles:** Integration Admin, E-commerce Manager, CSR

| TC ID | Title | Prio | Type | Automation | Status | Src row |
|---|---|---|---|---|---|---:|
| TC-CHN-004 | Debug logging captures request/response | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 164 |
| TC-CHN-001 | Existing channel configuration intact and the channel connects | P0 | INTEG | API | CANDIDATE | 165 |
| TC-CHN-003 | Safe mode prevents writes to the live store | P0 | FUNC | PYTHON_UNIT | CANDIDATE | 166 |
| TC-CHN-005 | Channel sync state and last-sync timestamps preserved | P1 | DATA | DATA_RECONCILIATION | CANDIDATE | 167 |
| TC-CHN-006 | Unit and currency alignment refreshes from the platform | P1 | INTEG | API | CANDIDATE | 168 |
| TC-DAT-015 | Channel configuration and credentials intact | P0 | DATA | DATA_RECONCILIATION | CANDIDATE | 169 |
| TC-CHN-002 | Create a new channel through the onboarding flow | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 170 |
| TC-CHN-007 | Channel customer mirror matches Odoo partners | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 171 |
| TC-CHN-008 | Shipping-address matching on partners | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 172 |
| TC-CHN-009 | Failed jobs with transient DB errors are requeued on schedule | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 173 |
| TC-CHN-010 | Scheduled inventory-quantity refresh runs | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 174 |
| TC-CHN-011 | Channel dashboard kanban with activity graph renders | P2 | UI | TOUR | NOT_PLANNED | 175 |
| TC-CHN-012 | Per-channel dynamic order menus still created | P2 | FUNC | PYTHON_UNIT | NOT_PLANNED | 176 |

## FG-09 — Product Listings & Channel Catalogue (PIM) (24 test cases)

> Managing what each channel sells: listing records, product import/export with field control, alternate SKUs & identifiers, inventory presentation rules, channel images, and variant-price security.
>
> **Key modules:** multichannel_product, multichannel_manage_price · **Roles:** E-commerce Manager, Product Manager, Inventory Manager

| TC ID | Title | Prio | Type | Automation | Status | Src row |
|---|---|---|---|---|---|---:|
| TC-PIM-020 | Variant price editing restricted to the pricing group | P1 | SEC | HTTP_CASE | CANDIDATE | 177 |
| TC-DAT-014 | Shopify listing data intact | P0 | DATA | DATA_RECONCILIATION | CANDIDATE | 178 |
| TC-PIM-001 | Existing listings resolve to products and channels | P0 | DATA | DATA_RECONCILIATION | CANDIDATE | 179 |
| TC-PIM-008 | Change a listing's channel | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 180 |
| TC-PIM-016 | Channel images stored, ordered and served | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 181 |
| TC-PIM-022 | Product settings page renders | P2 | UI | TOUR | NOT_PLANNED | 182 |
| TC-PIM-023 | pre_init_hook behaviour verified on a clean install | P2 | FUNC | PYTHON_UNIT | NOT_PLANNED | 183 |
| TC-PIM-005 | Import products from a store and map to existing Odoo products | P0 | INTEG | API | CANDIDATE | 184 |
| TC-PIM-006 | Import with auto-create for unmatched products | P1 | INTEG | API | CANDIDATE | 185 |
| TC-PIM-009 | Merge channel information into the Odoo product | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 186 |
| TC-PIM-010 | Import other data (brands, categories, vendors) | P2 | INTEG | API | NOT_PLANNED | 187 |
| TC-PIM-002 | Export selected products to a channel | P0 | INTEG | API | CANDIDATE | 188 |
| TC-PIM-003 | Exported-field control is honoured | P0 | INTEG | API | CANDIDATE | 189 |
| TC-PIM-004 | Preview the payload before exporting | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 190 |
| TC-PIM-007 | Scheduled product export runs | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 191 |
| TC-PIM-019 | Bulk export of channel categories | P2 | FUNC | PYTHON_UNIT | NOT_PLANNED | 192 |
| TC-PIM-021 | Pricelist assignment per channel respected on export | P1 | INTEG | API | CANDIDATE | 193 |
| TC-PIM-011 | Alternate SKUs and product identifiers maintained | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 194 |
| TC-PIM-012 | Inventory rules shape published quantity | P0 | FUNC | PYTHON_UNIT | CANDIDATE | 195 |
| TC-PIM-013 | Free quantity visible on a listing and drills through to stock | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 196 |
| TC-PIM-015 | Manually sync inventory from a listing | P1 | INTEG | API | CANDIDATE | 197 |
| TC-PIM-014 | "Open on Store" and "Generate URL" | P2 | FUNC | PYTHON_UNIT | NOT_PLANNED | 198 |
| TC-PIM-017 | Listing mapping views render | P1 | UI | TOUR | CANDIDATE | 199 |
| TC-PIM-018 | Import/export logs reachable per operation | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 200 |

## FG-10 — Shopify Storefront Integration (33 test cases)

> The live storefront (17,868 listings): OAuth connection, catalogue & metafield export, automatic publish/unpublish on stock, order-driven inventory sync, collections & tags, fulfillment posting, returns, monkey-patch verification and API-version support.
>
> **Key modules:** multichannel_shopify, mmg_multichannel_shopify · **Roles:** E-commerce Manager, Integration Admin, Inventory Manager, Gallery Manager

| TC ID | Title | Prio | Type | Automation | Status | Src row |
|---|---|---|---|---|---|---:|
| TC-SHP-004 | Export art attributes to Shopify as metafields | P0 | INTEG | API | PLANNED | 201 |
| TC-SHP-005 | Metafield comparison avoids redundant writes | P1 | INTEG | API | CANDIDATE | 202 |
| TC-SHP-006 | Metafield deletion when an attribute is cleared | P1 | INTEG | API | CANDIDATE | 203 |
| TC-SHP-019 | Product image upload → accept → thumbnail recompute | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 204 |
| TC-SHP-020 | Image download URL on channel images resolves | P2 | FUNC | PYTHON_UNIT | NOT_PLANNED | 205 |
| TC-SHP-024 | E-blast date carries between template and listing | P2 | FUNC | PYTHON_UNIT | NOT_PLANNED | 206 |
| TC-SHP-014 | Apply Collections and Tags in bulk (template level) | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 207 |
| TC-SHP-015 | Apply Collections and Tags in bulk (channel-listing level) | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 208 |
| TC-SHP-007 | Listing auto-unpublishes when stock reaches zero | P0 | INTEG | API | PLANNED | 209 |
| TC-SHP-008 | Listing republishes when stock returns | P0 | INTEG | API | PLANNED | 210 |
| TC-SHP-009 | Creating a sales order line triggers a Shopify stock update | P0 | INTEG | API | PLANNED | 211 |
| TC-SHP-010 | Editing an order line quantity triggers a stock update | P0 | INTEG | API | PLANNED | 212 |
| TC-SHP-011 | Deleting an order line triggers a stock update | P0 | INTEG | API | PLANNED | 213 |
| TC-SHP-012 | Automatic inventory sync toggle per channel | P0 | FUNC | PYTHON_UNIT | PLANNED | 214 |
| TC-SHP-018 | The Shopify override of the export scheduler wins | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 215 |
| TC-SHP-017 | Exclude From Cart flag exports and bulk actions work | P1 | INTEG | API | CANDIDATE | 216 |
| TC-SHP-021 | SKU / default-code uniqueness enforced | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 217 |
| TC-SHP-022 | Default Store pre-selected in the export wizard | P2 | FUNC | PYTHON_UNIT | NOT_PLANNED | 218 |
| TC-SHP-023 | Stores field searchable on the product template | P2 | FUNC | PYTHON_UNIT | NOT_PLANNED | 219 |
| TC-SHP-013 | Per-listing success/failure chatter after an inventory sync | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 220 |
| TC-SHP-001 | Connect a Shopify store via OAuth | P0 | INTEG | API | PLANNED | 221 |
| TC-SHP-002 | Disconnect a store | P2 | INTEG | API | NOT_PLANNED | 222 |
| TC-SHP-033 | Shopify API version still supported | P0 | INTEG | API | PLANNED | 223 |
| TC-SHP-003 | Import Shopify products, types, tags, collections and vendors | P1 | INTEG | API | CANDIDATE | 224 |
| TC-SHP-016 | Smart-collection rules parse and generate tags | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 225 |
| TC-SHP-026 | Import Shopify orders with fulfillment and payment status | P0 | INTEG | API | PLANNED | 226 |
| TC-SHP-027 | Map Shopify locations to Odoo warehouses | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 227 |
| TC-SHP-028 | Process a Shopify return through the return wizard | P1 | INTEG | API | CANDIDATE | 228 |
| TC-SHP-029 | Post a fulfillment to Shopify from a picking | P0 | INTEG | API | PLANNED | 229 |
| TC-SHP-030 | Post a fulfillment from a service picking | P1 | INTEG | API | CANDIDATE | 230 |
| TC-SHP-031 | Relation-field JS widget renders in collection rules | P1 | UI | TOUR | CANDIDATE | 231 |
| TC-SHP-032 | ⚠ Verify each monkey patch actually took effect | P0 | FUNC | PYTHON_UNIT | PLANNED | 232 |
| TC-SHP-034 | Full Shopify order-to-cash regression | P0 | INTEG | API | PLANNED | 233 |

## FG-11 — Omnichannel Order Processing (23 test cases)

> Importing web orders and automating them: taxes/shipping/fees as recognisable lines, process rules (confirm/invoice/pay), payment-gateway mapping, cancellations with credit notes, replacements, and customer groups.
>
> **Key modules:** multichannel_order · **Roles:** Order Processor, Operations Manager, CSR, Accountant

| TC ID | Title | Prio | Type | Automation | Status | Src row |
|---|---|---|---|---|---|---:|
| TC-ORD-001 | Import orders with taxes, shipping, discounts and fees as recognisable lines | P0 | INTEG | API | PLANNED | 234 |
| TC-ORD-008 | Manual order import by date range | P1 | INTEG | API | CANDIDATE | 235 |
| TC-ORD-009 | Manual order import by specific ID list | P1 | INTEG | API | CANDIDATE | 236 |
| TC-ORD-010 | Manual order import by status | P2 | INTEG | API | NOT_PLANNED | 237 |
| TC-ORD-014 | Guest and default customer handling | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 238 |
| TC-ORD-017 | Store order and payment status visible on the Odoo order | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 239 |
| TC-ORD-020 | Scheduled new-order check runs | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 240 |
| TC-ORD-022 | Import an order for a missing product | P1 | INTEG | API | CANDIDATE | 241 |
| TC-DAT-018 | Order process rules intact | P0 | DATA | DATA_RECONCILIATION | CANDIDATE | 242 |
| TC-ORD-002 | Process rules confirm / invoice / pay by status | P0 | FUNC | PYTHON_UNIT | PLANNED | 243 |
| TC-ORD-003 | Rule sequence — first match wins | P0 | FUNC | PYTHON_UNIT | PLANNED | 244 |
| TC-ORD-004 | Invoice trigger option honoured | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 245 |
| TC-ORD-005 | Payment gateway maps to journal, method and deposit account | P0 | INTEG | API | PLANNED | 246 |
| TC-ORD-006 | Import a payment settlement report for a date range | P1 | INTEG | API | CANDIDATE | 247 |
| TC-ORD-007 | Gateway transactions recorded against the order | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 248 |
| TC-ORD-018 | Order shipments and shipping status | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 249 |
| TC-ORD-011 | Cancel an online order with a credit note and customer email | P0 | INTEG | API | PLANNED | 250 |
| TC-ORD-012 | Cancel an order without a credit note | P1 | INTEG | API | CANDIDATE | 251 |
| TC-ORD-013 | Replacement order linked to the original | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 252 |
| TC-ORD-021 | Updated shipping address on an imported order | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 253 |
| TC-ORD-019 | Channel customer groups import and bulk export | P2 | INTEG | API | NOT_PLANNED | 254 |
| TC-ORD-015 | Per-channel order prefix, sales team and salesperson applied | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 255 |
| TC-ORD-016 | Minimum order date respected | P2 | FUNC | PYTHON_UNIT | NOT_PLANNED | 256 |

## FG-12 — Fulfillment & Inventory Sync (18 test cases)

> Keeping channel stock and shipments in sync: warehouse selection, sync percentage / min / max caps, exclusions, delta sync, FTP file delivery, shipment export with tracking, shipment import, and service fulfillment.
>
> **Key modules:** multichannel_fulfillment · **Roles:** Inventory Manager, Warehouse Operator, Operations Manager

| TC ID | Title | Prio | Type | Automation | Status | Src row |
|---|---|---|---|---|---|---:|
| TC-FUL-001 | Warehouse selection per channel | P0 | FUNC | PYTHON_UNIT | PLANNED | 257 |
| TC-FUL-002 | Sync percentage applied | P0 | FUNC | PYTHON_UNIT | PLANNED | 258 |
| TC-FUL-003 | Minimum and maximum quantity caps applied | P0 | FUNC | PYTHON_UNIT | PLANNED | 259 |
| TC-FUL-004 | Min/max validation rejects an invalid range | P2 | FUNC | PYTHON_UNIT | NOT_PLANNED | 260 |
| TC-FUL-005 | Exclude a product from inventory sync | P0 | FUNC | PYTHON_UNIT | PLANNED | 261 |
| TC-FUL-006 | Exclude a variant from inventory sync | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 262 |
| TC-FUL-007 | Exclude a whole product category from inventory sync | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 263 |
| TC-FUL-008 | Incremental (delta) inventory sync uses stock moves since last sync | P0 | FUNC | PYTHON_UNIT | PLANNED | 264 |
| TC-FUL-009 | Bulk inventory sync gated by the manual-bulk flag | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 265 |
| TC-FUL-010 | In-progress marker prevents duplicate bulk syncs | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 266 |
| TC-FUL-011 | Scheduled bulk inventory sync runs | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 267 |
| TC-FUL-012 | FTP/FTPS inventory file delivery | P1 | INTEG | API | CANDIDATE | 268 |
| TC-FUL-013 | Shipment export posts carrier, tracking, cost and date to the channel | P0 | INTEG | API | PLANNED | 269 |
| TC-FUL-014 | Change detection prevents re-sending unchanged shipments | P1 | INTEG | API | CANDIDATE | 270 |
| TC-FUL-015 | Auto-export shipment toggle honoured | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 271 |
| TC-FUL-016 | Shipment import matches channel shipments to Odoo pickings | P1 | INTEG | API | CANDIDATE | 272 |
| TC-FUL-017 | Service fulfillment via stock.service.picking | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 273 |
| TC-FUL-018 | Service immediate-transfer wizard | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 274 |

## FG-13 — Background Job Platform (Queue Jobs) (20 test cases)

> The asynchronous engine every sync depends on: job runner, retries and postponement, identity keys & deduplication override, channel capacity, context fidelity, garbage collection and job security.
>
> **Key modules:** queue_job (OCA), queue_job_enhancement · **Roles:** System Admin, Integration Admin, Developer

| TC ID | Title | Prio | Type | Automation | Status | Src row |
|---|---|---|---|---|---|---:|
| TC-DAT-020 | Queue job history and channel configuration intact | P2 | DATA | DATA_RECONCILIATION | NOT_PLANNED | 275 |
| TC-JOB-001 | Runner executes a job end to end | P0 | SMOKE | ORM_INTEGRATION | PLANNED | 276 |
| TC-JOB-002 | Failed job is visible and requeueable | P0 | FUNC | PYTHON_UNIT | PLANNED | 277 |
| TC-JOB-007 | Identity key prevents duplicate pending jobs | P0 | FUNC | PYTHON_UNIT | PLANNED | 278 |
| TC-SMK-010 | Queue job runner reachable and processing | P0 | SMOKE | ORM_INTEGRATION | CANDIDATE | 279 |
| TC-JOB-005 | Channel capacity limits are honoured | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 280 |
| TC-JOB-006 | Per-method retry policy applied | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 281 |
| TC-JOB-003 | Requeue a batch of failed jobs | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 282 |
| TC-JOB-004 | Force stuck jobs to done | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 283 |
| TC-JOB-013 | Garbage collector reclaims stuck jobs | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 284 |
| TC-JOB-014 | Autovacuum prunes old job records | P2 | FUNC | PYTHON_UNIT | NOT_PLANNED | 285 |
| TC-JOB-015 | Job chatter and activity assignment work | P2 | FUNC | PYTHON_UNIT | NOT_PLANNED | 286 |
| TC-JOB-016 | Job manager group restricts cancel/requeue | P1 | SEC | HTTP_CASE | CANDIDATE | 287 |
| TC-JOB-017 | Multi-company record rule isolates jobs | P2 | SEC | HTTP_CASE | NOT_PLANNED | 288 |
| TC-JOB-008 | Identity override supersedes a stale pending job | P0 | FUNC | PYTHON_UNIT | PLANNED | 289 |
| TC-JOB-009 | Superseded job explains itself | P2 | FUNC | PYTHON_UNIT | NOT_PLANNED | 290 |
| TC-JOB-010 | Postgres lock contention becomes a postponed retry, not a failure | P0 | FUNC | PYTHON_UNIT | PLANNED | 291 |
| TC-JOB-012 | runjob route state locking works | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 292 |
| TC-JOB-018 | Test-mode passthrough works for automated tests | P2 | FUNC | PYTHON_UNIT | NOT_PLANNED | 293 |
| TC-JOB-011 | Job executes with the context it was enqueued in | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 294 |

## FG-14 — Integration Monitoring & Logging (10 test cases)

> Seeing and repairing integration traffic: one log per operation, raw request/response diagnostics, re-import / re-export recovery, resolved marking, and the purge cron that keeps 6.8M rows under control.
>
> **Key modules:** omni_log · **Roles:** Integration Admin, System Admin

| TC ID | Title | Prio | Type | Automation | Status | Src row |
|---|---|---|---|---|---|---:|
| TC-LOG-001 | One log entry per operation with status and affected record | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 295 |
| TC-LOG-007 | queue.job links to its log entry | P2 | FUNC | PYTHON_UNIT | NOT_PLANNED | 296 |
| TC-LOG-009 | Log views and menu render with a large table | P1 | PERF | MANUAL | MANUAL_ONLY | 297 |
| TC-LOG-006 | Raw request/response inspectable for a failed API call | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 298 |
| TC-LOG-002 | Re-import from a failed log entry | P0 | FUNC | PYTHON_UNIT | CANDIDATE | 299 |
| TC-LOG-003 | Re-export from a failed log entry | P0 | FUNC | PYTHON_UNIT | CANDIDATE | 300 |
| TC-LOG-004 | Batch re-run of failed entries | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 301 |
| TC-LOG-005 | Mark resolved / unresolved | P1 | FUNC | PYTHON_UNIT | CANDIDATE | 302 |
| TC-DAT-021 | ⚠ Purge omni_log / api.process.log before the upgrade, then verify retention works | P0 | DATA | DATA_RECONCILIATION | CANDIDATE | 303 |
| TC-LOG-008 | clear_successful_log cron actually purges | P0 | FUNC | PYTHON_UNIT | CANDIDATE | 304 |

---

*Src row = row in the workbook sheet “Automation Export”; each test case also records its “Test Execution” sheet row in the registry JSON.*
