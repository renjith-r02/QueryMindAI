"""Fixtures shared by the whole suite: an in-memory knowledge store and SQLite databases."""

import sqlite3
import warnings

import pytest

from querymind.database import DatabaseRegistry
from querymind.ingest import parse_sql_file
from querymind.knowledge import KnowledgeStore
from support.fakes import SQLS, HashingEmbedder


@pytest.fixture(scope="session")
def store():
    store = KnowledgeStore(":memory:", "kb", HashingEmbedder())
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # local Qdrant ignores payload indexes
        store.ensure_collection()
    for name in ("ecommerce_mysql_schema.sql", "returns_postgres_schema.sql"):
        store.replace_source(name, parse_sql_file(SQLS / name))
    return store


@pytest.fixture
def databases(tmp_path):
    shop, rma = tmp_path / "shop.db", tmp_path / "rma.db"
    with sqlite3.connect(shop) as connection:
        connection.executescript("""
            CREATE TABLE order_lines (order_line_id INTEGER, category TEXT, quantity INTEGER);
            INSERT INTO order_lines VALUES (1, 'Shoes', 4), (2, 'Shoes', 6), (3, 'Hats', 5);
        """)
    with sqlite3.connect(rma) as connection:
        connection.executescript("""
            CREATE TABLE return_lines (order_line_id INTEGER, quantity INTEGER);
            INSERT INTO return_lines VALUES (1, 2);
        """)
    return DatabaseRegistry({"ecommerce": f"sqlite:///{shop}", "returns_db": f"sqlite:///{rma}"})
