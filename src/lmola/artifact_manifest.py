from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from lmola.artifact_contracts import ARTIFACT_CONTRACT_SCHEMA_VERSION, export_artifact_registry
from lmola.workflows.catalog import get_workflow_entry



def _safe_path(path: str | Path) -> Path:
    p = Path(path).expanduser().resolve()
    repo = Path.cwd().resolve()
    allowed = [repo / "outputs", repo / "examples", Path("/tmp")]
    if not any(p == root or root in p.parents for root in allowed):
        raise ValueError("unsafe_path")
    if str(p).startswith("/tmp") and "lmola" not in str(p):
        raise ValueError("unsafe_path")
    return p
ARTIFACT_MANIFEST_SCHEMA_VERSION = "lmola.artifact_manifest.v1"


class ArtifactCompatibilityHint(BaseModel):
    workflow_id: str
    reason: str
    source_artifact_id: str | None = None
    source_artifact_type: str | None = None
    compatibility_level: Literal["direct", "conditional", "informational"] = "informational"
    input_mapping: dict[str, Any] = Field(default_factory=dict)
    geometry_modified: bool | None = None
    requires_confirmation: bool = True
    requires_allow_execution: bool = True
    dry_run_recommended: bool = True
    safety_notes: list[str] = Field(default_factory=lambda: ["Compatibility hints are informational and do not grant execution permission."])


class ArtifactManifestEntry(BaseModel):
    artifact_id: str
    artifact_type: str
    path: str
    scope: Literal["batch", "item", "step", "audit"] = "batch"
    item_id: str | None = None
    status: Literal["ok", "error", "missing", "unknown"] = "unknown"
    created_by_workflow: str | None = None
    created_by_step: str | None = None
    produced_on: Literal["success", "failure", "always", "unknown"] = "unknown"
    geometry_modified: bool | None = None
    artifact_contract_schema_version: str | None = None
    semantic_tags: list[str] = Field(default_factory=list)
    properties: dict[str, Any] = Field(default_factory=dict)
    next_compatible_workflows: list[ArtifactCompatibilityHint] = Field(default_factory=list)


class ArtifactManifest(BaseModel):
    schema_version: str = ARTIFACT_MANIFEST_SCHEMA_VERSION
    manifest_kind: Literal["batch", "item", "mcp_audit", "agent_smoke"] = "batch"
    batch_id: str | None = None
    workflow_id: str | None = None
    root_path: str
    status: Literal["ok", "partial", "error"] = "ok"
    created_at: str | None = None
    generated_by: str = "lmola.artifact_manifest"
    workflow_contract_schema_version: str = "lmola.workflow_contract.v1"
    artifact_contract_schema_version: str = ARTIFACT_CONTRACT_SCHEMA_VERSION
    artifacts: list[ArtifactManifestEntry] = Field(default_factory=list)
    next_compatible_workflows: list[ArtifactCompatibilityHint] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def _compat_for_type(artifact_type: str, artifact_id: str) -> list[ArtifactCompatibilityHint]:
    geom = {"xyz_geometry", "validated_xyz", "generated_xyz", "relaxed_xyz"}
    if artifact_type in geom:
        workflows = ["validate_xyz", "xyz_to_geometry_analysis", "xyz_to_xtb_singlepoint", "xyz_to_xtb_relax", "count_element_atoms", "split_molecule_by_file_order"]
        out = [ArtifactCompatibilityHint(workflow_id=w, reason="Structure-like artifact can be consumed.", source_artifact_id=artifact_id, source_artifact_type=artifact_type, compatibility_level="direct", input_mapping={"input.path": "$artifact.path"}) for w in workflows]
        if artifact_type == "relaxed_xyz":
            out.append(ArtifactCompatibilityHint(workflow_id="compare_two_geometries", reason="Requires pairing with another geometry.", source_artifact_id=artifact_id, source_artifact_type=artifact_type, compatibility_level="conditional"))
        return out
    if artifact_type in {"xtb_singlepoint_result", "xtb_relax_result", "rmsd_report", "geometry_comparison_report", "descriptor_filter_report", "molecule_split_report"}:
        return [ArtifactCompatibilityHint(workflow_id="summarize_artifacts", reason="Artifact supports read-only summarization.", source_artifact_id=artifact_id, source_artifact_type=artifact_type)]
    if artifact_type == "rdkit_descriptor_table":
        return [ArtifactCompatibilityHint(workflow_id="filter_molecules_by_descriptors", reason="Descriptor table may be filterable.", source_artifact_id=artifact_id, source_artifact_type=artifact_type, compatibility_level="conditional")]
    return []


def generate_batch_artifact_manifest(batch_dir: str | Path) -> ArtifactManifest:
    p = Path(batch_dir).resolve()
    wr = p / "workflow_result.json"
    result = json.loads(wr.read_text(encoding="utf-8")) if wr.exists() else {}
    workflow_id = result.get("workflow_id")
    artifact_registry = export_artifact_registry(compact=False).get("artifact_contracts", {})
    outputs = []
    if workflow_id:
        try:
            contract = get_workflow_entry(workflow_id).contract or {}
            outputs = contract.get("artifact_outputs", []) if isinstance(contract, dict) else []
        except Exception:
            outputs = []
    artifacts: list[ArtifactManifestEntry] = []
    for idx, desc in enumerate(outputs):
        if not isinstance(desc, dict):
            continue
        file_name = f"artifact_{idx}.json"
        out_path = p / file_name
        aid = str(desc.get("name") or f"artifact_{idx}")
        atype = str(desc.get("artifact_type") or "unknown")
        contract = artifact_registry.get(atype, {}) if isinstance(artifact_registry, dict) else {}
        entry = ArtifactManifestEntry(
            artifact_id=aid,
            artifact_type=atype,
            path=str(out_path.relative_to(p)) if out_path.exists() else file_name,
            scope="batch",
            status="ok" if out_path.exists() else "missing",
            created_by_workflow=workflow_id,
            produced_on=str(desc.get("produced_on", "unknown")),
            geometry_modified=desc.get("geometry_modified"),
            artifact_contract_schema_version=contract.get("schema_version"),
            semantic_tags=contract.get("semantic_tags", []),
            next_compatible_workflows=_compat_for_type(atype, aid),
        )
        artifacts.append(entry)
    mstatus = "ok" if all(a.status == "ok" for a in artifacts) else "partial"
    mf = ArtifactManifest(batch_id=p.name, workflow_id=workflow_id, root_path=str(p), status=mstatus, artifacts=artifacts)
    hints: list[ArtifactCompatibilityHint] = []
    for a in artifacts:
        hints.extend(a.next_compatible_workflows)
    uniq: dict[tuple[str, str | None], ArtifactCompatibilityHint] = {}
    for h in hints:
        uniq[(h.workflow_id, h.source_artifact_type)] = h
    mf.next_compatible_workflows = list(uniq.values())
    return mf


def write_batch_artifact_manifest(batch_dir: str | Path) -> dict[str, Any]:
    p = Path(batch_dir)
    manifest = generate_batch_artifact_manifest(p)
    out = p / "artifact_manifest.json"
    out.write_text(json.dumps(manifest.model_dump(), indent=2, sort_keys=True), encoding="utf-8")
    return {"status": "ok", "artifact_manifest_path": str(out), "manifest": manifest.model_dump()}


def inspect_manifest(path: str | Path) -> dict[str, Any]:
    try:
        p = _safe_path(path)
    except ValueError:
        return {"status": "error", "error_type": "unsafe_path", "path": str(path)}
    m = p if p.name == "artifact_manifest.json" else p / "artifact_manifest.json"
    if not m.exists():
        return {"status": "error", "error_type": "manifest_not_found", "path": str(m)}
    payload = json.loads(m.read_text(encoding="utf-8"))
    ArtifactManifest.model_validate(payload)
    return {"status": "ok", "manifest": payload, "artifact_manifest_path": str(m)}


def get_compatibility(path: str | Path) -> dict[str, Any]:
    ins = inspect_manifest(path)
    if ins.get("status") != "ok":
        return ins
    manifest = ArtifactManifest.model_validate(ins["manifest"])
    return {
        "status": "ok",
        "artifact_manifest_path": ins["artifact_manifest_path"],
        "manifest_next_compatible_workflows": [h.model_dump() for h in manifest.next_compatible_workflows],
        "artifact_next_compatible_workflows": [{"artifact_id": a.artifact_id, "artifact_type": a.artifact_type, "next_compatible_workflows": [h.model_dump() for h in a.next_compatible_workflows]} for a in manifest.artifacts],
    }
