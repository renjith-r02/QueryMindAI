"""Store data sources in a Qdrant collection (records only; no vectors are needed)."""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable, Iterable

from qdrant_client import QdrantClient, models

from querymind.datasources.models import DataSource, DataSourceInput
from querymind.exceptions import QueryMindError


class DataSourceNotFoundError(QueryMindError, KeyError):
    """No data source with that id."""


class DuplicateDataSourceError(QueryMindError, ValueError):
    """Another data source already has that name."""


class DataSourceRepository:
    def __init__(
        self,
        client: QdrantClient,
        collection: str,
        seed: Callable[[], Iterable[DataSourceInput]] = tuple,
        clock: Callable[[], float] = time.time,
        on_change: Callable[[], None] = lambda: None,
    ):
        """`seed` provides the data sources to create the first time the collection is used;
        `on_change` is called after every create, update and delete."""
        self.client = client
        self.collection = collection
        self.seed = seed
        self.on_change = on_change
        self.clock = clock
        self._lock = threading.Lock()
        self._ready = False

    def list(self) -> list[DataSource]:
        self._ensure_collection()
        sources, offset = [], None
        while True:
            points, offset = self.client.scroll(
                self.collection, limit=256, offset=offset, with_payload=True, with_vectors=False
            )
            sources += [DataSource.model_validate(point.payload) for point in points]
            if offset is None:
                break
        return sorted(sources, key=lambda source: (source.created_at, source.name.lower()))

    def get(self, source_id: str) -> DataSource:
        self._ensure_collection()
        points = self.client.retrieve(self.collection, ids=[_point_id(source_id)], with_payload=True)
        if not points:
            raise DataSourceNotFoundError(source_id)
        return DataSource.model_validate(points[0].payload)

    def create(self, data: DataSourceInput) -> DataSource:
        with self._lock:
            self._check_name(data.name)
            now = self.clock()
            source = DataSource(**data.model_dump(), id=str(uuid.uuid4()), created_at=now, updated_at=now)
            self._save(source)
        self.on_change()
        return source

    def update(self, source_id: str, data: DataSourceInput) -> DataSource:
        with self._lock:
            current = self.get(source_id)
            self._check_name(data.name, except_id=source_id)
            source = DataSource(
                **data.model_dump(), id=source_id, created_at=current.created_at, updated_at=self.clock()
            )
            self._save(source)
        self.on_change()
        return source

    def delete(self, source_id: str) -> None:
        with self._lock:
            self.get(source_id)  # 404 when missing
            self.client.delete(
                self.collection, points_selector=models.PointIdsList(points=[_point_id(source_id)]), wait=True
            )
        self.on_change()

    def _check_name(self, name: str, except_id: str | None = None) -> None:
        for source in self.list():
            if source.name.lower() == name.lower() and source.id != except_id:
                raise DuplicateDataSourceError(f"A data source named {source.name!r} already exists.")

    def _save(self, source: DataSource) -> None:
        self.client.upsert(
            self.collection,
            points=[models.PointStruct(id=_point_id(source.id), vector={}, payload=source.model_dump(mode="json"))],
            wait=True,
        )

    def _ensure_collection(self) -> None:
        if self._ready:
            return
        if not self.client.collection_exists(self.collection):
            self.client.create_collection(self.collection, vectors_config={})
            now = self.clock()
            for data in self.seed():
                source = DataSource(**data.model_dump(), id=str(uuid.uuid4()), created_at=now, updated_at=now)
                self._save(source)
                now += 0.001  # keep the seed order
        self._ready = True


def _point_id(source_id: str) -> str:
    """Qdrant ids must be UUIDs or integers; normalise so lookups by any UUID spelling work."""
    try:
        return str(uuid.UUID(source_id))
    except ValueError as error:
        raise DataSourceNotFoundError(source_id) from error
