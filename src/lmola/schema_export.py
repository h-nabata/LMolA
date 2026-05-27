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
from lmola.llm_contract_catalog import NextActionItem, NextActionRecommendation, export_llm_contract_catalog
from lmola.workflows import check_workflow_backend_readiness, list_workflows
from lmola.workflows.catalog import WorkflowArtifactOutputDescriptor, WorkflowContract, WorkflowExecutionPolicy, WorkflowPortContract
from lmola.workflows.schemas import WorkflowInput, WorkflowOutputs, WorkflowRequest, WorkflowStep
from lmola.human_prompt_normalization import CandidateWorkflow, HumanPromptNormalizedIntent, HumanPromptNormalizationResult
from lmola.parameter_binding import ParameterValue, InputFileBinding, ElectronicStateBinding, SolventBinding, PeriodicBinding, AtomSelectionBinding, CalculationControlsBinding, GeometryOptimizationControls, BoundParameterSet, ParameterBindingResult
from lmola.clarification import ClarificationQuestion, ClarificationPlan

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
    "HumanPromptNormalizedIntent": HumanPromptNormalizedIntent,
    "HumanPromptNormalizationResult": HumanPromptNormalizationResult,
    "CandidateWorkflow": CandidateWorkflow,
    "ParameterValue": ParameterValue,
    "InputFileBinding": InputFileBinding,
    "ElectronicStateBinding": ElectronicStateBinding,
    "SolventBinding": SolventBinding,
    "PeriodicBinding": PeriodicBinding,
    "AtomSelectionBinding": AtomSelectionBinding,
    "CalculationControlsBinding": CalculationControlsBinding,
    "GeometryOptimizationControls": GeometryOptimizationControls,
    "BoundParameterSet": BoundParameterSet,
    "ParameterBindingResult": ParameterBindingResult,
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
            "artifact_manifest_runtime": {
                "schema_version": "lmola.artifact_manifest.v1",
                "manifest_filename": "artifact_manifest.json",
                "inspection_tools": ["lmola.inspect_artifact_manifest", "lmola.get_artifact_compatibility", "lmola.get_compact_contract_catalog", "lmola.recommend_next_actions"],
                "compatibility_field": "next_compatible_workflows",
                "notes": [
                    "Compact contract catalog available via lmola.get_compact_contract_catalog.",
                    "Next-action recommendations available via lmola.recommend_next_actions.",
                    "result artifacts are not geometries",
                    "Compatibility hints are read-only.",
                    "Compatibility hints do not grant execution permission.",
                    "Confirmed execution still requires dry_run=false, allow_execution=true, and confirm=true.",
                    "Human prompt normalization available via lmola.normalize_human_prompt.",
                    "Use lmola workflow eval-human-prompts as benchmark.",
                    "Ambiguous prompts must not force execution.",
                    "execution_allowed remains false at normalization stage.",
                    "Parameter binding available via lmola.bind_human_prompt_parameters and lmola workflow bind-parameters.",
                    "Parameter binding reports missing_parameters, assumed_defaults, clarification_recommended, unsupported_parameters, backend_specific.",
                    "Optional backend controls use workflow/backend defaults.",
                    "Clarification handling available via lmola.generate_clarification_plan and lmola workflow clarify-parameters.",
                    "missing_parameters become required_questions.",
                    "clarification_recommended become recommended_questions.",
                    "assumed_defaults should not block planning.",
                ],
            },
            "human_prompt_normalization": {
                "purpose": "Normalize a human prompt into a structured intent without executing chemistry.",
                "tool": "lmola.normalize_human_prompt",
                "benchmark": "lmola workflow eval-human-prompts",
                "ambiguous_policy": "If a human prompt is ambiguous, return ambiguous or needs_clarification rather than forcing a workflow.",
                "artifact_policy": "result artifacts are not geometries",
                "safety": {
                    "execution_allowed": False,
                    "dry_run_recommended": True,
                    "requires_confirmation": True,
                    "requires_allow_execution": True,
                },
            },
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
            "llm_contract_catalog_schema": {"schema_version": "lmola.llm_contract_catalog.v1", "example": export_llm_contract_catalog()},
            "next_action_recommendation_schema": NextActionRecommendation.model_json_schema(),
            "next_action_item_schema": NextActionItem.model_json_schema(),
            "artifact_contracts": export_artifact_registry(compact=False),
            "artifact_contracts_compact": export_artifact_registry(compact=True),
            "human_prompt_normalized_intent_schema": HumanPromptNormalizedIntent.model_json_schema(),
            "human_prompt_normalization_result_schema": HumanPromptNormalizationResult.model_json_schema(),
            "human_prompt_candidate_workflow_schema": CandidateWorkflow.model_json_schema(),
            "human_prompt_normalization_eval_schema": {"schema_version": "lmola.human_prompt_normalization_eval.v1", "required_fields": ["normalized_intent", "candidate_workflows", "missing_parameters", "clarification_questions", "execution_allowed", "dry_run_recommended", "result_artifact_as_geometry_error_rate", "forced_selection_on_ambiguous_prompt_rate"]},
            "parameter_value_schema": ParameterValue.model_json_schema(),
            "input_file_binding_schema": InputFileBinding.model_json_schema(),
            "electronic_state_binding_schema": ElectronicStateBinding.model_json_schema(),
            "solvent_binding_schema": SolventBinding.model_json_schema(),
            "periodic_binding_schema": PeriodicBinding.model_json_schema(),
            "atom_selection_binding_schema": AtomSelectionBinding.model_json_schema(),
            "calculation_controls_binding_schema": CalculationControlsBinding.model_json_schema(),
            "geometry_optimization_controls_schema": GeometryOptimizationControls.model_json_schema(),
            "bound_parameter_set_schema": BoundParameterSet.model_json_schema(),
            "parameter_binding_result_schema": ParameterBindingResult.model_json_schema(),
            "parameter_binding_eval_schema": {"schema_version": "lmola.parameter_binding_eval.v1", "required_fields": ["bound_parameters", "missing_parameters", "assumed_defaults", "clarification_recommended", "unsupported_parameters", "backend_specific", "execution_allowed", "dry_run_recommended"]},

            "clarification_question_schema": ClarificationQuestion.model_json_schema(),
            "clarification_plan_schema": ClarificationPlan.model_json_schema(),
            "clarification_eval_schema": {"schema_version": "lmola.clarification_eval.v1", "required_fields": ["required_questions", "recommended_questions", "optional_questions", "unsupported_notes", "can_create_dry_run_plan", "can_execute", "execution_allowed", "dry_run_recommended"]},
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
