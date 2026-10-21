"""Deterministic checks that run before (and independently of) the language model.

Prohibited requests (DELETE, INSERT, DDL, permissions) are refused here, so the decision
never depends on a model. The heuristic classifier is the fallback when no model answer
is available.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from querymind.intent.models import Intent

_POLITE = r"^\s*(?:please\s+)?(?:(?:can|could|would|will)\s+you\s+(?:please\s+)?|i\s+(?:want|need)\s+to\s+|let'?s\s+)?"

# Each rule: (pattern, refusal message). Checked in order; the first match wins.
_PROHIBITED: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            rf"{_POLITE}(?:delete|remove|purge|wipe|erase|truncate|clear\s+out|get\s+rid\s+of)\b"
            r"|\bdelete\s+(?:from|all|every|the|any|rows?|records?|them|it|those|these)\b|\btruncate\s+table\b"
            r"|\b(?:and|then)\s+(?:then\s+)?(?:delete|remove|purge|wipe|erase|drop)\b",
            re.I,
        ),
        "Deleting data is not allowed. QueryMind only reads data, and can draft UPDATE statements for review.",
    ),
    (
        re.compile(
            rf"{_POLITE}(?:drop|alter|create|rename)\s+(?:the\s+)?(?:table|view|index|column|schema|database)\b"
            r"|\b(?:drop|alter)\s+(?:table|view|index|column|schema|database)\b",
            re.I,
        ),
        "Changing the database structure (DDL) is not allowed.",
    ),
    (
        re.compile(rf"{_POLITE}(?:insert|add\s+(?:a\s+)?new\s+(?:row|record))\b|\binsert\s+into\b", re.I),
        "Adding rows (INSERT) is not allowed. QueryMind only reads data, and can draft UPDATE statements for review.",
    ),
    (
        re.compile(rf"{_POLITE}(?:grant|revoke)\b|\b(?:grant|revoke)\s+\w+\s+(?:on|to|from)\b", re.I),
        "Changing permissions is not allowed.",
    ),
]

_UPDATE = re.compile(
    rf"{_POLITE}(?:update|set|change|modify|edit|correct|fix|adjust|mark|increase|decrease|raise|lower|reduce"
    r"|apply\s+a?\s*(?:discount|price))\b(?!\s+(?:in|over|across)\b)",
    re.I,
)

_AGGREGATE = re.compile(
    r"\b(?:how\s+many|count|number\s+of|total|sum|average|avg|mean|median|min(?:imum)?|max(?:imum)?|top\s+\d+"
    r"|highest|lowest|most|least|per\s+\w+|by\s+(?:category|region|month|week|day|year|customer|product|status)"
    r"|breakdown|share|percent(?:age)?|ratio|rate)\b",
    re.I,
)
_TEMPORAL = re.compile(
    r"\b(?:today|yesterday|tomorrow|last|this|next|past|previous|since|before|after|between|during|ago|daily"
    r"|weekly|monthly|quarterly|yearly|annual|trend|over\s+time|per\s+(?:day|week|month|quarter|year)|ytd|mtd"
    r"|q[1-4]|(?:19|20)\d\d|january|february|march|april|may|june|july|august|september|october|november"
    r"|december|days?|weeks?|months?|quarters?|years?|date|duration|time\s+to)\b",
    re.I,
)


def prohibited(question: str) -> str | None:
    """Refusal message when the question asks for a prohibited operation, else None."""
    for pattern, message in _PROHIBITED:
        if pattern.search(question):
            return message
    return None


def looks_like_update(question: str) -> bool:
    return bool(_UPDATE.search(question))


def mentioned(question: str, vocabulary: Iterable[str]) -> list[str]:
    """Schema names (table or table.column) whose name appears in the question, ignoring _ and plurals."""
    text = " " + re.sub(r"[^a-z0-9]+", " ", question.lower()) + " "
    found = []
    for name in vocabulary:
        leaf = name.rsplit(".", 1)[-1].lower().replace("_", " ")
        if any(f" {form} " in text for form in {leaf, leaf.rstrip("s"), leaf + "s"}):
            found.append(name)
    return found


def classify_heuristically(question: str, tables: Iterable[str] = (), columns: Iterable[str] = ()) -> Intent:
    """Keyword-based classification, used when the model is unavailable."""
    if message := prohibited(question):
        return Intent("UNSUPPORTED", reason=message, source="rules", blocked_message=message)
    tables_found = mentioned(question, tables)
    columns_found = mentioned(question, columns)
    if looks_like_update(question):
        return Intent("UPDATE", tables_found, columns_found, reason="Asks to change existing data.", source="rules")

    traits = []
    if _AGGREGATE.search(question):
        traits.append("aggregate")
    if len({c.split(".")[0] for c in columns_found} | set(tables_found)) > 1:
        traits.append("join")
    if _TEMPORAL.search(question):
        traits.append("temporal")
    query_type = (
        "SELECT_TEMPORAL"
        if "temporal" in traits
        else "SELECT_AGGREGATE"
        if "aggregate" in traits
        else "SELECT_JOIN"
        if "join" in traits
        else "SELECT_SIMPLE"
    )
    return Intent(query_type, tables_found, columns_found, traits, "Keyword-based classification.", "rules")
