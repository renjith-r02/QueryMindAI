"""How the agent and RAG act on the classified intent."""

import pytest

from querymind.agent import QueryMindAgent, QueryMindRAG
from querymind.agent.rag import UPDATE_INSTRUCTION
from support.fakes import ScriptedLLM, intent, plan


def run(store, databases, llm, question="q"):
    events = []
    result = QueryMindAgent(QueryMindRAG(store, llm), databases).run(question, on_progress=events.append)
    return result, events


def test_select_intent_is_passed_to_the_generator(store, databases):
    llm = ScriptedLLM(
        plan(("ecommerce", "SELECT category, SUM(quantity) AS n FROM order_lines GROUP BY 1")),
        intent=intent("SELECT_AGGREGATE", traits=["aggregate"], tables=["order_lines"], reason="Totals."),
    )
    result, events = run(store, databases, llm, "units by category")

    assert result.status == "answered"
    assert result.intent.query_type == "SELECT_AGGREGATE"
    assert result.intent.tables_mentioned == ["order_lines"]
    assert "## Question type (from the intent classifier)\nSELECT_AGGREGATE: Totals." in llm.prompts[0]
    classify = [e for e in events if e.id == "classify"]
    assert classify[-1].status == "done" and classify[-1].message.startswith("Aggregate question (SELECT_AGGREGATE)")


@pytest.mark.parametrize("question", ["delete all cancelled orders", "DROP TABLE orders"])
def test_prohibited_request_never_reaches_retrieval_or_generation(store, databases, question):
    llm = ScriptedLLM(plan(("ecommerce", "SELECT 1")))
    result, events = run(store, databases, llm, question)

    assert result.status == "blocked"
    assert result.intent.query_type == "UNSUPPORTED" and result.intent.source == "rules"
    assert result.context == [] and result.final is None
    assert result.plan.queries == [] and "not allowed" in result.plan.explanation
    assert llm.classified == [] and llm.prompts == []  # no model call at all
    assert [(e.id, e.status) for e in events] == [("classify", "running"), ("classify", "failed")]
    assert result.to_dict()["intent"]["blocked_message"]


def test_model_refusal_blocks_too(store, databases):
    llm = ScriptedLLM(plan(("ecommerce", "SELECT 1")), intent=intent("UNSUPPORTED", reason="Removes rows."))
    result, _ = run(store, databases, llm, "make the test customers vanish")
    assert result.status == "blocked" and llm.prompts == []


def test_update_is_drafted_and_never_executed(store, databases, tmp_path):
    sql = "UPDATE order_lines SET quantity = 0 WHERE order_line_id = 3"
    llm = ScriptedLLM(plan(("ecommerce", sql)), intent=intent("UPDATE", tables=["order_lines"]))
    result, events = run(store, databases, llm, "set the quantity of line 3 to zero")

    assert result.status == "generated"
    assert result.plan.queries[0].sql == sql
    assert result.attempts[0].results == []  # nothing was executed
    assert llm.systems == [UPDATE_INSTRUCTION]
    assert "did not run it" in result.final.answer
    assert not any(e.id.startswith("execute") for e in events)
    assert ("generate-1", "done") in [(e.id, e.status) for e in events]
    # the database is untouched
    assert databases.execute("ecommerce", "SELECT quantity FROM order_lines WHERE order_line_id = 3").rows == [[5]]


@pytest.mark.parametrize(
    "sql,reason",
    [
        ("DELETE FROM order_lines WHERE order_line_id = 3", "only an UPDATE statement can be drafted"),
        ("UPDATE order_lines SET quantity = 0", "without a WHERE clause"),
        ("UPDATE order_lines SET quantity = 0 WHERE 1=1; DROP TABLE order_lines", "multiple statements"),
    ],
)
def test_unsafe_update_drafts_are_withheld(store, databases, sql, reason):
    llm = ScriptedLLM(plan(("ecommerce", sql)), intent=intent("UPDATE"))
    result, events = run(store, databases, llm, "zero out line 3")

    assert result.status == "failed"
    assert result.plan.queries == []  # the unsafe statement is never returned
    assert any(reason in warning for warning in result.warnings)
    assert sql not in str(result.to_dict())
    assert ("generate-1", "failed") in [(e.id, e.status) for e in events]


def test_ask_classifies_and_refuses(store):
    rag = QueryMindRAG(store, ScriptedLLM(plan(("ecommerce", "SELECT 1"))))
    answer = rag.answer("please remove every user")
    assert answer.status == "blocked"
    assert answer.answer.queries == [] and answer.context == []
    assert answer.to_dict()["intent"]["query_type"] == "UNSUPPORTED"


def test_ask_drafts_an_update(store):
    sql = "UPDATE orders SET status = 'shipped' WHERE order_id = 7"
    rag = QueryMindRAG(store, ScriptedLLM(plan(("ecommerce", sql)), intent=intent("UPDATE")))
    answer = rag.answer("mark order 7 as shipped")
    assert answer.status == "generated"
    assert answer.answer.queries[0].sql == sql


def test_schema_names_come_from_the_store(store):
    names = store.schema_names()
    assert "orders" in names.tables and "rma.returns" in names.tables
    assert "order_lines.line_total" in names.columns
    returns_only = store.schema_names("returns_db")
    assert "orders" not in returns_only.tables and "rma.returns" in returns_only.tables
