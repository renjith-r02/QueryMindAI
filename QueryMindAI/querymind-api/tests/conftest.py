import hashlib
import math
import re
import sqlite3
import warnings
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from querymind.agent import FinalAnswer, GeneratedQuery, SqlAnswer
from querymind.intent import IntentClassification
from querymind.config import DEFAULT_SOURCE_DIR, Settings
from querymind.database import DatabaseRegistry
from querymind.service import QueryMindService

from app.dependencies import get_service
from app.main import app


class HashingEmbedder:
    """Deterministic bag-of-words embedder so retrieval works offline."""

    model_name = "hashing-test"

    def _vector(self, text):
        vector = [0.0] * 256
        for word in re.findall(r"\w+", text.lower()):
            vector[int(hashlib.md5(word.encode()).hexdigest(), 16) % 256] += 1.0
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]

    def embed_documents(self, texts):
        return [self._vector(t) for t in texts]

    def embed_query(self, text):
        return self._vector(text)


class FakeLLM:
    """Classifies as `query_type`, plans one query on the test database, then answers 'final'."""

    model_name = "fake-llm"
    SELECT_SQL = "SELECT n FROM t ORDER BY n"
    UPDATE_SQL = "UPDATE t SET n = 0 WHERE n = 3"

    def __init__(self):
        self.calls = 0
        self.query_type = "SELECT_SIMPLE"

    def generate(self, system, prompt, schema):
        self.calls += 1
        if schema is IntentClassification:
            return IntentClassification(
                query_type=self.query_type,
                traits=[],
                tables_mentioned=["orders"],
                columns_mentioned=[],
                reason="fake",
            )
        if schema is FinalAnswer:
            return FinalAnswer(answer="final", caveats=[])
        sql = self.UPDATE_SQL if self.query_type == "UPDATE" else self.SELECT_SQL
        return SqlAnswer(
            answerable=True,
            queries=[GeneratedQuery(database="ecommerce", dialect="sqlite", sql=sql, purpose="numbers")],
            explanation="approach",
            assumptions=[],
            sources=["S1"],
        )


@pytest.fixture
def service(tmp_path: Path) -> QueryMindService:
    shop = tmp_path / "shop.db"
    with sqlite3.connect(shop) as connection:
        connection.executescript("CREATE TABLE t (n INTEGER); INSERT INTO t VALUES (1), (2), (3);")
    settings = Settings(
        qdrant_url=":memory:",
        collection="kb",
        source_dir=DEFAULT_SOURCE_DIR,
        max_rows=100,
    )
    service = QueryMindService(
        settings,
        embedder=HashingEmbedder(),
        llm=FakeLLM(),
        databases=DatabaseRegistry({"ecommerce": f"sqlite:///{shop}"}, max_rows=settings.max_rows),
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # local Qdrant ignores payload indexes
        service.index()
    return service


@pytest.fixture
def client(service: QueryMindService):
    app.dependency_overrides[get_service] = lambda: service
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
