"""Intent categories and the classifier's result."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field

QueryType = Literal[
    "SELECT_SIMPLE",
    "SELECT_AGGREGATE",
    "SELECT_JOIN",
    "SELECT_TEMPORAL",
    "UPDATE",
    "UNSUPPORTED",
]
Trait = Literal["aggregate", "join", "temporal"]

SELECT_TYPES: frozenset[str] = frozenset({"SELECT_SIMPLE", "SELECT_AGGREGATE", "SELECT_JOIN", "SELECT_TEMPORAL"})

DESCRIPTIONS: dict[str, str] = {
    "SELECT_SIMPLE": "Read rows from one table, optionally filtered or sorted; no totals, joins or date arithmetic.",
    "SELECT_AGGREGATE": "Totals, counts, averages, minimum/maximum, rankings or GROUP BY over the data.",
    "SELECT_JOIN": "Needs rows combined from two or more tables or databases.",
    "SELECT_TEMPORAL": "Depends on dates or time: periods (last month, this year), trends over time, durations.",
    "UPDATE": "Change values in existing rows. The SQL is written and returned, never executed.",
    "UNSUPPORTED": "Delete, insert, schema changes (DDL) or permissions. Refused before any SQL is written.",
}


class IntentClassification(BaseModel):
    """Structured output requested from the language model."""

    query_type: QueryType = Field(
        description="The single best category. When several SELECT categories apply, prefer "
        "SELECT_TEMPORAL, then SELECT_AGGREGATE, then SELECT_JOIN, then SELECT_SIMPLE."
    )
    traits: list[Trait] = Field(description="Every SELECT trait that applies: aggregate, join, temporal")
    tables_mentioned: list[str] = Field(description="Tables or views from the schema list the question refers to")
    columns_mentioned: list[str] = Field(
        description="Columns from the schema list (table.column) the question refers to"
    )
    reason: str = Field(description="One short sentence explaining the category")


@dataclass
class Intent:
    query_type: str
    tables_mentioned: list[str] = field(default_factory=list)
    columns_mentioned: list[str] = field(default_factory=list)
    traits: list[str] = field(default_factory=list)
    reason: str = ""
    source: Literal["rules", "model", "rules-fallback"] = "rules"
    #: Set when the request must not reach the SQL generator.
    blocked_message: str | None = None

    @property
    def blocked(self) -> bool:
        return self.query_type == "UNSUPPORTED"

    @property
    def is_update(self) -> bool:
        return self.query_type == "UPDATE"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Intent:
        return cls(**data)
