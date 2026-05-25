from __future__ import annotations

import json
from pathlib import Path

import yaml

from lmola.agent.planner_eval import PlannerEvalCase, PlannerEvalSuite
from lmola.schemas import BuildOptions, MoleculeBuildRequest, ToolCallRecord, ToolResult
from lmola.tools.registry import RelaxXtbRequest, ValidateStructureRequest, list_tools
from lmola.backends.capabilities import backend_capability_schema, list_backend_capabilities
from lmola.artifact_contracts import ArtifactContract, ArtifactRegistry, export_artifact_registry
from lmola.artifact_manifest import ArtifactManifest, ArtifactManifestEntry, ArtifactCompatibilityHint
from lmola.workflows import check_workflow_backend_readiness, list_workflows
from lmola.workflows.catalog import WorkflowArtifactOutputDescriptor, WorkflowContract, WorkflowExecutionPolicy, WorkflowPortContract
from lmola.workflows.schemas import WorkflowInput, WorkflowOutputs, WorkflowRequest, WorkflowStep

MODEL_REGISTRY = {
    "WorkflowRequest": WorkflowRequest,
    "WorkflowInput": WorkflowInput,
    "WorkflowOutputs": WorkflowOutputs,
    "WorkflowStep": WorkflowStep,
    "MoleculeBuildRequest": MoleculeBuildRequest,
    "BuildOptions": BuildOptions,
    "RelaxXtbRequest": RelaxXtbRequest,
    "ValidateStructureRequest": ValidateStructureRequest,
    "ToolResult": ToolResult,
    "ToolCallRecord": ToolCallRecord,
    "PlannerEvalSuite": PlannerEvalSuite,
    "PlannerEvalCase": PlannerEvalCase,
}


def _canonicalize(obj):
    if isinstance(obj, dict):
        return {k: _canonicalize(v) for k, v in sorted(obj.items(), key=lambda kv: kv[0])}
    if isinstance(obj, list):
        return [_canonicalize(v) for v in obj]
    return obj


def export_model_schemas() -> dict:
    models = {name: model.model_json_schema() for name, model in sorted(MODEL_REGISTRY.items())}
    return _canonicalize({"schema_version": "lmola.models.v1", "generated_by": "LMolA", "models": models})


def export_tool_registry_schema() -> dict:
    tools = []
    for tool in list_tools():
        tools.append(
            {
                "name": tool.name,
                "category": tool.category,
                "description": tool.description,
                "input_schema": tool.input_schema,
                "input_json_schema": MODEL_REGISTRY.get(tool.input_schema).model_json_schema() if MODEL_REGISTRY.get(tool.input_schema) else None,
                "required_backends": sorted(tool.required_backends),
                "output_schema": "ToolExecutionResult",
                "safe_execution_notes": tool.notes,
                "allowed_in_planner": True,
                "execution_kind": "validation" if tool.category == "validation" else ("external_cli" if tool.name in {"generate_small_molecule_openbabel", "generate_metal_complex_molsimplify", "relax_structure_xtb"} else "in_process"),
            }
        )
    return _canonicalize({"schema_version": "lmola.tools.v1", "tools": tools, "tool_names": [t["name"] for t in tools]})


def export_workflow_catalog_schema(*, compact: bool = False) -> dict:
    tool_map = {t.name: t for t in list_tools()}
    workflows = []
    for entry in list_workflows():
        canonical_steps = [{"tool": t} for t in entry.tools]
        backends = sorted({b for name in entry.tools for b in tool_map.get(name).required_backends})
        readiness = check_workflow_backend_readiness(entry.workflow_id)
        payload = {
            "workflow_id": entry.workflow_id,
            "task_type": entry.task_type,
            "input_types": entry.input_types,
            "tools": entry.tools,
            "description": entry.description,
            "canonical_steps": canonical_steps,
            "required_backends": backends,
            "contract": entry.contract,
            "readiness": readiness,
            "supported": True,
            "notes": "",
        }
        if compact:
            payload = {
                "workflow_id": entry.workflow_id,
                "task_type": entry.task_type,
                "input_types": entry.input_types,
                "tools": entry.tools,
                "description": entry.description,
                "required_backends": backends,
                "contract": {
                    "operation": entry.contract.get("operation"),
                    "method": entry.contract.get("method"),
                    "geometry_modified": entry.contract.get("geometry_modified"),
                    "cost_class": entry.contract.get("cost_class"),
                },
                "readiness": {
                    "ready": readiness["ready"],
                    "missing_backends": readiness["missing_backends"],
                },
            }
        workflows.append(payload)
    return _canonicalize({"schema_version": "lmola.workflow_catalog.v1", "workflows": workflows, "workflow_ids": [w["workflow_id"] for w in workflows]})


def export_planner_schema_bundle() -> dict:
    full = export_workflow_catalog_schema(compact=False)
    backend_capabilities = {k: v.model_dump() for k, v in list_backend_capabilities().items()}
    unavailable = [k for k, v in backend_capabilities.items() if v.get("status") != "available"]
    return _canonicalize(
        {
            "schema_version": "lmola.planner_context.v1",
            "output_contract": {
                "supported_task": {"required_fields": ["workflow_id", "input"], "optional_fields": ["columns", "outputs", "metadata"]},
                "unsupported_task": {"required_fields": ["status", "reason"], "status_value": "unsupported"},
            },
            "allowed_workflow_ids": full["workflow_ids"],
            "allowed_input_types": sorted({it for wf in full["workflows"] for it in wf.get("input_types", [])}),
            "workflows": [
                {
                    "workflow_id": wf["workflow_id"],
                    "task_type": wf["task_type"],
                    "input_types": wf["input_types"],
                    "canonical_tools": wf["tools"],
                    "description": wf["description"],
                    "required_backends": wf.get("required_backends", []),
                    "readiness": wf.get("readiness", {}),
                    "operation": wf.get("contract", {}).get("operation"),
                    "method": wf.get("contract", {}).get("method"),
                    "input_summary": wf.get("contract", {}).get("input_ports", []),
                    "output_summary": wf.get("contract", {}).get("output_ports", []),
                    "geometry_modified": wf.get("contract", {}).get("geometry_modified"),
                    "cost_class": wf.get("contract", {}).get("cost_class"),
                    "llm_use_when": wf.get("contract", {}).get("llm_use_when", []),
                    "llm_do_not_use_when": wf.get("contract", {}).get("llm_do_not_use_when", []),
                }
                for wf in full["workflows"]
            ],
            "backend_capabilities": backend_capabilities,
            "unavailable_backend_notes": [
                f"Backend {backend_id} is currently unavailable and workflows requiring it must not be selected."
                for backend_id in unavailable
            ],
            "unsupported_task_policy": "Return status='unsupported' with a short reason when no catalog workflow matches the user request.",
            "artifact_contract_summaries": export_artifact_registry(compact=True).get("artifact_contracts", {}),
            "runtime_artifact_manifest_note": "Runtime outputs may include artifact_manifest.json. Use lmola.inspect_artifact_manifest and lmola.get_artifact_compatibility for read-only inspection.",
        }
    )


def export_all_schemas() -> dict:
    model_bundle = export_model_schemas()
    return _canonicalize(
        {
            "schema_version": "lmola.schema_bundle.v1",
            "generated_by": "LMolA",
            "models": model_bundle["models"],
            "model_schema_bundle": model_bundle,
            "tools": export_tool_registry_schema(),
            "workflow_catalog": export_workflow_catalog_schema(compact=False),
            "workflow_catalog_compact": export_workflow_catalog_schema(compact=True),
            "planner_context_compact": export_planner_schema_bundle(),
            "backend_capability_schema": backend_capability_schema(),
            "workflow_contract_schema": WorkflowContract.model_json_schema(),
            "workflow_port_contract_schema": WorkflowPortContract.model_json_schema(),
            "workflow_execution_policy_schema": WorkflowExecutionPolicy.model_json_schema(),
            "workflow_artifact_output_descriptor_schema": WorkflowArtifactOutputDescriptor.model_json_schema(),
            "artifact_contract_schema": ArtifactContract.model_json_schema(),
            "artifact_registry_schema": ArtifactRegistry.model_json_schema(),
            "artifact_manifest_schema": ArtifactManifest.model_json_schema(),
            "artifact_manifest_entry_schema": ArtifactManifestEntry.model_json_schema(),
            "artifact_compatibility_hint_schema": ArtifactCompatibilityHint.model_json_schema(),
            "artifact_contracts": export_artifact_registry(compact=False),
            "artifact_contracts_compact": export_artifact_registry(compact=True),
            "backend_capabilities": {k: v.model_dump() for k, v in list_backend_capabilities().items()},
        }
    )


def write_schema_artifacts(output_dir: str | Path) -> dict:
    base = Path(output_dir)
    if str(base) == "":
        base = Path("outputs")
    target = base
    target.mkdir(parents=True, exist_ok=True)

    files = {
        "schema_bundle.json": export_all_schemas(),
        "model_schemas.json": export_model_schemas(),
        "tool_registry_schema.json": export_tool_registry_schema(),
        "workflow_catalog.json": export_workflow_catalog_schema(compact=False),
        "workflow_catalog.yaml": export_workflow_catalog_schema(compact=False),
        "planner_context_compact.json": export_planner_schema_bundle(),
    }
    for name, payload in files.items():
        path = target / name
        if name.endswith(".yaml"):
            path.write_text(yaml.safe_dump(payload, sort_keys=True), encoding="utf-8")
        else:
            path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    (target / "README_schema.md").write_text(
        "\n".join(
            [
                "# LMolA Schema Export",
                "",
                "- These schemas are generated from LMolA internal definitions.",
                "- LLMs should output WorkflowRequest JSON, not arbitrary commands.",
                "- Canonical workflows are generated by LMolA and not blindly trusted from LLM output.",
                "- Schema export is LLM-engine agnostic.",
                "- Ollama is one possible backend and not a schema dependency.",
            ]
        ),
        encoding="utf-8",
    )
    return {"status": "ok", "output_dir": str(target), "files": sorted([*files.keys(), "README_schema.md"])}
