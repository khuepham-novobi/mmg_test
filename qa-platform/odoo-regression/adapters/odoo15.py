"""Odoo 15 adapter — differences from the shared base only."""
from __future__ import annotations

import re

from .base import OdooAdapter

_ID_RE = re.compile(r"[#&]id=(\d+)")


class Odoo15Adapter(OdooAdapter):
    version = "15"

    # v15: storable products use type='product'
    def storable_product_values(self) -> dict:
        return {"type": "product"}

    # v15 cancels a draft/unconfirmed order directly with action_cancel.
    # (Orders with invoices may raise the cancel wizard — the MVP cancel test
    # runs on a draft quotation, where no wizard exists on v15.)

    def sales_list_url(self) -> str:
        # Resolve the Sales root menu by XML id — stable across databases,
        # works on Community and Enterprise (no hard-coded menu numbers).
        menu_id = self.rpc.ref("sale.sale_menu_root")
        action_id = self.rpc.ref("sale.action_quotations_with_onboarding") \
            or self.rpc.ref("sale.action_orders")
        base = f"{self.env.base_url}/web#menu_id={menu_id}"
        if action_id:
            base += f"&action={action_id}"
        return base + "&model=sale.order&view_type=list"

    def order_id_from_url(self, url: str) -> int | None:
        m = _ID_RE.search(url)
        return int(m.group(1)) if m else None

    @property
    def ui(self) -> dict:
        return {
            "login_user": ["input#login", "input[name='login']"],
            "login_password": ["input#password", "input[name='password']"],
            "login_submit": ["button[type='submit']"],
            "login_error": [".alert-danger", "p.alert"],
            # any of these proves the web client booted:
            "webclient_ready": [".o_home_menu", ".o_main_navbar", "nav.o_main_navbar"],
            "list_view_ready": [".o_list_view", ".o_list_table", ".o_content"],
            "list_new": ["button.o_list_button_add", ".o_list_button_add"],
            "form_view": [".o_form_view"],
            "partner_input": [
                ".o_field_widget[name='partner_id'] input",
                "div[name='partner_id'] input",
            ],
            "m2o_dropdown_item": [
                ".ui-autocomplete .ui-menu-item a",
                "ul.ui-autocomplete li a",
            ],
            "add_line": [
                ".o_field_x2many_list_row_add a:first-child",
                "a:has-text('Add a product')",
            ],
            "line_product_input": [
                ".o_selected_row .o_field_widget[name='product_template_id'] input",
                ".o_selected_row .o_field_widget[name='product_id'] input",
                "tr.o_selected_row td[name='product_template_id'] input",
                "tr.o_selected_row td[name='product_id'] input",
            ],
            "line_qty_input": [
                ".o_selected_row .o_field_widget[name='product_uom_qty'] input",
                "tr.o_selected_row td[name='product_uom_qty'] input",
            ],
            "form_save": ["button.o_form_button_save", ".o_form_button_save"],
            "form_saved_proof": [".o_form_saved", ".o_form_readonly",
                                 "button.o_form_button_create"],
            "app_menu_sales": [
                "a.o_app[data-menu-xmlid='sale.sale_menu_root']",
                ".o_navbar_apps_menu",
            ],
        }
