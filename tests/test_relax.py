from pathlib import Path
import json
import shutil

import pytest
from typer.testing import CliRunner

import lmola.cli as cli
from lmola.cli import app

runner = CliRunner()


def _patch_run_dir(monkeypatch, run_dir: Path) -> None:
    def _create_run_dir(base: str = "outputs") -> Path:
        del base
        run_dir.mkdir(parents=True)
        return run_dir

    monkeypatch.setattr(cli, "create_run_dir", _create_run_dir)


def _jsonl(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def test_relax_xtb_unavailable_safe_failure_and_artifacts(tmp_path: Path, monkeypatch) -> None:
    run_dir = tmp_path / "outputs" / "run_relax_1"
    _patch_run_dir(monkeypatch, run_dir)
    monkeypatch.setattr("lmola.relaxation.shutil.which", lambda name: None)

    result = runner.invoke(app, ["relax", "examples/example.xyz", "--method", "xtb"])
    assert result.exit_code == 0

    expected = {
        "input_structure.xyz",
        "relaxation_request.json",
        "effective_config.json",
        "environment.json",
        "tool_calls.jsonl",
        "relaxation_result.json",
        "run.log",
        "README_run.md",
        "validation_report.json",
    }
    assert expected.issubset({p.name for p in run_dir.iterdir()})

    payload = json.loads((run_dir / "relaxation_result.json").read_text(encoding="utf-8"))
    assert payload["status"] == "error"
    assert payload["method"] == "xtb"
    assert payload["input_structure"] == "input_structure.xyz"
    assert payload["run_dir"].endswith("run_relax_1")
    assert payload["validation_report_path"] == "validation_report.json"
    assert payload["cwd"].endswith("run_relax_1")
    assert payload["generated_files"] == []
    assert "artifact_files" in payload
    assert "xTB executable is unavailable" in payload["message"]

    records = _jsonl(run_dir / "tool_calls.jsonl")
    assert len(records) == 1
    assert records[0]["tool"] == "xtb"
    assert records[0]["status"] == "error"
    assert records[0]["cwd"].endswith("run_relax_1")


def test_relax_unsupported_method_safe_error_and_artifacts(tmp_path: Path, monkeypatch) -> None:
    run_dir = tmp_path / "outputs" / "run_relax_2"
    _patch_run_dir(monkeypatch, run_dir)

    result = runner.invoke(app, ["relax", "examples/example.xyz", "--method", "nope"])
    assert result.exit_code == 0

    payload = json.loads((run_dir / "relaxation_result.json").read_text(encoding="utf-8"))
    assert payload["status"] == "error"
    assert payload["method"] == "nope"
    assert "Unsupported relaxation method" in payload["message"]
    assert payload["cwd"].endswith("run_relax_2")
    assert (run_dir / "README_run.md").read_text(encoding="utf-8").find("exit_policy") >= 0

    json.loads((run_dir / "relaxation_result.json").read_text(encoding="utf-8"))
    _jsonl(run_dir / "tool_calls.jsonl")


@pytest.mark.external_tools
def test_relax_xtb_external_tool_scaffold(tmp_path: Path, monkeypatch) -> None:
    xtb = shutil.which("xtb")
    if not xtb:
        pytest.skip("xTB not installed")

    run_dir = tmp_path / "outputs" / "run_relax_xtb"
    _patch_run_dir(monkeypatch, run_dir)

    result = runner.invoke(app, ["relax", "examples/example.xyz", "--method", "xtb"])
    assert result.exit_code == 0

    payload = json.loads((run_dir / "relaxation_result.json").read_text(encoding="utf-8"))
    tool_calls = _jsonl(run_dir / "tool_calls.jsonl")

    assert payload["method"] == "xtb"
    assert payload["run_dir"].endswith("run_relax_xtb")
    assert payload["cwd"].endswith("run_relax_xtb")
    assert "status" in payload
    assert "message" in payload
    assert "command" in payload
    assert "returncode" in payload
    assert isinstance(payload["generated_files"], list)
    assert isinstance(payload["artifact_files"], list)
    assert "tool_calls.jsonl" in payload["artifact_files"]
    assert "relaxation_result.json" in payload["artifact_files"]

    assert len(tool_calls) == 1
    call = tool_calls[0]
    assert call["tool"] == "xtb"
    assert isinstance(call.get("command", []), list)
    assert call.get("command", [])
    assert all(isinstance(tok, str) for tok in call.get("command", []))
    assert call.get("cwd", "").endswith("run_relax_xtb")
    assert "returncode" in call
    assert "stdout_excerpt" in call
    assert "stderr_excerpt" in call

    if (run_dir / "xtb.stdout.txt").exists() or (run_dir / "xtb.stderr.txt").exists():
        assert "xtb.stdout.txt" in payload["generated_files"]
        assert "xtb.stderr.txt" in payload["generated_files"]

    if payload.get("output_structure"):
        assert payload["output_structure"] != "input_structure.xyz"

    if "validation_report_path" in payload and payload["validation_report_path"]:
        assert (run_dir / payload["validation_report_path"]).exists()
