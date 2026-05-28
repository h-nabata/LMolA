from __future__ import annotations

from pathlib import Path

from lmola.artifact_contracts import export_artifact_registry
from lmola.dry_run_plan import create_dry_run_execution_plan, run_molsimplify_pilot_eval
from lmola.mcp_runtime import call_mcp_tool, list_mcp_tools_runtime
from lmola.workflows.catalog import get_workflow_entry

CASES = Path("examples/phase16_6_molsimplify_pilot_cases.yaml")


def test_phase16_6_molsimplify_mock_eval_passes() -> None:
    result = run_molsimplify_pilot_eval(str(CASES), backend="mock")
    assert result["status"] == "ok"
    assert result["schema_version"] == "lmola.molsimplify_pilot_eval.v1"
    assert result["suite_id"] == "phase16_6_molsimplify_pilot"
    assert result["passed_cases"] == result["total_cases"] == 19
    assert result["pass_rate"] == 1.0
    assert result["low_level_tool_exposure_rate"] == 0.0


def test_molsimplify_complete_prompt_dry_run_contract() -> None:
    plan = create_dry_run_execution_plan(
        "Build an octahedral Fe(II) complex with six ammonia ligands using molSimplify."
    )
    assert plan["status"] == "ok"
    assert plan["selected_workflow"]["workflow_id"] == "molsimplify_build_metal_complex"
    assert plan["selected_workflow"]["geometry_modified"] is True
    params = {p["name"]: p["value"] for p in plan["parameter_bindings"]}
    assert params["metal"] == "Fe"
    assert params["oxidation_state"] == 2
    assert params["coordination_geometry"] == "octahedral"
    assert params["ligands"][0]["name"] == "ammonia"
    assert params["ligands"][0]["count"] == 6
    assert plan["can_execute"] is False
    assert plan["safety"]["execution_allowed"] is False


def test_molsimplify_incomplete_prompt_does_not_force_selection() -> None:
    plan = create_dry_run_execution_plan("Use molSimplify to build a metal complex.")
    assert plan["status"] == "needs_clarification"
    assert plan["selected_workflow"]["workflow_id"] is None
    assert plan["can_create_dry_run_plan"] is False
    blocking_text = str(plan["blocking_reasons"]).lower()
    assert "metal" in blocking_text
    assert "ligands" in blocking_text
    assert "coordination" in blocking_text


def test_molsimplify_artifacts_geometry_safety_contracts() -> None:
    contracts = export_artifact_registry(compact=False)["artifact_contracts"]
    assert contracts["molsimplify_complex_structure"]["category"] == "structure"
    assert contracts["molsimplify_complex_structure"]["geometry_modified"] is True
    assert "dry-run request preview" in " ".join(contracts["molsimplify_complex_structure"]["safety_notes"]).lower()
    assert contracts["molsimplify_build_report"]["geometry_role"] == "non_geometry"
    assert contracts["molsimplify_build_report"]["geometry_modified"] is False
    assert contracts["molsimplify_input_deck"]["geometry_role"] == "non_geometry"


def test_molsimplify_low_level_mcp_tools_remain_hidden() -> None:
    exposed = {tool["name"] for tool in list_mcp_tools_runtime()}
    forbidden = {
        "lmola.generate_metal_complex_molsimplify",
        "lmola.molsimplify_generate_complex",
        "lmola.molsimplify_build_complex",
        "lmola.molsimplify_generate_metal_complex",
        "lmola.calculate_molsimplify_complex",
    }
    assert exposed.isdisjoint(forbidden)
    assert "lmola.create_dry_run_execution_plan" in exposed


def test_mcp_molsimplify_dry_run_planning_tool() -> None:
    payload = call_mcp_tool(
        "lmola.create_dry_run_execution_plan",
        {"prompt": "Generate a tetrahedral Zn complex with four chloride ligands using molSimplify."},
    )
    assert payload["selected_workflow"]["workflow_id"] == "molsimplify_build_metal_complex"
    assert payload["safety"]["execution_allowed"] is False


def test_molsimplify_workflow_catalog_contract() -> None:
    entry = get_workflow_entry("molsimplify_build_metal_complex")
    assert entry.contract["operation"] == "metal_complex_generation"
    assert entry.contract["method"] == "molsimplify"
    assert entry.contract["geometry_modified"] is True
    assert entry.input_types == ["metal_complex_build_request"]
