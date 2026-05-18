from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from lmola.cli import app
from lmola.mcp_preview import export_mcp_preview_bundle, export_mcp_tools_preview, validate_mcp_preview_bundle

runner = CliRunner()


def _tool_map(payload: dict) -> dict[str, dict]:
    return {t["name"]: t for t in payload["tools"]}


def test_mcp_preview_tools_json_cli() -> None:
    result = runner.invoke(app, ["mcp", "preview-tools", "--format", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "tools" in payload and payload["tools"]


def test_mcp_preview_bundle_core_shape() -> None:
    bundle = export_mcp_preview_bundle()
    assert bundle["schema_version"] == "lmola.mcp_preview.v1"
    assert bundle["mcp_compatibility"]["server_runtime"] is False
    assert bundle["mcp_compatibility"]["jsonrpc"] is False


def test_mcp_preview_required_tools_and_meta() -> None:
    tools = _tool_map(export_mcp_preview_bundle())
    assert "lmola.plan_workflow" in tools
    assert "lmola.validate_workflow" in tools
    assert "lmola.run_workflow" in tools
    assert tools["lmola.run_workflow"]["_meta"]["lmola"]["requires_confirmation"] is True
    assert tools["lmola.run_workflow"]["_meta"]["lmola"]["side_effects"] is True
    assert tools["lmola.plan_workflow"]["_meta"]["lmola"]["side_effects"] is False


def test_mcp_preview_descriptor_shape_and_uniqueness() -> None:
    tools = export_mcp_tools_preview()["tools"]
    names = [t["name"] for t in tools]
    assert len(names) == len(set(names))
    for tool in tools:
        assert "name" in tool and "description" in tool and "inputSchema" in tool


def test_mcp_preview_inspect_workflow_enum_contains_smiles_to_xtb_relax() -> None:
    tools = _tool_map(export_mcp_preview_bundle())
    enum_values = tools["lmola.inspect_workflow"]["inputSchema"]["properties"]["workflow_id"]["enum"]
    assert "smiles_to_xtb_relax" in enum_values


def test_mcp_preview_workflow_schema_compatible() -> None:
    tools = _tool_map(export_mcp_preview_bundle())
    validate_schema = tools["lmola.validate_workflow"]["inputSchema"]
    assert "properties" in validate_schema
    assert "workflow_id" in validate_schema["properties"]
    assert "input" in validate_schema["properties"]


def test_mcp_preview_low_level_marked() -> None:
    tools = export_mcp_tools_preview()["tools"]
    low_level = [t for t in tools if t["name"].startswith("lmola.generate_") or t["name"].startswith("lmola.relax_") or t["name"].startswith("lmola.validate_structure_")]
    assert low_level
    for tool in low_level:
        assert tool["_meta"]["lmola"]["level"] == "low_level_tool"


def test_mcp_preview_out_writes_files(tmp_path: Path) -> None:
    out = tmp_path / "mcp_preview_test"
    result = runner.invoke(app, ["mcp", "preview", "--out", str(out)])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    expected = {"mcp_preview_bundle.json", "mcp_tools_preview.json", "README_mcp_preview.md"}
    assert expected.issubset({p.name for p in out.iterdir()})


def test_mcp_preview_deterministic_tools() -> None:
    assert export_mcp_tools_preview() == export_mcp_tools_preview()


def test_mcp_preview_validation_helper_ok() -> None:
    errors = validate_mcp_preview_bundle(export_mcp_preview_bundle())
    assert errors == []


def test_mcp_validate_preview_cli(tmp_path: Path) -> None:
    out = tmp_path / "mcp_preview_test"
    runner.invoke(app, ["mcp", "preview", "--out", str(out)])
    result = runner.invoke(app, ["mcp", "validate-preview", str(out / "mcp_preview_bundle.json")])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
