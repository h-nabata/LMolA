from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from lmola.mcp_runtime import encode_content_length_message, read_content_length_message

DEFAULT_SERVER_COMMAND = [sys.executable, "-c", "from lmola.cli import app; app(['mcp','serve-stdio'])"]
_WORKFLOW_ARGS = {
    "workflow_id": "smiles_to_xtb_relax",
    "input": {"type": "smiles_csv", "path": "examples/smiles_list.csv"},
    "columns": {"id": "id", "smiles": "smiles"},
}
_LOW_LEVEL_TOOL_NAMES = {"lmola.relax_structure_xtb", "lmola.generate_small_molecule_rdkit"}


def _count_mcp_run_batches() -> int:
    root = Path("outputs/mcp_runs")
    return len(list(root.glob("batch_*"))) if root.exists() else 0


def _rpc(req_id: int, method: str, params: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}


def run_mcp_client_smoke(*, timeout_seconds: float = 10.0, server_command: list[str] | None = None) -> dict[str, Any]:
    command = server_command or DEFAULT_SERVER_COMMAND
    requests = [
        _rpc(1, "initialize", {}),
        _rpc(2, "tools/list", {}),
        _rpc(3, "tools/call", {"name": "lmola.list_workflows", "arguments": {"compact": True}}),
        _rpc(4, "tools/call", {"name": "lmola.validate_workflow", "arguments": _WORKFLOW_ARGS}),
        _rpc(5, "tools/call", {"name": "lmola.run_workflow", "arguments": _WORKFLOW_ARGS}),
        _rpc(6, "tools/call", {"name": "lmola.run_workflow", "arguments": {**_WORKFLOW_ARGS, "dry_run": False, "allow_execution": True}}),
        _rpc(7, "tools/call", {"name": "lmola.nonexistent_tool", "arguments": {}}),
    ]
    responses: list[dict[str, Any]] = []
    checks = {
        "initialize_ok": False,
        "tools_list_ok": False,
        "run_workflow_present": False,
        "low_level_tools_absent": False,
        "validate_workflow_ok": False,
        "run_workflow_dry_run_safe": False,
        "confirmation_required_ok": False,
        "unknown_tool_handled": False,
        "mcp_runs_unchanged": False,
    }
    before = _count_mcp_run_batches()

    env = os.environ.copy()
    src_path = str(Path(__file__).resolve().parents[2] / "src")
    env["PYTHONPATH"] = src_path + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, cwd=str(Path(__file__).resolve().parents[2]))  # noqa: S603
    try:
        assert proc.stdin is not None and proc.stdout is not None
        for req in requests:
            proc.stdin.write(encode_content_length_message(req))
            proc.stdin.flush()
            response = read_content_length_message(proc.stdout)
            if response is None:
                raise RuntimeError("MCP server closed stdout before response.")
            responses.append(response)

        init = responses[0].get("result", {})
        checks["initialize_ok"] = bool(init.get("capabilities", {}).get("tools") == {})

        tools_result = responses[1].get("result", {})
        tools = tools_result.get("tools", []) if isinstance(tools_result, dict) else []
        names = {t.get("name") for t in tools if isinstance(t, dict)}
        checks["tools_list_ok"] = bool(tools)
        checks["run_workflow_present"] = "lmola.run_workflow" in names
        checks["low_level_tools_absent"] = _LOW_LEVEL_TOOL_NAMES.isdisjoint(names)

        checks["validate_workflow_ok"] = (
            responses[3].get("result", {}).get("structuredContent", {}).get("status") == "ok"
            and "canonical_workflow_json" in responses[3].get("result", {}).get("structuredContent", {})
        )
        dry = responses[4].get("result", {}).get("structuredContent", {})
        checks["run_workflow_dry_run_safe"] = dry.get("status") == "ok" and dry.get("executed") is False and dry.get("batch_dir") is None

        missing_confirm = responses[5].get("result", {})
        sc = missing_confirm.get("structuredContent", {}) if isinstance(missing_confirm, dict) else {}
        checks["confirmation_required_ok"] = bool(missing_confirm.get("isError") is True and sc.get("error_type") == "confirmation_required")

        unknown = responses[6]
        checks["unknown_tool_handled"] = unknown.get("error", {}).get("code") == -32601
    except Exception as exc:  # noqa: BLE001
        after = _count_mcp_run_batches()
        checks["mcp_runs_unchanged"] = before == after
        return {
            "status": "error",
            "message": "MCP stdio client smoke failed.",
            "server_command": command,
            "requests": requests,
            "responses": responses,
            "checks": checks,
            "mcp_runs_before": before,
            "mcp_runs_after": after,
            "error": str(exc),
        }
    finally:
        if proc.stdin:
            proc.stdin.close()
        try:
            proc.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            proc.terminate()
            proc.wait(timeout=timeout_seconds)

    after = _count_mcp_run_batches()
    checks["mcp_runs_unchanged"] = before == after
    ok = all(checks.values())
    return {
        "status": "ok" if ok else "error",
        "message": "MCP stdio client smoke completed." if ok else "MCP stdio client smoke completed with failed checks.",
        "server_command": command,
        "requests": requests,
        "responses": responses,
        "checks": checks,
        "mcp_runs_before": before,
        "mcp_runs_after": after,
    }


def render_smoke_result(result: dict[str, Any], fmt: str) -> str:
    if fmt == "json":
        return json.dumps(result, indent=2, sort_keys=True)
    return json.dumps(result, indent=2, sort_keys=True)
