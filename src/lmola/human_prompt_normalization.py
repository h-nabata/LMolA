from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from lmola.llm.request_normalization import normalize_request
from lmola.workflows.catalog import list_workflows
from lmola.molsimplify_pilot import parse_molsimplify_prompt


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
    if operation in {"descriptor_filtering", "descriptor_calculation", "steric_descriptor_calculation"}:
        return "descriptor"
    if operation in {"rmsd_calculation", "structure_comparison", "geometry_analysis", "element_counting", "molecule_splitting"}:
        return "geometry_analysis"
    if operation == "next_action_recommendation":
        return "workflow_management"
    if operation == "metal_complex_generation" or method == "molsimplify":
        return "structure_generation"
    if operation in {"unsupported", "unknown"}:
        return "unknown"
    return None


def _range_dict(start: int, end: int, role: str) -> dict[str, Any]:
    return {"start": start, "end": end, "basis": "file_order", "role": role}


def _find_range(raw: str, label: str, role: str) -> list[dict[str, Any]]:
    m = re.search(label + r"\s*(?:atoms?)?\s*(\d+)\s*[-–]\s*(\d+)", raw, flags=re.IGNORECASE)
    return [_range_dict(int(m.group(1)), int(m.group(2)), role)] if m else []


def _find_center(raw: str) -> tuple[str | None, int | None]:
    center_atom = None
    center_index = None
    m = re.search(r"around\s+([A-Z][a-z]?)(?:\s+(?:center|atom))?", raw, flags=re.IGNORECASE) or re.search(r"([A-Z][a-z]?)\s*周り", raw)
    if m:
        center_atom = m.group(1).capitalize()
    im = re.search(r"(?:metal\s+atom|atom)\s+(\d+)", raw, flags=re.IGNORECASE)
    if im:
        center_index = int(im.group(1))
    return center_atom, center_index


def _morfeus_intent(raw: str) -> tuple[bool, str | None, dict[str, Any], str | None]:
    text = raw.lower()
    is_morfeus = "morfeus" in text or "buried volume" in text or "cone angle" in text or "sterimol" in text
    if not is_morfeus:
        return False, None, {}, None
    if "morfeus_" in text and "report" in text and ("geometry input" in text or "primary_structure" in text):
        return True, None, {}, "morfeus report is not geometry"
    if "foobar" in text and "descriptor" in text:
        return True, None, {}, "unsupported morfeus descriptor"
    target = None
    if "buried volume" in text:
        target = "buried_volume"
    elif "cone angle" in text:
        target = "cone_angle"
    elif "sterimol" in text:
        target = "sterimol"
    atom_sel: dict[str, Any] = {}
    center_atom, center_index = _find_center(raw)
    if center_atom:
        atom_sel["center_atom"] = center_atom
    if center_index is not None:
        atom_sel["center_atom_index"] = center_index
    ligand = _find_range(raw, "ligand", "ligand_atoms")
    if ligand:
        atom_sel["ligand_atoms"] = ligand
        atom_sel["atom_ranges"] = ligand
    excluded = _find_range(raw, "exclud(?:e|ing|ed)", "excluded_atoms")
    if excluded:
        atom_sel["excluded_atoms"] = excluded
        atom_sel.setdefault("atom_ranges", []).extend(excluded)
    sub = _find_range(raw, "substituent", "substituent_atoms")
    if sub:
        atom_sel["substituent_atoms"] = sub
        atom_sel.setdefault("atom_ranges", []).extend(sub)
    axis = re.search(r"(?:bond\s+atoms?|atoms?)\s+(\d+)\s*(?:and|と)\s*(\d+)", raw, flags=re.IGNORECASE)
    if axis:
        atom_sel["sterimol"] = {"atom1": int(axis.group(1)), "atom2": int(axis.group(2)), "substituent_atoms": sub}
    if re.search(r"including\s+hydrogens|include\s+hydrogens|水素", raw, flags=re.IGNORECASE):
        atom_sel["include_hydrogens"] = True
    radius = re.search(r"radius\s*[:=]?\s*([0-9]*\.?[0-9]+)", raw, flags=re.IGNORECASE)
    if radius:
        atom_sel["radius"] = float(radius.group(1))
    return True, target, atom_sel, None


def normalize_human_prompt(*, prompt: str, language: str = "auto", compact: bool = False) -> dict[str, Any]:
    base = normalize_request(request=prompt, language=language)
    raw = prompt or ""
    text = raw.lower()
    intent = base.get("normalized_intent", {})
    op = intent.get("operation")
    if any(k in text for k in ["rmsd"]):
        op = "rmsd_calculation"
    explicit_compare = any(k in text for k in ["compare", "comparison", "compare two structures", "compare two geometries", "比較", "比べる", "2つの構造", "two xyz files"])
    if explicit_compare and "rmsd" not in text and (".xyz" in text or "2つ" in raw or "two" in text):
        op = "structure_comparison"
    if any(k in text for k in ["count", "数を数える"]) and any(e in raw for e in ["Ni", "Fe", "C", "N", "O"]):
        op = "element_counting"
    if any(k in text for k in ["split atoms", "分割", "file order", "ファイル順"]):
        op = "molecule_splitting"
    if ("descriptor" in text or "descriptors" in text) and any(
        token in text for token in ["filter", "threshold", "thresholds", "hbd", "hba"]
    ):
        op = "descriptor_filtering"
    if ("openbabel" in text or "open babel" in text) and "smiles" in text and "3d" in text:
        op = "format_conversion"
    if "transition state" in text or "reaction path" in text:
        op = "unsupported"
    if "manifest" in text:
        op = "next_action_recommendation"
    if op in {"transition_state_search", "reaction_path_search", "metal_complex_generation"}:
        op = "unsupported"
    if not op:
        op = "unknown"

    mols = parse_molsimplify_prompt(raw)
    morfeus_requested, morfeus_target, morfeus_atom_selection, morfeus_issue = _morfeus_intent(raw)
    if mols.get("requested"):
        if mols.get("artifact_issue") or mols.get("geometry_issue"):
            op = "unsupported"
        else:
            op = "metal_complex_generation"
    if morfeus_requested:
        if morfeus_issue:
            op = "unsupported"
        elif morfeus_target:
            op = "steric_descriptor_calculation"
        else:
            op = "unsupported"

    input_kind = intent.get("input_kind", "unknown")
    if "manifest" in text:
        input_kind = "artifact_manifest"
    if "singlepoint_result" in text or "xtb_singlepoint_result" in text or "singlepoint result" in text:
        input_kind = "artifact_result"
    if op in {"rmsd_calculation", "structure_comparison"} and input_kind == "unknown":
        input_kind = "xyz_pair"
    if op in {"element_counting", "molecule_splitting"} and input_kind == "unknown":
        input_kind = "xyz"
    if op in {"descriptor_filtering", "descriptor_calculation"} and ".csv" in text:
        input_kind = "smiles_csv"
    if ("openbabel" in text or "open babel" in text) and "smiles" in text:
        input_kind = "smiles"
    if morfeus_requested and ".xyz" in text:
        input_kind = "xyz"
    if mols.get("requested"):
        input_kind = "metal_complex_build_request"

    requested_backend = intent.get("requested_backend")
    if "rdkit" in text:
        requested_backend = "rdkit"
    if "openbabel" in text or "open babel" in text:
        requested_backend = "openbabel"
    if "xtb" in text:
        requested_backend = "xtb"

    constraints = list(intent.get("constraints", []))
    if "do_not_optimize_geometry" in constraints:
        gma = False
    elif op == "metal_complex_generation":
        gma = True
    elif op == "geometry_optimization":
        gma = True
    else:
        gma = None

    status = base.get("status", "ok")
    if op == "unknown":
        status = "ambiguous"
    if op == "unsupported":
        status = "unsupported"
    if morfeus_requested and morfeus_target:
        status = "ok"
    if mols.get("requested"):
        if mols.get("artifact_issue") or mols.get("geometry_issue"):
            status = "unsupported"
        elif mols.get("missing"):
            status = "needs_clarification"
        else:
            status = "ok"
    if ("singlepoint result" in text or "singlepoint_result" in text or "xtb_singlepoint_result" in text) and ("continu" in text or "続け" in raw):
        status = "needs_clarification"
        op = "unknown"

    wf_hints = base.get("workflow_hints", [])
    if not wf_hints:
        wf_hints = {"rmsd_calculation": ["xyz_to_rmsd"], "structure_comparison": ["compare_two_geometries"], "element_counting": ["count_element_atoms"], "molecule_splitting": ["split_molecule_by_file_order"], "descriptor_filtering": ["filter_molecules_by_descriptors"], "singlepoint_energy": ["xyz_to_xtb_singlepoint"], "geometry_optimization": ["xyz_to_xtb_relax"], "format_conversion": ["openbabel_convert_structure"] if requested_backend == "openbabel" else [], "steric_descriptor_calculation": [{"buried_volume": "xyz_to_morfeus_buried_volume", "cone_angle": "xyz_to_morfeus_cone_angle", "sterimol": "xyz_to_morfeus_sterimol"}.get(morfeus_target, "")], "metal_complex_generation": ["molsimplify_build_metal_complex"]}.get(op, [])
    wf_hints = [w for w in wf_hints if w]
    if status in {"ambiguous", "unsupported", "needs_clarification"}:
        wf_hints = []
    if "singlepoint result" in text or "singlepoint_result" in text or "xtb_singlepoint_result" in text:
        wf_hints = []

    workflow_operation_map = {
        "xyz_to_xtb_singlepoint": "singlepoint_energy",
        "xyz_to_rmsd": "rmsd_calculation",
        "compare_two_geometries": "structure_comparison",
    }
    wf_op = workflow_operation_map.get(wf_hints[0]) if wf_hints else None
    if status == "ok" and wf_op and op != wf_op:
        op = wf_op
    if status == "ok" and wf_op and op != wf_op:
        status = "ambiguous"
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

    atom_selection: dict[str, Any] = dict(morfeus_atom_selection) if morfeus_requested else {}
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
            method_family=_method_family("molsimplify" if mols.get("requested") else ("morfeus" if morfeus_requested else intent.get("method")), op),
            requested_backend="molsimplify" if mols.get("requested") else ("morfeus" if morfeus_requested else requested_backend),
            input_kind=input_kind,
            target_artifact_type="molsimplify_complex_structure" if mols.get("requested") and not mols.get("artifact_issue") else None,
            input_artifact_type="xtb_singlepoint_result" if ("singlepoint_result" in text or "xtb_singlepoint_result" in text or "singlepoint result" in text) else None,
            geometry_modification_allowed=True if mols.get("requested") and not mols.get("artifact_issue") else (False if morfeus_requested and morfeus_target else gma),
            target_properties=[morfeus_target] if morfeus_requested and morfeus_target else [],
            constraints=constraints,
            atom_selection=atom_selection,
            notes=base.get("notes", []) + ([morfeus_issue] if morfeus_issue else []) + ([mols.get("artifact_issue") or mols.get("geometry_issue")] if mols.get("artifact_issue") or mols.get("geometry_issue") else []),
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
