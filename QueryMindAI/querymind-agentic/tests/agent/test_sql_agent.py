from querymind.agent import QueryMindAgent, QueryMindRAG
from querymind.agent.rag import build_prompt
from support.fakes import ScriptedLLM, plan


def test_retrieval_covers_doc_types(store):
    rag = QueryMindRAG(store, ScriptedLLM())
    context = rag.retrieve("refund amount paid per month for returns")
    assert {"overview", "table", "column", "business_rule", "example_query"} <= {i.doc_type for i in context}
    assert [i.id for i in context] == [f"S{n}" for n in range(1, len(context) + 1)]
    prompt = build_prompt("q", context)
    assert "## Tables and views" in prompt and prompt.endswith("# Question\nq")


def test_single_database_answer(store, databases):
    llm = ScriptedLLM(
        plan(
            (
                "ecommerce",
                "SELECT category, SUM(quantity) AS units FROM order_lines GROUP BY category ORDER BY category",
            )
        )
    )
    result = QueryMindAgent(QueryMindRAG(store, llm), databases).run("units by category")

    assert result.status == "answered"
    assert result.final.answer == "final"
    assert result.result.rows == [["Hats", 5], ["Shoes", 10]]
    assert "## Live database objects" in llm.prompts[0]
    assert "ecommerce (sqlite): order_lines" in llm.prompts[0]
    assert '["Hats", 5]' in llm.prompts[-1]  # results were handed to the final LLM call


def test_cross_database_merge(store, databases):
    llm = ScriptedLLM(
        plan(
            ("ecommerce", "SELECT order_line_id, category, quantity AS sold_qty FROM order_lines"),
            ("returns_db", "SELECT order_line_id, SUM(quantity) AS returned_qty FROM return_lines GROUP BY 1"),
            merge_sql="SELECT q1.category, 1.0 * SUM(COALESCE(q2.returned_qty, 0)) / SUM(q1.sold_qty) AS rate "
            "FROM q1 LEFT JOIN q2 USING (order_line_id) GROUP BY q1.category ORDER BY q1.category",
        )
    )
    result = QueryMindAgent(QueryMindRAG(store, llm), databases).run("return rate by category")
    assert result.status == "answered"
    assert result.result.rows == [["Hats", 0.0], ["Shoes", 0.2]]


def test_repairs_failed_sql(store, databases):
    llm = ScriptedLLM(
        plan(("ecommerce", "SELECT no_such_column FROM order_lines")),
        plan(("ecommerce", "SELECT COUNT(*) AS n FROM order_lines")),
    )
    result = QueryMindAgent(QueryMindRAG(store, llm), databases).run("how many lines")
    assert result.status == "answered"
    assert len(result.attempts) == 2
    assert "Previous attempt failed" in llm.prompts[1]
    assert "no_such_column" in llm.prompts[1]
    assert result.result.rows == [[3]]


def test_missing_merge_sql_is_repaired(store, databases):
    queries = (("ecommerce", "SELECT 1 AS a"), ("returns_db", "SELECT 2 AS b"))
    llm = ScriptedLLM(plan(*queries), plan(*queries, merge_sql="SELECT q1.a + q2.b AS total FROM q1, q2"))
    result = QueryMindAgent(QueryMindRAG(store, llm), databases).run("sum")
    assert result.result.rows == [[3]]
    assert "merge_sql is missing" in llm.prompts[1]


def test_gives_up_after_max_repairs(store, databases):
    bad = plan(("ecommerce", "SELECT broken FROM nowhere"))
    llm = ScriptedLLM(bad, bad)
    result = QueryMindAgent(QueryMindRAG(store, llm), databases, max_repairs=1).run("q")
    assert result.status == "failed"
    assert result.final is None
    assert len(result.attempts) == 2


def test_unconfigured_database_is_not_retried(store, databases):
    llm = ScriptedLLM(plan(("warehouse", "SELECT 1")))
    result = QueryMindAgent(QueryMindRAG(store, llm), databases).run("q")
    assert result.status == "failed"
    assert result.attempts[-1].errors[0].error_kind == "config"
    assert len(llm.prompts) == 1


def test_not_answerable_skips_execution(store, databases):
    llm = ScriptedLLM(plan(answerable=False))
    result = QueryMindAgent(QueryMindRAG(store, llm), databases).run("profit margin?")
    assert result.status == "not_answerable"
    assert result.to_dict()["final"] is None
