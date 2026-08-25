"""Version-agnostic Odoo access.

Business operations are expressed once here; anything that differs between
Odoo 15 and Odoo 19 is overridden in adapters/odoo15.py / adapters/odoo19.py.

Transport is the **web client's own endpoint**, ``/web/dataset/call_kw`` over
an authenticated session — i.e. the platform drives Odoo exactly the way a
user's browser does. ``/jsonrpc`` is kept only for the version ping and
session-less authentication.

Why not the external ``/jsonrpc`` API for model calls: on Odoo 15 the two
paths do not have identical flush semantics. Verified empirically against
mmg_stock's product.level.data.sync.mixin, which mirrors template<->variant
fields from a ``cr.precommit`` callback:

    create product.template with x_artist via /jsonrpc            -> variant NOT synced
    same create via /web/dataset/call_kw                          -> variant synced
    write x_artist on an existing template (either path)          -> variant synced

The workbook's test cases describe in-process ORM semantics (they call
``env.cr.precommit.run()`` explicitly in a TransactionCase), which the web
path reproduces and the external API does not. Driving the UI path therefore
makes a test's verdict reflect what a real user/web session gets.

(The asymmetry is itself a finding worth reporting: records created through
the external API — as a connector would — silently skip the variant mirror.)

XML-RPC is not used at all: it cannot marshal the ``None`` many ORM methods
legitimately return (fields_view_get, action_archive, server actions).
"""
from __future__ import annotations

import itertools
import json
import time
import urllib.request
from typing import Any

from backend.config import EnvironmentConfig

QA_MARKER = "QA-AUTO"  # every record the platform creates carries this marker


class OdooRPCError(RuntimeError):
    pass


class OdooRPC:
    """Thin, dependency-free JSON-RPC client for Odoo 8..19."""

    _ids = itertools.count(1)

    def __init__(self, env: EnvironmentConfig):
        self.env = env
        self._endpoint = f"{env.base_url}/jsonrpc"
        self._uid: int | None = None
        self._opener = None          # authenticated web session (lazy)

    def _rpc(self, service: str, method: str, args: list) -> Any:
        payload = json.dumps({
            "jsonrpc": "2.0", "method": "call", "id": next(self._ids),
            "params": {"service": service, "method": method, "args": args},
        }).encode()
        req = urllib.request.Request(
            self._endpoint, data=payload,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=600) as res:
            reply = json.load(res)
        if reply.get("error"):
            err = reply["error"]
            data = err.get("data") or {}
            message = (data.get("message") or err.get("message")
                       or "unknown RPC error")
            raise OdooRPCError(str(message).strip().splitlines()[-1])
        return reply.get("result")

    # -- session ---------------------------------------------------------
    def server_version(self) -> str:
        return str((self._rpc("common", "version", []) or {})
                   .get("server_version", "?"))

    def authenticate(self) -> int:
        uid = self._rpc("common", "authenticate",
                        [self.env.db, self.env.username,
                         self.env.password, {}])
        if not uid:
            raise OdooRPCError(
                f"Authentication failed for user '{self.env.username}' "
                f"on db '{self.env.db}' at {self.env.base_url}")
        self._uid = uid
        return uid

    @property
    def uid(self) -> int:
        if self._uid is None:
            self._session()          # authenticates and sets _uid
        return self._uid

    # -- web session -------------------------------------------------------
    def _session(self):
        """Authenticated web session (cookie jar), created on first use."""
        if self._opener is not None:
            return self._opener
        import http.cookiejar
        jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(jar))
        payload = json.dumps({"jsonrpc": "2.0", "params": {
            "db": self.env.db, "login": self.env.username,
            "password": self.env.password}}).encode()
        req = urllib.request.Request(
            f"{self.env.base_url}/web/session/authenticate", data=payload,
            headers={"Content-Type": "application/json"})
        try:
            with opener.open(req, timeout=120) as res:
                reply = json.load(res)
        except OSError as exc:
            raise OdooRPCError(f"web session authentication failed: {exc}")
        if reply.get("error"):
            data = reply["error"].get("data") or {}
            err = data.get("message") or reply["error"].get("message")
            raise OdooRPCError(f"web session authentication failed: {err}")
        result = reply.get("result") or {}
        if not result.get("uid"):
            raise OdooRPCError(
                f"web session authentication failed for user "
                f"'{self.env.username}' on db '{self.env.db}'")
        self._uid = result["uid"]
        self._opener = opener
        return opener

    # -- generic calls -----------------------------------------------------
    def call(self, model: str, method: str, *args, **kwargs) -> Any:
        """Call a model method through the web client's endpoint."""
        opener = self._session()
        payload = json.dumps({
            "jsonrpc": "2.0", "method": "call", "id": next(self._ids),
            "params": {"model": model, "method": method,
                       "args": list(args), "kwargs": kwargs or {}},
        }, default=str).encode()
        req = urllib.request.Request(
            f"{self.env.base_url}/web/dataset/call_kw", data=payload,
            headers={"Content-Type": "application/json"})
        try:
            with opener.open(req, timeout=900) as res:
                reply = json.load(res)
        except OSError as exc:
            raise OdooRPCError(f"{model}.{method} failed: {exc}") from exc
        if reply.get("error"):
            err = reply["error"]
            data = err.get("data") or {}
            message = (data.get("message") or err.get("message")
                       or "unknown RPC error")
            raise OdooRPCError(
                f"{model}.{method} failed: "
                f"{str(message).strip().splitlines()[-1]}")
        return reply.get("result")

    def search(self, model, domain, **kw):
        return self.call(model, "search", domain, **kw)

    def search_read(self, model, domain, fields, **kw):
        return self.call(model, "search_read", domain, fields=fields, **kw)

    def read(self, model, ids, fields):
        return self.call(model, "read", ids, fields=fields)

    def create(self, model, values) -> int:
        return self.call(model, "create", values)

    def write(self, model, ids, values) -> bool:
        return self.call(model, "write", ids, values)

    def unlink(self, model, ids) -> bool:
        return self.call(model, "unlink", ids)

    def read_group(self, model, domain, fields, groupby, **kw):
        return self.call(model, "read_group", domain, fields, groupby, **kw)

    def field_exists(self, model: str, field: str) -> bool:
        fields = self.call(model, "fields_get", [field], attributes=["type"])
        return field in fields

    def model_exists(self, model: str) -> bool:
        return bool(self.search("ir.model", [("model", "=", model)], limit=1))

    def ref(self, xmlid: str) -> int | None:
        """Resolve an XML id (e.g. 'sale.sale_menu_root') to a database id."""
        module, _, name = xmlid.partition(".")
        rec = self.search_read(
            "ir.model.data",
            [("module", "=", module), ("name", "=", name)],
            ["res_id"], limit=1)
        return rec[0]["res_id"] if rec else None


class OdooAdapter:
    """Business-level operations shared by both versions.

    Subclasses override ONLY what genuinely differs between v15 and v19
    (storable-product flags, cancel flow, UI selectors, navigation URLs).
    Tests and page objects never contain `if version == ...` logic.
    """

    version = "?"

    def __init__(self, env: EnvironmentConfig):
        self.env = env
        self.rpc = OdooRPC(env)

    # ---------------------------------------------------------------- data
    def storable_product_values(self) -> dict:
        raise NotImplementedError

    def ensure_customer(self, name: str) -> int:
        found = self.rpc.search("res.partner", [("name", "=", name)], limit=1)
        if found:
            return found[0]
        return self.rpc.create("res.partner", {
            "name": name,
            "ref": QA_MARKER,
            "comment": "Created by the odoo-regression platform. Safe to delete.",
        })

    def ensure_product(self, name: str, default_code: str, price: float) -> int:
        found = self.rpc.search_read(
            "product.product", [("default_code", "=", default_code)],
            ["id"], limit=1)
        if found:
            return found[0]["id"]
        values = {
            "name": name,
            "default_code": default_code,
            "list_price": price,
            "sale_ok": True,
            # keep totals deterministic for the QA product regardless of the
            # database's default tax configuration:
            "taxes_id": [(6, 0, [])],
        }
        values.update(self.storable_product_values())
        tmpl_id = self.rpc.create("product.template", values)
        variant = self.rpc.search_read(
            "product.product", [("product_tmpl_id", "=", tmpl_id)], ["id"], limit=1)
        return variant[0]["id"]

    def product_price(self, product_id: int) -> float:
        return self.rpc.read("product.product", [product_id], ["lst_price"])[0]["lst_price"]

    # ------------------------------------------------------------- orders
    def create_quotation(self, customer_id: int, lines: list[tuple[int, float]],
                         origin: str = "") -> int:
        order_lines = []
        for product_id, qty in lines:
            prod = self.rpc.read("product.product", [product_id],
                                 ["display_name", "lst_price"])[0]
            order_lines.append((0, 0, {
                "product_id": product_id,
                "name": prod["display_name"],
                "product_uom_qty": qty,
                "price_unit": prod["lst_price"],
            }))
        return self.rpc.create("sale.order", {
            "partner_id": customer_id,
            "origin": origin or QA_MARKER,
            "order_line": order_lines,
        })

    def confirm_order(self, order_id: int) -> None:
        self.rpc.call("sale.order", "action_confirm", [order_id])

    def cancel_order(self, order_id: int) -> None:
        """Default cancel; overridden where the version needs a wizard bypass."""
        self.rpc.call("sale.order", "action_cancel", [order_id])

    def order_data(self, order_id: int) -> dict:
        fields = ["name", "state", "amount_untaxed", "amount_total",
                  "partner_id", "invoice_ids"]
        has_pickings = self.rpc.field_exists("sale.order", "picking_ids")
        if has_pickings:
            fields.append("picking_ids")
        data = self.rpc.read("sale.order", [order_id], fields)[0]
        data["has_picking_field"] = has_pickings
        lines = self.rpc.search_read(
            "sale.order.line", [("order_id", "=", order_id)],
            ["product_id", "product_uom_qty", "price_unit", "price_subtotal",
             "discount"])
        data["lines"] = lines
        return data

    def latest_order_for_customer(self, customer_id: int) -> int | None:
        found = self.rpc.search(
            "sale.order", [("partner_id", "=", customer_id)],
            order="id desc", limit=1)
        return found[0] if found else None

    def wait_order_state(self, order_id: int, state: str, timeout_s: float = 15.0) -> str:
        """Poll for asynchronous state changes (queued automations etc.)."""
        deadline = time.time() + timeout_s
        last = None
        while time.time() < deadline:
            last = self.rpc.read("sale.order", [order_id], ["state"])[0]["state"]
            if last == state:
                return last
            time.sleep(1.0)
        return last

    # ------------------------------------------------------------------ UI
    @property
    def ui(self) -> dict:
        """Selector map used by the page objects. Values are candidate lists —
        the first selector that resolves wins (defensive against minor
        per-database view differences)."""
        raise NotImplementedError

    def login_url(self) -> str:
        # ?db= pins the database when the server hosts several
        return f"{self.env.base_url}/web/login?db={self.env.db}"

    def sales_list_url(self) -> str:
        raise NotImplementedError

    def order_id_from_url(self, url: str) -> int | None:
        raise NotImplementedError
