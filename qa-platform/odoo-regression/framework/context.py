"""TestContext — everything a test needs, with full result recording.

A test receives one ``ctx`` and expresses business behavior:

    with ctx.step("Confirm order"):
        ctx.adapter.confirm_order(order_id)
    ctx.check("Order state", expected="sale", actual=data["state"])

The context records every step, assertion, log line and artifact; the runner
persists them and streams events to the UI. Browser pages are created lazily —
API-only tests never pay the browser startup cost.
"""
from __future__ import annotations

import time
import traceback
from contextlib import contextmanager
from pathlib import Path

from backend.config import EnvironmentConfig, settings
from adapters import get_adapter


class AssertionFailed(AssertionError):
    def __init__(self, name: str, expected, actual):
        self.name, self.expected, self.actual = name, expected, actual
        super().__init__(f"{name}: expected {expected!r}, got {actual!r}")


class SkipTest(Exception):
    """Raise (via ctx.skip) to mark a test SKIPPED with a recorded reason."""


class BlockedTest(Exception):
    """Raise (via ctx.blocked) when a precondition outside the test's control
    is not met — unreachable environment, missing module, missing fixture.
    The execution is recorded as BLOCKED (not FAILED)."""


class StepRecord:
    def __init__(self, index: int, name: str):
        self.index = index
        self.name = name
        self.status = "RUNNING"
        self.started_at = time.time()
        self.duration_ms = 0
        self.error = ""

    def finish(self, status: str, error: str = ""):
        self.status = status
        self.error = error
        self.duration_ms = int((time.time() - self.started_at) * 1000)


class TestContext:
    def __init__(self, test_def, env: EnvironmentConfig, artifacts_dir: Path,
                 emit=lambda type_, payload: None):
        self.test_def = test_def
        self.env = env
        self.adapter = get_adapter(env)
        self.artifacts_dir = artifacts_dir
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        self._emit = emit

        self.steps: list[StepRecord] = []
        self.assertions: list[dict] = []
        self.artifacts: list[dict] = []
        self.log_lines: list[str] = []
        self.failed_step: str = ""

        # Playwright state (lazy)
        self._pw = None
        self._browser = None
        self._context = None
        self.page = None
        self._tracing = False
        self._sql = None

    @property
    def sql(self):
        """Direct read-only SQL access for DATA_RECONCILIATION tests.
        Raises BlockedTest (→ BLOCKED) when the environment has no pg_*
        configuration."""
        if self._sql is None:
            from framework.sqltool import SqlTool, SqlUnavailable
            try:
                self._sql = SqlTool(self.env)
            except SqlUnavailable as exc:
                self.blocked(str(exc))
        return self._sql

    # ------------------------------------------------------------ logging
    def log(self, message: str):
        line = f"[{time.strftime('%H:%M:%S')}] {message}"
        self.log_lines.append(line)
        self._emit("LOG", {"message": line})

    # -------------------------------------------------------------- steps
    @contextmanager
    def step(self, name: str):
        rec = StepRecord(len(self.steps) + 1, name)
        self.steps.append(rec)
        self.log(f"STEP {rec.index}: {name}")
        self._emit("STEP_STARTED", {"index": rec.index, "name": name,
                                    "total_steps": None})
        try:
            yield rec
        except (SkipTest, BlockedTest) as exc:
            # a skip/block is a verdict about preconditions, not a failed
            # step: leaving it to the generic handler below would mark the
            # step FAILED and set failed_step, which reads as a defect
            rec.finish("SKIPPED", error="")
            self._emit("STEP_SKIPPED", {"index": rec.index, "name": name,
                                        "reason": str(exc)})
            raise
        except Exception as exc:
            rec.finish("FAILED", error=str(exc))
            self.failed_step = name
            self._emit("STEP_FAILED", {"index": rec.index, "name": name,
                                       "error": str(exc)})
            raise
        else:
            rec.finish("PASSED")
            self._emit("STEP_PASSED", {"index": rec.index, "name": name,
                                       "duration_ms": rec.duration_ms})

    # --------------------------------------------------------- assertions
    def check(self, name: str, expected, actual):
        passed = expected == actual
        self.assertions.append({"name": name, "expected": repr(expected),
                                "actual": repr(actual), "passed": passed})
        self._emit("ASSERTION", {"name": name, "expected": repr(expected),
                                 "actual": repr(actual), "passed": passed})
        if not passed:
            raise AssertionFailed(name, expected, actual)
        self.log(f"ASSERT OK — {name}: {actual!r}")

    def check_true(self, name: str, condition: bool, actual_desc: str = ""):
        self.check(name, True, bool(condition)) if not actual_desc else None
        if actual_desc:
            self.assertions.append({"name": name, "expected": "True",
                                    "actual": actual_desc, "passed": bool(condition)})
            self._emit("ASSERTION", {"name": name, "expected": "True",
                                     "actual": actual_desc,
                                     "passed": bool(condition)})
            if not condition:
                raise AssertionFailed(name, True, actual_desc)
            self.log(f"ASSERT OK — {name}")

    def skip(self, reason: str):
        self.log(f"SKIP — {reason}")
        raise SkipTest(reason)

    def blocked(self, reason: str):
        self.log(f"BLOCKED — {reason}")
        raise BlockedTest(reason)

    # ---------------------------------------------------------- artifacts
    def add_artifact(self, path: Path, type_: str, name: str = ""):
        self.artifacts.append({"path": str(path), "type": type_,
                               "name": name or path.name})
        self._emit("ARTIFACT", {"type": type_, "name": name or path.name})

    # ------------------------------------------------------------ browser
    def browser_page(self):
        """Launch Chromium (honouring HEADLESS/SLOWMO/TRACE/VIDEO) and return
        a Playwright page wired for console-log capture."""
        if self.page:
            return self.page
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=settings.headless, slow_mo=settings.slow_mo_ms)
        ctx_kwargs = {"viewport": {"width": 1440, "height": 900}}
        if settings.video:
            ctx_kwargs["record_video_dir"] = str(self.artifacts_dir)
        self._context = self._browser.new_context(**ctx_kwargs)
        self._context.set_default_timeout(settings.timeout_ms)
        self._context.set_default_navigation_timeout(settings.nav_timeout_ms)
        if settings.trace in ("on", "retain-on-failure"):
            self._context.tracing.start(screenshots=True, snapshots=True,
                                        sources=False)
            self._tracing = True
        self.page = self._context.new_page()
        self.page.on("console", lambda msg: self.log_lines.append(
            f"[console:{msg.type}] {msg.text[:500]}"))
        self.page.on("pageerror", lambda err: self.log_lines.append(
            f"[pageerror] {str(err)[:500]}"))
        return self.page

    def screenshot(self, name: str) -> Path | None:
        if not self.page:
            return None
        path = self.artifacts_dir / f"{name}.png"
        try:
            self.page.screenshot(path=str(path), full_page=True)
        except Exception:
            return None
        self.add_artifact(path, "screenshot", name)
        return path

    def _save_trace(self, keep: bool):
        if not (self._context and self._tracing):
            return
        path = self.artifacts_dir / "trace.zip"
        try:
            self._context.tracing.stop(path=str(path) if keep else None)
            if keep and path.exists():
                self.add_artifact(path, "trace", "Playwright trace")
        except Exception:
            pass
        self._tracing = False

    def close(self, failed: bool):
        """Finalize artifacts and shut the browser down safely."""
        if self._sql is not None:
            self._sql.close()
            self._sql = None
        try:
            if self.page:
                if failed:
                    self.screenshot("failure")
                elif settings.screenshot_on_success:
                    self.screenshot("final-state")
            keep_trace = settings.trace == "on" or (
                settings.trace == "retain-on-failure" and failed)
            self._save_trace(keep_trace)
            if self._context and settings.video:
                video = self.page.video if self.page else None
                self._context.close()
                self._context = None
                if video:
                    try:
                        self.add_artifact(Path(video.path()), "video", "Recording")
                    except Exception:
                        pass
        except Exception:
            self.log_lines.append("[warn] artifact finalization error:\n"
                                  + traceback.format_exc()[-800:])
        finally:
            for closer in (self._context, self._browser):
                try:
                    if closer:
                        closer.close()
                except Exception:
                    pass
            if self._pw:
                try:
                    self._pw.stop()
                except Exception:
                    pass
            self._pw = self._browser = self._context = self.page = None

    def write_log_artifact(self):
        path = self.artifacts_dir / "execution.log"
        path.write_text("\n".join(self.log_lines), encoding="utf-8")
        self.add_artifact(path, "log", "Execution log")
