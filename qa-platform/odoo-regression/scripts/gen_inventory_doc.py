# -*- coding: utf-8 -*-
"""Generate docs/TEST_INVENTORY.md from data/test_registry.json.

The registry JSON (synced read-only from the Excel workbook by
scripts/sync_registry.py) is the full capture — including preconditions,
steps and verbatim expected results. This document is the human-readable
inventory over it.

Usage:  python scripts/gen_inventory_doc.py
"""
from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REG = ROOT / "data" / "test_registry.json"
OUT = ROOT / "docs" / "TEST_INVENTORY.md"


def md_escape(s):
    return str(s or "").replace("|", "\\|").replace("\n", " ").strip()


def main():
    data = json.loads(REG.read_text(encoding="utf-8"))
    cases = [c for c in data["test_cases"] if c["in_scope"]]
    groups = {g["feature_id"]: g for g in data["feature_groups"] if g["in_scope"]}

    by_group = {}
    for c in cases:
        by_group.setdefault(c["feature_id"], []).append(c)

    type_counts = Counter(c["automation_type"] for c in cases)
    status_counts = Counter(c["automation_status"] for c in cases)
    prio_counts = Counter(c["priority"] for c in cases)

    lines = [
        "# Test Inventory — FG-01 → FG-14",
        "",
        f"Generated {time.strftime('%Y-%m-%d %H:%M')} by `scripts/gen_inventory_doc.py`.",
        "",
        f"**Source of truth:** `{data['workbook']}`, sheet **{data['sheet']}** "
        "(read-only — the platform never writes to the workbook).",
        "",
        "Full capture of every test case — including **preconditions, steps and "
        "the verbatim expected result** — lives in `data/test_registry.json` "
        "(regenerate with `python scripts/sync_registry.py`) and is browsable "
        "per test case in the web UI (`#/testcase/<TC-ID>`). Expected results "
        "are imported verbatim and are never modified by the platform.",
        "",
        "## Summary",
        "",
        "| Feature group | Name | Test cases | P0 | P1 | P2 | P3 |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for fg in sorted(by_group):
        tcs = by_group[fg]
        p = Counter(c["priority"] for c in tcs)
        lines.append(f"| {fg} | {md_escape(groups[fg]['name'])} | {len(tcs)} "
                     f"| {p.get('P0', 0)} | {p.get('P1', 0)} | {p.get('P2', 0)} "
                     f"| {p.get('P3', 0)} |")
    lines += [
        f"| **Total** | | **{len(cases)}** | **{prio_counts.get('P0', 0)}** "
        f"| **{prio_counts.get('P1', 0)}** | **{prio_counts.get('P2', 0)}** "
        f"| **{prio_counts.get('P3', 0)}** |",
        "",
        "### Automation classification (Step 3)",
        "",
        "Derived deterministically from the workbook `automation_approach` column "
        "(mapping in `scripts/sync_registry.py::_APPROACH_MAP`):",
        "",
        "| automation_type | Count | Meaning |",
        "|---|---:|---|",
    ]
    meanings = {
        "PYTHON_UNIT": "Odoo `TransactionCase` test inside the Odoo test runner",
        "ORM_INTEGRATION": "`odoo-bin` install/upgrade + registry & log checks",
        "API": "Connector integration test vs sandbox / mocked API (`TEST_QUEUE_JOB_NO_DELAY=1`)",
        "UI": "Playwright browser workflow driven by this platform",
        "HTTP_CASE": "Odoo `HttpCase` endpoint test (+ manual security review)",
        "TOUR": "Odoo tour (`HttpCase` / `browser_js`)",
        "HOOT": "Odoo 17+ JS unit test (none in FG-01..14 scope)",
        "DATA_RECONCILIATION": "SQL/ORM comparison — v15 baseline vs v19",
        "MANUAL": "Human execution required (decision gates, perf baselines, one-off checks)",
        "NOT_APPLICABLE": "Not applicable to the v19 scope",
    }
    for t in ("PYTHON_UNIT", "ORM_INTEGRATION", "API", "UI", "HTTP_CASE",
              "TOUR", "HOOT", "DATA_RECONCILIATION", "MANUAL", "NOT_APPLICABLE"):
        lines.append(f"| {t} | {type_counts.get(t, 0)} | {meanings[t]} |")
    lines += [
        "",
        "### Automation status",
        "",
        "| automation_status | Count | Meaning |",
        "|---|---:|---|",
        f"| AUTOMATED | {status_counts.get('AUTOMATED', 0)} | Covered by a registered platform test today |",
        f"| PLANNED | {status_counts.get('PLANNED', 0)} | Workbook Wave 1 — automate now |",
        f"| CANDIDATE | {status_counts.get('CANDIDATE', 0)} | Workbook Wave 2 — candidate |",
        f"| NOT_PLANNED | {status_counts.get('NOT_PLANNED', 0)} | Automatable type but workbook says manual for now |",
        f"| MANUAL_ONLY | {status_counts.get('MANUAL_ONLY', 0)} | Not automatable (decision gates, perf baselines) |",
        "",
        "---",
        "",
    ]

    for fg in sorted(by_group):
        g = groups[fg]
        tcs = by_group[fg]
        lines += [
            f"## {fg} — {g['name']} ({len(tcs)} test cases)",
            "",
            f"> {md_escape(g['business_purpose'])}",
            f">",
            f"> **Key modules:** {md_escape(g['key_modules'])} · "
            f"**Roles:** {md_escape(g['primary_roles'])}",
            "",
            "| TC ID | Title | Prio | Type | Automation | Status | Src row |",
            "|---|---|---|---|---|---|---:|",
        ]
        for c in tcs:
            lines.append(
                f"| {c['test_case_id']} | {md_escape(c['title'])} "
                f"| {c['priority']} | {c['test_type']} "
                f"| {c['automation_type']} | {c['automation_status']} "
                f"| {c['source_row']} |")
        lines.append("")

    lines += [
        "---",
        "",
        "*Src row = row in the workbook sheet “Automation Export”; each test case "
        "also records its “Test Execution” sheet row in the registry JSON.*",
        "",
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT} ({len(cases)} test cases, {len(by_group)} groups)")


if __name__ == "__main__":
    main()
