from types import SimpleNamespace

import pytest

from querymind.agent import FinalAnswer
from querymind.exceptions import MissingApiKeyError
from querymind.llm import GeminiLLM, OpenAILLM, create_llm


class FakeResponses:
    """Stands in for OpenAI().responses and records the last call."""

    def __init__(self, parsed=None, output=(), incomplete=None):
        self.parsed = parsed
        self.output = list(output)
        self.incomplete = incomplete
        self.kwargs = None

    def parse(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            output_parsed=self.parsed, output=self.output, incomplete_details=self.incomplete, status="completed"
        )


def openai_llm(responses, **kwargs):
    return OpenAILLM("gpt-6-luna", client=SimpleNamespace(responses=responses), **kwargs)


def test_openai_uses_structured_outputs_without_temperature():
    answer = FinalAnswer(answer="42", caveats=[])
    responses = FakeResponses(parsed=answer)

    assert openai_llm(responses).generate("system", "prompt", FinalAnswer) is answer
    assert responses.kwargs == {
        "model": "gpt-6-luna",
        "instructions": "system",
        "input": "prompt",
        "text_format": FinalAnswer,
        "store": False,
    }


def test_openai_reasoning_effort():
    responses = FakeResponses(parsed=FinalAnswer(answer="a", caveats=[]))
    openai_llm(responses, reasoning_effort="low").generate("s", "p", FinalAnswer)
    assert responses.kwargs["reasoning"] == {"effort": "low"}

    with pytest.raises(ValueError, match="reasoning effort"):
        openai_llm(responses, reasoning_effort="extreme")


def test_openai_refusal_is_reported():
    refusal = SimpleNamespace(content=[SimpleNamespace(type="refusal", refusal="cannot help")])
    with pytest.raises(RuntimeError, match="refused: cannot help"):
        openai_llm(FakeResponses(output=[refusal])).generate("s", "p", FinalAnswer)


def test_openai_incomplete_is_reported():
    with pytest.raises(RuntimeError, match="incomplete: max_output_tokens"):
        openai_llm(FakeResponses(incomplete=SimpleNamespace(reason="max_output_tokens"))).generate(
            "s", "p", FinalAnswer
        )


def test_create_llm_picks_provider_and_default_model(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("GEMINI_API_KEY", "g-test")

    llm = create_llm("openai")
    assert isinstance(llm, OpenAILLM) and llm.model_name == "gpt-6-luna"
    assert isinstance(create_llm("gemini"), GeminiLLM)


def test_create_llm_rejects_mismatched_model(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    with pytest.raises(ValueError, match="does not belong to provider 'openai'"):
        create_llm("openai", "gemini-2.5-flash")
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        create_llm("mistral", "x")


def test_missing_openai_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(MissingApiKeyError, match="OPENAI_API_KEY"):
        create_llm("openai")
