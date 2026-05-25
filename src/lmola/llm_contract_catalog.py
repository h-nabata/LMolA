from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from lmola.artifact_contracts import ARTIFACT_CONTRACT_SCHEMA_VERSION, export_artifact_registry
from lmola.artifact_manifest import ArtifactManifest, inspect_manifest
from lmola.workflows import check_workflow_backend_readiness, list_workflows

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

GEOMETRY_ARTIFACT_TYPES = {"relaxed_xyz", "generated_xyz", "validated_xyz", "xyz_geometry"}
RESULT_ARTIFACT_TYPES = {
    "xtb_singlepoint_result",
    "xtb_relax_result",
    "rdkit_descriptor_table",
    "descriptor_filter_report",
    "geometry_analysis_report",
    "rmsd_report",
    "geometry_comparison_report",
    "molecule_split_report",
}

LLM_CATALOG_SCHEMA_VERSION = "lmola.llm_contract_catalog.v1"
NEXT_ACTION_SCHEMA_VERSION = "lmola.next_action_recommendation.v1"


class NextActionItem(BaseModel):
    action_id: str
    workflow_id: str | None = None
    action_type: Literal["workflow", "inspect", "summarize", "triage", "stop"]
    source_artifact_id: str | None = None
    source_artifact_type: str | None = None
    compatibility_level: Literal["direct", "conditional", "informational"] = "informational"
    reason: str
    input_mapping: dict[str, Any] = Field(default_factory=dict)
    geometry_modified: bool | None = None
    dry_run_recommended: bool = True
    requires_confirmation: bool = True
    requires_allow_execution: bool = True
    execution_allowed: bool = False
    safety_notes: list[str] = Field(default_factory=list)


class NextActionRecommendation(BaseModel):
    status: Literal["ok"] = "ok"
    schema_version: Literal["lmola.next_action_recommendation.v1"] = NEXT_ACTION_SCHEMA_VERSION
    source_path: str
    manifest_schema_version: str
    recommended_next_actions: list[NextActionItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def export_llm_contract_catalog(*, compact: bool = True) -> dict[str, Any]:
    registry = export_artifact_registry(compact=True).get("artifact_contracts", {})
    workflows = []
    for wf in list_workflows():
        c = wf.contract or {}
        outs = [a.get("artifact_type") for a in c.get("artifact_outputs", []) if isinstance(a, dict)]
        workflows.append(
            {
                "workflow_id": wf.workflow_id,
                "task_type": wf.task_type,
                "operation": c.get("operation"),
                "method": c.get("method"),
                "input_types": wf.input_types,
                "input_artifact_types": wf.input_types,
                "output_artifact_types": outs,
                "geometry_modified": c.get("geometry_modified"),
                "required_backends": wf.required_backends,
                "readiness": check_workflow_backend_readiness(wf.workflow_id),
                "safe_for_confirmed_smoke": c.get("safe_for_confirmed_smoke", False),
                "execution_policy": {
                    "dry_run_default": True,
                    "requires_allow_execution": True,
                    "requires_confirm": True,
                    "mcp_allowlisted": wf.workflow_id in MCP_EXECUTION_ALLOWLIST,
                    "low_level_direct_call_allowed": False,
                },
                "llm_use_when": c.get("llm_use_when", []),
                "llm_do_not_use_when": c.get("llm_do_not_use_when", []),
                "compact_summary": f"{wf.workflow_id}: {wf.description}",
            }
        )
    return {
        "status": "ok",
        "schema_version": LLM_CATALOG_SCHEMA_VERSION,
        "workflow_contract_schema_version": "lmola.workflow_contract.v1",
        "artifact_contract_schema_version": ARTIFACT_CONTRACT_SCHEMA_VERSION,
        "workflow_count": len(workflows),
        "artifact_count": len(registry),
        "workflows": workflows,
        "artifact_types": registry,
        "selection_policy": {
            "result_artifacts_are_not_geometries": True,
            "compatibility_hints_do_not_grant_execution": True,
            "confirmed_execution_requires": ["dry_run=false", "allow_execution=true", "confirm=true"],
        },
    }


def recommend_next_actions(path: str, *, compact: bool = True) -> dict[str, Any]:
    ins = inspect_manifest(path)
    if ins.get("status") != "ok":
        return ins
    manifest = ArtifactManifest.model_validate(ins["manifest"])
    recommended_next_actions: list[NextActionItem] = []
    for artifact in manifest.artifacts:
        if artifact.artifact_type in GEOMETRY_ARTIFACT_TYPES:
            recommended_next_actions.append(
                NextActionItem(
                    action_id=f"act_{artifact.artifact_id}_geometry",
                    workflow_id="xyz_to_geometry_analysis",
                    action_type="workflow",
                    source_artifact_id=artifact.artifact_id,
                    source_artifact_type=artifact.artifact_type,
                    compatibility_level="direct",
                    reason="Geometry artifact can feed geometry workflows.",
                    input_mapping={"input.path": "$artifact.path"},
                    geometry_modified=False,
                    execution_allowed=False,
                    safety_notes=["Recommendation only; does not authorize execution."],
                )
            )
        elif artifact.artifact_type in RESULT_ARTIFACT_TYPES:
            recommended_next_actions.append(
                NextActionItem(
                    action_id=f"act_{artifact.artifact_id}_inspect",
                    action_type="summarize",
                    source_artifact_id=artifact.artifact_id,
                    source_artifact_type=artifact.artifact_type,
                    compatibility_level="informational",
                    reason="Result/report artifacts should be summarized/triaged, not treated as geometry.",
                    execution_allowed=False,
                    safety_notes=["Result artifacts are not geometries."],
                )
            )
    if not recommended_next_actions:
        recommended_next_actions.append(
            NextActionItem(
                action_id="act_stop",
                action_type="stop",
                reason="No safe next action identified.",
                execution_allowed=False,
                safety_notes=["Do not invent workflows; request user guidance."],
            )
        )
    payload = NextActionRecommendation(
        source_path=str(Path(path)),
        manifest_schema_version=manifest.schema_version,
        recommended_next_actions=recommended_next_actions,
    )
    return payload.model_dump()
