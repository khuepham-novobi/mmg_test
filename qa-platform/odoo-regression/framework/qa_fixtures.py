"""Shared fixtures/helpers for the FG suites.

Everything the suites create is namespaced:
  * record names start with the feature marker, e.g. "FG01 ..."
  * QA barcodes live in the 9001xxxxxx range
  * the dedicated plain internal user is QA_USER_LOGIN

sweep() removes leftovers from previous runs *that match the markers only*,
making every test idempotent and repeatable. Pre-existing business records
are never touched.
"""
from __future__ import annotations

from adapters.base import OdooRPC, OdooRPCError

QA_USER_LOGIN = "qa.auto.internal"
QA_USER_NAME = "QA AUTO Internal User"
# test-only credential for the disposable QA clone databases
QA_USER_PASSWORD = "QaAuto-2026!"


def sweep_products(rpc: OdooRPC, name_prefix: str):
    """Delete (or archive when referenced) templates/variants created by a
    previous run of a suite, identified by the name prefix."""
    for model in ("product.product", "product.template"):
        ids = rpc.search(model, [("name", "like", f"{name_prefix}%"),
                                 ("active", "in", [True, False])])
        if not ids:
            continue
        try:
            rpc.call(model, "unlink", ids)
        except OdooRPCError:
            # referenced somewhere (stock moves, orders): archive instead
            try:
                rpc.write(model, ids, {"active": False})
            except OdooRPCError:
                pass


def sweep_model(rpc: OdooRPC, model: str, domain: list):
    ids = rpc.search(model, domain)
    if ids:
        try:
            rpc.call(model, "unlink", ids)
        except OdooRPCError:
            pass


def ensure_qa_user(rpc: OdooRPC) -> int:
    """Create (or reuse) a plain internal user (base.group_user only)."""
    found = rpc.search("res.users", [("login", "=", QA_USER_LOGIN),
                                     ("active", "in", [True, False])], limit=1)
    if found:
        rpc.write("res.users", found, {"active": True,
                                       "password": QA_USER_PASSWORD})
        return found[0]
    group_user = rpc.ref("base.group_user")
    return rpc.create("res.users", {
        "name": QA_USER_NAME,
        "login": QA_USER_LOGIN,
        "password": QA_USER_PASSWORD,
        "groups_id": [(6, 0, [group_user])],
    })


def rpc_as_qa_user(env) -> OdooRPC:
    """A second RPC session authenticated as the plain internal user."""
    import copy
    qa_env = copy.copy(env)
    qa_env.username = QA_USER_LOGIN
    qa_env.password = QA_USER_PASSWORD
    return OdooRPC(qa_env)
