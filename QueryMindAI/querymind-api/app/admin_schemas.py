"""Bodies for the admin endpoints (model configuration and Okta setup).

Secrets are write-only: requests may set or clear them, responses only say whether one
is configured (`"…abcd"`), never the value.
"""

import re
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from querymind.llm import REASONING_EFFORTS

ReasoningEffort = Literal["none", "low", "medium", "high", "xhigh", "max"]
assert set(ReasoningEffort.__args__) == set(REASONING_EFFORTS)  # type: ignore[attr-defined]

_MODEL_NAME = re.compile(r"^[A-Za-z0-9._:/-]{1,100}$")
_SECRET = re.compile(r"^\S{8,512}$")

SECRET_HELP = "Omit or null to keep the current value, empty string to remove it, or the new value"


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _check_secret(value: str | None) -> str | None:
    if value is None or value == "":
        return value
    if not _SECRET.match(value):
        raise ValueError("must be 8 to 512 characters without spaces")
    return value


def _check_model(value: str) -> str:
    value = value.strip()
    if value and not _MODEL_NAME.match(value):
        raise ValueError("use letters, digits and . _ : / - only")
    return value


def _https_origin(value: str) -> str:
    value = value.strip().rstrip("/")
    if not value:
        return value
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.path or parsed.query or parsed.port:
        raise ValueError("must be an https origin such as https://acme.okta.com")
    return value


def _server_id(value: str) -> str:
    value = value.strip()
    if value and not re.fullmatch(r"[A-Za-z0-9]{1,64}", value):
        raise ValueError("letters and digits only, e.g. 'default' or 'aus1a2b3c4'")
    return value


# -- model configuration -------------------------------------------------------------------


class ModelConfigUpdate(Request):
    llm_provider: Literal["gemini", "openai"] = Field(description="Model that writes the SQL and the answers")
    openai_model: str = Field(default="", description="Empty for the default (gpt-6-luna)")
    openai_reasoning_effort: ReasoningEffort | None = Field(default=None, description="Empty for the model's default")
    openai_api_key: str | None = Field(default=None, description=SECRET_HELP)
    gemini_model: str = Field(default="", description="Empty for the default (gemini-3.8-flash)")
    gemini_api_key: str | None = Field(default=None, description=SECRET_HELP + "; also used for Gemini embeddings")
    embedding_provider: Literal["gemini", "fastembed"] = "gemini"
    embedding_model: str = Field(default="", description="Empty for the provider default")
    embedding_dimensions: Literal[768, 1536, 3072] | None = Field(
        default=None,
        description="Gemini embedding size; changing it requires re-indexing",
    )

    _secrets = field_validator("openai_api_key", "gemini_api_key")(_check_secret)
    _models = field_validator("openai_model", "gemini_model", "embedding_model")(_check_model)

    @model_validator(mode="after")
    def models_match_providers(self) -> "ModelConfigUpdate":
        if self.openai_model.startswith("gemini"):
            raise ValueError("openai_model looks like a Gemini model")
        if self.gemini_model and not self.gemini_model.startswith("gemini"):
            raise ValueError("gemini_model must be a Gemini model (gemini-…)")
        return self


class ProviderConfig(BaseModel):
    model: str = Field(description="Configured model, empty when the default is used")
    default_model: str
    api_key: str | None = Field(description="'…abcd' when a key is configured, otherwise null")


class OpenAIConfig(ProviderConfig):
    reasoning_effort: ReasoningEffort | None


class EmbeddingConfig(BaseModel):
    provider: Literal["gemini", "fastembed"]
    model: str
    default_models: dict[str, str]
    dimensions: int | None


class ModelConfig(BaseModel):
    llm_provider: Literal["gemini", "openai"]
    active_model: str = Field(description="The model the agent uses now")
    openai: OpenAIConfig
    gemini: ProviderConfig
    embedding: EmbeddingConfig
    reasoning_efforts: list[str]
    config_file: str
    warnings: list[str]


class ConnectionTest(BaseModel):
    ok: bool
    message: str


# -- Okta ----------------------------------------------------------------------------------


class OktaConfigUpdate(Request):
    enabled: bool = Field(default=False, description="Turn on Okta sign-in once QueryMind enforces it")
    org_url: str = Field(default="", description="Okta org URL, e.g. https://acme.okta.com")
    authorization_server_id: str = Field(
        default="default",
        description="'default', a custom server id, or empty for the org authorization server",
    )
    client_id: str = Field(default="", max_length=128)
    client_secret: str | None = Field(default=None, description=SECRET_HELP)
    scopes: str = Field(default="openid profile email groups", max_length=300)
    groups_claim: str = Field(default="groups", max_length=64)
    admin_group: str = Field(
        default="",
        max_length=128,
        description="Okta group whose members get the admin console",
    )
    user_group: str = Field(
        default="",
        max_length=128,
        description="Okta group allowed to use QueryMind; empty = all",
    )
    redirect_uri: str = Field(default="", description="Sign-in redirect URI registered in the Okta app")
    post_logout_redirect_uri: str = Field(default="", description="Sign-out redirect URI registered in the Okta app")

    _secret = field_validator("client_secret")(_check_secret)

    _org = field_validator("org_url")(_https_origin)
    _server = field_validator("authorization_server_id")(_server_id)

    @field_validator("redirect_uri", "post_logout_redirect_uri")
    @classmethod
    def http_url(cls, value: str) -> str:
        value = value.strip()
        if value and urlparse(value).scheme not in {"http", "https"}:
            raise ValueError("must be an http(s) URL")
        return value

    @field_validator("client_id", "scopes", "groups_claim", "admin_group", "user_group")
    @classmethod
    def single_line(cls, value: str) -> str:
        value = value.strip()
        if "\n" in value or "\r" in value:
            raise ValueError("must be a single line")
        return value

    @model_validator(mode="after")
    def complete_when_enabled(self) -> "OktaConfigUpdate":
        if self.enabled and not (self.org_url and self.client_id):
            raise ValueError("org_url and client_id are required to enable Okta")
        if self.scopes and "openid" not in self.scopes.split():
            raise ValueError("scopes must include openid")
        return self


class OktaConfig(BaseModel):
    enabled: bool
    org_url: str
    authorization_server_id: str
    issuer: str | None = Field(description="Issuer URL derived from the org URL and authorization server")
    client_id: str
    client_secret: str | None = Field(description="'…abcd' when a secret is configured, otherwise null")
    scopes: str
    groups_claim: str
    admin_group: str
    user_group: str
    redirect_uri: str
    post_logout_redirect_uri: str
    config_file: str
    warnings: list[str]


class OktaTestRequest(Request):
    org_url: str
    authorization_server_id: str = "default"

    _org = field_validator("org_url")(_https_origin)
    _server = field_validator("authorization_server_id")(_server_id)


class OktaTestResult(ConnectionTest):
    issuer: str | None = None
    authorization_endpoint: str | None = None
    token_endpoint: str | None = None
    jwks_uri: str | None = None
    scopes_supported: list[str] = []
