from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Chunk:
    """One retrievable unit of database knowledge.

    doc_type is one of: overview, section, business_rule, schema, table,
    column, view, routine, example_query, qa_pair.
    """

    doc_type: str
    title: str
    embed_text: str  # text that is turned into the vector
    content: str  # full text handed to the LLM at retrieval time
    database: str
    dialect: str
    source: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def payload(self) -> dict[str, Any]:
        return {
            "doc_type": self.doc_type,
            "title": self.title,
            "content": self.content,
            "database": self.database,
            "dialect": self.dialect,
            "source": self.source,
            **self.metadata,
        }
