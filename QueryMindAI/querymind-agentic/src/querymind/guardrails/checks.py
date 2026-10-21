"""Apply a guardrail policy to questions, generated SQL and query results.

These checks are a first line of defence only; the executor also runs every query in a
read-only transaction. For production, connect with a read-only database user.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from querymind.exceptions import UnsafeQueryError
from querymind.guardrails.policy import GuardrailPolicy, QuestionRule, default_policy, expand, with_baseline

_READ_START = re.compile(r"\s*\(?\s*(SELECT|WITH)\b", re.I)
_UPDATE_START = re.compile(r"\s*UPDATE\b", re.I)
_WHERE = re.compile(r"\bWHERE\b", re.I)
#: Keywords an UPDATE draft needs; every other blocked keyword is refused in a draft too.
_UPDATE_KEYWORDS = {"UPDATE", "SET"}


def strip_literals(sql: str) -> str:
    """Blank out string literals, quoted identifiers and comments so keywords inside them are ignored."""
    sql = re.sub(r"'(?:[^']|'')*'", "''", sql)
    sql = re.sub(r'"[^"]*"|`[^`]*`', '""', sql)
    return _strip_comments(sql)


def _strip_comments(sql: str) -> str:
    return re.sub(r"--[^\n]*|#[^\n]*|/\*.*?\*/", " ", sql, flags=re.S)


def _identifiers_visible(sql: str) -> str:
    """Blank out string literals and comments, and unquote identifiers ("x", `x`, [x] -> x)."""
    sql = _strip_comments(re.sub(r"'(?:[^']|'')*'", "''", sql))
    return re.sub(r'["`\[\]]', " ", sql)


def _keyword_regex(keywords: Iterable[str]) -> re.Pattern[str] | None:
    words = sorted(keywords, key=len, reverse=True)
    if not words:
        return None
    alternatives = "|".join(r"\s+".join(re.escape(part) for part in word.split()) for word in words)
    return re.compile(rf"\b({alternatives})\b", re.I)


class Guardrails:
    """A policy, compiled. The baseline (locked rules, required keywords) is always applied."""

    def __init__(self, policy: GuardrailPolicy):
        self.policy = with_baseline(policy)
        self._rules = [
            (rule, [re.compile(expand(pattern), re.I) for pattern in rule.patterns])
            for rule in self.policy.question_rules
            if rule.enabled
        ]
        keywords = self.policy.blocked_sql_keywords
        self._read_blocked = _keyword_regex(keywords)
        self._update_blocked = _keyword_regex(k for k in keywords if k not in _UPDATE_KEYWORDS)
        self._restricted_names = {column.rsplit(".", 1)[-1] for column in self.policy.restricted_columns}
        self._restricted = _keyword_regex(self._restricted_names)

    @classmethod
    def defaults(cls, max_rows: int = 1000) -> Guardrails:
        return cls(GuardrailPolicy(**default_policy(max_rows).model_dump()))

    @property
    def max_rows(self) -> int:
        return self.policy.max_rows

    @property
    def version(self) -> str:
        """Changes whenever the stored policy changes (for cache scopes)."""
        return f"{self.policy.updated_at:.3f}"

    # -- questions ----------------------------------------------------------------------

    def refuse(self, question: str) -> QuestionRule | None:
        """The first enabled rule that matches the question, or None."""
        for rule, patterns in self._rules:
            if any(pattern.search(question) for pattern in patterns):
                return rule
        return None

    def prompt_section(self) -> str:
        """Instructions for the SQL generator, so it avoids what the checks would refuse."""
        if not self.policy.restricted_columns:
            return ""
        return (
            "\n## Restricted columns (guardrail)\n"
            f"Never select, filter on, join on or otherwise use: {', '.join(self.policy.restricted_columns)}.\n"
        )

    # -- SQL ----------------------------------------------------------------------------

    def check_sql(self, sql: str) -> str | None:
        """Why the SQL is unsafe to run, or None if it is one allowed read-only query."""
        code = strip_literals(sql).strip().rstrip(";").strip()
        if not code:
            return "empty query"
        if ";" in code:
            return "multiple statements are not allowed"
        if not _READ_START.match(code):
            return "only SELECT / WITH queries are allowed"
        if self._read_blocked and (match := self._read_blocked.search(code)):
            return f"keyword {_words(match)} is not allowed"
        return self._restricted_reason(sql)

    def ensure_sql(self, sql: str) -> str:
        """The SQL without a trailing ';', or raise UnsafeQueryError."""
        if reason := self.check_sql(sql):
            raise UnsafeQueryError(reason)
        return sql.strip().rstrip(";").strip()

    def check_update(self, sql: str) -> str | None:
        """Why a drafted UPDATE is not acceptable, or None for one UPDATE ... WHERE ... statement.

        Drafted UPDATEs are shown to the user and never executed; this keeps the draft to a
        single, targeted UPDATE so nothing destructive is ever offered.
        """
        code = strip_literals(sql).strip().rstrip(";").strip()
        if not code:
            return "empty statement"
        if ";" in code:
            return "multiple statements are not allowed"
        if not _UPDATE_START.match(code):
            return "only an UPDATE statement can be drafted"
        if self._update_blocked and (match := self._update_blocked.search(code)):
            return f"keyword {_words(match)} is not allowed in an UPDATE draft"
        if not _WHERE.search(code):
            return "an UPDATE without a WHERE clause would change every row"
        return self._restricted_reason(sql)

    def _restricted_reason(self, sql: str) -> str | None:
        if self._restricted and (match := self._restricted.search(_identifiers_visible(sql))):
            return f"column {match.group(1).lower()} is restricted"
        return None

    # -- results ------------------------------------------------------------------------

    def redact(self, columns: list[str], rows: list[list[Any]]) -> tuple[list[str], list[list[Any]]]:
        """Drop restricted columns from a result (e.g. ones a SELECT * brought back)."""
        keep = [i for i, column in enumerate(columns) if column.lower() not in self._restricted_names]
        if len(keep) == len(columns):
            return columns, rows
        return [columns[i] for i in keep], [[row[i] for i in keep] for row in rows]


def _words(match: re.Match[str]) -> str:
    return " ".join(match.group(1).upper().split())


DEFAULT_GUARDRAILS = Guardrails.defaults()


def check_read_only(sql: str) -> str | None:
    """`Guardrails.check_sql` with the built-in policy."""
    return DEFAULT_GUARDRAILS.check_sql(sql)


def ensure_read_only(sql: str) -> str:
    return DEFAULT_GUARDRAILS.ensure_sql(sql)


def check_update(sql: str) -> str | None:
    return DEFAULT_GUARDRAILS.check_update(sql)
