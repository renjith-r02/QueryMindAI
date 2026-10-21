from querymind import cli
from querymind.config import Settings


def test_cli_flags_override_settings():
    settings = Settings(qdrant_url="http://env:6333", llm_model="env-model", max_rows=10)
    args = cli.build_parser(settings).parse_args(["--url", "http://flag", "run", "q", "--llm-model", "flag-model"])
    service = cli._service(args)
    assert service.settings.llm_model == "flag-model"
    assert service.settings.qdrant_url == "http://flag"
    assert service.settings.max_rows == 10  # not given on the command line


def test_cli_dry_run(capsys):
    assert cli.main(["index", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "ecommerce_mysql_schema.sql [ecommerce]" in out


def test_cli_llm_flags():
    args = cli.build_parser(Settings()).parse_args(
        ["run", "q", "--llm-provider", "openai", "--llm-model", "gpt-6-sol", "--reasoning-effort", "medium"]
    )
    settings = cli._service(args).settings
    assert (settings.llm_provider, settings.llm_model, settings.llm_reasoning_effort) == (
        "openai",
        "gpt-6-sol",
        "medium",
    )


def test_cli_refuses_delete_without_any_service_call(capsys, monkeypatch):
    # The rule check runs before the knowledge store or a model is touched.
    monkeypatch.setenv("QDRANT_URL", ":memory:")  # the guardrail policy is read from Qdrant
    monkeypatch.setattr("querymind.service.QueryMindService.store", property(lambda self: _no_store()))
    assert cli.main(["run", "delete every cancelled order"]) == 1
    out = capsys.readouterr().out
    assert "Intent: UNSUPPORTED (rules)" in out
    assert "Refused: Deleting data is not allowed" in out


def _no_store():
    raise AssertionError("the knowledge store must not be used for a refused request")
