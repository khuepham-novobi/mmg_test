from __future__ import annotations

import re
import time

from .base_page import BasePage


class QuotationPage(BasePage):
    """The sale.order form, as a business object."""

    # ---------------------------------------------------------- customer
    def set_customer(self, name: str):
        field = self.locator("partner_input")
        field.click()
        field.fill(name)
        # pick the exact record from the many2one autocomplete
        self._pick_dropdown_option(name)

    def _pick_dropdown_option(self, text: str):
        deadline = time.time() + 12
        last_err = None
        while time.time() < deadline:
            for sel in self.ui["m2o_dropdown_item"]:
                items = self.page.locator(sel)
                try:
                    count = items.count()
                except Exception as err:
                    last_err = err
                    continue
                for i in range(count):
                    item = items.nth(i)
                    try:
                        label = item.inner_text(timeout=800).strip()
                    except Exception:
                        continue
                    low = label.lower()
                    # never click the inline "Create ..." / "Search more" rows
                    if text.lower() in low and not low.startswith(
                            ("create ", "search more", "start typing")):
                        item.click()
                        return
            time.sleep(0.4)
        raise TimeoutError(
            f"Autocomplete option containing '{text}' never appeared"
        ) from last_err

    # ------------------------------------------------------------- lines
    def add_product_line(self, product_name: str, quantity: float):
        self.locator("add_line").click()
        prod_input = self.locator("line_product_input")
        prod_input.click()
        prod_input.fill(product_name)
        self._pick_dropdown_option(product_name)
        if quantity != 1:
            qty_input = self.locator("line_qty_input")
            qty_input.click()
            # triple-click selects current value so fill replaces it cleanly
            qty_input.press("Control+a")
            qty_input.fill(str(quantity))

    # -------------------------------------------------------------- save
    def save(self):
        # commit any in-progress line edit first, then save the record
        self.page.keyboard.press("Escape")
        save_btn = self.locator("form_save")
        save_btn.click()
        self._wait_saved()

    def _wait_saved(self, timeout_s: float = 20.0):
        """Saved = the record URL carries a database id AND no unsaved-marker
        remains. Works on both the v15 hash router and the v19 path router."""
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            oid = self.adapter.order_id_from_url(self.page.url)
            dirty = self.page.locator(".o_form_dirty").count() > 0
            if oid and not dirty:
                return
            time.sleep(0.4)
        raise TimeoutError(
            f"Form never reached saved state (url={self.page.url})")

    # ---------------------------------------------------------- reading
    def record_id(self) -> int | None:
        return self.adapter.order_id_from_url(self.page.url)

    def reference(self) -> str:
        """The quotation name (e.g. S00042) from the breadcrumb/title."""
        for sel in (".o_breadcrumb .o_last_breadcrumb_item",
                    ".breadcrumb-item.active", ".o_form_view .o_last_breadcrumb_item"):
            loc = self.page.locator(sel).first
            if loc.count():
                txt = loc.inner_text().strip()
                m = re.search(r"[A-Z]\d{4,}", txt)
                if m:
                    return m.group(0)
                if txt:
                    return txt
        return ""
