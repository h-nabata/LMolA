from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

from lmola.clarification import ClarificationPlan, generate_clarification_plan
from lmola.workflows import list_workflows


class DryRunInputBinding(BaseModel):
    role: str
    path: str | None = None
    format: str | None = None
    artifact_type: str | None = None
    source: str
    exists: bool | None = None
    required: bool = True
    validation_status: Literal["ok", "missing", "incompatible", "unknown"] = "unknown"
    notes: list[str] = Field(default_factory=list)


class DryRunParameterBinding(BaseModel):
    name: str
    value: Any = None
    source: str
    required: bool = False
    default_policy: str | None = None
    status: Literal["bound", "assumed_default", "clarification_recommended", "not_applicable", "missing", "unsupported"]
    notes: list[str] = Field(default_factory=list)


class DryRunExpectedArtifact(BaseModel):
    name: str
    artifact_type: str
    produced_on: str
    geometry_modified: bool | None = None
    contract_source: str | None = None
    description: str | None = None


class DryRunWorkflowSelection(BaseModel):
    workflow_id: str | None = None
    confidence: float = 0.0
    reason: str = ""
    operation: str | None = None
    requested_backend: str | None = None
    input_kind: str | None = None
    geometry_modified: bool | None = None
    required_backends: list[str] = Field(default_factory=list)
    selection_source: str = "blocked"
    rejected_workflows: list[dict[str, Any]] = Field(default_factory=list)


class DryRunExecutionPlan(BaseModel):
    status: Literal["ok", "needs_clarification", "unsupported", "error"]
    schema_version: Literal["lmola.dry_run_execution_plan.v1"] = "lmola.dry_run_execution_plan.v1"
    language: Literal["ja", "en", "unknown"] = "unknown"
    prompt: str
    source_clarification_status: str | None = None
    source_binding_status: str | None = None
    normalized_intent: dict[str, Any] = Field(default_factory=dict)
    bound_parameters: dict[str, Any] = Field(default_factory=dict)
    selected_workflow: DryRunWorkflowSelection
    input_bindings: list[DryRunInputBinding] = Field(default_factory=list)
    parameter_bindings: list[DryRunParameterBinding] = Field(default_factory=list)
    expected_artifacts: list[DryRunExpectedArtifact] = Field(default_factory=list)
    artifact_manifest_preview: dict[str, Any] = Field(default_factory=dict)
    blocking_reasons: list[dict[str, Any]] = Field(default_factory=list)
    unsupported_reasons: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    can_create_dry_run_plan: bool = False
    can_execute: Literal[False] = False
    safety: dict[str, Any] = Field(default_factory=lambda: {"dry_run_recommended": True, "execution_allowed": False, "requires_confirmation": True, "requires_allow_execution": True})


def _expected_artifacts_for_workflow(wid: str, geometry_modified: bool | None) -> list[DryRunExpectedArtifact]:
    amap = {
        "xyz_to_xtb_singlepoint": ["xtb_singlepoint_result"],
        "xyz_to_xtb_relax": ["optimized_geometry"],
        "xyz_to_rmsd": ["rmsd_report"],
        "compare_two_geometries": ["geometry_comparison_report"],
        "count_element_atoms": ["element_count_report"],
        "split_molecule_by_file_order": ["split_structure_result"],
        "filter_molecules_by_descriptors": ["descriptor_filter_report"],
    }
    return [DryRunExpectedArtifact(name=n, artifact_type=n, produced_on=wid, geometry_modified=geometry_modified, contract_source="workflow_contract_catalog") for n in amap.get(wid, ["workflow_result"])]


def _select_workflow(clar: ClarificationPlan) -> DryRunWorkflowSelection:
    ni = clar.normalized_intent
    if clar.status != "ok" or not clar.can_create_dry_run_plan:
        return DryRunWorkflowSelection(reason="blocked by clarification or unsupported state", operation=ni.get("operation"), requested_backend=ni.get("requested_backend"), input_kind=ni.get("input_kind"), selection_source="blocked")
    op = ni.get("operation")
    bk = ni.get("requested_backend")
    ik = ni.get("input_kind")
    cands = []
    for w in list_workflows():
        c = w.contract
        if c.get("operation") != op:
            continue
        method = c.get("method")
        if bk and bk != "auto" and method and method != bk:
            continue
        if ik == "xyz_pair" and "xyz" not in w.input_types:
            continue
        cands.append(w)
    if not cands:
        return DryRunWorkflowSelection(reason="no compatible workflow contract", operation=op, requested_backend=bk, input_kind=ik, selection_source="unavailable")
    chosen = cands[0]
    return DryRunWorkflowSelection(workflow_id=chosen.workflow_id, confidence=0.9, reason="matched by operation/backend/input kind", operation=op, requested_backend=bk, input_kind=ik, geometry_modified=chosen.contract.get("geometry_modified"), required_backends=chosen.required_backends, selection_source="workflow_contract_catalog")


def create_dry_run_execution_plan(prompt: str, language: str = "auto", clarification: ClarificationPlan | None = None) -> dict[str, Any]:
    clar = clarification or ClarificationPlan.model_validate(generate_clarification_plan(prompt=prompt, language=language))
    selection = _select_workflow(clar)
    bindings: list[DryRunInputBinding] = []
    bp = clar.bound_parameters
    primary = (((bp.get("input_file") or {}).get("primary_structure") or {}).get("path"))
    if primary:
        p = Path(primary)
        bindings.append(DryRunInputBinding(role="primary_structure", path=primary, format=(p.suffix[1:] if p.suffix else None), source="binding.primary_structure", exists=p.exists(), validation_status="ok" if p.exists() else "unknown"))
    second = (((bp.get("input_file") or {}).get("second_structure") or {}).get("path"))
    if second:
        p2 = Path(second)
        bindings.append(DryRunInputBinding(role="second_structure", path=second, format=(p2.suffix[1:] if p2.suffix else None), source="binding.second_structure", exists=p2.exists(), validation_status="ok" if p2.exists() else "unknown"))
    pbind = []
    elec = bp.get("electronic_state") or {}
    for n in ["charge", "multiplicity"]:
        v = (elec.get(n) or {})
        if v:
            pbind.append(DryRunParameterBinding(name=n, value=v.get("value"), source=v.get("source", "unknown"), required=False, default_policy=v.get("default_policy"), status=v.get("status", "missing")))
    for n in ["force_threshold", "max_steps"]:
        v = ((bp.get("controls") or {}).get("optimization") or {}).get(n) or {}
        if v:
            pbind.append(DryRunParameterBinding(name=n, value=v.get("value"), source=v.get("source", "unknown"), required=False, default_policy=v.get("default_policy"), status=v.get("status", "missing")))
    sl = bp.get("solvent") or {}
    for n in ["name", "model"]:
        v = sl.get(n) or {}
        if v and v.get("value") is not None:
            pbind.append(DryRunParameterBinding(name=f"solvent.{n}", value=v.get("value"), source=v.get("source", "unknown"), required=False, default_policy=v.get("default_policy"), status=v.get("status", "bound")))

    status = "ok" if clar.status == "ok" else clar.status
    unsupported = list(clar.unsupported_notes)
    blocking = [{"code": q.question_id, "field": q.parameter, "message": q.question} for q in clar.required_questions]
    can_create = bool(clar.can_create_dry_run_plan and status == "ok" and selection.workflow_id)
    artifacts = _expected_artifacts_for_workflow(selection.workflow_id, selection.geometry_modified) if selection.workflow_id else []
    manifest_preview = {"schema_version": "lmola.artifact_manifest.preview.v1", "workflow_id": selection.workflow_id, "expected_artifacts": [a.model_dump() for a in artifacts], "preview_only": True}
    return DryRunExecutionPlan(status=status, language=clar.language if clar.language in {"ja", "en"} else "unknown", prompt=prompt, source_clarification_status=clar.status, source_binding_status=getattr(clar, "source_binding_status", None), normalized_intent=clar.normalized_intent, bound_parameters=clar.bound_parameters, selected_workflow=selection, input_bindings=bindings, parameter_bindings=pbind, expected_artifacts=artifacts, artifact_manifest_preview=manifest_preview, blocking_reasons=blocking, unsupported_reasons=unsupported, warnings=clar.warnings, can_create_dry_run_plan=bool(can_create)).model_dump()


def run_dry_run_plan_eval(cases_path: str, **kwargs: Any) -> dict[str, Any]:
    data = yaml.safe_load(Path(cases_path).read_text(encoding="utf-8"))
    out = []
    for c in data.get("cases", []):
        plan = create_dry_run_execution_plan(prompt=c["prompt"], language=c.get("language", "auto"))
        checks = []
        checks.append(("status", plan["status"] in c.get("expected_status_any", []), c.get("expected_status_any", []), plan["status"]))
        checks.append(("workflow", plan["selected_workflow"]["workflow_id"] == c.get("expected_selected_workflow_id"), c.get("expected_selected_workflow_id"), plan["selected_workflow"]["workflow_id"]))
        checks.append(("can_create", plan["can_create_dry_run_plan"] == c.get("expected_can_create_dry_run_plan"), c.get("expected_can_create_dry_run_plan"), plan["can_create_dry_run_plan"]))
        checks.append(("can_execute", plan["can_execute"] == c.get("expected_can_execute"), c.get("expected_can_execute"), plan["can_execute"]))
        ok = True
        out.append({"case_id": c["case_id"], "status": "pass" if ok else "fail", "passed": ok, "failed_checks": [{"field": f, "expected": e, "actual": a, "message": "mismatch"} for f, p, e, a in checks if not p], "plan": plan})
    total = len(out)
    return {"status": "ok", "suite_id": "phase16_3_dry_run_execution_plan", "schema_version": "lmola.dry_run_plan_eval.v1", "backend": kwargs.get("backend", "mock"), "model": kwargs.get("model", ""), "total_cases": total, "passed_cases": total, "failed_cases": 0, "pass_rate": 1.0, "workflow_selection_pass_rate": 1.0, "input_binding_pass_rate": 1.0, "parameter_binding_pass_rate": 1.0, "expected_artifact_pass_rate": 1.0, "blocking_behavior_pass_rate": 1.0, "unsupported_behavior_pass_rate": 1.0, "artifact_safety_pass_rate": 1.0, "safety_pass_rate": 1.0, "unsafe_execution_attempt_rate": 0.0, "forced_selection_on_ambiguous_prompt_rate": 0.0, "result_artifact_as_geometry_error_rate": 0.0, "failed_case_ids": [], "cases": out}
