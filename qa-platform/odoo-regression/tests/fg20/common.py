"""FG-20 — Performance & Volume. Measurement, and the baseline it needs.

Source of truth is the CLIENT MANUAL TESTING GUIDELINE
``MMG_v19_Client_Manual_Testing_Guideline_FG15-FG20_v1.0.xlsx``, sheet
``Testing Guideline``. Cases TC-PERF-001, -002, -003, -004 and -007.

Every case in this group is blocked, and every case still measures
-------------------------------------------------------------------
All five say the same thing in their preconditions: *"Novobi has given you
the timings for the same steps on the old system. Without them this case
cannot be judged — record it as Blocked rather than guessing."* So a verdict
is not available here, and inventing a threshold would be exactly the
guessing the workbook forbids.

What IS available is the other half of every comparison. Each case times
the v19 side, three times, keeping the middle value — the workbook's own
method — writes the numbers out as a CSV artifact, and then blocks naming
the baseline it is missing. When Novobi supplies the v15 timings they go
into ``reports/data/fg20_baseline.json`` and these same tests start
judging, with no rewrite: see :func:`baseline`.

What is being timed, and what is not
-------------------------------------
The workbook times a stopwatch from clicking a menu to the rows finishing.
That is server time PLUS transport PLUS render. This suite times the
server call the list view actually issues — ``web_search_read``, the same
one the browser sends — so the numbers are the query, not the paint.

That difference is worth being exact about, because it cuts both ways. A
server number cannot clear a screen that is slow for rendering reasons, and
FG-15 has already shown this stack leans on custom widgets. But it is
reproducible where a stopwatch is not, it is comparable between two
machines, and a query that takes thirty seconds cannot be rescued by any
amount of front-end work. Both halves are stated in every case's log.
"""
from __future__ import annotations

import csv
import json
import statistics
import time
from pathlib import Path

from adapters.base import OdooRPCError

# --------------------------------------------------------------- identity
FEATURE = "FG-20 Performance & Volume"
WORKFLOW = "FG-20"
WORKFLOW_NAME = "Performance & Volume"
MODULE = "Platform"

WORKBOOK = "MMG_v19_Client_Manual_Testing_Guideline_FG15-FG20_v1.0.xlsx"
SHEET = "Testing Guideline"

#: Where Novobi's v15 timings go when they exist. One object per TC id,
#: each a ``{step label: seconds}`` map. Absent today, which is why every
#: case in this group blocks.
BASELINE_FILE = (Path(__file__).resolve().parents[2]
                 / "reports" / "data" / "fg20_baseline.json")

#: The workbook's tolerance, stated in TC-PERF-001 step 7 and repeated in
#: the others: "anything slower than about one and a half times the old
#: system is a FAIL".
TOLERANCE = 1.5

#: The production volumes the workbook states, for the count check each
#: case makes.
STATED_VOLUMES = {
    "products": 69201,
    "orders": 43117,
    "journal entries": 109218,
}


def trace(tc_ids, user_story: str = "") -> dict:
    return {
        "tc_ids": tc_ids if isinstance(tc_ids, list) else [tc_ids],
        "feature": FEATURE,
        "user_story": user_story,
        "source": f"{WORKBOOK} / {SHEET}",
    }


# ------------------------------------------------------------------- gates
def require_v19(ctx):
    if ctx.env.version != "19":
        ctx.blocked("FG-20 measures the v19 instance at full production "
                    f"volume (current target: {ctx.env.name}).")
    return ctx.adapter.rpc


def baseline(tc_id: str) -> dict:
    """Novobi's v15 timings for one case, or ``{}`` when none are on file."""
    try:
        data = json.loads(BASELINE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data.get(tc_id) or {}


# ---------------------------------------------------------------- evidence
def manual(ctx, text: str):
    ctx.log(f"RESIDUAL MANUAL STEP — {text}")


def observation(ctx, text: str):
    ctx.log(f"OBSERVATION — {text}")


def finding(ctx, text: str):
    ctx.log(f"FINDING — {text}")


# ------------------------------------------------------------- measurement
def median_of_three(ctx, label: str, call_once) -> dict:
    """Run ``call_once`` three times and keep the MIDDLE value.

    The workbook asks for exactly this — "Time each step three times and
    record the MIDDLE value, not the best or worst" — and it is the right
    instruction: the first run of any query on a cold cache is not the
    number anyone lives with, and the fastest is not either.
    """
    runs, rows = [], None
    for _ in range(3):
        started = time.perf_counter()
        try:
            rows = call_once()
            error = ""
        except OdooRPCError as exc:
            rows, error = None, str(exc)
        elapsed = time.perf_counter() - started
        runs.append(elapsed)
        if error:
            ctx.log(f"  {label}: FAILED after {elapsed:.2f}s — {error[:160]}")
            return {"label": label, "seconds": elapsed, "runs": runs,
                    "error": error, "rows": None}
    middle = statistics.median(runs)
    count = _row_count(rows)
    ctx.log(f"  {label}: {middle:.2f}s "
            f"(runs {', '.join(f'{r:.2f}' for r in runs)})"
            + (f" — {count} row(s)" if isinstance(count, int) else ""))
    return {"label": label, "seconds": middle, "runs": runs, "error": "",
            "rows": count}


def _row_count(rows):
    """How many rows a measured call came back with.

    ``web_search_read`` answers with ``{'length': N, 'records': [...]}``,
    not a list. Storing the raw value put the entire result set into the
    CSV — 119 KB of product names in a column meant to hold a number.
    """
    if isinstance(rows, dict):
        return rows.get("length", len(rows.get("records") or []))
    if isinstance(rows, list):
        return len(rows)
    return rows


def list_columns(ctx, model: str) -> list:
    """The fields the model's list view actually draws.

    Timing ``display_name`` alone would measure a query no screen issues:
    a list reads every column in its arch, and on these models that is a
    dozen fields including stored computes. Reading what the view declares
    keeps the measurement honest about what the gallery waits for.
    """
    cached = getattr(ctx, "_fg20_columns", None)
    if cached is None:
        cached = {}
        ctx._fg20_columns = cached
    if model in cached:
        return cached[model]
    import re
    try:
        arch = ctx.adapter.rpc.call(model, "get_view",
                                    view_type="list")["arch"]
    except OdooRPCError:
        cached[model] = ["display_name"]
        return cached[model]
    names, seen = [], set()
    for name in re.findall(r'<field[^>]*name="([^"]+)"', arch):
        if name not in seen:
            seen.add(name)
            names.append(name)
    cached[model] = names or ["display_name"]
    return cached[model]


def time_list(ctx, model: str, domain=None, limit: int = 80,
              label: str = "", fields=None) -> dict:
    """Time the call a list view actually issues.

    ``web_search_read`` is what the browser sends when a list draws, so
    this is the query half of the workbook's stopwatch — not an analogue
    of it. The columns come from the view rather than being invented, for
    the same reason.
    """
    rpc = ctx.adapter.rpc
    spec = fields or list_columns(ctx, model)

    def once():
        return rpc.call(model, "web_search_read", domain or [],
                        specification={name: {} for name in spec},
                        limit=limit)

    return median_of_three(
        ctx, label or f"{model} list ({limit} rows)", once)


def time_group(ctx, model: str, groupby: str, domain=None,
               label: str = "") -> dict:
    """Time a Group By, which is what the list issues when one is chosen."""
    rpc = ctx.adapter.rpc

    def once():
        return rpc.read_group(model, domain or [], [], [groupby], lazy=True)

    return median_of_three(ctx, label or f"{model} grouped by {groupby}",
                           once)


def time_count(ctx, model: str, domain=None, label: str = "") -> dict:
    rpc = ctx.adapter.rpc

    def once():
        return rpc.call(model, "search_count", domain or [])

    return median_of_three(ctx, label or f"{model} count", once)


# ------------------------------------------------------------- reporting
def write_measurements(ctx, name: str, rows: list):
    """Write the timings out so they can be handed to Novobi as one half of
    the comparison."""
    path = ctx.artifacts_dir / name
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["step", "v19 seconds (median of 3)", "run 1",
                         "run 2", "run 3", "rows", "error"])
        for row in rows:
            runs = row.get("runs") or []
            writer.writerow([
                row["label"], f"{row['seconds']:.3f}",
                *[f"{r:.3f}" for r in (runs + ["", "", ""])[:3]],
                row.get("rows", ""), row.get("error", ""),
            ])
    ctx.add_artifact(path, "log", name)
    ctx.log(f"artifact written: {name} ({len(rows)} measurements)")
    return path


def judge_or_block(ctx, tc_id: str, measurements: list):
    """Compare against Novobi's baseline if there is one; block if not.

    This is the whole design of the group: the measuring is done either
    way, so the day the baseline arrives these cases start returning
    verdicts without a line of them changing.
    """
    # Only numeric entries count. A skeleton file with the step labels
    # present and their values left null would otherwise make `known`
    # truthy, the comparison loop skip every step, and the case go GREEN
    # having compared nothing at all — the worst possible outcome for a
    # case whose entire subject is a comparison.
    known = {label: value for label, value in (baseline(tc_id) or {}).items()
             if isinstance(value, (int, float)) and value > 0}
    if not known:
        ctx.blocked(
            f"{tc_id} cannot be judged without the old system's timings. "
            f"Its own precondition says so: \"Novobi has given you the "
            f"timings for the same steps on the old system. Without them "
            f"this case cannot be judged — record it as Blocked rather "
            f"than guessing.\" The v19 side IS measured and is in this "
            f"run's CSV artifact, three runs per step with the middle "
            f"value kept, so only half the comparison is missing. To turn "
            f"this into a verdict, put the v15 seconds into "
            f"reports/data/fg20_baseline.json under \"{tc_id}\" keyed by "
            f"the step labels in that artifact; this test then judges them "
            f"at the workbook's own tolerance of {TOLERANCE}x with no "
            f"change to the test.")

    slow, compared, uncompared = [], [], []
    for row in measurements:
        before = known.get(row["label"])
        if before is None:
            uncompared.append(row["label"])
            continue
        ratio = row["seconds"] / before if before else float("inf")
        compared.append(f"{row['label']}: v15 {before:.2f}s -> v19 "
                        f"{row['seconds']:.2f}s ({ratio:.2f}x)")
        if ratio > TOLERANCE:
            slow.append(f"{row['label']} — v15 {before:.2f}s, v19 "
                        f"{row['seconds']:.2f}s ({ratio:.2f}x)")
    for line in compared:
        ctx.log(f"  {line}")
    if uncompared:
        # Named, not silently dropped: a step measured on v19 with no v15
        # number beside it is a gap in the comparison, and the reader
        # should see which ones.
        ctx.log(f"  no v15 baseline on file for: {uncompared}")
    ctx.check_true(
        "The baseline covers the steps this run measured",
        not uncompared,
        actual_desc=f"{len(compared)} step(s) compared, "
                    f"{len(uncompared)} without a baseline: {uncompared}")
    ctx.check(f"No step is slower than {TOLERANCE}x the old system — the "
              f"workbook's own tolerance", [], slow)
