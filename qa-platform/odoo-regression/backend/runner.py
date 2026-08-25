"""Execution engine.

A run executes on a worker thread: tests run sequentially (deterministic MVP;
the event/result model is already per-test, so parallel workers can be added
without changing the API or the UI). Every state change is BOTH persisted and
appended to the run's event log — the UI numbers are read back from the same
rows the engine wrote; nothing is synthesized.

Failure policy (PART 25): an exception in one test marks that test
FAILED/ERROR with artifacts captured, and the run continues with the next test.
"""
from __future__ import annotations

import threading
import time
import traceback

from backend.config import load_environments, settings
from backend.store import Store
from framework.context import (AssertionFailed, BlockedTest, SkipTest,
                               TestContext)
from framework.registry import TestCaseDef

_CANCELLED: set[str] = set()


def cancel_run(run_id: str):
    _CANCELLED.add(run_id)


class RunExecutor(threading.Thread):
    def __init__(self, store: Store, run_id: str, env_key: str,
                 tests: list[TestCaseDef]):
        super().__init__(daemon=True, name=f"runner-{run_id}")
        self.store = store
        self.run_id = run_id
        self.env_key = env_key
        self.tests = tests

    # ------------------------------------------------------------ helpers
    def emit(self, type_: str, payload: dict | None = None):
        self.store.append_event(self.run_id, type_, payload or {})

    # --------------------------------------------------------------- main
    def run(self):
        envs = load_environments()
        env = envs[self.env_key]
        store = self.store
        run_started = time.time()
        counts = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0,
                  "blocked": 0}

        store.update_run(self.run_id, status="RUNNING", started_at=run_started,
                         total=len(self.tests))
        self.emit("RUN_STARTED", {
            "run_id": self.run_id, "environment": self.env_key,
            "env_name": env.name, "total": len(self.tests),
            "tests": [t.id for t in self.tests]})

        # result rows exist upfront so the UI can show the full QUEUED list
        result_ids = {t.id: store.create_result(self.run_id, t) for t in self.tests}

        # Preflight: if the target environment is unreachable, every execution
        # is BLOCKED (environment problem), not ERROR (test problem).
        preflight_error = ""
        try:
            from adapters import get_adapter
            version = get_adapter(env).rpc.server_version()
            self.emit("LOG", {"message": f"Preflight OK — server version {version}"})
        except Exception as exc:  # noqa: BLE001
            preflight_error = (f"Environment '{env.name}' unreachable at "
                               f"{env.base_url}: {exc}")
        if preflight_error:
            now = time.time()
            for test in self.tests:
                store.update_result(
                    result_ids[test.id], status="BLOCKED", started_at=now,
                    finished_at=now, duration_ms=0, error=preflight_error,
                    skip_reason=preflight_error, failure_class="ENVIRONMENT")
                counts["blocked"] += 1
                self.emit("TEST_BLOCKED", {
                    "test_id": test.id, "result_id": result_ids[test.id],
                    "status": "BLOCKED", "duration_ms": 0,
                    "error": preflight_error, "failed_step": "",
                    "expected": "", "actual": "",
                    "skip_reason": preflight_error, **counts,
                    "done": counts["blocked"], "total": len(self.tests)})
            store.update_run(self.run_id, status="COMPLETED",
                             finished_at=time.time(), **counts)
            self.emit("RUN_COMPLETED", {
                "status": "COMPLETED",
                "duration_ms": int((time.time() - run_started) * 1000),
                "total": len(self.tests), **counts})
            return

        for index, test in enumerate(self.tests, start=1):
            if self.run_id in _CANCELLED:
                for remaining in self.tests[index - 1:]:
                    store.update_result(result_ids[remaining.id],
                                        status="SKIPPED",
                                        skip_reason="Run cancelled")
                    counts["skipped"] += 1
                self.emit("RUN_CANCELLED", {})
                break

            result_id = result_ids[test.id]
            started = time.time()
            store.update_result(result_id, status="RUNNING", started_at=started)
            self.emit("TEST_STARTED", {
                "test_id": test.id, "result_id": result_id, "name": test.name,
                "index": index, "total": len(self.tests), "kind": test.kind})

            artifacts_dir = (settings.artifacts_dir / self.run_id / test.id)
            ctx = TestContext(
                test, env, artifacts_dir,
                emit=lambda type_, payload, _tid=test.id, _rid=result_id:
                    self.emit(type_, {"test_id": _tid, "result_id": _rid,
                                      **payload}))

            status, error, expected, actual, skip_reason = \
                "PASSED", "", "", "", ""
            failure_class = "NONE"
            try:
                test.func(ctx)
            except SkipTest as exc:
                status, skip_reason = "SKIPPED", str(exc)
            except BlockedTest as exc:
                status, error = "BLOCKED", str(exc)
                failure_class = "BLOCKED"
            except AssertionFailed as exc:
                status, error = "FAILED", str(exc)
                expected, actual = repr(exc.expected), repr(exc.actual)
                failure_class = "ASSERTION"
            except Exception as exc:  # noqa: BLE001 — anything else = ERROR
                status = "ERROR"
                error = f"{type(exc).__name__}: {exc}"
                # connection-level failures are an environment problem, not a
                # product or script defect
                failure_class = ("ENVIRONMENT" if isinstance(
                    exc, (ConnectionError, OSError, TimeoutError))
                    or "WinError" in str(exc) or "Connection" in str(exc)
                    else "AUTOMATION_ERROR")
                ctx.log("TRACEBACK:\n" + traceback.format_exc())
            finally:
                ctx.close(failed=status in ("FAILED", "ERROR", "BLOCKED"))
                ctx.write_log_artifact()

            duration_ms = int((time.time() - started) * 1000)
            counts["passed" if status == "PASSED" else
                   "failed" if status == "FAILED" else
                   "skipped" if status == "SKIPPED" else
                   "blocked" if status == "BLOCKED"
                   else "errors"] += 1

            store.update_result(
                result_id, status=status, finished_at=time.time(),
                duration_ms=duration_ms, error=error,
                failed_step=ctx.failed_step, expected=expected, actual=actual,
                skip_reason=skip_reason, failure_class=failure_class)
            store.save_details(result_id, ctx.steps, ctx.assertions,
                               ctx.artifacts)
            store.update_run(self.run_id, **counts)

            self.emit({"PASSED": "TEST_PASSED", "FAILED": "TEST_FAILED",
                       "SKIPPED": "TEST_SKIPPED", "ERROR": "TEST_ERROR",
                       "BLOCKED": "TEST_BLOCKED"}[status],
                      {"test_id": test.id, "result_id": result_id,
                       "status": status, "duration_ms": duration_ms,
                       "error": error, "failed_step": ctx.failed_step,
                       "expected": expected, "actual": actual,
                       "skip_reason": skip_reason, **counts,
                       "done": index, "total": len(self.tests)})

        final = "CANCELLED" if self.run_id in _CANCELLED else "COMPLETED"
        store.update_run(self.run_id, status=final, finished_at=time.time(),
                         **counts)
        self.emit("RUN_COMPLETED", {
            "status": final, "duration_ms": int((time.time() - run_started) * 1000),
            "total": len(self.tests), **counts})
        _CANCELLED.discard(self.run_id)


class ChainedExecutor(threading.Thread):
    """'Both' mode: run the same tests on Odoo 15 then Odoo 19, one after the
    other, as two real runs sharing a comparison group."""

    def __init__(self, executors: list[RunExecutor]):
        super().__init__(daemon=True, name="runner-chain")
        self.executors = executors

    def run(self):
        for ex in self.executors:
            ex.run()  # run inline (sequential), not as a separate thread
