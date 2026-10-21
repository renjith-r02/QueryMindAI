"""The guardrail policy: which questions are refused, which SQL may run, and the row limit.

The policy is stored in Qdrant (see `repository`) and edited from the admin console.
`default_policy()` seeds the collection on first use and is the fallback when Qdrant can't
be read. A baseline can never be switched off: the locked question rules (deleting data,
DDL, inserts, permissions) and `REQUIRED_SQL_KEYWORDS`.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

#: An optional polite lead-in ("please", "can you", "I want to", ...). Rule patterns that start
#: with POLITE_TOKEN match a request phrased with or without one.
POLITE = r"^\s*(?:please\s+)?(?:(?:can|could|would|will)\s+you\s+(?:please\s+)?|i\s+(?:want|need)\s+to\s+|let'?s\s+)?"
POLITE_TOKEN = "{polite}"

#: Statement keywords that can change data, structure or permissions. These are always blocked.
REQUIRED_SQL_KEYWORDS = (
    "INSERT", "UPDATE", "DELETE", "MERGE", "DROP", "ALTER", "TRUNCATE", "CREATE", "GRANT", "REVOKE",
)  # fmt: skip

DEFAULT_SQL_KEYWORDS = (
    *REQUIRED_SQL_KEYWORDS,
    "REPLACE INTO", "COMMIT", "ROLLBACK", "CALL", "EXEC", "EXECUTE", "COPY", "LOAD", "HANDLER", "LOCK", "SET",
    "INTO OUTFILE",
)  # fmt: skip

_KEYWORD = re.compile(r"^[A-Z_]+(?: [A-Z_]+)*$")
_COLUMN = re.compile(r"^[a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)?$")


def expand(pattern: str) -> str:
    """The regular expression for a stored rule pattern."""
    return pattern.replace(POLITE_TOKEN, POLITE)


class QuestionRule(BaseModel):
    """Refuse a question when any pattern matches it (case-insensitive regular expressions)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$", description="Stable identifier, e.g. delete-data")
    label: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=500, description="Shown to the user when the rule refuses")
    patterns: list[str] = Field(
        min_length=1,
        max_length=20,
        description=f"Case-insensitive regular expressions; {POLITE_TOKEN} matches an optional polite lead-in",
    )
    enabled: bool = True
    locked: bool = Field(default=False, description="Part of the baseline; set by the server, cannot be disabled")

    @field_validator("label", "message")
    @classmethod
    def _strip(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value.strip()

    @field_validator("patterns")
    @classmethod
    def _compile(cls, patterns: list[str]) -> list[str]:
        cleaned = []
        for pattern in patterns:
            pattern = pattern.strip()
            if not pattern or len(pattern) > 1000:
                raise ValueError("patterns must be 1 to 1000 characters")
            try:
                re.compile(expand(pattern))
            except re.error as error:
                raise ValueError(f"invalid regular expression {pattern!r}: {error}") from None
            cleaned.append(pattern)
        return cleaned


class GuardrailPolicyInput(BaseModel):
    """The editable policy."""

    model_config = ConfigDict(extra="forbid")

    question_rules: list[QuestionRule] = Field(max_length=100)
    blocked_sql_keywords: list[str] = Field(
        max_length=100, description="Keywords that stop generated SQL from running, e.g. DELETE, INTO OUTFILE"
    )
    restricted_columns: list[str] = Field(
        default_factory=list,
        max_length=200,
        description="Columns (column or table.column) generated SQL may not use; removed from results too",
    )
    max_rows: int = Field(default=1000, ge=1, le=100_000, description="Most rows fetched per query")

    @field_validator("blocked_sql_keywords")
    @classmethod
    def _keywords(cls, keywords: list[str]) -> list[str]:
        cleaned = []
        for keyword in keywords:
            keyword = " ".join(keyword.upper().split())
            if not _KEYWORD.match(keyword):
                raise ValueError(f"{keyword!r} is not a SQL keyword (letters, _ and single spaces only)")
            if keyword not in cleaned:
                cleaned.append(keyword)
        return cleaned

    @field_validator("restricted_columns")
    @classmethod
    def _columns(cls, columns: list[str]) -> list[str]:
        cleaned = []
        for column in columns:
            column = column.strip().lower()
            if not _COLUMN.match(column):
                raise ValueError(f"{column!r} is not a column name (column or table.column)")
            if column not in cleaned:
                cleaned.append(column)
        return cleaned

    @model_validator(mode="after")
    def _unique_rule_ids(self) -> GuardrailPolicyInput:
        ids = [rule.id for rule in self.question_rules]
        if duplicates := sorted({i for i in ids if ids.count(i) > 1}):
            raise ValueError(f"question rule ids must be unique: {', '.join(duplicates)}")
        return self


class GuardrailPolicy(GuardrailPolicyInput):
    """The policy as stored."""

    updated_at: float = Field(default=0, description="Seconds since the epoch; 0 for the built-in defaults")


_LOCKED_RULES = (
    QuestionRule(
        id="delete-data",
        label="Deleting data",
        message="Deleting data is not allowed. QueryMind only reads data, and can draft UPDATE statements for review.",
        patterns=[
            rf"{POLITE_TOKEN}(?:delete|remove|purge|wipe|erase|truncate|clear\s+out|get\s+rid\s+of)\b",
            r"\bdelete\s+(?:from|all|every|the|any|rows?|records?|them|it|those|these)\b|\btruncate\s+table\b",
            r"\b(?:and|then)\s+(?:then\s+)?(?:delete|remove|purge|wipe|erase|drop)\b",
        ],
        locked=True,
    ),
    QuestionRule(
        id="change-structure",
        label="Changing the database structure (DDL)",
        message="Changing the database structure (DDL) is not allowed.",
        patterns=[
            rf"{POLITE_TOKEN}(?:drop|alter|create|rename)\s+(?:the\s+)?(?:table|view|index|column|schema|database)\b",
            r"\b(?:drop|alter)\s+(?:table|view|index|column|schema|database)\b",
        ],
        locked=True,
    ),
    QuestionRule(
        id="insert-rows",
        label="Adding rows (INSERT)",
        message="Adding rows (INSERT) is not allowed. QueryMind only reads data, and can draft UPDATE statements "
        "for review.",
        patterns=[rf"{POLITE_TOKEN}(?:insert|add\s+(?:a\s+)?new\s+(?:row|record))\b", r"\binsert\s+into\b"],
        locked=True,
    ),
    QuestionRule(
        id="permissions",
        label="Changing permissions",
        message="Changing permissions is not allowed.",
        patterns=[rf"{POLITE_TOKEN}(?:grant|revoke)\b", r"\b(?:grant|revoke)\s+\w+\s+(?:on|to|from)\b"],
        locked=True,
    ),
)
LOCKED_RULE_IDS = frozenset(rule.id for rule in _LOCKED_RULES)

_SENSITIVE_DATA = QuestionRule(
    id="sensitive-data",
    label="Passwords and payment card data",
    message="Passwords, payment card numbers and similar sensitive fields can't be queried.",
    patterns=[
        r"\b(?:show|list|get|give|select|reveal|display|export|what\s+(?:is|are))\b.*\b(?:passwords?"
        r"|password\s+hash(?:es)?|credit\s+card\s+numbers?|card\s+numbers?|cvv|ssn|social\s+security\s+numbers?)\b"
    ],
)


def default_policy(max_rows: int = 1000) -> GuardrailPolicyInput:
    """The built-in policy, used to seed Qdrant and when the stored policy can't be read."""
    return GuardrailPolicyInput(
        question_rules=[*(rule.model_copy() for rule in _LOCKED_RULES), _SENSITIVE_DATA.model_copy()],
        blocked_sql_keywords=list(DEFAULT_SQL_KEYWORDS),
        restricted_columns=["users.password_hash"],
        max_rows=max_rows,
    )


def baseline_problems(policy: GuardrailPolicyInput) -> list[str]:
    """Why the policy would weaken the baseline; empty when it keeps every locked rule and keyword."""
    problems = []
    rules = {rule.id: rule for rule in policy.question_rules}
    for locked in _LOCKED_RULES:
        rule = rules.get(locked.id)
        if rule is None:
            problems.append(f"the rule {locked.id!r} ({locked.label}) cannot be removed")
        elif not rule.enabled:
            problems.append(f"the rule {locked.id!r} ({locked.label}) cannot be disabled")
        elif missing := [p for p in locked.patterns if p not in rule.patterns]:
            problems.append(f"the built-in patterns of {locked.id!r} cannot be removed ({len(missing)} missing)")
    if missing := [k for k in REQUIRED_SQL_KEYWORDS if k not in policy.blocked_sql_keywords]:
        problems.append(f"these SQL keywords are always blocked: {', '.join(missing)}")
    return problems


def with_baseline(policy: GuardrailPolicy) -> GuardrailPolicy:
    """The policy with the baseline restored, whatever was stored, and `locked` set by rule id."""
    rules = []
    for rule in policy.question_rules:
        locked = next((r for r in _LOCKED_RULES if r.id == rule.id), None)
        if locked is None:
            rules.append(rule.model_copy(update={"locked": False}))
        else:
            patterns = [*locked.patterns, *(p for p in rule.patterns if p not in locked.patterns)]
            rules.append(rule.model_copy(update={"enabled": True, "locked": True, "patterns": patterns}))
    present = {rule.id for rule in rules}
    rules = [rule.model_copy() for rule in _LOCKED_RULES if rule.id not in present] + rules
    keywords = policy.blocked_sql_keywords
    keywords = [*keywords, *(k for k in REQUIRED_SQL_KEYWORDS if k not in keywords)]
    return policy.model_copy(update={"question_rules": rules, "blocked_sql_keywords": keywords})
