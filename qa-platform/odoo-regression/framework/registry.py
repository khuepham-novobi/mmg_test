"""Test-case registry.

Tests self-register with the @test_case decorator. The web UI, the API and
the execution engine all read from this registry — adding a test file under
tests/ makes it appear in the dashboard with zero UI changes.

Every entry carries traceability back to the Excel knowledge base
(MMG_v19_Test_Cases_Grouped_by_Feature_v2.0.xlsx) via tc_ids.
"""
from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class TestCaseDef:
    id: str
    name: str
    func: Callable
    workflow: str = ""
    workflow_name: str = ""
    module: str = ""
    priority: str = "P2"
    kind: str = "API"           # UI | API | HYBRID
    order: int = 100
    description: str = ""
    traceability: dict = field(default_factory=dict)  # excel tc_ids, feature, user_story

    def public_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "workflow": self.workflow,
            "workflow_name": self.workflow_name, "module": self.module,
            "priority": self.priority, "kind": self.kind,
            "description": self.description, "traceability": self.traceability,
        }


_REGISTRY: dict[str, TestCaseDef] = {}


def test_case(**meta):
    def wrapper(func):
        tc = TestCaseDef(func=func, **meta)
        if tc.id in _REGISTRY:
            raise ValueError(f"Duplicate test id: {tc.id}")
        _REGISTRY[tc.id] = tc
        return func
    return wrapper


def discover() -> list[TestCaseDef]:
    """Import every module under tests/ so decorators run, then return
    the registry ordered for execution."""
    import tests as tests_pkg
    for mod in pkgutil.walk_packages(tests_pkg.__path__, prefix="tests."):
        if not mod.ispkg:
            importlib.import_module(mod.name)
    return sorted(_REGISTRY.values(), key=lambda t: (t.order, t.id))


def reload() -> list[TestCaseDef]:
    """Drop the registry and re-import every test module from disk.

    Lets the platform pick up newly added or edited test scripts without a
    server restart (POST /api/registry/reload).
    """
    import sys
    _REGISTRY.clear()
    for name in [n for n in sys.modules
                 if n == "tests" or n.startswith("tests.")]:
        del sys.modules[name]
    importlib.invalidate_caches()
    return discover()


def get(test_id: str) -> TestCaseDef:
    if not _REGISTRY:
        discover()
    return _REGISTRY[test_id]
