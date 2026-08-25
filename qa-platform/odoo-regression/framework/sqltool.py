"""Direct PostgreSQL access for DATA_RECONCILIATION tests.

Strictly read-only by convention: reconciliation tests only SELECT. The
connection is opened in autocommit with default_transaction_read_only so a
stray write raises instead of mutating the target database.
"""
from __future__ import annotations

import csv
from pathlib import Path

from backend.config import EnvironmentConfig


class SqlUnavailable(RuntimeError):
    """No pg_* config for this environment — SQL tests must go BLOCKED."""


class SqlTool:
    def __init__(self, env: EnvironmentConfig):
        if not env.pg_host or not env.pg_user:
            raise SqlUnavailable(
                f"No PostgreSQL access configured for environment "
                f"'{env.key}' (set ODOO{env.version}_PG_HOST/_PG_USER/"
                f"_PG_PASSWORD)")
        import psycopg2
        self.env = env
        self._con = psycopg2.connect(
            host=env.pg_host, port=env.pg_port, user=env.pg_user,
            password=env.pg_password, dbname=env.db,
            options="-c default_transaction_read_only=on")
        self._con.autocommit = True

    def rows(self, query: str, params=None) -> list[tuple]:
        with self._con.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchall()

    def one(self, query: str, params=None):
        """First column of the first row."""
        res = self.rows(query, params)
        return res[0][0] if res else None

    def to_csv(self, query: str, out_path: Path, params=None) -> int:
        """Run a query and stream the result to a CSV file. Returns row count."""
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with self._con.cursor() as cur, \
                open(out_path, "w", newline="", encoding="utf-8") as fh:
            cur.execute(query, params)
            writer = csv.writer(fh)
            writer.writerow([d[0] for d in cur.description])
            n = 0
            for row in cur:
                writer.writerow(row)
                n += 1
            return n

    def column_exists(self, table: str, column: str) -> bool:
        return bool(self.one(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name=%s AND column_name=%s", (table, column)))

    def close(self):
        try:
            self._con.close()
        except Exception:
            pass
