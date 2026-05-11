from pathlib import Path

from typer.testing import CliRunner

import lmola.cli as cli
from lmola.cli import app
from lmola.tools.llm_client import LLMResult

runner = CliRunner()


def test_run_agent_not_configured(clean_lmola_config) -> None:
    result = runner.invoke(app, ["run-agent", "Generate an octahedral Fe(II) complex with six water ligands."])
    assert result.exit_code == 1
    assert "Local LLM mode is not configured" in result.stdout


def test_run_agent_mock(clean_lmola_config, tmp_path: Path) -> None:
    cfg_dir = tmp_path / ".lmola"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "config.yaml").write_text(
        "\n".join(
            [
                "llm:",
                "  enabled: true",
                "  backend: mock",
                "  model: mock-local",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = runner.invoke(app, ["run-agent", "Generate an octahedral Fe(II) complex with six water ligands."])
    assert result.exit_code == 0
    assert "Created run directory" in result.stdout


def test_run_agent_invalid_json_fails_safely(clean_lmola_config, tmp_path: Path, monkeypatch) -> None:
    cfg_dir = tmp_path / ".lmola"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "config.yaml").write_text("llm:\n  enabled: true\n  backend: mock\n", encoding="utf-8")

    class BadJsonClient:
        def complete_json(self, system_prompt: str, user_prompt: str) -> LLMResult:
            del system_prompt, user_prompt
            return LLMResult(status="error", backend="mock", raw_response="not-json", error_message="Invalid JSON from LLM: malformed payload")

    monkeypatch.setattr("lmola.agent.planner.make_llm_client", lambda cfg: BadJsonClient())
    result = runner.invoke(app, ["run-agent", "do thing"])
    assert result.exit_code == 1
    assert "Invalid JSON from LLM" in result.stdout


def test_run_agent_unsupported_request_not_implemented(clean_lmola_config, tmp_path: Path, monkeypatch) -> None:
    run_dir = tmp_path / "outputs" / "run_unsupported"

    def _create_run_dir(base: str = "outputs") -> Path:
        del base
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    monkeypatch.setattr(cli, "create_run_dir", _create_run_dir)
    cfg_dir = tmp_path / ".lmola"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "config.yaml").write_text("llm:\n  enabled: true\n  backend: mock\n", encoding="utf-8")

    class UnsupportedClient:
        def complete_json(self, system_prompt: str, user_prompt: str) -> LLMResult:
            del system_prompt, user_prompt
            payload = {"request_type": "polymer", "metal": "Fe"}
            return LLMResult(status="ok", backend="mock", raw_response='{"request_type":"polymer"}', parsed_json=payload)

    monkeypatch.setattr("lmola.agent.planner.make_llm_client", lambda cfg: UnsupportedClient())
    result = runner.invoke(app, ["run-agent", "unsupported"])
    assert result.exit_code == 0
    assert (run_dir / "tool_result.json").exists()
    assert '"status": "not_implemented"' in (run_dir / "tool_result.json").read_text(encoding="utf-8")
