from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from lmola.artifact_triage import triage_artifact_path
from lmola.cli import app
from lmola.mcp_runtime import call_mcp_tool, list_mcp_tools_runtime


def _mk_batch(name: str, rows: list[dict[str, str]]) -> Path:
    d = Path("outputs") / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "summary.json").write_text(json.dumps({"items": rows}), encoding="utf-8")
    return d


def test_batch_success_and_failures() -> None:
    ok = _mk_batch("batch_triage_ok", [{"item_id": "1", "status": "ok"}])
    assert triage_artifact_path(ok)["has_failure"] is False
    v = _mk_batch("batch_triage_val", [{"item_id": "1", "status": "error", "validation_status": "error", "error_message": "val failed"}])
    assert triage_artifact_path(v)["failure_category"] == "validation_failure"
    r = _mk_batch("batch_triage_relax", [{"item_id": "1", "status": "error", "relax_status": "error", "error_message": "xtb backend unavailable"}])
    assert triage_artifact_path(r)["failure_category"] in {"relaxation_failure", "partial_batch_failure"}
    g = _mk_batch("batch_triage_gen", [{"item_id": "1", "status": "error", "generate_status": "error", "error_message": "gen failed"}])
    assert triage_artifact_path(g)["failure_category"] == "generation_failure"


def test_mcp_audit_and_plan_and_cli() -> None:
    audit = Path("outputs/mcp_audit/mcp_run_triage.json")
    audit.parent.mkdir(parents=True, exist_ok=True)
    audit.write_text(json.dumps({"tool": "lmola.run_workflow", "dry_run": False, "executed": False, "error_type": "confirmation_required", "message": "need confirm"}), encoding="utf-8")
    assert triage_artifact_path(audit)["failure_category"] == "safety_rejection"
    plan = Path("outputs/plan_triage")
    plan.mkdir(parents=True, exist_ok=True)
    (plan / "planning_result.json").write_text(json.dumps({"validation_errors": [], "parsed_workflow": {"status": "unsupported"}}), encoding="utf-8")
    out = triage_artifact_path(plan)
    assert out["failure_category"] == "unsupported_task"
    runner = CliRunner()
    res = runner.invoke(app, ["artifacts", "triage", str(audit), "--format", "json"])
    assert res.exit_code == 0


def test_mcp_runtime_tool_and_unsafe_path() -> None:
    names = {t["name"] for t in list_mcp_tools_runtime()}
    assert "lmola.triage_artifacts" in names
    b = _mk_batch("batch_triage_mcp", [{"item_id": "1", "status": "ok"}])
    ok = call_mcp_tool("lmola.triage_artifacts", {"path": str(b)})
    assert ok["status"] == "ok"
    bad = call_mcp_tool("lmola.triage_artifacts", {"path": "/etc/passwd"})
    assert bad["status"] == "error"
