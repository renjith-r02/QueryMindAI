"""Run generated SQL against the configured databases.

Each logical database name used in the schema files (e.g. ``ecommerce``,
``returns_db``) maps to a SQLAlchemy URL in an environment variable
``QUERYMIND_DB_<NAME>``, for example::

    QUERYMIND_DB_ECOMMERCE=mysql+pymysql://user:pass@localhost:3306/ecommerce
    QUERYMIND_DB_RETURNS_DB=postgresql+psycopg://user:pass@localhost:5432/returns_db

Every query runs in a read-only transaction with a statement timeout, and at
most ``max_rows`` rows are fetched.
"""

from __future__ import annotations

import datetime as dt
import os
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from querymind.database.safety import UnsafeQueryError, ensure_read_only

ENV_PREFIX = "QUERYMIND_DB_"
_SYSTEM_SCHEMAS = {"information_schema", "pg_catalog", "pg_toast", "mysql", "performance_schema", "sys"}


@dataclass
class QueryResult:
    database: str
    sql: str
    columns: list[str] = field(default_factory=list)
    rows: list[list[Any]] = field(default_factory=list)
    truncated: bool = False
    elapsed_ms: float = 0.0
    error: str | None = None
    # "database" errors (bad SQL) and "unsafe" queries can be repaired by the
    # model; "config" errors (no connection configured) cannot.
    error_kind: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> QueryResult:
        return cls(**data)


class DatabaseRegistry:
    def __init__(self, urls: dict[str, str], max_rows: int = 1000, timeout_seconds: int = 30):
        self.urls = {name.lower(): url for name, url in urls.items()}
        self.max_rows = max_rows
        self.timeout_ms = timeout_seconds * 1000
        self._engines: dict[str, Engine] = {}
        self._objects: dict[str, list[str]] = {}

    @classmethod
    def from_env(cls, **kwargs) -> DatabaseRegistry:
        urls = {
            key[len(ENV_PREFIX) :]: value for key, value in os.environ.items() if key.startswith(ENV_PREFIX) and value
        }
        return cls(urls, **kwargs)

    def with_limits(self, max_rows: int, timeout_seconds: int) -> DatabaseRegistry:
        """A registry with other limits that reuses this one's engines and schema cache."""
        clone = DatabaseRegistry(self.urls, max_rows=max_rows, timeout_seconds=timeout_seconds)
        clone._engines = self._engines
        clone._objects = self._objects
        return clone

    def dispose(self) -> None:
        """Close pooled connections (when the registry is replaced)."""
        for engine in self._engines.values():
            engine.dispose()
        self._engines.clear()
        self._objects.clear()

    @property
    def names(self) -> list[str]:
        return sorted(self.urls)

    def engine(self, name: str) -> Engine:
        if name not in self._engines:
            self._engines[name] = create_engine(self.urls[name], pool_pre_ping=True)
        return self._engines[name]

    def dialect(self, name: str) -> str:
        return self.engine(name).dialect.name

    def objects(self, name: str) -> list[str]:
        """Tables and views that really exist, e.g. ['rma.returns', 'v_order_line_sales (view)']."""
        if name not in self._objects:
            inspector = inspect(self.engine(name))
            default_schema = inspector.default_schema_name
            found = []
            for schema in inspector.get_schema_names():
                if schema in _SYSTEM_SCHEMAS or (self.dialect(name) == "mysql" and schema != default_schema):
                    continue
                prefix = "" if schema == default_schema else f"{schema}."
                found += [f"{prefix}{t}" for t in inspector.get_table_names(schema=schema)]
                found += [f"{prefix}{v} (view)" for v in inspector.get_view_names(schema=schema)]
            self._objects[name] = sorted(found)
        return self._objects[name]

    def execute(self, name: str, sql: str) -> QueryResult:
        name = name.lower()
        if name not in self.urls:
            return QueryResult(
                name,
                sql,
                error=f"No connection configured for database '{name}' (add it in Settings, or set "
                f"{ENV_PREFIX}{name.upper()} in .env)",
                error_kind="config",
            )
        try:
            statement = ensure_read_only(sql)
        except UnsafeQueryError as error:
            return QueryResult(name, sql, error=f"Refused to run query: {error}", error_kind="unsafe")

        started = time.perf_counter()
        try:
            with self.engine(name).connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                self._begin_read_only(conn, self.dialect(name))
                try:
                    cursor = conn.execute(text(statement))
                    columns = list(cursor.keys())
                    rows = cursor.fetchmany(self.max_rows + 1)
                finally:
                    conn.exec_driver_sql("ROLLBACK")
        except SQLAlchemyError as error:
            message = str(getattr(error, "orig", None) or error).strip()
            return QueryResult(name, sql, error=message, error_kind="database", elapsed_ms=_elapsed(started))

        return QueryResult(
            name,
            sql,
            columns=columns,
            rows=[[_plain(value) for value in row] for row in rows[: self.max_rows]],
            truncated=len(rows) > self.max_rows,
            elapsed_ms=_elapsed(started),
        )

    def _begin_read_only(self, conn, dialect: str) -> None:
        if dialect == "mysql":
            conn.exec_driver_sql(f"SET SESSION MAX_EXECUTION_TIME = {self.timeout_ms}")
            conn.exec_driver_sql("START TRANSACTION READ ONLY")
        elif dialect == "postgresql":
            conn.exec_driver_sql(f"SET statement_timeout = {self.timeout_ms}")
            conn.exec_driver_sql("BEGIN READ ONLY")
        elif dialect == "sqlite":
            conn.exec_driver_sql("PRAGMA query_only = ON")
            conn.exec_driver_sql("BEGIN")
        else:
            conn.exec_driver_sql("BEGIN")


def merge_results(results: list[QueryResult], merge_sql: str) -> QueryResult:
    """Combine several result sets with a SQLite query over tables q1, q2, ..."""
    try:
        statement = ensure_read_only(merge_sql)
    except UnsafeQueryError as error:
        return QueryResult("merge", merge_sql, error=f"Refused to run merge: {error}", error_kind="unsafe")

    started = time.perf_counter()
    connection = sqlite3.connect(":memory:")
    try:
        for index, result in enumerate(results, start=1):
            columns = ", ".join(_quote(c) for c in _unique(result.columns))
            connection.execute(f"CREATE TABLE q{index} ({columns})")
            placeholders = ", ".join("?" for _ in result.columns)
            connection.executemany(f"INSERT INTO q{index} VALUES ({placeholders})", result.rows)
        cursor = connection.execute(statement)
        columns = [description[0] for description in cursor.description or []]
        rows = [list(row) for row in cursor.fetchall()]
    except sqlite3.Error as error:
        return QueryResult("merge", merge_sql, error=str(error), error_kind="database", elapsed_ms=_elapsed(started))
    finally:
        connection.close()
    return QueryResult(
        "merge",
        merge_sql,
        columns=columns,
        rows=rows,
        truncated=any(r.truncated for r in results),
        elapsed_ms=_elapsed(started),
    )


def _plain(value: Any) -> Any:
    """Convert driver types to JSON- and SQLite-friendly values."""
    if isinstance(value, Decimal):
        # MySQL returns SUM(int) as Decimal('14'); keep such values integral.
        return int(value) if value.as_tuple().exponent >= 0 else float(value)
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return value.isoformat()
    if isinstance(value, dt.timedelta):
        return value.total_seconds()
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex()
    return value


def _unique(columns: list[str]) -> list[str]:
    """Suffix duplicate column names (name, name_2, ...) so SQLite accepts them."""
    seen: dict[str, int] = {}
    unique = []
    for column in columns:
        seen[column] = seen.get(column, 0) + 1
        unique.append(column if seen[column] == 1 else f"{column}_{seen[column]}")
    return unique


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _elapsed(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)
