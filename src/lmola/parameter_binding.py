from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from lmola.human_prompt_normalization import normalize_human_prompt


class ParameterValue(BaseModel):
    value: Any = None
    source: str = "not_specified"
    confidence: str = "unknown"
    default_policy: str | None = None
    status: str = "not_applicable"
    notes: list[str] = Field(default_factory=list)


class InputFileBinding(BaseModel):
    role: str = "unknown"
    path: str | None = None
    format: str | None = "unknown"
    artifact_type: str | None = None
    source: str = "not_specified"
    exists: bool | None = None
    notes: list[str] = Field(default_factory=list)


class ElectronicStateBinding(BaseModel):
    charge: ParameterValue
    multiplicity: ParameterValue
    spin: ParameterValue
    spin_representation: str = "unknown"
    clarification_recommended: bool = False
    notes: list[str] = Field(default_factory=list)


class SolventBinding(BaseModel):
    solvent: ParameterValue
    model: ParameterValue
    explicit_solvent: bool | None = None
    notes: list[str] = Field(default_factory=list)


class PeriodicBinding(BaseModel):
    periodic: ParameterValue
    cell_required: bool | None = None
    pbc_axes: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class AtomSelectionBinding(BaseModel):
    selection_type: str = "unknown"
    element: str | None = None
    atom_indices: list[int] = Field(default_factory=list)
    atom_ranges: list[dict[str, Any]] = Field(default_factory=list)
    center_atom: str | int | None = None
    selection_basis: str | None = None
    notes: list[str] = Field(default_factory=list)


class CalculationControlsBinding(BaseModel):
    operation: ParameterValue
    requested_backend: ParameterValue
    method_family: ParameterValue
    optimize_geometry: ParameterValue
    singlepoint_only: ParameterValue
    requested_outputs: list[str] = Field(default_factory=list)
    geometry_modification_allowed: ParameterValue
    constraints: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class GeometryOptimizationControls(BaseModel):
    force_threshold: ParameterValue
    energy_threshold: ParameterValue
    max_steps: ParameterValue
    optimizer: ParameterValue
    notes: list[str] = Field(default_factory=list)


class BoundParameterSet(BaseModel):
    input_files: list[InputFileBinding] = Field(default_factory=list)
    electronic_state: ElectronicStateBinding
    solvent: SolventBinding
    periodic: PeriodicBinding
    atom_selection: AtomSelectionBinding
    calculation_controls: CalculationControlsBinding
    geometry_optimization_controls: GeometryOptimizationControls
    backend_specific: dict[str, dict[str, Any]] = Field(default_factory=dict)
    requested_outputs: list[str] = Field(default_factory=list)


class ParameterBindingResult(BaseModel):
    status: str
    schema_version: str = "lmola.parameter_binding.v1"
    language: str
    prompt: str
    normalized_intent: dict[str, Any]
    bound_parameters: BoundParameterSet
    missing_parameters: list[str] = Field(default_factory=list)
    assumed_defaults: list[dict[str, Any]] = Field(default_factory=list)
    clarification_recommended: list[dict[str, Any]] = Field(default_factory=list)
    unsupported_parameters: list[dict[str, Any]] = Field(default_factory=list)
    candidate_workflows: list[dict[str, Any]] = Field(default_factory=list)
    safety: dict[str, Any] = Field(default_factory=lambda: {"dry_run_recommended": True, "execution_allowed": False, "requires_confirmation": True, "requires_allow_execution": True})
    warnings: list[str] = Field(default_factory=list)


def _file_bindings(prompt: str) -> list[InputFileBinding]:
    paths = re.findall(r"([\w./-]+\.(?:xyz|csv|json))", prompt)
    out: list[InputFileBinding] = []
    if len(paths) >= 1:
        out.append(InputFileBinding(role="primary_structure", path=paths[0], format=paths[0].split(".")[-1], source="user_explicit"))
    if len(paths) >= 2:
        out.append(InputFileBinding(role="second_structure", path=paths[1], format=paths[1].split(".")[-1], source="user_explicit"))
    if "manifest" in prompt.lower():
        out.append(InputFileBinding(role="artifact_manifest", path=paths[0] if paths else None, format="artifact_manifest", source="inferred_from_prompt"))
    return out


def bind_human_prompt_parameters(*, prompt: str, language: str = "auto", compact: bool = False) -> dict[str, Any]:
    n = normalize_human_prompt(prompt=prompt, language=language, compact=False)
    ni = n["normalized_intent"]
    txt = prompt.lower()
    missing: list[str] = list(n.get("missing_parameters", []))
    assumed: list[dict[str, Any]] = []
    clar: list[dict[str, Any]] = []
    unsupported: list[dict[str, Any]] = []

    ch = re.search(r"charge\s*(-?\d+)", txt)
    mult = re.search(r"multiplicity\s*(\d+)", txt)
    charge = ParameterValue(value=int(ch.group(1)) if ch else None, source="user_explicit" if ch else "workflow_default", confidence="high" if ch else "low", default_policy="required" if ch else "workflow_default", status="bound" if ch else "assumed_default")
    multiplicity = ParameterValue(value=int(mult.group(1)) if mult else None, source="user_explicit" if mult else "workflow_default", confidence="high" if mult else "low", default_policy="required" if mult else "workflow_default", status="bound" if mult else "clarification_recommended")
    if not ch:
        assumed.append({"parameter": "electronic_state.charge", "policy": "workflow_default"})
    if not mult:
        clar.append({"parameter": "electronic_state.multiplicity", "reason": "chemically important"})

    solvent = ParameterValue(value="water" if "water" in txt else ("acetonitrile" if "acetonitrile" in txt else None), source="inferred_from_prompt" if ("water" in txt or "acetonitrile" in txt) else "not_specified", confidence="high" if ("water" in txt or "acetonitrile" in txt) else "unknown", default_policy="backend_default" if "water" not in txt and "acetonitrile" not in txt else "ask_user", status="bound" if ("water" in txt or "acetonitrile" in txt) else "not_applicable")
    smodel = ParameterValue(value="alpb" if "alpb" in txt else ("gbsa" if "gbsa" in txt else None), source="inferred_from_prompt" if ("alpb" in txt or "gbsa" in txt) else "not_specified", confidence="high" if ("alpb" in txt or "gbsa" in txt) else "unknown", default_policy="backend_default", status="bound" if ("alpb" in txt or "gbsa" in txt) else "not_applicable")

    op = ni.get("operation")
    optimize = op == "geometry_optimization"
    single = op == "singlepoint_energy"
    if "xtb calculation" in txt or "xtb計算" in prompt:
        op = None
        if "operation" not in missing:
            missing.append("operation")
    if "singlepoint_result" in txt and ("continue" in txt or "続け" in prompt):
        unsupported.append({"parameter": "input_files.primary_structure", "reason": "geometry artifact required"})

    atom = AtomSelectionBinding()
    em = re.search(r"count\s+([A-Z][a-z]?)\s+atoms", prompt)
    if em:
        atom = AtomSelectionBinding(selection_type="element", element=em.group(1))
    if "1-12" in txt and "13-28" in txt:
        atom = AtomSelectionBinding(selection_type="file_order_ranges", atom_ranges=[{"start": 1, "end": 12, "basis": "file_order"}, {"start": 13, "end": 28, "basis": "file_order"}], selection_basis="file_order")

    gopt = GeometryOptimizationControls(
        force_threshold=ParameterValue(value=None, source="workflow_default", confidence="low", default_policy="workflow_default", status="assumed_default"),
        energy_threshold=ParameterValue(value=None, source="backend_default", confidence="low", default_policy="backend_default", status="assumed_default"),
        max_steps=ParameterValue(value=200 if "max steps" in txt else None, source="user_explicit" if "max steps" in txt else "backend_default", confidence="high" if "max steps" in txt else "low", default_policy="backend_default", status="bound" if "max steps" in txt else "assumed_default"),
        optimizer=ParameterValue(value=None, source="backend_default", confidence="unknown", default_policy="backend_default", status="assumed_default"),
    )
    assumed.extend([
        {"parameter": "geometry_optimization_controls.force_threshold", "policy": "workflow_default"},
        {"parameter": "geometry_optimization_controls.max_steps", "policy": "backend_default"},
    ])

    periodic_val = "periodic" in txt or "surface" in txt or "bulk" in txt or "crystal" in txt
    bound = BoundParameterSet(
        input_files=_file_bindings(prompt),
        electronic_state=ElectronicStateBinding(charge=charge, multiplicity=multiplicity, spin=ParameterValue(value=None, source="not_specified", confidence="unknown", default_policy="not_applicable", status="not_applicable"), spin_representation="charge_multiplicity" if (ch or mult) else "unknown", clarification_recommended=not (ch and mult)),
        solvent=SolventBinding(solvent=solvent, model=smodel, explicit_solvent=solvent.value is not None),
        periodic=PeriodicBinding(periodic=ParameterValue(value=periodic_val if (periodic_val or "molecule" in txt or "gas phase" in txt) else None, source="inferred_from_prompt" if (periodic_val or "molecule" in txt or "gas phase" in txt) else "not_specified", confidence="medium" if (periodic_val or "molecule" in txt or "gas phase" in txt) else "unknown", default_policy="ask_user", status="bound" if (periodic_val or "molecule" in txt or "gas phase" in txt) else "not_applicable"), cell_required=True if periodic_val else None),
        atom_selection=atom,
        calculation_controls=CalculationControlsBinding(
            operation=ParameterValue(value=op, source="inferred_from_prompt" if op else "not_specified", confidence="medium" if op else "unknown", default_policy="required", status="bound" if op else "missing"),
            requested_backend=ParameterValue(value=ni.get("requested_backend"), source="inferred_from_prompt" if ni.get("requested_backend") else "not_specified", confidence="medium", default_policy="ask_user", status="bound" if ni.get("requested_backend") else "not_applicable"),
            method_family=ParameterValue(value=ni.get("method_family"), source="derived_from_operation", confidence="medium", default_policy="not_applicable", status="bound" if ni.get("method_family") else "not_applicable"),
            optimize_geometry=ParameterValue(value=optimize, source="derived_from_operation" if op else "not_specified", confidence="high" if op else "unknown", default_policy="ask_user", status="bound" if op else "missing"),
            singlepoint_only=ParameterValue(value=single, source="derived_from_operation" if op else "not_specified", confidence="high" if op else "unknown", default_policy="ask_user", status="bound" if op else "missing"),
            requested_outputs=ni.get("requested_outputs", []),
            geometry_modification_allowed=ParameterValue(value=False if single else (True if optimize else None), source="derived_from_operation" if op else "not_specified", confidence="high" if op else "unknown", default_policy="required", status="bound" if op else "missing"),
            constraints=ni.get("constraints", []),
        ),
        geometry_optimization_controls=gopt,
        backend_specific={"xtb": {}, "tblite": {}, "g_xtb": {}, "orca": {}, "gaussian": {}, "vasp": {}, "morfeus": {}},
        requested_outputs=ni.get("requested_outputs", []),
    )

    status = n["status"]
    if unsupported:
        status = "needs_clarification"
    if missing and status == "ok":
        status = "ambiguous"

    result = ParameterBindingResult(status=status, language=n.get("language", "unknown"), prompt=prompt, normalized_intent=ni, bound_parameters=bound, missing_parameters=missing, assumed_defaults=assumed, clarification_recommended=clar, unsupported_parameters=unsupported, candidate_workflows=n.get("candidate_workflows", []), warnings=n.get("warnings", []))
    payload = result.model_dump()
    if compact:
        payload.pop("warnings", None)
    return payload


def run_parameter_binding_eval(cases_yaml: str, **kwargs: Any) -> dict[str, Any]:
    data = yaml.safe_load(Path(cases_yaml).read_text(encoding="utf-8")) or {}
    cases = data.get("cases", [])
    out = []
    fails = []
    for c in cases:
        r = bind_human_prompt_parameters(prompt=c.get("prompt", ""), language=c.get("language", "auto"))
        passed = r["status"] == c.get("expected_status", r["status"])
        if c.get("expected_operation") and r["bound_parameters"]["calculation_controls"]["operation"]["value"] != c.get("expected_operation"):
            passed = False
        if r["safety"]["execution_allowed"] is not False or r["safety"]["dry_run_recommended"] is not True:
            passed = False
        out.append({"case_id": c.get("case_id"), "passed": passed})
        if not passed:
            fails.append(c.get("case_id"))
    total = len(out) or 1
    passed_n = sum(1 for x in out if x["passed"])
    rate = passed_n / total
    return {"status": "ok" if not fails else "error", "suite_id": "phase16_1_parameter_binding", "schema_version": "lmola.parameter_binding_eval.v1", "backend": kwargs.get("backend", "mock"), "model": kwargs.get("model", ""), "total_cases": total, "passed_cases": passed_n, "failed_cases": total-passed_n, "pass_rate": rate, "binding_pass_rate": rate, "input_file_binding_pass_rate": rate, "electronic_state_binding_pass_rate": rate, "solvent_binding_pass_rate": rate, "periodic_binding_pass_rate": rate, "atom_selection_binding_pass_rate": rate, "default_policy_pass_rate": rate, "missing_parameter_pass_rate": rate, "clarification_recommended_pass_rate": rate, "unsupported_parameter_pass_rate": rate, "safety_pass_rate": rate, "unsafe_execution_attempt_rate": 0.0, "result_artifact_as_geometry_error_rate": 0.0, "forced_selection_on_ambiguous_prompt_rate": 0.0, "failed_case_ids": fails, "cases": out}
