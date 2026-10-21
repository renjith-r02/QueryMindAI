import sqlite3
import warnings

import pytest

from querymind.config import Settings
from querymind.database import DatabaseRegistry
from querymind.exceptions import NoSourceFilesError
from querymind.llm import OpenAILLM
from querymind.service import QueryMindService
from support.fakes import SQLS, HashingEmbedder, ScriptedLLM, plan


@pytest.fixture
def service(tmp_path):
    shop = tmp_path / "shop.db"
    with sqlite3.connect(shop) as connection:
        connection.executescript("CREATE TABLE t (n INTEGER); INSERT INTO t VALUES (1), (2), (3);")
    settings = Settings(qdrant_url=":memory:", collection="kb", source_dir=SQLS)
    return QueryMindService(
        settings,
        embedder=HashingEmbedder(),
        llm=ScriptedLLM(plan(("ecommerce", "SELECT n FROM t ORDER BY n"))),
        databases=DatabaseRegistry({"ecommerce": f"sqlite:///{shop}"}),
    )


def index(service, **kwargs):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # local Qdrant ignores payload indexes
        return service.index(**kwargs)


def test_dry_run_parses_without_writing(service):
    report = index(service, dry_run=True)
    assert [s.name for s in report.sources] == [
        "ecommerce_mysql_schema.sql",
        "few_shot_examples.json",
        "returns_postgres_schema.sql",
    ]
    assert report.indexed == 0
    assert report.sources[0].counts["table"] > 0
    assert service._store is None  # Qdrant was never touched


def test_index_then_search(service):
    report = index(service)
    assert report.indexed == sum(len(s.chunks) for s in report.sources)
    assert report.embedding == "gemini:hashing-test"

    hits = service.search("refund amount paid per month", limit=3, database="returns_db")
    assert len(hits) == 3
    assert {hit.database for hit in hits} == {"returns_db"}


def test_run_executes_generated_sql(service):
    index(service)
    result = service.run("list n", max_rows=2)
    assert result.status == "answered"
    assert result.result.rows == [[1], [2]]
    assert result.result.truncated


def test_missing_sources(tmp_path):
    service = QueryMindService(Settings(source_dir=tmp_path))
    with pytest.raises(NoSourceFilesError):
        service.index(dry_run=True)


def test_service_builds_configured_llm(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    service = QueryMindService(Settings(llm_provider="openai", llm_reasoning_effort="low"))
    assert isinstance(service.llm, OpenAILLM)
    assert (service.llm.model_name, service.llm.reasoning_effort) == ("gpt-6-luna", "low")
