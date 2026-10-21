import sqlite3
from decimal import Decimal

import pytest

from querymind.database import DatabaseRegistry, QueryResult, check_read_only, merge_results
from querymind.database.executor import _plain


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1",
        "select * from orders;",
        "WITH x AS (SELECT 1) SELECT * FROM x",
        "SELECT updated_at, created_at FROM t WHERE note = 'please delete; drop'",
        'SELECT "update" FROM t -- delete everything',
    ],
)
def test_read_only_accepted(sql):
    assert check_read_only(sql) is None


@pytest.mark.parametrize(
    "sql, reason",
    [
        ("DELETE FROM orders", "only SELECT"),
        ("SELECT 1; DROP TABLE orders", "multiple statements"),
        ("WITH d AS (DELETE FROM t RETURNING *) SELECT * FROM d", "DELETE"),
        ("SELECT * INTO OUTFILE '/tmp/x' FROM t", "INTO OUTFILE"),
        ("", "empty"),
    ],
)
def test_read_only_rejected(sql, reason):
    assert reason in check_read_only(sql)


@pytest.fixture
def sqlite_registry(tmp_path):
    path = tmp_path / "shop.db"
    connection = sqlite3.connect(path)
    connection.executescript("""
        CREATE TABLE orders (order_id INTEGER, status TEXT, total REAL);
        INSERT INTO orders VALUES (1, 'delivered', 10.5), (2, 'delivered', 20), (3, 'cancelled', 5);
        CREATE VIEW v_delivered AS SELECT * FROM orders WHERE status = 'delivered';
    """)
    connection.close()
    return DatabaseRegistry({"SHOP": f"sqlite:///{path}"}, max_rows=2)


def test_execute_caps_rows(sqlite_registry):
    result = sqlite_registry.execute("shop", "SELECT order_id, total FROM orders ORDER BY order_id;")
    assert result.ok
    assert result.columns == ["order_id", "total"]
    assert result.rows == [[1, 10.5], [2, 20]]
    assert result.truncated


def test_execute_errors(sqlite_registry):
    assert sqlite_registry.execute("shop", "SELECT nope FROM orders").error_kind == "database"
    assert sqlite_registry.execute("shop", "DELETE FROM orders").error_kind == "unsafe"
    missing = sqlite_registry.execute("warehouse", "SELECT 1")
    assert missing.error_kind == "config"
    assert "QUERYMIND_DB_WAREHOUSE" in missing.error


def test_objects_lists_tables_and_views(sqlite_registry):
    assert sqlite_registry.objects("shop") == ["orders", "v_delivered (view)"]


def test_from_env(monkeypatch):
    monkeypatch.setenv("QUERYMIND_DB_RETURNS_DB", "sqlite://")
    assert "returns_db" in DatabaseRegistry.from_env().names


def test_merge_results_joins_result_sets():
    sales = QueryResult(
        "ecommerce",
        "",
        columns=["order_line_id", "category", "sold_qty"],
        rows=[[1, "Shoes", 4], [2, "Shoes", 6], [3, "Hats", 5]],
    )
    returns = QueryResult("returns_db", "", columns=["order_line_id", "returned_qty"], rows=[[1, 2]])
    merged = merge_results(
        [sales, returns],
        """
        SELECT q1.category, 1.0 * SUM(COALESCE(q2.returned_qty, 0)) / SUM(q1.sold_qty) AS rate
        FROM q1 LEFT JOIN q2 ON q2.order_line_id = q1.order_line_id
        GROUP BY q1.category ORDER BY q1.category""",
    )
    assert merged.rows == [["Hats", 0.0], ["Shoes", 0.2]]


def test_merge_handles_duplicate_columns_and_errors():
    result = QueryResult("a", "", columns=["name", "name"], rows=[["x", "y"]])
    assert merge_results([result], "SELECT name_2 FROM q1").rows == [["y"]]
    assert merge_results([result], "SELECT missing FROM q1").error_kind == "database"
    assert merge_results([result], "DROP TABLE q1").error_kind == "unsafe"


def test_plain_values():
    assert _plain(Decimal("14")) == 14 and isinstance(_plain(Decimal("14")), int)
    assert _plain(Decimal("3.50")) == 3.5
