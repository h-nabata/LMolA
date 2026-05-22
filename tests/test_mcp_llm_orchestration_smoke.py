from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from lmola.cli import app


def _run(*args: str):
    return CliRunner().invoke(app, ["mcp", "llm-orchestration-smoke", *args])


def test_orchestration_command_exists() -> None:
    res = _run("--help")
    assert res.exit_code == 0
    assert "--execute-safe" in res.stdout


def test_orchestration_mock_execute_safe_ok_and_files() -> None:
    res = _run("--backend", "mock", "--execute-safe", "--format", "json")
    assert res.exit_code == 0
    payload = json.loads(res.stdout)
    assert payload["status"] == "ok"
    assert payload["phase"] == "13.7_multi_step_llm_tool_orchestration_smoke"
    by_case = {c["case_id"]: c for c in payload["case_results"]}
    assert by_case["geometry_then_relax_dry_run"]["next_workflow_executed"] is False
    assert by_case["unavailable_backend_stop"]["executed"] is False
    assert by_case["unsupported_research_task_stop"]["executed"] is False
    assert by_case["geometry_then_relax_dry_run"]["second_step_decision_ok"] is True
    smoke_dir = Path(payload["smoke_dir"])
    for case_id in by_case:
        cdir = smoke_dir / "cases" / case_id
        for fname in [
            "initial_raw_llm_response.txt",
            "initial_sanitized_llm_response.txt",
            "initial_parsed_output.json",
            "initial_normalized_output.json",
            "second_step_prompt.txt",
            "second_step_raw_llm_response.txt",
            "second_step_sanitized_llm_response.txt",
            "second_step_decision.json",
            "case_result.json",
        ]:
            assert (cdir / fname).exists()


def test_execute_next_true_is_normalized_false() -> None:
    res = _run("--backend", "mock", "--execute-safe", "--format", "json")
    payload = json.loads(res.stdout)
    smoke_dir = Path(payload["smoke_dir"])
    d = json.loads((smoke_dir / "cases" / "geometry_then_relax_dry_run" / "second_step_decision.json").read_text())
    assert d["execute_next"] is False
