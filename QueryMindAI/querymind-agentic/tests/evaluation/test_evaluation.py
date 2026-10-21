import json
import sqlite3
import warnings
from collections import Counter

import pytest

from querymind.config import Settings
from querymind.database import DatabaseRegistry, QueryResult
from querymind.evaluation import (
    DEFAULT_FEW_SHOT,
    DEFAULT_TEST_SET,
    Evaluator,
    compare_results,
    exact_match,
    load_few_shot,
    load_test_set,
    render_markdown,
    semantic_match,
    summary,
    validate,
    write_report,
)
from querymind.ingest import load_qa_file
from querymind.service import QueryMindService
from support.fakes import SQLS, HashingEmbedder, ScriptedLLM, plan


def table(columns, rows, error=None):
    return QueryResult("db", "", columns=columns, rows=rows, error=error)


# -- the shipped library and test set ------------------------------------------------------


def test_few_shot_library_covers_every_type_in_both_databases():
    examples = load_few_shot(DEFAULT_FEW_SHOT)
    assert len(examples) >= 30
    counts = Counter((e.database, e.query_type) for e in examples)
    for database in ("ecommerce", "returns_db"):
        for query_type in ("SELECT_SIMPLE", "SELECT_AGGREGATE", "SELECT_JOIN", "SELECT_TEMPORAL", "UPDATE"):
            assert counts[database, query_type] >= 1, (database, query_type)
    chunks = load_qa_file(DEFAULT_FEW_SHOT)  # indexable as qa_pair chunks with their labels
    assert chunks[0].metadata["query_type"] == "SELECT_SIMPLE" and chunks[0].metadata["example_id"] == "FS01"


def test_test_set_has_25_cases_that_do_not_repeat_the_few_shot_questions():
    test_set = load_test_set(DEFAULT_TEST_SET)
    assert len(test_set.cases) == 25
    assert {c.query_type for c in test_set.cases} == {
        "SELECT_SIMPLE", "SELECT_AGGREGATE", "SELECT_JOIN", "SELECT_TEMPORAL"
    }  # fmt: skip
    assert {c.database for c in test_set.cases} == {"ecommerce", "returns_db"}
    few_shot = {e.question.lower() for e in load_few_shot(DEFAULT_FEW_SHOT)}
    assert not few_shot & {c.question.lower() for c in test_set.cases}


# -- execution comparison ------------------------------------------------------------------


def test_results_match_ignoring_names_column_order_row_order_and_number_types():
    truth = table(["status", "n"], [["shipped", 5], ["delivered", 91]])
    assert compare_results(truth, table(["cnt", "s"], [[91.0, "delivered"], [5, "shipped"]])).match


def test_order_matters_only_when_asked():
    truth = table(["m", "n"], [["2025-01", 1], ["2025-02", 2]])
    flipped = table(["m", "n"], [["2025-02", 2], ["2025-01", 1]])
    assert compare_results(truth, flipped).match
    result = compare_results(truth, flipped, order_matters=True)
    assert not result.match and result.reason == "same rows in a different order"


def test_rounding_is_tolerated_but_different_counts_are_not():
    assert compare_results(table(["avg"], [[12.3456]]), table(["avg"], [[12.35]])).match
    assert compare_results(table(["avg"], [[8.647727]]), table(["avg"], [[8.6]])).match  # rounded to 1 dp
    assert not compare_results(table(["avg"], [[12.3]]), table(["avg"], [[12.4]])).match
    assert not compare_results(table(["avg"], [[3.4]]), table(["avg"], [[3.0]])).match
    assert not compare_results(table(["n"], [[150]]), table(["n"], [[151]])).match


def test_extra_columns_pass_only_the_relaxed_check():
    truth = table(["sku"], [["A"], ["B"]])
    result = compare_results(truth, table(["sku", "name"], [["A", "x"], ["B", "y"]]))
    assert (result.match, result.relaxed_match, result.reason) == (False, True, "1 extra column(s)")


@pytest.mark.parametrize(
    "actual,reason",
    [
        (table(["n"], [[1]]), "1 rows instead of 2"),
        (table(["n"], [], error="boom"), "generated SQL failed: boom"),
        (table(["n"], [[1], [3]]), "different values"),
    ],
)
def test_mismatches_say_why(actual, reason):
    assert compare_results(table(["n"], [[1], [2]]), actual).reason == reason


# -- SQL matching ----------------------------------------------------------------------------


def test_exact_match_normalises_whitespace_case_and_semicolons():
    assert exact_match("select sku ,name from products where status='active';", "SELECT sku, name\nFROM products\n"
                       "WHERE status = 'active'", "mysql")  # fmt: skip
    assert not exact_match("SELECT sku FROM products", "SELECT name FROM products", "mysql")


def test_semantic_match_ignores_aliases_and_qualification():
    schema = {"orders": {"order_id": "INT", "status": "TEXT"}, "users": {"user_id": "INT"}}
    truth = "SELECT status, COUNT(*) AS orders FROM orders GROUP BY status"
    generated = "SELECT o.status, COUNT(*) AS order_count FROM orders o GROUP BY o.status"
    assert not exact_match(generated, truth, "mysql")
    assert semantic_match(generated, truth, "mysql", schema) == (True, 0)
    different, edits = semantic_match("SELECT status FROM orders", truth, "mysql", schema)
    assert not different and edits > 0


def test_semantic_match_can_ignore_a_final_order_by_but_not_one_a_limit_needs():
    truth = "SELECT sku FROM products WHERE status = 'active'"
    ordered = "SELECT sku FROM products WHERE status = 'active' ORDER BY sku"
    assert not semantic_match(ordered, truth, "mysql")[0]
    assert semantic_match(ordered, truth, "mysql", ignore_order=True)[0]
    top = "SELECT sku FROM products ORDER BY sku LIMIT 5"
    assert not semantic_match(top, "SELECT sku FROM products LIMIT 5", "mysql", ignore_order=True)[0]


# -- the harness, offline ----------------------------------------------------------------------


@pytest.fixture
def evaluation_files(tmp_path):
    test_set = {
        "name": "mini",
        "cases": [
            {"id": "C1", "query_type": "SELECT_SIMPLE", "database": "ecommerce", "dialect": "sqlite",
             "question": "list n", "ground_truth_sql": "SELECT n FROM t"},
            {"id": "C2", "query_type": "SELECT_AGGREGATE", "database": "ecommerce", "dialect": "sqlite",
             "question": "sum of n", "ground_truth_sql": "SELECT SUM(n) FROM t"},
        ],
        "guardrail_probes": [{"id": "G1", "question": "delete all rows of t"}],
    }  # fmt: skip
    few_shot = {"pairs": [{"id": "F1", "query_type": "SELECT_SIMPLE", "database": "ecommerce", "dialect": "sqlite",
                           "question": "largest n", "sql": "SELECT MAX(n) FROM t"}]}  # fmt: skip
    (tmp_path / "test_set.json").write_text(json.dumps(test_set))
    (tmp_path / "few_shot.json").write_text(json.dumps(few_shot))
    return tmp_path / "test_set.json", tmp_path / "few_shot.json"


@pytest.fixture
def service(tmp_path):
    shop = tmp_path / "shop.db"
    with sqlite3.connect(shop) as connection:
        connection.executescript("CREATE TABLE t (n INTEGER); INSERT INTO t VALUES (1), (2), (3);")
    service = QueryMindService(
        Settings(qdrant_url=":memory:", collection="kb", source_dir=SQLS, cache_enabled=False),
        embedder=HashingEmbedder(),
        # C1 is answered correctly; C2 sums the wrong thing.
        llm=ScriptedLLM(plan(("ecommerce", "select n from t;")), plan(("ecommerce", "SELECT COUNT(n) FROM t"))),
        databases=DatabaseRegistry({"ecommerce": f"sqlite:///{shop}"}),
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # local Qdrant ignores payload indexes
        service.index()
    return service


def test_validate_runs_ground_truth_and_few_shot_sql(service, evaluation_files, tmp_path):
    assert validate(service, *evaluation_files) == (3, [])
    broken = json.loads(evaluation_files[0].read_text())
    broken["cases"][0]["ground_truth_sql"] = "SELECT missing FROM t"
    evaluation_files[0].write_text(json.dumps(broken))
    checked, issues = validate(service, *evaluation_files)
    assert [(i.source, i.id) for i in issues] == [("test_set", "C1")]


def test_harness_scores_cases_probes_and_writes_the_report(service, evaluation_files, tmp_path):
    seen = []
    run = Evaluator(service, on_case=seen.append).run(*evaluation_files)
    assert [c.id for c in seen] == ["C1", "C2"]
    first, second = run.cases
    assert (first.execution_match, first.exact_match, first.status) == (True, True, "answered")
    assert (second.execution_match, second.exact_match, second.reason) == (False, False, "different values")
    assert run.probes[0].compliant and run.probes[0].status == "blocked" and not run.probes[0].executed

    totals = summary(run)
    assert totals["overall"]["execution_accuracy"] == 0.5
    assert totals["by_query_type"]["SELECT_SIMPLE"]["execution_accuracy"] == 1.0
    assert totals["by_query_type"]["SELECT_AGGREGATE"]["execution_accuracy"] == 0.0
    assert totals["guardrail_compliance"] == 1.0

    markdown, data = write_report(run, tmp_path / "report")
    text = markdown.read_text()
    assert "| **Execution accuracy** (same result set as the ground truth) | **50.0%** (1/2) |" in text
    assert "## Accuracy by query type" in text and "### C2 · SELECT_AGGREGATE · ecommerce" in text
    assert json.loads(data.read_text())["summary"]["overall"]["cases"] == 2
    assert render_markdown(run) == text
