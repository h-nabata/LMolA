from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from lmola.artifact_summary import summarize_artifact_path
from lmola.cli import app
from lmola.mcp_runtime import call_mcp_tool, list_mcp_tools_runtime


def test_summarize_mcp_audit_and_unsafe_path(tmp_path: Path) -> None:
    out = Path("outputs/mcp_audit")
    out.mkdir(parents=True, exist_ok=True)
    p = out / "mcp_run_test.json"
    p.write_text(json.dumps({"tool": "lmola.run_workflow", "workflow_id": "smiles_to_xtb_relax", "dry_run": True, "executed": False, "execution_allowed": False, "canonical_workflow_json": {"steps": [{"tool": "generate_small_molecule_rdkit"}]}}), encoding="utf-8")
    s = summarize_artifact_path(p)
    assert s["status"] == "ok"
    assert s["artifact_kind"] == "mcp_audit"
    assert s["executed"] is False
    assert "Review canonical workflow" in " ".join(s["next_recommended_actions"])
    bad = summarize_artifact_path("/etc/passwd")
    assert bad["status"] == "error"
    assert bad["error_type"] == "unsafe_path"


def test_summarize_batch_and_truncation() -> None:
    b = Path("outputs/batch_test")
    b.mkdir(parents=True, exist_ok=True)
    (b / "summary.csv").write_text("item_id,status\n1,ok\n2,error\n", encoding="utf-8")
    (b / "run.log").write_text("abcdef" * 1000, encoding="utf-8")
    s = summarize_artifact_path(b, max_items=1, max_text_chars=20)
    assert s["artifact_kind"] == "batch_dir"
    assert len(s["items"]) == 1
    assert len(s["run_log_excerpt"]) <= 20


def test_summarize_batch_with_null_steps_and_mcp_tool() -> None:
    b = Path("outputs/batch_null_steps")
    b.mkdir(parents=True, exist_ok=True)
    (b / "summary.csv").write_text("item_id,status\n1,ok\n", encoding="utf-8")
    (b / "normalized_workflow.json").write_text(json.dumps({"workflow_id": "smiles_to_xtb_relax", "steps": None}), encoding="utf-8")
    payload = summarize_artifact_path(b)
    assert payload["status"] == "ok"
    assert payload["artifact_kind"] == "batch_dir"
    assert payload["canonical_tools"] == ["generate_small_molecule_rdkit", "validate_structure_ase", "relax_structure_xtb"]
    assert any("inferred from workflow catalog" in w for w in payload["warnings"])
    mcp_payload = call_mcp_tool("lmola.summarize_artifacts", {"path": str(b)})
    assert mcp_payload["status"] == "ok"
    assert mcp_payload["canonical_tools"] == ["generate_small_molecule_rdkit", "validate_structure_ase", "relax_structure_xtb"]


def test_batch_next_actions_success_vs_error() -> None:
    ok = Path("outputs/batch_next_ok")
    ok.mkdir(parents=True, exist_ok=True)
    (ok / "summary.csv").write_text("item_id,status\n1,ok\n", encoding="utf-8")
    ok_payload = summarize_artifact_path(ok)
    assert "summary.csv" in " ".join(ok_payload["next_recommended_actions"])
    err = Path("outputs/batch_next_error")
    err.mkdir(parents=True, exist_ok=True)
    (err / "summary.csv").write_text("item_id,status\n1,error\n", encoding="utf-8")
    err_payload = summarize_artifact_path(err)
    assert "failed_items" in " ".join(err_payload["next_recommended_actions"])


def test_cli_and_mcp_tool() -> None:
    d = Path("outputs/agent_smoke_test")
    d.mkdir(parents=True, exist_ok=True)
    (d / "agent_smoke_result.json").write_text(json.dumps({"backend": "mock", "model": "", "task": "x", "checks": {}}), encoding="utf-8")
    (d / "tool_selection_final.json").write_text(json.dumps({"tool_name": "lmola.run_workflow", "arguments": {"workflow_id": "smiles_to_xtb_relax"}}), encoding="utf-8")
    (d / "result_analysis_parsed.json").write_text(json.dumps({"execution_mode": "dry_run", "canonical_tools": []}), encoding="utf-8")
    (d / "mcp_tool_call_response.json").write_text(json.dumps({}), encoding="utf-8")
    runner = CliRunner()
    res = runner.invoke(app, ["artifacts", "summarize", str(d), "--format", "json"])
    assert res.exit_code == 0
    payload = json.loads(res.stdout)
    assert payload["artifact_kind"] == "agent_smoke_dir"
    names = {t["name"] for t in list_mcp_tools_runtime()}
    assert "lmola.summarize_artifacts" in names
    out = call_mcp_tool("lmola.summarize_artifacts", {"path": str(d)})
    assert out["status"] == "ok"
    bad = call_mcp_tool("lmola.summarize_artifacts", {"path": "/etc/passwd"})
    assert bad["status"] == "error"
