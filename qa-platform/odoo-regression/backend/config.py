"""Configuration: .env + config/environments.yaml.

Nothing is hard-coded: URLs, databases and credentials come from environment
variables (see .env.example), referenced from environments.yaml as ${VAR:default}.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _load_local_overrides():
    """Machine-local overrides from config/local.yaml (not committed).

    Lets a workstation point the runner at its own QA clone — and supply the
    read-only PostgreSQL credentials the DATA_RECONCILIATION tests need —
    without editing the shared .env. Values win over .env, and real
    environment variables still win over both.
    """
    path = ROOT / "config" / "local.yaml"
    if not path.exists():
        return
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    for key, value in (data.get("env") or {}).items():
        if value is not None:
            os.environ[str(key)] = str(value)


_load_local_overrides()

_VAR_RE = re.compile(r"\$\{([A-Z0-9_]+)(?::([^}]*))?\}")


def _interpolate(value):
    if isinstance(value, str):
        def repl(m):
            return os.environ.get(m.group(1), m.group(2) or "")
        return _VAR_RE.sub(repl, value)
    if isinstance(value, dict):
        return {k: _interpolate(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_interpolate(v) for v in value]
    return value


@dataclass
class EnvironmentConfig:
    key: str                 # "odoo15" | "odoo19"
    name: str                # display name
    version: str             # "15" | "19"
    base_url: str
    db: str
    username: str
    password: str = field(repr=False, default="")
    # Direct PostgreSQL access for DATA_RECONCILIATION tests (optional —
    # tests that need SQL are BLOCKED when pg_host is empty).
    pg_host: str = ""
    pg_port: int = 5432
    pg_user: str = ""
    pg_password: str = field(repr=False, default="")

    def public_dict(self) -> dict:
        """Safe to expose to the UI — never leaks credentials."""
        return {
            "key": self.key,
            "name": self.name,
            "version": self.version,
            "base_url": self.base_url,
            "db": self.db,
        }


def load_environments() -> dict[str, EnvironmentConfig]:
    cfg_file = ROOT / "config" / "environments.yaml"
    raw = yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
    envs: dict[str, EnvironmentConfig] = {}
    for key, e in _interpolate(raw)["environments"].items():
        envs[key] = EnvironmentConfig(
            key=key,
            name=e.get("name", key),
            version=str(e["version"]),
            base_url=e["base_url"].rstrip("/"),
            db=e["db"],
            username=e["username"],
            password=e["password"],
            pg_host=e.get("pg_host", ""),
            pg_port=int(e.get("pg_port") or 5432),
            pg_user=e.get("pg_user", ""),
            pg_password=e.get("pg_password", ""),
        )
    return envs


def _flag(name: str, default: str = "false") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Settings:
    headless: bool = _flag("HEADLESS", "true")
    slow_mo_ms: int = int(os.environ.get("SLOWMO", "0"))
    timeout_ms: int = int(os.environ.get("TIMEOUT_MS", "30000"))
    nav_timeout_ms: int = int(os.environ.get("NAV_TIMEOUT_MS", "60000"))
    trace: str = os.environ.get("TRACE", "retain-on-failure")  # off|on|retain-on-failure
    video: bool = _flag("VIDEO", "false")
    screenshot_on_success: bool = _flag("SCREENSHOT_ON_SUCCESS", "true")
    artifacts_dir: Path = ROOT / os.environ.get("ARTIFACTS_DIR", "artifacts")
    data_dir: Path = ROOT / os.environ.get("DATA_DIR", "data")
    server_host: str = os.environ.get("RUNNER_HOST", "127.0.0.1")
    server_port: int = int(os.environ.get("RUNNER_PORT", "8000"))


settings = Settings()
settings.artifacts_dir.mkdir(parents=True, exist_ok=True)
settings.data_dir.mkdir(parents=True, exist_ok=True)
