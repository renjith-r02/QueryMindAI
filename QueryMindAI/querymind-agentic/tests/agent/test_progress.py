import pytest

from querymind.agent import QueryMindAgent, QueryMindRAG
from support.fakes import ScriptedLLM, plan


def steps(events):
    return [(event.id, event.status) for event in events]


def test_run_reports_each_step(store, databases):
    events = []
    llm = ScriptedLLM(plan(("ecommerce", "SELECT category, SUM(quantity) AS n FROM order_lines GROUP BY 1")))
    result = QueryMindAgent(QueryMindRAG(store, llm), databases).run("units by category", on_progress=events.append)

    assert result.status == "answered"
    assert steps(events) == [
        ("classify", "running"),
        ("classify", "done"),
        ("retrieve", "running"),
        ("retrieve", "done"),
        ("schema", "running"),
        ("schema", "done"),
        ("generate-1", "running"),
        ("generate-1", "done"),
        ("execute-1-1", "running"),
        ("execute-1-1", "done"),
        ("answer", "running"),
        ("answer", "done"),
    ]
    executed = events[9]
    assert executed.message.startswith("2 rows from ecommerce in ")
    assert executed.detail["rows"] == 2
    assert events[7].detail["queries"][0]["database"] == "ecommerce"


def test_failed_query_and_repair_are_reported(store, databases):
    events = []
    llm = ScriptedLLM(
        plan(("ecommerce", "SELECT nope FROM order_lines")),
        plan(("ecommerce", "SELECT COUNT(*) AS n FROM order_lines")),
    )
    QueryMindAgent(QueryMindRAG(store, llm), databases).run("count", on_progress=events.append)

    failed = next(event for event in events if event.status == "failed")
    assert failed.id == "execute-1-1" and "nope" in failed.message
    retry = next(event for event in events if event.id == "generate-2")
    assert retry.message == "Rewriting the SQL to fix the error (attempt 2)"


def test_merge_step_is_reported(store, databases):
    events = []
    llm = ScriptedLLM(
        plan(
            ("ecommerce", "SELECT 1 AS a"),
            ("returns_db", "SELECT 2 AS b"),
            merge_sql="SELECT q1.a + q2.b AS total FROM q1, q2",
        )
    )
    QueryMindAgent(QueryMindRAG(store, llm), databases).run("sum", on_progress=events.append)
    assert ("merge-1", "done") in steps(events)
    assert ("execute-1-2", "done") in steps(events)


def test_callback_can_cancel_the_run(store, databases):
    class Cancelled(Exception):
        pass

    def stop_after_retrieval(event):
        if event.id == "schema":
            raise Cancelled

    llm = ScriptedLLM(plan(("ecommerce", "SELECT 1")))
    with pytest.raises(Cancelled):
        QueryMindAgent(QueryMindRAG(store, llm), databases).run("q", on_progress=stop_after_retrieval)
    assert llm.prompts == []  # no SQL was generated
    assert len(llm.plans) == 1


def test_ask_reports_retrieval_and_generation(store):
    events = []
    QueryMindRAG(store, ScriptedLLM(plan(("ecommerce", "SELECT 1")))).answer("q", on_progress=events.append)
    assert steps(events) == [
        ("classify", "running"),
        ("classify", "done"),
        ("retrieve", "running"),
        ("retrieve", "done"),
        ("generate-1", "running"),
        ("generate-1", "done"),
    ]
