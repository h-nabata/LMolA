from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from lmola.schema_export import MODEL_REGISTRY
from lmola.tools.registry import list_tools
from lmola.workflows.catalog import list_workflows
from lmola.workflows.schemas import WorkflowRequest


PREVIEW_SCHEMA_VERSION = "lmola.mcp_preview.v1"


def _canonicalize(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _canonicalize(v) for k, v in sorted(obj.items(), key=lambda kv: kv[0])}
    if isinstance(obj, list):
        return [_canonicalize(v) for v in obj]
    return obj


def workflow_request_input_schema() -> dict[str, Any]:
    return _canonicalize(WorkflowRequest.model_json_schema())


def workflow_id_enum_schema() -> dict[str, Any]:
    workflow_ids = [w.workflow_id for w in list_workflows()]
    return {"type": "string", "enum": workflow_ids}


def make_mcp_tool_descriptor(*, name: str, description: str, input_schema: dict[str, Any], lmola_meta: dict[str, Any]) -> dict[str, Any]:
    return _canonicalize(
        {
            "name": name,
            "description": description,
            "inputSchema": input_schema,
            "_meta": {"lmola": lmola_meta},
        }
    )


def make_high_level_workflow_descriptors() -> list[dict[str, Any]]:
    workflow_schema = workflow_request_input_schema()
    workflow_ids = workflow_id_enum_schema()
    workflows = [w.model_dump() for w in list_workflows()]

    return [
        make_mcp_tool_descriptor(
            name="lmola.list_workflows",
            description="List available LMolA workflow catalog entries.",
            input_schema={"type": "object", "properties": {"compact": {"type": "boolean"}}, "additionalProperties": False},
            lmola_meta={"level": "high_level_workflow", "source": "workflow_catalog", "side_effects": False, "dry_run_only": True},
        ),
        make_mcp_tool_descriptor(
            name="lmola.inspect_workflow",
            description="Inspect one workflow by workflow_id.",
            input_schema={"type": "object", "properties": {"workflow_id": workflow_ids}, "required": ["workflow_id"], "additionalProperties": False},
            lmola_meta={"level": "high_level_workflow", "source": "workflow_catalog", "side_effects": False, "dry_run_only": True},
        ),
        make_mcp_tool_descriptor(
            name="lmola.plan_workflow",
            description="Convert a natural-language request into a validated LMolA WorkflowRequest plan without executing chemistry tools.",
            input_schema={"type": "object", "properties": {"request": {"type": "string"}}, "required": ["request"], "additionalProperties": False},
            lmola_meta={
                "level": "high_level_workflow",
                "source": "planner_context",
                "side_effects": False,
                "dry_run_only": True,
                "canonical_tools": [w["tools"] for w in workflows],
            },
        ),
        make_mcp_tool_descriptor(
            name="lmola.validate_workflow",
            description="Validate and canonicalize an LMolA WorkflowRequest without executing chemistry tools.",
            input_schema=workflow_schema,
            lmola_meta={"level": "high_level_workflow", "source": "pydantic_schema", "side_effects": False, "dry_run_only": True},
        ),
        make_mcp_tool_descriptor(
            name="lmola.run_workflow",
            description="Run a validated LMolA workflow request and write batch artifacts.",
            input_schema=workflow_schema,
            lmola_meta={
                "level": "high_level_workflow",
                "source": "pydantic_schema",
                "side_effects": True,
                "writes_files": True,
                "requires_confirmation": True,
                "dry_run_only": False,
                "safe_execution_notes": "Static preview metadata only; runtime availability is determined by lmola mcp runtime-tools for the active phase.",
            },
        ),
    ]


def make_low_level_tool_descriptors() -> list[dict[str, Any]]:
    descriptors: list[dict[str, Any]] = []
    for tool in list_tools():
        model = MODEL_REGISTRY.get(tool.input_schema)
        input_schema = model.model_json_schema() if model is not None else {"type": "object"}
        descriptors.append(
            make_mcp_tool_descriptor(
                name=f"lmola.{tool.name}",
                description=tool.description,
                input_schema=input_schema,
                lmola_meta={
                    "level": "low_level_tool",
                    "source": "tool_registry",
                    "internal_tool_name": tool.name,
                    "category": tool.category,
                    "required_backends": sorted(tool.required_backends),
                    "execution_kind": "validation"
                    if tool.category == "validation"
                    else ("external_cli" if tool.name in {"generate_small_molecule_openbabel", "generate_metal_complex_molsimplify", "relax_structure_xtb"} else "in_process"),
                    "recommended_for_external_agents": False,
                    "safe_execution_notes": tool.notes,
                },
            )
        )
    return descriptors


def export_mcp_tools_preview(*, include_low_level: bool = True) -> dict[str, Any]:
    tools = make_high_level_workflow_descriptors()
    if include_low_level:
        tools.extend(make_low_level_tool_descriptors())
    return _canonicalize({"tools": tools})


def export_mcp_resources_preview() -> dict[str, Any]:
    return {"resources": []}


def export_mcp_prompts_preview() -> dict[str, Any]:
    return {"prompts": []}


def export_mcp_preview_bundle(*, include_low_level: bool = True) -> dict[str, Any]:
    return _canonicalize(
        {
            "schema_version": PREVIEW_SCHEMA_VERSION,
            "generated_by": "LMolA",
            "mcp_compatibility": {
                "kind": "static_descriptor_preview",
                "server_runtime": False,
                "jsonrpc": False,
                "transport": "none",
                "tools_list_shape": True,
            },
            "tools": export_mcp_tools_preview(include_low_level=include_low_level)["tools"],
            "resources": export_mcp_resources_preview()["resources"],
            "prompts": export_mcp_prompts_preview()["prompts"],
        }
    )


def validate_mcp_tool_descriptor_shape(descriptor: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in ["name", "description", "inputSchema"]:
        if field not in descriptor:
            errors.append(f"missing field: {field}")
    if "inputSchema" in descriptor and not isinstance(descriptor["inputSchema"], dict):
        errors.append("inputSchema must be an object")
    if "_meta" in descriptor and not isinstance(descriptor["_meta"], dict):
        errors.append("_meta must be an object")
    if isinstance(descriptor.get("_meta"), dict) and "lmola" in descriptor["_meta"] and not isinstance(descriptor["_meta"]["lmola"], dict):
        errors.append("_meta.lmola must be an object")
    try:
        json.dumps(descriptor, sort_keys=True)
    except TypeError as exc:
        errors.append(f"non-serializable descriptor: {exc}")
    return errors


def validate_mcp_preview_bundle(bundle: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    tools = bundle.get("tools") if "tools" in bundle else bundle.get("descriptors")
    if not isinstance(tools, list):
        return ["tools must be a list"]
    seen: set[str] = set()
    for idx, tool in enumerate(tools):
        if not isinstance(tool, dict):
            errors.append(f"tools[{idx}] must be an object")
            continue
        name = tool.get("name")
        if isinstance(name, str):
            if name in seen:
                errors.append(f"duplicate tool name: {name}")
            seen.add(name)
        errors.extend([f"tools[{idx}]: {e}" for e in validate_mcp_tool_descriptor_shape(tool)])
    return errors


def write_mcp_preview(out_dir: Path, *, include_low_level: bool = True) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    bundle = export_mcp_preview_bundle(include_low_level=include_low_level)
    tools = export_mcp_tools_preview(include_low_level=include_low_level)
    files = {
        "mcp_preview_bundle.json": bundle,
        "mcp_tools_preview.json": tools,
    }
    for name, payload in files.items():
        (out_dir / name).write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    (out_dir / "README_mcp_preview.md").write_text(
        "\n".join(
            [
                "# LMolA MCP-compatible descriptor preview",
                "",
                "- This is a static descriptor preview.",
                "- It is not a running MCP server.",
                "- It does not implement JSON-RPC.",
                "- It does not implement tools/call.",
                "- Descriptors are generated from LMolA internal schemas/catalogs.",
                "- Standard descriptor fields are name, description, inputSchema.",
                "- LMolA-specific metadata is stored under _meta.lmola.",
                "- Phase 12 will implement the runtime MCP adapter.",
            ]
        ),
        encoding="utf-8",
    )
    return {"status": "ok", "output_dir": str(out_dir), "files": sorted([*files.keys(), "README_mcp_preview.md"])}


def render_preview(payload: dict[str, Any], fmt: str) -> str:
    if fmt == "yaml":
        return yaml.safe_dump(payload, sort_keys=True)
    return json.dumps(payload, indent=2, sort_keys=True)
