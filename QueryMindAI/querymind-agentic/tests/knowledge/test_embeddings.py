import math
from types import SimpleNamespace

import pytest
from google.genai import errors

from querymind.exceptions import CollectionMismatchError, MissingApiKeyError
from querymind.ingest import Chunk
from querymind.knowledge import KnowledgeStore, embeddings
from querymind.knowledge.embeddings import GeminiEmbedder, create_embedder
from querymind.llm import gemini_client


class FakeModels:
    def __init__(self, fail_first_with=None):
        self.calls = []
        self.fail_first_with = fail_first_with

    def embed_content(self, model, contents, config):
        self.calls.append((model, list(contents), config.task_type, config.output_dimensionality))
        if self.fail_first_with is not None:
            code, self.fail_first_with = self.fail_first_with, None
            raise errors.APIError(code, {"error": {"message": "rate limited"}})
        values = [[3.0, 4.0] + [0.0] * (config.output_dimensionality - 2) for _ in contents]
        return SimpleNamespace(embeddings=[SimpleNamespace(values=v) for v in values])


def _gemini(monkeypatch, models=None, dimensions=4):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    embedder = GeminiEmbedder("gemini-embedding-001", dimensions=dimensions)
    embedder.client = SimpleNamespace(models=models or FakeModels())
    return embedder


def test_missing_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(MissingApiKeyError):
        create_embedder("gemini")


def test_explicit_api_key_wins(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    embedder = create_embedder("gemini", api_key="explicit")
    assert embedder.model_name == "gemini-embedding-001"
    assert embedder.dimensions == embeddings.DEFAULT_GEMINI_DIM


def test_task_types_batching_and_normalization(monkeypatch):
    models = FakeModels()
    embedder = _gemini(monkeypatch, models)
    embedder.max_batch = 2

    vectors = embedder.embed_documents(["a", "b", "c"])
    query = embedder.embed_query("q")

    assert [len(call[1]) for call in models.calls] == [2, 1, 1]
    assert [call[2] for call in models.calls] == ["RETRIEVAL_DOCUMENT", "RETRIEVAL_DOCUMENT", "RETRIEVAL_QUERY"]
    assert vectors[0] == pytest.approx([0.6, 0.8, 0.0, 0.0])
    assert math.isclose(sum(v * v for v in query), 1.0)


def test_retries_rate_limit(monkeypatch):
    monkeypatch.setattr(gemini_client.time, "sleep", lambda _: None)
    models = FakeModels(fail_first_with=429)
    assert len(_gemini(monkeypatch, models).embed_documents(["a"])) == 1
    assert len(models.calls) == 2


def test_does_not_retry_bad_request(monkeypatch):
    with pytest.raises(errors.APIError):
        _gemini(monkeypatch, FakeModels(fail_first_with=400)).embed_documents(["a"])


def _chunk(title):
    return Chunk("table", title, f"table {title}", f"Table {title}", "ecommerce", "mysql", "x.sql")


def test_store_round_trip_and_dimension_check(monkeypatch):
    store = KnowledgeStore(":memory:", "kb", _gemini(monkeypatch, dimensions=4))
    store.ensure_collection()
    assert store.replace_source("x.sql", [_chunk("orders"), _chunk("users")]) == 2
    store.replace_source("x.sql", [_chunk("orders")])  # replaces, does not append
    assert store.client.count("kb").count == 1
    [hit] = store.search("orders", database="ecommerce")
    assert hit.payload["embedding_model"] == "gemini-embedding-001"

    store.embedder = _gemini(monkeypatch, dimensions=8)
    with pytest.raises(CollectionMismatchError):
        store.ensure_collection()
    store.ensure_collection(recreate=True)
    assert store.client.count("kb").count == 0
