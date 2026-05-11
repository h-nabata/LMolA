from pathlib import Path

from typer.testing import CliRunner

from lmola.cli import app

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
