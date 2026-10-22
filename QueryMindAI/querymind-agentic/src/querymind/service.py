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

import logging
import threading
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from qdrant_client import QdrantClient

from querymind.agent.rag import QueryMindRAG, RagAnswer, refused_answer
from querymind.agent.sql_agent import AgentResult, QueryMindAgent, refused_result
from querymind.cache import CacheStats, SemanticCache
from querymind.config import Settings
from querymind.database.executor import DatabaseRegistry
from querymind.datasources import DataSource, DataSourceInput, DataSourceRepository, from_schema_file
from querymind.datasources.connections import connection_from_url, env_database_urls, resolve
from querymind.exceptions import NoSourceFilesError
from querymind.guardrails import GuardrailRepository, Guardrails, default_policy
from querymind.ingest.models import Chunk, SchemaFile
from querymind.ingest.qa_loader import load_qa_file
from querymind.ingest.sql_parser import describe_sql_file, parse_sql_file
from querymind.intent import IntentClassifier
from querymind.knowledge.embeddings import Embedder, create_embedder
from querymind.knowledge.store import KnowledgeStore
from querymind.llm.providers import LLM, create_llm
from querymind.progress import ProgressCallback

SOURCE_SUFFIXES = {".sql", ".json"}
GUARDRAILS_TTL = 10.0  # seconds a loaded guardrail policy is reused before Qdrant is read again
logger = logging.getLogger(__name__)


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
        self._databases_injected = databases is not None
        self.connection_notes: list[str] = []  # why databases were skipped or fell back to .env
        self._store: KnowledgeStore | None = None
        self._cache: SemanticCache | None = None
        self._datasources: DataSourceRepository | None = None
        self._guardrail_store: GuardrailRepository | None = None
        self._guardrails: tuple[float, Guardrails] | None = None
        self._records: QdrantClient | None = None
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
        """Connections for queries: saved data sources first, QUERYMIND_DB_<NAME> in .env as fallback.

        Rebuilt after any data source change. If the data source store can't be read, only .env is used."""
        if self._databases is None:
            stored = self._stored_datasources()
            with self._lock:
                if self._databases is None:
                    resolution = resolve(stored, env_database_urls())
                    self.connection_notes = resolution.notes
                    for note in resolution.notes:
                        logger.info("Database connections: %s", note)
                    self._databases = DatabaseRegistry(
                        resolution.urls, max_rows=self.settings.max_rows, timeout_seconds=self.settings.query_timeout
                    )
        return self._databases

    def _stored_datasources(self) -> list[DataSource]:
        try:
            return self.datasources.list()
        except Exception as error:  # noqa: BLE001 - queries must keep working from .env
            logger.warning("Could not read saved data sources; using .env connections only: %s", error)
            return []

    def _datasources_changed(self) -> None:
        """Saved settings changed: rebuild the query connections on next use."""
        with self._lock:
            if self._databases is not None and not self._databases_injected:
                self._databases.dispose()
                self._databases = None

    def list_datasources(self) -> list[DataSource]:
        """Saved data sources, plus databases configured only in .env (origin "env", id "env:<name>")."""
        stored = self.datasources.list()
        saved = {source.name.lower() for source in stored}
        env_only = []
        for name, url in sorted(env_database_urls().items()):
            if name in saved or (described := connection_from_url(url)) is None:
                continue
            kind, connection = described
            env_only.append(
                DataSource(
                    id=f"env:{name}", origin="env", name=name, type=kind, connection=connection,
                    created_at=0, updated_at=0,
                )
            )  # fmt: skip
        return stored + env_only

    def env_datasource(self, source_id: str) -> DataSource | None:
        """The .env-only entry for an "env:<name>" id, if that database is still configured there."""
        return next((s for s in self.list_datasources() if s.id == source_id and s.origin == "env"), None)

    @property
    def datasources(self) -> DataSourceRepository:
        """Data source settings in Qdrant, seeded from the schema files on first use.

        Uses its own Qdrant client, so it needs no embedding model or API key."""
        with self._lock:
            if self._datasources is None:
                s = self.settings
                self._datasources = DataSourceRepository(
                    self._records_client(),
                    s.datasources_collection,
                    seed=self._seed_datasources,
                    on_change=self._datasources_changed,
                )
            return self._datasources

    def _records_client(self) -> QdrantClient:
        """Qdrant client for settings records (no embedding model or API key needed). Call with the lock held."""
        if self._records is None:
            s = self.settings
            self._records = (
                self._store.client
                if self._store is not None
                else QdrantClient(location=s.qdrant_url, api_key=s.qdrant_api_key)
            )
        return self._records

    @property
    def guardrail_store(self) -> GuardrailRepository:
        """The guardrail policy in Qdrant, saved from the built-in defaults on first use."""
        with self._lock:
            if self._guardrail_store is None:
                s = self.settings
                self._guardrail_store = GuardrailRepository(
                    self._records_client(),
                    s.guardrails_collection,
                    default=lambda: default_policy(s.max_rows),
                    on_change=self._guardrails_changed,
                )
            return self._guardrail_store

    def guardrails(self) -> Guardrails:
        """The current guardrail policy, re-read from Qdrant at most every GUARDRAILS_TTL seconds.

        If Qdrant can't be read, the built-in policy applies, so the checks never get weaker."""
        cached = self._guardrails
        if cached is not None and time.monotonic() - cached[0] < GUARDRAILS_TTL:
            return cached[1]
        try:
            guardrails = Guardrails(self.guardrail_store.get())
        except Exception as error:  # noqa: BLE001 - questions must still be checked
            logger.warning("Could not read the guardrail policy; using the built-in policy: %s", error)
            guardrails = Guardrails.defaults(self.settings.max_rows)
        self._guardrails = (time.monotonic(), guardrails)
        return guardrails

    def _guardrails_changed(self) -> None:
        self._guardrails = None

    def _seed_datasources(self) -> list[DataSourceInput]:
        """The data sources documented by the schema files, for the first use of the collection.

        Connection details come from the matching QUERYMIND_DB_<NAME> in .env when it is set."""
        env = env_database_urls()
        seeds = []
        for path in self.source_files():
            if path.suffix.lower() != ".sql" or (source := from_schema_file(path)) is None:
                continue
            described = connection_from_url(env[source.name.lower()]) if source.name.lower() in env else None
            if described and described[0] == source.type:
                source = source.model_copy(update={"connection": described[1]})
            seeds.append(source)
        return seeds

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

    def cache_scope(self, max_rows: int, guardrails: Guardrails | None = None) -> str:
        """Everything besides the question that changes an answer; cache entries match only within it."""
        s = self.settings
        return (
            f"llm={s.llm_provider}:{s.resolved_llm_model}|emb={s.embedding_provider}:{self.store.embedder.model_name}"
            f":{s.embedding_dimensions or 'default'}|kb={s.collection}|rows={max_rows}"
            f"|guard={(guardrails or self.guardrails()).version}"
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

    def schema(self, database: str | None = None) -> list[SchemaFile]:
        """Tables and views documented in the .sql source files, with columns, keys and comments.

        Read from the files directly, so it needs no Qdrant, model or database connection."""
        files = [describe_sql_file(path) for path in self.source_files() if path.suffix.lower() == ".sql"]
        return [f for f in files if database is None or f.database.lower() == database.lower()]

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
        guardrails = self.guardrails()
        if refused := IntentClassifier.refuse(question, guardrails):
            return refused_answer(question, refused, self.settings.resolved_llm_model, on_progress)
        return self.rag(guardrails).answer(question, database=database, on_progress=on_progress)

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
        Requests refused by the guardrail question rules (DELETE, INSERT, DDL, ...) stop here,
        before the knowledge store, a model or a database is used. `max_rows` can lower the
        guardrail row limit, never raise it.
        """
        guardrails = self.guardrails()
        if refused := IntentClassifier.refuse(question, guardrails):
            return refused_result(question, refused, self.settings.resolved_llm_model, on_progress)
        databases = self.databases.with_limits(
            min(max_rows or guardrails.max_rows, guardrails.max_rows),
            timeout_seconds or self.settings.query_timeout,
            guardrails,
        )
        agent = QueryMindAgent(
            self.rag(guardrails),
            databases,
            max_repairs=max_repairs,
            cache=self.cache,
            cache_scope=self.cache_scope(databases.max_rows, guardrails),
        )
        return agent.run(question, database=database, on_progress=on_progress, use_cache=use_cache)

    def rag(self, guardrails: Guardrails | None = None) -> QueryMindRAG:
        return QueryMindRAG(self.store, self.llm, guardrails=guardrails or self.guardrails())


def _load(path: Path, database: str | None, dialect: str | None) -> list[Chunk]:
    if path.suffix.lower() == ".json":
        return load_qa_file(path)
    return parse_sql_file(path, database=database, dialect=dialect)
