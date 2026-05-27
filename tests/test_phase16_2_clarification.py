from lmola.clarification import generate_clarification_plan, run_clarification_eval
from lmola.mcp_runtime import call_mcp_tool, list_mcp_tools_runtime
from lmola.schema_export import export_all_schemas


def test_clarification_ambiguous_xtb_required_question():
    out = generate_clarification_plan(prompt="Run an xTB calculation for examples/mol.xyz.", language="en")
    assert out["status"] == "needs_clarification"
    assert out["can_execute"] is False
    assert out["safety"]["execution_allowed"] is False
    assert out["required_questions"]


def test_schema_export_contains_clarification_schemas():
    out = export_all_schemas()
    assert "clarification_question_schema" in out
    assert "clarification_plan_schema" in out
    assert "clarification_eval_schema" in out


def test_mcp_runtime_has_clarification_tool():
    names = {t["name"] for t in list_mcp_tools_runtime()}
    assert "lmola.generate_clarification_plan" in names
    out = call_mcp_tool("lmola.generate_clarification_plan", {"prompt": "Run an xTB calculation for examples/mol.xyz."})
    assert out["can_execute"] is False


def test_eval_clarifications_mock_cases():
    out = run_clarification_eval("examples/phase16_2_clarification_cases.yaml", backend="mock")
    assert out["total_cases"] >= 18
