from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from lmola.cli import app
from lmola.mcp_confirmed_execution_smoke import run_mcp_confirmed_execution_smoke
from lmola.mcp_runtime import call_mcp_tool, list_mcp_tools_runtime

runner = CliRunner()


def test_confirmed_execution_smoke_helper() -> None:
    result = run_mcp_confirmed_execution_smoke(timeout_seconds=30)
    assert result["status"] == "ok"
    assert all(result["checks"].values())
    smoke_dir = Path(result["smoke_dir"])
    assert (smoke_dir / "smoke_result.json").exists()
    assert (smoke_dir / "requests.json").exists()
    assert (smoke_dir / "responses.json").exists()


def test_confirmed_execution_smoke_cli_json() -> None:
    res = runner.invoke(app, ["mcp", "confirmed-execution-smoke", "--format", "json"])
    assert res.exit_code == 0
    payload = json.loads(res.stdout)
    assert payload["status"] == "ok"


def test_execution_policy_and_artifact_followups() -> None:
    names = {t["name"] for t in list_mcp_tools_runtime()}
    assert "lmola.compute_rdkit_descriptors" not in names
    assert "lmola.analyze_xyz_geometry" not in names

    no_allow = call_mcp_tool("lmola.run_workflow", {"workflow_id": "smiles_to_rdkit_descriptors", "input": {"type": "smiles", "value": "CCO"}, "dry_run": False, "confirm": True})
    assert no_allow["error_type"] == "execution_not_allowed"
    no_confirm = call_mcp_tool("lmola.run_workflow", {"workflow_id": "smiles_to_rdkit_descriptors", "input": {"type": "smiles", "value": "CCO"}, "dry_run": False, "allow_execution": True})
    assert no_confirm["error_type"] == "confirmation_required"
