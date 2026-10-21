import os
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config_file import read_env_file, update_env_file
from app.dependencies import get_settings
from app.main import app
from app.routers import admin

MODEL = "/admin/model-config"
OKTA = "/admin/okta"
WATCHED = [*admin.MODEL_KEYS, "GOOGLE_API_KEY", *admin.OKTA_KEYS.values(), "OKTA_CLIENT_SECRET",
           "QUERYMIND_OKTA_ALLOWED_HOSTS"]


@pytest.fixture
def files(tmp_path, monkeypatch):
    """Temp config files, no real .env loading, and os.environ restored afterwards."""
    saved = dict(os.environ)
    for key in WATCHED:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr("app.dependencies.load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr("querymind.config.load_dotenv", lambda *a, **k: None)
    agent_env = tmp_path / "agent.env"
    agent_env.write_text("# Agent settings\nGEMINI_API_KEY=old-gemini-key-1234\nLLM_MODEL=gemini-2.5-flash\nQDRANT_URL=http://q:6333\n")
    paths = admin.ConfigFiles(agent=agent_env, api=tmp_path / "api.env")
    app.dependency_overrides[admin.get_config_files] = lambda: paths
    os.environ["GEMINI_API_KEY"] = "old-gemini-key-1234"
    os.environ["LLM_MODEL"] = "gemini-2.5-flash"
    get_settings.cache_clear()
    yield paths
    app.dependency_overrides.pop(admin.get_config_files, None)
    os.environ.clear()
    os.environ.update(saved)
    get_settings.cache_clear()


@pytest.fixture
def api(files):
    with TestClient(app) as client:
        yield client


def model_update(**overrides):
    return {"llm_provider": "openai", "openai_model": "gpt-6-sol", "openai_reasoning_effort": "low",
            "openai_api_key": "sk-test-abcdefgh9876", "gemini_model": "", "embedding_provider": "gemini",
            **overrides}


def test_read_model_config_masks_keys(api):
    body = api.get(MODEL).json()
    assert body["llm_provider"] == "gemini"
    assert body["active_model"] == "gemini-2.5-flash"
    assert body["gemini"]["api_key"] == "…1234"
    assert body["openai"]["api_key"] is None
    assert any("LLM_MODEL=gemini-2.5-flash overrides" in w for w in body["warnings"])
    assert "old-gemini-key" not in str(body)


def test_update_model_config_writes_file_and_applies(api, files):
    body = api.put(MODEL, json=model_update()).json()

    assert body["llm_provider"] == "openai"
    assert body["active_model"] == "gpt-6-sol"
    assert body["openai"] == {"model": "gpt-6-sol", "default_model": "gpt-6-luna", "reasoning_effort": "low",
                              "api_key": "…9876"}
    assert body["gemini"]["api_key"] == "…1234"  # omitted -> kept

    saved = read_env_file(files.agent)
    assert saved["LLM_PROVIDER"] == "openai"
    assert saved["OPENAI_MODEL"] == "gpt-6-sol"
    assert saved["OPENAI_API_KEY"] == "sk-test-abcdefgh9876"
    assert "LLM_MODEL" not in saved  # the global override is removed
    assert saved["QDRANT_URL"] == "http://q:6333"  # untouched
    assert files.agent.read_text().startswith("# Agent settings\n")
    assert get_settings().resolved_llm_model == "gpt-6-sol"  # applied without a restart


def test_clearing_a_key_and_embedding_warning(api, files):
    body = api.put(MODEL, json=model_update(gemini_api_key="", embedding_dimensions=1536)).json()
    assert body["gemini"]["api_key"] is None
    assert "GEMINI_API_KEY" not in read_env_file(files.agent)
    assert any("re-index" in w for w in body["warnings"])


@pytest.mark.parametrize(
    "change",
    [
        {"openai_model": "gemini-2.5-flash"},
        {"gemini_model": "gpt-6-luna"},
        {"openai_reasoning_effort": "extreme"},
        {"openai_api_key": "short"},
        {"openai_api_key": "has spaces in it"},
        {"llm_model": "x"},
        {"embedding_dimensions": 1000},
    ],
)
def test_update_model_config_validation(api, change):
    assert api.put(MODEL, json=model_update(**change)).status_code == 422


def test_model_connection_test_reports_missing_key(api):
    api.put(MODEL, json=model_update(openai_api_key=""))
    body = api.post(f"{MODEL}/test").json()
    assert body == {"ok": False, "message": "No API key is configured for OpenAI model gpt-6-sol."}


def test_model_connection_test_success(api, monkeypatch):
    calls = []
    fake = SimpleNamespace(client=SimpleNamespace(models=SimpleNamespace(retrieve=calls.append)))
    monkeypatch.setattr(admin, "create_llm", lambda provider, model: fake)
    api.put(MODEL, json=model_update())
    assert api.post(f"{MODEL}/test").json() == {"ok": True, "message": "Connected. OpenAI model gpt-6-sol is available."}
    assert calls == ["gpt-6-sol"]


def okta_update(**overrides):
    return {"enabled": True, "org_url": "https://acme.okta.com/", "authorization_server_id": "default",
            "client_id": "0oa1abc", "client_secret": "okta-secret-5678", "admin_group": "QueryMind Admins",
            "redirect_uri": "http://localhost:8080/login/callback", **overrides}


def test_okta_round_trip(api, files):
    assert api.get(OKTA).json()["enabled"] is False

    body = api.put(OKTA, json=okta_update()).json()
    assert body["org_url"] == "https://acme.okta.com"
    assert body["issuer"] == "https://acme.okta.com/oauth2/default"
    assert body["client_secret"] == "…5678"
    assert body["scopes"] == "openid profile email groups"
    assert any("not enforced" in w for w in body["warnings"])

    saved = read_env_file(files.api)
    assert saved["OKTA_ENABLED"] == "true"
    assert saved["OKTA_ADMIN_GROUP"] == "QueryMind Admins"
    assert saved["OKTA_CLIENT_SECRET"] == "okta-secret-5678"
    assert oct(files.api.stat().st_mode & 0o777) == "0o600"

    # org authorization server, secret kept when omitted
    body = api.put(OKTA, json=okta_update(authorization_server_id="", client_secret=None)).json()
    assert body["issuer"] == "https://acme.okta.com"
    assert body["client_secret"] == "…5678"


@pytest.mark.parametrize(
    "change",
    [
        {"org_url": "http://acme.okta.com"},
        {"org_url": "https://acme.okta.com/path"},
        {"client_id": ""},  # required when enabled
        {"scopes": "profile email"},
        {"authorization_server_id": "bad id"},
        {"redirect_uri": "javascript:alert(1)"},
    ],
)
def test_okta_validation(api, change):
    assert api.put(OKTA, json=okta_update(**change)).status_code == 422


def test_okta_rejects_non_okta_hosts(api, monkeypatch):
    response = api.post(f"{OKTA}/test", json={"org_url": "https://169.254.169.254"})
    assert response.status_code == 422
    assert "not an Okta domain" in response.json()["detail"]

    monkeypatch.setenv("QUERYMIND_OKTA_ALLOWED_HOSTS", "login.example.com")
    monkeypatch.setattr(admin.httpx, "get", lambda url, **kw: httpx.Response(404))
    assert api.post(f"{OKTA}/test", json={"org_url": "https://login.example.com"}).status_code == 200


def test_okta_connection_test(api, monkeypatch):
    seen = {}

    def fake_get(url, **kwargs):
        seen["url"], seen["redirects"] = url, kwargs["follow_redirects"]
        return httpx.Response(200, json={
            "issuer": "https://acme.okta.com/oauth2/default",
            "authorization_endpoint": "https://acme.okta.com/oauth2/default/v1/authorize",
            "token_endpoint": "https://acme.okta.com/oauth2/default/v1/token",
            "jwks_uri": "https://acme.okta.com/oauth2/default/v1/keys",
            "scopes_supported": ["openid", "profile", "groups"],
        })

    monkeypatch.setattr(admin.httpx, "get", fake_get)
    body = api.post(f"{OKTA}/test", json={"org_url": "https://acme.okta.com"}).json()
    assert body["ok"] is True
    assert body["token_endpoint"].endswith("/v1/token")
    assert seen == {"url": "https://acme.okta.com/oauth2/default/.well-known/openid-configuration", "redirects": False}

    monkeypatch.setattr(admin.httpx, "get", lambda url, **kw: httpx.Response(200, json={"issuer": "https://evil"}))
    body = api.post(f"{OKTA}/test", json={"org_url": "https://acme.okta.com"}).json()
    assert body["ok"] is False and "Unexpected issuer" in body["message"]


def test_update_env_file_quotes_and_removes(tmp_path):
    path = tmp_path / ".env"
    path.write_text("A=1\n# note\nB=2\nB=3\n")
    update_env_file(path, {"B": "two words # not a comment", "A": None, "C": 'say "hi"'})
    assert path.read_text() == '# note\nB="two words # not a comment"\n\nC="say \\"hi\\""\n'
    assert read_env_file(path) == {"B": "two words # not a comment", "C": 'say "hi"'}
    with pytest.raises(ValueError):
        update_env_file(path, {"D": "line\nbreak"})
    for key in ("A", "B", "C"):
        os.environ.pop(key, None)
