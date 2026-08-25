"""FastAPI backend: REST API + Server-Sent Events + static frontend.

SSE was chosen over WebSocket for the MVP: updates flow one way
(engine → browser), EventSource auto-reconnects natively, and no extra
client library is needed. Events are persisted first, then streamed — a page
refresh replays the full history and continues live from the same channel.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.config import ROOT, load_environments, settings
from backend.runner import ChainedExecutor, RunExecutor, cancel_run
from backend.store import Store
from framework import registry

app = FastAPI(title="Odoo Regression Test Runner")
store = Store(settings.data_dir / "results.db")
# Load the workbook-derived registry (regenerate with scripts/sync_registry.py)
store.load_registry(settings.data_dir / "test_registry.json")
# Close out executions orphaned by a previous process
_orphans = store.reconcile_orphans()

FRONTEND = ROOT / "frontend"
IN_SCOPE_FEATURES = [f"FG-{n:02d}" for n in range(1, 15)]


# --------------------------------------------------------------------- API
@app.get("/api/environments")
def api_environments():
    return {"environments": [e.public_dict() for e in load_environments().values()],
            "settings": {"headless": settings.headless,
                         "trace": settings.trace,
                         "screenshot_on_success": settings.screenshot_on_success}}


@app.get("/api/tests")
def api_tests():
    tests = registry.discover()
    latest = store.latest_status_by_test()
    return {"tests": [{**t.public_dict(),
                       "latest": latest.get(t.id, {})} for t in tests]}


@app.get("/api/features")
def api_features(all: bool = False):
    """FG-01..FG-14 dashboard rollup (pass all=true to include out-of-scope
    groups FG-15..FG-20 from the workbook)."""
    return {"features": store.feature_summary(in_scope_only=not all)}


@app.get("/api/testcases")
def api_testcases(feature: str | None = None, all: bool = False):
    return {"test_cases": store.test_cases_list(
        feature_id=feature, in_scope_only=not all)}


@app.get("/api/testcases/{tc_id}")
def api_testcase(tc_id: str):
    tc = store.test_case(tc_id)
    if not tc:
        raise HTTPException(404, "Test case not found")
    return tc


class RunRequest(BaseModel):
    environment: str            # "odoo15" | "odoo19" | "both"
    test_ids: list[str] | None = None       # platform test ids (TEST-…)
    features: list[str] | None = None       # feature groups (FG-01 …)
    test_case_ids: list[str] | None = None  # workbook TC ids (TC-…)
    scope: str | None = None                # "in_scope" → FG-01…FG-14, "all"
    label: str | None = None


def _resolve_selection(req: RunRequest):
    """Selection → registered platform tests. Any combination of platform
    test ids, feature groups, workbook TC ids, or a whole-suite scope."""
    all_tests = registry.discover()
    if not any((req.test_ids, req.features, req.test_case_ids, req.scope)):
        return all_tests, "all registered tests"

    picked, why = {}, []
    if req.test_ids:
        wanted = set(req.test_ids)
        picked.update({t.id: t for t in all_tests if t.id in wanted})
        why.append(f"{len(wanted)} test id(s)")
    if req.features or req.scope:
        features = set(req.features or [])
        if req.scope == "in_scope":
            features |= set(IN_SCOPE_FEATURES)
            why.append("FG-01→FG-14")
        elif req.scope == "all":
            features |= {t.workflow for t in all_tests}
            why.append("every feature")
        if req.features:
            why.append(", ".join(sorted(req.features)))
        # a feature's automation = tests tagged with it, plus any test the
        # registry records as covering one of its workbook test cases (an
        # older suite may cover a TC without carrying the FG tag)
        by_id = {t.id: t for t in all_tests}
        picked.update({t.id: t for t in all_tests if t.workflow in features})
        for fg in features:
            for tc in store.test_cases_list(feature_id=fg, in_scope_only=False):
                for test_id in tc.get("automated_test_ids", []):
                    if test_id in by_id:
                        picked[test_id] = by_id[test_id]
    if req.test_case_ids:
        wanted = set(req.test_case_ids)
        for t in all_tests:
            tc_ids = {str(x).split()[0].strip("()")
                      for x in t.traceability.get("tc_ids", [])}
            if tc_ids & wanted:
                picked[t.id] = t
        why.append(", ".join(sorted(wanted)))
    ordered = [t for t in all_tests if t.id in picked]
    return ordered, " · ".join(why)


@app.post("/api/runs")
def api_start_run(req: RunRequest):
    envs = load_environments()
    selected, why = _resolve_selection(req)
    if not selected:
        raise HTTPException(400, "No matching registered tests for that selection")

    what = req.label or why or f"{len(selected)} tests"

    # One run at a time per target. Suites sweep marker-scoped fixtures, so
    # two runs against the same database delete each other's data mid-flight
    # (seen as fixture-token mismatches and FK violations). Refuse instead of
    # producing quietly corrupt results.
    wanted_envs = (["odoo15", "odoo19"] if req.environment == "both"
                   else [req.environment])
    for env_key in wanted_envs:
        busy = store.active_runs(env_key)
        if busy:
            raise HTTPException(409, {
                "message": f"A run is already in progress on "
                           f"{envs[env_key].name if env_key in envs else env_key}. "
                           f"Wait for it to finish (or cancel it) before "
                           f"starting another — concurrent runs corrupt each "
                           f"other's fixtures.",
                "active_run_id": busy[0]["id"],
            })

    if req.environment == "both":
        group_id = "CMP-" + uuid.uuid4().hex[:8].upper()
        executors, run_ids = [], []
        for key in ("odoo15", "odoo19"):
            if key not in envs:
                raise HTTPException(400, f"Environment '{key}' not configured")
            run_id = store.create_run(
                key, envs[key].name, "compare", group_id,
                label=f"{what} — compare {group_id} — {envs[key].name}")
            executors.append(RunExecutor(store, run_id, key, selected))
            run_ids.append(run_id)
        ChainedExecutor(executors).start()
        return {"run_ids": run_ids, "group_id": group_id, "mode": "compare",
                "selected": len(selected), "selection": what}

    if req.environment not in envs:
        raise HTTPException(400, f"Unknown environment '{req.environment}'")
    run_id = store.create_run(req.environment, envs[req.environment].name,
                              "single", None,
                              label=f"{what} — {envs[req.environment].name}")
    RunExecutor(store, run_id, req.environment, selected).start()
    return {"run_ids": [run_id], "mode": "single",
            "selected": len(selected), "selection": what}


@app.post("/api/registry/reload")
def api_registry_reload():
    """Re-import the test packages and re-sync the workbook registry, so
    newly added or edited test scripts become runnable without a restart."""
    n_tests = len(registry.reload())
    n_cases = store.load_registry(settings.data_dir / "test_registry.json")
    return {"tests": n_tests, "test_cases": n_cases}


@app.get("/api/runs")
def api_runs():
    return {"runs": store.runs()}


@app.get("/api/runs/{run_id}")
def api_run(run_id: str):
    run = store.run(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    return run


@app.post("/api/runs/{run_id}/cancel")
def api_cancel(run_id: str):
    cancel_run(run_id)
    return {"ok": True}


@app.get("/api/runs/{run_id}/events")
async def api_events(run_id: str):
    """SSE stream: replays persisted events, then polls for new ones (0.4 s).
    Ends automatically once RUN_COMPLETED has been delivered."""
    if not store.run(run_id):
        raise HTTPException(404, "Run not found")

    async def gen():
        last_seq = 0
        finished = False
        idle_after_finish = 0
        while True:
            events = await asyncio.to_thread(store.events_since, run_id, last_seq)
            for ev in events:
                last_seq = ev["seq"]
                if ev["type"] in ("RUN_COMPLETED",):
                    finished = True
                yield f"event: {ev['type']}\ndata: {json.dumps(ev)}\n\n"
            if finished:
                idle_after_finish += 1
                if idle_after_finish > 2:
                    yield "event: STREAM_END\ndata: {}\n\n"
                    return
            yield ": keepalive\n\n"
            await asyncio.sleep(0.4)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@app.get("/api/results/{result_id}")
def api_result(result_id: str):
    res = store.result(result_id)
    if not res:
        raise HTTPException(404, "Result not found")
    return res


@app.get("/api/artifacts/{artifact_id}")
def api_artifact(artifact_id: int):
    art = store.artifact(artifact_id)
    if not art or not Path(art["path"]).exists():
        raise HTTPException(404, "Artifact not found")
    media = {"screenshot": "image/png", "trace": "application/zip",
             "video": "video/webm", "log": "text/plain; charset=utf-8"}
    return FileResponse(art["path"],
                        media_type=media.get(art["type"],
                                             "application/octet-stream"),
                        filename=Path(art["path"]).name)


@app.get("/api/compare/{group_id}")
def api_compare(group_id: str):
    cmp_ = store.compare_group(group_id)
    if not cmp_:
        raise HTTPException(404, "Comparison group not found")
    return cmp_


# ---------------------------------------------------------------- frontend
app.mount("/static", StaticFiles(directory=str(FRONTEND)), name="static")


@app.get("/")
def index():
    return FileResponse(FRONTEND / "index.html")
