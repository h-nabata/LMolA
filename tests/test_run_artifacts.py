from pathlib import Path

from typer.testing import CliRunner

import lmola.cli as cli
from lmola.cli import app

runner = CliRunner()


def test_generate_writes_phase3_artifacts(tmp_path: Path, monkeypatch) -> None:
    run_dir = tmp_path / "outputs" / "run_123"

    def _create_run_dir(base: str = "outputs") -> Path:
        del base
        run_dir.mkdir(parents=True)
        return run_dir

    monkeypatch.setattr(cli, "create_run_dir", _create_run_dir)

    req = tmp_path / "request.yaml"
    req.write_text(
        "\n".join(
            [
                "request_type: metal_complex",
                "metal: Fe",
                "oxidation_state: 2",
                "ligands:",
                "  - name: H2O",
                "    count: 6",
            ]
        ),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["generate", str(req)])
    assert result.exit_code == 0

    assert (run_dir / "request.yaml").exists()
    assert (run_dir / "normalized_request.json").exists()
    assert (run_dir / "effective_config.json").exists()
    assert (run_dir / "environment.json").exists()
    assert (run_dir / "tool_calls.jsonl").exists()
    assert (run_dir / "tool_result.json").exists()
    assert (run_dir / "run.log").exists()
    assert (run_dir / "README_run.md").exists()


def test_run_agent_writes_hardening_artifacts(clean_lmola_config, tmp_path: Path, monkeypatch) -> None:
    run_dir = tmp_path / "outputs" / "run_agent_123"

    def _create_run_dir(base: str = "outputs") -> Path:
        del base
        run_dir.mkdir(parents=True)
        return run_dir

    monkeypatch.setattr(cli, "create_run_dir", _create_run_dir)
    cfg_dir = tmp_path / ".lmola"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "config.yaml").write_text("llm:\n  enabled: true\n  backend: mock\n  model: mock-local\n", encoding="utf-8")
    result = runner.invoke(app, ["run-agent", "Generate an octahedral Fe(II) complex with six water ligands."])
    assert result.exit_code == 0
    for name in [
        "natural_language_request.txt",
        "llm_prompt.txt",
        "llm_response.json",
        "parsed_request.json",
        "request.yaml",
        "normalized_request.json",
        "effective_config.json",
        "environment.json",
        "tool_calls.jsonl",
        "tool_result.json",
        "run.log",
        "README_run.md",
        "llm_config_redacted.json",
    ]:
        assert (run_dir / name).exists(), name
