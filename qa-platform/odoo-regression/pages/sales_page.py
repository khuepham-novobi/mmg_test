from __future__ import annotations

from .base_page import BasePage


class SalesPage(BasePage):
    """Navigation into the Sales app's quotation list.

    The URL comes from the version adapter (v15: menu/action hash resolved by
    XML id over RPC; v19: the stable /odoo/sales route) — no hard-coded menu ids.
    """

    def open(self):
        self.goto(self.adapter.sales_list_url())
        self.page.wait_for_load_state("domcontentloaded")
        return self

    def is_loaded(self) -> bool:
        return self.exists("list_view_ready", timeout=25000)

    def click_new(self):
        self.locator("list_new").click()
        self.locator("form_view", timeout=15000)
