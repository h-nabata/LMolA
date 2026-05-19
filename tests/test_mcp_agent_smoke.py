from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from lmola.cli import app
from lmola.mcp_agent_smoke import run_mcp_agent_smoke, validate_agent_tool_call
from lmola.workflows.catalog import WORKFLOW_CATALOG

runner = CliRunner()


def test_agent_smoke_mock_end_to_end() -> None:
    result = run_mcp_agent_smoke(backend="mock")
    assert result["checks"]["run_workflow_dry_run_safe"] is True
    assert result["checks"]["mcp_runs_unchanged"] is True
    smoke_dir = Path(result["agent_smoke_dir"])
    assert (smoke_dir / "tool_selection_validation_errors.json").exists()


def test_agent_smoke_cli_mock_json() -> None:
    res = runner.invoke(app, ["mcp", "agent-smoke", "--backend", "mock", "--format", "json"])
    assert res.exit_code == 0
    payload = json.loads(res.stdout)
    assert payload["selected_workflow_id"] == "smiles_to_xtb_relax"


def test_validation_rejects_observed_bad_ollama_json() -> None:
    bad = {
        "tool_name": "lmola.run_workflow",
        "arguments": {
            "workflow_id": "generate_and_relax_structures",
            "inputs": {"smiles_list_file": "examples/smiles_list.csv"},
            "settings": {"relaxation_method": "xtb", "dry_run": True},
        },
    }
    res = validate_agent_tool_call(tool_call=bad, runtime_tools={"lmola.run_workflow"}, workflow_catalog=WORKFLOW_CATALOG)
    assert res.valid is False
    assert any(e["error_type"] == "unknown_workflow_id" for e in res.errors)
    assert any(e["error_type"] == "forbidden_key" and e["field"] == "arguments.inputs" for e in res.errors)
    assert any(e["error_type"] == "forbidden_key" and e["field"] == "arguments.settings" for e in res.errors)


def test_validation_rejects_execution_flags_default_mode() -> None:
    call = {"tool_name": "lmola.run_workflow", "arguments": {"workflow_id": "smiles_to_xtb_relax", "input": {"type": "smiles_csv", "path": "examples/smiles_list.csv"}, "dry_run": False, "allow_execution": True, "confirm": True}}
    res = validate_agent_tool_call(tool_call=call, runtime_tools={"lmola.run_workflow"}, workflow_catalog=WORKFLOW_CATALOG)
    assert res.valid is False
    assert sum(1 for e in res.errors if e["error_type"] == "execution_not_allowed") >= 3


def test_validation_rejects_low_level_tool() -> None:
    res = validate_agent_tool_call(tool_call={"tool_name": "lmola.generate_small_molecule_rdkit", "arguments": {}}, runtime_tools={"lmola.run_workflow", "lmola.generate_small_molecule_rdkit"}, workflow_catalog=WORKFLOW_CATALOG)
    assert res.valid is False
    assert any(e["error_type"] == "low_level_tool_not_allowed" for e in res.errors)
