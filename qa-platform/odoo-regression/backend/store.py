"""Persistent result model (SQLite, stdlib only).

TestRun → TestResult → StepResult / AssertionResult / Artifact, plus an
append-only event log per run (drives SSE replay + live updates).
Statuses: NOT RUN, QUEUED, RUNNING, PASSED, FAILED, SKIPPED, ERROR, FLAKY.
"""
from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
import uuid
from pathlib import Path

_TC_ID_RE = re.compile(r"TC-[A-Z]+-\d+")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY,
  label TEXT, environment TEXT, env_name TEXT, mode TEXT,
  group_id TEXT, status TEXT,
  started_at REAL, finished_at REAL,
  total INTEGER DEFAULT 0, passed INTEGER DEFAULT 0, failed INTEGER DEFAULT 0,
  skipped INTEGER DEFAULT 0, errors INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS results (
  id TEXT PRIMARY KEY,
  run_id TEXT, test_id TEXT, name TEXT, workflow TEXT, kind TEXT,
  priority TEXT, status TEXT,
  started_at REAL, finished_at REAL, duration_ms INTEGER,
  error TEXT, failed_step TEXT, expected TEXT, actual TEXT,
  skip_reason TEXT, traceability TEXT
);
CREATE TABLE IF NOT EXISTS steps (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  result_id TEXT, idx INTEGER, name TEXT, status TEXT,
  duration_ms INTEGER, error TEXT
);
CREATE TABLE IF NOT EXISTS assertions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  result_id TEXT, name TEXT, expected TEXT, actual TEXT, passed INTEGER
);
CREATE TABLE IF NOT EXISTS artifacts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  result_id TEXT, type TEXT, name TEXT, path TEXT
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT, seq INTEGER, ts REAL, type TEXT, payload TEXT
);
CREATE TABLE IF NOT EXISTS test_cases (
  test_case_id TEXT PRIMARY KEY,       -- immutable workbook TC id
  feature_id TEXT, feature_name TEXT, in_scope INTEGER,
  seq INTEGER, title TEXT, description TEXT,
  feature_ref TEXT, feature TEXT, feature_category TEXT,
  priority TEXT, test_type TEXT, role TEXT, modules TEXT,
  preconditions TEXT, steps TEXT,
  expected_result TEXT,                -- verbatim from Excel; never edited here
  v19_watch TEXT, suite TEXT, suite_name TEXT, execution_phase TEXT,
  related_features TEXT,
  automation_wave TEXT, automation_approach TEXT,
  automation_type TEXT, automation_status TEXT,
  automated_test_ids TEXT, related_test_ids TEXT,
  source_notes TEXT, source_workbook TEXT, source_sheet TEXT,
  source_row INTEGER, test_execution_row INTEGER
);
CREATE TABLE IF NOT EXISTS feature_groups (
  feature_id TEXT PRIMARY KEY, name TEXT, business_purpose TEXT,
  key_modules TEXT, primary_roles TEXT, in_scope INTEGER
);
CREATE INDEX IF NOT EXISTS idx_results_run ON results(run_id);
CREATE INDEX IF NOT EXISTS idx_events_run ON events(run_id, seq);
CREATE INDEX IF NOT EXISTS idx_tc_feature ON test_cases(feature_id);
"""

# Platform-internal result statuses → canonical execution statuses reported
# by the API / UI (PASS, FAIL, BLOCKED, ERROR, SKIPPED, NOT_IMPLEMENTED,
# NOT_APPLICABLE).
CANONICAL_STATUS = {
    "PASSED": "PASS", "FAILED": "FAIL", "ERROR": "ERROR",
    "SKIPPED": "SKIPPED", "BLOCKED": "BLOCKED",
    "NOT_APPLICABLE": "NOT_APPLICABLE",
    "QUEUED": "NOT_RUN", "RUNNING": "RUNNING", "NOT RUN": "NOT_RUN",
}


class Store:
    def __init__(self, db_path: Path):
        self.db_path = str(db_path)
        self._lock = threading.Lock()
        with self._conn() as con:
            con.executescript(_SCHEMA)
            self._migrate(con)

    @staticmethod
    def _migrate(con):
        """Additive migrations for databases created by earlier versions."""
        cols = {r["name"] for r in con.execute("PRAGMA table_info(results)")}
        if "failure_class" not in cols:
            # ASSERTION | AUTOMATION_ERROR | ENVIRONMENT | BLOCKED | NONE
            con.execute("ALTER TABLE results ADD COLUMN failure_class TEXT")
        run_cols = {r["name"] for r in con.execute("PRAGMA table_info(runs)")}
        if "blocked" not in run_cols:
            con.execute("ALTER TABLE runs ADD COLUMN blocked INTEGER DEFAULT 0")

    def reconcile_orphans(self) -> int:
        """Close out runs left RUNNING/QUEUED by a previous server process.

        Executions are per-process (a worker thread); if the server stops
        mid-run those rows would otherwise stay RUNNING forever and pollute
        every 'latest status' rollup. Called once at startup.
        """
        reason = ("Interrupted — the runner process stopped before this "
                  "execution finished. Re-run the test.")
        with self._lock, self._conn() as con:
            stale = [r["id"] for r in con.execute(
                "SELECT id FROM runs WHERE status IN ('RUNNING','QUEUED')")]
            if not stale:
                return 0
            marks = ",".join("?" * len(stale))
            con.execute(
                f"UPDATE results SET status='ERROR', failure_class='INTERRUPTED',"
                f" error=? , finished_at=COALESCE(finished_at, ?)"
                f" WHERE run_id IN ({marks}) "
                f"AND status IN ('RUNNING','QUEUED')",
                (reason, time.time(), *stale))
            con.execute(
                f"UPDATE runs SET status='INTERRUPTED', "
                f"finished_at=COALESCE(finished_at, ?) WHERE id IN ({marks})",
                (time.time(), *stale))
            for run_id in stale:
                counts = {k: 0 for k in ("passed", "failed", "skipped",
                                         "errors", "blocked")}
                for row in con.execute(
                        "SELECT status, COUNT(*) n FROM results "
                        "WHERE run_id=? GROUP BY status", (run_id,)):
                    key = {"PASSED": "passed", "FAILED": "failed",
                           "SKIPPED": "skipped", "ERROR": "errors",
                           "BLOCKED": "blocked"}.get(row["status"])
                    if key:
                        counts[key] = row["n"]
                cols = ", ".join(f"{k}=?" for k in counts)
                con.execute(f"UPDATE runs SET {cols} WHERE id=?",
                            (*counts.values(), run_id))
            return len(stale)

    def _conn(self):
        con = sqlite3.connect(self.db_path, timeout=30)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        return con

    # ------------------------------------------------------------- writes
    def create_run(self, environment: str, env_name: str, mode: str,
                   group_id: str | None, label: str) -> str:
        run_id = "RUN-" + uuid.uuid4().hex[:8].upper()
        with self._lock, self._conn() as con:
            con.execute(
                "INSERT INTO runs (id,label,environment,env_name,mode,group_id,"
                "status,started_at) VALUES (?,?,?,?,?,?,?,?)",
                (run_id, label, environment, env_name, mode, group_id,
                 "QUEUED", time.time()))
        return run_id

    def update_run(self, run_id: str, **fields):
        cols = ", ".join(f"{k}=?" for k in fields)
        with self._lock, self._conn() as con:
            con.execute(f"UPDATE runs SET {cols} WHERE id=?",
                        (*fields.values(), run_id))

    def create_result(self, run_id: str, test_def, status="QUEUED") -> str:
        rid = "RES-" + uuid.uuid4().hex[:10].upper()
        with self._lock, self._conn() as con:
            con.execute(
                "INSERT INTO results (id,run_id,test_id,name,workflow,kind,"
                "priority,status,traceability) VALUES (?,?,?,?,?,?,?,?,?)",
                (rid, run_id, test_def.id, test_def.name, test_def.workflow,
                 test_def.kind, test_def.priority, status,
                 json.dumps(test_def.traceability)))
        return rid

    def update_result(self, result_id: str, **fields):
        cols = ", ".join(f"{k}=?" for k in fields)
        with self._lock, self._conn() as con:
            con.execute(f"UPDATE results SET {cols} WHERE id=?",
                        (*fields.values(), result_id))

    def save_details(self, result_id: str, steps, assertions, artifacts):
        with self._lock, self._conn() as con:
            for s in steps:
                con.execute(
                    "INSERT INTO steps (result_id,idx,name,status,duration_ms,"
                    "error) VALUES (?,?,?,?,?,?)",
                    (result_id, s.index, s.name, s.status, s.duration_ms,
                     s.error))
            for a in assertions:
                con.execute(
                    "INSERT INTO assertions (result_id,name,expected,actual,"
                    "passed) VALUES (?,?,?,?,?)",
                    (result_id, a["name"], a["expected"], a["actual"],
                     1 if a["passed"] else 0))
            for art in artifacts:
                con.execute(
                    "INSERT INTO artifacts (result_id,type,name,path) "
                    "VALUES (?,?,?,?)",
                    (result_id, art["type"], art["name"], art["path"]))

    def append_event(self, run_id: str, type_: str, payload: dict) -> int:
        with self._lock, self._conn() as con:
            cur = con.execute(
                "SELECT COALESCE(MAX(seq),0)+1 FROM events WHERE run_id=?",
                (run_id,))
            seq = cur.fetchone()[0]
            con.execute(
                "INSERT INTO events (run_id,seq,ts,type,payload) "
                "VALUES (?,?,?,?,?)",
                (run_id, seq, time.time(), type_, json.dumps(payload)))
        return seq

    # -------------------------------------------------------------- reads
    def events_since(self, run_id: str, after_seq: int) -> list[dict]:
        with self._conn() as con:
            rows = con.execute(
                "SELECT seq, ts, type, payload FROM events "
                "WHERE run_id=? AND seq>? ORDER BY seq", (run_id, after_seq))
            return [{"seq": r["seq"], "ts": r["ts"], "type": r["type"],
                     "payload": json.loads(r["payload"])} for r in rows]

    def run(self, run_id: str) -> dict | None:
        with self._conn() as con:
            r = con.execute("SELECT * FROM runs WHERE id=?",
                            (run_id,)).fetchone()
            if not r:
                return None
            run = dict(r)
            run["results"] = [dict(x) for x in con.execute(
                "SELECT * FROM results WHERE run_id=? ORDER BY rowid",
                (run_id,))]
            return run

    def runs(self, limit=50) -> list[dict]:
        with self._conn() as con:
            return [dict(r) for r in con.execute(
                "SELECT * FROM runs ORDER BY started_at DESC LIMIT ?",
                (limit,))]

    def result(self, result_id: str) -> dict | None:
        with self._conn() as con:
            r = con.execute("SELECT * FROM results WHERE id=?",
                            (result_id,)).fetchone()
            if not r:
                return None
            res = dict(r)
            res["traceability"] = json.loads(res.get("traceability") or "{}")
            res["steps"] = [dict(x) for x in con.execute(
                "SELECT * FROM steps WHERE result_id=? ORDER BY idx",
                (result_id,))]
            res["assertions"] = [dict(x) for x in con.execute(
                "SELECT * FROM assertions WHERE result_id=? ORDER BY id",
                (result_id,))]
            res["artifacts"] = [dict(x) for x in con.execute(
                "SELECT * FROM artifacts WHERE result_id=? ORDER BY id",
                (result_id,))]
            run = con.execute("SELECT * FROM runs WHERE id=?",
                              (res["run_id"],)).fetchone()
            res["run"] = dict(run) if run else None
            return res

    def artifact(self, artifact_id: int) -> dict | None:
        with self._conn() as con:
            r = con.execute("SELECT * FROM artifacts WHERE id=?",
                            (artifact_id,)).fetchone()
            return dict(r) if r else None

    def latest_status_by_test(self) -> dict:
        """test_id → {environment: {status, run_id, result_id}} for the dashboard."""
        with self._conn() as con:
            rows = con.execute("""
                SELECT res.test_id, run.environment, res.status,
                       res.run_id, res.id AS result_id, res.finished_at
                FROM results res JOIN runs run ON run.id = res.run_id
                ORDER BY res.rowid""")
            out: dict = {}
            for r in rows:
                out.setdefault(r["test_id"], {})[r["environment"]] = {
                    "status": r["status"], "run_id": r["run_id"],
                    "result_id": r["result_id"]}
            return out

    def compare_group(self, group_id: str) -> dict | None:
        with self._conn() as con:
            runs = [dict(r) for r in con.execute(
                "SELECT * FROM runs WHERE group_id=? ORDER BY started_at",
                (group_id,))]
            if not runs:
                return None
            matrix: dict = {}
            for run in runs:
                for res in con.execute(
                        "SELECT * FROM results WHERE run_id=? ORDER BY rowid",
                        (run["id"],)):
                    cell = matrix.setdefault(res["test_id"], {
                        "test_id": res["test_id"], "name": res["name"],
                        "workflow": res["workflow"], "by_env": {}})
                    cell["by_env"][run["environment"]] = {
                        "status": res["status"], "result_id": res["id"],
                        "duration_ms": res["duration_ms"],
                        "error": res["error"], "failed_step": res["failed_step"],
                        "expected": res["expected"], "actual": res["actual"],
                    }
            envs = [r["environment"] for r in runs]
            regressions = []
            for cell in matrix.values():
                statuses = {e: cell["by_env"].get(e, {}).get("status", "NOT RUN")
                            for e in envs}
                cell["statuses"] = statuses
                if len(envs) == 2:
                    a, b = envs[0], envs[1]
                    cell["classification"] = self._classify_pair(
                        statuses.get(a), statuses.get(b))
                    # kept for backward compat; a candidate is not a confirmed
                    # regression until triage
                    cell["regression"] = (cell["classification"]
                                          == "REGRESSION_CANDIDATE")
                    if cell["regression"]:
                        regressions.append(cell["test_id"])
            return {"group_id": group_id, "runs": runs, "envs": envs,
                    "tests": list(matrix.values()),
                    "regressions": regressions}

    @staticmethod
    def _classify_pair(baseline_status: str, target_status: str) -> str:
        """Cross-version outcome classification (v15 baseline vs v19 target).
        REGRESSION_CANDIDATE requires failure triage before being called a
        regression."""
        fail = ("FAILED", "ERROR")
        b, t = baseline_status, target_status
        if b == "BLOCKED" or t == "BLOCKED":
            return "BLOCKED"
        if b in ("NOT RUN", "QUEUED", "SKIPPED", None) \
                or t in ("NOT RUN", "QUEUED", "SKIPPED", None):
            return "NOT_COMPARED"
        if b == "PASSED" and t == "PASSED":
            return "SAME_BEHAVIOR"
        if b == "PASSED" and t in fail:
            return "REGRESSION_CANDIDATE"
        if b in fail and t == "PASSED":
            return "FIXED"
        if b in fail and t in fail:
            return "SAME_FAILURE"
        return "NOT_COMPARED"

    def active_runs(self, environment: str | None = None) -> list[dict]:
        """Runs still QUEUED/RUNNING — optionally for one environment.

        Test suites share fixture namespaces and sweep marker-scoped records,
        so two runs executing at once against the same database corrupt each
        other's data (observed: one run's sweep deleting another's taxes
        mid-flight). The API refuses to start an overlapping run.
        """
        sql = "SELECT * FROM runs WHERE status IN ('QUEUED','RUNNING')"
        args: list = []
        if environment:
            sql += " AND environment=?"
            args.append(environment)
        with self._conn() as con:
            return [dict(r) for r in con.execute(sql + " ORDER BY started_at", args)]

    # ------------------------------------------------- test-case registry
    def load_registry(self, registry_json: Path) -> int:
        """Upsert data/test_registry.json (generated by scripts/sync_registry.py
        from the Excel workbook — the source of truth). Expected results are
        written exactly as they appear in the JSON; nothing here edits them."""
        if not registry_json.exists():
            return 0
        data = json.loads(registry_json.read_text(encoding="utf-8"))
        with self._lock, self._conn() as con:
            for g in data.get("feature_groups", []):
                con.execute(
                    "INSERT INTO feature_groups (feature_id,name,business_purpose,"
                    "key_modules,primary_roles,in_scope) VALUES (?,?,?,?,?,?) "
                    "ON CONFLICT(feature_id) DO UPDATE SET name=excluded.name, "
                    "business_purpose=excluded.business_purpose, "
                    "key_modules=excluded.key_modules, "
                    "primary_roles=excluded.primary_roles, "
                    "in_scope=excluded.in_scope",
                    (g["feature_id"], g["name"], g["business_purpose"],
                     g["key_modules"], g["primary_roles"], int(g["in_scope"])))
            cols = ["test_case_id", "feature_id", "feature_name", "in_scope",
                    "seq", "title", "description", "feature_ref", "feature",
                    "feature_category", "priority", "test_type", "role",
                    "modules", "preconditions", "steps", "expected_result",
                    "v19_watch", "suite", "suite_name", "execution_phase",
                    "related_features", "automation_wave",
                    "automation_approach", "automation_type",
                    "automation_status", "automated_test_ids",
                    "related_test_ids", "source_notes", "source_workbook",
                    "source_sheet", "source_row", "test_execution_row"]
            update = ", ".join(f"{c}=excluded.{c}" for c in cols[1:])
            sql = (f"INSERT INTO test_cases ({','.join(cols)}) "
                   f"VALUES ({','.join('?' * len(cols))}) "
                   f"ON CONFLICT(test_case_id) DO UPDATE SET {update}")
            n = 0
            for tc in data.get("test_cases", []):
                row = dict(tc)
                row["in_scope"] = int(row.get("in_scope") or 0)
                row["automated_test_ids"] = json.dumps(row.get("automated_test_ids") or [])
                row["related_test_ids"] = json.dumps(row.get("related_test_ids") or [])
                con.execute(sql, tuple(row.get(c) for c in cols))
                n += 1
            return n

    def _tc_execution_index(self, con) -> dict:
        """tc_id → {environment → latest {status, canonical, result_id, run_id,
        finished_at}} built from every persisted result's traceability block."""
        rows = con.execute("""
            SELECT res.id AS result_id, res.run_id, res.status, res.traceability,
                   res.finished_at, res.started_at, run.environment
            FROM results res JOIN runs run ON run.id = res.run_id
            ORDER BY res.rowid""")
        index: dict = {}
        for r in rows:
            try:
                tc_ids = json.loads(r["traceability"] or "{}").get("tc_ids", [])
            except (ValueError, TypeError):
                tc_ids = []
            for raw in tc_ids:
                m = _TC_ID_RE.search(str(raw))
                if not m:
                    continue
                index.setdefault(m.group(0), {})[r["environment"]] = {
                    "status": r["status"],
                    "canonical": CANONICAL_STATUS.get(r["status"], r["status"]),
                    "result_id": r["result_id"], "run_id": r["run_id"],
                    "finished_at": r["finished_at"],
                }
        return index

    def _tc_row_public(self, r, exec_index) -> dict:
        tc = dict(r)
        tc["automated_test_ids"] = json.loads(tc.get("automated_test_ids") or "[]")
        tc["related_test_ids"] = json.loads(tc.get("related_test_ids") or "[]")
        by_env = exec_index.get(tc["test_case_id"], {})
        v15 = by_env.get("odoo15")
        v19 = by_env.get("odoo19")
        not_run = ("NOT_RUN" if tc["automation_status"] == "AUTOMATED"
                   else "NOT_IMPLEMENTED"
                   if tc["automation_type"] != "MANUAL" else "MANUAL")
        tc["v15_status"] = v15["canonical"] if v15 else not_run
        tc["v19_status"] = v19["canonical"] if v19 else not_run
        latest = max((x for x in (v15, v19) if x),
                     key=lambda x: x["finished_at"] or 0, default=None)
        tc["last_execution_id"] = latest["result_id"] if latest else None
        tc["executions_by_env"] = by_env
        return tc

    def feature_summary(self, in_scope_only: bool = True) -> list[dict]:
        """Per feature group: counts, automation coverage, v15/v19 rollups."""
        with self._conn() as con:
            exec_index = self._tc_execution_index(con)
            groups = [dict(g) for g in con.execute(
                "SELECT * FROM feature_groups"
                + (" WHERE in_scope=1" if in_scope_only else "")
                + " ORDER BY feature_id")]
            out = []
            for g in groups:
                tcs = [self._tc_row_public(r, exec_index) for r in con.execute(
                    "SELECT * FROM test_cases WHERE feature_id=? ORDER BY seq",
                    (g["feature_id"],))]
                summary = {
                    "total": len(tcs),
                    "priorities": {}, "automation_types": {},
                    "automation_statuses": {},
                    "v15": {}, "v19": {},
                }
                for tc in tcs:
                    for key, field_ in (("priorities", "priority"),
                                        ("automation_types", "automation_type"),
                                        ("automation_statuses", "automation_status")):
                        v = tc[field_] or "?"
                        summary[key][v] = summary[key].get(v, 0) + 1
                    for env in ("v15", "v19"):
                        s = tc[f"{env}_status"]
                        summary[env][s] = summary[env].get(s, 0) + 1
                automatable = sum(v for k, v in summary["automation_types"].items()
                                  if k not in ("MANUAL", "NOT_APPLICABLE"))
                automated = summary["automation_statuses"].get("AUTOMATED", 0)
                summary["automatable"] = automatable
                summary["automated"] = automated
                summary["coverage_pct"] = round(100 * automated / automatable, 1) \
                    if automatable else 0.0
                out.append({**g, **summary})
            return out

    def test_cases_list(self, feature_id: str | None = None,
                        in_scope_only: bool = True) -> list[dict]:
        with self._conn() as con:
            exec_index = self._tc_execution_index(con)
            sql, args = "SELECT * FROM test_cases", []
            where = []
            if feature_id:
                where.append("feature_id=?")
                args.append(feature_id)
            if in_scope_only:
                where.append("in_scope=1")
            if where:
                sql += " WHERE " + " AND ".join(where)
            sql += " ORDER BY seq"
            return [self._tc_row_public(r, exec_index)
                    for r in con.execute(sql, args)]

    def test_case(self, tc_id: str) -> dict | None:
        with self._conn() as con:
            r = con.execute("SELECT * FROM test_cases WHERE test_case_id=?",
                            (tc_id,)).fetchone()
            if not r:
                return None
            exec_index = self._tc_execution_index(con)
            tc = self._tc_row_public(r, exec_index)
            # full execution history for this TC (any result whose
            # traceability names it)
            history = []
            for row in con.execute("""
                SELECT res.*, run.environment, run.env_name
                FROM results res JOIN runs run ON run.id = res.run_id
                ORDER BY res.rowid DESC"""):
                try:
                    tc_ids = json.loads(row["traceability"] or "{}").get("tc_ids", [])
                except (ValueError, TypeError):
                    tc_ids = []
                if any(_TC_ID_RE.search(str(x)) and
                       _TC_ID_RE.search(str(x)).group(0) == tc_id
                       for x in tc_ids):
                    h = dict(row)
                    h["canonical"] = CANONICAL_STATUS.get(h["status"], h["status"])
                    h.pop("traceability", None)
                    history.append(h)
            tc["executions"] = history
            return tc
