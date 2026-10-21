"""The agent and service answer repeated questions from the cache without calling the LLM."""

import sqlite3
import warnings

import pytest
from qdrant_client import QdrantClient

from querymind.agent import QueryMindAgent, QueryMindRAG
from querymind.cache import SemanticCache
from querymind.config import Settings
from querymind.database import DatabaseRegistry
from querymind.service import QueryMindService
from support.fakes import SQLS, HashingEmbedder, ScriptedLLM, intent, plan

SQL = "SELECT category, SUM(quantity) AS units FROM order_lines GROUP BY category ORDER BY category"


class CountingLLM(ScriptedLLM):
    """A ScriptedLLM that can answer any number of questions and counts every model call."""

    def __init__(self, sql=SQL, **kwargs):
        super().__init__(**kwargs)
        self.sql, self.calls = sql, 0

    def generate(self, system, prompt, schema):
        self.calls += 1
        if not self.plans:
            self.plans.append(plan(("ecommerce", self.sql)))
        return super().generate(system, prompt, schema)


@pytest.fixture
def cache():
    return SemanticCache(QdrantClient(":memory:"), "kb_cache", threshold=0.9, ttl_seconds=3600)


def agent(store, databases, llm, cache, scope="llm=scripted"):
    return QueryMindAgent(QueryMindRAG(store, llm), databases, cache=cache, cache_scope=scope)


def run(agent_, question, **kwargs):
    events = []
    result = agent_.run(question, on_progress=events.append, **kwargs)
    return result, events


def test_repeat_question_uses_no_llm_calls(store, databases, cache):
    llm = CountingLLM()
    a = agent(store, databases, llm, cache)

    first, events = run(a, "Units by category")
    assert first.status == "answered" and first.cache is None
    calls_after_first = llm.calls
    assert calls_after_first == 3  # classify, generate SQL, write answer
    assert [(e.id, e.status) for e in events][:2] == [("cache", "running"), ("cache", "done")]

    second, events = run(a, "units by category?")
    assert llm.calls == calls_after_first  # served entirely from the cache
    assert second.status == "answered"
    assert second.question == "units by category?"
    assert second.cache["hit"] is True and second.cache["question"] == "Units by category"
    assert second.result.rows == first.result.rows == [["Hats", 5], ["Shoes", 10]]
    assert second.final.answer == first.final.answer
    assert second.intent.query_type == first.intent.query_type
    assert [(e.id, e.status) for e in events] == [("cache", "running"), ("cache", "done")]
    assert "no model calls" in events[-1].message


def test_different_constraints_are_not_served_from_cache(store, databases, cache):
    llm = CountingLLM()
    a = agent(store, databases, llm, cache)
    run(a, "Top 5 categories by units")
    calls = llm.calls
    result, _ = run(a, "Top 10 categories by units")
    assert result.cache is None and llm.calls > calls


def test_use_cache_false_refreshes_the_entry(store, databases, cache):
    llm = CountingLLM()
    a = agent(store, databases, llm, cache)
    run(a, "units by category")
    calls = llm.calls
    fresh, events = run(a, "units by category", use_cache=False)
    assert fresh.cache is None and llm.calls > calls
    assert not any(e.id == "cache" for e in events)
    again, _ = run(a, "units by category")
    assert again.cache["hit"] is True


def test_scope_and_database_separate_entries(store, databases, cache):
    llm = CountingLLM()
    run(agent(store, databases, llm, cache, scope="llm=a"), "units by category")
    result, _ = run(agent(store, databases, llm, cache, scope="llm=b"), "units by category")
    assert result.cache is None
    result, _ = run(agent(store, databases, llm, cache, scope="llm=a"), "units by category", database="ecommerce")
    assert result.cache is None


def test_failures_and_refusals_are_not_cached(store, databases, cache):
    llm = CountingLLM(sql="SELECT missing_column FROM order_lines")
    a = QueryMindAgent(QueryMindRAG(store, llm), databases, max_repairs=0, cache=cache, cache_scope="s")
    failed, _ = run(a, "units by category")
    assert failed.status == "failed"
    refused, events = run(a, "delete all orders")
    assert refused.status == "blocked" and not any(e.id == "cache" for e in events)
    assert cache.stats().entries == 0


def test_update_drafts_are_cached(store, databases, cache):
    sql = "UPDATE order_lines SET quantity = 0 WHERE order_line_id = 3"
    llm = CountingLLM(sql=sql, intent=intent("UPDATE"))
    a = agent(store, databases, llm, cache)
    first, _ = run(a, "set the quantity of line 3 to zero")
    calls = llm.calls
    second, _ = run(a, "Set the quantity of line 3 to zero")
    assert second.status == first.status == "generated"
    assert second.plan.queries[0].sql == sql and llm.calls == calls


@pytest.fixture
def service(tmp_path):
    shop = tmp_path / "shop.db"
    with sqlite3.connect(shop) as connection:
        connection.executescript("CREATE TABLE t (n INTEGER); INSERT INTO t VALUES (1), (2), (3);")
    llm = CountingLLM(sql="SELECT n FROM t ORDER BY n")
    svc = QueryMindService(
        Settings(qdrant_url=":memory:", collection="kb", source_dir=SQLS, cache_threshold=0.9),
        embedder=HashingEmbedder(),
        llm=llm,
        databases=DatabaseRegistry({"ecommerce": f"sqlite:///{shop}"}),
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        svc.index()
    return svc


def test_service_caches_and_reindexing_clears(service):
    assert service.run("list n").cache is None
    assert service.run("List n.").cache["hit"] is True
    assert service.cache_stats().entries == 1

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        service.index()  # the knowledge changed, so cached answers are dropped
    assert service.cache_stats().entries == 0
    assert service.run("list n").cache is None


def test_row_limit_is_part_of_the_scope(service):
    service.run("list n", max_rows=2)
    assert service.run("list n", max_rows=2).cache["hit"] is True
    assert service.run("list n", max_rows=3).cache is None


def test_cache_can_be_disabled(tmp_path):
    svc = QueryMindService(Settings(qdrant_url=":memory:", cache_enabled=False), embedder=HashingEmbedder())
    assert svc.cache is None
    stats = svc.cache_stats()
    assert stats.enabled is False and stats.entries == 0
