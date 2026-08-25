# -*- coding: utf-8 -*-
"""Validate the target Odoo environments and the QA platform tooling.

Read-only against Odoo: version ping, authentication, installed-module
listing. Writes only inside the platform (data/env_validation.json and a
scratch file under artifacts/ to prove evidence storage works).

Usage:  python scripts/validate_env.py
"""
from __future__ import annotations

import json
import socket
import sys
import time
import xmlrpc.client
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.config import load_environments, settings          # noqa: E402

KEY_MODULES = [
    "mmg_sale", "mmg_stock", "mmg_account", "mmg_automated_action",
    "account_avatax_oca", "odoo_magento2_ept", "mmg_multichannel_shopify",
    "queue_job",
]


def check(name, fn):
    try:
        value = fn()
        return {"check": name, "ok": True, "detail": value}
    except Exception as exc:                       # noqa: BLE001 — report all
        return {"check": name, "ok": False,
                "detail": f"{type(exc).__name__}: {exc}"}


def validate_environment(env) -> dict:
    checks = []
    parsed = urlparse(env.base_url)
    host, port = parsed.hostname, parsed.port or 80

    def tcp():
        with socket.create_connection((host, port), timeout=5):
            return f"TCP {host}:{port} open"
    checks.append(check("server_reachable", tcp))

    rpc_common = xmlrpc.client.ServerProxy(
        f"{env.base_url}/xmlrpc/2/common", allow_none=True)

    def version():
        v = rpc_common.version()
        return f"server_version={v.get('server_version')}"
    checks.append(check("rpc_version", version))

    uid = None

    def auth():
        nonlocal uid
        uid = rpc_common.authenticate(env.db, env.username, env.password, {})
        if not uid:
            raise RuntimeError(f"authentication failed on db '{env.db}'")
        return f"login ok (db={env.db}, uid={uid})"
    checks.append(check("database_login", auth))

    def modules():
        if not uid:
            raise RuntimeError("skipped — no authenticated session")
        obj = xmlrpc.client.ServerProxy(
            f"{env.base_url}/xmlrpc/2/object", allow_none=True)
        installed = obj.execute_kw(
            env.db, uid, env.password, "ir.module.module", "search_read",
            [[["state", "=", "installed"], ["name", "in", KEY_MODULES]]],
            {"fields": ["name"]})
        names = sorted(m["name"] for m in installed)
        missing = sorted(set(KEY_MODULES) - set(names))
        return {"installed": names, "missing": missing}
    checks.append(check("custom_modules", modules))

    return {"key": env.key, "name": env.name, "version": env.version,
            "base_url": env.base_url, "db": env.db,
            "ready": all(c["ok"] for c in checks), "checks": checks}


def validate_platform() -> dict:
    checks = []

    def runner():
        from framework import registry
        tests = registry.discover()
        return f"{len(tests)} automated tests discovered"
    checks.append(check("test_runner", runner))

    def registry_db():
        from backend.store import Store
        store = Store(settings.data_dir / "results.db")
        n = store.load_registry(settings.data_dir / "test_registry.json")
        feats = store.feature_summary()
        return f"{n} test cases in registry, {len(feats)} in-scope feature groups"
    checks.append(check("registry_store", registry_db))

    def browser():
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            b = pw.chromium.launch(headless=True)
            page = b.new_page()
            page.goto("about:blank")
            shot = settings.artifacts_dir / "env-validation-screenshot.png"
            page.screenshot(path=str(shot))
            b.close()
            ok = shot.exists() and shot.stat().st_size > 0
            if not ok:
                raise RuntimeError("screenshot file missing/empty")
            return f"chromium ok, screenshot stored ({shot.stat().st_size} bytes)"
    checks.append(check("browser_and_screenshots", browser))

    def logs():
        probe = settings.artifacts_dir / "env-validation-log.txt"
        probe.write_text(f"validated {time.strftime('%Y-%m-%d %H:%M:%S')}",
                         encoding="utf-8")
        return f"artifacts dir writable: {settings.artifacts_dir}"
    checks.append(check("log_storage", logs))

    return {"ready": all(c["ok"] for c in checks), "checks": checks}


def main():
    report = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "platform": validate_platform(),
        "environments": [validate_environment(e)
                         for e in load_environments().values()],
    }
    out = settings.data_dir / "env_validation.json"
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False),
                   encoding="utf-8")

    print(f"report: {out}\n")
    p = report["platform"]
    print(f"QA PLATFORM: {'READY' if p['ready'] else 'NEEDS WORK'}")
    for c in p["checks"]:
        print(f"  [{'OK' if c['ok'] else '!!'}] {c['check']}: {c['detail']}")
    for e in report["environments"]:
        print(f"\n{e['name']} ({e['base_url']}, db={e['db']}): "
              f"{'READY' if e['ready'] else 'NOT READY'}")
        for c in e["checks"]:
            print(f"  [{'OK' if c['ok'] else '!!'}] {c['check']}: {c['detail']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
