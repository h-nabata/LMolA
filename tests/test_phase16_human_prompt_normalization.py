from typer.testing import CliRunner

from lmola.cli import app
from lmola.human_prompt_normalization import normalize_human_prompt
from lmola.mcp_runtime import call_mcp_tool, list_mcp_tools_runtime
from lmola.schema_export import export_all_schemas


def test_normalize_human_prompt_safety_and_artifact_non_geometry():
    out = normalize_human_prompt(prompt="continue optimization from this singlepoint result", language="en")
    assert out["status"] == "needs_clarification"
    assert out["safety"]["execution_allowed"] is False
    assert out["safety"]["dry_run_recommended"] is True
    assert "xyz_to_xtb_relax" not in [w["workflow_id"] for w in out["candidate_workflows"]]


def test_eval_human_prompts_cli_mock():
    r = CliRunner().invoke(app, ["workflow", "eval-human-prompts", "examples/phase16_0_human_prompt_normalization_cases.yaml", "--backend", "mock", "--format", "json"])
    assert r.exit_code == 0
    assert '"status": "ok"' in r.stdout
    assert '"pass_rate": 1.0' in r.stdout


def test_mcp_human_prompt_normalization_smoke_cli_mock():
    r = CliRunner().invoke(app, ["mcp", "human-prompt-normalization-smoke", "--backend", "mock", "--format", "json"])
    assert r.exit_code == 0
    assert '"status": "ok"' in r.stdout


def test_mcp_runtime_normalize_human_prompt_tool_and_schema_export_entries():
    names = {t["name"] for t in list_mcp_tools_runtime()}
    assert "lmola.normalize_human_prompt" in names
    out = call_mcp_tool("lmola.normalize_human_prompt", {"prompt": "xTB calculation", "language": "en"})
    assert out["safety"]["execution_allowed"] is False
    bundle = export_all_schemas()
    assert "human_prompt_normalized_intent_schema" in bundle
    assert "human_prompt_normalization_eval_schema" in bundle
