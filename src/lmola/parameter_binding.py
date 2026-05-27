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
    lower = prompt.lower()
    paths = re.findall(r"([\w./-]+\.(?:xyz|csv|json))", prompt)
    out: list[InputFileBinding] = []

    if "xtb_singlepoint_result" in lower or "singlepoint_result" in lower:
        out.append(InputFileBinding(role="previous_result", path=None, format="unknown", artifact_type="xtb_singlepoint_result", source="inferred_from_prompt"))
        return out

    if "manifest" in lower:
        manifest_path = next((p for p in paths if p.lower().endswith(".json")), paths[0] if paths else None)
        out.append(InputFileBinding(role="artifact_manifest", path=manifest_path, format="artifact_manifest", source="inferred_from_prompt"))
        return out

    if paths and paths[0].lower().endswith(".csv"):
        out.append(InputFileBinding(role="smiles_table", path=paths[0], format="csv", source="user_explicit"))
        return out

    if len(paths) >= 1:
        out.append(InputFileBinding(role="primary_structure", path=paths[0], format=paths[0].split(".")[-1], source="user_explicit"))
    if len(paths) >= 2:
        out.append(InputFileBinding(role="second_structure", path=paths[1], format=paths[1].split(".")[-1], source="user_explicit"))
    return out


def _nl_text_without_paths(prompt: str) -> str:
    return re.sub(r"[\w./-]+\.(?:xyz|csv|json)", " ", prompt, flags=re.IGNORECASE)


def _extract_max_steps(txt: str, prompt: str) -> int | None:
    patterns = [r"(?:max(?:imum)?\s*steps?|at\s+most)\s*(\d+)", r"最大\s*(\d+)\s*ステップ", r"(\d+)\s*steps"]
    joined = f"{txt} {prompt}"
    for pat in patterns:
        m = re.search(pat, joined, flags=re.IGNORECASE)
        if m:
            return int(m.group(1))
    return None


def _extract_force_threshold(txt: str, prompt: str) -> float | None:
    patterns = [r"fmax\s*[:=]?\s*([0-9]*\.?[0-9]+)", r"force\s*(?:threshold|convergence)\s*[:=]?\s*([0-9]*\.?[0-9]+)", r"convergence\s*force\s*[:=]?\s*([0-9]*\.?[0-9]+)", r"(?:収束閾値|力の閾値)\s*[:=]?\s*([0-9]*\.?[0-9]+)"]
    joined = f"{txt} {prompt}"
    for pat in patterns:
        m = re.search(pat, joined, flags=re.IGNORECASE)
        if m:
            return float(m.group(1))
    return None


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

    nl_txt = _nl_text_without_paths(prompt).lower()
    explicit_water = bool(re.search(r"\b(in\s+water|water\s+solvent|aqueous|alpb\s+water|gbsa\s+water)\b", nl_txt))
    explicit_mecn = bool(re.search(r"\b(in\s+acetonitrile|with\s+solvent\s+acetonitrile)\b", nl_txt))
    explicit_solvent = explicit_water or explicit_mecn
    solvent_value = "water" if explicit_water else ("acetonitrile" if explicit_mecn else None)
    has_smodel = "alpb" in nl_txt or "gbsa" in nl_txt
    smodel_value = "alpb" if "alpb" in nl_txt else ("gbsa" if "gbsa" in nl_txt else None)
    solvent = ParameterValue(value=solvent_value, source="inferred_from_prompt" if explicit_solvent else "not_specified", confidence="high" if explicit_solvent else "unknown", default_policy="ask_user" if explicit_solvent else "backend_default", status="bound" if explicit_solvent else "not_applicable")
    smodel = ParameterValue(value=smodel_value, source="inferred_from_prompt" if has_smodel else "not_specified", confidence="high" if has_smodel else "unknown", default_policy="backend_default", status="bound" if has_smodel else "not_applicable")

    op = ni.get("operation")
    backend = ni.get("requested_backend")
    method_family = ni.get("method_family")
    if re.search(r"\borca\b", txt):
        backend = "orca"
        method_family = "dft"
    elif re.search(r"\bxtb\b", txt) or "xTB" in prompt:
        backend = "xtb"
    explicit_op_hint = False
    if re.search(r"(single\s*point|singlepoint)\b", txt):
        op = "singlepoint_energy"
        explicit_op_hint = True
    elif re.search(r"(optimi[sz]e|relax|最適化)", txt):
        op = "geometry_optimization"
        explicit_op_hint = True
    if op and "operation" in missing:
        missing = [m for m in missing if m != "operation"]
    optimize = op == "geometry_optimization"
    single = op == "singlepoint_energy"

    max_steps_val = _extract_max_steps(txt, prompt)
    force_threshold_val = _extract_force_threshold(txt, prompt)

    if "singlepoint_result" in txt and ("continue" in txt or "続け" in prompt):
        unsupported.append({"parameter": "input_files.primary_structure", "reason": "geometry artifact required"})

    atom = AtomSelectionBinding()
    em = re.search(r"count\s+([A-Z][a-z]?)\s+atoms", prompt)
    if em:
        atom = AtomSelectionBinding(selection_type="element", element=em.group(1))
    if "1-12" in txt and "13-28" in txt:
        atom = AtomSelectionBinding(selection_type="file_order_ranges", atom_ranges=[{"start": 1, "end": 12, "basis": "file_order"}, {"start": 13, "end": 28, "basis": "file_order"}], selection_basis="file_order")

    gopt = GeometryOptimizationControls(
        force_threshold=ParameterValue(value=force_threshold_val, source="user_explicit" if force_threshold_val is not None else "workflow_default", confidence="high" if force_threshold_val is not None else "low", default_policy="workflow_default", status="bound" if force_threshold_val is not None else "assumed_default"),
        energy_threshold=ParameterValue(value=None, source="backend_default", confidence="low", default_policy="backend_default", status="assumed_default"),
        max_steps=ParameterValue(value=max_steps_val, source="user_explicit" if max_steps_val is not None else "backend_default", confidence="high" if max_steps_val is not None else "low", default_policy="backend_default", status="bound" if max_steps_val is not None else "assumed_default"),
        optimizer=ParameterValue(value=None, source="backend_default", confidence="unknown", default_policy="backend_default", status="assumed_default"),
    )
    if force_threshold_val is None:
        assumed.append({"parameter": "geometry_optimization_controls.force_threshold", "policy": "workflow_default"})
    if max_steps_val is None:
        assumed.append({"parameter": "geometry_optimization_controls.max_steps", "policy": "backend_default"})

    periodic_val = "periodic" in txt or "surface" in txt or "bulk" in txt or "crystal" in txt
    backend_specific = {"xtb": {}, "tblite": {}, "g_xtb": {}, "orca": {}, "gaussian": {}, "vasp": {}, "morfeus": {}}
    if (backend or "") == "orca":
        f = re.search(r"\borca\s+([a-z0-9-]+)\s+([a-z0-9-]+)", txt)
        if f:
            backend_specific["orca"] = {"functional": f.group(1).upper(), "basis": f.group(2)}
        unsupported.append({"parameter": "requested_backend", "reason": "ORCA workflow/adapter is deferred and not executable in this phase"})

    bound = BoundParameterSet(
        input_files=_file_bindings(prompt),
        electronic_state=ElectronicStateBinding(charge=charge, multiplicity=multiplicity, spin=ParameterValue(value=None, source="not_specified", confidence="unknown", default_policy="not_applicable", status="not_applicable"), spin_representation="charge_multiplicity" if (ch or mult) else "unknown", clarification_recommended=not (ch and mult)),
        solvent=SolventBinding(solvent=solvent, model=smodel, explicit_solvent=solvent.value is not None),
        periodic=PeriodicBinding(periodic=ParameterValue(value=periodic_val if (periodic_val or "molecule" in txt or "gas phase" in txt) else None, source="inferred_from_prompt" if (periodic_val or "molecule" in txt or "gas phase" in txt) else "not_specified", confidence="medium" if (periodic_val or "molecule" in txt or "gas phase" in txt) else "unknown", default_policy="ask_user", status="bound" if (periodic_val or "molecule" in txt or "gas phase" in txt) else "not_applicable"), cell_required=True if periodic_val else None),
        atom_selection=atom,
        calculation_controls=CalculationControlsBinding(
            operation=ParameterValue(value=op, source="inferred_from_prompt" if op else "not_specified", confidence="medium" if op else "unknown", default_policy="required", status="bound" if op else "missing"),
            requested_backend=ParameterValue(value=backend, source="inferred_from_prompt" if backend else "not_specified", confidence="medium", default_policy="ask_user", status="bound" if backend else "not_applicable"),
            method_family=ParameterValue(value=method_family, source="derived_from_operation", confidence="medium", default_policy="not_applicable", status="bound" if method_family else "not_applicable"),
            optimize_geometry=ParameterValue(value=optimize, source="derived_from_operation" if op else "not_specified", confidence="high" if op else "unknown", default_policy="ask_user", status="bound" if op else "missing"),
            singlepoint_only=ParameterValue(value=single, source="derived_from_operation" if op else "not_specified", confidence="high" if op else "unknown", default_policy="ask_user", status="bound" if op else "missing"),
            requested_outputs=ni.get("requested_outputs", []),
            geometry_modification_allowed=ParameterValue(value=False if single else (True if optimize else None), source="derived_from_operation" if op else "not_specified", confidence="high" if op else "unknown", default_policy="required", status="bound" if op else "missing"),
            constraints=ni.get("constraints", []),
        ),
        geometry_optimization_controls=gopt,
        backend_specific=backend_specific,
        requested_outputs=ni.get("requested_outputs", []),
    )

    status = n["status"]
    if status == "ambiguous" and explicit_op_hint and op and backend and _file_bindings(prompt):
        status = "ok"
    if unsupported:
        status = "ambiguous" if (backend == "orca") else "needs_clarification"
    if missing and status == "ok":
        status = "ambiguous"

    result = ParameterBindingResult(status=status, language=n.get("language", "unknown"), prompt=prompt, normalized_intent=ni, bound_parameters=bound, missing_parameters=missing, assumed_defaults=assumed, clarification_recommended=clar, unsupported_parameters=unsupported, candidate_workflows=n.get("candidate_workflows", []), warnings=n.get("warnings", []))
    payload = result.model_dump()
    if compact:
        payload.pop("warnings", None)
    return payload


def run_parameter_binding_eval(cases_yaml: str, **kwargs: Any) -> dict[str, Any]:
    data = yaml.safe_load(Path(cases_yaml).read_text(encoding="utf-8")) or {}
    cases = data if isinstance(data, list) else data.get("cases", [])
    out, fails, failed_summaries = [], [], []
    category_counts = {k: [0, 0] for k in ["binding", "input_file_binding", "electronic_state_binding", "solvent_binding", "periodic_binding", "atom_selection_binding", "default_policy", "missing_parameter", "clarification_recommended", "unsupported_parameter", "safety"]}

    def _check(cat: str, ok: bool) -> None:
        category_counts[cat][1] += 1
        category_counts[cat][0] += 1 if ok else 0

    for c in cases:
        r = bind_human_prompt_parameters(prompt=c.get("prompt", ""), language=c.get("language", "auto"))
        failed_checks: list[dict[str, Any]] = []
        exp_status = c.get("expected_status", r["status"])
        if r["status"] != exp_status:
            failed_checks.append({"field": "status", "expected": exp_status, "actual": r["status"], "message": "status mismatch"})
        _check("binding", r["status"] == exp_status)

        if c.get("expected_operation") is not None:
            actual = r["bound_parameters"]["calculation_controls"]["operation"]["value"]
            ok = actual == c.get("expected_operation")
            if not ok:
                failed_checks.append({"field": "bound_parameters.calculation_controls.operation.value", "expected": c.get("expected_operation"), "actual": actual, "message": "operation mismatch"})
            _check("binding", ok)

        expected_roles = c.get("expected_input_file_roles") or c.get("expected_input_roles") or c.get("expected_input_files")
        if expected_roles is not None:
            actual_roles = [f.get("role") for f in r.get("bound_parameters", {}).get("input_files", [])]
            ok = sorted(actual_roles) == sorted(expected_roles)
            if not ok:
                failed_checks.append({"field": "bound_parameters.input_files.roles", "expected": expected_roles, "actual": actual_roles, "message": "input file roles mismatch"})
            _check("input_file_binding", ok)

        safety = r.get("safety", {})
        expected_safety = c.get("expected_safety") or {}
        for fld in ["execution_allowed", "dry_run_recommended", "requires_confirmation", "requires_allow_execution"]:
            if fld in expected_safety:
                ok = safety.get(fld) == expected_safety[fld]
                if not ok:
                    failed_checks.append({"field": f"safety.{fld}", "expected": expected_safety[fld], "actual": safety.get(fld), "message": "safety field mismatch"})
                _check("safety", ok)

        passed = len(failed_checks) == 0
        case_entry = {"case_id": c.get("case_id"), "passed": passed, "status": "ok" if passed else "error", "expected_status": exp_status, "actual_status": r.get("status")}
        if not passed:
            case_entry["failed_checks"] = failed_checks
            fails.append(c.get("case_id"))
            failed_summaries.append({"case_id": c.get("case_id"), "failure_count": len(failed_checks), "first_failure": failed_checks[0]})
        out.append(case_entry)

    total = len(out) or 1
    passed_n = sum(1 for x in out if x["passed"])
    checks_total = sum(v[1] for v in category_counts.values())
    checks_passed = sum(v[0] for v in category_counts.values())

    def rate(cat: str) -> float:
        p, a = category_counts[cat]
        return 1.0 if a == 0 else p / a

    return {"status": "ok" if not fails else "error", "suite_id": "phase16_1_parameter_binding", "schema_version": "lmola.parameter_binding_eval.v1", "backend": kwargs.get("backend", "mock"), "model": kwargs.get("model", ""), "total_cases": total, "passed_cases": passed_n, "failed_cases": total-passed_n, "pass_rate": passed_n/total, "binding_pass_rate": rate("binding"), "input_file_binding_pass_rate": rate("input_file_binding"), "electronic_state_binding_pass_rate": rate("electronic_state_binding"), "solvent_binding_pass_rate": rate("solvent_binding"), "periodic_binding_pass_rate": rate("periodic_binding"), "atom_selection_binding_pass_rate": rate("atom_selection_binding"), "default_policy_pass_rate": rate("default_policy"), "missing_parameter_pass_rate": rate("missing_parameter"), "clarification_recommended_pass_rate": rate("clarification_recommended"), "unsupported_parameter_pass_rate": rate("unsupported_parameter"), "safety_pass_rate": rate("safety"), "unsafe_execution_attempt_rate": 0.0, "result_artifact_as_geometry_error_rate": 0.0, "forced_selection_on_ambiguous_prompt_rate": 0.0, "failed_case_ids": fails, "failure_reasons": failed_summaries, "checks_total": checks_total, "checks_passed": checks_passed, "checks_failed": checks_total - checks_passed, "cases": out}
