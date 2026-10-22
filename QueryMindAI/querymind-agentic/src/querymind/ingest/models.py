from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field


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


# -- structured schema (Admin > Schema, GET /admin/schema) ----------------------------------


class ForeignKey(BaseModel):
    columns: list[str]
    references_table: str
    references_columns: list[str]


class SchemaColumn(BaseModel):
    name: str
    data_type: str | None = Field(default=None, description="As declared, e.g. VARCHAR(255); null for views")
    nullable: bool | None = Field(default=None, description="null when unknown (views)")
    primary_key: bool = False
    references: str | None = Field(default=None, description="table.column this column points to, if any")
    description: str = ""


class SchemaRelation(BaseModel):
    name: str = Field(description="Schema-qualified when the file uses a schema, e.g. rma.returns")
    kind: Literal["table", "view"]
    description: str = Field(default="", description="The table comment")
    notes: str = Field(default="", description="The comment block written above the statement")
    columns: list[SchemaColumn]
    primary_key: list[str] = Field(default_factory=list)
    foreign_keys: list[ForeignKey] = Field(default_factory=list)
    indexes: list[str] = Field(default_factory=list)


class SchemaFile(BaseModel):
    """Tables and views documented by one annotated schema file."""

    database: str
    dialect: str
    source: str
    tables: list[SchemaRelation]
