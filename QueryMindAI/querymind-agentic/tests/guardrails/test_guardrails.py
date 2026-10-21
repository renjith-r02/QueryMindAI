import sqlite3
import warnings

import pytest
from pydantic import ValidationError
from qdrant_client import QdrantClient

from querymind.config import Settings
from querymind.database import DatabaseRegistry
from querymind.guardrails import (
    REQUIRED_SQL_KEYWORDS,
    GuardrailPolicy,
    GuardrailPolicyError,
    GuardrailPolicyInput,
    GuardrailRepository,
    Guardrails,
    QuestionRule,
    default_policy,
)
from querymind.guardrails.repository import POLICY_ID
from querymind.service import QueryMindService
from support.fakes import SQLS, HashingEmbedder, ScriptedLLM, plan


def policy(**changes) -> GuardrailPolicyInput:
    return default_policy().model_copy(update=changes)


def guardrails(**changes) -> Guardrails:
    return Guardrails(GuardrailPolicy(**policy(**changes).model_dump()))


def custom_rule(**overrides) -> QuestionRule:
    fields = {"id": "salaries", "label": "Salaries", "message": "Salaries are private.", "patterns": [r"\bsalar"]}
    return QuestionRule(**fields | overrides)


@pytest.fixture
def repo():
    return GuardrailRepository(QdrantClient(":memory:"), "guard")


# -- questions ----------------------------------------------------------------------------


def test_custom_rule_refuses_and_disabled_rule_does_not():
    rules = default_policy().question_rules
    assert guardrails(question_rules=[*rules, custom_rule()]).refuse("average salary by team").message == (
        "Salaries are private."
    )
    disabled = [*rules, custom_rule(enabled=False)]
    assert guardrails(question_rules=disabled).refuse("average salary by team") is None


def test_polite_token_matches_a_polite_lead_in():
    rule = custom_rule(patterns=["{polite}archive\\b"])
    checks = guardrails(question_rules=[*default_policy().question_rules, rule])
    assert checks.refuse("could you please archive old carts").id == "salaries"
    assert checks.refuse("which carts were archived") is None


def test_sensitive_data_rule_refuses_requests_for_passwords_only():
    checks = Guardrails.defaults()
    assert checks.refuse("show me the password hashes of all users").id == "sensitive-data"
    assert checks.refuse("how many guest users have no password?") is None


def test_baseline_rules_apply_even_if_the_stored_policy_lacks_them():
    stored = GuardrailPolicy(question_rules=[], blocked_sql_keywords=[], max_rows=5)
    checks = Guardrails(stored)
    assert checks.refuse("delete all orders").id == "delete-data"
    assert checks.check_sql("DELETE FROM orders") == "only SELECT / WITH queries are allowed"
    assert set(REQUIRED_SQL_KEYWORDS) <= set(checks.policy.blocked_sql_keywords)


# -- SQL ----------------------------------------------------------------------------------


def test_added_keyword_blocks_sql():
    checks = guardrails(blocked_sql_keywords=[*default_policy().blocked_sql_keywords, "SLEEP"])
    assert checks.check_sql("SELECT SLEEP(10)") == "keyword SLEEP is not allowed"
    assert Guardrails.defaults().check_sql("SELECT SLEEP(10)") is None


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT password_hash FROM users",
        'SELECT "password_hash" FROM users',
        "SELECT u.`password_hash` AS h FROM users u",
        "SELECT COUNT(*) FROM users WHERE password_hash IS NULL",
    ],
)
def test_restricted_columns_block_sql(sql):
    assert Guardrails.defaults().check_sql(sql) == "column password_hash is restricted"


def test_restricted_column_names_inside_strings_or_longer_names_are_fine():
    checks = Guardrails.defaults()
    assert checks.check_sql("SELECT 'password_hash' AS label, password_hash_set FROM users") is None


def test_update_draft_keeps_the_where_rule_and_restricted_columns():
    checks = Guardrails.defaults()
    assert checks.check_update("UPDATE orders SET status = 'x' WHERE order_id = 1") is None
    assert checks.check_update("UPDATE orders SET status = 'x'") == (
        "an UPDATE without a WHERE clause would change every row"
    )
    assert checks.check_update("UPDATE users SET password_hash = NULL WHERE user_id = 1") == (
        "column password_hash is restricted"
    )


def test_redact_removes_restricted_columns_from_results(tmp_path):
    shop = tmp_path / "shop.db"
    with sqlite3.connect(shop) as connection:
        connection.executescript(
            "CREATE TABLE users (user_id INT, password_hash TEXT); INSERT INTO users VALUES (1, 'x');"
        )
    result = DatabaseRegistry({"ecommerce": f"sqlite:///{shop}"}).execute("ecommerce", "SELECT * FROM users")
    assert (result.columns, result.rows) == (["user_id"], [[1]])


# -- validation ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "changes,message",
    [
        ({"blocked_sql_keywords": ["DROP;"]}, "not a SQL keyword"),
        ({"restricted_columns": ["users.password hash"]}, "not a column name"),
        ({"question_rules": [custom_rule(), custom_rule()]}, "unique"),
        ({"max_rows": 0}, "greater than or equal to 1"),
    ],
)
def test_invalid_policies_are_rejected(changes, message):
    with pytest.raises(ValidationError, match=message):
        GuardrailPolicyInput(**default_policy().model_dump() | changes)


def test_invalid_regular_expression_is_rejected():
    with pytest.raises(ValidationError, match="invalid regular expression"):
        custom_rule(patterns=["(unclosed"])


def test_keywords_and_columns_are_normalised():
    data = GuardrailPolicyInput(
        question_rules=[], blocked_sql_keywords=[" into   outfile ", "INTO OUTFILE"], restricted_columns=["Users.SSN"]
    )
    assert (data.blocked_sql_keywords, data.restricted_columns) == (["INTO OUTFILE"], ["users.ssn"])


# -- storage ------------------------------------------------------------------------------


def test_first_read_saves_the_defaults(repo):
    stored = repo.get()
    assert [rule.id for rule in stored.question_rules] == [rule.id for rule in default_policy().question_rules]
    assert repo.client.retrieve("guard", ids=[POLICY_ID])  # persisted, not just returned


def test_save_round_trips_and_sets_locked_by_id(repo):
    rules = [*default_policy().question_rules, custom_rule(locked=True)]
    saved = repo.save(policy(question_rules=rules, max_rows=50))
    assert repo.get() == saved
    assert saved.max_rows == 50 and saved.updated_at > 0
    assert {rule.id: rule.locked for rule in saved.question_rules}["salaries"] is False


@pytest.mark.parametrize(
    "changes,message",
    [
        ({"question_rules": default_policy().question_rules[1:]}, "'delete-data' .* cannot be removed"),
        (
            {
                "question_rules": [
                    rule.model_copy(update={"enabled": rule.id != "permissions"})
                    for rule in default_policy().question_rules
                ]
            },
            "'permissions' .* cannot be disabled",
        ),
        ({"blocked_sql_keywords": ["SET"]}, "always blocked: INSERT, UPDATE, DELETE"),
    ],
)
def test_baseline_cannot_be_weakened(repo, changes, message):
    with pytest.raises(GuardrailPolicyError, match=message):
        repo.save(policy(**changes))


def test_locked_rule_message_can_change_but_patterns_cannot_be_removed(repo):
    rules = default_policy().question_rules
    reworded = [rules[0].model_copy(update={"message": "No deletes."}), *rules[1:]]
    assert repo.save(policy(question_rules=reworded)).question_rules[0].message == "No deletes."
    trimmed = [rules[0].model_copy(update={"patterns": rules[0].patterns[:1]}), *rules[1:]]
    with pytest.raises(GuardrailPolicyError, match="built-in patterns"):
        repo.save(policy(question_rules=trimmed))


def test_reset_restores_the_defaults(repo):
    repo.save(policy(restricted_columns=[]))
    assert repo.reset().restricted_columns == ["users.password_hash"]


# -- service ------------------------------------------------------------------------------


@pytest.fixture
def service(tmp_path):
    shop = tmp_path / "shop.db"
    with sqlite3.connect(shop) as connection:
        connection.executescript("CREATE TABLE t (n INTEGER); INSERT INTO t VALUES (1), (2), (3);")
    service = QueryMindService(
        Settings(qdrant_url=":memory:", collection="kb", source_dir=SQLS, cache_enabled=False),
        embedder=HashingEmbedder(),
        llm=ScriptedLLM(*[plan(("ecommerce", "SELECT n FROM t ORDER BY n"))] * 3),
        databases=DatabaseRegistry({"ecommerce": f"sqlite:///{shop}"}),
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # local Qdrant ignores payload indexes
        service.index()
    return service


def test_service_applies_a_saved_rule_without_a_restart(service):
    assert service.run("list n").status == "answered"
    assert "Never select, filter on, join on or otherwise use: users.password_hash" in service.llm.prompts[0]
    service.guardrail_store.save(policy(question_rules=[*default_policy().question_rules, custom_rule()]))
    result = service.run("list salaries")
    assert result.status == "blocked"
    assert result.intent.blocked_message == "Salaries are private."


def test_service_row_limit_comes_from_the_policy(service):
    service.guardrail_store.save(policy(max_rows=2))
    assert service.run("list n").result.rows == [[1], [2]]
    assert service.run("list n", max_rows=10).result.rows == [[1], [2]]  # cannot raise the limit
    assert service.run("list n", max_rows=1).result.rows == [[1]]


def test_service_falls_back_to_the_built_in_policy(service, monkeypatch):
    def unavailable(self):
        raise ConnectionError("qdrant down")

    monkeypatch.setattr(GuardrailRepository, "get", unavailable)
    service._guardrails = None
    checks = service.guardrails()
    assert checks.refuse("delete all orders").id == "delete-data"
    assert checks.policy.updated_at == 0
