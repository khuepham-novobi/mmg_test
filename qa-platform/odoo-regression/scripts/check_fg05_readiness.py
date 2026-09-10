"""FG-05 readiness check — run this BEFORE clicking Run in the web UI.

Answers one question: *if I run the 14 FG-05 AvaTax cases right now, what
will happen?* Every condition it checks is one the suite itself gates on, so
a clean report here means the tests will actually exercise tax computation
instead of reporting BLOCKED.

    venv\\Scripts\\python.exe scripts\\check_fg05_readiness.py

THIN WRAPPER. The checks themselves now live in ``scripts/check_readiness.py``
alongside FG-06, FG-07 and FG-08, and this file runs its FG-05 section — the
same conditions, the same output, the same exit codes — so the command in
CLAUDE.md §4 and docs/FG-05_MANUAL_GUIDELINE_SUITE.md keeps working unchanged.

For the other three groups, or all four in one pass:

    venv\\Scripts\\python.exe scripts\\check_readiness.py
    venv\\Scripts\\python.exe scripts\\check_readiness.py FG-06 FG-07

Read-only: it creates nothing, writes nothing, and never calls Avalara.
Exit code 0 = ready, 1 = something would block or fail.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_readiness import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(["FG-05"]))
