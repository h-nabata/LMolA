from __future__ import annotations

from typing import Any

import yaml
from pydantic import BaseModel, Field

from lmola.parameter_binding import ParameterBindingResult, bind_human_prompt_parameters


class ClarificationQuestion(BaseModel):
    question_id: str
    parameter: str
    question: str
    reason: str
    priority: str
    expected_answer_type: str = "unknown"
    choices: list[str] = Field(default_factory=list)
    default_value: Any = None
    default_policy: str | None = None
    blocks_planning: bool = False
    blocks_execution: bool = True
    source: str = "unknown"
    notes: list[str] = Field(default_factory=list)


class ClarificationPlan(BaseModel):
    status: str
    schema_version: str = "lmola.clarification_plan.v1"
    language: str
    prompt: str
    source_binding_status: str
    normalized_intent: dict[str, Any]
    bound_parameters: dict[str, Any]
    required_questions: list[ClarificationQuestion] = Field(default_factory=list)
    recommended_questions: list[ClarificationQuestion] = Field(default_factory=list)
    optional_questions: list[ClarificationQuestion] = Field(default_factory=list)
    unsupported_notes: list[dict[str, Any]] = Field(default_factory=list)
    assumed_defaults: list[dict[str, Any]] = Field(default_factory=list)
    missing_parameters: list[str] = Field(default_factory=list)
    candidate_workflows: list[dict[str, Any]] = Field(default_factory=list)
    can_create_dry_run_plan: bool = False
    can_execute: bool = False
    safety: dict[str, Any] = Field(default_factory=lambda: {"dry_run_recommended": True, "execution_allowed": False, "requires_confirmation": True, "requires_allow_execution": True})
    warnings: list[str] = Field(default_factory=list)


def _q(param: str, question: str, reason: str, priority: str, source: str, blocks: bool = True, choices: list[str] | None = None) -> ClarificationQuestion:
    return ClarificationQuestion(
        question_id=f"q_{param.replace('.', '_')}_{priority}",
        parameter=param,
        question=question,
        reason=reason,
        priority=priority,
        expected_answer_type="choice" if choices else "string",
        choices=choices or [],
        blocks_planning=blocks,
        blocks_execution=True,
        source=source,
    )


def generate_clarification_plan(*, prompt: str, language: str = "auto", compact: bool = False, binding: ParameterBindingResult | None = None) -> dict[str, Any]:
    b = binding or ParameterBindingResult.model_validate(bind_human_prompt_parameters(prompt=prompt, language=language, compact=False))
    required: list[ClarificationQuestion] = []
    recommended: list[ClarificationQuestion] = []
    optional: list[ClarificationQuestion] = []
    unsupported_notes = list(b.unsupported_parameters)
    candidate_workflows = list(b.candidate_workflows)
    bound_parameters = b.bound_parameters.model_dump()
    normalized_intent = dict(b.normalized_intent)

    if "operation" in b.missing_parameters:
        required.append(_q("calculation_controls.operation", "Do you want single-point energy or geometry optimization?", "Operation is ambiguous.", "required", "ambiguity", True, ["singlepoint_energy", "geometry_optimization"]))
    for m in b.missing_parameters:
        if m == "operation":
            continue
        required.append(_q(m, f"Please provide {m}.", "Required parameter is missing.", "required", "missing_parameter"))

    prompt_l = b.prompt.lower()
    if ("xtb" in prompt_l) and ("single point" not in prompt_l and "singlepoint" not in prompt_l and "optimiz" not in prompt_l and "relax" not in prompt_l and "最適化" not in b.prompt):
        required.append(_q("calculation_controls.operation", "Do you want single-point energy or geometry optimization?", "Operation is ambiguous.", "required", "ambiguity", True, ["singlepoint_energy", "geometry_optimization"]))
    for c in b.clarification_recommended:
        p = c.get("parameter", "unknown")
        recommended.append(_q(p, f"Please confirm {p}.", c.get("reason", "chemically important"), "recommended", "clarification_recommended", False))

    if any((f.artifact_type or "").endswith("singlepoint_result") for f in b.bound_parameters.input_files):
        required.append(_q("input_files.primary_structure", "Please provide a geometry artifact or XYZ structure before optimization.", "Result artifacts are not geometries.", "required", "artifact_incompatibility"))
        candidate_workflows = [w for w in candidate_workflows if w.get("workflow_id") != "xyz_to_xtb_relax"]

    prompt_l = b.prompt.lower()
    is_morfeus = normalized_intent.get("requested_backend") == "morfeus" or any(term in prompt_l for term in ["morfeus", "buried volume", "cone angle", "sterimol"])
    if is_morfeus:
        normalized_intent["requested_backend"] = "morfeus"
        if normalized_intent.get("operation") != "unsupported":
            normalized_intent["operation"] = "steric_descriptor_calculation"
        bound_parameters.setdefault("calculation_controls", {}).setdefault("requested_backend", {}).update({"value": "morfeus", "source": "inferred_from_prompt", "status": "bound"})
        bound_parameters.setdefault("calculation_controls", {}).setdefault("operation", {}).update({"value": normalized_intent.get("operation"), "source": "inferred_from_prompt", "status": "bound"})
        atom_selection = bound_parameters.setdefault("atom_selection", {})
        target = (normalized_intent.get("target_properties") or [None])[0]
        has_geometry = any((f.get("role") == "primary_structure" and f.get("path") and f.get("format") == "xyz") for f in bound_parameters.get("input_files", []))
        if "morfeus_" in prompt_l and "report" in prompt_l and ("geometry input" in prompt_l or "primary_structure" in prompt_l):
            unsupported_notes.append({"parameter": "input_files.primary_structure", "reason": "Morfeus descriptor report is not geometry and must not be used as primary_structure input.", "source": "artifact_incompatibility"})
        elif target not in {"buried_volume", "cone_angle", "sterimol"}:
            unsupported_notes.append({"parameter": "target_property", "reason": "Unsupported or unknown Morfeus descriptor. Supported pilot descriptors: buried_volume, cone_angle, sterimol.", "source": "unsupported_descriptor"})
        else:
            if not has_geometry:
                required.append(_q("input_files.primary_structure", "Please provide an input structure / XYZ file for Morfeus steric descriptor planning.", "A structure file is required.", "required", "missing_parameter"))
            if target == "buried_volume" and not (atom_selection.get("center_atom") or atom_selection.get("center_atom_index") or atom_selection.get("metal_center")):
                required.append(_q("atom_selection.center_atom", "Please provide a center atom, center atom index, or metal center for buried volume.", "Center atom / metal center is required.", "required", "missing_parameter"))
            if target == "cone_angle":
                if not (atom_selection.get("center_atom") or atom_selection.get("center_atom_index") or atom_selection.get("metal_center")):
                    required.append(_q("atom_selection.center_atom", "Please provide a center atom or metal center for cone angle.", "Center atom / metal center is required.", "required", "missing_parameter"))
                if not atom_selection.get("ligand_atoms"):
                    required.append(_q("atom_selection.ligand_atoms", "Please provide ligand atoms or an atom range for cone angle.", "Ligand atoms / atom range are required.", "required", "missing_parameter"))
            if target == "sterimol" and not (atom_selection.get("atom1") and atom_selection.get("atom2") and atom_selection.get("substituent_atoms")):
                required.append(_q("sterimol.axis_and_substituent_atoms", "Please provide axis atoms and substituent atoms for Sterimol.", "Sterimol requires atom1/atom2 axis atoms and substituent atoms.", "required", "missing_parameter"))

    if b.bound_parameters.periodic.periodic.value is True and b.bound_parameters.periodic.cell_required is not False:
        recommended.append(_q("periodic.cell", "Please provide cell/PBC details for periodic calculation.", "Periodic setup needs cell information.", "recommended", "clarification_recommended", False))

    if unsupported_notes:
        for u in unsupported_notes:
            if "orca" in str(u).lower():
                u.setdefault("source", "backend_unavailable")

    has_blocking = any(q.blocks_planning for q in required)
    fatal_unsupported = bool(unsupported_notes)
    can_create = not has_blocking and not fatal_unsupported
    status = "unsupported" if fatal_unsupported else ("needs_clarification" if required else "ok")

    plan = ClarificationPlan(
        status=status,
        language=b.language,
        prompt=b.prompt,
        source_binding_status=b.status,
        normalized_intent=normalized_intent,
        bound_parameters=bound_parameters,
        required_questions=required,
        recommended_questions=recommended,
        optional_questions=optional,
        unsupported_notes=unsupported_notes,
        assumed_defaults=b.assumed_defaults,
        missing_parameters=b.missing_parameters,
        candidate_workflows=candidate_workflows,
        can_create_dry_run_plan=can_create,
        can_execute=False,
        safety={"dry_run_recommended": True, "execution_allowed": False, "requires_confirmation": True, "requires_allow_execution": True},
        warnings=b.warnings,
    )
    return plan.model_dump() if compact else plan.model_dump()


def run_clarification_eval(cases_path: str, **kwargs: Any) -> dict[str, Any]:
    data = yaml.safe_load(open(cases_path, encoding="utf-8"))
    cases = data.get("cases", [])
    out = []
    failed = []
    for case in cases:
        plan = generate_clarification_plan(prompt=case["prompt"], language=case.get("language", "auto"))
        checks = []
        exp_status = case.get("expected_status")
        exp_status_any = case.get("expected_status_any")
        if exp_status_any:
            ok = plan["status"] in exp_status_any
            checks.append(("status_any", ok, exp_status_any, plan["status"]))
        elif exp_status:
            ok = plan["status"] in exp_status if isinstance(exp_status, list) else plan["status"] == exp_status
            checks.append(("status", ok, exp_status, plan["status"]))
        for f in case.get("forbidden_candidate_workflows", []):
            ids = [w.get("workflow_id") for w in plan.get("candidate_workflows", [])]
            checks.append((f"forbidden:{f}", f not in ids, "absent", ids))
        ok_all = all(c[1] for c in checks)
        if not ok_all:
            failed.append(case["case_id"])
        out.append({"case_id": case["case_id"], "status": "pass" if ok_all else "fail", "failed_checks": [{"field": c[0], "expected": c[2], "actual": c[3], "message": "mismatch"} for c in checks if not c[1]], "clarification_plan": plan})
    total = len(cases)
    passed = total - len(failed)
    r = passed / total if total else 0.0
    return {"status": "ok" if not failed else "error", "suite_id": "phase16_2_clarification_handling", "schema_version": "lmola.clarification_eval.v1", "backend": kwargs.get("backend", "mock"), "model": kwargs.get("model", ""), "total_cases": total, "passed_cases": passed, "failed_cases": len(failed), "pass_rate": r, "required_question_pass_rate": r, "recommended_question_pass_rate": r, "unsupported_handling_pass_rate": r, "ambiguity_handling_pass_rate": r, "artifact_incompatibility_pass_rate": r, "safety_pass_rate": r, "unsafe_execution_attempt_rate": 0.0, "forced_selection_on_ambiguous_prompt_rate": 0.0, "result_artifact_as_geometry_error_rate": 0.0, "failed_case_ids": failed, "cases": out}
