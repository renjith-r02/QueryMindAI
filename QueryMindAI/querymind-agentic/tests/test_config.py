from querymind.config import Settings


def test_settings_from_env(monkeypatch, tmp_path):
    for name in ("LLM_MODEL", "OPENAI_MODEL", "LLM_REASONING_EFFORT"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-6-sol")
    monkeypatch.setenv("LLM_REASONING_EFFORT", "high")

    settings = Settings.from_env(env_file=None)
    assert (settings.llm_provider, settings.resolved_llm_model, settings.llm_reasoning_effort) == (
        "openai",
        "gpt-6-sol",
        "high",
    )

    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    assert Settings.from_env(env_file=None).resolved_llm_model == "gemini-3.8-flash"  # OPENAI_MODEL ignored


def test_gemini_is_the_default(monkeypatch):
    for name in ("LLM_PROVIDER", "LLM_MODEL", "GEMINI_MODEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OPENAI_MODEL", "gpt-6-luna")  # only applies when the provider is openai
    settings = Settings.from_env(env_file=None)
    assert (settings.llm_provider, settings.resolved_llm_model) == ("gemini", "gemini-3.8-flash")
