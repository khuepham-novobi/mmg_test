# -*- coding: utf-8 -*-
"""Sync the test-case registry from the Excel knowledge base.

Reads MMG_v19_Test_Cases_Grouped_by_Feature_v3.0.xlsx (READ-ONLY — the
workbook is the source of truth and is never written) and regenerates
``data/test_registry.json``. The backend upserts that JSON into the SQLite
``test_cases`` table at startup.

Rules
-----
* ``tc_id`` is the immutable test_case_id. It is never renamed here.
* ``expected_result`` (and steps / preconditions / title) are copied
  VERBATIM from the workbook. Nothing in the platform may modify them —
  a change in the workbook is the only way they change.
* ``automation_type`` is derived deterministically from the workbook's
  ``automation_approach`` column (mapping below), so re-running the sync
  is idempotent.

Usage:  python scripts/sync_registry.py  [--workbook PATH]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WORKBOOK = ROOT.parent.parent / "MMG_v19_Test_Cases_Grouped_by_Feature_v3.0.xlsx"
OUT_JSON = ROOT / "data" / "test_registry.json"

SHEET = "Automation Export"
EXEC_SHEET = "Test Execution"
OVERVIEW_SHEET = "Feature Groups Overview"

# Scope of the current QA phase: FG-01 … FG-14. Everything is imported;
# out-of-scope groups are flagged so the UI can filter.
IN_SCOPE_GROUPS = {f"FG-{n:02d}" for n in range(1, 15)}

# Workbook automation_approach (prefix) → platform automation_type.
# PYTHON_UNIT        Odoo TransactionCase test inside the Odoo test runner
# ORM_INTEGRATION    odoo-bin install/upgrade + registry/log checks
# API                connector integration test vs sandbox / mocked API
# UI                 Playwright browser workflow (platform-driven)
# HTTP_CASE          Odoo HttpCase endpoint test
# TOUR               Odoo tour (HttpCase / browser_js)
# HOOT               Odoo 17+ JS unit test framework
# DATA_RECONCILIATION  SQL/ORM comparison v15 baseline vs v19
# MANUAL             human execution required (incl. decision gates, perf baselines)
_APPROACH_MAP = [
    ("odoo python test", "PYTHON_UNIT"),
    ("integration test vs sandbox", "API"),
    ("sql / orm assertion", "DATA_RECONCILIATION"),
    ("odoo tour test", "TOUR"),
    ("httpcase endpoint", "HTTP_CASE"),
    ("ci boot & install", "ORM_INTEGRATION"),
    ("performance harness", "MANUAL"),
    ("one-off migration task", "MANUAL"),
    ("decision gate", "MANUAL"),
]

# Workbook TCs covered by registered platform tests. Derived live from the
# @test_case traceability blocks under tests/ — falls back to the static
# map when the test registry cannot be imported.
_STATIC_AUTOMATED_BY = {
    "TC-SMK-003": ["TEST-SMOKE-001"],
    "TC-SAL-017": ["TEST-SALES-001", "TEST-SALES-002"],
    "TC-ART-001": ["TEST-SALES-001"],
    "TC-SAL-007": ["TEST-SALES-004"],
}
RELATED_AUTOMATION = {
    "TC-SAL-021": ["TEST-SALES-003"],   # related coverage only, not the full TC
}


def _derive_automated_by() -> dict:
    """tc_id → [platform test ids], from the live test registry."""
    import re
    try:
        import sys
        sys.path.insert(0, str(ROOT))
        from framework import registry
        mapping: dict = {}
        for test in registry.discover():
            for raw in test.traceability.get("tc_ids", []):
                raw = str(raw)
                if "related" in raw.lower() or "gap" in raw.lower():
                    continue
                m = re.search(r"TC-[A-Z]+-\d+", raw)
                if m:
                    mapping.setdefault(m.group(0), []).append(test.id)
        return mapping or dict(_STATIC_AUTOMATED_BY)
    except Exception as exc:  # noqa: BLE001
        print(f"WARN: could not derive automation map from tests/ ({exc}); "
              f"using the static map", file=sys.stderr)
        return dict(_STATIC_AUTOMATED_BY)


AUTOMATED_BY = _derive_automated_by()


def classify(approach: str) -> str:
    a = (approach or "").strip().lower()
    for prefix, kind in _APPROACH_MAP:
        if a.startswith(prefix):
            return kind
    return "MANUAL"          # conservative default for unknown approaches


def automation_status(tc_id: str, automation_type: str, wave: str) -> str:
    """AUTOMATED > MANUAL_ONLY > PLANNED (wave 1) > CANDIDATE (wave 2)
    > NOT_PLANNED (workbook says manual although the type is automatable)."""
    if tc_id in AUTOMATED_BY:
        return "AUTOMATED"
    if automation_type == "MANUAL":
        return "MANUAL_ONLY"
    w = (wave or "").lower()
    if w.startswith("wave 1"):
        return "PLANNED"
    if w.startswith("wave 2"):
        return "CANDIDATE"
    return "NOT_PLANNED"


def load_rows(workbook: Path):
    import openpyxl
    wb = openpyxl.load_workbook(workbook, data_only=True, read_only=True)

    def sheet_rows(name):
        ws = wb[name]
        rows = list(ws.iter_rows(values_only=True))
        hdr = {h: i for i, h in enumerate(rows[0])}
        return hdr, rows[1:]

    hdr, rows = sheet_rows(SHEET)
    exec_hdr, exec_rows = sheet_rows(EXEC_SHEET)
    ov_hdr, ov_rows = sheet_rows(OVERVIEW_SHEET)

    exec_row_by_tc = {
        r[exec_hdr["TC ID"]]: i + 2            # +2: 1-based + header row
        for i, r in enumerate(exec_rows) if r and r[exec_hdr["TC ID"]]
    }
    groups = {}
    for r in ov_rows:
        if r and r[ov_hdr["Group ID"]]:
            groups[r[ov_hdr["Group ID"]]] = {
                "feature_id": r[ov_hdr["Group ID"]],
                "name": r[ov_hdr["Feature Group"]],
                "business_purpose": r[ov_hdr["Business Purpose"]],
                "key_modules": r[ov_hdr["Key Modules"]],
                "primary_roles": r[ov_hdr["Primary Roles"]],
                "in_scope": r[ov_hdr["Group ID"]] in IN_SCOPE_GROUPS,
            }

    cases = []
    for i, r in enumerate(rows):
        if not r or not r[hdr["tc_id"]]:
            continue
        get = lambda col: r[hdr[col]]
        tc_id = str(get("tc_id")).strip()
        approach = str(get("automation_approach") or "")
        wave = str(get("automation_wave") or "")
        auto_type = classify(approach)
        cases.append({
            "test_case_id": tc_id,
            "feature_id": get("group_id"),
            "feature_name": get("group_name"),
            "in_scope": get("group_id") in IN_SCOPE_GROUPS,
            "seq": get("seq"),
            "title": get("title"),
            "description": get("user_story"),
            "feature_ref": get("feature_ref"),
            "feature": get("feature_name"),
            "feature_category": get("feature_category"),
            "priority": get("priority"),
            "test_type": get("test_type"),
            "role": get("role"),
            "modules": get("modules"),
            "preconditions": get("preconditions"),
            "steps": get("steps"),
            "expected_result": get("expected_result"),   # verbatim — source of truth
            "v19_watch": get("v19_watch"),
            "suite": get("suite"),
            "suite_name": get("suite_name"),
            "execution_phase": get("execution_phase"),
            "related_features": get("related_features"),
            "automation_wave": wave,
            "automation_approach": approach,
            "automation_type": auto_type,
            "automation_status": automation_status(tc_id, auto_type, wave),
            "automated_test_ids": AUTOMATED_BY.get(tc_id, []),
            "related_test_ids": RELATED_AUTOMATION.get(tc_id, []),
            "source_notes": get("source_notes"),
            "source_workbook": DEFAULT_WORKBOOK.name,
            "source_sheet": SHEET,
            "source_row": i + 2,                          # 1-based incl. header
            "test_execution_row": exec_row_by_tc.get(tc_id),
        })
    return groups, cases


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    args = ap.parse_args(argv)

    if not args.workbook.exists():
        print(f"Workbook not found: {args.workbook}", file=sys.stderr)
        return 1

    groups, cases = load_rows(args.workbook)
    ids = [c["test_case_id"] for c in cases]
    if len(ids) != len(set(ids)):
        dupes = sorted({x for x in ids if ids.count(x) > 1})
        print(f"FATAL: duplicate tc_ids in workbook: {dupes}", file=sys.stderr)
        return 1

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps({
        "workbook": str(args.workbook),
        "sheet": SHEET,
        "feature_groups": list(groups.values()),
        "test_cases": cases,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    in_scope = [c for c in cases if c["in_scope"]]
    by_type = {}
    for c in in_scope:
        by_type[c["automation_type"]] = by_type.get(c["automation_type"], 0) + 1
    print(f"Registry written: {OUT_JSON}")
    print(f"  feature groups: {len(groups)} ({sum(1 for g in groups.values() if g['in_scope'])} in scope)")
    print(f"  test cases:     {len(cases)} ({len(in_scope)} in scope FG-01..FG-14)")
    print(f"  in-scope automation_type: {by_type}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
