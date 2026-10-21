"""Admin settings: the language/embedding model and Okta, saved to the .env config files.

Model settings live in querymind-agentic/.env (the keys the agent reads), Okta settings
in querymind-api/.env. Saving applies them immediately; no restart is needed.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated
from urllib.parse import urlparse

import httpx
import openai
from fastapi import APIRouter, Depends, HTTPException, status
from google.genai import errors as genai_errors
from querymind.config import PROJECT_DIR as AGENT_DIR
from querymind.exceptions import MissingApiKeyError
from querymind.knowledge.embeddings import DEFAULT_MODELS as EMBEDDING_DEFAULTS
from querymind.llm import DEFAULT_LLM_MODELS, REASONING_EFFORTS, create_llm
from querymind.service import QueryMindService

from app.admin_schemas import (
    ConnectionTest,
    EmbeddingConfig,
    ModelConfig,
    ModelConfigUpdate,
    OktaConfig,
    OktaConfigUpdate,
    OktaTestRequest,
    OktaTestResult,
    OpenAIConfig,
    ProviderConfig,
)
from app.config_file import SHELL_ENV_KEYS, secret_hint, update_env_file
from app.dependencies import API_DIR, get_service, get_settings
from app.schemas import CacheStatsOut

router = APIRouter(prefix="/admin", tags=["admin"])

# Okta-hosted domains the connection test may call. Add a custom Okta domain with
# QUERYMIND_OKTA_ALLOWED_HOSTS=login.example.com (comma-separated).
OKTA_DOMAINS = (
    "okta.com",
    "oktapreview.com",
    "okta-emea.com",
    "okta-gov.com",
    "okta.mil",
)


@dataclass(frozen=True)
class ConfigFiles:
    agent: Path  # model settings
    api: Path  # Okta settings


def get_config_files() -> ConfigFiles:
    return ConfigFiles(agent=AGENT_DIR / ".env", api=API_DIR / ".env")


Files = Annotated[ConfigFiles, Depends(get_config_files)]
Service = Annotated[QueryMindService, Depends(get_service)]


def _env(key: str) -> str:
    return os.getenv(key) or ""


def _shell_warning(keys: list[str]) -> list[str]:
    fixed = [key for key in keys if key in SHELL_ENV_KEYS]
    if not fixed:
        return []
    return [f"{', '.join(fixed)} also set in the server's environment; a restart re-applies those values."]


# -- model configuration -------------------------------------------------------------------

MODEL_KEYS = [
    "LLM_PROVIDER",
    "LLM_MODEL",
    "OPENAI_MODEL",
    "GEMINI_MODEL",
    "LLM_REASONING_EFFORT",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "EMBEDDING_PROVIDER",
    "EMBEDDING_MODEL",
    "EMBEDDING_DIM",
]


def _model_config(files: ConfigFiles, warnings: list[str] | None = None) -> ModelConfig:
    settings = get_settings()  # also loads the .env files on first use
    notes = list(warnings or [])
    if _env("LLM_MODEL"):
        notes.append(f"LLM_MODEL={_env('LLM_MODEL')} overrides the per-provider models until you save here.")
    notes += _shell_warning(MODEL_KEYS)
    dimensions = _env("EMBEDDING_DIM")
    return ModelConfig(
        llm_provider=settings.llm_provider,  # type: ignore[arg-type]
        active_model=settings.resolved_llm_model,
        openai=OpenAIConfig(
            model=_env("OPENAI_MODEL"),
            default_model=DEFAULT_LLM_MODELS["openai"],
            reasoning_effort=settings.llm_reasoning_effort,  # type: ignore[arg-type]
            api_key=secret_hint(_env("OPENAI_API_KEY")),
        ),
        gemini=ProviderConfig(
            model=_env("GEMINI_MODEL"),
            default_model=DEFAULT_LLM_MODELS["gemini"],
            api_key=secret_hint(_env("GEMINI_API_KEY") or _env("GOOGLE_API_KEY")),
        ),
        embedding=EmbeddingConfig(
            provider=settings.embedding_provider,  # type: ignore[arg-type]
            model=settings.embedding_model or "",
            default_models=dict(EMBEDDING_DEFAULTS),
            dimensions=int(dimensions) if dimensions.isdigit() else None,
        ),
        reasoning_efforts=list(REASONING_EFFORTS),
        config_file=str(files.agent),
        warnings=notes,
    )


@router.get("/model-config", response_model=ModelConfig, summary="Read the model configuration")
def read_model_config(files: Files) -> ModelConfig:
    """The language and embedding model settings in use. API keys are shown only as `…abcd`."""
    return _model_config(files)


@router.put(
    "/model-config",
    response_model=ModelConfig,
    summary="Update the model configuration",
)
def update_model_config(body: ModelConfigUpdate, files: Files) -> ModelConfig:
    """Save to querymind-agentic/.env and apply immediately (new requests use the new model)."""
    before = get_settings()
    changes: dict[str, str | None] = {
        "LLM_PROVIDER": body.llm_provider,
        "LLM_MODEL": None,  # per-provider models below replace the global override
        "OPENAI_MODEL": body.openai_model or None,
        "GEMINI_MODEL": body.gemini_model or None,
        "LLM_REASONING_EFFORT": body.openai_reasoning_effort,
        "EMBEDDING_PROVIDER": body.embedding_provider,
        "EMBEDDING_MODEL": body.embedding_model or None,
        "EMBEDDING_DIM": str(body.embedding_dimensions) if body.embedding_dimensions else None,
    }
    for key, value in (
        ("OPENAI_API_KEY", body.openai_api_key),
        ("GEMINI_API_KEY", body.gemini_api_key),
    ):
        if value is not None:  # None keeps the current key
            changes[key] = value or None
    update_env_file(files.agent, changes)
    _reload_service()

    after = get_settings()
    warnings = []
    if (
        before.embedding_provider,
        before.embedding_model,
        before.embedding_dimensions,
    ) != (after.embedding_provider, after.embedding_model, after.embedding_dimensions):
        warnings.append("The embedding model changed: re-index with POST /index and recreate=true before asking.")
    return _model_config(files, warnings)


@router.post(
    "/model-config/test",
    response_model=ConnectionTest,
    summary="Test the language model",
)
def test_model_config() -> ConnectionTest:
    """Check that the saved API key works and the configured model exists. Uses no tokens."""
    settings = get_settings()
    provider, model = settings.llm_provider, settings.resolved_llm_model
    label = f"{'OpenAI' if provider == 'openai' else 'Gemini'} model {model}"
    try:
        llm = create_llm(provider, model)
        if provider == "openai":
            llm.client.models.retrieve(model)
        else:
            llm.client.models.get(model=model)
    except MissingApiKeyError:
        return ConnectionTest(ok=False, message=f"No API key is configured for {label}.")
    except ValueError as error:
        return ConnectionTest(ok=False, message=str(error))
    except openai.APIError as error:
        code = getattr(error, "status_code", None) or type(error).__name__
        return ConnectionTest(ok=False, message=f"OpenAI rejected the request for {label} ({code}).")
    except genai_errors.APIError as error:
        return ConnectionTest(ok=False, message=f"Gemini rejected the request for {label} ({error.code}).")
    return ConnectionTest(ok=True, message=f"Connected. {label} is available.")


@router.get("/cache", response_model=CacheStatsOut, summary="Semantic cache statistics")
def read_cache(service: Service) -> CacheStatsOut:
    """How many answers are cached, and the similarity threshold and lifetime that apply."""
    return CacheStatsOut.model_validate(service.cache_stats())


@router.delete("/cache", response_model=CacheStatsOut, summary="Clear the semantic cache")
def clear_cache(service: Service) -> CacheStatsOut:
    """Drop every cached answer, e.g. after the data changed. Re-indexing also clears it."""
    service.clear_cache()
    return CacheStatsOut.model_validate(service.cache_stats())


def _reload_service() -> None:
    get_settings.cache_clear()
    get_service.cache_clear()


# -- Okta ----------------------------------------------------------------------------------

OKTA_KEYS = {
    "enabled": "OKTA_ENABLED",
    "org_url": "OKTA_ORG_URL",
    "authorization_server_id": "OKTA_AUTH_SERVER_ID",
    "client_id": "OKTA_CLIENT_ID",
    "scopes": "OKTA_SCOPES",
    "groups_claim": "OKTA_GROUPS_CLAIM",
    "admin_group": "OKTA_ADMIN_GROUP",
    "user_group": "OKTA_USER_GROUP",
    "redirect_uri": "OKTA_REDIRECT_URI",
    "post_logout_redirect_uri": "OKTA_POST_LOGOUT_REDIRECT_URI",
}
OKTA_DEFAULTS = OktaConfigUpdate()


def issuer_url(org_url: str, server_id: str) -> str | None:
    if not org_url:
        return None
    return f"{org_url}/oauth2/{server_id}" if server_id else org_url


def _okta_config(files: ConfigFiles) -> OktaConfig:
    get_settings()  # loads querymind-api/.env on first use
    values = {
        field: _env(key) if key in os.environ else getattr(OKTA_DEFAULTS, field)
        for field, key in OKTA_KEYS.items()
        if field != "enabled"
    }
    enabled = _env("OKTA_ENABLED").lower() == "true"
    warnings = ["Okta sign-in is configured here but not enforced yet; QueryMind is still open without login."]
    warnings += _shell_warning([*OKTA_KEYS.values(), "OKTA_CLIENT_SECRET"])
    return OktaConfig(
        enabled=enabled,
        issuer=issuer_url(values["org_url"], values["authorization_server_id"]),
        client_secret=secret_hint(_env("OKTA_CLIENT_SECRET")),
        config_file=str(files.api),
        warnings=warnings,
        **values,
    )


@router.get("/okta", response_model=OktaConfig, summary="Read the Okta configuration")
def read_okta(files: Files) -> OktaConfig:
    """Okta OIDC settings. The client secret is shown only as `…abcd`."""
    return _okta_config(files)


@router.put("/okta", response_model=OktaConfig, summary="Update the Okta configuration")
def update_okta(body: OktaConfigUpdate, files: Files) -> OktaConfig:
    """Save the Okta settings to querymind-api/.env."""
    if body.org_url:
        _check_okta_host(body.org_url)
    changes: dict[str, str | None] = {
        key: (("true" if body.enabled else "false") if field == "enabled" else (getattr(body, field) or None))
        for field, key in OKTA_KEYS.items()
    }
    # An empty server id is meaningful (the org authorization server), so it is stored, not removed.
    changes["OKTA_AUTH_SERVER_ID"] = body.authorization_server_id
    if body.client_secret is not None:
        changes["OKTA_CLIENT_SECRET"] = body.client_secret or None
    update_env_file(files.api, changes)
    return _okta_config(files)


@router.post("/okta/test", response_model=OktaTestResult, summary="Test the Okta connection")
def test_okta(body: OktaTestRequest) -> OktaTestResult:
    """Fetch the authorization server's OpenID discovery document to check the org URL and server id."""
    _check_okta_host(body.org_url)
    issuer = issuer_url(body.org_url, body.authorization_server_id)
    url = f"{issuer}/.well-known/openid-configuration"
    try:
        response = httpx.get(
            url,
            timeout=5.0,
            follow_redirects=False,
            headers={"Accept": "application/json"},
        )
    except httpx.HTTPError as error:
        return OktaTestResult(
            ok=False,
            message=f"Could not reach Okta at {body.org_url} ({type(error).__name__}).",
        )
    if response.status_code == 404:
        return OktaTestResult(
            ok=False,
            message="Okta answered, but the authorization server was not found.",
        )
    if response.status_code != 200:
        return OktaTestResult(ok=False, message=f"Okta answered with HTTP {response.status_code}.")
    try:
        document = response.json()
    except ValueError:
        return OktaTestResult(ok=False, message="Okta did not return an OpenID configuration document.")
    if document.get("issuer") != issuer:
        return OktaTestResult(
            ok=False,
            message=f"Unexpected issuer {document.get('issuer')!r}; expected {issuer}.",
        )
    return OktaTestResult(
        ok=True,
        message=f"Connected to the authorization server at {issuer}.",
        issuer=document.get("issuer"),
        authorization_endpoint=document.get("authorization_endpoint"),
        token_endpoint=document.get("token_endpoint"),
        jwks_uri=document.get("jwks_uri"),
        scopes_supported=document.get("scopes_supported") or [],
    )


def _check_okta_host(org_url: str) -> None:
    """Only Okta domains (plus configured custom domains) may be called from the server."""
    host = (urlparse(org_url).hostname or "").lower()
    extra = {h.strip().lower() for h in _env("QUERYMIND_OKTA_ALLOWED_HOSTS").split(",") if h.strip()}
    if host in extra or any(host == d or host.endswith("." + d) for d in OKTA_DOMAINS):
        return
    raise HTTPException(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        f"{host} is not an Okta domain. For a custom Okta domain, add it to QUERYMIND_OKTA_ALLOWED_HOSTS "
        "on the server.",
    )
