"""Request and response bodies.

Requests forbid unknown fields, so callers cannot choose the LLM, API keys or
connection settings; those come from the server configuration only.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from querymind.agent import AgentResult, FinalAnswer, RagAnswer, SqlAnswer
from querymind.service import IndexReport, SearchHit


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Response(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# -- requests ------------------------------------------------------------------------------


class IndexRequest(Request):
    files: list[str] | None = Field(
        default=None,
        description="File names from GET /sources; omit to index every source file",
    )
    database: str | None = Field(default=None, description="Override the detected database name (SQL files)")
    dialect: Literal["mysql", "postgresql"] | None = Field(default=None, description="Override the detected dialect")
    recreate: bool = Field(default=False, description="Drop and recreate the whole collection first")
    dry_run: bool = Field(default=False, description="Parse only; do not embed or write")
    include_chunks: bool = Field(default=False, description="List every chunk in the response")


class AskRequest(Request):
    question: str = Field(min_length=1, max_length=2000)
    database: str | None = Field(default=None, description="Restrict retrieval to one database, e.g. ecommerce")


class RunRequest(AskRequest):
    max_rows: int | None = Field(
        default=None,
        ge=1,
        description="Rows fetched per query; cannot exceed the guardrail row limit (GET /guardrails)",
    )
    max_repairs: int = Field(default=2, ge=0, le=5, description="Times to regenerate SQL after an error")
    use_cache: bool = Field(
        default=True,
        description="Reuse the answer to a recent near-identical question (no LLM calls). "
        "false always asks the model and refreshes the cached answer.",
    )


# -- responses -----------------------------------------------------------------------------


class SourceFile(BaseModel):
    name: str
    size_bytes: int


class ChunkSummary(Response):
    doc_type: str
    title: str


class SourceSummary(BaseModel):
    name: str
    database: str
    chunk_count: int
    counts: dict[str, int]
    chunks: list[ChunkSummary] | None = None


class IndexResponse(BaseModel):
    dry_run: bool
    indexed: int
    collection: str
    embedding: str
    sources: list[SourceSummary]

    @classmethod
    def from_report(cls, report: IndexReport, include_chunks: bool) -> "IndexResponse":
        return cls(
            dry_run=report.dry_run,
            indexed=report.indexed,
            collection=report.collection,
            embedding=report.embedding,
            sources=[
                SourceSummary(
                    name=source.name,
                    database=source.database,
                    chunk_count=len(source.chunks),
                    counts=source.counts,
                    chunks=[ChunkSummary.model_validate(c) for c in source.chunks] if include_chunks else None,
                )
                for source in report.sources
            ],
        )


class SearchHitOut(Response):
    score: float
    doc_type: str | None
    database: str | None
    title: str | None
    content: str | None = None

    @classmethod
    def from_hit(cls, hit: SearchHit, include_content: bool) -> "SearchHitOut":
        out = cls.model_validate(hit)
        return out if include_content else out.model_copy(update={"content": None})


class ContextItemOut(Response):
    id: str
    score: float
    doc_type: str
    database: str
    title: str
    content: str


class IntentOut(Response):
    """What the question asks for, decided before any SQL is written."""

    query_type: Literal[
        "SELECT_SIMPLE",
        "SELECT_AGGREGATE",
        "SELECT_JOIN",
        "SELECT_TEMPORAL",
        "UPDATE",
        "UNSUPPORTED",
    ] = Field(description="UPDATE drafts are returned but never executed; UNSUPPORTED requests are refused")
    tables_mentioned: list[str]
    columns_mentioned: list[str]
    traits: list[Literal["aggregate", "join", "temporal"]]
    reason: str
    source: Literal["rules", "model", "rules-fallback"] = Field(description="What decided the intent")
    blocked_message: str | None = Field(description="Why the request was refused, when it was")


class CacheInfo(BaseModel):
    """Present when the answer came from the semantic cache."""

    hit: bool
    similarity: float = Field(description="Cosine similarity to the cached question")
    question: str = Field(description="The question the cached answer was produced for")
    cached_at: float = Field(description="When the cached answer was produced (unix time)")


class CacheStatsOut(Response):
    enabled: bool
    entries: int
    threshold: float = Field(description="Minimum similarity for a cached answer to be reused")
    ttl_seconds: int = Field(description="How long an answer may be reused")
    collection: str


class AskResponse(Response):
    question: str
    status: Literal["generated", "not_answerable", "blocked"] = Field(
        description="generated: SQL was written (for UPDATE: drafted, not run); blocked: refused by intent"
    )
    model: str
    intent: IntentOut | None
    answer: SqlAnswer
    warnings: list[str]
    context: list[ContextItemOut]

    @classmethod
    def from_result(cls, result: RagAnswer) -> "AskResponse":
        return cls.model_validate(result)


class QueryResultOut(Response):
    database: str
    sql: str
    columns: list[str]
    rows: list[list[Any]]
    truncated: bool
    elapsed_ms: float
    error: str | None
    error_kind: str | None


class AttemptOut(Response):
    plan: SqlAnswer
    results: list[QueryResultOut]
    merged: QueryResultOut | None


class RunResponse(Response):
    question: str
    status: Literal["answered", "not_answerable", "failed", "blocked", "generated"] = Field(
        description="answered: SQL ran and was answered; generated: an UPDATE was drafted and NOT executed; "
        "blocked: refused by a guardrail question rule or the intent classifier before any SQL was written"
    )
    model: str
    intent: IntentOut | None
    cache: CacheInfo | None = Field(default=None, description="Set when the answer came from the semantic cache")
    final: FinalAnswer | None
    result: QueryResultOut | None = Field(description="The table the final answer is based on")
    warnings: list[str]
    attempts: list[AttemptOut]
    context: list[ContextItemOut]

    @classmethod
    def from_result(cls, result: AgentResult) -> "RunResponse":
        return cls.model_validate(result)
