from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from lmola.artifact_triage import triage_artifact_path
from lmola.cli import app
from lmola.mcp_runtime import call_mcp_tool, list_mcp_tools_runtime


def _mk_batch_json(name: str, rows: list[dict[str, str]] | dict[str, object], *, workflow_error_count: int | None = None) -> Path:
    d = Path("outputs") / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "summary.json").write_text(json.dumps(rows), encoding="utf-8")
    if workflow_error_count is not None:
        (d / "workflow_result.json").write_text(json.dumps({"error_count": workflow_error_count}), encoding="utf-8")
    return d


def _mk_batch_csv(name: str, csv_text: str, *, workflow_error_count: int | None = None) -> Path:
    d = Path("outputs") / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "summary.csv").write_text(csv_text, encoding="utf-8")
    if workflow_error_count is not None:
        (d / "workflow_result.json").write_text(json.dumps({"error_count": workflow_error_count}), encoding="utf-8")
    return d


def test_batch_step_classification_json_list_and_csv() -> None:
    ok = _mk_batch_json("batch_triage_ok", [{"item_id": "1", "status": "ok"}])
    assert triage_artifact_path(ok)["has_failure"] is False

    v = _mk_batch_json("batch_triage_val", [{"item_id": "1", "validation_status": "ERROR", "error_message": "val failed"}])
    assert triage_artifact_path(v)["failure_category"] == "validation_failure"

    g = _mk_batch_json("batch_triage_gen", [{"item_id": "1", "generate_status": "failed", "error_message": "gen failed"}])
    assert triage_artifact_path(g)["failure_category"] == "generation_failure"

    r = _mk_batch_csv("batch_triage_relax", "item_id,relax_status,error_message\n1,fail,xtb unavailable\n")
    assert triage_artifact_path(r)["failure_category"] == "relaxation_failure"


def test_batch_partial_and_workflow_error_fallback() -> None:
    mixed = _mk_batch_json(
        "batch_triage_mixed",
        {"items": [{"item_id": "1", "generate_status": "error", "relax_status": "error", "error_message": "two-step failure"}]},
    )
    out = triage_artifact_path(mixed)
    assert out["failure_category"] == "partial_batch_failure"
    assert set(out["failed_steps"]) == {"generate", "relax"}

    fallback = _mk_batch_json("batch_triage_fallback", {"error_count": 1}, workflow_error_count=1)
    out2 = triage_artifact_path(fallback)
    assert out2["has_failure"] is True
    assert out2["failure_category"] == "unknown_failure"
    assert any(ev.get("source") == "workflow_result.json" for ev in out2["evidence"])


def test_summary_json_list_only_and_summary_csv_only() -> None:
    list_only = _mk_batch_json("batch_triage_list_only", [{"item_id": "a", "failed_step": "validation", "error_message": "invalid"}])
    assert triage_artifact_path(list_only)["failure_category"] == "validation_failure"

    csv_only = _mk_batch_csv("batch_triage_csv_only", "item_id,generate_status,error_message\n4,error,gen boom\n")
    assert triage_artifact_path(csv_only)["failure_category"] == "generation_failure"


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
    b = _mk_batch_json("batch_triage_mcp", [{"item_id": "1", "status": "ok"}])
    ok = call_mcp_tool("lmola.triage_artifacts", {"path": str(b)})
    assert ok["status"] == "ok"
    bad = call_mcp_tool("lmola.triage_artifacts", {"path": "/etc/passwd"})
    assert bad["status"] == "error"
