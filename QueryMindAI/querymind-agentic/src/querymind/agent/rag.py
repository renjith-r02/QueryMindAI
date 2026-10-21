"""Retrieval-augmented text-to-SQL: retrieve knowledge from Qdrant, then ask the LLM.

rag = QueryMindRAG(store, create_llm("openai"))
result = rag.answer("What was the unit return rate by category last quarter?")
result.answer.queries  # one read-only query per database involved
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from pydantic import BaseModel, Field

from querymind.database.safety import check_read_only, check_update
from querymind.intent import Intent, IntentClassifier
from querymind.knowledge.store import KnowledgeStore
from querymind.llm.providers import LLM
from querymind.progress import Progress, ProgressCallback, plural

# How many hits to pull per doc_type. Searching per type keeps the context
# balanced: a question always gets schema, rules and similar examples.
RETRIEVAL_PLAN: dict[str, int] = {
    "overview": 4,
    "table": 4,
    "view": 3,
    "column": 6,
    "business_rule": 5,
    "section": 3,
    "example_query": 4,
    "qa_pair": 3,
}

_CONTEXT_GROUPS = [
    ("Database overviews (dialect and scope)", {"overview", "schema"}),
    ("Tables and views", {"table", "view"}),
    ("Columns", {"column"}),
    ("Business rules and query guidance", {"business_rule", "section", "routine"}),
    ("Similar questions with verified answers", {"example_query", "qa_pair"}),
]

SYSTEM_INSTRUCTION = """\
You are QueryMind, an expert text-to-SQL assistant for an e-commerce platform whose data
lives in more than one database. Answer the user's question by writing SQL, using ONLY the
retrieved context.

Rules:
1. Use only tables, views and columns that appear in the context. Never invent names.
2. Write each query in the dialect of the database it runs on (MySQL vs PostgreSQL) and use
   that dialect's functions only.
3. A single query cannot read tables from two different databases. If the question needs
   both, write one query per database, each aggregated to a shared key (for example
   order_line_id, order_id, user_id or product_id), describe the merge in merge_steps and
   write merge_sql: one SQLite query over tables q1, q2, ... (the result of each query, in
   order, with the column names/aliases you selected) that produces the final answer.
4. Apply the business rules in the context (which statuses count as sales, when a refund
   is paid, revenue definitions, date columns to use, currency handling).
5. Prefer the views and patterns shown in the similar examples.
6. Generate read-only SQL only (SELECT / WITH). Never write INSERT, UPDATE, DELETE or DDL.
7. If the context is not enough to answer, set answerable to false, leave queries empty
   and explain what is missing. Do not guess.
8. List the context ids (e.g. S3) you relied on in sources.
9. If a "Live database objects" section is present, only use tables and views listed there;
   if a view from the context is missing, inline its definition using the base tables.
10. If a "Previous attempt" section is present, fix the reported errors.
"""


UPDATE_INSTRUCTION = """\
You are QueryMind. The user asked to change existing data. Draft ONE UPDATE statement that does it,
using ONLY the retrieved context. The statement is shown to a person for review and is NEVER run
by QueryMind.

Rules:
1. Write exactly one UPDATE statement, in the dialect of the database that holds the table.
2. Always include a WHERE clause that limits the change to the rows the user meant.
3. Never write DELETE, INSERT, DDL, or more than one statement.
4. Use only tables and columns from the context; apply the business rules in the context.
5. If the context is not enough to identify the table, columns or rows, set answerable to false,
   leave queries empty and explain what is missing.
6. In explanation, say which rows will change and how; list assumptions; cite context ids in sources.
"""


class GeneratedQuery(BaseModel):
    database: str = Field(description="Database the query runs on, e.g. ecommerce or returns_db")
    dialect: str = Field(description="SQL dialect of that database: mysql or postgresql")
    sql: str = Field(description="A single read-only SQL statement")
    purpose: str = Field(description="What this query returns and why it is needed")


class SqlAnswer(BaseModel):
    answerable: bool = Field(description="False when the context does not support an answer")
    queries: list[GeneratedQuery] = Field(description="One query per database involved, in execution order")
    merge_steps: str | None = Field(
        default=None, description="How to combine results of several queries in code; null for a single query"
    )
    merge_sql: str | None = Field(
        default=None,
        description="SQLite query over tables q1, q2, ... (results of queries 1, 2, ...) that combines them; "
        "null for a single query",
    )
    explanation: str = Field(description="Short explanation of the approach and business rules applied")
    assumptions: list[str] = Field(description="Assumptions made, e.g. time window or definition used")
    sources: list[str] = Field(description="Context ids used, e.g. ['S1', 'S4']")


@dataclass
class ContextItem:
    id: str
    score: float
    doc_type: str
    database: str
    title: str
    content: str


@dataclass
class RagAnswer:
    question: str
    answer: SqlAnswer
    context: list[ContextItem]
    model: str
    warnings: list[str] = field(default_factory=list)
    intent: Intent | None = None

    @property
    def status(self) -> str:
        """generated (SQL written), blocked (refused by intent), or not_answerable."""
        if self.intent is not None and self.intent.blocked:
            return "blocked"
        return "generated" if self.answer.answerable and self.answer.queries else "not_answerable"

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "status": self.status,
            "model": self.model,
            "intent": self.intent.to_dict() if self.intent else None,
            "answer": self.answer.model_dump(),
            "warnings": self.warnings,
            "context": [asdict(item) for item in self.context],
        }


class QueryMindRAG:
    def __init__(
        self,
        store: KnowledgeStore,
        llm: LLM,
        plan: dict[str, int] | None = None,
        classifier: IntentClassifier | None = None,
    ):
        self.store = store
        self.llm = llm
        self.plan = plan or RETRIEVAL_PLAN
        self.classifier = classifier or IntentClassifier(llm)

    def classify(self, question: str, database: str | None = None, progress: Progress | None = None) -> Intent:
        """Decide the question's intent before any SQL is written (see querymind.intent)."""
        progress = progress or Progress()
        progress.running("classify", "Working out what kind of question this is")
        intent = IntentClassifier.refuse(question)  # prohibited requests stop before any lookup
        if intent is None:
            names = self.store.schema_names(database)
            intent = self.classifier.classify(question, names.tables, names.columns)
        report_intent(progress, intent)
        return intent

    def retrieve(
        self,
        question: str,
        database: str | None = None,
        progress: Progress | None = None,
        vector: list[float] | None = None,
    ) -> list[ContextItem]:
        """`vector` is the question's embedding when the caller already has it (e.g. from the cache lookup)."""
        progress = progress or Progress()
        progress.running("retrieve", "Searching the knowledge base for relevant tables, rules and examples")
        if vector is None:
            vector = self.store.embedder.embed_query(question)
        hits = {}
        for doc_type, limit in self.plan.items():
            for hit in self.store.search(vector, limit=limit, doc_type=doc_type, database=database):
                hits.setdefault(hit.id, hit)
        ranked = sorted(hits.values(), key=lambda h: h.score, reverse=True)
        databases = sorted({hit.payload["database"] for hit in ranked})
        progress.done(
            "retrieve",
            f"Found {plural(len(ranked), 'relevant note')}" + (f" across {', '.join(databases)}" if databases else ""),
            chunks=len(ranked),
            databases=databases,
        )
        return [
            ContextItem(
                id=f"S{index}",
                score=hit.score,
                doc_type=hit.payload["doc_type"],
                database=hit.payload["database"],
                title=hit.payload["title"],
                content=hit.payload["content"],
            )
            for index, hit in enumerate(ranked, start=1)
        ]

    def generate(
        self,
        question: str,
        context: list[ContextItem],
        extra_sections: list[str] | None = None,
        intent: Intent | None = None,
    ) -> SqlAnswer:
        sections = [*(extra_sections or []), *([intent_section(intent)] if intent else [])]
        prompt = build_prompt(question, context, sections)
        system = UPDATE_INSTRUCTION if intent is not None and intent.is_update else SYSTEM_INSTRUCTION
        return self.llm.generate(system, prompt, SqlAnswer)

    def answer(
        self, question: str, database: str | None = None, on_progress: ProgressCallback | None = None
    ) -> RagAnswer:
        progress = Progress(on_progress)
        intent = self.classify(question, database, progress)
        if intent.blocked:
            return RagAnswer(question, refusal(intent), [], self.llm.model_name, [], intent)
        context = self.retrieve(question, database, progress)
        progress.running(
            "generate-1",
            "Drafting the UPDATE statement" if intent.is_update else "Writing SQL",
            attempt=1,
            model=self.llm.model_name,
        )
        answer = self.generate(question, context, intent=intent)
        if answer.answerable and answer.queries:
            progress.done(
                "generate-1",
                f"Wrote {plural(len(answer.queries), 'query', 'queries')}",
                attempt=1,
                queries=[query.model_dump() for query in answer.queries],
            )
        else:
            progress.done("generate-1", "The question can't be answered from the available data", answerable=False)
        answer, warnings = (
            screen_update(answer, context) if intent.is_update else (answer, check_answer(answer, context))
        )
        return RagAnswer(question, answer, context, self.llm.model_name, warnings, intent)


def build_prompt(question: str, context: list[ContextItem], extra_sections: list[str] | None = None) -> str:
    parts = ["# Retrieved context"]
    for heading, doc_types in _CONTEXT_GROUPS:
        items = [item for item in context if item.doc_type in doc_types]
        if not items:
            continue
        parts.append(f"\n## {heading}")
        parts += [f"[{item.id}] ({item.database}, {item.doc_type})\n{item.content}\n" for item in items]
    parts += extra_sections or []
    parts.append(f"# Question\n{question}")
    return "\n".join(parts)


_LABELS = {
    "SELECT_SIMPLE": "Simple lookup (SELECT_SIMPLE)",
    "SELECT_AGGREGATE": "Aggregate question (SELECT_AGGREGATE)",
    "SELECT_JOIN": "Question across tables (SELECT_JOIN)",
    "SELECT_TEMPORAL": "Time-based question (SELECT_TEMPORAL)",
    "UPDATE": "Change request (UPDATE): the SQL will be drafted, not run",
    "UNSUPPORTED": "Not allowed (UNSUPPORTED)",
}


def report_intent(progress: Progress, intent: Intent) -> None:
    detail = {"intent": intent.to_dict()}
    if intent.blocked:
        progress.failed("classify", intent.blocked_message or "This request is not allowed.", **detail)
    else:
        tables = f" on {', '.join(intent.tables_mentioned)}" if intent.tables_mentioned else ""
        progress.done("classify", f"{_LABELS[intent.query_type]}{tables}", **detail)


def refused_answer(question: str, intent: Intent, model: str, on_progress: ProgressCallback | None = None) -> RagAnswer:
    """The result of `answer` for a request refused before any client is needed."""
    progress = Progress(on_progress)
    progress.running("classify", "Working out what kind of question this is")
    report_intent(progress, intent)
    return RagAnswer(question, refusal(intent), [], model, [], intent)


def intent_section(intent: Intent) -> str:
    lines = ["\n## Question type (from the intent classifier)", f"{intent.query_type}: {intent.reason}"]
    if intent.traits:
        lines.append(f"Traits: {', '.join(intent.traits)}")
    if intent.tables_mentioned:
        lines.append(f"Tables the question refers to: {', '.join(intent.tables_mentioned)}")
    if intent.columns_mentioned:
        lines.append(f"Columns the question refers to: {', '.join(intent.columns_mentioned)}")
    return "\n".join(lines) + "\n"


def refusal(intent: Intent) -> SqlAnswer:
    """The answer for a refused request: nothing to run, and why."""
    return SqlAnswer(
        answerable=False,
        queries=[],
        explanation=intent.blocked_message or "This request is not allowed.",
        assumptions=[],
        sources=[],
    )


def screen_update(answer: SqlAnswer, context: list[ContextItem]) -> tuple[SqlAnswer, list[str]]:
    """Keep only acceptable UPDATE drafts; anything else (e.g. a DELETE) is removed, never returned."""
    warnings = []
    known_databases = {item.database for item in context}
    kept = []
    for query in answer.queries:
        if reason := check_update(query.sql):
            warnings.append(f"The drafted statement for {query.database} was withheld: {reason}.")
            continue
        if query.database not in known_databases:
            warnings.append(f"Query targets unknown database '{query.database}'.")
        kept.append(query)
    if len(kept) > 1:
        warnings.append("Only one UPDATE statement can be drafted at a time; review each statement separately.")
    screened = answer.model_copy(update={"queries": kept, "answerable": answer.answerable and bool(kept)})
    return screened, warnings


def check_answer(answer: SqlAnswer, context: list[ContextItem]) -> list[str]:
    warnings = []
    known_databases = {item.database for item in context}
    for query in answer.queries:
        if reason := check_read_only(query.sql):
            warnings.append(f"Query for {query.database} will not be executed: {reason}.")
        if query.database not in known_databases:
            warnings.append(f"Query targets unknown database '{query.database}'.")
    if answer.answerable and not answer.queries:
        warnings.append("Model marked the question answerable but returned no queries.")
    return warnings
