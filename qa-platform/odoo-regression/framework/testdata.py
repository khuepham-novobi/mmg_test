"""Deterministic, repeatable test data.

Strategy: find-or-create controlled records identified by fixed names/codes.
Records carry the QA-AUTO marker so they are identifiable and cleanable.
Re-running tests reuses the same master data; transactional records
(quotations) are created fresh each run and tagged with the run id in
`origin` for traceability.
"""
from __future__ import annotations

CUSTOMER_NAME = "QA AUTO CUSTOMER"
PRODUCT_NAME = "QA AUTO PRODUCT (do not sell)"
PRODUCT_CODE = "QA-AUTO-PROD-001"
PRODUCT_PRICE = 150.0


def ensure_master_data(ctx) -> tuple[int, int]:
    """Returns (customer_id, product_id), creating them only if absent."""
    customer_id = ctx.adapter.ensure_customer(CUSTOMER_NAME)
    product_id = ctx.adapter.ensure_product(
        PRODUCT_NAME, PRODUCT_CODE, PRODUCT_PRICE)
    ctx.log(f"Master data ready: customer #{customer_id}, product #{product_id}")
    return customer_id, product_id
