# FG-01 → FG-14 Summary

Generated 2026-08-19 09:42. Source: persisted executions in `data/results.db` + the workbook-synced registry (303 in-scope test cases).

## Headline numbers

- **Total cases:** 303
- **Automated (covered by platform tests):** 65
- **Manual-only:** 9
- **Blocked (any environment):** 55
- **Odoo 15:** PASS 33 / FAIL 28
- **Odoo 19:** PASS 0 / FAIL 0
- **Regression candidates:** 0 (pending triage)
- **Fixed cases:** 0
- **Automation coverage:** 21.5% of all in-scope cases (65/303)
- **Execution coverage:** v15 21.8% (66/303) · v19 16.8% (51/303)

## Classification totals

| Classification | Count |
|---|---:|
| SAME_BEHAVIOR | 0 |
| REGRESSION_CANDIDATE | 0 |
| FIXED | 0 |
| SAME_FAILURE | 0 |
| BLOCKED | 55 |
| NOT_COMPARED | 248 |

## Per feature group

| FG | Feature | TCs | Automated | v15 P/F | v19 P/F | Regr. cand. | Fixed |
|---|---|---:|---:|---|---|---:|---:|
| FG-01 | Art Catalogue & Product Master Data | 36 | 35 | 21/14 | 0/0 | 0 | 0 |
| FG-02 | Certificates of Authenticity & Label Print | 13 | 12 | 0/8 | 0/0 | 0 | 0 |
| FG-03 | Sales Order Processing & Pricing | 27 | 2 | 0/3 | 0/0 | 0 | 0 |
| FG-04 | Bulk Data Maintenance Wizards | 18 | 16 | 12/3 | 0/0 | 0 | 0 |
| FG-05 | Tax Computation — Avalara AvaTax | 20 | 0 | 0/0 | 0/0 | 0 | 0 |
| FG-06 | Customer & Vendor Deposits | 23 | 0 | 0/0 | 0/0 | 0 | 0 |
| FG-07 | Invoicing, Payments & Accounting Documents | 25 | 0 | 0/0 | 0/0 | 0 | 0 |
| FG-08 | E-commerce Channel Management | 13 | 0 | 0/0 | 0/0 | 0 | 0 |
| FG-09 | Product Listings & Channel Catalogue (PIM) | 24 | 0 | 0/0 | 0/0 | 0 | 0 |
| FG-10 | Shopify Storefront Integration | 33 | 0 | 0/0 | 0/0 | 0 | 0 |
| FG-11 | Omnichannel Order Processing | 23 | 0 | 0/0 | 0/0 | 0 | 0 |
| FG-12 | Fulfillment & Inventory Sync | 18 | 0 | 0/0 | 0/0 | 0 | 0 |
| FG-13 | Background Job Platform (Queue Jobs) | 20 | 0 | 0/0 | 0/0 | 0 | 0 |
| FG-14 | Integration Monitoring & Logging | 10 | 0 | 0/0 | 0/0 | 0 | 0 |

## Reading guide

- v19 executions are BLOCKED until a local Odoo 19 environment exists — the v19 side of every comparison is pending, so regression candidates cannot exist yet by construction.
- v15 FAILs where the workbook expectation encodes the v19 target state (formalized fields, ACL decision #4, DW-fixes, the v19 discount formula) are the *documented baseline*, expected to classify as FIXED once v19 runs.
- Evidence per execution (steps, assertions, logs, screenshots, baselines) is in the web UI: test case → EVIDENCE.
