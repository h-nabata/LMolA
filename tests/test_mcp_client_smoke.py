from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from lmola.cli import app
from lmola.mcp_client_smoke import run_mcp_client_smoke

runner = CliRunner()


def test_client_smoke_helper_end_to_end() -> None:
    result = run_mcp_client_smoke(timeout_seconds=10)
    assert result["status"] == "ok"
    assert result["checks"]["initialize_ok"] is True
    assert result["checks"]["tools_list_ok"] is True
    assert result["checks"]["run_workflow_present"] is True
    assert result["checks"]["low_level_tools_absent"] is True
    assert result["checks"]["validate_workflow_ok"] is True
    assert result["checks"]["run_workflow_dry_run_safe"] is True
    assert result["checks"]["confirmation_required_ok"] is True
    assert result["checks"]["unknown_tool_handled"] is True
    assert result["checks"]["mcp_runs_unchanged"] is True
    assert result["mcp_runs_before"] == result["mcp_runs_after"]


def test_client_smoke_cli_json() -> None:
    out = Path("/tmp/lmola_mcp_client_smoke_test.json")
    res = runner.invoke(app, ["mcp", "client-smoke", "--format", "json"])
    assert res.exit_code == 0
    payload = json.loads(res.stdout)
    out.write_text(res.stdout, encoding="utf-8")
    assert payload["status"] == "ok"


def test_claude_desktop_config_example_json_valid() -> None:
    payload = json.loads(Path("docs/mcp/claude_desktop_config.example.json").read_text(encoding="utf-8"))
    assert "mcpServers" in payload
    assert "lmola" in payload["mcpServers"]
