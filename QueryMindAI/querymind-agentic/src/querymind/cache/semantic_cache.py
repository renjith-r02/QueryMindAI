"""Semantic cache: reuse the answer to a recent, near-identical question without calling the LLM.

An entry is reused only when all of these hold:
  * the question is the same after normalising case, punctuation and spacing, or the cosine
    similarity of the question embeddings is >= `threshold`;
  * the constraint fingerprint (numbers, quoted values, time/direction/negation words) is equal;
  * the scope is equal: database filter and a settings key (model, embedding, row limit);
  * the entry is younger than `ttl_seconds`.

Entries live in their own Qdrant collection, so they survive restarts and are shared by
every API worker. Re-indexing the knowledge base clears the cache.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

from qdrant_client import QdrantClient, models

from querymind.cache.fingerprint import fingerprint, normalize

_ID_NAMESPACE = uuid.UUID("0c6e3f0a-8d3e-4b47-9a52-3d0f2a5c7e19")
_KEYWORD_FIELDS = ("scope", "fingerprint")


@dataclass(frozen=True)
class CacheHit:
    similarity: float
    question: str  # the question the cached answer was produced for
    cached_at: float  # unix time
    payload: dict[str, Any]  # the stored result

    def info(self) -> dict[str, Any]:
        """What a client is told about the hit (without the payload)."""
        return {
            "hit": True,
            "similarity": round(self.similarity, 4),
            "question": self.question,
            "cached_at": self.cached_at,
        }


@dataclass(frozen=True)
class CacheStats:
    enabled: bool
    entries: int
    threshold: float
    ttl_seconds: int
    collection: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SemanticCache:
    def __init__(
        self,
        client: QdrantClient,
        collection: str,
        threshold: float = 0.95,
        ttl_seconds: int = 3600,
        clock: Callable[[], float] = time.time,
    ):
        if not 0 < threshold <= 1:
            raise ValueError("threshold must be in (0, 1]")
        self.client = client
        self.collection = collection
        self.threshold = threshold
        self.ttl_seconds = ttl_seconds
        self.clock = clock
        self._ready: int | bool = False  # the embedding size the collection was checked for

    def lookup(self, vector: list[float], question: str, scope: str) -> CacheHit | None:
        """The best live entry for this question within `scope`, or None."""
        if not self._ensure_collection(len(vector), create=False):
            return None
        now = self.clock()

        # The same question up to case, punctuation and spacing: reuse it directly. Embeddings
        # alone don't guarantee this (e.g. "per status?" vs "per status" can score ~0.98).
        exact = self.client.retrieve(self.collection, ids=[self._point_id(question, scope)], with_payload=True)
        if exact and (payload := exact[0].payload or {}).get("cached_at", 0) >= now - self.ttl_seconds:
            return CacheHit(1.0, payload["question"], payload["cached_at"], payload["result"])

        must = [
            models.FieldCondition(key="scope", match=models.MatchValue(value=scope)),
            models.FieldCondition(key="fingerprint", match=models.MatchValue(value=fingerprint(question))),
            models.FieldCondition(key="cached_at", range=models.Range(gte=now - self.ttl_seconds)),
        ]
        points = self.client.query_points(
            self.collection,
            query=vector,
            query_filter=models.Filter(must=must),
            limit=1,
            score_threshold=self.threshold,
            with_payload=True,
        ).points
        if not points:
            return None
        payload = points[0].payload or {}
        return CacheHit(points[0].score, payload["question"], payload["cached_at"], payload["result"])

    def store(self, vector: list[float], question: str, scope: str, result: dict[str, Any]) -> None:
        """Save (or replace) the answer for this question within `scope`; drop expired entries."""
        self._ensure_collection(len(vector), create=True)
        now = self.clock()
        self.client.upsert(
            self.collection,
            points=[
                models.PointStruct(
                    id=self._point_id(question, scope),
                    vector=vector,
                    payload={
                        "question": question,
                        "scope": scope,
                        "fingerprint": fingerprint(question),
                        "cached_at": now,
                        "result": result,
                    },
                )
            ],
            wait=True,
        )
        self.client.delete(
            self.collection,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[models.FieldCondition(key="cached_at", range=models.Range(lt=now - self.ttl_seconds))]
                )
            ),
            wait=True,
        )

    @staticmethod
    def _point_id(question: str, scope: str) -> str:
        """One entry per normalized question and scope, so asking again replaces it."""
        return str(uuid.uuid5(_ID_NAMESPACE, f"{scope}\n{normalize(question)}"))

    def clear(self) -> None:
        if self.client.collection_exists(self.collection):
            self.client.delete_collection(self.collection)
        self._ready = False

    def stats(self) -> CacheStats:
        entries = 0
        if self.client.collection_exists(self.collection):
            entries = self.client.count(self.collection, exact=True).count
        return CacheStats(True, entries, self.threshold, self.ttl_seconds, self.collection)

    def _ensure_collection(self, dimensions: int, create: bool) -> bool:
        if self._ready == dimensions:
            return True
        if self.client.collection_exists(self.collection):
            vectors = self.client.get_collection(self.collection).config.params.vectors
            size = vectors.size if isinstance(vectors, models.VectorParams) else None
            if size == dimensions:
                self._ready = dimensions
                return True
            # Built with another embedding size: the entries can't be compared, so start over.
            self.client.delete_collection(self.collection)
        if not create:
            return False
        self.client.create_collection(
            self.collection,
            vectors_config=models.VectorParams(size=dimensions, distance=models.Distance.COSINE),
        )
        for field_name in _KEYWORD_FIELDS:
            self.client.create_payload_index(self.collection, field_name, models.PayloadSchemaType.KEYWORD)
        self.client.create_payload_index(self.collection, "cached_at", models.PayloadSchemaType.FLOAT)
        self._ready = dimensions
        return True
