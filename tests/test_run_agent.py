from typer.testing import CliRunner

from lmola.cli import app

runner = CliRunner()


def test_run_agent_not_configured() -> None:
    result = runner.invoke(app, ["run-agent", "Generate an octahedral Fe(II) complex with six water ligands."])
    assert result.exit_code == 1
    assert "Local LLM mode is not configured" in result.stdout


def test_run_agent_mock(monkeypatch) -> None:
    monkeypatch.setenv("LMOLA_LLM_ENABLED", "true")
    monkeypatch.setenv("LMOLA_LLM_BACKEND", "mock")
    result = runner.invoke(app, ["run-agent", "Generate an octahedral Fe(II) complex with six water ligands."])
    assert result.exit_code == 0
    assert "Created run directory" in result.stdout
