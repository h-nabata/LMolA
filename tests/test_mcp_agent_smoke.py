from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from lmola.cli import app
from lmola.mcp_agent_smoke import run_mcp_agent_smoke

runner = CliRunner()


def test_agent_smoke_mock_end_to_end() -> None:
    result = run_mcp_agent_smoke(backend="mock")
    assert result["status"] == "ok"
    assert result["checks"]["initialize_ok"] is True
    assert result["checks"]["tools_list_ok"] is True
    assert result["checks"]["low_level_tools_absent"] is True
    assert result["checks"]["run_workflow_dry_run_safe"] is True
    assert result["checks"]["mcp_runs_unchanged"] is True

    smoke_dir = Path(result["agent_smoke_dir"])
    assert (smoke_dir / "agent_smoke_result.json").exists()
    assert (smoke_dir / "agent_smoke_transcript.json").exists()
    assert (smoke_dir / "tool_selection_parsed.json").exists()
    parsed = json.loads((smoke_dir / "tool_selection_parsed.json").read_text(encoding="utf-8"))
    assert parsed["tool_name"] == "lmola.run_workflow"
    assert parsed["arguments"]["dry_run"] is True


def test_agent_smoke_cli_mock_json() -> None:
    res = runner.invoke(app, ["mcp", "agent-smoke", "--backend", "mock", "--format", "json"])
    assert res.exit_code == 0
    payload = json.loads(res.stdout)
    assert payload["status"] == "ok"


def test_agent_smoke_rejects_unsafe_call() -> None:
    from lmola.mcp_agent_smoke import validate_agent_tool_call

    ok, err, _ = validate_agent_tool_call(
        parsed={"tool_name": "lmola.generate_small_molecule_rdkit", "arguments": {}},
        runtime_tool_names={"lmola.run_workflow", "lmola.plan_workflow"},
        allow_confirmed_execution=False,
        confirm_execution=False,
    )
    assert ok is False
    assert err == "unsafe_tool_call"


def test_agent_smoke_rejects_dry_run_false_default() -> None:
    from lmola.mcp_agent_smoke import validate_agent_tool_call

    ok, err, _ = validate_agent_tool_call(
        parsed={"tool_name": "lmola.run_workflow", "arguments": {"dry_run": False}},
        runtime_tool_names={"lmola.run_workflow", "lmola.plan_workflow"},
        allow_confirmed_execution=False,
        confirm_execution=False,
    )
    assert ok is False
    assert err == "unsafe_tool_call"
