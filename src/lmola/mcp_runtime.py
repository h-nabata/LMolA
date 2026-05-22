from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from lmola.agent.planner_eval import _infer_unavailable_backend
from lmola.agent.workflow_planner import plan_workflow_request
from lmola.mcp_preview import export_mcp_tools_preview
from lmola.artifact_summary import summarize_artifact_path
from lmola.artifact_triage import triage_artifact_path
from lmola.schema_export import export_all_schemas, export_planner_schema_bundle, export_tool_registry_schema, export_workflow_catalog_schema
from lmola.backends.capabilities import list_backend_capabilities, resolve_backend_capability
from lmola.workflows.catalog import get_workflow_entry, list_workflows
from lmola.workflows.runner import run_workflow_request
from lmola.workflows.schemas import WorkflowRequest

RUNTIME_PHASE = "12.5_external_client_smoke"
MCP_EXECUTION_ALLOWLIST = {
    "smiles_to_3d_rdkit",
    "smiles_to_conformers_rdkit",
    "smiles_to_3d_openbabel",
    "smiles_to_xtb_relax",
    "validate_xyz",
    "xyz_to_xtb_relax",
    "smiles_to_rdkit_descriptors",
    "xyz_to_geometry_analysis",
}
RUNTIME_ALLOWED_TOOLS = {
    "lmola.list_workflows",
    "lmola.inspect_workflow",
    "lmola.get_schema_bundle",
    "lmola.get_tool_registry_schema",
    "lmola.get_workflow_catalog",
    "lmola.get_planner_context",
    "lmola.validate_workflow",
    "lmola.plan_workflow",
    "lmola.run_workflow",
    "lmola.summarize_artifacts",
    "lmola.triage_artifacts",
    "lmola.get_backend_capabilities",
}


def _runtime_error(error_type: str, message: str, **data: Any) -> dict[str, Any]:
    payload = {"status": "error", "error_type": error_type, "message": message}
    if data:
        payload.update(data)
    return payload


def _mcp_content(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": json.dumps(payload, sort_keys=True)}],
        "structuredContent": payload,
        "isError": payload.get("status") == "error",
    }


def encode_content_length_message(message: dict[str, Any]) -> bytes:
    body = json.dumps(message, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    return header + body


def decode_content_length_message(data: bytes) -> dict[str, Any]:
    sep = b"\r\n\r\n"
    if sep not in data:
        raise ValueError("Missing header separator")
    header_blob, body = data.split(sep, 1)
    headers = header_blob.decode("ascii")
    length = None
    for line in headers.split("\r\n"):
        if line.lower().startswith("content-length:"):
            length = int(line.split(":", 1)[1].strip())
            break
    if length is None:
        raise ValueError("Missing Content-Length header")
    payload = body[:length]
    if len(payload) != length:
        raise ValueError("Incomplete payload")
    return json.loads(payload.decode("utf-8"))


def read_content_length_message(stdin: Any) -> dict[str, Any] | None:
    headers: list[bytes] = []
    while True:
        line = stdin.readline()
        if not line:
            return None
        if line in {b"\r\n", b"\n"}:
            break
        headers.append(line)
    length = None
    for raw in headers:
        text = raw.decode("ascii").strip()
        if text.lower().startswith("content-length:"):
            length = int(text.split(":", 1)[1].strip())
            break
    if length is None:
        raise ValueError("Missing Content-Length header")
    body = stdin.read(length)
    if not body or len(body) != length:
        raise ValueError("Incomplete payload")
    return json.loads(body.decode("utf-8"))


def write_content_length_message(stdout: Any, message: dict[str, Any]) -> None:
    stdout.write(encode_content_length_message(message))
    stdout.flush()


def _canonicalize_workflow(req: WorkflowRequest) -> dict[str, Any]:
    entry = get_workflow_entry(req.workflow_id)
    if req.input.type not in entry.input_types:
        raise ValueError(f"Input type {req.input.type} is not supported by {req.workflow_id}")
    steps = req.steps or [{"tool": tool_name} for tool_name in entry.tools]
    return {
        "workflow_id": req.workflow_id,
        "input": req.input.model_dump(),
        "columns": req.columns,
        "steps": [s if isinstance(s, dict) else s.model_dump() for s in steps],
        "outputs": req.outputs.model_dump(),
        "metadata": req.metadata,
    }


def _safe_output_root(root: str | None) -> Path:
    requested = Path(root) if root else Path("outputs/mcp_runs")
    resolved = requested.resolve()
    allowed = [Path("outputs").resolve(), Path("/tmp/lmola_mcp_runs").resolve()]
    if not any(resolved == base or base in resolved.parents for base in allowed):
        raise ValueError("output_root must resolve under outputs/ or /tmp/lmola_mcp_runs/")
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _write_audit(payload: dict[str, Any]) -> str:
    audit_dir = Path("outputs/mcp_audit")
    audit_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    path = audit_dir / f"mcp_run_{stamp}_{uuid4().hex[:6]}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return str(path)


def list_mcp_tools_runtime() -> list[dict[str, Any]]:
    preview_map = {t["name"]: t for t in export_mcp_tools_preview(include_low_level=True)["tools"]}
    runtime_specs = {
        "lmola.list_workflows": {"description": "List available LMolA workflow catalog entries.", "inputSchema": {"type": "object", "properties": {"compact": {"type": "boolean"}}, "additionalProperties": False}},
        "lmola.inspect_workflow": {"description": "Inspect one workflow by workflow_id.", "inputSchema": {"type": "object", "properties": {"workflow_id": {"type": "string"}}, "required": ["workflow_id"], "additionalProperties": False}},
        "lmola.get_schema_bundle": {"description": "Return exported LMolA schema bundle.", "inputSchema": {"type": "object", "properties": {"compact": {"type": "boolean"}}, "additionalProperties": False}},
        "lmola.get_tool_registry_schema": {"description": "Return exported LMolA tool registry schema.", "inputSchema": {"type": "object", "properties": {"compact": {"type": "boolean"}}, "additionalProperties": False}},
        "lmola.get_workflow_catalog": {"description": "Return exported LMolA workflow catalog.", "inputSchema": {"type": "object", "properties": {"compact": {"type": "boolean"}}, "additionalProperties": False}},
        "lmola.get_planner_context": {"description": "Return compact planner context export.", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
        "lmola.validate_workflow": {"description": "Validate and canonicalize an LMolA WorkflowRequest without executing chemistry tools.", "inputSchema": WorkflowRequest.model_json_schema()},
        "lmola.plan_workflow": {"description": "Convert a natural-language request into a validated LMolA WorkflowRequest plan without executing chemistry tools.", "inputSchema": {"type": "object", "additionalProperties": False, "properties": {"request": {"type": "string"}, "write_artifacts": {"type": "boolean", "default": False}}, "required": ["request"]}},
        "lmola.run_workflow": {"description": "Run a validated, allowlisted LMolA workflow request after explicit confirmation and write batch artifacts.", "inputSchema": {"type": "object", "additionalProperties": False, "properties": {"workflow_id": {"type": "string"}, "input": {"type": "object"}, "columns": {"type": ["object", "null"]}, "outputs": {"type": ["object", "null"]}, "metadata": {"type": ["object", "null"]}, "dry_run": {"type": "boolean", "default": True}, "allow_execution": {"type": "boolean", "default": False}, "confirm": {"type": "boolean", "default": False}, "confirmation_text": {"type": ["string", "null"]}, "output_root": {"type": ["string", "null"]}, "reason": {"type": ["string", "null"]}}, "required": ["workflow_id", "input"]}},
        "lmola.summarize_artifacts": {"description": "Summarize LMolA output artifacts into compact structured JSON for LLM interpretation.", "inputSchema": {"type": "object", "additionalProperties": False, "properties": {"path": {"type": "string"}, "max_items": {"type": "integer", "default": 20, "minimum": 1, "maximum": 200}, "max_text_chars": {"type": "integer", "default": 4000, "minimum": 100, "maximum": 20000}}, "required": ["path"]}},
        "lmola.triage_artifacts": {"description": "Diagnose LMolA output artifacts and produce read-only failure triage JSON.", "inputSchema": {"type": "object", "additionalProperties": False, "properties": {"path": {"type": "string"}, "max_items": {"type": "integer", "default": 20, "minimum": 1, "maximum": 200}, "max_text_chars": {"type": "integer", "default": 4000, "minimum": 100, "maximum": 20000}}, "required": ["path"]}},
        "lmola.get_backend_capabilities": {"description": "Return backend capability registry metadata without executing tools.", "inputSchema": {"type": "object", "additionalProperties": False, "properties": {"backend_id": {"type": ["string", "null"]}, "compact": {"type": "boolean", "default": False}}}},
    }
    runtime_tools: list[dict[str, Any]] = []
    for name in sorted(RUNTIME_ALLOWED_TOOLS):
        base = json.loads(json.dumps(preview_map.get(name, {})))
        spec = runtime_specs[name]
        base["name"] = name
        base["description"] = spec["description"]
        base["inputSchema"] = spec["inputSchema"]
        meta = base.setdefault("_meta", {}).setdefault("lmola", {})
        meta["runtime_enabled"] = True
        meta["runtime_phase"] = RUNTIME_PHASE
        meta["runtime_features"] = ["12.7_artifact_summarizer", "12.8_artifact_aware_agent_analysis", "12.9_artifact_triage", "13_backend_capability_registry"]
        meta.setdefault("dry_run_only", True)
        meta.setdefault("side_effects", False)
        meta.setdefault("executes_workflow", False)
        meta.setdefault("writes_batch_artifacts", False)
        if name == "lmola.plan_workflow":
            meta["source"] = "planner_context"
            writes_plan_artifacts = False
            meta["writes_plan_artifacts"] = writes_plan_artifacts
            meta["side_effects"] = "plan_artifacts_only" if writes_plan_artifacts else False
        if name == "lmola.run_workflow":
            meta["runtime_phase"] = RUNTIME_PHASE
            meta["source"] = "pydantic_schema"
            meta["dry_run_only"] = False
            meta["side_effects"] = True
            meta["executes_workflow"] = True
            meta["writes_batch_artifacts"] = True
            meta["requires_confirmation"] = True
            meta["requires_allow_execution"] = True
            meta["allowlisted_only"] = True
            meta["mcp_execution_allowlist"] = sorted(MCP_EXECUTION_ALLOWLIST)
            meta["supported_workflow_ids"] = [w.workflow_id for w in list_workflows()]
            meta["safe_execution_notes"] = "MCP runtime execution is enabled only for allowlisted workflows and requires dry_run=false, allow_execution=true, and confirm=true. Low-level chemistry tools remain unavailable as direct MCP runtime tools."
        if name == "lmola.summarize_artifacts":
            meta["runtime_phase"] = "12.7_artifact_summarizer"
            meta["level"] = "artifact_inspection"
            meta["source"] = "artifact_summary"
            meta["side_effects"] = False
            meta["executes_workflow"] = False
            meta["writes_batch_artifacts"] = False
            meta["dry_run_only"] = True
        if name == "lmola.triage_artifacts":
            meta["runtime_phase"] = "12.9_artifact_triage"
            meta["level"] = "artifact_inspection"
            meta["source"] = "artifact_triage"
            meta["side_effects"] = False
            meta["executes_workflow"] = False
            meta["writes_batch_artifacts"] = False
            meta["dry_run_only"] = True
        if name == "lmola.summarize_artifacts":
            meta["runtime_phase"] = "12.7_artifact_summarizer"
            meta["level"] = "artifact_inspection"
            meta["source"] = "artifact_summary"
            meta["side_effects"] = False
            meta["executes_workflow"] = False
            meta["writes_batch_artifacts"] = False
            meta["dry_run_only"] = True
        runtime_tools.append(base)
    return runtime_tools


def call_mcp_tool(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    args = arguments or {}
    if name not in RUNTIME_ALLOWED_TOOLS:
        return _runtime_error("tool_not_allowed", "Tool is not enabled in MCP runtime.", tool=name, runtime_phase=RUNTIME_PHASE)

    try:
        if name == "lmola.list_workflows":
            compact = bool(args.get("compact", False))
            workflows = [w.model_dump() for w in list_workflows()]
            return {"status": "ok", "workflows": [{k: v for k, v in w.items() if k in {"workflow_id", "task_type", "input_types", "tools", "description"}} for w in workflows] if compact else workflows}
        if name == "lmola.inspect_workflow":
            workflow_id = args.get("workflow_id")
            if not isinstance(workflow_id, str) or not workflow_id:
                return _runtime_error("invalid_arguments", "workflow_id is required.")
            return {"status": "ok", "workflow": get_workflow_entry(workflow_id).model_dump()}
        if name == "lmola.get_schema_bundle":
            bundle = export_all_schemas()
            return {"status": "ok", "schema_bundle": bundle if not bool(args.get("compact", False)) else {"schema_version": bundle["schema_version"], "generated_by": bundle["generated_by"]}}
        if name == "lmola.get_tool_registry_schema":
            payload = export_tool_registry_schema()
            return {"status": "ok", "tool_registry_schema": payload if not bool(args.get("compact", False)) else {"schema_version": payload["schema_version"], "tool_names": payload["tool_names"]}}
        if name == "lmola.get_workflow_catalog":
            return {"status": "ok", "workflow_catalog": export_workflow_catalog_schema(compact=bool(args.get("compact", False)))}
        if name == "lmola.get_planner_context":
            return {"status": "ok", "planner_context": export_planner_schema_bundle()}
        if name == "lmola.get_backend_capabilities":
            backend_id = args.get("backend_id")
            if backend_id is None:
                return {"status": "ok", "backend_capabilities": {k: v.model_dump() for k, v in list_backend_capabilities().items()}}
            if not isinstance(backend_id, str):
                return _runtime_error("invalid_arguments", "backend_id must be string or null.")
            cap = resolve_backend_capability(backend_id)
            if cap is None:
                return _runtime_error("unknown_backend", "Unknown backend_id.", backend_id=backend_id)
            return {"status": "ok", "backend_capability": cap.model_dump()}
        if name == "lmola.validate_workflow":
            req = WorkflowRequest.model_validate(args)
            return {"status": "ok", "canonical_workflow_json": _canonicalize_workflow(req)}
        if name == "lmola.plan_workflow":
            request_text = args.get("request")
            if not isinstance(request_text, str) or not request_text.strip():
                return _runtime_error("invalid_arguments", "request must be a non-empty string.")
            write_artifacts = bool(args.get("write_artifacts", False))
            planning = plan_workflow_request(request_text.strip(), write_artifacts=write_artifacts)
            planning_payload = planning.model_dump()
            planning_payload["actual_status"] = planning.status
            if planning.status == "ok":
                planning_payload["normalized_status"] = "ok"
            else:
                parsed_status = (planning.parsed_workflow or {}).get("status")
                inferred = _infer_unavailable_backend(
                    [
                        request_text,
                        str((planning.parsed_workflow or {}).get("reason") or ""),
                        planning.message or "",
                    ]
                )
                if inferred and parsed_status in {None, "unsupported", "backend_unavailable"}:
                    planning_payload["normalized_status"] = "backend_unavailable"
                elif parsed_status == "backend_unavailable":
                    planning_payload["normalized_status"] = "backend_unavailable"
                elif parsed_status == "unsupported":
                    planning_payload["normalized_status"] = "unsupported"
                else:
                    planning_payload["normalized_status"] = "error"
                if planning_payload["normalized_status"] in {"unsupported", "backend_unavailable"}:
                    return {"status": "ok", "planning_result": planning_payload}
            if planning.status == "ok":
                return {"status": "ok", "planning_result": planning_payload}
            return _runtime_error("planning_error", planning.message, planning_result=planning_payload)
        if name == "lmola.run_workflow":
            dry_run = bool(args.get("dry_run", True))
            allow_execution = bool(args.get("allow_execution", False))
            confirm = bool(args.get("confirm", False))
            workflow_id = args.get("workflow_id")
            audit_payload: dict[str, Any] = {
                "timestamp": datetime.now(UTC).isoformat(),
                "runtime_phase": RUNTIME_PHASE,
                "tool": name,
                "workflow_id": workflow_id,
                "dry_run": dry_run,
                "allow_execution": allow_execution,
                "confirm": confirm,
                "confirmation_text": args.get("confirmation_text"),
                "reason": args.get("reason"),
                "output_root": args.get("output_root"),
                "request_json": args,
                "execution_allowed": False,
                "executed": False,
                "status": "error",
                "error_type": None,
                "message": None,
                "batch_dir": None,
                "summary_csv": None,
                "summary_json": None,
            }
            try:
                req = WorkflowRequest.model_validate({k: v for k, v in args.items() if k in {"workflow_id", "input", "columns", "steps", "outputs", "metadata"}})
                canonical: dict[str, Any] | None = None
                if dry_run:
                    canonical = _canonicalize_workflow(req)
                    audit_payload["canonical_workflow_json"] = canonical
                    audit_payload["status"] = "ok"
                    audit_path = _write_audit(audit_payload)
                    return {"status": "ok", "dry_run": True, "execution_allowed": False, "executed": False, "canonical_workflow_json": canonical, "batch_dir": None, "summary_csv": None, "summary_json": None, "audit_path": audit_path}
                if not confirm:
                    audit_payload["error_type"] = "confirmation_required"
                    audit_payload["message"] = "Explicit confirm=true is required when dry_run is false."
                    audit_path = _write_audit(audit_payload)
                    return _runtime_error("confirmation_required", audit_payload["message"], executed=False, batch_dir=None, audit_path=audit_path)
                if not allow_execution:
                    audit_payload["error_type"] = "execution_not_allowed"
                    audit_payload["message"] = "allow_execution=true is required when dry_run is false."
                    audit_path = _write_audit(audit_payload)
                    return _runtime_error("execution_not_allowed", audit_payload["message"], executed=False, batch_dir=None, audit_path=audit_path)
                if req.workflow_id not in MCP_EXECUTION_ALLOWLIST:
                    audit_payload["error_type"] = "workflow_not_allowlisted"
                    audit_payload["message"] = f"Workflow {req.workflow_id} is not in the MCP execution allowlist."
                    audit_path = _write_audit(audit_payload)
                    return _runtime_error("workflow_not_allowlisted", audit_payload["message"], executed=False, batch_dir=None, audit_path=audit_path)
                output_root = _safe_output_root(args.get("output_root"))
                canonical = _canonicalize_workflow(req)
                audit_payload["canonical_workflow_json"] = canonical
                audit_payload["execution_allowed"] = True
                result = run_workflow_request(req, output_root=output_root)
                audit_payload["executed"] = True
                audit_payload["batch_dir"] = result.batch_dir
                audit_payload["summary_csv"] = result.summary_csv
                audit_payload["summary_json"] = result.summary_json
                if result.status != "ok":
                    audit_payload["error_type"] = "execution_failed"
                    audit_payload["message"] = result.message
                    audit_path = _write_audit(audit_payload)
                    return _runtime_error("execution_failed", result.message, executed=True, workflow_id=req.workflow_id, batch_dir=result.batch_dir, summary_csv=result.summary_csv, summary_json=result.summary_json, execution_result=result.model_dump(), audit_path=audit_path)
                audit_payload["status"] = "ok"
                audit_path = _write_audit(audit_payload)
                return {"status": "ok", "executed": True, "workflow_id": req.workflow_id, "batch_dir": result.batch_dir, "summary_csv": result.summary_csv, "summary_json": result.summary_json, "execution_result": result.model_dump(), "audit_path": audit_path}
            except ValidationError as exc:
                audit_payload["error_type"] = "validation_error"
                audit_payload["message"] = "WorkflowRequest validation failed."
                audit_payload["validation_errors"] = exc.errors()
                audit_path = _write_audit(audit_payload)
                return _runtime_error("validation_error", "WorkflowRequest validation failed.", validation_errors=exc.errors(), executed=False, batch_dir=None, audit_path=audit_path)
            except ValueError as exc:
                etype = "unsafe_output_path" if "output_root" in str(exc) else "validation_error"
                audit_payload["error_type"] = etype
                audit_payload["message"] = str(exc)
                audit_path = _write_audit(audit_payload)
                return _runtime_error(etype, str(exc), executed=False, batch_dir=None, audit_path=audit_path)
        if name == "lmola.summarize_artifacts":
            p = args.get("path")
            if not isinstance(p, str) or not p.strip():
                return _runtime_error("invalid_arguments", "path is required.")
            return summarize_artifact_path(p, max_items=int(args.get("max_items", 20)), max_text_chars=int(args.get("max_text_chars", 4000)))
        if name == "lmola.triage_artifacts":
            p = args.get("path")
            if not isinstance(p, str) or not p.strip():
                return _runtime_error("invalid_arguments", "path is required.")
            return triage_artifact_path(p, max_items=int(args.get("max_items", 20)), max_text_chars=int(args.get("max_text_chars", 4000)))
    except KeyError as exc:
        return _runtime_error("not_found", str(exc))
    except ValidationError as exc:
        return _runtime_error("validation_error", "WorkflowRequest validation failed.", validation_errors=exc.errors())
    except Exception as exc:  # noqa: BLE001
        return _runtime_error("validation_error", str(exc))

    return _runtime_error("unknown_tool", f"Unhandled tool: {name}")


def handle_jsonrpc_message(message: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid request"}}
    req_id = message.get("id")
    method = message.get("method")
    params = message.get("params") or {}
    if not isinstance(params, dict):
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32602, "message": "Invalid params", "data": {"reason": "params must be an object"}}}

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"protocolVersion": "2024-11-05", "serverInfo": {"name": "lmola", "version": RUNTIME_PHASE}, "capabilities": {"tools": {}}, "_meta": {"lmola": {"runtime_phase": RUNTIME_PHASE, "execution_policy": "confirmed_allowlisted_execution", "low_level_tools_direct_call": False}}}}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"status": "ok"}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"runtime_phase": RUNTIME_PHASE, "server_runtime": True, "jsonrpc": True, "transport": "stdio", "tools": list_mcp_tools_runtime()}}
    if method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(tool_name, str):
            return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32602, "message": "Invalid params", "data": {"reason": "name is required"}}}
        if tool_name not in RUNTIME_ALLOWED_TOOLS:
            return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"}}
        return {"jsonrpc": "2.0", "id": req_id, "result": _mcp_content(call_mcp_tool(tool_name, arguments if isinstance(arguments, dict) else {}))}
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}


def run_mcp_stdio_server() -> None:
    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer
    while True:
        try:
            msg = read_content_length_message(stdin)
            if msg is None:
                return
        except Exception as exc:  # noqa: BLE001
            err = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error", "data": {"detail": str(exc)}}}
            write_content_length_message(stdout, err)
            continue
        response = handle_jsonrpc_message(msg)
        if response is not None:
            write_content_length_message(stdout, response)
