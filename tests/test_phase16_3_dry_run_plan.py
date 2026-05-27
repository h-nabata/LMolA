from lmola.dry_run_plan import create_dry_run_execution_plan, run_dry_run_plan_eval
from lmola.mcp_runtime import call_mcp_tool, list_mcp_tools_runtime
from lmola.schema_export import export_all_schemas


def test_dry_run_plan_xtb_singlepoint_safety():
    out = create_dry_run_execution_plan(prompt="Run an xTB single point for examples/water.xyz with charge 0 and multiplicity 1. Do not optimize geometry.", language="en")
    assert out["status"] == "ok"
    assert out["selected_workflow"]["workflow_id"] == "xyz_to_xtb_singlepoint"
    assert out["can_execute"] is False
    assert out["safety"]["execution_allowed"] is False


def test_schema_export_contains_dry_run_schemas():
    out = export_all_schemas()
    for k in [
        "dry_run_input_binding_schema",
        "dry_run_parameter_binding_schema",
        "dry_run_expected_artifact_schema",
        "dry_run_workflow_selection_schema",
        "dry_run_execution_plan_schema",
        "dry_run_plan_eval_schema",
    ]:
        assert k in out


def test_mcp_runtime_has_dry_run_plan_tool():
    names = {t["name"] for t in list_mcp_tools_runtime()}
    assert "lmola.create_dry_run_execution_plan" in names
    out = call_mcp_tool("lmola.create_dry_run_execution_plan", {"prompt": "Run an xTB single point for examples/water.xyz with charge 0 and multiplicity 1."})
    assert out["can_execute"] is False


def test_eval_dry_run_cases_mock():
    out = run_dry_run_plan_eval("examples/phase16_3_dry_run_plan_cases.yaml", backend="mock")
    assert out["status"] == "ok"
