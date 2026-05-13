from pathlib import Path
import json
import shutil

import pytest
from typer.testing import CliRunner
import yaml

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


@pytest.mark.external_tools
def test_generate_molsimplify_external_tool_artifacts(tmp_path: Path, monkeypatch) -> None:
    exe = shutil.which("molsimplify") or shutil.which("molSimplify")
    if not exe:
        pytest.skip("molSimplify not installed")

    run_dir = tmp_path / "outputs" / "run_generate_molsimplify"
    _patch_run_dir(monkeypatch, run_dir)

    from lmola.tools import molsimplify_tool

    real_run = molsimplify_tool.subprocess.run
    captured: dict[str, object] = {}

    def _spy_run(*args, **kwargs):
        captured["kwargs"] = dict(kwargs)
        return real_run(*args, **kwargs)

    monkeypatch.setattr("lmola.tools.molsimplify_tool.subprocess.run", _spy_run)

    result = runner.invoke(app, ["generate", "examples/fe_h2o6.yaml"])
    assert result.exit_code == 0
    assert captured.get("kwargs", {}).get("shell") is not True

    assert (run_dir / "request.yaml").exists()
    assert (run_dir / "normalized_request.json").exists()
    assert (run_dir / "tool_result.json").exists()
    assert (run_dir / "tool_calls.jsonl").exists()

    yaml.safe_load((run_dir / "request.yaml").read_text(encoding="utf-8"))
    json.loads((run_dir / "normalized_request.json").read_text(encoding="utf-8"))

    payload = json.loads((run_dir / "tool_result.json").read_text(encoding="utf-8"))
    calls = _jsonl(run_dir / "tool_calls.jsonl")

    assert payload.get("status") in {"ok", "error"}
    assert isinstance(payload.get("command", []), list)
    assert payload.get("cwd")
    assert "returncode" in payload
    assert payload.get("run_dir", "").endswith("run_generate_molsimplify")
    assert isinstance(payload.get("generated_files", []), list)
    assert isinstance(payload.get("artifact_files", []), list)

    assert len(calls) == 1
    call = calls[0]
    assert call["tool"] == "molsimplify"
    assert isinstance(call.get("command", []), list)
    assert call.get("cwd")
    assert "returncode" in call
    assert "stdout_excerpt" in call or "stdout_path" in call
    assert "stderr_excerpt" in call or "stderr_path" in call

    if call.get("stdout_path"):
        assert (run_dir / call["stdout_path"]).exists()
    if call.get("stderr_path"):
        assert (run_dir / call["stderr_path"]).exists()

    xyz_files = [p for p in payload.get("generated_files", []) if p.endswith(".xyz")]
    if payload.get("status") == "ok" and xyz_files:
        assert (run_dir / "validation_report.json").exists()
    if payload.get("status") == "error":
        assert isinstance(payload.get("message"), str)
