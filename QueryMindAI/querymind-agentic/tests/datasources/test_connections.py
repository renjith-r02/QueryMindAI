import sqlite3

import pytest
from qdrant_client import QdrantClient
from sqlalchemy.engine import make_url

from querymind.config import Settings
from querymind.datasources import DataSource, DataSourceInput, DataSourceRepository
from querymind.datasources.connections import connection_from_url, env_database_urls, resolve
from querymind.service import QueryMindService
from support.fakes import SQLS

ENV = {
    "ecommerce": "mysql+pymysql://root:s3cret@db.internal:3306/ecommerce",
    "returns_db": "postgresql+psycopg://postgres:pg-pass@localhost:5432/postgres",
}


def saved(name, type_="mysql", enabled=True, **connection):
    return DataSource(
        name=name, type=type_, enabled=enabled, connection=connection, id=name, created_at=0, updated_at=0
    )


def test_env_urls_are_read_by_lower_case_name():
    environ = {"QUERYMIND_DB_ECOMMERCE": "mysql://x", "QUERYMIND_DB_EMPTY": "", "OTHER": "y"}
    assert env_database_urls(environ) == {"ecommerce": "mysql://x"}


def test_missing_data_source_uses_the_env_url():
    resolution = resolve([], ENV)
    assert resolution.urls == ENV
    assert resolution.origins == {"ecommerce": "env", "returns_db": "env"}


def test_saved_fields_win_and_empty_fields_fall_back_to_env():
    resolution = resolve([saved("ecommerce", host="replica.internal", username="readonly")], ENV)
    url = make_url(resolution.urls["ecommerce"])
    assert (url.drivername, url.host, url.port, url.database) == (
        "mysql+pymysql",
        "replica.internal",
        3306,
        "ecommerce",
    )
    assert url.username == "readonly"
    assert url.password == "s3cret"  # the password always comes from .env
    assert resolution.origins == {"ecommerce": "settings", "returns_db": "env"}


def test_saved_source_without_env_needs_host_and_database():
    complete = resolve([saved("warehouse", "postgresql", host="wh", database="dw", port="6543", schema="mart")], {})
    url = make_url(complete.urls["warehouse"])
    assert (url.drivername, url.host, url.port, url.database, url.password) == (
        "postgresql+psycopg", "wh", 6543, "dw", None
    )  # fmt: skip
    assert url.query["options"] == "-csearch_path=mart,public"

    incomplete = resolve([saved("warehouse", "postgresql", host="wh")], {})
    assert incomplete.urls == {}
    assert "no host or database" in incomplete.notes[0] and "QUERYMIND_DB_WAREHOUSE is not set" in incomplete.notes[0]


def test_unusable_saved_sources_fall_back_to_env():
    resolution = resolve([saved("ecommerce", port="abc"), saved("returns_db", "cassandra")], ENV)
    assert resolution.urls == ENV  # both fell back
    assert any("not a number" in note for note in resolution.notes)
    assert any("cassandra data sources can't be queried yet" in note for note in resolution.notes)


def test_disabled_sources_are_not_queried_even_with_an_env_url():
    resolution = resolve([saved("ecommerce", enabled=False)], ENV)
    assert set(resolution.urls) == {"returns_db"}
    assert "disabled" in resolution.notes[0]


def test_env_url_of_another_type_is_not_mixed_in():
    resolution = resolve([saved("returns_db", "mysql", host="m", database="r")], ENV)
    url = make_url(resolution.urls["returns_db"])
    assert (url.drivername, url.password, url.username) == ("mysql+pymysql", None, None)


def test_connection_from_url():
    assert connection_from_url(ENV["returns_db"]) == (
        "postgresql",
        {"host": "localhost", "port": "5432", "database": "postgres", "username": "postgres"},
    )
    assert connection_from_url("sqlite:///x.db") is None
    assert connection_from_url("not a url") is None


# -- service ------------------------------------------------------------------------------


@pytest.fixture
def env(monkeypatch):
    for key in [k for k in __import__("os").environ if k.startswith("QUERYMIND_DB_")]:
        monkeypatch.delenv(key)
    for name, url in ENV.items():
        monkeypatch.setenv(f"QUERYMIND_DB_{name.upper()}", url)


def service(**settings):
    return QueryMindService(Settings(qdrant_url=":memory:", source_dir=SQLS, **settings))


def test_seeds_take_connection_details_from_env(env):
    sources = {s.name: s for s in service().datasources.list()}
    assert sources["ecommerce"].connection == {
        "host": "db.internal", "port": "3306", "database": "ecommerce", "username": "root"
    }  # fmt: skip
    assert sources["returns_db"].connection["database"] == "postgres"
    stored = str([s.model_dump() for s in sources.values()])
    assert "s3cret" not in stored and "pg-pass" not in stored  # passwords never reach Qdrant


def test_listing_includes_env_only_databases(env, monkeypatch):
    monkeypatch.setenv("QUERYMIND_DB_ANALYTICS", "postgresql+psycopg://bi:pw@bi.internal/analytics")
    svc = service()
    listed = {s.name: s for s in svc.list_datasources()}
    assert listed["ecommerce"].origin == "qdrant"
    analytics = listed["analytics"]
    assert (analytics.origin, analytics.id, analytics.type) == ("env", "env:analytics", "postgresql")
    assert analytics.connection == {"host": "bi.internal", "database": "analytics", "username": "bi"}
    assert svc.env_datasource("env:analytics") == analytics
    assert svc.env_datasource("env:ecommerce") is None  # saved, so not an env-only entry


def test_queries_use_saved_settings_and_follow_changes(env, tmp_path):
    db = tmp_path / "shop.db"
    sqlite3.connect(db).close()
    svc = service()
    assert set(svc.databases.names) == {"ecommerce", "returns_db"}
    assert make_url(svc.databases.urls["ecommerce"]).host == "db.internal"

    ecommerce = next(s for s in svc.datasources.list() if s.name == "ecommerce")
    svc.datasources.update(
        ecommerce.id, DataSourceInput(**ecommerce.model_dump(include={"name", "type", "sections"}), enabled=False)
    )
    assert svc.databases.names == ["returns_db"]  # rebuilt after the change


def test_queries_fall_back_to_env_when_settings_cannot_be_read(env, monkeypatch):
    svc = service()

    def broken(self):
        raise ConnectionError("qdrant down")

    monkeypatch.setattr(DataSourceRepository, "list", broken)
    assert svc.databases.urls == ENV


def test_injected_registry_is_left_alone(env):
    from querymind.database import DatabaseRegistry

    registry = DatabaseRegistry({"x": "sqlite://"})
    svc = QueryMindService(Settings(qdrant_url=":memory:", source_dir=SQLS), databases=registry)
    svc.datasources.create(DataSourceInput(name="extra", type="mysql"))
    assert svc.databases is registry


def test_repository_reports_changes():
    calls = []
    repo = DataSourceRepository(QdrantClient(":memory:"), "ds", on_change=lambda: calls.append(1))
    source = repo.create(DataSourceInput(name="a", type="mysql"))
    repo.update(source.id, DataSourceInput(name="b", type="mysql"))
    repo.delete(source.id)
    assert len(calls) == 3


def test_notes_name_a_valid_env_variable():
    resolution = resolve([saved("Cassandra source 1", "cassandra")], {})
    assert "QUERYMIND_DB_CASSANDRA_SOURCE_1 is not set" in resolution.notes[0]
