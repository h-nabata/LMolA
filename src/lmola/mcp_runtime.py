from __future__ import annotations

import json
import sys
from typing import Any

from pydantic import ValidationError

from lmola.agent.workflow_planner import plan_workflow_request
from lmola.mcp_preview import export_mcp_tools_preview
from lmola.schema_export import export_all_schemas, export_planner_schema_bundle, export_tool_registry_schema, export_workflow_catalog_schema
from lmola.workflows.catalog import get_workflow_entry, list_workflows
from lmola.workflows.schemas import WorkflowRequest

RUNTIME_PHASE = "12.1_plan_validate"
RUNTIME_ALLOWED_TOOLS = {
    "lmola.list_workflows",
    "lmola.inspect_workflow",
    "lmola.get_schema_bundle",
    "lmola.get_tool_registry_schema",
    "lmola.get_workflow_catalog",
    "lmola.get_planner_context",
    "lmola.validate_workflow",
    "lmola.plan_workflow",
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
    }


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
        meta.setdefault("dry_run_only", True)
        meta.setdefault("side_effects", False)
        meta.setdefault("executes_workflow", False)
        meta.setdefault("writes_batch_artifacts", False)
        if name == "lmola.plan_workflow":
            meta["source"] = "planner_context"
            writes_plan_artifacts = False
            meta["writes_plan_artifacts"] = writes_plan_artifacts
            meta["side_effects"] = "plan_artifacts_only" if writes_plan_artifacts else False
        runtime_tools.append(base)
    return runtime_tools


def call_mcp_tool(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    args = arguments or {}
    if name not in RUNTIME_ALLOWED_TOOLS:
        return _runtime_error("tool_not_allowed", "Tool is not enabled in Phase 12.1 plan/validate MCP runtime.", tool=name, runtime_phase=RUNTIME_PHASE)

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
            if planning.status == "error" and planning.parsed_workflow and planning.parsed_workflow.get("status") == "unsupported":
                planning_payload["actual_status"] = planning.status
                planning_payload["normalized_status"] = "unsupported"
                return {"status": "ok", "planning_result": planning_payload}
            planning_payload["actual_status"] = planning.status
            planning_payload["normalized_status"] = "ok" if planning.status == "ok" else "error"
            if planning.status == "ok":
                return {"status": "ok", "planning_result": planning_payload}
            return _runtime_error("planning_error", planning.message, planning_result=planning_payload)
    except KeyError as exc:
        return _runtime_error("not_found", str(exc))
    except ValidationError as exc:
        return _runtime_error("validation_error", "WorkflowRequest validation failed.", validation_errors=exc.errors())
    except Exception as exc:  # noqa: BLE001
        return _runtime_error("validation_error", str(exc))

    return _runtime_error("unknown_tool", f"Unhandled tool: {name}")


def handle_jsonrpc_message(message: dict[str, Any]) -> dict[str, Any] | None:
    req_id = message.get("id")
    method = message.get("method")
    params = message.get("params") or {}

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"serverInfo": {"name": "lmola-mcp-runtime", "version": RUNTIME_PHASE}, "capabilities": {"tools": {}, "lmola": {"read_only": True, "plan_validate_only": True}}}}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"status": "ok"}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"runtime_phase": RUNTIME_PHASE, "server_runtime": True, "jsonrpc": True, "transport": "stdio", "tools": list_mcp_tools_runtime()}}
    if method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(tool_name, str):
            return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32602, "message": "Invalid params", "data": {"reason": "name is required"}}}
        return {"jsonrpc": "2.0", "id": req_id, "result": _mcp_content(call_mcp_tool(tool_name, arguments))}
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}


def run_mcp_stdio_server() -> None:
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception as exc:  # noqa: BLE001
            err = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error", "data": {"detail": str(exc)}}}
            sys.stdout.write(json.dumps(err) + "\n")
            sys.stdout.flush()
            continue
        response = handle_jsonrpc_message(msg)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
