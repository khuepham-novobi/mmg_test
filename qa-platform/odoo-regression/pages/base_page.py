"""Base page object: candidate-selector resolution.

Selector maps live in the version adapters (adapters/odoo15.py, odoo19.py).
Each logical element has a LIST of candidate selectors; the first one that
appears wins. Page objects therefore contain no version conditionals and
tests contain no raw selectors at all.
"""
from __future__ import annotations


class SelectorNotFound(RuntimeError):
    pass


class BasePage:
    def __init__(self, page, adapter):
        self.page = page
        self.adapter = adapter
        self.ui = adapter.ui

    def locator(self, key: str, timeout: int | None = None):
        """Return the first visible locator among the candidates for `key`."""
        candidates = self.ui[key]
        per_try = max(1500, (timeout or 12000) // max(len(candidates), 1))
        last_err = None
        for _ in range(2):  # two passes over the candidate list
            for sel in candidates:
                loc = self.page.locator(sel).first
                try:
                    loc.wait_for(state="visible", timeout=per_try)
                    return loc
                except Exception as err:
                    last_err = err
        raise SelectorNotFound(
            f"None of the candidate selectors for '{key}' became visible: "
            f"{candidates}") from last_err

    def exists(self, key: str, timeout: int = 2500) -> bool:
        try:
            self.locator(key, timeout=timeout)
            return True
        except SelectorNotFound:
            return False

    def goto(self, url: str):
        self.page.goto(url, wait_until="domcontentloaded")
