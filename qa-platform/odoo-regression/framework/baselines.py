"""Cross-version baselines for DATA_RECONCILIATION tests.

Pattern: the run on the *baseline* environment (Odoo 15) captures a
snapshot and stores it here; the run on the *target* environment (Odoo 19)
loads the stored snapshot and diffs against live data. Baselines are
per-test JSON files under data/baselines/ plus optional CSV payloads.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from backend.config import settings

BASELINE_DIR = settings.data_dir / "baselines"


def baseline_path(tc_id: str) -> Path:
    return BASELINE_DIR / f"{tc_id}.json"


def save_baseline(tc_id: str, env_key: str, db: str, data: dict) -> Path:
    path = baseline_path(tc_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "tc_id": tc_id,
        "captured_env": env_key,
        "captured_db": db,
        "captured_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "data": data,
    }, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    return path


def load_baseline(tc_id: str) -> dict | None:
    path = baseline_path(tc_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def csv_baseline_path(tc_id: str, name: str) -> Path:
    return BASELINE_DIR / tc_id / f"{name}.csv"


def diff_counts(baseline: dict, current: dict) -> list[str]:
    """Compare two {key: count} dicts; return human-readable differences."""
    diffs = []
    for key in sorted(set(baseline) | set(current)):
        b, c = baseline.get(key), current.get(key)
        if b != c:
            diffs.append(f"{key}: baseline={b!r} current={c!r}")
    return diffs
