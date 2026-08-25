"""Odoo 19 adapter — differences from the shared base only."""
from __future__ import annotations

import re

from .base import OdooAdapter

# v17+ routes records as /odoo/<path>/<id>; keep the legacy #id= form too.
_ID_RES = [re.compile(r"/odoo/[^?#]*?/(\d+)(?:[?#]|$)"),
           re.compile(r"[#&]id=(\d+)")]


class Odoo19Adapter(OdooAdapter):
    version = "19"

    # v17+ split "storable" out of type: consu + is_storable=True
    def storable_product_values(self) -> dict:
        return {"type": "consu", "is_storable": True}

    def cancel_order(self, order_id: int) -> None:
        # v19 may return a confirmation wizard action; the context key skips
        # it for the automated path (same business outcome, no dialog).
        self.rpc.call("sale.order", "action_cancel", [order_id],
                      context={"disable_cancel_warning": True})

    def sales_list_url(self) -> str:
        # v17+ has stable, human-readable action routes.
        return f"{self.env.base_url}/odoo/sales"

    def order_id_from_url(self, url: str) -> int | None:
        for rx in _ID_RES:
            m = rx.search(url)
            if m:
                return int(m.group(1))
        return None

    @property
    def ui(self) -> dict:
        return {
            "login_user": ["input#login", "input[name='login']"],
            "login_password": ["input#password", "input[name='password']"],
            "login_submit": ["button[type='submit']"],
            "login_error": [".alert-danger", "p.alert"],
            "webclient_ready": [".o_main_navbar", ".o_home_menu", "header.o_navbar"],
            "list_view_ready": [".o_list_view", ".o_list_renderer", ".o_content"],
            "list_new": ["button.o_list_button_add", ".o_list_button_add",
                         ".o_control_panel_main_buttons button:has-text('New')"],
            "form_view": [".o_form_view"],
            "partner_input": [
                ".o_field_widget[name='partner_id'] input",
                "div[name='partner_id'] input",
            ],
            "m2o_dropdown_item": [
                ".o-autocomplete--dropdown-menu .o-autocomplete--dropdown-item a",
                ".o-autocomplete--dropdown-menu li a",
                ".ui-autocomplete .ui-menu-item a",
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
            "form_save": ["button.o_form_button_save", ".o_form_button_save",
                          ".o_form_status_indicator button[title*='Save']"],
            "form_saved_proof": [".o_form_saved", ".o_breadcrumb .o_last_breadcrumb_item",
                                 "button.o_form_button_create"],
            "app_menu_sales": [
                "a.o_app[data-menu-xmlid='sale.sale_menu_root']",
                ".o_navbar_apps_menu",
            ],
        }
