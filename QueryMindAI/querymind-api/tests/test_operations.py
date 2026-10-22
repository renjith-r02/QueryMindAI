import warnings

import pytest
from querymind.exceptions import MissingApiKeyError

SOURCES = ["ecommerce_mysql_schema.sql", "few_shot_examples.json", "returns_postgres_schema.sql"]


def test_list_sources(client):
    response = client.get("/sources")
    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == SOURCES


def test_index_dry_run_with_chunks(client):
    response = client.post("/index", json={"files": [SOURCES[0]], "dry_run": True, "include_chunks": True})
    body = response.json()
    assert response.status_code == 200
    assert body["dry_run"] is True and body["indexed"] == 0
    [source] = body["sources"]
    assert source["database"] == "ecommerce"
    assert source["chunk_count"] == len(source["chunks"]) == sum(source["counts"].values())


def test_index_writes_chunks(client):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        body = client.post("/index", json={}).json()
    assert body["indexed"] == sum(source["chunk_count"] for source in body["sources"])
    assert body["embedding"] == "gemini:hashing-test"
    assert "chunks" not in body["sources"][0] or body["sources"][0]["chunks"] is None


def test_index_rejects_paths_outside_source_dir(client):
    response = client.post("/index", json={"files": ["../.env"]})
    assert response.status_code == 404
    assert "Unknown source file" in response.json()["detail"]


def test_search(client):
    response = client.get(
        "/search",
        params={"q": "refund amount paid", "limit": 3, "database": "returns_db"},
    )
    hits = response.json()
    assert response.status_code == 200
    assert len(hits) == 3
    assert all(hit["database"] == "returns_db" and "content" not in hit for hit in hits)

    with_content = client.get("/search", params={"q": "refund", "limit": 1, "include_content": True}).json()
    assert with_content[0]["content"]


def test_ask(client):
    response = client.post("/ask", json={"question": "list n"})
    body = response.json()
    assert response.status_code == 200
    assert body["model"] == "fake-llm"
    assert body["answer"]["queries"][0]["sql"] == "SELECT n FROM t ORDER BY n"
    assert body["context"][0]["id"] == "S1"


def test_run(client):
    response = client.post("/run", json={"question": "list n", "max_rows": 2})
    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "answered"
    assert body["final"]["answer"] == "final"
    assert body["result"]["rows"] == [[1], [2]]
    assert body["result"]["truncated"] is True
    assert len(body["attempts"]) == 1


def test_run_caps_max_rows(client):
    response = client.post("/run", json={"question": "q", "max_rows": 101})
    assert response.status_code == 422


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/ask", {"question": "q", "llm_model": "gemini-pro"}),
        ("/run", {"question": "q", "model": "other"}),
        ("/ask", {"question": "q", "api_key": "secret"}),
        ("/index", {"paths": ["/etc/passwd"]}),
    ],
)
def test_callers_cannot_choose_llm_or_settings(client, path, payload):
    response = client.post(path, json=payload)
    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "extra_forbidden"


def test_missing_api_key_is_503(client, service, monkeypatch):
    def fail(*args, **kwargs):
        raise MissingApiKeyError("no key")

    monkeypatch.setattr(service, "ask", fail)
    response = client.post("/ask", json={"question": "q"})
    assert response.status_code == 503
    assert "not configured" in response.json()["detail"]


def test_server_defaults_to_gemini(monkeypatch):
    from app.dependencies import get_settings

    for name in ("LLM_PROVIDER", "LLM_MODEL", "GEMINI_MODEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("app.dependencies.load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setattr("querymind.config.load_dotenv", lambda *args, **kwargs: None)
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert (settings.llm_provider, settings.resolved_llm_model) == (
            "gemini",
            "gemini-3.8-flash",
        )
    finally:
        get_settings.cache_clear()


def test_run_returns_the_intent(client):
    body = client.post("/run", json={"question": "list n"}).json()
    assert body["status"] == "answered"
    assert body["intent"]["query_type"] == "SELECT_SIMPLE"
    assert body["intent"]["source"] == "model"


@pytest.mark.parametrize(
    "question",
    ["delete all orders", "drop table orders", "insert into orders values (1)"],
)
def test_run_refuses_prohibited_requests(client, service, question):
    calls_before = service.llm.calls
    body = client.post("/run", json={"question": question}).json()
    assert body["status"] == "blocked"
    assert body["intent"]["query_type"] == "UNSUPPORTED"
    assert body["intent"]["blocked_message"]
    assert body["attempts"][0]["plan"]["queries"] == [] and body["result"] is None
    assert service.llm.calls == calls_before  # refused without calling the model


def test_run_drafts_update_without_executing(client, service):
    service.llm.query_type = "UPDATE"
    body = client.post("/run", json={"question": "set n to zero where it is 3"}).json()
    assert body["status"] == "generated"
    assert body["attempts"][0]["plan"]["queries"][0]["sql"] == service.llm.UPDATE_SQL
    assert body["attempts"][0]["results"] == [] and body["result"] is None
    rows = service.databases.execute("ecommerce", "SELECT n FROM t ORDER BY n").rows
    assert rows == [[1], [2], [3]]  # untouched


def test_ask_reports_status_and_intent(client, service):
    body = client.post("/ask", json={"question": "please delete every row"}).json()
    assert body["status"] == "blocked" and body["answer"]["queries"] == []
    service.llm.query_type = "UPDATE"
    body = client.post("/ask", json={"question": "set n to zero"}).json()
    assert body["status"] == "generated" and body["intent"]["query_type"] == "UPDATE"


def test_repeat_question_is_served_from_cache(client, service):
    first = client.post("/run", json={"question": "list n"}).json()
    assert first["cache"] is None
    calls = service.llm.calls

    second = client.post("/run", json={"question": "List n?"}).json()
    assert service.llm.calls == calls  # no model calls
    assert second["cache"]["hit"] is True and second["cache"]["question"] == "list n"
    assert second["result"]["rows"] == first["result"]["rows"]

    fresh = client.post("/run", json={"question": "list n", "use_cache": False}).json()
    assert fresh["cache"] is None and service.llm.calls > calls


def test_cache_admin_stats_and_clear(client):
    client.post("/run", json={"question": "list n"})
    stats = client.get("/admin/cache").json()
    assert stats["enabled"] is True and stats["entries"] == 1 and stats["threshold"] == 0.95
    assert client.delete("/admin/cache").json()["entries"] == 0
    assert client.post("/run", json={"question": "list n"}).json()["cache"] is None
