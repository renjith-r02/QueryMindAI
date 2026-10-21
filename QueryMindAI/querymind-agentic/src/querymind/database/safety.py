"""Static checks for model-generated SQL before it is executed.

These are a first line of defence only; the executor also runs every query in a
read-only transaction. For production, connect with a read-only database user.
"""

from __future__ import annotations

import re

from querymind.exceptions import UnsafeQueryError

_WRITE_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|ALTER|TRUNCATE|CREATE|GRANT|REVOKE|REPLACE\s+INTO|"
    r"COMMIT|ROLLBACK|CALL|EXEC|EXECUTE|COPY|LOAD|HANDLER|LOCK|SET|INTO\s+OUTFILE)\b",
    re.I,
)
_READ_START = re.compile(r"\s*\(?\s*(SELECT|WITH)\b", re.I)


def strip_literals(sql: str) -> str:
    """Blank out string literals, quoted identifiers and comments so keywords inside them are ignored."""
    sql = re.sub(r"'(?:[^']|'')*'", "''", sql)
    sql = re.sub(r'"[^"]*"|`[^`]*`', '""', sql)
    return re.sub(r"--[^\n]*|#[^\n]*|/\*.*?\*/", " ", sql, flags=re.S)


def check_read_only(sql: str) -> str | None:
    """Return a reason the SQL is unsafe to run, or None if it looks like one read-only query."""
    code = strip_literals(sql).strip().rstrip(";").strip()
    if not code:
        return "empty query"
    if ";" in code:
        return "multiple statements are not allowed"
    if not _READ_START.match(code):
        return "only SELECT / WITH queries are allowed"
    if match := _WRITE_KEYWORDS.search(code):
        return f"keyword {match.group(1).upper()} is not allowed"
    return None


def ensure_read_only(sql: str) -> str:
    """Return the SQL without a trailing ';', or raise UnsafeQueryError."""
    if reason := check_read_only(sql):
        raise UnsafeQueryError(reason)
    return sql.strip().rstrip(";").strip()


_UPDATE_START = re.compile(r"\s*UPDATE\b", re.I)
_UPDATE_FORBIDDEN = re.compile(
    r"\b(DELETE|INSERT|MERGE|DROP|ALTER|TRUNCATE|CREATE|GRANT|REVOKE|REPLACE|COMMIT|ROLLBACK|CALL|EXEC|EXECUTE"
    r"|COPY|LOAD|HANDLER|LOCK|INTO\s+OUTFILE)\b",
    re.I,
)
_WHERE = re.compile(r"\bWHERE\b", re.I)


def check_update(sql: str) -> str | None:
    """Return a reason a drafted UPDATE is not acceptable, or None for one UPDATE ... WHERE ... statement.

    Drafted UPDATEs are shown to the user and never executed; this keeps the draft to a single,
    targeted UPDATE so nothing destructive is ever offered.
    """
    code = strip_literals(sql).strip().rstrip(";").strip()
    if not code:
        return "empty statement"
    if ";" in code:
        return "multiple statements are not allowed"
    if not _UPDATE_START.match(code):
        return "only an UPDATE statement can be drafted"
    if match := _UPDATE_FORBIDDEN.search(code):
        return f"keyword {match.group(1).upper()} is not allowed in an UPDATE draft"
    if not _WHERE.search(code):
        return "an UPDATE without a WHERE clause would change every row"
    return None
