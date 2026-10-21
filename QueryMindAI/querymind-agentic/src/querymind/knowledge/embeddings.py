"""Embedding providers.

* gemini    - Google Gemini embedding API (default). Needs an API key from
              GEMINI_API_KEY / GOOGLE_API_KEY (environment or .env) or --api-key.
* fastembed - local ONNX model, no API key, runs offline.
"""

from __future__ import annotations

import math
from typing import Protocol

from querymind.llm.gemini_client import make_client, with_retry

__all__ = ["Embedder", "create_embedder"]

PROVIDERS = ("gemini", "fastembed")
DEFAULT_MODELS = {
    "gemini": "gemini-embedding-001",
    "fastembed": "BAAI/bge-small-en-v1.5",
}
# gemini-embedding-001 returns 3072 dims by default; 768 keeps nearly all of the
# retrieval quality at a quarter of the storage. Override with EMBEDDING_DIM.
DEFAULT_GEMINI_DIM = 768


class Embedder(Protocol):
    model_name: str

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class GeminiEmbedder:
    """Gemini embeddings with retrieval task types and retry on rate limits."""

    max_batch = 100  # batchEmbedContents limit

    def __init__(
        self,
        model_name: str,
        api_key: str | None = None,
        dimensions: int | None = DEFAULT_GEMINI_DIM,
        max_retries: int = 5,
    ):
        self.client = make_client(api_key)
        self.model_name = model_name
        self.dimensions = dimensions
        self.max_retries = max_retries

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.max_batch):
            vectors += self._embed(texts[start : start + self.max_batch], "RETRIEVAL_DOCUMENT")
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text], "RETRIEVAL_QUERY")[0]

    def _embed(self, texts: list[str], task_type: str) -> list[list[float]]:
        from google.genai import types

        config = types.EmbedContentConfig(task_type=task_type, output_dimensionality=self.dimensions)
        response = with_retry(
            lambda: self.client.models.embed_content(model=self.model_name, contents=texts, config=config),
            self.max_retries,
        )

        embeddings = response.embeddings or []
        if len(embeddings) != len(texts):
            raise RuntimeError(
                f"{self.model_name} returned {len(embeddings)} embeddings for {len(texts)} texts; "
                "use a text embedding model such as gemini-embedding-001"
            )
        # Truncated (non-3072) Gemini vectors are not unit length; normalize them.
        return [_normalize(e.values) for e in embeddings]


class FastEmbedEmbedder:
    """Local ONNX embeddings via fastembed."""

    def __init__(self, model_name: str):
        from fastembed import TextEmbedding

        self.model_name = model_name
        self._model = TextEmbedding(model_name)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [vector.tolist() for vector in self._model.passage_embed(texts)]

    def embed_query(self, text: str) -> list[float]:
        return next(iter(self._model.query_embed(text))).tolist()


def create_embedder(
    provider: str, model_name: str | None = None, api_key: str | None = None, dimensions: int | None = None
) -> Embedder:
    model_name = model_name or DEFAULT_MODELS[provider]
    if provider == "gemini":
        return GeminiEmbedder(model_name, api_key=api_key, dimensions=dimensions or DEFAULT_GEMINI_DIM)
    if provider == "fastembed":
        return FastEmbedEmbedder(model_name)
    raise ValueError(f"Unknown embedding provider {provider!r}; choose one of {PROVIDERS}")


def _normalize(values: list[float] | None) -> list[float]:
    values = values or []
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / norm for v in values]
