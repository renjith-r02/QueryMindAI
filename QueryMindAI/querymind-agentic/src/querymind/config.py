"""Settings, read from the environment and the project's .env file.

Real environment variables win over values in .env. See .env.example for every key.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path

from dotenv import load_dotenv

from querymind.llm.providers import DEFAULT_LLM_MODELS, DEFAULT_LLM_PROVIDER

# src/querymind/config.py -> the project directory, which holds .env and sqls/
PROJECT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE_DIR = PROJECT_DIR / "sqls"
DEFAULT_COLLECTION = "querymind_knowledge"


@dataclass(frozen=True)
class Settings:
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    collection: str = DEFAULT_COLLECTION
    embedding_provider: str = "gemini"
    embedding_model: str | None = None
    embedding_dimensions: int | None = None
    gemini_api_key: str | None = None
    llm_provider: str = DEFAULT_LLM_PROVIDER
    llm_model: str | None = None  # None means the provider's default model
    llm_reasoning_effort: str | None = None  # OpenAI reasoning models only
    max_rows: int = 1000  # seeds the guardrail policy's row limit, which then applies
    cache_enabled: bool = True  # semantic cache of answers (see querymind.cache)
    cache_threshold: float = 0.95  # minimum cosine similarity to reuse an answer
    cache_ttl: int = 3600  # seconds an answer may be reused
    datasources_collection: str = "querymind_datasources"  # Qdrant collection holding data source settings
    guardrails_collection: str = "querymind_guardrails"  # Qdrant collection holding the guardrail policy
    query_timeout: int = 30
    source_dir: Path = DEFAULT_SOURCE_DIR

    @classmethod
    def from_env(cls, env_file: Path | None = PROJECT_DIR / ".env") -> Settings:
        """Read settings from the environment; values in `env_file` fill in what is unset."""
        if env_file is not None:
            load_dotenv(env_file)
        llm_provider = os.getenv("LLM_PROVIDER", cls.llm_provider)
        return cls(
            qdrant_url=os.getenv("QDRANT_URL", cls.qdrant_url),
            qdrant_api_key=os.getenv("QDRANT_API_KEY") or None,
            collection=os.getenv("QDRANT_COLLECTION", DEFAULT_COLLECTION),
            embedding_provider=os.getenv("EMBEDDING_PROVIDER", cls.embedding_provider),
            embedding_model=os.getenv("EMBEDDING_MODEL") or None,
            embedding_dimensions=_int_env("EMBEDDING_DIM"),
            llm_provider=llm_provider,
            # LLM_MODEL applies to any provider; OPENAI_MODEL / GEMINI_MODEL only to their own.
            llm_model=os.getenv("LLM_MODEL") or os.getenv(f"{llm_provider.upper()}_MODEL") or None,
            llm_reasoning_effort=os.getenv("LLM_REASONING_EFFORT") or None,
            max_rows=_int_env("QUERYMIND_MAX_ROWS") or cls.max_rows,
            cache_enabled=os.getenv("QUERYMIND_CACHE_ENABLED", "true").strip().lower()
            not in {"0", "false", "no", "off"},
            cache_threshold=float(os.getenv("QUERYMIND_CACHE_THRESHOLD") or cls.cache_threshold),
            cache_ttl=_int_env("QUERYMIND_CACHE_TTL") or cls.cache_ttl,
            datasources_collection=os.getenv("QUERYMIND_DATASOURCES_COLLECTION") or cls.datasources_collection,
            guardrails_collection=os.getenv("QUERYMIND_GUARDRAILS_COLLECTION") or cls.guardrails_collection,
            query_timeout=_int_env("QUERYMIND_QUERY_TIMEOUT") or cls.query_timeout,
            source_dir=Path(os.getenv("QUERYMIND_SOURCE_DIR") or DEFAULT_SOURCE_DIR),
        )

    def with_overrides(self, **changes) -> Settings:
        """Copy with the given fields replaced; None values are ignored."""
        return replace(self, **{key: value for key, value in changes.items() if value is not None})

    @property
    def resolved_llm_model(self) -> str:
        return self.llm_model or DEFAULT_LLM_MODELS.get(self.llm_provider, "")


def _int_env(name: str) -> int | None:
    value = os.getenv(name)
    return int(value) if value else None
