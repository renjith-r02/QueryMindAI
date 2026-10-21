from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass

from qdrant_client import QdrantClient, models

from querymind.exceptions import CollectionMismatchError
from querymind.ingest.models import Chunk
from querymind.knowledge.embeddings import Embedder


@dataclass(frozen=True)
class SchemaNames:
    tables: list[str]
    columns: list[str]


_ID_NAMESPACE = uuid.UUID("6f1d3c52-5d0e-4a8e-9a43-1c0b7f6a2e11")
_KEYWORD_FIELDS = ("doc_type", "database", "dialect", "source", "table")


class KnowledgeStore:
    """Embeds chunks with the given embedder and stores them in a Qdrant collection."""

    def __init__(self, url: str, collection: str, embedder: Embedder, api_key: str | None = None):
        # location accepts a URL or ":memory:" (used by the tests)
        self.client = QdrantClient(location=url, api_key=api_key)
        self.collection = collection
        self.embedder = embedder
        self._schema_names: dict[str | None, SchemaNames] = {}

    def ensure_collection(self, recreate: bool = False) -> None:
        self._schema_names.clear()
        exists = self.client.collection_exists(self.collection)
        if exists and recreate:
            self.client.delete_collection(self.collection)
            exists = False
        size = len(self.embedder.embed_query("dimension probe"))
        if exists:
            self._check_dimensions(size)
            return
        self.client.create_collection(
            self.collection,
            vectors_config=models.VectorParams(size=size, distance=models.Distance.COSINE),
        )
        for field_name in _KEYWORD_FIELDS:
            self.client.create_payload_index(self.collection, field_name, models.PayloadSchemaType.KEYWORD)

    def _check_dimensions(self, size: int) -> None:
        vectors = self.client.get_collection(self.collection).config.params.vectors
        existing = vectors.size if isinstance(vectors, models.VectorParams) else None
        if existing is not None and existing != size:
            raise CollectionMismatchError(
                f"Collection '{self.collection}' stores {existing}-dim vectors but "
                f"{self.embedder.model_name} produces {size}-dim vectors. "
                "Re-run with --recreate (or use another --collection)."
            )

    def replace_source(self, source: str, chunks: list[Chunk], batch_size: int = 64) -> int:
        """Delete everything previously indexed from `source`, then upsert `chunks`."""
        self._schema_names.clear()
        self.client.delete(
            self.collection,
            points_selector=models.FilterSelector(filter=_match_filter(source=source)),
            wait=True,
        )
        seen: Counter[str] = Counter()
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            vectors = self.embedder.embed_documents([chunk.embed_text for chunk in batch])
            points = []
            for chunk, vector in zip(batch, vectors, strict=True):
                key = f"{chunk.source}|{chunk.doc_type}|{chunk.title}"
                seen[key] += 1
                points.append(
                    models.PointStruct(
                        id=str(uuid.uuid5(_ID_NAMESPACE, f"{key}|{seen[key]}")),
                        vector=vector,
                        payload={**chunk.payload(), "embedding_model": self.embedder.model_name},
                    )
                )
            self.client.upsert(self.collection, points=points, wait=True)
        return len(chunks)

    def search(self, query: str | list[float], limit: int = 5, **filters: str | None) -> list[models.ScoredPoint]:
        """Search by text, or by a vector already produced with embedder.embed_query."""
        vector = self.embedder.embed_query(query) if isinstance(query, str) else query
        return self.client.query_points(
            self.collection,
            query=vector,
            query_filter=_match_filter(**filters),
            limit=limit,
            with_payload=True,
        ).points

    def schema_names(self, database: str | None = None) -> SchemaNames:
        """Every indexed table/view name and table.column name (cached until the next re-index)."""
        if database not in self._schema_names:
            tables: set[str] = set()
            columns: set[str] = set()
            if self.client.collection_exists(self.collection):
                must = [models.FieldCondition(key="doc_type", match=models.MatchAny(any=["table", "view", "column"]))]
                if database:
                    must.append(models.FieldCondition(key="database", match=models.MatchValue(value=database)))
                for point in _scroll_all(self.client, self.collection, models.Filter(must=must)):
                    payload = point.payload or {}
                    target = columns if payload.get("doc_type") == "column" else tables
                    target.add(payload.get("title", ""))
            self._schema_names[database] = SchemaNames(sorted(tables - {""}), sorted(columns - {""}))
        return self._schema_names[database]


def _scroll_all(client: QdrantClient, collection: str, query_filter: models.Filter):
    offset = None
    while True:
        points, offset = client.scroll(
            collection, scroll_filter=query_filter, limit=256, offset=offset, with_payload=True, with_vectors=False
        )
        yield from points
        if offset is None:
            return


def _match_filter(**conditions: str | None) -> models.Filter | None:
    must = [
        models.FieldCondition(key=key, match=models.MatchValue(value=value))
        for key, value in conditions.items()
        if value
    ]
    return models.Filter(must=must) if must else None
