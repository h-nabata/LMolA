from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel

from lmola.mcp_client_smoke import DEFAULT_SERVER_COMMAND
from lmola.mcp_runtime import encode_content_length_message, read_content_length_message
from lmola.artifact_summary import summarize_artifact_path
from lmola.workflows.catalog import WORKFLOW_CATALOG

DEFAULT_TASK = "Generate structures from examples/smiles_list.csv and relax them with xTB. Use dry-run only."
LOW_LEVEL_TOOL_NAMES = {
    "lmola.generate_small_molecule_rdkit",
    "lmola.generate_small_molecule_openbabel",
    "lmola.generate_metal_complex_molsimplify",
    "lmola.relax_structure_xtb",
    "lmola.validate_structure_ase",
}
ALLOWED_INPUT_TYPES = {"smiles", "smiles_csv", "xyz", "xyz_list"}
FORBIDDEN_ARGUMENT_KEYS = {"inputs", "settings", "parameters", "command", "shell", "bash"}


class AgentToolCall(BaseModel):
    tool_name: str
    arguments: dict[str, Any]
    rationale: str | None = None


@dataclass
class ValidationResult:
    valid: bool
    errors: list[dict[str, Any]]
    warnings: list[str]
    normalized_tool_call: dict[str, Any] | None
    safe_to_execute: bool


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


def _workflow_catalog_for_prompt() -> list[dict[str, Any]]:
    out = []
    for wf_id in sorted(WORKFLOW_CATALOG):
        e = WORKFLOW_CATALOG[wf_id]
        out.append({"workflow_id": e.workflow_id, "task_type": e.task_type, "input_types": e.input_types, "canonical_tools": e.tools, "description": e.description})
    return out


def build_agent_tool_selection_prompt(*, task: str, allowed_tools: list[str]) -> str:
    wf_enum = sorted(WORKFLOW_CATALOG)
    return (
        "Output JSON only.\n"
        f"Task: {task}\n"
        f"Allowed tool names: {allowed_tools}\n"
        f"Allowed workflow_id enum: {wf_enum}\n"
        f"Allowed input.type enum: {sorted(ALLOWED_INPUT_TYPES)}\n"
        "Required schema: {\"tool_name\":\"lmola.run_workflow\",\"arguments\":{\"workflow_id\":str,\"input\":{\"type\":str,\"path\":str|optional,\"value\":str|optional},\"columns\":{\"id\":str,\"smiles\":str}|optional,\"dry_run\":true|omitted},\"rationale\":str|optional}.\n"
        "Forbidden keys: arguments.inputs, arguments.settings, arguments.parameters, arguments.command, arguments.shell.\n"
        "Never invent workflow_id. Never invent keys like inputs/settings/parameters. Use dry_run=true unless explicitly told otherwise. In default agent-smoke mode never set allow_execution=true or confirm=true.\n"
        "Positive example: {\"tool_name\":\"lmola.run_workflow\",\"arguments\":{\"workflow_id\":\"smiles_to_xtb_relax\",\"input\":{\"type\":\"smiles_csv\",\"path\":\"examples/smiles_list.csv\"},\"columns\":{\"id\":\"id\",\"smiles\":\"smiles\"},\"dry_run\":true},\"rationale\":\"Dry-run plan only\"}\n"
        "Negative example (invalid): {\"tool_name\":\"lmola.run_workflow\",\"arguments\":{\"workflow_id\":\"generate_and_relax_structures\",\"inputs\":{},\"settings\":{}}}\n"
        f"Workflow catalog: {json.dumps(_workflow_catalog_for_prompt(), sort_keys=True)}\n"
    )


def build_repair_prompt(*, task: str, invalid_call: dict[str, Any], errors: list[dict[str, Any]]) -> str:
    return (
        "Output corrected JSON only.\n"
        f"Original task: {task}\n"
        f"Invalid tool call: {json.dumps(invalid_call, sort_keys=True)}\n"
        f"Validation errors: {json.dumps(errors, sort_keys=True)}\n"
        f"Allowed workflow_id enum: {sorted(WORKFLOW_CATALOG)}\n"
        "Required schema: {\"tool_name\":\"lmola.run_workflow\",\"arguments\":{\"workflow_id\":str,\"input\":{\"type\":\"smiles|smiles_csv|xyz|xyz_list\",\"path\":str|optional,\"value\":str|optional},\"columns\":{\"id\":str,\"smiles\":str}|optional,\"dry_run\":true|omitted},\"rationale\":str|optional}.\n"
        "Example for this task: {\"tool_name\":\"lmola.run_workflow\",\"arguments\":{\"workflow_id\":\"smiles_to_xtb_relax\",\"input\":{\"type\":\"smiles_csv\",\"path\":\"examples/smiles_list.csv\"},\"columns\":{\"id\":\"id\",\"smiles\":\"smiles\"},\"dry_run\":true}}"
    )


def build_agent_result_analysis_prompt(*, task: str, selected_tool_name: str, selected_workflow_id: str, tool_response: dict[str, Any], artifact_summary: dict[str, Any] | None) -> str:
    return (
        "Return JSON only. Analyze LMolA MCP dry-run/tool response using structured summaries only.\n"
        f"Original task: {task}\nSelected tool: {selected_tool_name}\nSelected workflow: {selected_workflow_id}\n"
        f"MCP tool response JSON: {json.dumps(tool_response, sort_keys=True)}\n"
        f"Artifact summary JSON: {json.dumps(artifact_summary or {}, sort_keys=True)}\n"
        "Do not infer chemical correctness. Report execution status, artifact status, and the next safe action.\n"
        "Schema: {\"status\":\"ok|error\",\"task_interpretation\":\"...\",\"selected_tool_name\":\"...\",\"selected_workflow_id\":\"...\",\"execution_mode\":\"dry_run|plan_only|confirmed_execution|unknown\",\"executed\":false,\"artifact_summary_kind\":\"mcp_audit|batch_dir|agent_smoke_dir|plan_dir|unknown\",\"canonical_tools\":[],\"artifact_status\":\"ok|error\",\"summary\":\"...\",\"warnings\":[],\"next_recommended_actions\":[]}"
    )


def call_mock_agent_llm(*, phase: str) -> str:
    if phase == "selection":
        return json.dumps({"tool_name": "lmola.run_workflow", "arguments": {"workflow_id": "smiles_to_xtb_relax", "input": {"type": "smiles_csv", "path": "examples/smiles_list.csv"}, "columns": {"id": "id", "smiles": "smiles"}, "dry_run": True}})
    if phase == "repair":
        return call_mock_agent_llm(phase="selection")
    return json.dumps({"status": "ok", "task_interpretation": "Generate structures from a SMILES CSV and relax them with xTB.", "selected_tool_name": "lmola.run_workflow", "selected_workflow_id": "smiles_to_xtb_relax", "execution_mode": "dry_run", "executed": False, "artifact_summary_kind": "mcp_audit", "canonical_tools": ["generate_small_molecule_rdkit", "validate_structure_ase", "relax_structure_xtb"], "artifact_status": "ok", "summary": "Dry-run completed and produced audit artifacts without execution.", "warnings": [], "next_recommended_actions": ["Review canonical workflow before confirmed execution."]})


def call_ollama_agent_llm(*, prompt: str, config: AgentCallConfig) -> str:
    payload = {"model": config.model, "stream": False, "format": "json", "options": {"temperature": config.temperature, "num_predict": config.max_tokens}, "messages": [{"role": "user", "content": prompt}]}
    req = urllib.request.Request(f"{config.base_url.rstrip('/')}/api/chat", data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=config.timeout_seconds) as resp:  # noqa: S310
            body = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        raise RuntimeError("ollama_error") from exc
    content = body.get("message", {}).get("content") if isinstance(body, dict) else None
    if not isinstance(content, str):
        raise RuntimeError("ollama_invalid_response")
    return content


def validate_agent_tool_call(*, tool_call: dict[str, Any], runtime_tools: set[str], workflow_catalog: dict[str, Any], allow_confirmed_execution: bool = False) -> ValidationResult:
    errors: list[dict[str, Any]] = []
    warnings: list[str] = []
    try:
        call = AgentToolCall.model_validate(tool_call)
    except Exception as exc:  # noqa: BLE001
        return ValidationResult(False, [{"error_type": "invalid_arguments_schema", "field": "root", "message": str(exc)}], warnings, None, False)
    if call.tool_name in LOW_LEVEL_TOOL_NAMES:
        errors.append({"error_type": "low_level_tool_not_allowed", "field": "tool_name", "message": "Low-level tools are not directly callable."})
    if call.tool_name not in runtime_tools:
        errors.append({"error_type": "unknown_tool_name", "field": "tool_name", "message": "Tool not available in runtime tools."})
    args = dict(call.arguments)
    for k in FORBIDDEN_ARGUMENT_KEYS:
        if k in args:
            errors.append({"error_type": "forbidden_key", "field": f"arguments.{k}", "message": f"Forbidden key: {k}"})
    if call.tool_name == "lmola.run_workflow":
        wf = args.get("workflow_id")
        if wf not in workflow_catalog:
            errors.append({"error_type": "unknown_workflow_id", "field": "arguments.workflow_id", "message": "Unknown workflow_id.", "allowed_values": sorted(workflow_catalog)})
        input_obj = args.get("input")
        if not isinstance(input_obj, dict):
            errors.append({"error_type": "missing_required_field", "field": "arguments.input", "message": "arguments.input is required."})
        else:
            if input_obj.get("type") not in ALLOWED_INPUT_TYPES:
                errors.append({"error_type": "unsupported_input_shape", "field": "arguments.input.type", "message": "Unsupported input.type.", "allowed_values": sorted(ALLOWED_INPUT_TYPES)})
            if not input_obj.get("path") and not input_obj.get("value"):
                errors.append({"error_type": "missing_required_field", "field": "arguments.input.path|value", "message": "Need input.path or input.value."})
        if args.get("dry_run") is False:
            errors.append({"error_type": "execution_not_allowed", "field": "arguments.dry_run", "message": "dry_run=false is not allowed in default mode."})
        if args.get("allow_execution") is True:
            errors.append({"error_type": "execution_not_allowed", "field": "arguments.allow_execution", "message": "allow_execution=true is forbidden."})
        if args.get("confirm") is True:
            errors.append({"error_type": "execution_not_allowed", "field": "arguments.confirm", "message": "confirm=true is forbidden."})
        if not allow_confirmed_execution and args.get("output_root") and str(args["output_root"]).startswith("/"):
            errors.append({"error_type": "unsafe_output_path", "field": "arguments.output_root", "message": "Absolute output_root not allowed."})
        if "dry_run" not in args:
            args["dry_run"] = True
        if wf in {"smiles_to_xtb_relax", "smiles_to_3d_rdkit"} and isinstance(input_obj, dict) and input_obj.get("type") == "smiles_csv" and input_obj.get("path") == "examples/smiles_list.csv" and "columns" not in args:
            args["columns"] = {"id": "id", "smiles": "smiles"}
    normalized = {"name": call.tool_name, "arguments": args}
    return ValidationResult(valid=not errors, errors=errors, warnings=warnings, normalized_tool_call=normalized if not errors else None, safe_to_execute=not errors)


def run_mcp_agent_smoke(*, task: str = DEFAULT_TASK, backend: str = "mock", model: str = "", base_url: str = "http://127.0.0.1:11434", timeout_seconds: float = 20.0, temperature: float = 0.0, max_tokens: int = 800, out_dir: str = "", allow_confirmed_execution: bool = False, confirm_execution: bool = False, use_artifact_summary: bool = True, artifact_summary_mode: str = "mcp", summarize_after_tool_call: bool = True, max_artifact_items: int = 20, max_artifact_text_chars: int = 4000) -> dict[str, Any]:
    cfg = AgentCallConfig(backend=backend, model=model, base_url=base_url, timeout_seconds=timeout_seconds, temperature=temperature, max_tokens=max_tokens)
    smoke_dir = Path(out_dir) if out_dir else Path("outputs") / f"agent_smoke_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"
    smoke_dir.mkdir(parents=True, exist_ok=True)
    checks = {k: False for k in ["initialize_ok", "tools_list_ok", "low_level_tools_absent", "tool_selection_initial_parse_ok", "tool_selection_initial_valid", "tool_selection_repair_attempted", "tool_selection_repair_successful", "tool_selection_final_valid", "tool_selection_safe", "mcp_tool_call_ok", "run_workflow_dry_run_safe", "artifact_summary_requested", "artifact_summary_ok", "artifact_summary_read_only", "artifact_aware_analysis_parse_ok", "artifact_aware_analysis_status_ok", "analysis_parse_ok", "analysis_schema_ok", "analysis_status_ok", "mcp_runs_unchanged"]}
    transcript: dict[str, Any] = {"backend": backend, "task": task}
    before = _count_mcp_run_batches()
    tool_call_req = None
    tool_call_resp: dict[str, Any] = {}
    repair_attempted = False
    repair_successful = False
    validation_errors: list[dict[str, Any]] = []
    artifact_summary_req: dict[str, Any] = {}
    artifact_summary_resp: dict[str, Any] = {}
    artifact_summary_parsed: dict[str, Any] | None = None
    try:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2] / "src")
        proc = subprocess.Popen(DEFAULT_SERVER_COMMAND, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, cwd=str(Path(__file__).resolve().parents[2]))  # noqa: S603
        assert proc.stdin and proc.stdout
        for req in [_rpc(1, "initialize", {}), _rpc(2, "tools/list", {})]:
            proc.stdin.write(encode_content_length_message(req))
            proc.stdin.flush()
            resp = read_content_length_message(proc.stdout)
            transcript.setdefault("mcp", []).append({"request": req, "response": resp})
        names = {t.get("name") for t in transcript["mcp"][1]["response"].get("result", {}).get("tools", []) if isinstance(t, dict) and isinstance(t.get("name"), str)}
        checks["initialize_ok"] = True
        checks["tools_list_ok"] = "lmola.run_workflow" in names
        checks["low_level_tools_absent"] = LOW_LEVEL_TOOL_NAMES.isdisjoint(names)
        prompt = build_agent_tool_selection_prompt(task=task, allowed_tools=sorted(names))
        raw = call_mock_agent_llm(phase="selection") if backend == "mock" else call_ollama_agent_llm(prompt=prompt, config=cfg)
        parsed = _extract_json_object(raw)
        checks["tool_selection_initial_parse_ok"] = True
        vr = validate_agent_tool_call(tool_call=parsed, runtime_tools=names, workflow_catalog=WORKFLOW_CATALOG, allow_confirmed_execution=allow_confirmed_execution)
        checks["tool_selection_initial_valid"] = vr.valid
        final_call = parsed
        if not vr.valid:
            validation_errors = vr.errors
            checks["tool_selection_repair_attempted"] = True
            repair_attempted = True
            repair_prompt = build_repair_prompt(task=task, invalid_call=parsed, errors=vr.errors)
            repair_raw = call_mock_agent_llm(phase="repair") if backend == "mock" else call_ollama_agent_llm(prompt=repair_prompt, config=cfg)
            repaired_parsed = _extract_json_object(repair_raw)
            vr2 = validate_agent_tool_call(tool_call=repaired_parsed, runtime_tools=names, workflow_catalog=WORKFLOW_CATALOG, allow_confirmed_execution=allow_confirmed_execution)
            transcript.update({"tool_selection_repair_prompt": repair_prompt, "tool_selection_repair_raw_response": repair_raw, "tool_selection_repaired_parsed": repaired_parsed})
            if vr2.valid:
                repair_successful = True
                checks["tool_selection_repair_successful"] = True
                final_call = repaired_parsed
                vr = vr2
        checks["tool_selection_final_valid"] = vr.valid
        checks["tool_selection_safe"] = vr.safe_to_execute
        transcript.update({"tool_selection_prompt": prompt, "tool_selection_raw_response": raw, "tool_selection_parsed": parsed, "tool_selection_final": final_call, "tool_selection_validation_errors": validation_errors})
        if not vr.valid or vr.normalized_tool_call is None:
            raise RuntimeError("tool_call_validation_failed")
        tool_call_req = _rpc(3, "tools/call", vr.normalized_tool_call)
        proc.stdin.write(encode_content_length_message(tool_call_req))
        proc.stdin.flush()
        tool_call_resp = read_content_length_message(proc.stdout) or {}
        checks["mcp_tool_call_ok"] = "result" in tool_call_resp and "error" not in tool_call_resp
        sc = tool_call_resp.get("result", {}).get("structuredContent", {})
        checks["run_workflow_dry_run_safe"] = sc.get("executed") is False and sc.get("batch_dir") is None
        sc = tool_call_resp.get("result", {}).get("structuredContent", {})
        if use_artifact_summary:
            checks["artifact_summary_requested"] = True
            if summarize_after_tool_call:
                artifact_path = next((sc.get(k) for k in ("audit_path", "batch_dir", "agent_smoke_dir", "plan_dir") if isinstance(sc.get(k), str) and sc.get(k)), None)
                if artifact_path:
                    if artifact_summary_mode == "internal":
                        artifact_summary_req = {"name": "internal.summarize_artifacts", "arguments": {"path": artifact_path, "max_items": max_artifact_items, "max_text_chars": max_artifact_text_chars}}
                        artifact_summary_parsed = summarize_artifact_path(artifact_path, max_items=max_artifact_items, max_text_chars=max_artifact_text_chars)
                        artifact_summary_resp = {"result": {"structuredContent": artifact_summary_parsed}}
                    else:
                        artifact_summary_req = _rpc(4, "tools/call", {"name": "lmola.summarize_artifacts", "arguments": {"path": artifact_path, "max_items": max_artifact_items, "max_text_chars": max_artifact_text_chars}})
                        proc.stdin.write(encode_content_length_message(artifact_summary_req))
                        proc.stdin.flush()
                        artifact_summary_resp = read_content_length_message(proc.stdout) or {}
                        artifact_summary_parsed = artifact_summary_resp.get("result", {}).get("structuredContent") if isinstance(artifact_summary_resp, dict) else None
                    checks["artifact_summary_ok"] = isinstance(artifact_summary_parsed, dict) and artifact_summary_parsed.get("status") == "ok"
                    checks["artifact_summary_read_only"] = bool(isinstance(artifact_summary_parsed, dict) and artifact_summary_parsed.get("executed") in {False, None})
                else:
                    artifact_summary_parsed = None
                    transcript.setdefault("warnings", []).append("No summarizable artifact path found in tool result fields.")
        analysis_prompt = build_agent_result_analysis_prompt(task=task, selected_tool_name=final_call.get("tool_name", ""), selected_workflow_id=final_call.get("arguments", {}).get("workflow_id", ""), tool_response=tool_call_resp, artifact_summary=artifact_summary_parsed)
        raw_a = call_mock_agent_llm(phase="analysis") if backend == "mock" else call_ollama_agent_llm(prompt=analysis_prompt, config=cfg)
        parsed_a = _extract_json_object(raw_a)
        checks["analysis_parse_ok"] = True
        checks["artifact_aware_analysis_parse_ok"] = True
        checks["analysis_schema_ok"] = all(k in parsed_a for k in ["status", "selected_tool_name", "selected_workflow_id"])
        checks["analysis_status_ok"] = parsed_a.get("status") in {"ok", "error"} if checks["analysis_schema_ok"] else False
        checks["artifact_aware_analysis_status_ok"] = parsed_a.get("status") in {"ok", "error"}
        transcript.update({"artifact_summary_request": artifact_summary_req, "artifact_summary_response": artifact_summary_resp, "artifact_summary_parsed": artifact_summary_parsed or {}, "artifact_aware_analysis_prompt": analysis_prompt, "artifact_aware_analysis_raw_response": raw_a, "artifact_aware_analysis_parsed": parsed_a, "result_analysis_prompt": analysis_prompt, "result_analysis_raw_response": raw_a, "result_analysis_parsed": parsed_a})
    except Exception as exc:  # noqa: BLE001
        after = _count_mcp_run_batches()
        checks["mcp_runs_unchanged"] = before == after
        result = {"status": "error", "error_type": str(exc), "agent_smoke_phase": "12.6.1_tool_call_schema_enforcement", "backend": backend, "model": model, "task": task, "agent_smoke_dir": str(smoke_dir), "initial_selected_tool_name": transcript.get("tool_selection_parsed", {}).get("tool_name", ""), "initial_selected_workflow_id": transcript.get("tool_selection_parsed", {}).get("arguments", {}).get("workflow_id", ""), "selected_tool_name": transcript.get("tool_selection_final", {}).get("tool_name", ""), "selected_workflow_id": transcript.get("tool_selection_final", {}).get("arguments", {}).get("workflow_id", ""), "tool_selection_repaired": repair_successful, "tool_selection_validation_errors": validation_errors, "repair_attempted": repair_attempted, "repair_successful": repair_successful, "mcp_tool_call_executed": bool(tool_call_req), "rejected_before_mcp_call": not bool(tool_call_req), "checks": checks, "mcp_runs_before": before, "mcp_runs_after": after, "python_executable": shutil.which("python"), "lmola_executable": shutil.which("lmola"), "ollama_model": model, "ollama_reachable": backend != "ollama"}
        write_agent_smoke_artifacts(smoke_dir=smoke_dir, transcript=transcript, result=result, tools_list=transcript.get("mcp", [{}, {"response": {"result": {"tools": []}}}])[1]["response"].get("result", {}), tool_call_req=tool_call_req, tool_call_resp=tool_call_resp)
        return result
    after = _count_mcp_run_batches()
    checks["mcp_runs_unchanged"] = before == after
    final = transcript.get("tool_selection_final", {})
    analysis = transcript.get("result_analysis_parsed", {})
    required = ["initialize_ok", "tools_list_ok", "low_level_tools_absent", "tool_selection_initial_parse_ok", "tool_selection_final_valid", "tool_selection_safe", "mcp_tool_call_ok", "run_workflow_dry_run_safe", "analysis_parse_ok", "analysis_schema_ok", "analysis_status_ok", "mcp_runs_unchanged"]
    artifact_summary = transcript.get("artifact_summary_parsed") if isinstance(transcript.get("artifact_summary_parsed"), dict) else None
    result = {"status": "ok" if all(checks[k] for k in required) else "error", "agent_smoke_phase": "12.8_artifact_aware_agent_analysis", "backend": backend, "model": model, "task": task, "agent_smoke_dir": str(smoke_dir), "initial_selected_tool_name": transcript.get("tool_selection_parsed", {}).get("tool_name", ""), "initial_selected_workflow_id": transcript.get("tool_selection_parsed", {}).get("arguments", {}).get("workflow_id", ""), "selected_tool_name": final.get("tool_name", ""), "selected_workflow_id": final.get("arguments", {}).get("workflow_id", ""), "tool_selection_repaired": repair_successful, "tool_selection_validation_errors": validation_errors, "repair_attempted": repair_attempted, "repair_successful": repair_successful, "mcp_tool_call_executed": True, "rejected_before_mcp_call": False, "execution_mode": analysis.get("execution_mode", "unknown"), "executed": bool(analysis.get("executed", False)), "artifact_summary_enabled": use_artifact_summary, "artifact_summary_mode": artifact_summary_mode if use_artifact_summary else "none", "artifact_summary_path": (artifact_summary or {}).get("path"), "artifact_summary_kind": (artifact_summary or {}).get("artifact_kind"), "artifact_summary_status": (artifact_summary or {}).get("status"), "artifact_summary_canonical_tools": (artifact_summary or {}).get("canonical_tools", []), "artifact_summary_executed": (artifact_summary or {}).get("executed"), "final_report": analysis if isinstance(analysis, dict) else None, "checks": checks, "mcp_runs_before": before, "mcp_runs_after": after, "python_executable": shutil.which("python"), "lmola_executable": shutil.which("lmola"), "ollama_model": model, "ollama_reachable": True, "artifact_summary": artifact_summary}
    write_agent_smoke_artifacts(smoke_dir=smoke_dir, transcript=transcript, result=result, tools_list=transcript["mcp"][1]["response"].get("result", {}), tool_call_req=tool_call_req, tool_call_resp=tool_call_resp)
    return result

def write_agent_smoke_artifacts(*, smoke_dir: Path, transcript: dict[str, Any], result: dict[str, Any], tools_list: dict[str, Any], tool_call_req: dict[str, Any] | None, tool_call_resp: dict[str, Any]) -> None:
    files = {
        "agent_smoke_result.json": result,
        "agent_smoke_transcript.json": transcript,
        "tools_list.json": tools_list,
        "tool_selection_parsed.json": transcript.get("tool_selection_parsed", {}),
        "tool_selection_repaired_parsed.json": transcript.get("tool_selection_repaired_parsed", {}),
        "tool_selection_final.json": transcript.get("tool_selection_final", {}),
        "tool_selection_validation_errors.json": transcript.get("tool_selection_validation_errors", []),
        "mcp_tool_call_request.json": tool_call_req or {},
        "mcp_tool_call_response.json": tool_call_resp,
        "artifact_summary_request.json": transcript.get("artifact_summary_request", {}),
        "artifact_summary_response.json": transcript.get("artifact_summary_response", {}),
        "artifact_summary_parsed.json": transcript.get("artifact_summary_parsed", {}),
        "artifact_aware_analysis_parsed.json": transcript.get("artifact_aware_analysis_parsed", {}),
        "result_analysis_parsed.json": transcript.get("result_analysis_parsed", {}),
    }
    for n, payload in files.items():
        (smoke_dir / n).write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    text_files = {
        "tool_selection_prompt.txt": transcript.get("tool_selection_prompt", ""),
        "tool_selection_raw_response.txt": transcript.get("tool_selection_raw_response", ""),
        "tool_selection_repair_prompt.txt": transcript.get("tool_selection_repair_prompt", ""),
        "tool_selection_repair_raw_response.txt": transcript.get("tool_selection_repair_raw_response", ""),
        "result_analysis_prompt.txt": transcript.get("result_analysis_prompt", ""),
        "result_analysis_raw_response.txt": transcript.get("result_analysis_raw_response", ""),
        "artifact_aware_analysis_prompt.txt": transcript.get("artifact_aware_analysis_prompt", ""),
        "artifact_aware_analysis_raw_response.txt": transcript.get("artifact_aware_analysis_raw_response", ""),
    }
    for n, txt in text_files.items():
        (smoke_dir / n).write_text(txt, encoding="utf-8")
