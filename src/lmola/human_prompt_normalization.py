from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from lmola.llm.request_normalization import normalize_request
from lmola.workflows.catalog import list_workflows


class CandidateWorkflow(BaseModel):
    workflow_id: str
    confidence: float
    reason: str
    geometry_modified: bool | None = None
    required_backends: list[str] = Field(default_factory=list)


class HumanPromptNormalizedIntent(BaseModel):
    operation: str | None = None
    method_family: str | None = None
    requested_backend: str | None = None
    input_kind: str | None = None
    input_artifact_type: str | None = None
    target_artifact_type: str | None = None
    geometry_modification_allowed: bool | None = None
    target_properties: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    requested_outputs: list[str] = Field(default_factory=list)
    atom_selection: dict[str, Any] = Field(default_factory=dict)
    charge: int | None = None
    spin: int | None = None
    solvent: str | None = None
    periodic: bool | None = None
    notes: list[str] = Field(default_factory=list)


class HumanPromptNormalizationResult(BaseModel):
    status: str
    schema_version: str = "lmola.human_prompt_normalization.v1"
    language: str
    prompt: str
    normalized_intent: HumanPromptNormalizedIntent
    candidate_workflows: list[CandidateWorkflow] = Field(default_factory=list)
    missing_parameters: list[str] = Field(default_factory=list)
    clarification_questions: list[str] = Field(default_factory=list)
    safety: dict[str, Any] = Field(default_factory=lambda: {
        "dry_run_recommended": True,
        "execution_allowed": False,
        "requires_confirmation": True,
        "requires_allow_execution": True,
    })
    warnings: list[str] = Field(default_factory=list)


def _method_family(method: str | None, operation: str | None) -> str | None:
    if method == "xtb":
        return "semiempirical"
    if operation in {"descriptor_filtering", "descriptor_calculation"}:
        return "descriptor"
    if operation in {"rmsd_calculation", "structure_comparison", "geometry_analysis", "element_counting", "molecule_splitting"}:
        return "geometry_analysis"
    if operation == "next_action_recommendation":
        return "workflow_management"
    if operation in {"unsupported", "unknown"}:
        return "unknown"
    return None


def normalize_human_prompt(*, prompt: str, language: str = "auto", compact: bool = False) -> dict[str, Any]:
    base = normalize_request(request=prompt, language=language)
    raw = prompt or ""
    text = raw.lower()
    intent = base.get("normalized_intent", {})
    op = intent.get("operation")
    if any(k in text for k in ["rmsd"]):
        op = "rmsd_calculation"
    if any(k in text for k in ["compare two structures", "compare two geometries", "構造", "比較"]) and "rmsd" not in text and (".xyz" in text or "2つ" in raw or "two" in text):
        op = "structure_comparison"
    if any(k in text for k in ["count", "数を数える"]) and any(e in raw for e in ["Ni", "Fe", "C", "N", "O"]):
        op = "element_counting"
    if any(k in text for k in ["split atoms", "分割", "file order", "ファイル順"]):
        op = "molecule_splitting"
    if "transition state" in text or "reaction path" in text:
        op = "unsupported"
    if "manifest" in text:
        op = "next_action_recommendation"
    if op in {"transition_state_search", "reaction_path_search", "metal_complex_generation"}:
        op = "unsupported"
    if not op:
        op = "unknown"

    input_kind = intent.get("input_kind", "unknown")
    if "manifest" in text:
        input_kind = "artifact_manifest"
    if "singlepoint_result" in text or "xtb_singlepoint_result" in text or "singlepoint result" in text:
        input_kind = "artifact_result"
    if op in {"rmsd_calculation", "structure_comparison"} and input_kind == "unknown":
        input_kind = "xyz_pair"
    if op in {"element_counting", "molecule_splitting"} and input_kind == "unknown":
        input_kind = "xyz"

    constraints = list(intent.get("constraints", []))
    if "do_not_optimize_geometry" in constraints:
        gma = False
    elif op == "geometry_optimization":
        gma = True
    else:
        gma = None

    status = base.get("status", "ok")
    if op == "unknown":
        status = "ambiguous"
    if op == "unsupported":
        status = "unsupported"
    if ("singlepoint result" in text or "singlepoint_result" in text or "xtb_singlepoint_result" in text) and ("continu" in text or "続け" in raw):
        status = "needs_clarification"
        op = "unknown"

    wf_hints = base.get("workflow_hints", [])
    if not wf_hints:
        wf_hints = {"rmsd_calculation": ["xyz_to_rmsd"], "structure_comparison": ["compare_two_geometries"], "element_counting": ["count_element_atoms"], "molecule_splitting": ["split_molecule_by_file_order"], "descriptor_filtering": ["filter_molecules_by_descriptors"], "singlepoint_energy": ["xyz_to_xtb_singlepoint"], "geometry_optimization": ["xyz_to_xtb_relax"]}.get(op, [])
    if status in {"ambiguous", "unsupported", "needs_clarification"}:
        wf_hints = []
    if "singlepoint result" in text or "singlepoint_result" in text or "xtb_singlepoint_result" in text:
        wf_hints = []

    wf_map = {w.workflow_id: w for w in list_workflows()}
    cands: list[CandidateWorkflow] = []
    for idx, wid in enumerate(wf_hints):
        entry = wf_map.get(wid)
        cands.append(CandidateWorkflow(workflow_id=wid, confidence=max(0.5, 0.9 - idx * 0.1), reason="catalog-validated normalization hint", geometry_modified=(entry.contract or {}).get("geometry_modified") if entry else None, required_backends=sorted({b for t in (entry.tools if entry else []) for b in []})))

    missing: list[str] = []
    clarifications: list[str] = []
    if status in {"ambiguous", "needs_clarification"}:
        clarifications.append("Do you want single-point energy or geometry optimization?")
    if op in {"rmsd_calculation", "structure_comparison"} and input_kind != "xyz_pair":
        missing.append("second_xyz_input")
    if op == "unknown":
        missing.append("operation")

    atom_selection: dict[str, Any] = {}
    m = re.search(r"count\s+([A-Z][a-z]?)\s+atoms", raw, flags=re.IGNORECASE)
    if m:
        atom_selection["element"] = m.group(1).capitalize()
    m2 = re.search(r"([A-Z][a-z]?)\s*の数", raw)
    if m2:
        atom_selection["element"] = m2.group(1)

    result = HumanPromptNormalizationResult(
        status=status,
        language=base.get("language", "unknown"),
        prompt=raw,
        normalized_intent=HumanPromptNormalizedIntent(
            operation=op,
            method_family=_method_family(intent.get("method"), op),
            requested_backend=intent.get("method"),
            input_kind=input_kind,
            input_artifact_type="xtb_singlepoint_result" if "singlepoint_result" in text else None,
            geometry_modification_allowed=gma,
            constraints=constraints,
            atom_selection=atom_selection,
            notes=base.get("notes", []),
        ),
        candidate_workflows=cands,
        missing_parameters=missing,
        clarification_questions=clarifications,
        warnings=[] if status != "unsupported" else ["unsupported_task"],
    )
    payload = result.model_dump()
    if compact:
        payload.pop("warnings", None)
    return payload
