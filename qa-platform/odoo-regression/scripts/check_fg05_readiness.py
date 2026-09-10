"""FG-05 readiness check — run this BEFORE clicking Run in the web UI.

Answers one question: *if I run the 14 FG-05 AvaTax cases right now, what
will happen?* Every condition below is one the suite itself gates on, so a
clean report here means the tests will actually exercise tax computation
instead of reporting BLOCKED.

    venv\\Scripts\\python.exe scripts\\check_fg05_readiness.py

Read-only: it creates nothing, writes nothing, and never calls Avalara.
Exit code 0 = ready, 1 = something would block or fail.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from adapters import get_adapter  # noqa: E402
from adapters.base import OdooRPCError  # noqa: E402
from backend.config import load_environments  # noqa: E402

OK, WARN, BAD = "[ OK ]", "[WARN]", "[FAIL]"


def _m2o(value):
    return value[0] if isinstance(value, (list, tuple)) else (value or None)


def main() -> int:
    problems, warnings = [], []
    env = load_environments().get("odoo19")
    if env is None:
        print(f"{BAD} no 'odoo19' environment in config/environments.yaml")
        return 1

    print("FG-05 readiness — Odoo 19 AvaTax suite")
    print("=" * 68)
    print(f"target : {env.base_url}  db={env.db}  user={env.username}")
    print()

    # ---------------------------------------------------------- 1. reachable
    rpc = get_adapter(env).rpc
    try:
        version = rpc.server_version()
        print(f"{OK} server reachable — version {version}")
        if not version.startswith("19"):
            problems.append(
                f"server reports version {version!r}, not 19.x. FG-05 is "
                f"Odoo-19-only and every case will report BLOCKED.")
            print(f"{BAD} not an Odoo 19 server")
    except Exception as exc:  # noqa: BLE001
        print(f"{BAD} server UNREACHABLE at {env.base_url}: {exc}")
        print()
        print("  Every FG-05 case will report BLOCKED / ENVIRONMENT.")
        print("  Fix ODOO19_URL in config/local.yaml, or start the v19 server.")
        return 1

    # ------------------------------------------------------- 2. authenticate
    try:
        uid = rpc.uid
        print(f"{OK} authenticated as {env.username!r} (uid {uid})")
    except OdooRPCError as exc:
        print(f"{BAD} authentication FAILED for {env.username!r}: {exc}")
        print()
        print("  On a restored production database res.users id 1 is")
        print("  __system__ and INACTIVE. Find the real administrator:")
        print("    SELECT id, login, active FROM res_users WHERE id IN (1,2);")
        print("  Then set ODOO19_USERNAME / ODOO19_PASSWORD in local.yaml.")
        return 1

    # ------------------------------------------------------------ 3. modules
    if not rpc.field_exists("account.move", "is_avatax"):
        problems.append("Odoo Enterprise 'account_avatax' is not installed — "
                        "no FG-05 expectation can be evaluated.")
        print(f"{BAD} account_avatax NOT installed")
        _summary(problems, warnings)
        return 1
    print(f"{OK} account_avatax installed (account.move.is_avatax present)")

    installed = {m["name"] for m in rpc.search_read(
        "ir.module.module",
        [("name", "in", ["account_avatax", "account_avatax_sale",
                         "mmg_account_avatax_enhancement"]),
         ("state", "=", "installed")], ["name"])}
    for mod in ("account_avatax_sale", "mmg_account_avatax_enhancement"):
        if mod in installed:
            print(f"{OK} {mod} installed")
        else:
            problems.append(f"module {mod!r} is not installed")
            print(f"{BAD} {mod} NOT installed")

    # ------------------------------------------------- 4. system rights
    fields = rpc.call("res.company", "fields_get",
                      ["avalara_api_id", "avalara_api_key"],
                      attributes=["type"])
    creds_readable = "avalara_api_key" in fields
    if creds_readable:
        print(f"{OK} credential fields readable (user is in base.group_system)")
    else:
        problems.append(
            f"{env.username!r} is NOT in base.group_system, so "
            f"res.company.avalara_api_id / avalara_api_key are invisible. "
            f"TC-DAT-017 will report them 'not set' and TC-TAX-017 will BLOCK.")
        print(f"{BAD} credential fields NOT readable — user lacks "
              f"base.group_system")

    # ------------------------------------------------------- 5. company setup
    company_id = _m2o(rpc.call("res.users", "read", [rpc.uid],
                               fields=["company_id"])[0]["company_id"])
    wanted = ["name", "setting_account_avatax", "avalara_environment",
              "avalara_commit", "avalara_api_id", "avalara_api_key",
              "parent_id"]
    present = rpc.call("res.company", "fields_get", wanted, attributes=["type"])
    company = rpc.read("res.company", [company_id],
                       [f for f in wanted if f in present])[0]
    print(f"\ncompany: {company.get('name')!r} (id {company_id})")

    environment = company.get("avalara_environment") or ""
    if environment == "sandbox":
        print(f"{OK} Avalara Environment = 'sandbox'")
    elif environment == "production":
        problems.append(
            "Avalara Environment reads 'production'. The suite BLOCKS rather "
            "than compute tax against a live Avalara account — it would file "
            "REAL tax documents. Point the test company at the SANDBOX.")
        print(f"{BAD} Avalara Environment = 'production' — suite will BLOCK")
    else:
        problems.append(f"Avalara Environment reads {environment or 'empty'!r},"
                        f" not 'sandbox'")
        print(f"{BAD} Avalara Environment = {environment or 'empty'!r}")

    if _m2o(company.get("parent_id")):
        warnings.append(
            "this company has a parent. account_avatax resolves credentials "
            "UP the parent chain and uses THAT company's environment, so "
            "confirm the credential-holding ancestor is also on the sandbox.")
        print(f"{WARN} company has a parent — check the credential ancestor")

    if creds_readable:
        for field, label in (("avalara_api_id", "API ID"),
                             ("avalara_api_key", "API KEY")):
            if company.get(field):
                print(f"{OK} {label} is set")
            else:
                problems.append(f"{label} is empty — the 12 sandbox cases "
                                f"will BLOCK")
                print(f"{BAD} {label} is EMPTY")

    if company.get("setting_account_avatax"):
        print(f"{OK} 'Use AvaTax' is ticked")
    else:
        problems.append(
            "'Use AvaTax' (res.company.setting_account_avatax) is OFF, so no "
            "document computes tax externally. The 12 sandbox cases BLOCK.")
        print(f"{BAD} 'Use AvaTax' is OFF")

    if company.get("avalara_commit"):
        print(f"{OK} 'Commit Transactions' is ticked")
    else:
        warnings.append(
            "'Commit Transactions' (avalara_commit) is OFF. TC-TAX-011 BLOCKS "
            "— its own precondition requires it on. The other 13 are fine.")
        print(f"{WARN} 'Commit Transactions' is OFF — TC-TAX-011 will BLOCK")

    # ------------------------------------------------- 6. fiscal positions
    fps = rpc.search_read(
        "account.fiscal.position", [("is_avatax", "=", True)],
        ["name", "avatax_invoice_account_id", "avatax_refund_account_id"],
        order="id")
    total_fp = rpc.call("account.fiscal.position", "search_count", [])
    if not fps:
        problems.append(
            f"NO fiscal position has 'Use AvaTax API' ticked ({total_fp} exist "
            f"in total). TC-DAT-017 FAILS and the other 13 BLOCK. This is the "
            f"workbook's GATE 3 finding — the flag did not survive the "
            f"upgrade. Fix: tick 'Use AvaTax API' on the AvaTax fiscal "
            f"position and set both its Avatax accounts.")
        print(f"{BAD} 0 of {total_fp} fiscal positions have is_avatax set")
    else:
        print(f"{OK} {len(fps)} of {total_fp} fiscal positions use AvaTax")
        for fp in fps:
            inv, ref = (_m2o(fp.get("avatax_invoice_account_id")),
                        _m2o(fp.get("avatax_refund_account_id")))
            if inv and ref and inv != ref:
                print(f"{OK}   {fp['name']!r}: invoice + refund accounts differ")
            elif not inv or not ref:
                warnings.append(f"fiscal position {fp['name']!r} is missing an "
                                f"Avatax account — TC-TAX-015 will BLOCK")
                print(f"{WARN}   {fp['name']!r}: an Avatax account is missing")
            else:
                warnings.append(f"fiscal position {fp['name']!r} uses the SAME "
                                f"account for invoice and refund — "
                                f"TC-TAX-015 will BLOCK")
                print(f"{WARN}   {fp['name']!r}: invoice == refund account")

    # ---------------------------------------------------- 7. supporting data
    n_categ = rpc.call("product.avatax.category", "search_count", [])
    if n_categ >= 2:
        print(f"{OK} {n_categ} product.avatax.category records")
    else:
        warnings.append(f"only {n_categ} product.avatax.category record(s) — "
                        f"TC-TAX-014 and TC-TAX-016 need two with different "
                        f"treatments and will BLOCK")
        print(f"{WARN} only {n_categ} AvaTax category record(s)")

    n_exempt = rpc.call("avatax.exemption", "search_count",
                        [("company_id", "=", company_id)])
    if n_exempt:
        print(f"{OK} {n_exempt} avatax.exemption record(s) for this company")
    else:
        warnings.append("no avatax.exemption records for this company — "
                        "TC-TAX-013 will BLOCK. Use 'Sync Parameters' in the "
                        "AvaTax settings block to pull the exemption list.")
        print(f"{WARN} no avatax.exemption records — TC-TAX-013 will BLOCK")

    return _summary(problems, warnings)


def _summary(problems, warnings) -> int:
    print()
    print("=" * 68)
    if problems:
        print(f"NOT READY — {len(problems)} blocking problem(s):")
        for i, p in enumerate(problems, 1):
            print(f"  {i}. {p}")
    else:
        print("READY — the 14 FG-05 cases will run against the Avalara sandbox.")
    if warnings:
        print(f"\n{len(warnings)} warning(s) — some cases will BLOCK:")
        for i, w in enumerate(warnings, 1):
            print(f"  {i}. {w}")
    print("=" * 68)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
