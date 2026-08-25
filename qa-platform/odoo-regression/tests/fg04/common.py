"""Shared fixtures and helpers for the FG-04 suite
(Bulk Data Maintenance Wizards).

Live-DB determinism adaptations (documented, not assertion-weakening):
* fixtures carry the FG04 marker and the "new" values written by the wizards
  (taxes, categories, fiscal positions, the x_type marker string) are created
  fresh per run, so "exactly N records carry the new value" assertions stay
  deterministic against the production clone's live data;
* reference fixtures (taxes/categories/fiscal positions) use an
  ensure-by-name pattern: a leftover that survived a crashed run (because an
  archived product still references it) is reused, never duplicated.

Version notes mirrored from the workbook steps themselves:
* the v15 Update Customer Type button method is update() — renamed to
  action_update_customer_type() in the v19 port (DW-006). The version split
  lives in customer_type_method(), never inline in test bodies;
* the v19 Assign Product Category port adds a select/confirm gate
  (action_show_confirmation); run_assign_product_categ() drives whichever
  flow the target version exposes. The v19-only confirmation *assertions*
  stay in TEST-FG04-BLK-008 and are expected to FAIL on the v15 baseline
  (immutable expectation → classified FIXED when v19 passes).
"""
from __future__ import annotations

import copy
import uuid

from adapters.base import OdooRPC, OdooRPCError
from framework.fg_common import m2o_id, make_trace, reconcile  # noqa: F401 — re-exported
from framework.qa_fixtures import sweep_model, sweep_products

FEATURE = "FG-04 Bulk Data Maintenance Wizards"
MARK = "FG04"

trace = make_trace(FEATURE)

TAX_WIZARD = "assign.customer.taxes.wizard"
FP_WIZARD = "assign.fiscal.position.wizard"
CATEG_WIZARD = "assign.product.categ.wizard"
WEB_CATEG_WIZARD = "assign.website.extra.categ.wizard"
TYPE_WIZARD = "update.customer.type.wizard"

# dedicated manager user for the ACL positive control and the attribution
# case (reused across runs, never removed — mirrors the framework QA user)
FG04_MANAGER_LOGIN = "fg04.auto.manager"
FG04_MANAGER_NAME = "FG04 AUTO Manager User"
FG04_MANAGER_PASSWORD = "Fg04Auto-2026!"
FG04_MANAGER_GROUPS = [
    "base.group_user",
    "account.group_account_manager",   # tax/fiscal wizards + product RW
    "sales_team.group_sale_manager",   # product RW, customer segmentation
    "stock.group_stock_manager",       # product category writes
    "base.group_partner_manager",      # res.partner RW
]


# Per-execution fixture namespace. Every test starts with sweep_fg04(), which
# mints a fresh token; all fixtures created afterwards carry it in their name.
#
# Why: on a production clone, deletion frequently cannot succeed — a product
# referenced by stock moves or channel listings is archived instead of
# removed. Reused-by-name fixtures therefore accumulated across runs, and
# "exactly N records carry the new value" assertions started counting the
# previous run's leftovers (observed: expected 5, got 10) or reusing a stale
# partner whose property was already set. A unique namespace per execution
# makes every run self-contained regardless of what survived before.
_TOKEN = "init"


def fixture_token() -> str:
    return _TOKEN


def fx(name: str) -> str:
    """Namespace a fixture name for this execution: 'FG04 Old Sale Tax' →
    'FG04 Old Sale Tax [a1b2c3]'. The MARK prefix is preserved so sweeps and
    prefix searches keep working."""
    return f"{name} [{_TOKEN}]"


def sweep_fg04(rpc):
    """Open a fresh fixture namespace, then remove marker-scoped leftovers.

    Deletion is best-effort by design: `sweep_products` archives what it
    cannot unlink. Because the new namespace is unique, anything that
    survives can never collide with this execution's assertions.
    """
    global _TOKEN
    _TOKEN = uuid.uuid4().hex[:6]

    sweep_products(rpc, MARK)
    sweep_model(rpc, "res.partner", [("name", "like", f"{MARK} %"),
                                     ("user_ids", "=", False)])
    # reference fixtures from *previous* executions only — this execution
    # creates its own after the sweep, so no id in hand can be invalidated
    sweep_model(rpc, "product.category", [("name", "like", f"{MARK} %")])
    sweep_model(rpc, "account.fiscal.position",
                [("name", "like", f"{MARK} %")])
    sweep_model(rpc, "account.tax", [("name", "like", f"{MARK} %")])


def ensure_sale_tax(rpc, name, amount):
    """Sale-tax fixture for this execution (namespaced, so a leftover from an
    earlier run is never reused)."""
    name = fx(name)
    found = rpc.search("account.tax",
                       [("name", "=", name),
                        ("type_tax_use", "=", "sale")], limit=1)
    if found:
        return found[0]
    return rpc.create("account.tax", {
        "name": name, "amount": amount,
        "amount_type": "percent", "type_tax_use": "sale",
    })


def ensure_category(rpc, name):
    name = fx(name)
    found = rpc.search("product.category", [("name", "=", name)], limit=1)
    return found[0] if found else rpc.create("product.category",
                                             {"name": name})


def ensure_fiscal_position(rpc, name, company_id=None):
    name = fx(name)
    domain = [("name", "=", name)]
    if company_id:
        domain.append(("company_id", "=", company_id))
    found = rpc.search("account.fiscal.position", domain, limit=1)
    if found:
        return found[0]
    vals = {"name": name}
    if company_id:
        vals["company_id"] = company_id
    return rpc.create("account.fiscal.position", vals)


def make_templates(rpc, count, label, tax_id):
    """Batch-create `count` FG04 product templates carrying the given tax."""
    vals_list = [{"name": fx(f"{MARK} {label} {i:03d}"),
                  "taxes_id": [(6, 0, [tax_id])]}
                 for i in range(1, count + 1)]
    return rpc.create("product.template", vals_list)


def make_partners(rpc, count, label, extra=None):
    vals_list = []
    for i in range(1, count + 1):
        vals = {"name": fx(f"{MARK} {label} {i:03d}")}
        vals.update(extra or {})
        vals_list.append(vals)
    return rpc.create("res.partner", vals_list)


def customer_type_method(ctx) -> str:
    """v15 button method is update(); the v19 port renames it to
    action_update_customer_type() (DW-006) — the workbook step documents
    both names."""
    return "update" if ctx.env.version == "15" else "action_update_customer_type"


def run_assign_product_categ(ctx, rpc, wizard_id, sel_ctx):
    """Apply the Assign Product Category wizard through whichever flow the
    target version exposes: v19 goes through the select→confirm gate, v15
    applies directly (it has no gate — TEST-FG04-BLK-008 asserts the gate
    itself and is the expected v15 baseline FAIL)."""
    if rpc.field_exists(CATEG_WIZARD, "state"):
        rpc.call(CATEG_WIZARD, "action_show_confirmation", [wizard_id],
                 context=sel_ctx)
    rpc.call(CATEG_WIZARD, "action_assign_product_categ", [wizard_id],
             context=sel_ctx)


def rpc_session(env, login, password) -> OdooRPC:
    """A second RPC session authenticated as the given user."""
    user_env = copy.copy(env)
    user_env.username = login
    user_env.password = password
    return OdooRPC(user_env)


def ensure_fg04_manager(rpc) -> int:
    """Create (or reuse) the FG-04 manager-group user."""
    group_ids = [rpc.ref(xmlid) for xmlid in FG04_MANAGER_GROUPS]
    found = rpc.search("res.users",
                       [("login", "=", FG04_MANAGER_LOGIN),
                        ("active", "in", [True, False])], limit=1)
    if found:
        rpc.write("res.users", found,
                  {"active": True, "password": FG04_MANAGER_PASSWORD,
                   "groups_id": [(4, gid) for gid in group_ids]})
        return found[0]
    return rpc.call("res.users", "create", {
        "name": FG04_MANAGER_NAME,
        "login": FG04_MANAGER_LOGIN,
        "password": FG04_MANAGER_PASSWORD,
        "groups_id": [(6, 0, group_ids)],
    }, context={"no_reset_password": True})


def expect_user_error(rpc_callable, *args, **kwargs):
    """Run an RPC call that the workbook expects to raise; return
    (raised: bool, message: str)."""
    try:
        rpc_callable(*args, **kwargs)
        return False, "no error raised"
    except OdooRPCError as exc:
        return True, str(exc)
