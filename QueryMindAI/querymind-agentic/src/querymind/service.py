"""QueryMind operations shared by the command line and the HTTP API.

    service = QueryMindService(Settings.from_env())
    service.index()                                   # parse sqls/ and upsert into Qdrant
    service.search("refunds per month", doc_type="example_query")
    service.ask("net revenue by category last month")  # RAG: generate SQL
    service.run("top 5 products by revenue")           # generate, execute, answer

Clients are created on first use and reused, so one service instance can serve
many requests.
"""

from __future__ import annotations

import threading
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from querymind.agent.rag import QueryMindRAG, RagAnswer, refused_answer
from querymind.agent.sql_agent import AgentResult, QueryMindAgent, refused_result
from querymind.cache import CacheStats, SemanticCache
from querymind.config import Settings
from querymind.database.executor import DatabaseRegistry
from querymind.exceptions import NoSourceFilesError
from querymind.ingest.models import Chunk
from querymind.ingest.qa_loader import load_qa_file
from querymind.ingest.sql_parser import parse_sql_file
from querymind.intent import IntentClassifier
from querymind.knowledge.embeddings import Embedder, create_embedder
from querymind.knowledge.store import KnowledgeStore
from querymind.llm.providers import LLM, create_llm
from querymind.progress import ProgressCallback

SOURCE_SUFFIXES = {".sql", ".json"}


@dataclass
class SourceReport:
    name: str
    database: str
    chunks: list[Chunk]

    @property
    def counts(self) -> dict[str, int]:
        return dict(sorted(Counter(chunk.doc_type for chunk in self.chunks).items()))


@dataclass
class IndexReport:
    sources: list[SourceReport]
    dry_run: bool
    indexed: int = 0
    collection: str = ""
    qdrant_url: str = ""
    embedding: str = ""


@dataclass
class SearchHit:
    score: float
    doc_type: str | None
    database: str | None
    title: str | None
    content: str
    payload: dict = field(default_factory=dict)


class QueryMindService:
    def __init__(
        self,
        settings: Settings,
        *,
        embedder: Embedder | None = None,
        llm: LLM | None = None,
        databases: DatabaseRegistry | None = None,
    ):
        self.settings = settings
        self._embedder = embedder
        self._llm = llm
        self._databases = databases
        self._store: KnowledgeStore | None = None
        self._cache: SemanticCache | None = None
        self._lock = threading.Lock()

    # -- shared clients, created on first use ------------------------------------------

    @property
    def store(self) -> KnowledgeStore:
        with self._lock:
            if self._store is None:
                s = self.settings
                embedder = self._embedder or create_embedder(
                    s.embedding_provider,
                    s.embedding_model,
                    api_key=s.gemini_api_key,
                    dimensions=s.embedding_dimensions,
                )
                self._store = KnowledgeStore(s.qdrant_url, s.collection, embedder, api_key=s.qdrant_api_key)
            return self._store

    @property
    def llm(self) -> LLM:
        with self._lock:
            if self._llm is None:
                s = self.settings
                # The CLI's --api-key is a Gemini key; OpenAI reads OPENAI_API_KEY.
                api_key = s.gemini_api_key if s.llm_provider == "gemini" else None
                self._llm = create_llm(
                    s.llm_provider, s.resolved_llm_model, api_key=api_key, reasoning_effort=s.llm_reasoning_effort
                )
            return self._llm

    @property
    def databases(self) -> DatabaseRegistry:
        with self._lock:
            if self._databases is None:
                self._databases = DatabaseRegistry.from_env(
                    max_rows=self.settings.max_rows, timeout_seconds=self.settings.query_timeout
                )
            return self._databases

    @property
    def cache(self) -> SemanticCache | None:
        """The semantic answer cache, stored next to the knowledge base; None when disabled."""
        if not self.settings.cache_enabled:
            return None
        store = self.store  # outside the lock: creating the store takes it too
        with self._lock:
            if self._cache is None:
                self._cache = SemanticCache(
                    store.client,
                    f"{self.settings.collection}_cache",
                    threshold=self.settings.cache_threshold,
                    ttl_seconds=self.settings.cache_ttl,
                )
            return self._cache

    def cache_scope(self, max_rows: int) -> str:
        """Everything besides the question that changes an answer; cache entries match only within it."""
        s = self.settings
        return (
            f"llm={s.llm_provider}:{s.resolved_llm_model}|emb={s.embedding_provider}:{self.store.embedder.model_name}"
            f":{s.embedding_dimensions or 'default'}|kb={s.collection}|rows={max_rows}"
        )

    def cache_stats(self) -> CacheStats:
        cache = self.cache
        if cache is None:
            return CacheStats(False, 0, self.settings.cache_threshold, self.settings.cache_ttl, "")
        return cache.stats()

    def clear_cache(self) -> None:
        if (cache := self.cache) is not None:
            cache.clear()

    # -- operations --------------------------------------------------------------------

    def source_files(self) -> list[Path]:
        """Indexable files in the source directory."""
        directory = self.settings.source_dir
        if not directory.is_dir():
            return []
        return sorted(p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in SOURCE_SUFFIXES)

    def parse(
        self, paths: list[Path] | None = None, database: str | None = None, dialect: str | None = None
    ) -> list[SourceReport]:
        paths = paths or self.source_files()
        if not paths:
            raise NoSourceFilesError(f"No .sql or .json files found in {self.settings.source_dir}")
        reports = []
        for path in paths:
            chunks = _load(path, database, dialect)
            reports.append(SourceReport(path.name, chunks[0].database if chunks else "?", chunks))
        return reports

    def index(
        self,
        paths: list[Path] | None = None,
        database: str | None = None,
        dialect: str | None = None,
        recreate: bool = False,
        dry_run: bool = False,
    ) -> IndexReport:
        """Parse files (default: every file in the source directory) and replace them in Qdrant."""
        sources = self.parse(paths, database, dialect)
        report = IndexReport(sources, dry_run, collection=self.settings.collection, qdrant_url=self.settings.qdrant_url)
        if dry_run:
            return report
        store = self.store
        store.ensure_collection(recreate=recreate)
        report.indexed = sum(store.replace_source(source.name, source.chunks) for source in sources)
        report.embedding = f"{self.settings.embedding_provider}:{store.embedder.model_name}"
        self.clear_cache()  # cached answers may depend on the knowledge that just changed
        return report

    def search(
        self, query: str, limit: int = 5, doc_type: str | None = None, database: str | None = None
    ) -> list[SearchHit]:
        hits = self.store.search(query, limit=limit, doc_type=doc_type, database=database)
        results = []
        for hit in hits:
            payload = hit.payload or {}
            results.append(
                SearchHit(
                    score=hit.score,
                    doc_type=payload.get("doc_type"),
                    database=payload.get("database"),
                    title=payload.get("title"),
                    content=payload.get("content", ""),
                    payload=payload,
                )
            )
        return results

    def ask(self, question: str, database: str | None = None, on_progress: ProgressCallback | None = None) -> RagAnswer:
        """Retrieve context and generate SQL, without running it."""
        if refused := IntentClassifier.refuse(question):
            return refused_answer(question, refused, self.settings.resolved_llm_model, on_progress)
        return self.rag().answer(question, database=database, on_progress=on_progress)

    def run(
        self,
        question: str,
        database: str | None = None,
        max_repairs: int = 2,
        max_rows: int | None = None,
        timeout_seconds: int | None = None,
        on_progress: ProgressCallback | None = None,
        use_cache: bool = True,
    ) -> AgentResult:
        """Generate SQL, run it on the databases, repair on errors, and answer from the results.

        `on_progress` receives a ProgressEvent at each step; raising from it cancels the run.
        A recent near-identical question is answered from the semantic cache without LLM calls,
        unless `use_cache` is False (the fresh answer then replaces the cached one).
        Prohibited requests (DELETE, INSERT, DDL) are refused here, before any client is created.
        """
        if refused := IntentClassifier.refuse(question):
            return refused_result(question, refused, self.settings.resolved_llm_model, on_progress)
        databases = self.databases
        if max_rows is not None or timeout_seconds is not None:
            databases = databases.with_limits(
                max_rows or databases.max_rows, timeout_seconds or self.settings.query_timeout
            )
        agent = QueryMindAgent(
            self.rag(),
            databases,
            max_repairs=max_repairs,
            cache=self.cache,
            cache_scope=self.cache_scope(databases.max_rows),
        )
        return agent.run(question, database=database, on_progress=on_progress, use_cache=use_cache)

    def rag(self) -> QueryMindRAG:
        return QueryMindRAG(self.store, self.llm)


def _load(path: Path, database: str | None, dialect: str | None) -> list[Chunk]:
    if path.suffix.lower() == ".json":
        return load_qa_file(path)
    return parse_sql_file(path, database=database, dialect=dialect)
