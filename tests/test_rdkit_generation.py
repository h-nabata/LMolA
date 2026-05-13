from pathlib import Path
import json
import pytest
from typer.testing import CliRunner

import lmola.cli as cli
from lmola.cli import app
from lmola.schemas import MoleculeBuildRequest

runner = CliRunner()


def _patch_run_dir(monkeypatch, run_dir: Path) -> None:
    def _create_run_dir(base: str = "outputs") -> Path:
        del base
        run_dir.mkdir(parents=True)
        return run_dir
    monkeypatch.setattr(cli, "create_run_dir", _create_run_dir)


def test_small_molecule_schema_parse() -> None:
    req = MoleculeBuildRequest.model_validate({"request_type":"small_molecule","smiles":"CCO","backend":"rdkit"})
    assert req.smiles == "CCO"


def test_generate_rdkit_unavailable_safe_failure(tmp_path: Path, monkeypatch) -> None:
    run_dir = tmp_path / "outputs" / "run_rdkit_missing"
    _patch_run_dir(monkeypatch, run_dir)
    monkeypatch.setattr("lmola.tools.rdkit_tool.run_rdkit_generation", lambda req, rd: __import__("lmola.schemas", fromlist=["ToolResult"]).ToolResult(status="error", message="RDKit is unavailable. Install LMolA with the rdkit extra or install RDKit in the environment.", cwd=str(rd)))
    result = runner.invoke(app, ["generate", "examples/ethanol_smiles.yaml"])
    assert result.exit_code == 0
    payload = json.loads((run_dir / "tool_result.json").read_text())
    assert payload["status"] == "error"
    assert "RDKit is unavailable" in payload["message"]


@pytest.mark.external_tools
def test_generate_rdkit_external(tmp_path: Path, monkeypatch) -> None:
    pytest.importorskip("rdkit")
    run_dir = tmp_path / "outputs" / "run_rdkit"
    _patch_run_dir(monkeypatch, run_dir)
    result = runner.invoke(app, ["generate", "examples/ethanol_smiles.yaml"])
    assert result.exit_code == 0
    assert (run_dir / "molecule.xyz").exists()
    assert (run_dir / "tool_result.json").exists()
    assert (run_dir / "validation_report.json").exists()
