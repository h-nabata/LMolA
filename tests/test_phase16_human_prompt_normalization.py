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


def test_direct_mcp_ja_singlepoint_no_opt_consistent():
    prompt = "examples/example.xyz に対してxTB単一点エネルギー計算を行ってください。構造最適化は行わず、入力構造を変更しないでください。"
    out = call_mcp_tool("lmola.normalize_human_prompt", {"prompt": prompt, "language": "ja", "compact": False})
    assert out["status"] == "ok"
    assert out["normalized_intent"]["operation"] == "singlepoint_energy"
    assert out["normalized_intent"]["method_family"] == "semiempirical"
    assert out["normalized_intent"]["requested_backend"] == "xtb"
    assert out["normalized_intent"]["input_kind"] == "xyz"
    assert out["normalized_intent"]["geometry_modification_allowed"] is False
    assert "do_not_optimize_geometry" in out["normalized_intent"]["constraints"]
    cands = [c["workflow_id"] for c in out["candidate_workflows"]]
    assert "xyz_to_xtb_singlepoint" in cands
    assert "xyz_to_xtb_relax" not in cands


def test_direct_mcp_en_singlepoint_no_opt_consistent():
    out = call_mcp_tool("lmola.normalize_human_prompt", {"prompt": "Run singlepoint xTB for examples/example.xyz without optimization.", "language": "en"})
    assert out["status"] == "ok"
    assert out["normalized_intent"]["operation"] == "singlepoint_energy"


def test_japanese_nitaisite_not_structure_comparison_by_itself():
    out = normalize_human_prompt(prompt="examples/example.xyz に対してxTB計算してください", language="ja")
    assert out["normalized_intent"]["operation"] != "structure_comparison"


def test_structure_comparison_requires_explicit_compare_wording():
    ambiguous = normalize_human_prompt(prompt="a.xyz と b.xyz を処理して", language="ja")
    assert ambiguous["normalized_intent"]["operation"] != "structure_comparison"
    explicit = normalize_human_prompt(prompt="a.xyz と b.xyz を比較", language="ja")
    assert explicit["normalized_intent"]["operation"] == "structure_comparison"


def test_generic_xtb_prompt_remains_ambiguous():
    out = call_mcp_tool("lmola.normalize_human_prompt", {"prompt": "xTB calculation", "language": "en"})
    assert out["status"] in {"ambiguous", "needs_clarification"}


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
