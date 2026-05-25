from pathlib import Path
from typer.testing import CliRunner
from lmola.cli import app
from lmola.mcp_runtime import call_mcp_tool

runner = CliRunner()

def test_export_llm_catalog_cli():
    r = runner.invoke(app, ["workflow", "export-llm-catalog", "--format", "json"])
    assert r.exit_code == 0
    assert '"status": "ok"' in r.stdout


def test_recommend_next_actions_mcp():
    d = Path("outputs/test_phase15_3")
    d.mkdir(parents=True, exist_ok=True)
    p = d / "artifact_manifest.json"
    p.write_text('{"schema_version":"lmola.artifact_manifest.v1","manifest_kind":"batch","root_path":"x","status":"ok","artifacts":[{"artifact_id":"a1","artifact_type":"xtb_singlepoint_result","path":"artifact_0.json","scope":"batch","status":"ok"}],"next_compatible_workflows":[],"warnings":[]}', encoding='utf-8')
    out = call_mcp_tool("lmola.recommend_next_actions", {"path": str(p)})
    assert out["status"] == "ok"
    assert out["recommended_next_actions"][0]["execution_allowed"] is False
