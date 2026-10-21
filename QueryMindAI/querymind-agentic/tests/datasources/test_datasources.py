import pytest
from pydantic import ValidationError
from qdrant_client import QdrantClient

from querymind.config import Settings
from querymind.datasources import (
    SECTION_KEYS,
    DataSourceInput,
    DataSourceNotFoundError,
    DataSourceRepository,
    DuplicateDataSourceError,
    from_schema_file,
)
from querymind.service import QueryMindService
from support.fakes import SQLS


class Clock:
    def __init__(self):
        self.now = 1_000.0

    def __call__(self):
        self.now += 1
        return self.now


def cassandra(**overrides):
    return DataSourceInput(
        **{"name": "events", "type": "cassandra", "connection": {"contact_points": "10.0.0.1", "port": "9042"}}
        | overrides
    )


@pytest.fixture
def repo():
    return DataSourceRepository(QdrantClient(":memory:"), "ds", clock=Clock())


# -- seeding from the schema files --------------------------------------------------------


def test_mysql_header_seeds_every_section():
    source = from_schema_file(SQLS / "ecommerce_mysql_schema.sql")
    assert (source.name, source.type) == ("ecommerce", "mysql")
    assert source.connection == {"host": "localhost", "port": "3306", "database": "ecommerce"}
    assert list(source.sections) == list(SECTION_KEYS)
    assert source.sections["join_paths"].startswith("Order with customer:")
    assert source.sections["business_rules"].startswith("1. Historical revenue")
    assert "STANDARD JOIN PATHS" not in source.sections["relationships"]  # sections do not run together


def test_postgres_header_maps_its_own_headings():
    source = from_schema_file(SQLS / "returns_postgres_schema.sql")
    assert (source.name, source.type, source.connection["port"]) == ("returns_db", "postgresql", "5432")
    assert set(source.sections) == {
        "purpose", "table_overview", "relationships", "entity_diagram", "returns_questions", "business_rules"
    }  # fmt: skip
    assert source.sections["returns_questions"].startswith("A single SQL statement CANNOT join")
    assert "SNAPSHOT COLUMNS" not in str(source.sections)  # undocumented heading is not merged into others
    assert "\\c returns_db" not in source.sections["business_rules"]  # stops at the closing banner


def test_files_without_a_header_are_skipped(tmp_path):
    path = tmp_path / "plain.sql"
    path.write_text("CREATE TABLE t (id INT);\n")
    assert from_schema_file(path) is None


# -- validation ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides,message",
    [
        ({"connection": {"password": "x"}}, "not used by cassandra"),
        ({"connection": {"host": "db"}}, "not used by cassandra"),
        ({"connection": {"port": "1\n2"}}, "single line"),
        ({"name": "  "}, "non-empty"),
        ({"type": "oracle"}, "type"),
        ({"sections": {"unknown": "x"}}, "sections"),
        ({"sections": {"purpose": "x" * 20_001}}, "longer than"),
        ({"owner": "me"}, "Extra inputs"),
    ],
)
def test_invalid_input_is_rejected(overrides, message):
    with pytest.raises(ValidationError, match=message):
        cassandra(**overrides)


def test_connection_values_are_trimmed():
    assert cassandra(connection={"contact_points": " 10.0.0.1 "}).connection == {"contact_points": "10.0.0.1"}


# -- repository ---------------------------------------------------------------------------


def test_create_get_update_delete(repo):
    created = repo.create(cassandra())
    assert repo.get(created.id) == created
    assert repo.list() == [created]

    changed = repo.update(created.id, cassandra(name="clickstream", enabled=False))
    assert (changed.name, changed.enabled, changed.created_at) == ("clickstream", False, created.created_at)
    assert changed.updated_at > created.updated_at
    assert repo.get(created.id).name == "clickstream"

    repo.delete(created.id)
    assert repo.list() == []
    with pytest.raises(DataSourceNotFoundError):
        repo.get(created.id)


def test_names_are_unique_ignoring_case(repo):
    first = repo.create(cassandra(name="Events"))
    with pytest.raises(DuplicateDataSourceError):
        repo.create(cassandra(name="events"))
    second = repo.create(cassandra(name="other"))
    with pytest.raises(DuplicateDataSourceError):
        repo.update(second.id, cassandra(name="EVENTS"))
    repo.update(first.id, cassandra(name="events"))  # renaming itself is fine


def test_unknown_or_malformed_ids_are_not_found(repo):
    for bad in ("00000000-0000-0000-0000-000000000000", "not-a-uuid"):
        with pytest.raises(DataSourceNotFoundError):
            repo.get(bad)
        with pytest.raises(DataSourceNotFoundError):
            repo.delete(bad)


def test_seeded_once_in_order():
    calls = []

    def seed():
        calls.append(1)
        return [cassandra(name="first"), cassandra(name="second")]

    client = QdrantClient(":memory:")
    repo = DataSourceRepository(client, "ds", seed=seed)
    assert [s.name for s in repo.list()] == ["first", "second"]
    repo.delete(repo.list()[0].id)
    # a new repository on the same collection does not seed again
    assert [s.name for s in DataSourceRepository(client, "ds", seed=seed).list()] == ["second"]
    assert calls == [1]


def test_service_seeds_from_the_schema_files():
    service = QueryMindService(Settings(qdrant_url=":memory:", source_dir=SQLS))
    sources = service.datasources.list()
    assert [(s.name, s.type) for s in sources] == [("ecommerce", "mysql"), ("returns_db", "postgresql")]
    assert service._llm is None and service._store is None  # no model or embedding needed
