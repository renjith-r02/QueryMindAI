from querymind.intent import IntentClassification, IntentClassifier
from support.fakes import intent

TABLES = ["orders", "order_lines", "products"]
COLUMNS = ["orders.placed_at", "order_lines.line_total", "products.name"]


class FixedLLM:
    model_name = "fixed"

    def __init__(self, answer=None, error=None):
        self.answer, self.error, self.calls = answer, error, []

    def generate(self, system, prompt, schema):
        assert schema is IntentClassification
        self.calls.append((system, prompt))
        if self.error:
            raise self.error
        return self.answer


def test_model_classification_is_grounded_in_the_schema():
    llm = FixedLLM(
        intent(
            "SELECT_TEMPORAL",
            traits=["aggregate", "temporal", "join"],
            tables=["Orders", "order_lines", "invented_table"],
            columns=["order_lines.line_total", "orders.made_up"],
            reason="Revenue by month.",
        )
    )
    result = IntentClassifier(llm).classify("revenue by month this year", TABLES, COLUMNS)

    assert result.query_type == "SELECT_TEMPORAL"
    assert result.traits == ["aggregate", "join", "temporal"]
    assert result.tables_mentioned == ["orders", "order_lines"]  # unknown names dropped, schema spelling
    assert result.columns_mentioned == ["order_lines.line_total"]
    assert result.source == "model" and not result.blocked

    system, prompt = llm.calls[0]
    assert "SELECT_AGGREGATE" in system and "UNSUPPORTED" in system
    assert "order_lines.line_total" in prompt and prompt.endswith("# Question\nrevenue by month this year")


def test_rules_refuse_without_calling_the_model():
    llm = FixedLLM(intent("SELECT_SIMPLE"))
    result = IntentClassifier(llm).classify("delete all test users", TABLES, COLUMNS)
    assert result.blocked and result.source == "rules"
    assert "Deleting data is not allowed" in result.blocked_message
    assert llm.calls == []


def test_model_can_refuse_a_paraphrased_delete():
    llm = FixedLLM(intent("UNSUPPORTED", reason="Wants rows removed."))
    result = IntentClassifier(llm).classify("make the cancelled orders disappear", TABLES, COLUMNS)
    assert result.blocked and result.source == "model"
    assert "not allowed" in result.blocked_message


def test_update_is_classified_but_not_blocked():
    llm = FixedLLM(intent("UPDATE", tables=["orders"], columns=["orders.placed_at"]))
    result = IntentClassifier(llm).classify("move order 5's date to yesterday", TABLES, COLUMNS)
    assert result.is_update and not result.blocked
    assert result.traits == []  # traits only describe reads


def test_falls_back_to_rules_when_the_model_fails():
    result = IntentClassifier(FixedLLM(error=RuntimeError("quota"))).classify("orders per month", TABLES, COLUMNS)
    assert result.query_type == "SELECT_TEMPORAL"
    assert result.source == "rules-fallback"


def test_works_without_a_model():
    result = IntentClassifier(None).classify("how many orders", TABLES, COLUMNS)
    assert result.query_type == "SELECT_AGGREGATE" and result.tables_mentioned == ["orders"]
