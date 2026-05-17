from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from lmola.cli import app
from lmola.schema_export import export_all_schemas, export_planner_schema_bundle

runner = CliRunner()


def test_schema_export_json_cli() -> None:
    result = runner.invoke(app, ["schema", "export", "--format", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "lmola.schema_bundle.v1"
    assert "WorkflowRequest" in payload["models"]["models"]


def test_model_schema_contains_molecule_build_request() -> None:
    payload = export_all_schemas()
    assert "MoleculeBuildRequest" in payload["models"]["models"]


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


def test_planner_context_compact_contract() -> None:
    payload = export_planner_schema_bundle()
    assert payload["allowed_workflow_ids"]
    assert payload["output_contract"]["unsupported_task"]["status_value"] == "unsupported"


def test_schema_export_out_writes_files(tmp_path: Path) -> None:
    out = tmp_path / "schema_manual_test"
    result = runner.invoke(app, ["schema", "export", "--out", str(out)])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    output_dir = Path(payload["output_dir"])
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
