import json
from collections import Counter

import pytest

from querymind.ingest import load_qa_file, parse_sql, parse_sql_file
from support.fakes import SQLS


@pytest.fixture(scope="module")
def mysql_chunks():
    return {c.title: c for c in parse_sql_file(SQLS / "ecommerce_mysql_schema.sql")}


@pytest.fixture(scope="module")
def postgres_chunks():
    return {c.title: c for c in parse_sql_file(SQLS / "returns_postgres_schema.sql")}


def _counts(chunks):
    return Counter(c.doc_type for c in chunks.values())


def test_detects_database_and_dialect(mysql_chunks, postgres_chunks):
    assert {(c.database, c.dialect) for c in mysql_chunks.values()} == {("ecommerce", "mysql")}
    assert {(c.database, c.dialect) for c in postgres_chunks.values()} == {("returns_db", "postgresql")}


def test_mysql_chunk_counts(mysql_chunks):
    counts = _counts(mysql_chunks)
    assert counts["table"] == 7
    assert counts["view"] == 2
    assert counts["business_rule"] == 12
    assert counts["example_query"] == 10
    assert counts["overview"] == 1


def test_postgres_chunk_counts(postgres_chunks):
    counts = _counts(postgres_chunks)
    assert counts["table"] == 2
    assert counts["view"] == 2
    assert counts["business_rule"] == 11
    assert counts["example_query"] == 10


def test_mysql_inline_comments_with_semicolons(mysql_chunks):
    # The order_line_id comment contains a ';' inside the string literal.
    column = mysql_chunks["order_lines.order_line_id"]
    assert "the key for merging sales with returns" in column.content
    assert len(mysql_chunks["order_lines"].metadata["columns"]) == 14


def test_postgres_comment_on_is_merged(postgres_chunks):
    table = postgres_chunks["rma.returns"]
    assert table.content.startswith("Table: rma.returns")
    assert "Return header (RMA)" in table.content
    assert "CREATE INDEX idx_returns_order" in table.content
    assert "Lifecycle: requested -> approved" in postgres_chunks["rma.returns.status"].content
    assert "One row per MySQL order_line_id" in postgres_chunks["rma.v_returned_by_order_line"].content


def test_dollar_quoted_function_is_one_statement(postgres_chunks):
    routine = postgres_chunks["rma.set_updated_at"]
    assert "NEW.updated_at := now();" in routine.content
    assert "keep updated_at current" in routine.content


def test_example_question_and_sql(mysql_chunks):
    example = mysql_chunks["Q4: Customer lifetime gross revenue and order count."]
    assert example.embed_text == "Customer lifetime gross revenue and order count."
    assert example.metadata["sql"].endswith("ORDER BY lifetime_gross_revenue DESC;")
    assert example.metadata["notes"].startswith("(For NET lifetime value")


def test_wrapped_question_is_joined(mysql_chunks):
    example = next(c for t, c in mysql_chunks.items() if t.startswith("Q9:"))
    assert example.metadata["question"].endswith("WHERE order_number = 'ORD-2026-000123').")
    assert example.metadata["sql"].startswith("SELECT ol.order_line_id")


def test_multi_database_example_keeps_full_answer(postgres_chunks):
    example = next(c for t, c in postgres_chunks.items() if t.startswith("Q8:"))
    assert example.metadata["scope"].startswith("Needs MySQL too")
    assert "sql" not in example.metadata
    assert "Merge: LEFT JOIN MySQL rows" in example.metadata["answer"]


def test_business_rule_keeps_formula_layout(mysql_chunks):
    rule = next(c for t, c in mysql_chunks.items() if t.startswith("Rule 6:"))
    assert "Revenue definitions:\n    gross line revenue  = order_lines.line_total\n" in rule.content


def test_documentation_sections(mysql_chunks):
    assert "STANDARD JOIN PATHS (MySQL)" in mysql_chunks
    overview = next(c for c in mysql_chunks.values() if c.doc_type == "overview")
    assert "SQL DIALECT: MySQL" in overview.content


def test_minimal_file_without_header():
    chunks = parse_sql(
        "CREATE TABLE t (id INT PRIMARY KEY COMMENT 'Key; unique', name TEXT) COMMENT='Things';",
        source="mini_mysql.sql",
    )
    by_title = {c.title: c for c in chunks}
    assert by_title["t"].database == "mini_mysql"
    assert by_title["t"].dialect == "mysql"
    assert "Things" in by_title["t"].content
    assert "Key; unique" in by_title["t.id"].content


def test_qa_file(tmp_path):
    path = tmp_path / "pairs.json"
    path.write_text(
        json.dumps(
            [
                {
                    "question": "How many orders last week?",
                    "sql": "SELECT COUNT(*) FROM orders WHERE placed_at >= NOW() - INTERVAL 7 DAY;",
                    "database": "ecommerce",
                    "dialect": "MySQL",
                }
            ]
        )
    )
    [chunk] = load_qa_file(path)
    assert chunk.doc_type == "qa_pair"
    assert chunk.dialect == "mysql"
    assert chunk.embed_text == "How many orders last week?"
    assert chunk.metadata["sql"].startswith("SELECT COUNT(*)")


def test_qa_file_rejects_incomplete_pair(tmp_path):
    path = tmp_path / "pairs.json"
    path.write_text(json.dumps({"pairs": [{"question": "No answer"}]}))
    with pytest.raises(ValueError):
        load_qa_file(path)
