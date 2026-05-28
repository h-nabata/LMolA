from __future__ import annotations

import json

from typer.testing import CliRunner

from lmola.artifact_contracts import export_artifact_registry, validate_artifact_contract_registry
from lmola.cli import app
from lmola.mcp_runtime import call_mcp_tool, list_mcp_tools_runtime
from lmola.workflows.catalog import WORKFLOW_CATALOG

runner = CliRunner()


def test_registry_contains_expected_artifact_types() -> None:
    contracts = export_artifact_registry(compact=False)["artifact_contracts"]
    for name in {
        "xyz_geometry", "validated_xyz", "generated_xyz", "relaxed_xyz", "optimized_geometry", "converted_structure", "xtb_singlepoint_result", "xtb_relax_result", "geometry_analysis_report", "rmsd_report", "geometry_comparison_report", "element_count_report", "molecule_split_report", "rdkit_descriptor_table", "descriptor_filter_report", "conformer_ensemble", "validation_report", "workflow_summary", "triage_report", "mcp_audit",
    }:
        assert name in contracts


def test_selected_semantics() -> None:
    contracts = export_artifact_registry(compact=False)["artifact_contracts"]
    assert contracts["relaxed_xyz"]["category"] == "structure"
    assert contracts["relaxed_xyz"]["geometry_modified"] is True
    assert "xyz_to_xtb_relax" in contracts["relaxed_xyz"]["produced_by"]
    assert "relaxed" in contracts["relaxed_xyz"]["semantic_tags"]

    assert contracts["xtb_singlepoint_result"]["category"] == "result"
    assert contracts["xtb_singlepoint_result"]["geometry_modified"] is False
    assert "xyz_to_xtb_singlepoint" in contracts["xtb_singlepoint_result"]["produced_by"]


def test_cross_reference_workflow_artifacts_in_registry() -> None:
    contracts = export_artifact_registry(compact=False)["artifact_contracts"]
    for entry in WORKFLOW_CATALOG.values():
        for out in entry.contract.get("artifact_outputs", []):
            assert out["artifact_type"] in contracts


def test_validate_contracts_ok() -> None:
    payload = validate_artifact_contract_registry()
    assert payload["status"] == "ok"
    assert payload["missing_artifact_contracts"] == []
    assert payload["invalid_artifact_contracts"] == []
    assert payload["workflow_artifact_reference_errors"] == []


def test_artifact_cli_commands() -> None:
    exp = runner.invoke(app, ["artifact", "export-contracts", "--format", "json"])
    assert exp.exit_code == 0
    payload = json.loads(exp.stdout)
    assert payload["status"] == "ok"
    assert payload["schema_version"] == "lmola.artifact_registry.v1"

    val = runner.invoke(app, ["artifact", "validate-contracts", "--format", "json"])
    assert val.exit_code == 0
    vp = json.loads(val.stdout)
    assert vp["status"] == "ok"


def test_mcp_artifact_contract_tool() -> None:
    names = {t["name"] for t in list_mcp_tools_runtime()}
    assert "lmola.get_artifact_contracts" in names

    all_out = call_mcp_tool("lmola.get_artifact_contracts", {"compact": False})
    assert all_out["status"] == "ok"
    assert "artifact_contracts" in all_out

    one = call_mcp_tool("lmola.get_artifact_contracts", {"artifact_type": "xtb_singlepoint_result", "compact": False})
    assert one["status"] == "ok"
    assert one["artifact_type"] == "xtb_singlepoint_result"

    bad = call_mcp_tool("lmola.get_artifact_contracts", {"artifact_type": "not_real"})
    assert bad["status"] == "error"
    assert bad["error_type"] == "unknown_artifact_type"
