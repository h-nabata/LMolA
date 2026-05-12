from pathlib import Path
import json

from typer.testing import CliRunner

import lmola.cli as cli
from lmola.cli import app

runner = CliRunner()


def test_relax_xtb_unavailable_safe_failure(tmp_path: Path, monkeypatch) -> None:
    run_dir = tmp_path / "outputs" / "run_relax_1"

    def _create_run_dir(base: str = "outputs") -> Path:
        del base
        run_dir.mkdir(parents=True)
        return run_dir

    monkeypatch.setattr(cli, "create_run_dir", _create_run_dir)
    monkeypatch.setattr("lmola.relaxation.shutil.which", lambda name: None)

    result = runner.invoke(app, ["relax", "examples/example.xyz", "--method", "xtb"])
    assert result.exit_code == 0

    payload = json.loads((run_dir / "relaxation_result.json").read_text(encoding="utf-8"))
    assert payload["status"] == "error"
    assert "xTB executable is unavailable" in payload["message"]
    assert (run_dir / "input_structure.xyz").exists()


def test_relax_artifacts_created_for_unsupported_method(tmp_path: Path, monkeypatch) -> None:
    run_dir = tmp_path / "outputs" / "run_relax_2"

    def _create_run_dir(base: str = "outputs") -> Path:
        del base
        run_dir.mkdir(parents=True)
        return run_dir

    monkeypatch.setattr(cli, "create_run_dir", _create_run_dir)

    result = runner.invoke(app, ["relax", "examples/example.xyz", "--method", "nope"])
    assert result.exit_code == 0

    for name in [
        "input_structure.xyz",
        "relaxation_request.json",
        "effective_config.json",
        "environment.json",
        "tool_calls.jsonl",
        "relaxation_result.json",
        "run.log",
        "README_run.md",
        "validation_report.json",
    ]:
        assert (run_dir / name).exists(), name

    payload = json.loads((run_dir / "relaxation_result.json").read_text(encoding="utf-8"))
    assert payload["status"] == "error"
    assert "Unsupported relaxation method" in payload["message"]
