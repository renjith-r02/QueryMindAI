from querymind.guardrails import REQUIRED_SQL_KEYWORDS

SALARIES = {
    "id": "salaries",
    "label": "Salaries",
    "message": "Salaries are private.",
    "patterns": [r"\bsalar"],
}


def editable(policy: dict) -> dict:
    """The fields PUT /guardrails accepts."""
    return {
        key: policy[key]
        for key in (
            "question_rules",
            "blocked_sql_keywords",
            "restricted_columns",
            "max_rows",
        )
    }


def test_get_returns_the_seeded_policy_and_baseline(client):
    policy = client.get("/guardrails").json()
    assert policy["max_rows"] == 100  # QUERYMIND_MAX_ROWS (settings.max_rows) seeds the limit
    assert policy["required_sql_keywords"] == list(REQUIRED_SQL_KEYWORDS)
    assert policy["polite_token"] == "{polite}"
    locked = {rule["id"] for rule in policy["question_rules"] if rule["locked"]}
    assert locked == set(policy["locked_rule_ids"]) == {"delete-data", "change-structure", "insert-rows", "permissions"}
    assert policy["restricted_columns"] == ["users.password_hash"]


def test_put_saves_and_applies_to_queries(client):
    policy = editable(client.get("/guardrails").json())
    policy["question_rules"].append(SALARIES)
    saved = client.put("/guardrails", json=policy | {"max_rows": 2})
    assert saved.status_code == 200
    assert saved.json()["updated_at"] > 0
    assert client.get("/guardrails").json()["question_rules"][-1]["id"] == "salaries"

    blocked = client.post("/run", json={"question": "average salary"}).json()
    assert blocked["status"] == "blocked"
    assert blocked["intent"]["blocked_message"] == "Salaries are private."

    answered = client.post("/run", json={"question": "list n", "use_cache": False}).json()
    assert answered["result"]["rows"] == [[1], [2]]
    too_many = client.post("/run", json={"question": "list n", "max_rows": 3})
    assert too_many.status_code == 422 and "cannot exceed 2" in too_many.text


def test_put_rejects_weakening_the_baseline(client):
    policy = editable(client.get("/guardrails").json())
    policy["question_rules"] = [rule | {"enabled": rule["id"] != "delete-data"} for rule in policy["question_rules"]]
    response = client.put("/guardrails", json=policy)
    assert response.status_code == 422
    assert "'delete-data' (Deleting data) cannot be disabled" in response.json()["detail"]


def test_put_rejects_invalid_patterns_and_unknown_fields(client):
    policy = editable(client.get("/guardrails").json())
    bad_rule = client.put(
        "/guardrails",
        json=policy | {"question_rules": [SALARIES | {"patterns": ["("]}]},
    )
    assert bad_rule.status_code == 422 and "invalid regular expression" in bad_rule.text
    assert client.put("/guardrails", json=policy | {"updated_at": 1}).status_code == 422


def test_reset_restores_the_defaults(client):
    policy = editable(client.get("/guardrails").json())
    client.put("/guardrails", json=policy | {"restricted_columns": []})
    assert client.post("/guardrails/reset").json()["restricted_columns"] == ["users.password_hash"]


def test_check_uses_the_saved_or_a_draft_policy(client):
    checked = client.post(
        "/guardrails/check",
        json={
            "question": "please delete old carts",
            "sql": "SELECT password_hash FROM users",
        },
    ).json()
    assert checked["question"] == {
        "allowed": False,
        "rule_id": "delete-data",
        "message": checked["question"]["message"],
    }
    assert checked["sql"] == {
        "allowed": False,
        "reason": "column password_hash is restricted",
    }

    draft = editable(client.get("/guardrails").json()) | {"restricted_columns": []}
    allowed = client.post(
        "/guardrails/check",
        json={"sql": "SELECT password_hash FROM users", "policy": draft},
    )
    assert allowed.json() == {
        "question": None,
        "sql": {"allowed": True, "reason": None},
    }
    assert client.post("/guardrails/check", json={}).status_code == 422
