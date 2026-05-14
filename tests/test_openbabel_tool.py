from pathlib import Path
import json
import stat

import pytest
from typer.testing import CliRunner

import lmola.cli as cli
from lmola.cli import app
from lmola.schemas import MoleculeBuildRequest
from lmola.tools.openbabel_tool import detect_openbabel_cli, run_openbabel_conversion
from lmola.tools.molsimplify_tool import run_generation

runner = CliRunner()

def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _patch_run_dir(monkeypatch, run_dir: Path) -> None:
    def _create_run_dir(base: str = "outputs") -> Path:
        del base
        run_dir.mkdir(parents=True)
        return run_dir

    monkeypatch.setattr(cli, "create_run_dir", _create_run_dir)


def test_detect_openbabel_cli_env_override(tmp_path: Path, monkeypatch) -> None:
    fake_exe = tmp_path / "obabel"
    fake_exe.write_text("#!/bin/sh\necho 'Open Babel 3.1.1'\n", encoding="utf-8")
    fake_exe.chmod(fake_exe.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("LMOLA_OBABEL_EXECUTABLE", str(fake_exe))
    assert detect_openbabel_cli() == str(fake_exe.resolve())


def test_openbabel_unavailable_safe_failure(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("LMOLA_OBABEL_EXECUTABLE", raising=False)
    monkeypatch.setattr("lmola.tools.openbabel_tool.shutil.which", lambda *_: None)
    req = MoleculeBuildRequest.model_validate({"request_type": "small_molecule", "backend": "openbabel", "smiles": "CCO"})
    result = run_generation(req, tmp_path)
    assert result.status == "error"
    assert "Open Babel CLI is unavailable" in result.message
    assert result.command == []


def test_openbabel_conversion_unavailable_safe_failure(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("lmola.tools.openbabel_tool.detect_openbabel_cli", lambda: None)
    result = run_openbabel_conversion(tmp_path, Path("in.xyz"), Path("out.sdf"))
    assert result.status == "error"


def test_generate_dispatch_openbabel(tmp_path: Path, monkeypatch) -> None:
    run_dir = tmp_path / "outputs" / "run_ob"
    _patch_run_dir(monkeypatch, run_dir)
    result = runner.invoke(app, ["generate", "examples/ethanol_openbabel.yaml"])
    assert result.exit_code == 0
    payload = json.loads((run_dir / "tool_result.json").read_text(encoding="utf-8"))
    assert payload["cwd"] == str(run_dir)


@pytest.mark.external_tools
def test_generate_openbabel_external(tmp_path: Path, monkeypatch) -> None:
    if not detect_openbabel_cli():
        pytest.skip("obabel unavailable")
    run_dir = tmp_path / "outputs" / "run_ob_external"
    _patch_run_dir(monkeypatch, run_dir)
    result = runner.invoke(app, ["generate", "examples/ethanol_openbabel.yaml"])
    assert result.exit_code == 0
    payload = json.loads((run_dir / "tool_result.json").read_text(encoding="utf-8"))
    calls = _jsonl(run_dir / "tool_calls.jsonl")
    assert payload["command"]
    assert payload["cwd"] == str(run_dir)
    assert isinstance(payload.get("returncode"), int)
    assert calls
    assert calls[0]["tool"] == "openbabel"
    assert calls[0]["command"]
    assert calls[0]["cwd"] == str(run_dir)
    assert isinstance(calls[0].get("returncode"), int)
    if (run_dir / "molecule.xyz").exists():
        assert (run_dir / "validation_report.json").exists()
        assert "molecule.xyz" in payload.get("generated_files", [])


@pytest.mark.external_tools
def test_convert_openbabel_external(tmp_path: Path, monkeypatch) -> None:
    if not detect_openbabel_cli():
        pytest.skip("obabel unavailable")
    run_dir = tmp_path / "outputs" / "run_convert_external"
    _patch_run_dir(monkeypatch, run_dir)
    result = runner.invoke(app, ["convert", "examples/example.xyz", "--to", "sdf"])
    assert result.exit_code == 0
    assert (run_dir / "conversion_result.json").exists()


def test_openbabel_run_and_collect_relative_run_dir(tmp_path: Path, monkeypatch) -> None:
    from lmola.tools import openbabel_tool

    class DummyCompleted:
        returncode = 0
        stdout = "ok"
        stderr = ""

    monkeypatch.chdir(tmp_path)
    run_dir = Path("outputs") / "run_relative"
    run_dir.mkdir(parents=True)
    monkeypatch.setattr(openbabel_tool.subprocess, "run", lambda *args, **kwargs: DummyCompleted())

    result = openbabel_tool._run_and_collect(["obabel", "in.smi", "-O", "molecule.xyz"], run_dir, set(), "test")

    assert result.status == "ok"
    assert result.cwd
    assert "openbabel.stdout.txt" in result.generated_files
    assert "openbabel.stderr.txt" in result.generated_files
    assert all(not Path(name).is_absolute() for name in result.generated_files)
