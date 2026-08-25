"""Shared helpers for all FG suites (FG-01 … FG-14).

Live-DB determinism rules every suite follows:
* fixtures are namespaced with the suite marker (e.g. "FG03 ...") and swept
  before/after each test — pre-existing business records are never modified;
* reconciliation tests are read-only and use the baseline/diff pattern;
* over XML-RPC each call commits, so cr.precommit hooks fire per call.
"""
from __future__ import annotations

import http.cookiejar
import json
import urllib.request

from framework.baselines import (baseline_path, diff_counts, load_baseline,
                                 save_baseline)

WORKBOOK = "MMG_v19_Test_Cases_Grouped_by_Feature_v3.0.xlsx"


def make_trace(feature: str):
    """trace('TC-…') factory bound to one feature group."""
    def trace(tc_ids, user_story=""):
        return {"tc_ids": tc_ids if isinstance(tc_ids, list) else [tc_ids],
                "feature": feature, "user_story": user_story,
                "source": f"{WORKBOOK} / Automation Export"}
    return trace


def m2o_id(value):
    """RPC read() returns m2o as [id, display_name] or False."""
    return value[0] if isinstance(value, (list, tuple)) else (value or None)


def form_arch(ctx, model, view_type="form"):
    """Version-agnostic view arch fetch (v15 fields_view_get / v16+ get_view)."""
    if ctx.env.version == "15":
        return ctx.adapter.rpc.call(model, "fields_view_get",
                                    view_type=view_type)["arch"]
    vt = "list" if view_type == "tree" else view_type
    return ctx.adapter.rpc.call(model, "get_view", view_type=vt)["arch"]


def http_session(env):
    """An authenticated urllib opener (real web session) for HTTP evidence."""
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar))
    payload = json.dumps({"jsonrpc": "2.0", "params": {
        "db": env.db, "login": env.username, "password": env.password}})
    req = urllib.request.Request(
        f"{env.base_url}/web/session/authenticate", data=payload.encode(),
        headers={"Content-Type": "application/json"})
    res = json.loads(opener.open(req, timeout=30).read())
    if not (res.get("result") or {}).get("uid"):
        raise RuntimeError("web session authentication failed")
    return opener


def reconcile(ctx, tc_id, capture, anchors=None):
    """DATA_RECONCILIATION driver — see framework/baselines.py.

    capture(ctx) -> {key: value} snapshot of the current environment.
    v15: capture, assert anchors, persist baseline.
    v19: load baseline (BLOCKED if absent), capture, assert zero diff.
    """
    with ctx.step("Capture current-environment snapshot (read-only SQL/ORM)"):
        current = capture(ctx)
        for key, value in sorted(current.items()):
            ctx.log(f"  {key} = {value}")

    if anchors:
        with ctx.step("Assert workbook anchor values"):
            for key, expected in anchors.items():
                ctx.check(f"anchor {key}", expected=expected,
                          actual=current.get(key))

    if ctx.env.version == "15":
        with ctx.step("Persist v15 baseline for the v19 comparison"):
            path = save_baseline(tc_id, ctx.env.key, ctx.env.db, current)
            ctx.add_artifact(path, "log", f"{tc_id} v15 baseline")
            ctx.log(f"baseline stored: {path}")
    else:
        with ctx.step("Diff against the stored v15 baseline"):
            base = load_baseline(tc_id)
            if base is None:
                ctx.blocked(f"No v15 baseline captured yet for {tc_id} — "
                            "run the suite on Odoo 15 first")
            ctx.add_artifact(baseline_path(tc_id), "log",
                             f"{tc_id} v15 baseline")
            diffs = diff_counts(base["data"], current)
            ctx.check("No differences vs v15 baseline", expected=[],
                      actual=diffs)
