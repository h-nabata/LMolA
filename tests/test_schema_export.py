from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from lmola.cli import app
from lmola.schema_export import export_all_schemas, export_model_schemas, export_planner_schema_bundle
from lmola.agent.workflow_planner import build_schema_driven_planner_context

runner = CliRunner()


def test_schema_export_json_cli() -> None:
    result = runner.invoke(app, ["schema", "export", "--format", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "lmola.schema_bundle.v1"
    assert "WorkflowRequest" in payload["models"]
    assert "MoleculeBuildRequest" in payload["models"]
    assert "RelaxXtbRequest" in payload["models"]
    assert "ValidateStructureRequest" in payload["models"]
    assert "workflow_contract_schema" in payload
    assert "artifact_contract_schema" in payload
    assert "artifact_registry_schema" in payload
    assert "artifact_contracts" in payload


def test_model_schema_contains_molecule_build_request() -> None:
    payload = export_all_schemas()
    required = {
        "WorkflowRequest",
        "MoleculeBuildRequest",
        "BuildOptions",
        "RelaxXtbRequest",
        "ValidateStructureRequest",
        "ToolResult",
        "ToolCallRecord",
        "PlannerEvalSuite",
        "PlannerEvalCase",
    }
    assert required.issubset(set(payload["models"].keys()))


def test_model_schemas_standalone_contains_required_models() -> None:
    payload = export_model_schemas()
    required = {
        "WorkflowRequest",
        "MoleculeBuildRequest",
        "BuildOptions",
        "RelaxXtbRequest",
        "ValidateStructureRequest",
        "ToolResult",
        "ToolCallRecord",
        "PlannerEvalSuite",
        "PlannerEvalCase",
    }
    assert required.issubset(set(payload["models"].keys()))


def test_tools_export_schema_contains_expected_tools() -> None:
    result = runner.invoke(app, ["tools", "export-schema", "--format", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    names = {tool["name"] for tool in payload["tools"]}
    assert "generate_small_molecule_rdkit" in names
    assert "relax_structure_xtb" in names


def test_workflow_export_catalog_contains_smiles_to_xtb_relax() -> None:
    result = runner.invoke(app, ["workflow", "export-catalog", "--format", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    wf = {w["workflow_id"]: w for w in payload["workflows"]}
    assert "smiles_to_xtb_relax" in wf
    assert wf["smiles_to_xtb_relax"]["canonical_steps"]
    assert "contract" in wf["smiles_to_xtb_relax"]


def test_planner_context_compact_contract() -> None:
    payload = export_planner_schema_bundle()
    assert payload["allowed_workflow_ids"]
    assert payload["output_contract"]["unsupported_task"]["status_value"] == "unsupported"
    sample = payload["workflows"][0]
    assert "operation" in sample and "method" in sample and "geometry_modified" in sample
    assert "artifact_contract_summaries" in payload
    assert len(payload["artifact_contract_summaries"]) >= 10
    assert payload["artifact_manifest_runtime"]["compatibility_field"] == "next_compatible_workflows"


def test_schema_export_out_writes_files(tmp_path: Path) -> None:
    out = tmp_path / "schema_manual_test"
    result = runner.invoke(app, ["schema", "export", "--out", str(out)])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    output_dir = Path(payload["output_dir"])
    assert output_dir == out
    expected = {
        "schema_bundle.json",
        "model_schemas.json",
        "tool_registry_schema.json",
        "workflow_catalog.json",
        "workflow_catalog.yaml",
        "planner_context_compact.json",
        "README_schema.md",
    }
    assert expected.issubset({p.name for p in output_dir.iterdir()})


def test_schema_export_deterministic_except_output_metadata() -> None:
    a = export_all_schemas()
    b = export_all_schemas()
    assert a == b


def test_schema_export_out_deterministic_json_payloads(tmp_path: Path) -> None:
    out_a = tmp_path / "schema_export_a"
    out_b = tmp_path / "schema_export_b"

    result_a = runner.invoke(app, ["schema", "export", "--out", str(out_a)])
    result_b = runner.invoke(app, ["schema", "export", "--out", str(out_b)])
    assert result_a.exit_code == 0
    assert result_b.exit_code == 0

    for name in [
        "model_schemas.json",
        "tool_registry_schema.json",
        "workflow_catalog.json",
        "planner_context_compact.json",
    ]:
        a = json.loads((out_a / name).read_text())
        b = json.loads((out_b / name).read_text())
        assert a == b


def test_schema_driven_context_matches_export() -> None:
    assert build_schema_driven_planner_context() == export_planner_schema_bundle()
