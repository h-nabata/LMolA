from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from lmola.cli import app
from lmola.tools.registry import get_tool_availability


pytestmark = pytest.mark.external_tools

runner = CliRunner()


def _require(tool_name: str) -> None:
    if not get_tool_availability(tool_name).available:
        pytest.skip(f"{tool_name} unavailable")


def _run_and_load_summary(path: str) -> list[dict]:
    result = runner.invoke(app, ["workflow", "run", path])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    summary_path = Path(payload["summary_json"])
    assert summary_path.exists()
    return json.loads(summary_path.read_text(encoding="utf-8"))


def test_external_workflow_smiles_to_3d_rdkit() -> None:
    _require("generate_small_molecule_rdkit")
    _require("validate_structure_ase")
    rows = _run_and_load_summary("examples/workflow_smiles_to_3d_rdkit.yaml")
    assert any(r["generate_status"] == "ok" for r in rows)
    assert any(r["validation_status"] == "ok" for r in rows)
    for r in rows:
        if r.get("primary_structure_path"):
            assert Path(r["primary_structure_path"]).exists()


def test_external_workflow_smiles_to_xtb_relax() -> None:
    _require("generate_small_molecule_rdkit")
    _require("validate_structure_ase")
    _require("relax_structure_xtb")
    rows = _run_and_load_summary("examples/workflow_smiles_to_xtb.yaml")
    assert any(r["generate_status"] == "ok" for r in rows)
    assert any(r["validation_status"] == "ok" for r in rows)
    assert any(r["relax_run_dir"] for r in rows)
    for r in rows:
        if r.get("relaxed_structure_path"):
            assert Path(r["relaxed_structure_path"]).exists()
