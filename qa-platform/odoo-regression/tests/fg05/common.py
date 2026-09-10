"""FG-05 — Tax Computation · Avalara AvaTax. Shared fixtures and gates.

Source of truth for this suite is the CLIENT MANUAL TESTING GUIDELINE
``MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0.xlsx``, sheet
``Testing Guideline``, rows 1–14 (TC-DAT-017 and TC-TAX-001 … TC-TAX-017).
Every assertion in this suite implements that workbook's *Expected Result*
column verbatim — never weakened, never inverted.

Odoo 19 only
------------
The workbook describes Odoo 19 screens, and the v19 AvaTax surface is a
different module from v15's: v19 uses Odoo Enterprise ``account_avatax`` on
top of ``account.external.tax.mixin`` (``button_external_tax_calculation``,
``avatax_unique_code``, ``is_avatax``), while v15 used the OCA/Emipro
``account_avatax`` fork (``button_update_avatax``, ``_map_avatax``). Running
these assertions against a v15 target would report defects that are only a
version difference, so every test in the suite calls :func:`require_v19`
first and reports BLOCKED on anything else.

Deviation from AUTOMATION_CONVENTIONS rule 4 — recorded, not hidden
------------------------------------------------------------------
``docs/AUTOMATION_CONVENTIONS.md`` rule 4 says a test whose essence needs an
external system must call ``ctx.blocked(...)``. Twelve of these fourteen
cases ARE the Avalara call — under a literal reading they would all be
permanent BLOCKED stubs and FG-05 would never get a verdict. The suite
therefore runs them for real, against the Avalara **SANDBOX only**, behind
:func:`require_sandbox`, which BLOCKS (never fails, never proceeds) unless
ALL of the following hold:

  1. the target environment is Odoo 19;
  2. ``Use AvaTax`` is enabled on the company;
  3. ``avalara_environment`` reads ``sandbox`` — a company pointed at
     ``production`` is BLOCKED, because computing tax there files real tax
     documents (Read Me, safety rule 1);
  4. both ``avalara_api_id`` and ``avalara_api_key`` are populated.

Credential VALUES never enter evidence: the gate records them as
``set`` / ``not set`` only.

Safety properties this suite keeps
----------------------------------
* Every record it creates is namespaced with the ``FG05`` marker and swept
  before and after each test; pre-existing business records — fiscal
  positions, the chart of accounts, real customers — are read-only.
* It never writes an Avalara credential, never switches the environment to
  production, and never enables a cron or a connector instance.
* TC-TAX-014 and TC-TAX-017 mutate a setting by design (a product category's
  AvaTax code, the API key). Both restore it in a ``finally:`` block, and
  both record the restore as an assertion so a failed restore is visible.
* Every fixture product resolves an Avalara Tax Code, because a line that
  resolves none is refused before the request leaves Odoo — see
  :func:`fg05_product_category`. The category that supplies it is created
  from the codes already on the target database, is ``FG05``-marked, and is
  swept with the rest of the fixtures.

Gates that name a defect instead of relaying a cryptic failure
--------------------------------------------------------------
A case whose document never comes back from Avalara cannot evaluate its
expectation, and reporting Avalara's own wording for that is close to useless
to the person reading the report. Two probes here turn such a run into a
statement about the target system:

* :func:`require_warehouse_shipfrom` — QUOTATIONS only. Odoo 19 Enterprise
  builds a *line-level* ``shipFrom`` from a sale order line's warehouse
  address, and builds an EMPTY one instead of skipping it when the warehouse
  has no address, so Avalara refuses the whole ``CreateTransaction`` with
  "Unknown country name or code (FALSE)". The gate reports BLOCKED naming
  ``stock.warehouse``, the warehouse, exactly which of country / state / zip is
  missing, the Inventory remedy, and the two Odoo defects
  (:data:`ODOO_SHIPFROM_DEFECT`). Invoice cases never call it, and are
  unaffected.
* :func:`tax_account_verdict` — reads whether an account is a plausible place
  to POST a tax amount, from Odoo's own repartition-line domain and its
  tax-closing rule rather than from an opinion about charts of accounts. Its
  callers LOG the verdict; none of them blocks or asserts on it, so a workbook
  expectation about tax accounts still decides its own case.

Neither probe changes an assertion, and neither can turn a real defect green:
the first refuses to give a verdict at all, and the second only writes evidence.
"""
from __future__ import annotations

import json
import re
import urllib.request

from adapters.base import OdooRPCError
from framework.fg_common import http_session

# --------------------------------------------------------------- identity
FEATURE = "FG-05 Tax Computation — Avalara AvaTax"
WORKFLOW = "FG-05"
WORKFLOW_NAME = "AvaTax Tax Computation"
MODULE = "mmg_account_avatax_enhancement"
MARK = "FG05"

WORKBOOK = "MMG_v19_Client_Manual_Testing_Guideline_FG05-FG14_v1.0.xlsx"
SHEET = "Testing Guideline"


def trace(tc_ids, user_story: str = "") -> dict:
    """Traceability back to the client manual testing guideline."""
    return {
        "tc_ids": tc_ids if isinstance(tc_ids, list) else [tc_ids],
        "feature": FEATURE,
        "user_story": user_story,
        "source": f"{WORKBOOK} / {SHEET}",
    }


# ------------------------------------------------------------ block reasons
V19_ONLY = (
    "FG-05 targets Odoo 19 only: the client manual testing guideline describes "
    "the v19 AvaTax surface (Odoo Enterprise account_avatax — "
    "button_external_tax_calculation, is_avatax, avatax_unique_code), which "
    "does not exist on the v15 OCA fork. Point the runner at the odoo19 "
    "environment (ODOO19_URL / ODOO19_DB in config/local.yaml)"
)

NO_AVATAX_MODULE = (
    "Odoo Enterprise 'account_avatax' is not installed on this database — "
    "account.move.is_avatax is absent, so no FG-05 expectation can be "
    "evaluated"
)


def _sandbox_block(detail: str) -> str:
    return (
        f"requires the Avalara SANDBOX — {detail}. Configure sandbox "
        f"credentials on the company (Accounting > Configuration > Settings > "
        f"Taxes > AvaTax) with Environment = Sandbox. NEVER point a test "
        f"system at the production Avalara credentials: it files real tax "
        f"documents (client guideline Read Me, safety rule 1)"
    )


# ---------------------------------------------------------------- addresses
# Workbook Test Data. Phoenix AZ is the multi-jurisdiction address the
# workbook names for TC-TAX-002/003/009; Missoula MT is its no-state-sales-tax
# counterpart for TC-TAX-009.
ADDRESS_PHOENIX_AZ = {
    "street": "1 E Washington St", "city": "Phoenix",
    "zip": "85004", "state_code": "AZ", "country_code": "US",
}
ADDRESS_MISSOULA_MT = {
    "street": "100 N Higgins Ave", "city": "Missoula",
    "zip": "59802", "state_code": "MT", "country_code": "US",
}
ADDRESS_TUCSON_AZ = {
    "street": "7000 E Tanque Verde Rd", "city": "Tucson",
    "zip": "85715", "state_code": "AZ", "country_code": "US",
}
# Deliberately missing zip / state / country — TC-TAX-007's delivery contact.
ADDRESS_INCOMPLETE = {
    "street": "200 Side St", "city": "Tucson",
    "zip": False, "state_code": None, "country_code": None,
}

# v15 jurisdiction tax naming, kept deliberately by
# mmg_account_avatax_enhancement._extract_tax_values_from_avatax_detail:
#   "ARIZONA STATE TAX [AZ] (5.6000 %)"    percentage jurisdictions
#   "AZ RETAIL DELIVERY FEE [AZ] ($ 0.2700)"  flat per-transaction fees
# The workbook (TC-TAX-002 Expected Result) fails any name without the
# square-bracketed authority code.
JURISDICTION_TAX_NAME_RE = re.compile(
    r"^.+\s\[[^\[\]]+\]\s\((?:\$\s)?-?\d+(?:\.\d+)?(?:\s%)?\)$")

AUTHORITY_CODE_RE = re.compile(r"\[([^\[\]]+)\]")


# ------------------------------------------------------- Avalara tax codes
# Every line account_avatax sends carries a ``taxCode``, resolved by
# ``product.product._get_avatax_category_id()`` — the product's own code, else
# the template's, else ``product.category``'s walking ``parent_id`` upward
# (account_avatax/models/product.py:29-57). A line that resolves nothing makes
# ``_prepare_avatax_document_line_service_call`` raise "The Avalara Tax Code
# is required for <product> (#<id>) / See https://taxcode.avatax.avalara.com/"
# BEFORE the HTTP call (account_avatax/models/
# account_external_tax_mixin.py:86-95), so the document never reaches Avalara
# and no FG-05 expectation can be evaluated. The target database's default
# product category carries no code, which is why every FG05 fixture product is
# created inside ONE FG05-marked product category that does — see
# :func:`fg05_product_category`.
AVATAX_CATEGORY_MODEL = "product.avatax.category"

# Avalara's general "tangible personal property" code — the catch-all a
# gallery's art items map to, and the same code TC-TAX-014 / TC-TAX-016 prefer
# for the taxable side of their pair. It ships with account_avatax
# (data/product.avatax.category.csv, 3,483 codes). It is a PREFERENCE, never a
# requirement: :func:`pick_default_avatax_category` falls back to the lowest id
# on the database, so nothing here depends on one code string existing.
DEFAULT_AVATAX_CODE = "P0000000"

# Label of the single shared FG05 product category. ``make_product_category``
# prefixes the marker, so ``sweep_fg05`` removes it like every other fixture.
DEFAULT_CATEGORY_LABEL = "Default Taxable Goods"

NO_AVATAX_CATEGORY_MODEL = (
    "the model product.avatax.category does not exist on this database "
    "(Odoo Enterprise 'account_avatax' is not installed), so no fixture "
    "product can carry an Avalara Tax Code and no FG-05 expectation can be "
    "evaluated"
)

NO_AVATAX_CATEGORY_DATA = (
    "no product.avatax.category record exists on this database, so no FG05 "
    "fixture product can be given an Avalara Tax Code and account_avatax "
    "refuses every document before it reaches Avalara ('The Avalara Tax Code "
    "is required for ...', account_avatax/models/"
    "account_external_tax_mixin.py:86-95). The module's own data file "
    "(account_avatax/data/product.avatax.category.csv, 3,483 codes) has not "
    "loaded: upgrade or reinstall Odoo Enterprise 'account_avatax' on the "
    "target database and re-run. This is a data-setup gap in the target "
    "database — a regression test may not invent a tax code around it"
)


# ------------------------------------------------------------------- gates
def require_v19(ctx):
    """BLOCK unless the target environment is Odoo 19."""
    if ctx.env.version != "19":
        ctx.blocked(f"{V19_ONLY} (current target: {ctx.env.name})")
    if not ctx.adapter.rpc.field_exists("account.move", "is_avatax"):
        ctx.blocked(NO_AVATAX_MODULE)


def company_avatax_config(ctx) -> dict:
    """The company's AvaTax configuration, credentials as set/not-set only.

    ``avalara_api_id`` / ``avalara_api_key`` carry ``groups='base.group_system'``
    (account_avatax/models/res_company.py:15-16), so a non-system runner user
    simply does not receive them — that reads as 'not set' here, which is the
    correct verdict for a run that could not prove the credential is present.
    """
    rpc = ctx.adapter.rpc
    company_id = ctx.adapter.rpc.call("res.users", "read", [rpc.uid],
                                      fields=["company_id"])[0]["company_id"]
    company_id = company_id[0] if isinstance(company_id, (list, tuple)) else company_id

    wanted = ["name", "country_id", "setting_account_avatax",
              "avalara_environment", "avalara_commit",
              "avalara_address_validation", "avalara_use_upc",
              "avalara_api_id", "avalara_api_key"]
    present = rpc.call("res.company", "fields_get", wanted, attributes=["type"])
    readable = [f for f in wanted if f in present]
    data = rpc.read("res.company", [company_id], readable)[0]

    def _flag(field):
        value = data.get(field)
        return "set" if value else "not set"

    return {
        "company_id": company_id,
        "company_name": data.get("name"),
        "country": (data.get("country_id") or [None, ""])[1]
        if isinstance(data.get("country_id"), (list, tuple)) else "",
        "use_avatax": bool(data.get("setting_account_avatax")),
        "environment": data.get("avalara_environment") or "",
        "commit": bool(data.get("avalara_commit")),
        "address_validation": bool(data.get("avalara_address_validation")),
        "use_upc": bool(data.get("avalara_use_upc")),
        "api_id": _flag("avalara_api_id"),
        "api_key": _flag("avalara_api_key"),
        "credential_fields_readable": "avalara_api_key" in readable,
    }


def _company_row(rpc, company_id: int) -> dict:
    """One company's Avalara-relevant fields, credentials as set/not-set.

    Restricted fields (``groups='base.group_system'``) are absent from
    ``fields_get`` for a user without the group, which is reported here as
    ``credentials_readable = False`` — never silently as 'not set', because
    the two lead to opposite safety decisions.
    """
    wanted = ["name", "parent_id", "avalara_environment",
              "avalara_api_id", "avalara_api_key"]
    present = rpc.call("res.company", "fields_get", wanted, attributes=["type"])
    readable = [f for f in wanted if f in present]
    data = rpc.read("res.company", [company_id], readable)[0]
    parent = data.get("parent_id")
    creds_readable = ("avalara_api_id" in readable
                      and "avalara_api_key" in readable)
    return {
        "id": company_id,
        "name": data.get("name") or "",
        "parent_id": parent[0] if isinstance(parent, (list, tuple)) else (parent or None),
        "environment": data.get("avalara_environment") or "",
        "credentials_readable": creds_readable,
        "has_credentials": bool(creds_readable and data.get("avalara_api_id")
                                and data.get("avalara_api_key")),
    }


def avatax_client_target(ctx, company_id=None) -> dict:
    """Which Avalara HOST a call from ``company_id`` would actually reach.

    This mirrors ``account_avatax`` rather than guessing, because the obvious
    check is wrong. ``res.company.avalara_environment`` is
    ``required=True, default='sandbox'``
    (account_avatax/models/res_company.py:17-25), so EVERY company reads
    'sandbox' until someone changes it — including one that was never
    configured for AvaTax at all. And ``_get_client`` does not use the acting
    company's environment: it first calls ``_find_avatax_credentials_company``,
    which walks ``parent_id`` upward (with sudo) until it finds a company
    holding BOTH credentials, then builds
    ``AvataxClient(environment=<that ancestor>.avalara_environment)``
    (account_external_tax_mixin.py:300-321), and ``AvataxClient`` points at
    ``https://rest.avatax.com`` whenever that reads 'production'
    (lib/avatax_client.py:42-46).

    So a subsidiary with no credentials and the default 'sandbox' resolves to
    a parent holding PRODUCTION credentials. Checking the subsidiary would say
    "safe" while the call goes to the live Avalara account.

    Returns ``{"sandbox": bool, "reason": str, "resolved_id", "resolved_name",
    "environment", "chain"}``. ``sandbox`` is True only when the host is
    PROVABLY the sandbox; anything unprovable is False.
    """
    rpc = ctx.adapter.rpc
    if company_id is None:
        user = rpc.call("res.users", "read", [rpc.uid], fields=["company_id"])[0]
        raw = user["company_id"]
        company_id = raw[0] if isinstance(raw, (list, tuple)) else raw

    chain, seen, resolved = [], set(), None
    cursor = company_id
    while cursor and cursor not in seen:
        seen.add(cursor)
        row = _company_row(rpc, cursor)
        chain.append(row)
        if not row["credentials_readable"]:
            return {
                "sandbox": False, "resolved_id": None, "resolved_name": "",
                "environment": "", "chain": chain,
                "reason": (
                    f"res.company.avalara_api_id / avalara_api_key are not "
                    f"readable as {ctx.env.username!r} (they carry "
                    f"groups='base.group_system'), so the company whose "
                    f"environment AvataxClient would use cannot be resolved. "
                    f"Refusing to treat the target as the sandbox"),
            }
        if row["has_credentials"]:
            resolved = row
            break
        cursor = row["parent_id"]

    trail = " -> ".join(f"{c['name']}#{c['id']}({c['environment'] or '?'})"
                        for c in chain)
    if resolved is None:
        return {
            "sandbox": False, "resolved_id": None, "resolved_name": "",
            "environment": "", "chain": chain,
            "reason": (f"no company in the chain {trail} holds both Avalara "
                       f"credentials, so _find_avatax_credentials_company "
                       f"returns None and _get_client raises RedirectWarning "
                       f"— the target cannot be proven to be the sandbox"),
        }

    # Defence in depth: refuse if ANY company on the walked path is
    # production-pointed, not only the resolved one.
    production = [c for c in chain if c["environment"] == "production"]
    if production or resolved["environment"] != "sandbox":
        offenders = ", ".join(f"{c['name']}#{c['id']}={c['environment']!r}"
                              for c in (production or [resolved]))
        return {
            "sandbox": False, "resolved_id": resolved["id"],
            "resolved_name": resolved["name"],
            "environment": resolved["environment"], "chain": chain,
            "reason": (f"the Avalara credentials resolve to "
                       f"{resolved['name']}#{resolved['id']} whose "
                       f"environment is {resolved['environment'] or 'empty'!r} "
                       f"(chain {trail}; offending: {offenders})"),
        }

    return {
        "sandbox": True, "resolved_id": resolved["id"],
        "resolved_name": resolved["name"], "environment": "sandbox",
        "chain": chain, "reason": "",
    }


def _avatax_calls_are_safe(ctx, company_id=None) -> tuple[bool, str]:
    """``(safe, reason)`` — never raises, for use in teardown paths."""
    try:
        target = avatax_client_target(ctx, company_id)
    except Exception as exc:  # noqa: BLE001 — teardown must not raise
        return False, f"could not resolve the Avalara target ({exc})"
    return target["sandbox"], target["reason"]


def require_sandbox(ctx, detail: str) -> dict:
    """Gate every case whose essence is a live Avalara call.

    Returns the company AvaTax configuration when the SANDBOX is usable;
    otherwise BLOCKS with a precise, actionable reason. ``detail`` names what
    this particular case needed the sandbox for.
    """
    require_v19(ctx)
    config = company_avatax_config(ctx)
    ctx.log(f"AvaTax config — company={config['company_name']!r} "
            f"use_avatax={config['use_avatax']} "
            f"environment={config['environment']!r} "
            f"commit={config['commit']} "
            f"api_id={config['api_id']} api_key={config['api_key']}")

    if not config["use_avatax"]:
        ctx.blocked(_sandbox_block(
            "'Use AvaTax' is not enabled on the company, so no document "
            "computes tax externally"))
    if config["environment"] != "sandbox":
        ctx.blocked(_sandbox_block(
            f"the company's Avalara Environment reads "
            f"{config['environment'] or 'empty'!r}, not 'sandbox'. This suite "
            f"refuses to compute tax against a non-sandbox Avalara account"))
    if config["api_id"] != "set" or config["api_key"] != "set":
        missing = [n for n in ("api_id", "api_key") if config[n] != "set"]
        ctx.blocked(_sandbox_block(
            f"sandbox credential(s) {', '.join(missing)} are not readable as "
            f"set on the company (needed for: {detail})"))

    # The checks above look at the company the runner user acts as. That is
    # not necessarily the company whose environment AvataxClient uses — see
    # avatax_client_target() for why. Prove the actual host as well.
    target = avatax_client_target(ctx, config["company_id"])
    ctx.log(f"Avalara host resolves via {target['resolved_name']}"
            f"#{target['resolved_id']} -> "
            f"{'sandbox' if target['sandbox'] else 'NOT PROVABLY SANDBOX'}")
    if not target["sandbox"]:
        ctx.blocked(_sandbox_block(
            f"{target['reason']} (needed for: {detail})"))
    return config


def require_avatax_fiscal_position(ctx) -> tuple[int, dict]:
    """First fiscal position flagged for AvaTax — READ-ONLY reference.

    The workbook's precondition on almost every case is "the AvaTax fiscal
    position exists". Returns ``(id, values)`` including both AvaTax accounts,
    which TC-TAX-015 compares against.
    """
    rpc = ctx.adapter.rpc
    found = rpc.search_read(
        "account.fiscal.position", [("is_avatax", "=", True)],
        ["name", "avatax_invoice_account_id", "avatax_refund_account_id"],
        limit=1, order="id")
    if not found:
        ctx.blocked(
            "no fiscal position has 'Use AvaTax API' ticked on this database "
            "— TC-DAT-017 covers that setup gap; every other FG-05 case "
            "depends on it (client guideline, GATE 3)")
    return found[0]["id"], found[0]


# ------------------------------------------------- warehouse shipFrom gate
# Odoo 19 Enterprise sends a LINE-LEVEL ``shipFrom`` address for a sale order
# line whose warehouse has an address of its own, and gets that address wrong
# in two independent places. A warehouse with NO address at all therefore does
# not fall back to the document-level shipFrom: it sends ``country: False`` and
# Avalara rejects the whole CreateTransaction with "Unknown country name or
# code (FALSE)". No FG-05 QUOTATION expectation can be evaluated on such a
# database — not because the expectation is wrong, but because the document
# never gets a tax figure of any kind.
AVATAX_STOCK_MODULE = "account_avatax_stock"

ODOO_SHIPFROM_DEFECT = (
    "WHY THIS IS AN ODOO DEFECT AND NOT A TEST FAULT — two stock Odoo 19 "
    "Enterprise bugs combine here. (1) account_avatax_stock/models/"
    "account_external_tax_mixin.py:32-35 adds the line-level addresses "
    "whenever `warehouse and warehouse.partner_id != "
    "line_data['base_line']['record'].company_id.partner_id`; an EMPTY "
    "res.partner recordset is not equal to the company's partner, so a "
    "warehouse with no Address TAKES that branch instead of being skipped, and "
    "line 22 then calls `self._get_avatax_address(warehouse_id.partner_id)` on "
    "that empty recordset. (2) account_avatax/models/"
    "account_external_tax_mixin.py:108-121 `_get_avatax_address` guards its "
    "real branch with `all(partner._fields[field] for field in ['zip', "
    "'state_id', 'country_id'])` — `partner._fields[f]` is the FIELD "
    "DESCRIPTOR, which is always truthy, so the test can never be False, the "
    "latitude/longitude fallback on lines 118-120 is unreachable dead code, "
    "and the call goes out with 'country': partner.country_id.code = False for "
    "an empty or incomplete partner. mmg_account_avatax_enhancement cannot "
    "catch it either: its _check_partner_shipping_address guard validates "
    "partner_shipping_id only (mmg_account_avatax_enhancement/models/"
    "account_external_tax_mixin.py:44-71) and never looks at the warehouse. "
    "Report this to Odoo Enterprise; the database-side remedy above is what "
    "unblocks FG-05 in the meantime."
)

SHIPFROM_REMEDY = (
    "REMEDY (an Inventory administrator, not a code change): open Inventory > "
    "Configuration > Warehouses > the warehouse named below, set its Address "
    "(stock.warehouse.partner_id, addons/stock/models/stock_warehouse.py:41 — "
    "the field is NOT required, which is how it came to be empty) to a partner "
    "whose Country, State and Zip are all filled in, and re-run. Pointing the "
    "warehouse at the company's own partner also works: that is the one case "
    "account_avatax_stock treats as 'nothing to add'."
)


def _partner_address_row(rpc, partner_id: int) -> dict:
    """name / street / city / zip / state / country of one partner."""
    data = rpc.read("res.partner", [partner_id],
                    ["display_name", "street", "city", "zip",
                     "state_id", "country_id"])[0]
    return {
        "id": partner_id,
        "name": data.get("display_name") or "",
        "street": data.get("street") or "",
        "city": data.get("city") or "",
        "zip": data.get("zip") or "",
        "state_id": _m2o(data.get("state_id")),
        "country_id": _m2o(data.get("country_id")),
    }


def warehouse_shipfrom_probe(ctx, order_id: int) -> dict:
    """Can Avalara be given a usable ``shipFrom`` for this quotation's lines?

    Reads the warehouse each ``sale.order.line`` actually ships from — which is
    exactly what ``account_avatax_stock`` reads: ``sale.order`` builds the line
    data as ``line['warehouse_id'] = line['base_line']['record'].warehouse_id``
    (account_avatax_stock/models/sale_order.py:11), and ``sale.order.line.
    warehouse_id`` is a stored computed field seeded from
    ``order_id.warehouse_id`` (addons/sale_stock/models/sale_order_line.py:23
    and 32-52). ``sale.order.warehouse_id`` itself is
    addons/sale_stock/models/sale_order.py:27-30.

    Returns ``{"applicable", "ok", "gap", "note", "warehouses"}``. ``ok`` is
    True when every warehouse involved either has a complete address or IS the
    company partner (the one case account_avatax_stock skips). ``applicable``
    is False when nothing on this database can add a line-level address, in
    which case ``ok`` stays True and no case is gated.
    """
    rpc = ctx.adapter.rpc
    probe = {"applicable": True, "ok": True, "gap": "", "note": "",
             "warehouses": []}

    if not rpc.model_exists("stock.warehouse") or not rpc.field_exists(
            "sale.order", "warehouse_id"):
        probe["applicable"] = False
        probe["note"] = (
            "sale.order.warehouse_id does not exist on this database "
            "(addons/sale_stock is not installed), so no line-level shipFrom "
            "can be built and this gate does not apply")
        return probe

    # account_avatax_stock is the module that adds the line-level addresses.
    # ir.module.module is readable to base.group_system only (odoo/addons/base/
    # security/ir.model.access.csv:25), so an unreadable state is reported and
    # treated as installed — which is the module's own auto_install default
    # (account_avatax_stock/__manifest__.py: 'auto_install': True).
    try:
        rows = rpc.search_read("ir.module.module",
                               [("name", "=", AVATAX_STOCK_MODULE)],
                               ["state"], limit=1)
        state = rows[0]["state"] if rows else "not present"
    except OdooRPCError as exc:
        state = f"unreadable ({exc})"
    if state in ("uninstalled", "uninstallable", "not present"):
        probe["applicable"] = False
        probe["note"] = (
            f"{AVATAX_STOCK_MODULE} is {state} on this database, so no "
            f"line-level shipFrom is sent and this gate does not apply")
        return probe
    probe["note"] = f"{AVATAX_STOCK_MODULE} state: {state}"

    order = rpc.read("sale.order", [order_id],
                     ["name", "warehouse_id", "company_id"])[0]
    company_id = _m2o(order.get("company_id"))
    company_partner_id = None
    if company_id:
        company_partner_id = _m2o(
            rpc.read("res.company", [company_id], ["partner_id"])[0]
            .get("partner_id"))

    # The LINE warehouse is what account_avatax_stock reads; the order's is
    # only its seed, and a route rule can move a line to another warehouse
    # (sale_order_line.py:36-52). Prefer the line values when they exist.
    warehouse_ids, source = [], "sale.order.line.warehouse_id"
    if rpc.field_exists("sale.order.line", "warehouse_id"):
        for row in rpc.search_read("sale.order.line",
                                   [("order_id", "=", order_id)],
                                   ["warehouse_id"]):
            wid = _m2o(row.get("warehouse_id"))
            if wid and wid not in warehouse_ids:
                warehouse_ids.append(wid)
    else:
        source = "sale.order.warehouse_id"
        order_wh = _m2o(order.get("warehouse_id"))
        if order_wh:
            warehouse_ids = [order_wh]
    probe["note"] += f"; warehouse(s) read from {source}"

    gaps = []
    for warehouse_id in warehouse_ids:
        wh = rpc.read("stock.warehouse", [warehouse_id],
                      ["name", "code", "partner_id"])[0]
        partner_id = _m2o(wh.get("partner_id"))
        row = {"id": warehouse_id, "name": wh.get("name") or "",
               "code": wh.get("code") or "", "partner_id": partner_id,
               "partner": None, "verdict": ""}
        label = (f"stock.warehouse #{warehouse_id} "
                 f"{(wh.get('name') or '')!r} (short name "
                 f"{(wh.get('code') or '')!r})")
        if not partner_id:
            row["verdict"] = "no Address at all"
            gaps.append(f"{label} has NO Address at all — its "
                        f"stock.warehouse.partner_id is empty")
        elif company_partner_id and partner_id == company_partner_id:
            row["verdict"] = "is the company partner — skipped by Odoo"
        else:
            partner = _partner_address_row(rpc, partner_id)
            row["partner"] = partner
            missing = [name for name, value in
                       (("country_id", partner["country_id"]),
                        ("state_id", partner["state_id"]),
                        ("zip", partner["zip"])) if not value]
            if missing:
                row["verdict"] = f"Address incomplete: {', '.join(missing)}"
                gaps.append(
                    f"{label} has Address res.partner #{partner_id} "
                    f"{partner['name']!r}, which is missing "
                    f"{', '.join(missing)}")
            else:
                row["verdict"] = "complete"
        probe["warehouses"].append(row)

    probe["ok"] = not gaps
    probe["gap"] = "; ".join(gaps)
    return probe


def require_warehouse_shipfrom(ctx, order_id: int, detail: str) -> dict:
    """BLOCK a QUOTATION case whose shipFrom address cannot be built.

    Called only where a warehouse is genuinely involved — i.e. on
    ``sale.order``. Invoice cases never reach it: ``account_avatax_stock``
    resolves an invoice line's warehouse from its delivery moves and leaves it
    ``None`` unless the line's stock moves resolve to exactly one shipping
    address (account_avatax_stock/models/account_move.py:10-15), so a
    stand-alone customer invoice sends no line-level address at all.
    """
    probe = warehouse_shipfrom_probe(ctx, order_id)
    if not probe["applicable"]:
        summary = "gate not applicable"
    else:
        summary = " | ".join(
            f"#{w['id']} {w['name']!r}: {w['verdict']}"
            for w in probe["warehouses"]) or "no warehouse on any line"
    ctx.log(f"shipFrom probe on sale.order #{order_id} — {probe['note']}; "
            f"{summary}")
    if probe["applicable"] and not probe["ok"]:
        ctx.blocked(
            f"this quotation cannot be taxed by AvaTax on this database "
            f"because its shipFrom address cannot be built: {probe['gap']}. "
            f"Odoo sends that empty address to Avalara as 'country': False and "
            f"Avalara rejects the entire CreateTransaction with 'Unknown "
            f"country name or code (FALSE)', so the document never receives a "
            f"tax figure and no FG-05 quotation expectation can be evaluated "
            f"(needed for: {detail}). This is a BLOCKED verdict, not a pass: "
            f"FG-05's quotation coverage is unavailable until the warehouse "
            f"address is fixed. {SHIPFROM_REMEDY} {ODOO_SHIPFROM_DEFECT}")
    return probe


# ---------------------------------------------------------------- fixtures
def _ref_country(rpc, code: str):
    found = rpc.search("res.country", [("code", "=", code)], limit=1)
    return found[0] if found else None


def _ref_state(rpc, country_id: int, code: str):
    found = rpc.search("res.country.state",
                       [("country_id", "=", country_id), ("code", "=", code)],
                       limit=1)
    return found[0] if found else None


def address_values(rpc, address: dict) -> dict:
    """Turn one of the ADDRESS_* dicts into res.partner write values."""
    values = {"street": address.get("street") or False,
              "city": address.get("city") or False,
              "zip": address.get("zip") or False}
    country_id = False
    if address.get("country_code"):
        country_id = _ref_country(rpc, address["country_code"]) or False
    values["country_id"] = country_id
    state_id = False
    if country_id and address.get("state_code"):
        state_id = _ref_state(rpc, country_id, address["state_code"]) or False
    values["state_id"] = state_id
    return values


def make_partner(ctx, label: str, address: dict, *, fiscal_position_id=None,
                 parent_id=None, partner_type=None, exemption_id=None) -> int:
    """Create one FG05-marked partner. Never reuses a business record."""
    rpc = ctx.adapter.rpc
    values = {"name": f"{MARK} {label}"}
    values.update(address_values(rpc, address))
    if fiscal_position_id:
        values["property_account_position_id"] = fiscal_position_id
    if parent_id:
        values["parent_id"] = parent_id
    if partner_type:
        values["type"] = partner_type
    if exemption_id is not None:
        values["avalara_exemption_id"] = exemption_id
    partner_id = rpc.create("res.partner", values)
    ctx.log(f"fixture partner #{partner_id} {values['name']!r}")
    return partner_id


def make_product(ctx, label: str, price: float, *, categ_id=None) -> int:
    """Create one FG05-marked storable product with NO Odoo-side tax.

    Odoo-side taxes are cleared so the only tax on a document is the one
    Avalara returns — which is what every FG-05 expectation is about.

    The product is filed under the shared FG05 AvaTax product category
    (:func:`fg05_product_category`) unless the caller supplies ``categ_id``.
    Without it the fixture would inherit the database's default product
    category, which carries no ``avatax_category_id``, and account_avatax
    would refuse the document with "The Avalara Tax Code is required for ..."
    before the request left Odoo (account_avatax/models/
    account_external_tax_mixin.py:86-95) — every FG-05 expectation about the
    computed tax would then be unevaluable. TC-TAX-014 and TC-TAX-016 build
    their own category, because the code ON that category is the thing those
    two cases are testing, and they keep passing it here.
    """
    rpc = ctx.adapter.rpc
    if categ_id is None:
        categ_id = fg05_product_category(ctx)
    values = {
        "name": f"{MARK} {label}",
        "default_code": f"{MARK}-{label.upper().replace(' ', '-')}",
        "list_price": price,
        "sale_ok": True,
        "taxes_id": [(6, 0, [])],
        "categ_id": categ_id,
    }
    values.update(ctx.adapter.storable_product_values())
    tmpl_id = rpc.create("product.template", values)
    variant = rpc.search_read("product.product",
                              [("product_tmpl_id", "=", tmpl_id)],
                              ["id"], limit=1)
    ctx.log(f"fixture product #{variant[0]['id']} {values['name']!r} "
            f"@ {price} in product.category #{categ_id}")
    return variant[0]["id"]


def make_product_category(ctx, label: str, avatax_category_id=None) -> int:
    rpc = ctx.adapter.rpc
    values = {"name": f"{MARK} {label}"}
    if avatax_category_id is not None:
        values["avatax_category_id"] = avatax_category_id
    return rpc.create("product.category", values)


def _m2o(value):
    """``[id, display_name]`` -> id; ``False`` / ``None`` / ``[]`` -> ``None``."""
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    return value or None


def pick_default_avatax_category(ctx) -> dict:
    """The ``product.avatax.category`` the FG05 fixture products map to.

    Chosen from what the TARGET DATABASE actually holds, never from a
    hard-coded code that has to exist: the general tangible-personal-property
    code (:data:`DEFAULT_AVATAX_CODE`) when it is loaded, otherwise the lowest
    id. Both branches are deterministic, so repeated runs against the same
    database send the same ``taxCode`` and the tax figures stay repeatable.

    Returns the row plus ``preferred`` — True when the general code was found,
    so callers can say in evidence WHICH code they used and why. Blocks when
    the database holds no code at all: that is a data-setup gap, and inventing
    a ``product.avatax.category`` row would be fabricating tax configuration.
    """
    rpc = ctx.adapter.rpc
    if not rpc.model_exists(AVATAX_CATEGORY_MODEL):
        ctx.blocked(NO_AVATAX_CATEGORY_MODEL)
    preferred = rpc.search_read(AVATAX_CATEGORY_MODEL,
                                [("code", "=", DEFAULT_AVATAX_CODE)],
                                ["code", "description"], limit=1, order="id")
    rows = preferred or rpc.search_read(AVATAX_CATEGORY_MODEL, [],
                                        ["code", "description"],
                                        limit=1, order="id")
    if not rows:
        ctx.blocked(NO_AVATAX_CATEGORY_DATA)
    chosen = dict(rows[0])
    chosen["preferred"] = bool(preferred)
    return chosen


def fg05_product_category(ctx) -> int:
    """Find-or-create the ONE FG05 product category carrying an AvaTax code.

    Find-or-create rather than create: :func:`sweep_fg05` removes it between
    tests, and the two products a single test may build have to land in the
    same category. An existing FG05 category whose ``avatax_category_id`` was
    somehow cleared is repaired rather than duplicated.

    The category is ``FG05``-marked through :func:`make_product_category`, so
    it is swept exactly like every other fixture and no business product
    category is read, written or relied upon.
    """
    rpc = ctx.adapter.rpc
    name = f"{MARK} {DEFAULT_CATEGORY_LABEL}"
    existing = rpc.search_read("product.category", [("name", "=", name)],
                               ["avatax_category_id"], limit=1, order="id")
    if existing and _m2o(existing[0].get("avatax_category_id")):
        return existing[0]["id"]

    chosen = pick_default_avatax_category(ctx)
    if existing:
        categ_id = existing[0]["id"]
        rpc.write("product.category", [categ_id],
                  {"avatax_category_id": chosen["id"]})
    else:
        categ_id = make_product_category(ctx, DEFAULT_CATEGORY_LABEL,
                                         avatax_category_id=chosen["id"])
    why = ("the general tangible-personal-property code"
           if chosen["preferred"]
           else f"the lowest id on this database — {DEFAULT_AVATAX_CODE} is "
                f"not loaded here")
    ctx.log(f"FG05 fixture product category #{categ_id} {name!r} carries "
            f"product.avatax.category #{chosen['id']} [{chosen['code']}] "
            f"{chosen.get('description') or ''} ({why}); every FG05 fixture "
            f"product resolves its Avalara Tax Code from here unless its own "
            f"case supplies a category")
    return categ_id


def make_invoice(ctx, partner_id: int, lines, *, fiscal_position_id,
                 shipping_partner_id=None, move_type="out_invoice") -> int:
    """Create one draft customer invoice. ``lines`` is [(product_id, qty, price)].

    ``invoice_date`` is left unset on purpose: Odoo fills it at posting and
    Avalara defaults to today, which is exactly what a tester following the
    workbook by hand gets.
    """
    rpc = ctx.adapter.rpc
    invoice_lines = []
    for product_id, qty, price in lines:
        invoice_lines.append((0, 0, {
            "product_id": product_id,
            "quantity": qty,
            "price_unit": price,
            "tax_ids": [(6, 0, [])],
        }))
    values = {
        "move_type": move_type,
        "partner_id": partner_id,
        "fiscal_position_id": fiscal_position_id,
        "invoice_line_ids": invoice_lines,
    }
    if shipping_partner_id:
        values["partner_shipping_id"] = shipping_partner_id
    move_id = rpc.create("account.move", values)
    ctx.log(f"draft invoice #{move_id} for partner #{partner_id}")
    return move_id


def make_quotation(ctx, partner_id: int, lines, *, fiscal_position_id,
                   shipping_partner_id=None) -> int:
    """Create one draft quotation. ``lines`` is [(product_id, qty, price)]."""
    rpc = ctx.adapter.rpc
    order_lines = []
    for product_id, qty, price in lines:
        order_lines.append((0, 0, {
            "product_id": product_id,
            "product_uom_qty": qty,
            "price_unit": price,
            # v19 field name: sale.order.line.tax_ids (addons/sale/models/
            # sale_order_line.py). v15's tax_id no longer exists.
            "tax_ids": [(6, 0, [])],
        }))
    values = {
        "partner_id": partner_id,
        "fiscal_position_id": fiscal_position_id,
        "order_line": order_lines,
    }
    if shipping_partner_id:
        values["partner_shipping_id"] = shipping_partner_id
    order_id = rpc.create("sale.order", values)
    ctx.log(f"draft quotation #{order_id} for partner #{partner_id}")
    return order_id


# ------------------------------------------------------------- document ops
def compute_taxes(ctx, model: str, record_id: int):
    """The workbook's 'Compute Taxes' button.

    v19 renamed v15's ``button_update_avatax`` to
    ``button_external_tax_calculation`` (account_external_tax /
    sale_external_tax views, string="Compute Taxes"). This is the ONE place
    the suite calls Avalara; every caller has passed require_sandbox() first.
    """
    return ctx.adapter.rpc.call(model, "button_external_tax_calculation",
                                [record_id])


def doc_totals(ctx, model: str, record_id: int) -> dict:
    """Untaxed / Taxes / Total as the workbook's totals block reads them."""
    fields = ["amount_untaxed", "amount_tax", "amount_total", "state",
              "avatax_unique_code"]
    data = ctx.adapter.rpc.read(model, [record_id], fields)[0]
    return {
        "untaxed": round(float(data["amount_untaxed"]), 2),
        "tax": round(float(data["amount_tax"]), 2),
        "total": round(float(data["amount_total"]), 2),
        "state": data["state"],
        "avalara_code": data.get("avatax_unique_code") or "",
    }


def move_tax_lines(ctx, move_id: int) -> list[dict]:
    """Journal items that carry a tax — the workbook's TC-TAX-002 step 3.

    ``tax_line_id`` set means the line IS the tax, which is the split the
    gallery files its returns from.
    """
    rows = ctx.adapter.rpc.search_read(
        "account.move.line",
        [("move_id", "=", move_id), ("tax_line_id", "!=", False)],
        ["account_id", "tax_line_id", "balance", "name"], order="id")
    out = []
    for row in rows:
        account = row["account_id"]
        tax = row["tax_line_id"]
        out.append({
            "account_id": account[0] if isinstance(account, (list, tuple)) else account,
            "account": account[1] if isinstance(account, (list, tuple)) else "",
            "tax_id": tax[0] if isinstance(tax, (list, tuple)) else tax,
            "tax_name": tax[1] if isinstance(tax, (list, tuple)) else "",
            "balance": round(float(row["balance"]), 2),
        })
    return out


def account_code(ctx, account_id) -> str:
    if not account_id:
        return ""
    data = ctx.adapter.rpc.read("account.account", [account_id], ["code"])
    return data[0]["code"] if data else ""


# ------------------------------------------------ tax account plausibility
# ``account.tax.repartition.line.account_id`` is "Account on which to post the
# tax amount" (addons/account/models/account_tax.py:5287-5291), and it is where
# ``account_avatax`` puts the fiscal position's Avatax Invoice / Refund Account
# (account_avatax/models/account_external_tax_mixin.py:187 and :191). What
# counts as a sane account for that is taken from Odoo's own source, never from
# an opinion about charts of accounts:
#
#   * the field's own domain refuses ``asset_receivable``, ``liability_payable``
#     and ``off_balance`` outright (account_tax.py:5289);
#   * ``_compute_use_in_tax_closing`` (account_tax.py:5310-5317) drops any tax
#     repartition account whose ``internal_group`` is 'income' or 'expense' out
#     of the tax closing entry, so tax booked there never reaches the return;
#   * ``internal_group`` is ``account_type.split('_', 1)[0]``
#     (addons/account/models/account_account.py:649-650), and the account_type
#     selection is account_account.py:44-65.
#
# What is left, and what a sales-tax control account actually is, is a tax
# liability — money collected and owed to the authority — or, in the charts that
# book recoverable tax on the asset side, a current asset.
TAX_ACCOUNT_EXPECTED_TYPES = ("liability_current", "liability_non_current",
                              "asset_current")

TAX_ACCOUNT_DOMAIN_REFUSED = ("asset_receivable", "liability_payable",
                              "off_balance")


def _internal_group(account_type: str) -> str:
    """Odoo's own derivation — account_account.py:649-650."""
    return (account_type or "").split("_", 1)[0]


def account_row(ctx, account_id) -> dict:
    """id / code / name / account_type / internal_group for one account."""
    if not account_id:
        return {"id": None, "code": "", "name": "", "account_type": "",
                "internal_group": ""}
    data = ctx.adapter.rpc.read("account.account", [account_id],
                                ["code", "name", "account_type"])
    if not data:
        return {"id": account_id, "code": "", "name": "", "account_type": "",
                "internal_group": ""}
    account_type = data[0].get("account_type") or ""
    return {
        "id": account_id,
        "code": data[0].get("code") or "",
        "name": data[0].get("name") or "",
        "account_type": account_type,
        "internal_group": _internal_group(account_type),
    }


def tax_account_verdict(row: dict) -> tuple[bool, str]:
    """``(plausible, why_not)`` for an account used to POST a tax amount."""
    account_type = row.get("account_type") or ""
    group = row.get("internal_group") or _internal_group(account_type)
    if not account_type:
        return False, ("the account carries no Type at all, so nothing can be "
                       "said about where the tax would land")
    if account_type in TAX_ACCOUNT_DOMAIN_REFUSED:
        return False, (f"Odoo's own domain on account.tax.repartition.line."
                       f"account_id refuses {account_type!r} outright "
                       f"(addons/account/models/account_tax.py:5289)")
    if group in ("income", "expense"):
        return False, (f"{account_type!r} is in the {group!r} internal group, "
                       f"and _compute_use_in_tax_closing (addons/account/"
                       f"models/account_tax.py:5310-5317) drops an income or "
                       f"expense repartition account OUT of the tax closing "
                       f"entry — tax posted here is booked as "
                       f"{'revenue' if group == 'income' else 'cost'} and "
                       f"never reaches the tax return")
    if account_type == "asset_cash":
        return False, ("this is a BANK/CASH account: posting a tax charge to "
                       "it records the tax as money already in the bank "
                       "instead of a liability owed to the tax authority, and "
                       "it puts phantom entries into every bank "
                       "reconciliation on that account")
    if account_type == "liability_credit_card":
        return False, ("this is a credit-card liability account: it is "
                       "reconciled against a card statement, not remitted to "
                       "a tax authority")
    if account_type not in TAX_ACCOUNT_EXPECTED_TYPES:
        return False, (f"{account_type!r} is not a tax control account — a "
                       f"sales tax collected on behalf of an authority is a "
                       f"liability (one of "
                       f"{', '.join(TAX_ACCOUNT_EXPECTED_TYPES)})")
    return True, ""


def describe_account(row: dict) -> str:
    """One evidence-line description of an account."""
    return (f"account.account #{row.get('id')} code {row.get('code')!r} "
            f"{row.get('name')!r} Type={row.get('account_type')!r} "
            f"(internal group {row.get('internal_group')!r})")


# ------------------------------------------------------ untruncated errors
def server_error_message(ctx, model: str, method: str, *args) -> str:
    """Repeat one model call over a raw web session and return the FULL error.

    ``adapters.base.OdooRPC.call`` reports only
    ``str(message).strip().splitlines()[-1]`` of a server error
    (adapters/base.py:156), so every multi-line Odoo message reaches a test
    with all but its last line already gone. Two FG-05 expectations are ABOUT
    the text of such a message — TC-TAX-007's address guard (a two-line
    ``ValidationError`` whose first line names the rule) and TC-TAX-017's
    step-6 readability check (``_handle_response`` returns
    "<Odoo title>\\n<Avalara detail>",
    account_avatax/models/account_external_tax_mixin.py:287-295) — and both
    must judge what the SERVER produced, not what the transport left of it.

    The identical ``/web/dataset/call_kw`` POST is therefore re-issued through
    ``framework.fg_common.http_session`` (a public framework helper; nothing
    in ``framework/`` is modified) and ``error.data.message`` is read
    untouched.

    Callers must only use this on a call that ALREADY failed: the failing
    transaction was rolled back, so the repeat writes nothing, but a repeat of
    a call that succeeded would be a second real document.

    Returns ``""`` when the repeat unexpectedly succeeds or when the raw read
    is not possible — the caller then falls back to the adapter's truncated
    message.
    """
    payload = json.dumps({
        "jsonrpc": "2.0", "method": "call", "id": 1,
        "params": {"model": model, "method": method,
                   "args": list(args), "kwargs": {}},
    }, default=str).encode()
    request = urllib.request.Request(
        f"{ctx.env.base_url}/web/dataset/call_kw", data=payload,
        headers={"Content-Type": "application/json"})
    try:
        opener = http_session(ctx.env)
        with opener.open(request, timeout=900) as response:
            reply = json.load(response)
    except (OSError, ValueError, RuntimeError) as exc:
        ctx.log(f"[evidence] could not re-read the untruncated server error "
                f"for {model}.{method}: {exc} — falling back to the adapter's "
                f"last-line-only message")
        return ""
    error = reply.get("error")
    if not error:
        return ""
    data = error.get("data") or {}
    return str(data.get("message") or error.get("message") or "").strip()


# ----------------------------------------------------------------- sweeping
def sweep_fg05(ctx):
    """Remove leftovers from previous FG-05 runs — marker-scoped only.

    POSTED moves are deliberately NOT deleted: Odoo forbids it, and the
    workbook itself says to leave posted sandbox documents in place. Every
    assertion in the suite is therefore scoped to ids captured in-test, never
    to a count of all FG05 records.

    The shared FG05 AvaTax product category (:func:`fg05_product_category`) is
    marker-named like every other fixture and is removed here with them, after
    the products that sit in it; the next test that needs it re-creates it.

    SAFETY — deleting an AvaTax invoice calls Avalara.
    ``account_external_tax/models/account_move.py::unlink`` runs
    ``_void_external_taxes()``, which ``account_avatax`` implements as
    ``_change_avatax_state('void')`` -> ``client.void_transaction(...)``
    against ``company.avalara_environment``. So an ordinary sweep of a draft
    AvaTax invoice is an outbound call, and on a production-pointed company it
    would void a REAL tax document. TC-TAX-007 runs without a sandbox gate by
    design (it needs no credentials), so this function cannot assume one has
    been applied: AvaTax-flagged moves are swept only when the company is
    verifiably on the sandbox, and are otherwise left in place with a logged
    reason. ``sale.order`` has no such override (``sale_external_tax`` does
    not extend ``unlink``), so quotations are always safe to sweep.
    """
    rpc = ctx.adapter.rpc
    marker = f"{MARK} %"

    # The guard below can only speak for ONE company, so the sweep must not
    # reach records belonging to another. The platform never sends
    # allowed_company_ids, so env.companies falls back to every company the
    # runner user is allowed into and the account.move record rule
    # ([('company_id','in',company_ids)]) would happily return a sibling
    # company's FG05 leftover — whose own company_id is what
    # _change_avatax_state passes to _get_client.
    try:
        company_id = company_avatax_config(ctx)["company_id"]
    except (OdooRPCError, IndexError, KeyError) as exc:
        ctx.log(f"[sweep] could not resolve the acting company ({exc}) — "
                f"nothing swept")
        return
    scope = [("company_id", "=", company_id)]

    # 1a. draft/cancelled invoices — split by whether deleting them calls out
    move_domain = [("partner_id.name", "like", marker),
                   ("state", "in", ("draft", "cancel"))] + scope
    avatax_ids = rpc.search(
        "account.move", move_domain + [("fiscal_position_id.is_avatax", "=", True)])
    plain_ids = [i for i in rpc.search("account.move", move_domain)
                 if i not in set(avatax_ids)]

    if avatax_ids:
        safe, reason = _avatax_calls_are_safe(ctx, company_id)
        if safe:
            try:
                rpc.unlink("account.move", avatax_ids)
                ctx.log(f"swept {len(avatax_ids)} draft AvaTax fixture "
                        f"invoice(s) — each void()s its SANDBOX transaction")
            except OdooRPCError as exc:
                ctx.log(f"[sweep] account.move not removable ({exc}) — "
                        f"left in place")
        else:
            ctx.log(f"[sweep] {len(avatax_ids)} draft AvaTax fixture "
                    f"invoice(s) LEFT IN PLACE: deleting one calls Avalara "
                    f"void_transaction and the target is not provably the "
                    f"sandbox — {reason}. Ids: {avatax_ids}")

    # 1b. everything else (no external-tax hook on unlink)
    for model, ids in (("account.move", plain_ids),
                       ("sale.order", rpc.search(
                           "sale.order",
                           [("partner_id.name", "like", marker),
                            ("state", "in", ("draft", "sent", "cancel"))]
                           + scope))):
        if ids:
            try:
                rpc.unlink(model, ids)
                ctx.log(f"swept {len(ids)} {model} fixture record(s)")
            except OdooRPCError as exc:
                ctx.log(f"[sweep] {model} not removable ({exc}) — left in place")

    # 2. products, then their categories, then partners
    for model in ("product.product", "product.template"):
        ids = rpc.search(model, [("name", "like", marker),
                                 ("active", "in", [True, False])])
        if ids:
            try:
                rpc.unlink(model, ids)
            except OdooRPCError:
                try:
                    rpc.write(model, ids, {"active": False})
                except OdooRPCError:
                    pass

    for model, domain in (
        ("product.category", [("name", "like", marker)]),
        ("res.partner", [("name", "like", marker), ("user_ids", "=", False)]),
    ):
        ids = rpc.search(model, domain)
        if ids:
            try:
                rpc.unlink(model, ids)
            except OdooRPCError as exc:
                ctx.log(f"[sweep] {model} not removable ({exc}) — left in place")


def cleanup(ctx, created: dict):
    """Best-effort teardown of ids captured during a test, then a sweep.

    ``created`` maps model name -> list of ids, deleted in the order given.
    Never raises: teardown must not turn a real verdict into an ERROR.

    Callers must REMOVE a move id from ``created`` once it is posted: a posted
    move cannot be unlinked, and handing one here would only produce a logged
    refusal. AvaTax-flagged draft moves are subject to the same sandbox guard
    as :func:`sweep_fg05` — see its docstring for why deleting one is an
    outbound Avalara call.
    """
    rpc = ctx.adapter.rpc
    for model, ids in created.items():
        ids = [i for i in ids if i]
        if not ids:
            continue
        if model == "account.move":
            # Never raises: an unguarded call here would escape the caller's
            # finally: and be recorded as ERROR/AUTOMATION_ERROR, destroying
            # the real FAILED or BLOCKED verdict the test had already reached.
            try:
                risky = rpc.search("account.move",
                                   [("id", "in", ids),
                                    ("fiscal_position_id.is_avatax", "=", True)])
            except Exception as exc:  # noqa: BLE001
                ctx.log(f"[cleanup] could not classify account.move{ids} "
                        f"({exc}) — left in place")
                continue
            if risky:
                safe, reason = _avatax_calls_are_safe(ctx)
                if not safe:
                    ctx.log(f"[cleanup] AvaTax move(s) {risky} LEFT IN PLACE: "
                            f"unlink calls Avalara void_transaction and the "
                            f"target is not provably the sandbox — {reason}")
                    ids = [i for i in ids if i not in set(risky)]
                    if not ids:
                        continue
        try:
            rpc.unlink(model, ids)
        except Exception as exc:  # noqa: BLE001 — teardown must never raise
            ctx.log(f"[cleanup] {model}{ids} not removable ({exc}) — "
                    f"left in place (a posted move cannot be deleted; note "
                    f"that account_external_tax.unlink sends the Avalara void "
                    f"BEFORE super().unlink() refuses, so a posted id must "
                    f"never reach here — callers remove it once posted)")
    try:
        sweep_fg05(ctx)
    except OdooRPCError as exc:
        ctx.log(f"[cleanup] sweep incomplete: {exc}")
