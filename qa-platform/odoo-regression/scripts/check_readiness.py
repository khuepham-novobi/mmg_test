"""Readiness pre-flight for the MMG regression suites — FG-05 … FG-08.

Answers one question: *if I press Run right now, what will happen?* Every
condition below is one a suite itself gates on, so a clean report here means
the tests will exercise real behaviour instead of reporting BLOCKED.

    venv\\Scripts\\python.exe scripts\\check_readiness.py             # all four
    venv\\Scripts\\python.exe scripts\\check_readiness.py FG-06 FG-07 # a subset

Read-only. It creates nothing, writes nothing, calls no model method that is
not a read, and never reaches Avalara, Shopify or any other external system.
The only host it talks to is the target Odoo server it was asked about —
plus, when it detects it is running inside a container, one DNS lookup of the
compose service name, so the remedy it prints is one it has confirmed works.

Exit code 0 = ready, 1 = something would block or fail.
"""
from __future__ import annotations

import os
import re
import socket
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from adapters import get_adapter  # noqa: E402
from adapters.base import OdooRPCError  # noqa: E402
from backend.config import load_environments  # noqa: E402

# A console under a legacy code page cannot encode the em dashes this report
# is written with. errors="replace" keeps a readability nicety from ever
# becoming a UnicodeEncodeError traceback in front of a tester.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):  # pragma: no cover - non-reconfigurable stream
    pass

OK, WARN, BAD = "[ OK ]", "[WARN]", "[FAIL]"
WIDTH = 68

# Ranks order the closing "what to fix, in order" list. Nothing below is
# worth doing before the thing above it: a wrong URL hides an auth problem,
# a missing module hides missing data inside it.
R_CONFIG, R_CONNECT, R_MODULE, R_DATA = 10, 20, 30, 40

GROUPS = {
    "FG-05": "AvaTax Tax Calculation",
    "FG-06": "Customer & Vendor Deposits",
    "FG-07": "Invoicing, Payments & Accounting Documents",
    "FG-08": "E-commerce Channel Management",
}


# --------------------------------------------------------------- reporting
class SectionAbort(Exception):
    """Stop one group's section — its remaining checks cannot mean anything."""


class Report:
    """Collects the [ OK ] / [WARN] / [FAIL] stream into a per-group verdict."""

    def __init__(self):
        self.group = "ENV"
        self.order: list[str] = []
        self.checked: dict[str, bool] = {}
        self.blocking: dict[str, int] = {}
        self.warned: dict[str, int] = {}
        self.problems: list[dict] = []
        self.warnings: list[dict] = []
        self.defects: list[dict] = []

    # -- structure -------------------------------------------------------
    def heading(self, key: str, title: str) -> None:
        self.group = key
        self.order.append(key)
        self.checked[key] = True
        self.blocking.setdefault(key, 0)
        self.warned.setdefault(key, 0)
        print()
        print(f"== {key} - {title} ".ljust(WIDTH, "="))

    def not_checked(self, key: str, why: str) -> None:
        if key not in self.order:
            self.order.append(key)
        self.checked[key] = False
        self.blocking.setdefault(key, 0)
        self.warned.setdefault(key, 0)
        self.note = why

    # -- lines -----------------------------------------------------------
    def ok(self, line: str) -> None:
        print(f"{OK} {line}")

    def info(self, line: str) -> None:
        print(f"       {line}")

    def warn(self, line: str, why: str = "", fix: str = "",
             rank: int = R_DATA) -> None:
        print(f"{WARN} {line}")
        self.warned[self.group] = self.warned.get(self.group, 0) + 1
        self.warnings.append({"group": self.group, "why": why or line,
                              "fix": fix, "rank": rank})

    def bad(self, line: str, why: str = "", fix: str = "",
            rank: int = R_DATA) -> None:
        print(f"{BAD} {line}")
        self.blocking[self.group] = self.blocking.get(self.group, 0) + 1
        self.problems.append({"group": self.group, "why": why or line,
                              "fix": fix, "rank": rank})

    def defect(self, line: str, detail: str) -> None:
        """A known PRODUCT defect. Reported, never fixed by this script, and
        never a tester action — it belongs to the dev team."""
        print(f"{WARN} PRODUCT DEFECT — {line}")
        self.warned[self.group] = self.warned.get(self.group, 0) + 1
        self.defects.append({"group": self.group, "what": line,
                             "detail": detail})

    # -- flow ------------------------------------------------------------
    def abort(self, line: str, why: str = "", fix: str = "",
              rank: int = R_MODULE) -> None:
        self.bad(line, why, fix, rank)
        raise SectionAbort


def _m2o(value):
    return value[0] if isinstance(value, (list, tuple)) else (value or None)


# ------------------------------------------------------ container awareness
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}

# The service names docker-compose.yml reaches on the external network
# "mmg_default" (its own comment: odoo19:8069, odoo15:8069, db:5432).
SERVICE_URL = {"odoo19": "http://odoo19:8069", "odoo15": "http://odoo15:8069"}
SERVICE_NAMES = {"odoo19", "odoo15", "db", "mmg-qa", "host.docker.internal"}
PG_SERVICE = "db"


def _read_text(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def detect_container() -> tuple[bool, list[str]]:
    """Are we running inside a Linux container?

    Signals, in the order they are trusted:

    1. ``/.dockerenv``. The Docker daemon creates this file in every container
       it starts. It comes from the RUNTIME, not from the image, so it is
       there on ``python:3.12-slim-bookworm`` — this platform's base image
       (``Dockerfile:3``) — exactly as on any other. Podman's equivalent is
       ``/run/.containerenv``, and systemd/podman also export ``$container``.
    2. ``/proc/self/mountinfo``. Inside Docker the container's own
       ``/etc/hostname``, ``/etc/hosts`` and ``/etc/resolv.conf`` are bind
       mounts out of ``/var/lib/docker/containers/<id>/``, and the root is an
       overlay. Survives a stripped image.
    3. ``/proc/1/cgroup``. Best effort ONLY, deliberately last: on a cgroup-v2
       host with Docker's default private cgroup namespace this reads a bare
       ``0::/`` and names no runtime at all, so its silence proves nothing.

    On Windows (or any non-POSIX host) none of this exists and the answer is
    a flat no, which is the correct reading for the bare-metal workstation
    the suites are also run from.
    """
    if os.name != "posix":
        return False, []
    signals = []
    if Path("/.dockerenv").exists():
        signals.append("/.dockerenv is present (Docker creates it in every "
                       "container it starts)")
    if Path("/run/.containerenv").exists():
        signals.append("/run/.containerenv is present (Podman)")
    if os.environ.get("container"):
        signals.append(f"$container={os.environ['container']!r}")
    mountinfo = _read_text("/proc/self/mountinfo")
    if re.search(r"/var/lib/docker/|/docker/containers/|/containerd/",
                 mountinfo):
        signals.append("/proc/self/mountinfo shows container bind mounts")
    cgroup = _read_text("/proc/1/cgroup")
    if re.search(r"docker|containerd|kubepods|lxc|/ecs/", cgroup):
        signals.append("/proc/1/cgroup names a container runtime")
    return bool(signals), signals


def _resolves(hostname: str) -> bool:
    try:
        socket.getaddrinfo(hostname, None)
        return True
    except OSError:
        return False


def check_runtime(rep: Report, envs: dict) -> None:
    """Where is this process, and does the config make sense from there?

    This is the check that costs a tester a whole afternoon when it is
    missing. ``config/environments.yaml`` defaults ODOO19_URL to
    ``http://localhost:8076``, which is right on the Windows host and wrong
    inside the container: there, "localhost" is the CONTAINER — nothing
    answers on it, and every case in all four groups reports
    ``BLOCKED / ENVIRONMENT`` before its first step runs.
    """
    rep.heading("ENV", "runtime & configuration")
    inside, signals = detect_container()
    if inside:
        rep.ok(f"running INSIDE a container — {signals[0]}")
        for extra in signals[1:]:
            rep.info(f"also: {extra}")
        rep.info("'localhost' here is the CONTAINER, not the Windows host")
    else:
        rep.ok("running on the host — 'localhost' means this machine's own "
               "ports (no container signal found)")

    for key in ("odoo19", "odoo15"):
        env = envs.get(key)
        if env is None:
            continue
        _check_url(rep, env, inside, blocking=(key == "odoo19"))
        _check_pg_host(rep, env, inside)

    if inside:
        target = urlsplit((envs.get("odoo19") or envs["odoo15"]).base_url)
        name = (target.hostname or "").lower()
        if name in SERVICE_NAMES and name != "host.docker.internal":
            if _resolves(name):
                rep.ok(f"service name {name!r} resolves — this container is on "
                       f"the mmg_default network")
            else:
                rep.bad(
                    f"service name {name!r} does NOT resolve from this "
                    f"container",
                    why=(f"ODOO19_URL names {name!r} but DNS does not resolve "
                         f"it, so the container is not on the network that "
                         f"publishes it. docker-compose.yml joins the EXTERNAL "
                         f"network 'mmg_default'; if the instances under test "
                         f"were started by a different compose project, that "
                         f"network does not exist or has a different name."),
                    fix=("bring up D:\\project\\mmg\\docker\\docker-compose.yml "
                         "first (it owns the mmg_default network), then "
                         "re-create this container so it joins it"),
                    rank=R_CONFIG)


def _check_url(rep: Report, env, inside: bool, blocking: bool) -> None:
    parts = urlsplit(env.base_url)
    host = (parts.hostname or "").lower()
    port = parts.port
    var = f"ODOO{env.version}_URL"

    if inside and host in LOCAL_HOSTS:
        service = SERVICE_URL.get(env.key, "http://odoo19:8069")
        host_url = f"http://host.docker.internal:{port or 8076}"
        why = (
            f"{var} is {env.base_url!r}, but this process is running inside a "
            f"container, where 'localhost' is the CONTAINER — not the machine "
            f"the Odoo server is on. Nothing listens there, so every case "
            f"reports BLOCKED / ENVIRONMENT in the runner's preflight before a "
            f"single test body executes.")
        fix = (f"in config/local.yaml set  {var}: {service}   (the instance "
               f"under test, by service name on the external network "
               f"'mmg_default' — see the networks.mmg comment in "
               f"docker-compose.yml), or  {var}: {host_url}   to reach a "
               f"server running on the Windows host (docker-compose.yml "
               f"already maps extra_hosts host.docker.internal:host-gateway)")
        if blocking:
            rep.bad(f"{var} points at {host!r} from inside a container",
                    why=why, fix=fix, rank=R_CONFIG)
        else:
            rep.warn(f"{var} points at {host!r} from inside a container "
                     f"(only FG-01..FG-04 use it)", why=why, fix=fix,
                     rank=R_CONFIG)
        rep.info(f"use {service}  or  {host_url}")
        return

    if not inside and host in SERVICE_NAMES:
        why = (f"{var} is {env.base_url!r} — a Docker service name — but this "
               f"process is NOT in a container, and the host cannot resolve "
               f"compose service names. Every case would report BLOCKED / "
               f"ENVIRONMENT.")
        fix = (f"in config/local.yaml set {var} back to the port the server "
               f"listens on for the host, e.g. http://localhost:8076 "
               f"(MMG's mmg.conf uses http_port = 8076)")
        if blocking:
            rep.bad(f"{var} names the container service {host!r} but we are on "
                    f"the host", why=why, fix=fix, rank=R_CONFIG)
        else:
            rep.warn(f"{var} names the container service {host!r} but we are "
                     f"on the host (only FG-01..FG-04 use it)", why=why,
                     fix=fix, rank=R_CONFIG)
        return

    rep.ok(f"{var} = {env.base_url} — reachable shape for this runtime")


def _check_pg_host(rep: Report, env, inside: bool) -> None:
    """Direct SQL is optional; a WRONG host is not.

    An unset pg_host is a documented, handled state — framework/sqltool.py
    raises SqlUnavailable and the affected cases report BLOCKED with a reason.
    A pg_host of 'localhost' read from inside a container is different: it
    points at the container's own (empty) port 5432 and fails as a connection
    error, which reads like an outage rather than a config mistake.
    """
    var = f"ODOO{env.version}_PG_HOST"
    host = (env.pg_host or "").strip().lower()
    if not host:
        return  # unset is legitimate — the SQL-backed cases block by design
    if inside and host in LOCAL_HOSTS:
        rep.bad(
            f"{var} = {host!r} from inside a container",
            why=(f"{var} is {host!r}, which inside the container is the "
                 f"CONTAINER's own port {env.pg_port} — there is no PostgreSQL "
                 f"there. The DATA_RECONCILIATION reads (FG-06's TC-DAT-019 "
                 f"stored-value probe among them) fail as a connection error "
                 f"instead of degrading cleanly."),
            fix=(f"in config/local.yaml set  {var}: {PG_SERVICE}  with "
                 f"ODOO{env.version}_PG_PORT: 5432 — Postgres answers on the "
                 f"mmg_default network by service name (docker-compose.yml, "
                 f"networks.mmg comment) — or host.docker.internal for a "
                 f"server on the Windows host"),
            rank=R_CONFIG)
        return
    if not inside and host == PG_SERVICE:
        rep.bad(
            f"{var} = {host!r} but we are on the host",
            why=(f"{var} names the Docker service {host!r}, which the Windows "
                 f"host cannot resolve."),
            fix=(f"in config/local.yaml set {var} to localhost and "
                 f"ODOO{env.version}_PG_PORT to the port the host publishes"),
            rank=R_CONFIG)
        return
    rep.ok(f"{var} = {host} (port {env.pg_port}) — direct SQL configured")


# ------------------------------------------------------------- the target
class Target:
    """One authenticated Odoo connection, plus the lookups every group needs.

    Module states and the acting company are fetched once and shared: four
    group sections asking the same three questions is four round trips a
    tester waits through for no reason.
    """

    def __init__(self, env, rpc):
        self.env = env
        self.rpc = rpc
        self.version = ""
        self._modules: dict[str, str] = {}
        self._company: dict | None = None

    # -- modules ---------------------------------------------------------
    def module_states(self, names) -> dict[str, str]:
        missing = [n for n in names if n not in self._modules]
        if missing:
            try:
                rows = self.rpc.search_read(
                    "ir.module.module", [("name", "in", missing)],
                    ["name", "state"])
            except OdooRPCError:
                rows = []
            found = {r["name"]: (r.get("state") or "") for r in rows}
            for name in missing:
                self._modules[name] = found.get(name, "")
        return {n: self._modules[n] for n in names}

    def installed(self, name: str) -> bool:
        return self.module_states([name])[name] == "installed"

    # -- company ---------------------------------------------------------
    def company(self) -> dict:
        if self._company is None:
            row = self.rpc.call("res.users", "read", [self.rpc.uid],
                                fields=["company_id"])[0]
            company_id = _m2o(row["company_id"])
            name = self.rpc.read("res.company", [company_id],
                                 ["name"])[0]["name"]
            self._company = {"id": company_id, "name": name}
        return self._company

    # -- introspection ---------------------------------------------------
    def fields_get(self, model: str, names=None, attributes=None) -> dict:
        args = [names] if names is not None else []
        kwargs = {"attributes": attributes} if attributes else {}
        return self.rpc.call(model, "fields_get", *args, **kwargs)

    def field_exists(self, model: str, field: str) -> bool:
        try:
            return self.rpc.field_exists(model, field)
        except OdooRPCError:
            return False

    def count(self, model: str, domain) -> int:
        return self.rpc.call(model, "search_count", domain)


def connect(rep: Report, env, selected) -> Target | None:
    """Reach and authenticate, or explain why nothing else can be checked."""
    rep.heading("CONN", f"{env.name} @ {env.base_url}")
    rpc = get_adapter(env).rpc
    target = Target(env, rpc)
    groups = ", ".join(selected)

    try:
        version = rpc.server_version()
    except Exception as exc:  # noqa: BLE001 — urllib raises many shapes
        rep.bad(
            f"server UNREACHABLE at {env.base_url}: {exc}",
            why=(f"nothing answers at {env.base_url}, so every case in "
                 f"{groups} reports BLOCKED / ENVIRONMENT in the runner's "
                 f"preflight — before a single test body executes. That is the "
                 f"platform refusing to invent a verdict, not a broken test."),
            fix=("start the Odoo 19 server, or correct ODOO19_URL in "
                 "config/local.yaml (see the ENV section above for the value "
                 "this runtime needs)"),
            rank=R_CONNECT)
        return None

    target.version = version
    rep.ok(f"server reachable — version {version}")
    if not version.startswith("19"):
        rep.bad(
            f"not an Odoo 19 server (reports {version!r})",
            why=(f"the server reports version {version!r}, not 19.x. "
                 f"{groups} are Odoo-19-only — every case reports BLOCKED."),
            fix="point ODOO19_URL / ODOO19_DB at the v19 QA clone",
            rank=R_CONNECT)
        return None

    try:
        uid = rpc.uid
    except OdooRPCError as exc:
        rep.bad(
            f"authentication FAILED for {env.username!r}: {exc}",
            why=(f"authentication failed for {env.username!r} on db "
                 f"{env.db!r}. On a restored production database res.users id "
                 f"1 is __system__ and INACTIVE, so the real administrator is "
                 f"a named person."),
            fix=("find the live administrator — SELECT id, login, active FROM "
                 "res_users WHERE id IN (1,2); — then set ODOO19_USERNAME / "
                 "ODOO19_PASSWORD in config/local.yaml"),
            rank=R_CONNECT)
        return None
    rep.ok(f"authenticated as {env.username!r} (uid {uid})")

    company = target.company()
    rep.ok(f"acting company: {company['name']!r} (id {company['id']}) "
           f"on db {env.db!r}")
    return target


# ---------------------------------------------------------------- FG-05
def check_fg05(rep: Report, t: Target) -> None:
    """AvaTax. Unchanged in substance from scripts/check_fg05_readiness.py —
    the wrapper still calls exactly this."""
    rpc = t.rpc
    company_id = t.company()["id"]

    # ------------------------------------------------------------ modules
    if not t.field_exists("account.move", "is_avatax"):
        rep.abort(
            "account_avatax NOT installed",
            why=("Odoo Enterprise 'account_avatax' is not installed — no FG-05 "
                 "expectation can be evaluated."),
            fix="install account_avatax from the Enterprise addons path")
    rep.ok("account_avatax installed (account.move.is_avatax present)")

    for mod in ("account_avatax_sale", "mmg_account_avatax_enhancement"):
        if t.installed(mod):
            rep.ok(f"{mod} installed")
        else:
            rep.bad(f"{mod} NOT installed",
                    why=f"module {mod!r} is not installed",
                    fix=f"install {mod}", rank=R_MODULE)

    # ------------------------------------------------------ system rights
    fields = t.fields_get("res.company", ["avalara_api_id", "avalara_api_key"],
                          attributes=["type"])
    creds_readable = "avalara_api_key" in fields
    if creds_readable:
        rep.ok("credential fields readable (user is in base.group_system)")
    else:
        rep.bad(
            "credential fields NOT readable — user lacks base.group_system",
            why=(f"{t.env.username!r} is NOT in base.group_system, so "
                 f"res.company.avalara_api_id / avalara_api_key are invisible. "
                 f"TC-DAT-017 will report them 'not set' and TC-TAX-017 will "
                 f"BLOCK."),
            fix=(f"add {t.env.username!r} to Settings > Users > "
                 f"Administration: Settings (base.group_system), or point "
                 f"ODOO19_USERNAME at a user who has it"),
            rank=R_CONNECT)

    # ------------------------------------------------------ company setup
    wanted = ["name", "setting_account_avatax", "avalara_environment",
              "avalara_commit", "avalara_api_id", "avalara_api_key",
              "parent_id"]
    present = t.fields_get("res.company", wanted, attributes=["type"])
    company = rpc.read("res.company", [company_id],
                       [f for f in wanted if f in present])[0]

    environment = company.get("avalara_environment") or ""
    if environment == "sandbox":
        rep.ok("Avalara Environment = 'sandbox'")
    elif environment == "production":
        rep.bad(
            "Avalara Environment = 'production' — suite will BLOCK",
            why=("Avalara Environment reads 'production'. The suite BLOCKS "
                 "rather than compute tax against a live Avalara account — it "
                 "would file REAL tax documents."),
            fix="point the test company at the Avalara SANDBOX")
    else:
        rep.bad(
            f"Avalara Environment = {environment or 'empty'!r}",
            why=(f"Avalara Environment reads {environment or 'empty'!r}, not "
                 f"'sandbox'"),
            fix="set Avalara Environment to 'sandbox' on the test company")

    if _m2o(company.get("parent_id")):
        rep.warn(
            "company has a parent — check the credential ancestor",
            why=("this company has a parent. account_avatax resolves "
                 "credentials UP the parent chain and uses THAT company's "
                 "environment, so confirm the credential-holding ancestor is "
                 "also on the sandbox."))

    if creds_readable:
        for field, label in (("avalara_api_id", "API ID"),
                             ("avalara_api_key", "API KEY")):
            if company.get(field):
                rep.ok(f"{label} is set")
            else:
                rep.bad(f"{label} is EMPTY",
                        why=f"{label} is empty — the 12 sandbox cases BLOCK",
                        fix=f"paste the sandbox {label} into the company's "
                            f"AvaTax settings")

    if company.get("setting_account_avatax"):
        rep.ok("'Use AvaTax' is ticked")
    else:
        rep.bad(
            "'Use AvaTax' is OFF",
            why=("'Use AvaTax' (res.company.setting_account_avatax) is OFF, so "
                 "no document computes tax externally. The 12 sandbox cases "
                 "BLOCK."),
            fix=("tick 'Use AvaTax' on the company — a BUSINESS decision on "
                 "the migrated database; ask before changing it"))

    if company.get("avalara_commit"):
        rep.ok("'Commit Transactions' is ticked")
    else:
        rep.warn(
            "'Commit Transactions' is OFF — TC-TAX-011 will BLOCK",
            why=("'Commit Transactions' (avalara_commit) is OFF. TC-TAX-011 "
                 "BLOCKS — its own precondition requires it on. The other 13 "
                 "are fine."),
            fix="tick 'Commit Transactions' if TC-TAX-011 is in scope")

    # --------------------------------------------------- fiscal positions
    fps = rpc.search_read(
        "account.fiscal.position", [("is_avatax", "=", True)],
        ["name", "avatax_invoice_account_id", "avatax_refund_account_id"],
        order="id")
    total_fp = t.count("account.fiscal.position", [])
    if not fps:
        rep.bad(
            f"0 of {total_fp} fiscal positions have is_avatax set",
            why=(f"NO fiscal position has 'Use AvaTax API' ticked ({total_fp} "
                 f"exist in total). TC-DAT-017 FAILS and the other 13 BLOCK. "
                 f"This is the workbook's GATE 3 finding — the flag did not "
                 f"survive the upgrade."),
            fix=("tick 'Use AvaTax API' on the AvaTax fiscal position and set "
                 "BOTH its Avatax accounts to DIFFERENT accounts"))
    else:
        rep.ok(f"{len(fps)} of {total_fp} fiscal positions use AvaTax")
        for fp in fps:
            inv = _m2o(fp.get("avatax_invoice_account_id"))
            ref = _m2o(fp.get("avatax_refund_account_id"))
            if inv and ref and inv != ref:
                rep.ok(f"  {fp['name']!r}: invoice + refund accounts differ")
            elif not inv or not ref:
                rep.warn(
                    f"  {fp['name']!r}: an Avatax account is missing",
                    why=(f"fiscal position {fp['name']!r} is missing an Avatax "
                         f"account — TC-TAX-015 will BLOCK"),
                    fix=(f"set both Avatax accounts on fiscal position "
                         f"{fp['name']!r}"))
            else:
                rep.warn(
                    f"  {fp['name']!r}: invoice == refund account",
                    why=(f"fiscal position {fp['name']!r} uses the SAME account "
                         f"for invoice and refund — TC-TAX-015 will BLOCK"),
                    fix=(f"give fiscal position {fp['name']!r} DIFFERENT "
                         f"invoice and refund Avatax accounts"))

    # ------------------------------------------------------ support data
    n_categ = t.count("product.avatax.category", [])
    if n_categ >= 2:
        rep.ok(f"{n_categ} product.avatax.category records")
    else:
        rep.warn(
            f"only {n_categ} AvaTax category record(s)",
            why=(f"only {n_categ} product.avatax.category record(s) — "
                 f"TC-TAX-014 and TC-TAX-016 need two with different "
                 f"treatments and will BLOCK"),
            fix="use 'Sync Parameters' in the AvaTax settings block")

    n_exempt = t.count("avatax.exemption", [("company_id", "=", company_id)])
    if n_exempt:
        rep.ok(f"{n_exempt} avatax.exemption record(s) for this company")
    else:
        rep.warn(
            "no avatax.exemption records — TC-TAX-013 will BLOCK",
            why=("no avatax.exemption records for this company — TC-TAX-013 "
                 "will BLOCK."),
            fix=("use 'Sync Parameters' in the AvaTax settings block to pull "
                 "the exemption list"))


# ---------------------------------------------------------------- FG-06
# field -> where it is declared on staging_19, so a defect line names the one
# line a developer has to open.
DEPOSIT_FIELDS = {
    "property_account_customer_deposit_id":
        "account_partner_deposit/models/res_partner.py:7-15 (domain at :13)",
    "property_account_vendor_deposit_id":
        "account_partner_deposit/models/res_partner.py:17-25 (domain at :23)",
}


def check_fg06(rep: Report, t: Target) -> None:
    """Deposits. The one thing worth knowing before pressing Run is whether
    the MS-001 ir.property -> JSONB migration actually left any defaults
    behind: without them TC-DAT-019 fails and every deposit whose contact has
    no override cannot be created at all."""
    rpc = t.rpc
    company = t.company()

    if not t.installed("account_partner_deposit"):
        rep.abort(
            "account_partner_deposit NOT installed",
            why=("'account_partner_deposit' is not installed, so no FG-06 "
                 "expectation exists on this database — all 15 cases BLOCK."),
            fix="install account_partner_deposit from the MMG v19 addons path")
    rep.ok("account_partner_deposit installed")

    if t.installed("sale_partner_deposit"):
        rep.ok("sale_partner_deposit installed")
    else:
        rep.bad(
            "sale_partner_deposit NOT installed",
            why=("'sale_partner_deposit' is not installed. Seven of the eleven "
                 "FG-06 test files gate on it (require_sale_deposit: "
                 "sale.order.deposit_total and the order.make.deposit wizard) "
                 "and BLOCK without it."),
            fix="install sale_partner_deposit from the MMG v19 addons path",
            rank=R_MODULE)

    # -------------------------------------------- ir.default deposit rows
    # The company-dependent fallback lives in ir.default rows, not in an
    # ir.property table any more. ir.default._get_model_defaults is private
    # and unreachable over RPC, so the rows are read directly — the same
    # query tests/fg06/common.py uses.
    for field_name in DEPOSIT_FIELDS:
        try:
            rows = rpc.search_read(
                "ir.default",
                [("field_id.model", "=", "res.partner"),
                 ("field_id.name", "=", field_name),
                 ("user_id", "=", False),
                 ("condition", "=", False),
                 ("company_id", "in", [company["id"], False])],
                ["json_value", "company_id"], order="id")
        except OdooRPCError as exc:
            rep.warn(f"could not read ir.default for {field_name}: {exc}",
                     why=(f"the ir.default rows behind {field_name} could not "
                          f"be read ({exc}), so the MS-001 migration state is "
                          f"unknown"))
            continue

        scoped = [r for r in rows if _m2o(r.get("company_id")) == company["id"]]
        if rows:
            where = ("this company" if scoped
                     else "the GLOBAL scope only (company_id = NULL)")
            rep.ok(f"{len(rows)} ir.default row(s) for res.partner."
                   f"{field_name} — {where}")
            if not scoped:
                rep.warn(
                    f"  {field_name} has no COMPANY-scoped default",
                    why=(f"res.partner.{field_name} has only a global "
                         f"ir.default row. It still resolves, but a "
                         f"multi-company database gets one account for every "
                         f"company — confirm that is intended."))
        else:
            rep.bad(
                f"ZERO ir.default rows for res.partner.{field_name}",
                why=(f"there is NO company default for res.partner."
                     f"{field_name} on company {company['name']!r} (id "
                     f"{company['id']}). That means the MS-001 ir.property -> "
                     f"JSONB migration never ran for this side: v19 stores the "
                     f"company-dependent fallback as ir.default rows, and "
                     f"account_partner_deposit/models/res_company.py:165-181 "
                     f"(create_or_update_deposit_property) is the ONLY code "
                     f"that writes them. Consequences: TC-DAT-019 FAILS, and "
                     f"account.payment.create raises "
                     f"ValidationError('Deposit account has not been set') for "
                     f"any deposit whose contact carries no override "
                     f"(account_partner_deposit/models/account_payment.py:63-68)"
                     f"."),
                fix=("run env['res.company'].search([('parent_id','=',False),"
                     "('chart_template','!=',False)]).init_deposit_accounts() "
                     "once — it creates the accounts and calls "
                     "create_or_update_deposit_property for each company. "
                     "Setting the two accounts is a BUSINESS decision on a "
                     "migrated database: ask before changing it"),
                rank=R_DATA)

    # ---------------------------------------------------- product defects
    try:
        meta = t.fields_get("res.partner", list(DEPOSIT_FIELDS),
                            attributes=["string", "domain", "type"])
    except OdooRPCError as exc:
        rep.warn(f"could not read res.partner fields_get: {exc}")
        meta = {}

    for field_name in DEPOSIT_FIELDS:
        info = meta.get(field_name)
        if info is None:
            rep.bad(
                f"res.partner.{field_name} is MISSING",
                why=(f"res.partner.{field_name} does not exist — a partial "
                     f"install; the module's res_partner.py did not load. "
                     f"require_v19 BLOCKS every FG-06 case."),
                fix="reinstall/upgrade account_partner_deposit",
                rank=R_MODULE)
            continue
        domain = str(info.get("domain") or "")
        if "deprecated" in domain:
            rep.defect(
                f"res.partner.{field_name} domain still filters on "
                f"'deprecated'",
                detail=(f"the field's domain is {domain} — but Odoo 19 REMOVED "
                        f"account.account.deprecated (v19 declares 'active' "
                        f"instead; the only survivor is dead code at "
                        f"addons/account/models/account_account.py:1075). Any "
                        f"UI that evaluates this domain raises 'Invalid field "
                        f"account.account.deprecated in domain'. Source: "
                        f"{DEPOSIT_FIELDS[field_name]}. Fix is to drop the "
                        f"('deprecated','=',False) leaf, or replace it with "
                        f"('active','=',True)."))
        else:
            rep.ok(f"res.partner.{field_name} domain is v19-clean")

    if t.field_exists("res.partner", "total_deposit"):
        rep.defect(
            "res.partner._compute_total_deposit reads aml.blocked, removed in "
            "v19",
            detail=("res.partner.total_deposit is present, and its compute "
                    "skips lines with `not aml.blocked` — "
                    "account_partner_deposit/models/res_partner.py:61. "
                    "account.move.line.blocked does not exist in Odoo 19 "
                    "(no such field anywhere in "
                    "D:/Projects/odoo-19.0/addons/account/models/"
                    "account_move_line.py), so every read of total_deposit "
                    "raises AttributeError. Fix is to drop the blocked test "
                    "from the loop."))
    else:
        rep.ok("res.partner.total_deposit is not exposed to this user "
               "(groups=account.group_account_readonly/invoice) — the "
               "aml.blocked defect cannot be probed from here")


# ---------------------------------------------------------------- FG-07
def check_fg07(rep: Report, t: Target) -> None:
    """Invoicing & payments. The blocker that costs a whole case is the NULL
    batch payment sequence: it kills the Pay pop-up for any multi-invoice
    customer payment, which is exactly what TC-INV-008 does."""
    rpc = t.rpc
    company = t.company()

    # ------------------------------------------------------------ modules
    if t.installed("mmg_account"):
        rep.ok("mmg_account installed — it owns the printed invoice layout")
    else:
        rep.bad(
            "mmg_account NOT installed",
            why=("'mmg_account' is not installed, so none of the nine layout "
                 "changes the workbook checks can be present and the invoice "
                 "prints as a stock Odoo document. The three PDF cases "
                 "BLOCK."),
            fix="install mmg_account from the MMG v19 addons path",
            rank=R_MODULE)

    template_state = t.module_states(["mmg_change_invoice_template"])[
        "mmg_change_invoice_template"]
    if not template_state:
        rep.ok("mmg_change_invoice_template absent — EXPECTED, not a gap "
               "(decision D1: mmg_account ABSORBED it in the v19 port; see "
               "mmg_account/__manifest__.py)")
    elif template_state == "installed":
        rep.warn(
            "mmg_change_invoice_template is INSTALLED — unexpected on v19",
            why=("decision D1 folded mmg_change_invoice_template into "
                 "mmg_account for the v19 port (mmg_account/__manifest__.py: "
                 "'Absorbs mmg_change_invoice_template as of the v19 "
                 "upgrade'), and the consolidated layout lives in "
                 "mmg_account/report/report_invoice.xml. A surviving copy on "
                 "this database means TWO modules inherit the invoice report "
                 "and the printed result may be either one."),
            fix=("confirm which module owns report_invoice_document on this "
                 "database before trusting the three PDF cases"),
            rank=R_MODULE)
    else:
        rep.ok(f"mmg_change_invoice_template present but {template_state!r} "
               f"(not installed) — consistent with decision D1")

    # -------------------------------------------- batch payment sequence
    if not t.field_exists("res.company", "batch_payment_sequence_id"):
        rep.warn(
            "res.company.batch_payment_sequence_id does not exist",
            why=("res.company.batch_payment_sequence_id is absent, so this "
                 "server is not the v19 'account' module this check was "
                 "written against (addons/account/models/company.py:160)."))
    else:
        row = rpc.read("res.company", [company["id"]],
                       ["batch_payment_sequence_id"])[0]
        sequence = _m2o(row.get("batch_payment_sequence_id"))
        if sequence:
            rep.ok(f"batch_payment_sequence_id is set (ir.sequence id "
                   f"{sequence}) — the Pay pop-up can build a reference")
        else:
            rep.bad(
                "res.company.batch_payment_sequence_id is NOT SET — "
                "TC-INV-008 will die",
                why=("res.company.batch_payment_sequence_id is NULL on "
                     f"{company['name']!r}, and Odoo 19 dereferences it the "
                     "moment a customer pays TWO OR MORE invoices at once. "
                     "account.payment.register._get_communication falls "
                     "through to company.get_next_batch_payment_communication()"
                     " (addons/account/wizard/account_payment_register.py:"
                     "176-190), which calls .next_by_id() on an EMPTY "
                     "ir.sequence recordset "
                     "(addons/account/models/company.py:303-309); ir.sequence "
                     "then issues 'SELECT number_next ... WHERE id=%s FOR "
                     "UPDATE NOWAIT' with id=False and PostgreSQL rejects it "
                     "with a type error. CAUSE: the sequence is created by the "
                     "'account' post-init hook "
                     "(addons/account/__init__.py:13-24), and a post-init hook "
                     "does not run on an UPGRADED database — the column stayed "
                     "NULL across v15 -> v19. This is a database-state finding, "
                     "not a broken test."),
                fix=("run env['res.company'].search([('batch_payment_sequence_"
                     "id','=',False)])._create_batch_payment_sequence() once — "
                     "EVERY company needs it, not only the acting one"),
                rank=R_DATA)

    # ------------------------------------------------- payment providers
    try:
        stale = rpc.search_read(
            "payment.provider",
            [("is_published", "=", True), ("state", "=", "disabled")],
            ["name", "state", "is_published", "company_id"],
            context={"active_test": False})
    except OdooRPCError as exc:
        rep.warn(f"could not read payment.provider: {exc}")
        stale = []
    if stale:
        names = ", ".join(repr(p["name"]) for p in stale)
        rep.warn(
            f"{len(stale)} payment provider(s) published while DISABLED: "
            f"{names}",
            why=(f"{len(stale)} payment.provider row(s) carry is_published = "
                 f"True while state = 'disabled' ({names}). That is a stale "
                 f"upgrade row, not an offer: v19 filters on STATE FIRST — "
                 f"_get_compatible_providers searches "
                 f"[('state','in',['enabled','test'])] "
                 f"(addons/payment/models/payment_provider.py:580-583) and "
                 f"only then applies is_published (:586-588) — so the provider "
                 f"is never offered at checkout. Reading the Published flag as "
                 f"'available' would produce a false expectation in TC-INV-010."),
            fix=("leave it alone unless the client wants the provider live; "
                 "action_toggle_is_published clears the flag for a disabled "
                 "provider. Report it as a migration tidy-up, not a defect"))
    else:
        rep.ok("no payment provider is published while disabled")


# ---------------------------------------------------------------- FG-08
# The exact five the suite probes — read from tests/fg08/common.py
# require_connector(), which gates on ONE field per module rather than on the
# ir.module.module row, because a partial install is the failure it exists to
# catch.
FG08_MODULES = (
    ("omni_manage_channel", "status"),
    ("multichannel_product", "auto_create_master_product"),
    ("multichannel_fulfillment", "is_enable_inventory_sync"),
    ("multichannel_order", "kanban_dashboard_period"),
    ("multichannel_shopify", "shopify_hostname"),
)
CHANNEL = "ecommerce.channel"
CHANNEL_FORM = "omni_manage_channel.view_ecommerce_channel_form_settings"


def check_fg08(rep: Report, t: Target) -> None:
    """E-commerce channels."""
    rpc = t.rpc

    if not rpc.model_exists(CHANNEL):
        rep.abort(
            f"model {CHANNEL!r} does not exist",
            why=(f"model {CHANNEL!r} does not exist — the e-commerce connector "
                 f"stack is not installed, so every FG-08 case is about a "
                 f"screen that is not there and all three BLOCK."),
            fix=("install " + ", ".join(m for m, _ in FG08_MODULES)
                 + " on the target database"))
    rep.ok(f"model {CHANNEL!r} exists")

    try:
        fields = t.fields_get(CHANNEL)
    except OdooRPCError as exc:
        rep.abort(f"{CHANNEL}.fields_get failed: {exc}",
                  why=f"{CHANNEL}.fields_get failed ({exc})",
                  fix="check the RPC user's access to ecommerce.channel")

    states = t.module_states([m for m, _ in FG08_MODULES])
    missing = []
    for module, probe in FG08_MODULES:
        if probe in fields:
            rep.ok(f"{module} installed ({CHANNEL}.{probe} present)")
        else:
            missing.append((module, probe))
            rep.bad(
                f"{module} NOT installed ({CHANNEL}.{probe} missing, "
                f"ir.module.module state {states[module] or 'no row'!r})",
                why=(f"the e-commerce connector stack is only partly "
                     f"installed — {module} is absent ({CHANNEL}.{probe} "
                     f"missing). require_connector BLOCKS all three FG-08 "
                     f"cases; their expectations span all five modules."),
                fix=f"install {module}",
                rank=R_MODULE)
    if not missing:
        rep.ok("all five connector modules the suite probes are installed")

    # --------------------------------------------------------- a channel
    try:
        channels = rpc.search_read(
            CHANNEL, [], ["name", "platform", "active"],
            order="id", context={"active_test": False})
    except OdooRPCError as exc:
        rep.warn(f"could not read {CHANNEL}: {exc}")
        channels = []
    if channels:
        live = [c for c in channels if c.get("active")]
        rep.ok(f"{len(channels)} {CHANNEL} record(s), {len(live)} active")
        for chan in channels:
            rep.info(f"{chan['name']!r} platform={chan.get('platform')!r} "
                     f"active={bool(chan.get('active'))}")
        if not live:
            rep.warn(
                "every e-commerce channel is ARCHIVED",
                why=("every ecommerce.channel record is archived, so the "
                     "Manage Stores list is empty for a normal user and "
                     "TC-CHN-001 has no store to walk."),
                fix="unarchive the store under test, or confirm with the "
                    "client that the archive is intended")
    else:
        rep.bad(
            f"no {CHANNEL} records exist",
            why=(f"there is not a single {CHANNEL} record on this database, so "
                 f"TC-CHN-001 (store settings), TC-CHN-005 and TC-CHN-011 have "
                 f"nothing to read and all three BLOCK."),
            fix="restore or create the store under test on this database",
            rank=R_DATA)

    # ---------------------------------------------------- product defect
    if "user_id" not in fields:
        rep.warn(
            f"{CHANNEL}.user_id is not readable by this user",
            why=(f"{CHANNEL}.user_id (Salesperson) is not in fields_get. In "
                 f"v19 a group-restricted field is OMITTED rather than "
                 f"returned empty, so this may be an access artefact — check "
                 f"the RPC user is in omni_manage_channel."
                 f"group_listing_manager."))
        return

    view_id = rpc.ref(CHANNEL_FORM)
    if not view_id:
        rep.warn(f"view {CHANNEL_FORM!r} does not exist — cannot check "
                 f"whether Salesperson is on the form",
                 why=(f"the store settings form {CHANNEL_FORM!r} was not found, "
                      f"so the user_id placement could not be probed"))
        return
    try:
        arch = rpc.call(CHANNEL, "get_view", view_id=view_id,
                        view_type="form")["arch"]
    except (OdooRPCError, KeyError, TypeError) as exc:
        rep.warn(f"could not read the {CHANNEL} form arch: {exc}",
                 why=f"get_view on {CHANNEL_FORM!r} failed ({exc})")
        return

    if re.search(r"<field\b[^>]*\bname=[\"']user_id[\"']", arch):
        rep.ok(f"{CHANNEL}.user_id (Salesperson) IS bound in the store "
               f"settings form")
    else:
        rep.defect(
            f"{CHANNEL}.user_id exists on the model but is on NO view",
            detail=("user_id (Salesperson) was restored on the MODEL by the "
                    "port under FG11-D2 / BC-012 "
                    "(multichannel_order/models/ecommerce_channel.py:44-61) "
                    "but placed on no view: the assembled arch of "
                    f"{CHANNEL_FORM} contains no <field name=\"user_id\"/>. "
                    "v15 carried one on exactly the tab the workbook names — "
                    "novobi-omni-addons/multichannel_order/views/"
                    "omnichannel_dashboard_views.xml:71, inside "
                    "<group name=\"top_left\"> of page "
                    "'order_configuration_page'. Until it is put back the "
                    "field cannot be read or set from the screen at all, so "
                    "TC-CHN-001's 'Salesperson is present on the Order "
                    "Configuration tab and carries the expected user' fails on "
                    "both halves. The fix is a one-line view addition."))


# ---------------------------------------------------------------- driver
CHECKS = {
    "FG-05": check_fg05,
    "FG-06": check_fg06,
    "FG-07": check_fg07,
    "FG-08": check_fg08,
}


def _select(args) -> list[str]:
    """Which groups to check. No argument = all four."""
    wanted = []
    for raw in args:
        key = str(raw).strip().upper().replace("FG", "FG-").replace("--", "-")
        if not key.startswith("FG-"):
            key = "FG-" + key.lstrip("-")
        if key in CHECKS:
            wanted.append(key)
        else:
            print(f"{WARN} ignoring unknown group {raw!r} — known: "
                  f"{', '.join(CHECKS)}")
    return wanted or list(CHECKS)


def main(groups=None) -> int:
    selected = _select(groups if groups is not None else sys.argv[1:])
    rep = Report()

    title = ("readiness — " + " / ".join(selected)) if len(selected) > 1 \
        else f"readiness — {selected[0]} {GROUPS[selected[0]]}"
    print(f"MMG regression platform {title}")
    print("=" * WIDTH)

    try:
        envs = load_environments()
    except Exception as exc:  # noqa: BLE001 — a bad YAML must not traceback
        print(f"{BAD} could not load config/environments.yaml: {exc}")
        print()
        print("  Copy config/local.yaml.example to config/local.yaml and fill")
        print("  in the ODOO19_* block, then run this again.")
        return 1

    env = envs.get("odoo19")
    if env is None:
        print(f"{BAD} no 'odoo19' environment in config/environments.yaml")
        return 1
    print(f"target : {env.base_url}  db={env.db}  user={env.username}")

    check_runtime(rep, envs)

    target = connect(rep, env, selected)
    if target is None:
        for key in selected:
            rep.not_checked(key, "the target could not be reached")
        print()
        print("  Every case in " + ", ".join(selected) + " would report "
              "BLOCKED / ENVIRONMENT.")
        return _summary(rep, selected)

    for key in selected:
        rep.heading(key, GROUPS[key])
        try:
            CHECKS[key](rep, target)
        except SectionAbort:
            rep.info("remaining checks for this group skipped — they cannot "
                     "mean anything until the above is fixed")
        except OdooRPCError as exc:
            rep.bad(f"check aborted: {exc}",
                    why=(f"{key} could not be evaluated — the server refused a "
                         f"read: {exc}"),
                    fix=f"check the RPC user's access rights, then re-run {key}",
                    rank=R_CONNECT)
        except Exception as exc:  # noqa: BLE001 — a surprise is a finding
            rep.bad(f"check aborted: {type(exc).__name__}: {exc}",
                    why=(f"{key} could not be evaluated — the readiness check "
                         f"itself failed with {type(exc).__name__}: {exc}"),
                    fix=f"re-run with only {key} to see where it stops",
                    rank=R_CONNECT)

    return _summary(rep, selected)


def _verdict(rep: Report, key: str) -> str:
    if not rep.checked.get(key, False):
        return "NOT CHECKED"
    if rep.blocking.get(key):
        return "NOT READY"
    if rep.warned.get(key):
        return "READY, with warnings"
    return "READY"


def _summary(rep: Report, selected) -> int:
    print()
    print("=" * WIDTH)
    print("group readiness")
    for key in ["ENV", "CONN"] + list(selected):
        if key not in rep.checked:
            continue
        label = {"ENV": "runtime & configuration",
                 "CONN": "connection"}.get(key, GROUPS.get(key, ""))
        counts = []
        if rep.blocking.get(key):
            counts.append(f"{rep.blocking[key]} blocking")
        if rep.warned.get(key):
            counts.append(f"{rep.warned[key]} warning(s)")
        tail = f"  ({', '.join(counts)})" if counts else ""
        print(f"  {key:<6} {_verdict(rep, key):<21} {label}{tail}")

    print()
    if rep.problems:
        print(f"NOT READY — {len(rep.problems)} blocking problem(s):")
        for i, p in enumerate(rep.problems, 1):
            print(f"  {i}. [{p['group']}] {p['why']}")
    else:
        print("READY — every checked group will run.")

    if rep.warnings:
        print(f"\n{len(rep.warnings)} warning(s) — some cases will BLOCK:")
        for i, w in enumerate(rep.warnings, 1):
            print(f"  {i}. [{w['group']}] {w['why']}")

    if rep.defects:
        print(f"\n{len(rep.defects)} known PRODUCT defect(s) — report them, do "
              f"NOT fix them here:")
        for i, d in enumerate(rep.defects, 1):
            print(f"  {i}. [{d['group']}] {d['what']}")
            print(f"     {d['detail']}")

    # ------------------------------------------------- what to fix, in order
    fixes, seen = [], set()
    for item in sorted(rep.problems, key=lambda p: p["rank"]):
        if item["fix"] and item["fix"] not in seen:
            seen.add(item["fix"])
            fixes.append(("blocking", item["group"], item["fix"]))
    for item in sorted(rep.warnings, key=lambda w: w["rank"]):
        if item["fix"] and item["fix"] not in seen:
            seen.add(item["fix"])
            fixes.append(("optional", item["group"], item["fix"]))

    print()
    if fixes:
        print("what to fix, in order:")
        for i, (kind, group, fix) in enumerate(fixes, 1):
            marker = "" if kind == "blocking" else "  (optional — unblocks "\
                                                   "individual cases)"
            print(f"  {i}. [{group}] {fix}{marker}")
    else:
        print("what to fix, in order: nothing — press Run.")
    if rep.defects:
        print(f"  (the {len(rep.defects)} product defect(s) above are findings "
              f"for the dev team, not tester actions)")
    print("=" * WIDTH)
    return 1 if rep.problems else 0


if __name__ == "__main__":
    sys.exit(main())
