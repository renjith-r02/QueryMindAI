from querymind.datasources import SECTION_KEYS

NEW = {
    "name": "events",
    "type": "cassandra",
    "connection": {"contact_points": "10.0.0.1", "port": "9042", "keyspace": "shop"},
    "sections": {
        "purpose": "Click events.",
        "join_paths": "Query by user_id partition.",
    },
}


def test_seeded_from_the_schema_files(client):
    sources = client.get("/datasources").json()
    assert [(s["name"], s["type"]) for s in sources] == [
        ("ecommerce", "mysql"),
        ("returns_db", "postgresql"),
    ]
    ecommerce = sources[0]
    assert set(ecommerce["sections"]) == set(SECTION_KEYS)
    assert ecommerce["connection"]["database"] == "ecommerce"
    assert {"id", "created_at", "updated_at", "enabled"} <= set(ecommerce)


def test_crud_round_trip(client):
    created = client.post("/datasources", json=NEW)
    assert created.status_code == 201
    source = created.json()
    assert source["name"] == "events" and source["enabled"] is True

    assert client.get(f"/datasources/{source['id']}").json() == source

    updated = client.put(
        f"/datasources/{source['id']}",
        json=NEW | {"name": "clickstream", "enabled": False},
    ).json()
    assert updated["name"] == "clickstream" and updated["enabled"] is False
    assert updated["created_at"] == source["created_at"] and updated["updated_at"] > source["updated_at"]
    assert "clickstream" in [s["name"] for s in client.get("/datasources").json()]

    assert client.delete(f"/datasources/{source['id']}").status_code == 204
    assert client.get(f"/datasources/{source['id']}").status_code == 404
    assert client.delete(f"/datasources/{source['id']}").status_code == 404


def test_duplicate_names_conflict(client):
    response = client.post("/datasources", json=NEW | {"name": "ECOMMERCE"})
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


def test_validation(client):
    bad = [
        NEW | {"connection": {"password": "secret"}},  # no secrets, and not a cassandra field
        NEW | {"type": "oracle"},
        NEW | {"sections": {"notes": "x"}},
        NEW | {"id": "chosen-by-client"},
        NEW | {"name": ""},
    ]
    for body in bad:
        assert client.post("/datasources", json=body).status_code == 422, body


def test_unknown_ids(client):
    assert client.get("/datasources/not-a-uuid").status_code == 404
    assert client.put("/datasources/00000000-0000-0000-0000-000000000000", json=NEW).status_code == 404


def test_env_only_databases_are_listed_and_can_be_saved(client, monkeypatch):
    monkeypatch.setenv(
        "QUERYMIND_DB_ANALYTICS",
        "postgresql+psycopg://bi:secret@bi.internal:5433/analytics",
    )
    listed = {s["name"]: s for s in client.get("/datasources").json()}
    entry = listed["analytics"]
    assert entry["origin"] == "env" and entry["id"] == "env:analytics"
    assert entry["connection"] == {
        "host": "bi.internal",
        "port": "5433",
        "database": "analytics",
        "username": "bi",
    }
    assert "secret" not in str(listed)
    assert listed["ecommerce"]["origin"] == "qdrant"

    assert client.get("/datasources/env:analytics").json() == entry
    assert client.delete("/datasources/env:analytics").status_code == 409

    body = {k: entry[k] for k in ("name", "type", "enabled", "connection", "sections")}
    saved = client.put("/datasources/env:analytics", json=body | {"sections": {"purpose": "BI marts."}}).json()
    assert saved["origin"] == "qdrant" and not saved["id"].startswith("env:")
    listed = [s for s in client.get("/datasources").json() if s["name"] == "analytics"]
    assert len(listed) == 1 and listed[0]["origin"] == "qdrant"


def test_unknown_env_ids(client):
    assert client.get("/datasources/env:nothing").status_code == 404
    assert client.delete("/datasources/env:nothing").status_code == 404
