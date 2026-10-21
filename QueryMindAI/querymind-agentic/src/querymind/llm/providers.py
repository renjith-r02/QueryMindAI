"""Language models that return structured (pydantic) output.

* gemini - Google Gemini (default). Key from GEMINI_API_KEY / GOOGLE_API_KEY.
* openai - OpenAI Responses API with Structured Outputs. Key from OPENAI_API_KEY.

    llm = create_llm("openai")                 # gpt-6-luna
    plan = llm.generate(system, prompt, SqlAnswer)
"""

from __future__ import annotations

import os
from typing import Protocol, TypeVar

from pydantic import BaseModel

from querymind.exceptions import MissingApiKeyError
from querymind.llm.gemini_client import make_client, with_retry

T = TypeVar("T", bound=BaseModel)

LLM_PROVIDERS = ("gemini", "openai")
DEFAULT_LLM_PROVIDER = "gemini"
DEFAULT_LLM_MODELS = {
    "gemini": "gemini-3.8-flash",
    "openai": "gpt-6-luna",
}
REASONING_EFFORTS = ("none", "low", "medium", "high", "xhigh", "max")


class LLM(Protocol):
    model_name: str

    def generate(self, system: str, prompt: str, schema: type[T]) -> T: ...


class GeminiLLM:
    def __init__(
        self, model_name: str = DEFAULT_LLM_MODELS["gemini"], api_key: str | None = None, temperature: float = 0.0
    ):
        self.client = make_client(api_key)
        self.model_name = model_name
        self.temperature = temperature

    def generate(self, system: str, prompt: str, schema: type[T]) -> T:
        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=self.temperature,
            response_mime_type="application/json",
            response_schema=schema,
        )
        response = with_retry(
            lambda: self.client.models.generate_content(model=self.model_name, contents=prompt, config=config)
        )
        if isinstance(response.parsed, schema):
            return response.parsed
        if not response.text:
            raise RuntimeError(f"{self.model_name} returned no content (finish reason: {_finish_reason(response)})")
        return schema.model_validate_json(response.text)


class OpenAILLM:
    """OpenAI Responses API with Structured Outputs.

    Temperature is not sent: GPT-6 models are reasoning models, tuned with
    `reasoning_effort` instead (none, low, medium, high, xhigh, max; the model's
    default when unset).
    """

    def __init__(
        self,
        model_name: str = DEFAULT_LLM_MODELS["openai"],
        api_key: str | None = None,
        reasoning_effort: str | None = None,
        max_retries: int = 5,
        client=None,
    ):
        if reasoning_effort is not None and reasoning_effort not in REASONING_EFFORTS:
            raise ValueError(f"Unknown reasoning effort {reasoning_effort!r}; choose one of {REASONING_EFFORTS}")
        self.client = client or _make_openai_client(api_key, max_retries)
        self.model_name = model_name
        self.reasoning_effort = reasoning_effort

    def generate(self, system: str, prompt: str, schema: type[T]) -> T:
        options = {"reasoning": {"effort": self.reasoning_effort}} if self.reasoning_effort else {}
        # The SDK retries rate limits and server errors itself (max_retries).
        response = self.client.responses.parse(
            model=self.model_name,
            instructions=system,
            input=prompt,
            text_format=schema,
            store=False,
            **options,
        )
        parsed = response.output_parsed
        if parsed is None:
            raise RuntimeError(f"{self.model_name} returned no structured output ({_openai_reason(response)})")
        return parsed


def create_llm(
    provider: str = DEFAULT_LLM_PROVIDER,
    model_name: str | None = None,
    api_key: str | None = None,
    reasoning_effort: str | None = None,
) -> LLM:
    if provider not in LLM_PROVIDERS:
        raise ValueError(f"Unknown LLM provider {provider!r}; choose one of {LLM_PROVIDERS}")
    model_name = model_name or DEFAULT_LLM_MODELS[provider]
    if (provider == "openai") == model_name.startswith("gemini"):
        raise ValueError(
            f"LLM model {model_name!r} does not belong to provider {provider!r}. "
            "Set LLM_MODEL (or --llm-model) for that provider, or leave it unset to use "
            f"{DEFAULT_LLM_MODELS.get(provider)}."
        )
    if provider == "gemini":
        return GeminiLLM(model_name, api_key=api_key)
    return OpenAILLM(model_name, api_key=api_key, reasoning_effort=reasoning_effort)


def _make_openai_client(api_key: str | None, max_retries: int):
    from openai import OpenAI

    api_key = api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise MissingApiKeyError(
            "No OpenAI API key. Set OPENAI_API_KEY in the environment or in querymind-agentic/.env. "
            "Create a key at https://platform.openai.com/api-keys"
        )
    return OpenAI(api_key=api_key, max_retries=max_retries)


def _openai_reason(response) -> str:
    for item in getattr(response, "output", None) or []:
        for content in getattr(item, "content", None) or []:
            if getattr(content, "type", None) == "refusal":
                return f"refused: {content.refusal}"
    details = getattr(response, "incomplete_details", None)
    if details is not None:
        return f"incomplete: {details.reason}"
    return f"status: {getattr(response, 'status', 'unknown')}"


def _finish_reason(response) -> str:
    candidates = getattr(response, "candidates", None) or []
    return str(candidates[0].finish_reason) if candidates else "unknown"
