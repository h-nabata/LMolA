from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from lmola.cli import app


def _run(*args: str):
    runner = CliRunner()
    return runner.invoke(app, ["mcp", "llm-execution-smoke", *args])


def test_llm_execution_smoke_exists() -> None:
    res = _run("--help")
    assert res.exit_code == 0
    assert "--execute-safe" in res.stdout


def test_mock_llm_execution_smoke_execute_safe_and_aliases() -> None:
    res = _run("--backend", "mock", "--execute-safe", "--format", "json")
    assert res.exit_code == 0
    payload = json.loads(res.stdout)
    assert payload["status"] == "ok"
    assert "descriptor" in payload["executed_case_ids"]
    assert "geometry" in payload["executed_case_ids"]
    assert "descriptor" not in payload["skipped_execution_case_ids"]
    assert "geometry" not in payload["skipped_execution_case_ids"]
    assert "xtb" in payload["skipped_execution_case_ids"]
    assert payload["case_id_aliases"]["descriptor_request"] == "descriptor"
    assert payload["case_id_aliases"]["geometry_request"] == "geometry"
    smoke_dir = Path(payload["smoke_dir"])
    assert (smoke_dir / "cases" / "descriptor").exists()
    assert (smoke_dir / "cases" / "geometry").exists()
    checks = payload["checks"]
    for key in [
        "descriptor_selected_ok",
        "descriptor_dry_run_ok",
        "descriptor_confirmed_execution_ok",
        "descriptor_artifact_summary_ok",
        "geometry_selected_ok",
        "geometry_dry_run_ok",
        "geometry_confirmed_execution_ok",
        "geometry_artifact_summary_ok",
        "xtb_not_confirmed_by_smoke",
        "molsimplify_not_executed",
        "unsupported_not_executed",
        "no_hallucinated_workflow_id",
        "no_backend_constraint_violation",
        "no_unavailable_backend_selected",
        "low_level_tools_absent",
        "tools_list_ok",
    ]:
        assert key in checks
        assert checks[key] is True
    for case_id in ("descriptor", "geometry"):
        case_dir = smoke_dir / "cases" / case_id
        assert (case_dir / "mcp_dry_run_response.json").exists()
        assert (case_dir / "mcp_confirmed_execution_response.json").exists()
        assert (case_dir / "artifact_summary.json").exists()
        assert (case_dir / "artifact_triage.json").exists()
        assert (case_dir / "case_result.json").exists()


def test_qwen_geometry_normalization_repair() -> None:
    from lmola.mcp_llm_execution_smoke import _normalize_selection

    parsed, *_ = _normalize_selection({"status": "ok", "workflow_id": "weird_id"}, "xyz_to_geometry_analysis", "ok")
    assert parsed["status"] == "ok"
    assert parsed["workflow_id"] == "xyz_to_geometry_analysis"


def test_molsimplify_normalized_backend_unavailable() -> None:
    res = _run("--backend", "mock", "--format", "json")
    payload = json.loads(res.stdout)
    by_case = {row["case_id"]: row for row in payload["case_results"]}
    assert by_case["molsimplify"]["normalized_status"] == "backend_unavailable"
    assert by_case["molsimplify"]["selected_workflow_id"] is None


def test_confirmed_execution_smoke_alias_keys_stable() -> None:
    runner = CliRunner()
    res = runner.invoke(app, ["mcp", "confirmed-execution-smoke", "--format", "json"])
    assert res.exit_code == 0
    assert "dry_run_no_execution" in res.stdout
    assert "descriptor_confirmed_execution_ok" in res.stdout
    assert "geometry_confirmed_execution_ok" in res.stdout
