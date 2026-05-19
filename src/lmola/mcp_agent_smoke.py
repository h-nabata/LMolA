from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from lmola.mcp_client_smoke import DEFAULT_SERVER_COMMAND
from lmola.mcp_runtime import encode_content_length_message, read_content_length_message

DEFAULT_TASK = "Generate structures from examples/smiles_list.csv and relax them with xTB. Use dry-run only."
LOW_LEVEL_TOOL_NAMES = {
    "lmola.generate_small_molecule_rdkit",
    "lmola.generate_small_molecule_openbabel",
    "lmola.generate_metal_complex_molsimplify",
    "lmola.relax_structure_xtb",
    "lmola.validate_structure_ase",
}


@dataclass
class AgentCallConfig:
    backend: str = "mock"
    model: str = ""
    base_url: str = "http://127.0.0.1:11434"
    timeout_seconds: float = 20.0
    temperature: float = 0.0
    max_tokens: int = 800


def _count_mcp_run_batches() -> int:
    root = Path("outputs/mcp_runs")
    return len(list(root.glob("batch_*"))) if root.exists() else 0


def _rpc(req_id: int, method: str, params: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}


def _extract_json_object(raw: str) -> dict[str, Any]:
    txt = raw.strip()
    if txt.startswith("{"):
        val = json.loads(txt)
        if not isinstance(val, dict):
            raise ValueError("JSON root must be an object.")
        return val
    start = txt.find("{")
    end = txt.rfind("}")
    if start >= 0 and end > start:
        val = json.loads(txt[start : end + 1])
        if not isinstance(val, dict):
            raise ValueError("JSON root must be an object.")
        return val
    raise ValueError("No JSON object found.")


def build_agent_tool_selection_prompt(*, task: str, allowed_tools: list[str]) -> str:
    return (
        "Return JSON only. Select one LMolA MCP tool call for this task.\\n"
        f"Task: {task}\\n"
        f"Allowed tools: {', '.join(allowed_tools)}\\n"
        "Safety: do not use low-level chemistry tools; prefer lmola.run_workflow dry_run=true; no shell commands.\\n"
        'Output schema: {"tool_name": string, "arguments": object, "rationale": string}'
    )


def build_agent_result_analysis_prompt(*, task: str, selected_tool_name: str, tool_response: dict[str, Any]) -> str:
    return (
        "Return JSON only. Analyze MCP tool response for LMolA smoke.\\n"
        f"Task: {task}\\n"
        f"Selected tool: {selected_tool_name}\\n"
        f"Tool response JSON: {json.dumps(tool_response, sort_keys=True)}\\n"
        "Schema: {\"status\":\"ok|error\",\"task_interpretation\":string,\"selected_tool_name\":string,\"selected_workflow_id\":string,\"execution_mode\":\"dry_run|plan_only|confirmed_execution|unknown\",\"executed\":bool,\"canonical_tools\":list,\"artifacts_to_inspect\":list,\"warnings\":list,\"next_recommended_action\":string}"
    )


def call_mock_agent_llm(*, phase: str) -> str:
    if phase == "selection":
        return json.dumps(
            {
                "tool_name": "lmola.run_workflow",
                "arguments": {
                    "workflow_id": "smiles_to_xtb_relax",
                    "input": {"type": "smiles_csv", "path": "examples/smiles_list.csv"},
                    "columns": {"id": "id", "smiles": "smiles"},
                    "dry_run": True,
                },
                "rationale": "Use dry-run run_workflow to validate the execution plan without running chemistry tools.",
            }
        )
    return json.dumps(
        {
            "status": "ok",
            "task_interpretation": "Generate structures from a SMILES CSV and relax them with xTB.",
            "selected_tool_name": "lmola.run_workflow",
            "selected_workflow_id": "smiles_to_xtb_relax",
            "execution_mode": "dry_run",
            "executed": False,
            "canonical_tools": ["generate_small_molecule_rdkit", "validate_structure_ase", "relax_structure_xtb"],
            "artifacts_to_inspect": ["canonical_workflow_json", "audit_path"],
            "warnings": [],
            "next_recommended_action": "Run confirmed execution only after reviewing the canonical workflow.",
        }
    )


def call_ollama_agent_llm(*, prompt: str, config: AgentCallConfig) -> str:
    payload = {
        "model": config.model,
        "stream": False,
        "format": "json",
        "options": {"temperature": config.temperature, "num_predict": config.max_tokens},
        "messages": [{"role": "user", "content": prompt}],
    }
    req = urllib.request.Request(
        f"{config.base_url.rstrip('/')}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=config.timeout_seconds) as resp:  # noqa: S310
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        if "model" in detail.lower() and "not found" in detail.lower():
            raise RuntimeError("ollama_model_missing") from exc
        raise RuntimeError("ollama_invalid_response") from exc
    except TimeoutError as exc:
        raise RuntimeError("ollama_timeout") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError("ollama_unreachable") from exc
    msg = body.get("message", {}) if isinstance(body, dict) else {}
    content = msg.get("content") if isinstance(msg, dict) else None
    if not isinstance(content, str):
        raise RuntimeError("ollama_invalid_response")
    return content


def validate_agent_tool_call(*, parsed: dict[str, Any], runtime_tool_names: set[str], allow_confirmed_execution: bool, confirm_execution: bool) -> tuple[bool, str, dict[str, Any]]:
    tool_name = parsed.get("tool_name")
    args = parsed.get("arguments")
    if not isinstance(tool_name, str):
        return False, "invalid_tool_call", {}
    if tool_name not in runtime_tool_names or tool_name in LOW_LEVEL_TOOL_NAMES:
        return False, "unsafe_tool_call", {}
    if not isinstance(args, dict):
        return False, "invalid_tool_call", {}
    if any(k in args for k in ["command", "shell", "bash"]):
        return False, "unsafe_tool_call", {}
    if tool_name == "lmola.run_workflow":
        args.setdefault("dry_run", True)
        if args.get("dry_run") is False and not (allow_confirmed_execution and confirm_execution):
            return False, "unsafe_tool_call", {}
        if not allow_confirmed_execution and any(args.get(k) is True for k in ["allow_execution", "confirm"]):
            return False, "unsafe_tool_call", {}
    return True, "", {"name": tool_name, "arguments": args}


def run_mcp_agent_smoke(*, task: str = DEFAULT_TASK, backend: str = "mock", model: str = "", base_url: str = "http://127.0.0.1:11434", timeout_seconds: float = 20.0, temperature: float = 0.0, max_tokens: int = 800, out_dir: str = "", allow_confirmed_execution: bool = False, confirm_execution: bool = False) -> dict[str, Any]:
    cfg = AgentCallConfig(backend=backend, model=model, base_url=base_url, timeout_seconds=timeout_seconds, temperature=temperature, max_tokens=max_tokens)
    smoke_dir = Path(out_dir) if out_dir else Path("outputs") / f"agent_smoke_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"
    smoke_dir.mkdir(parents=True, exist_ok=True)
    checks = {k: False for k in ["initialize_ok", "tools_list_ok", "low_level_tools_absent", "tool_selection_parse_ok", "tool_selection_safe", "mcp_tool_call_ok", "run_workflow_dry_run_safe", "analysis_parse_ok", "analysis_status_ok", "mcp_runs_unchanged"]}
    transcript: dict[str, Any] = {"backend": backend, "task": task}
    before = _count_mcp_run_batches()
    tool_call_req = None
    tool_call_resp: dict[str, Any] = {}
    try:
        env = os.environ.copy()
        src_path = str(Path(__file__).resolve().parents[2] / "src")
        env["PYTHONPATH"] = src_path + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        proc = subprocess.Popen(DEFAULT_SERVER_COMMAND, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, cwd=str(Path(__file__).resolve().parents[2]))  # noqa: S603
        transcript["server_command"] = DEFAULT_SERVER_COMMAND
        assert proc.stdin is not None and proc.stdout is not None
        for req in [_rpc(1, "initialize", {}), _rpc(2, "tools/list", {})]:
            proc.stdin.write(encode_content_length_message(req))
            proc.stdin.flush()
            resp = read_content_length_message(proc.stdout)
            if resp is None:
                raise RuntimeError("mcp_server_closed")
            transcript.setdefault("mcp", []).append({"request": req, "response": resp})
        init = transcript["mcp"][0]["response"].get("result", {})
        checks["initialize_ok"] = bool(init.get("capabilities", {}).get("tools") == {})
        tools = transcript["mcp"][1]["response"].get("result", {}).get("tools", [])
        names = {t.get("name") for t in tools if isinstance(t, dict) and isinstance(t.get("name"), str)}
        checks["tools_list_ok"] = "lmola.run_workflow" in names
        checks["low_level_tools_absent"] = LOW_LEVEL_TOOL_NAMES.isdisjoint(names)
        tool_prompt = build_agent_tool_selection_prompt(task=task, allowed_tools=sorted(names))
        raw_sel = call_mock_agent_llm(phase="selection") if backend == "mock" else call_ollama_agent_llm(prompt=tool_prompt, config=cfg)
        parsed_sel = _extract_json_object(raw_sel)
        checks["tool_selection_parse_ok"] = True
        safe, err, payload = validate_agent_tool_call(parsed=parsed_sel, runtime_tool_names=names, allow_confirmed_execution=allow_confirmed_execution, confirm_execution=confirm_execution)
        checks["tool_selection_safe"] = safe
        if not safe:
            raise RuntimeError(err)
        tool_call_req = _rpc(3, "tools/call", payload)
        proc.stdin.write(encode_content_length_message(tool_call_req))
        proc.stdin.flush()
        tool_call_resp = read_content_length_message(proc.stdout) or {}
        transcript.setdefault("mcp", []).append({"request": tool_call_req, "response": tool_call_resp})
        checks["mcp_tool_call_ok"] = "result" in tool_call_resp and "error" not in tool_call_resp
        sc = tool_call_resp.get("result", {}).get("structuredContent", {})
        checks["run_workflow_dry_run_safe"] = parsed_sel.get("tool_name") != "lmola.run_workflow" or (sc.get("executed") is False and sc.get("batch_dir") is None and "canonical_workflow_json" in sc)
        analysis_prompt = build_agent_result_analysis_prompt(task=task, selected_tool_name=parsed_sel.get("tool_name", ""), tool_response=tool_call_resp)
        raw_analysis = call_mock_agent_llm(phase="analysis") if backend == "mock" else call_ollama_agent_llm(prompt=analysis_prompt, config=cfg)
        parsed_analysis = _extract_json_object(raw_analysis)
        checks["analysis_parse_ok"] = True
        checks["analysis_status_ok"] = parsed_analysis.get("status") in {"ok", "error"}
        transcript.update({"tool_selection_prompt": tool_prompt, "tool_selection_raw_response": raw_sel, "tool_selection_parsed": parsed_sel, "result_analysis_prompt": analysis_prompt, "result_analysis_raw_response": raw_analysis, "result_analysis_parsed": parsed_analysis})
    except Exception as exc:  # noqa: BLE001
        after = _count_mcp_run_batches()
        checks["mcp_runs_unchanged"] = before == after
        result = {"status": "error", "message": "Ollama-in-the-loop MCP agent smoke failed.", "error": str(exc), "backend": backend, "model": model, "base_url": base_url, "task": task, "agent_smoke_dir": str(smoke_dir), "selected_tool_name": transcript.get("tool_selection_parsed", {}).get("tool_name", ""), "selected_workflow_id": transcript.get("tool_selection_parsed", {}).get("arguments", {}).get("workflow_id", ""), "execution_mode": "unknown", "executed": False, "checks": checks, "mcp_runs_before": before, "mcp_runs_after": after}
        write_agent_smoke_artifacts(smoke_dir=smoke_dir, transcript=transcript, result=result, tools_list=transcript.get("mcp", [{}, {"response": {"result": {"tools": []}}}])[1]["response"].get("result", {}), tool_call_req=tool_call_req, tool_call_resp=tool_call_resp)
        return result
    finally:
        if 'proc' in locals():
            if proc.stdin:
                proc.stdin.close()
            try:
                proc.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                proc.terminate()
                proc.wait(timeout=timeout_seconds)
    after = _count_mcp_run_batches()
    checks["mcp_runs_unchanged"] = before == after
    parsed = transcript["tool_selection_parsed"]
    analysis = transcript["result_analysis_parsed"]
    result = {"status": "ok" if all(checks.values()) else "error", "message": "Ollama-in-the-loop MCP agent smoke completed.", "backend": backend, "model": model, "base_url": base_url, "task": task, "agent_smoke_dir": str(smoke_dir), "selected_tool_name": parsed.get("tool_name", ""), "selected_workflow_id": parsed.get("arguments", {}).get("workflow_id", ""), "execution_mode": analysis.get("execution_mode", "unknown"), "executed": bool(analysis.get("executed", False)), "checks": checks, "mcp_runs_before": before, "mcp_runs_after": after}
    write_agent_smoke_artifacts(smoke_dir=smoke_dir, transcript=transcript, result=result, tools_list=transcript["mcp"][1]["response"].get("result", {}), tool_call_req=tool_call_req, tool_call_resp=tool_call_resp)
    return result


def write_agent_smoke_artifacts(*, smoke_dir: Path, transcript: dict[str, Any], result: dict[str, Any], tools_list: dict[str, Any], tool_call_req: dict[str, Any] | None, tool_call_resp: dict[str, Any]) -> None:
    (smoke_dir / "agent_smoke_result.json").write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    (smoke_dir / "agent_smoke_transcript.json").write_text(json.dumps(transcript, indent=2, sort_keys=True), encoding="utf-8")
    (smoke_dir / "tools_list.json").write_text(json.dumps(tools_list, indent=2, sort_keys=True), encoding="utf-8")
    (smoke_dir / "tool_selection_prompt.txt").write_text(transcript.get("tool_selection_prompt", ""), encoding="utf-8")
    (smoke_dir / "tool_selection_raw_response.txt").write_text(transcript.get("tool_selection_raw_response", ""), encoding="utf-8")
    (smoke_dir / "tool_selection_parsed.json").write_text(json.dumps(transcript.get("tool_selection_parsed", {}), indent=2, sort_keys=True), encoding="utf-8")
    (smoke_dir / "mcp_tool_call_request.json").write_text(json.dumps(tool_call_req or {}, indent=2, sort_keys=True), encoding="utf-8")
    (smoke_dir / "mcp_tool_call_response.json").write_text(json.dumps(tool_call_resp, indent=2, sort_keys=True), encoding="utf-8")
    (smoke_dir / "result_analysis_prompt.txt").write_text(transcript.get("result_analysis_prompt", ""), encoding="utf-8")
    (smoke_dir / "result_analysis_raw_response.txt").write_text(transcript.get("result_analysis_raw_response", ""), encoding="utf-8")
    (smoke_dir / "result_analysis_parsed.json").write_text(json.dumps(transcript.get("result_analysis_parsed", {}), indent=2, sort_keys=True), encoding="utf-8")
    (smoke_dir / "README_agent_smoke.md").write_text("# LMolA MCP Agent Smoke\n\nArtifacts for MCP agent-smoke run.\n", encoding="utf-8")
