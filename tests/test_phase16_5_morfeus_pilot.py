from __future__ import annotations

import importlib.util

import pytest

from lmola.artifact_contracts import export_artifact_registry
from lmola.dry_run_plan import create_dry_run_execution_plan, run_morfeus_pilot_eval
from lmola.schema_export import export_all_schemas
from lmola.workflows.catalog import WORKFLOW_CATALOG

CASES = "examples/phase16_5_morfeus_pilot_cases.yaml"


def test_morfeus_pilot_mock_eval_passes() -> None:
    result = run_morfeus_pilot_eval(CASES, backend="mock")
    assert result["status"] == "ok"
    assert result["passed_cases"] == 18
    assert result["pass_rate"] == 1.0
    assert result["low_level_tool_exposure_rate"] == 0.0


def test_complete_morfeus_prompts_select_high_level_workflows() -> None:
    cases = {
        "Calculate buried volume around Ni in examples/complex.xyz using morfeus.": "xyz_to_morfeus_buried_volume",
        "Calculate the Morfeus cone angle for examples/complex.xyz using metal atom 1 and ligand atoms 2-7.": "xyz_to_morfeus_cone_angle",
        "Calculate Morfeus Sterimol parameters for examples/complex.xyz along bond atoms 1 and 4 using substituent atoms 4-12.": "xyz_to_morfeus_sterimol",
    }
    for prompt, workflow_id in cases.items():
        plan = create_dry_run_execution_plan(prompt)
        assert plan["status"] == "ok"
        assert plan["selected_workflow"]["workflow_id"] == workflow_id
        assert plan["can_execute"] is False
        assert plan["safety"]["execution_allowed"] is False


def test_morfeus_reports_are_not_geometry_contracts() -> None:
    registry = export_artifact_registry(compact=False)["artifact_contracts"]
    for artifact_type in ["morfeus_buried_volume_report", "morfeus_cone_angle_report", "morfeus_sterimol_report"]:
        contract = registry[artifact_type]
        assert contract["category"] == "report"
        assert contract["geometry_role"] == "non_geometry"
        assert contract["geometry_modified"] is False
        assert "primary_structure" not in contract["compatible_input_data_types"]


def test_morfeus_schema_export_contains_phase16_5_contracts() -> None:
    payload = export_all_schemas()
    text = str(payload)
    for token in [
        "lmola.morfeus_pilot_eval.v1",
        "morfeus_pilot_core_v1",
        "xyz_to_morfeus_buried_volume",
        "xyz_to_morfeus_cone_angle",
        "xyz_to_morfeus_sterimol",
        "morfeus_buried_volume_report",
        "morfeus_cone_angle_report",
        "morfeus_sterimol_report",
        "steric_descriptor_calculation",
        "buried_volume",
        "cone_angle",
        "sterimol",
    ]:
        assert token in text


def test_no_low_level_morfeus_runtime_workflows() -> None:
    forbidden = {
        "lmola.morfeus_buried_volume",
        "lmola.morfeus_cone_angle",
        "lmola.morfeus_sterimol",
        "lmola.calculate_buried_volume_morfeus",
        "lmola.calculate_cone_angle_morfeus",
        "lmola.calculate_sterimol_morfeus",
    }
    assert forbidden.isdisjoint(WORKFLOW_CATALOG)


@pytest.mark.external_tools
def test_optional_morfeus_import_smoke() -> None:
    if importlib.util.find_spec("morfeus") is None:
        pytest.skip("morfeus is not installed in this optional external-tools environment")
    import morfeus  # noqa: F401
