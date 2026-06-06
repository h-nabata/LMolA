from __future__ import annotations

import json

from typer.testing import CliRunner

from lmola.adapters import AdapterRiskClass, list_adapter_metadata, list_optional_smoke_results
from lmola.artifact_contracts import export_artifact_registry
from lmola.cli import app
from lmola.dry_run_plan import create_dry_run_execution_plan, run_phase17_existing_tool_depth_eval
from lmola.mcp_runtime import call_mcp_tool, list_mcp_tools_runtime
from lmola.schema_export import export_all_schemas, export_planner_schema_bundle

CASES = "examples/phase17_existing_tool_depth_cases.yaml"
runner = CliRunner()


def _operation_ids(adapter_id: str) -> set[str]:
    return {profile.operation_id for profile in list_adapter_metadata()[adapter_id].operation_profiles}


def test_phase17_adapter_operation_profiles_are_explicit() -> None:
    adapters = list_adapter_metadata()

    assert adapters["xtb"].risk_class == AdapterRiskClass.EXTERNAL_EXECUTION
    assert {"singlepoint_energy", "geometry_optimization"}.issubset(_operation_ids("xtb"))
    xtb_single = next(p for p in adapters["xtb"].operation_profiles if p.operation_id == "singlepoint_energy")
    xtb_relax = next(p for p in adapters["xtb"].operation_profiles if p.operation_id == "geometry_optimization")
    assert xtb_single.geometry_modified is False
    assert xtb_single.output_artifact_types == ["xtb_singlepoint_result"]
    assert xtb_relax.geometry_modified is True
    assert "optimized_geometry" in xtb_relax.output_artifact_types

    assert {"structure_validation", "geometry_analysis"}.issubset(_operation_ids("ase"))
    assert {"descriptor_calculation", "conformer_generation"}.issubset(_operation_ids("rdkit"))
    assert {"format_conversion", "smiles_3d_generation"}.issubset(_operation_ids("openbabel"))
    assert all(
        not profile.low_level_mcp_exposed
        for adapter in adapters.values()
        for profile in adapter.operation_profiles
    )


def test_phase17_smoke_results_align_with_adapter_metadata() -> None:
    adapters = list_adapter_metadata()
    smoke = list_optional_smoke_results()
    for backend in ["ase", "rdkit", "openbabel", "xtb"]:
        assert backend in smoke
        assert smoke[backend].smoke_execution == adapters[backend].availability.smoke_execution
        if smoke[backend].status == "unavailable":
            assert smoke[backend].unavailable_reason


def test_phase17_artifact_contract_boundaries() -> None:
    contracts = export_artifact_registry(compact=False)["artifact_contracts"]
    assert contracts["xtb_singlepoint_result"]["geometry_modified"] is False
    assert contracts["xtb_singlepoint_result"]["geometry_role"] == "non_geometry"
    assert contracts["xtb_relax_result"]["geometry_modified"] is False
    assert contracts["relaxed_xyz"]["geometry_modified"] is True
    assert contracts["geometry_analysis_report"]["geometry_modified"] is False
    assert contracts["rdkit_descriptor_table"]["geometry_modified"] is False
    assert contracts["conformer_ensemble"]["geometry_modified"] is True
    assert contracts["converted_structure"]["geometry_modified"] is False
    assert contracts["openbabel_conversion_report"]["geometry_modified"] is False


def test_phase17_parameter_binding_existing_tool_controls() -> None:
    single = create_dry_run_execution_plan(
        "Run an xTB single point for examples/water.xyz with charge -1 and multiplicity 2 in water using ALPB. Do not optimize geometry.",
        language="en",
    )
    single_names = {item["name"] for item in single["parameter_bindings"]}
    assert single["selected_workflow"]["workflow_id"] == "xyz_to_xtb_singlepoint"
    assert single["selected_workflow"]["geometry_modified"] is False
    assert {"charge", "multiplicity", "solvent.name", "solvent.model"}.issubset(single_names)

    relax = create_dry_run_execution_plan(
        "Relax examples/water.xyz with xTB using max 25 steps and force threshold 0.05.",
        language="en",
    )
    relax_names = {item["name"] for item in relax["parameter_bindings"]}
    assert relax["selected_workflow"]["workflow_id"] == "xyz_to_xtb_relax"
    assert relax["selected_workflow"]["geometry_modified"] is True
    assert {
        "geometry_optimization_controls.max_steps",
        "geometry_optimization_controls.force_threshold",
    }.issubset(relax_names)


def test_phase17_eval_cases_pass() -> None:
    result = run_phase17_existing_tool_depth_eval(CASES, backend="mock")
    assert result["status"] == "ok"
    assert result["pass_rate"] == 1.0
    assert result["adapter_metadata_pass_rate"] == 1.0
    assert result["parameter_binding_pass_rate"] == 1.0
    assert result["artifact_contract_pass_rate"] == 1.0
    assert result["smoke_consistency_pass_rate"] == 1.0
    assert result["safety_pass_rate"] == 1.0
    assert result["unsafe_execution_attempt_rate"] == 0.0
    assert result["result_artifact_as_geometry_error_rate"] == 0.0
    assert result["low_level_tool_exposure_rate"] == 0.0
    assert result["forced_selection_on_ambiguous_prompt_rate"] == 0.0


def test_phase17_cli_eval_existing_tools_uses_phase17_metrics() -> None:
    result = runner.invoke(
        app,
        ["workflow", "eval-existing-tools", CASES, "--backend", "mock", "--format", "json"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "lmola.phase17_existing_tool_depth_eval.v1"
    assert payload["adapter_metadata_pass_rate"] == 1.0


def test_phase17_backend_adapter_cli_is_read_only() -> None:
    listed = runner.invoke(app, ["backends", "list-adapters", "--format", "json"])
    assert listed.exit_code == 0
    payload = json.loads(listed.stdout)
    assert "xtb" in payload
    assert "operation_profiles" in payload["xtb"]

    smoke = runner.invoke(app, ["backends", "smoke", "--backend", "rdkit", "--format", "json"])
    assert smoke.exit_code == 0
    smoke_payload = json.loads(smoke.stdout)
    assert smoke_payload["backend_id"] == "rdkit"
    assert smoke_payload["status"] in {"available", "unavailable"}


def test_phase17_schema_exports_adapter_metadata() -> None:
    schemas = export_all_schemas()
    assert "adapter_metadata_schema" in schemas
    assert "adapter_operation_profile_schema" in schemas
    assert "adapter_metadata" in schemas
    planner = export_planner_schema_bundle()
    assert "adapter_metadata" in planner
    assert "xtb" in planner["adapter_metadata"]


def test_phase17_low_level_mcp_tools_remain_hidden_and_gates_preserved() -> None:
    names = {tool["name"] for tool in list_mcp_tools_runtime()}
    forbidden = {
        "lmola.xtb_singlepoint",
        "lmola.relax_structure_xtb",
        "lmola.validate_structure_ase",
        "lmola.analyze_geometry_ase",
        "lmola.generate_small_molecule_openbabel",
        "lmola.generate_small_molecule_rdkit",
        "lmola.compute_rdkit_descriptors",
    }
    assert forbidden.isdisjoint(names)

    no_allow = call_mcp_tool(
        "lmola.run_workflow",
        {
            "workflow_id": "xyz_to_xtb_relax",
            "input": {"type": "xyz", "path": "examples/water.xyz"},
            "dry_run": False,
            "confirm": True,
        },
    )
    assert no_allow["status"] == "error"
    assert no_allow["error_type"] == "execution_not_allowed"
