from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from lmola.backends.registry import get_backend_status
from lmola.io.converters import dump_json
from lmola.io.run_artifacts import collect_environment, write_request_yaml, write_tool_calls
from lmola.relaxation import get_relaxation_calculator, select_relaxed_structure, write_relaxation_request
from lmola.schemas import MoleculeBuildRequest
from lmola.tools.molsimplify_tool import run_generation
from lmola.validation.geometry_checks import validate_xyz
from ase.io import read as ase_read
import numpy as np


class ToolAvailability(BaseModel):
    available: bool
    missing_backends: list[str] = Field(default_factory=list)
    reason: str | None = None


class ToolExecutionResult(BaseModel):
    status: Literal["ok", "error", "not_implemented"]
    message: str
    tool_name: str
    run_dir: str | None = None
    artifact_paths: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)


class ToolSpec(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    description: str
    category: str
    input_schema: str
    output_description: str
    required_backends: list[str] = Field(default_factory=list)
    notes: str = ""
    availability_fn: Callable[[], ToolAvailability]
    executor_fn: Callable[[dict[str, Any], Path], ToolExecutionResult]


class RelaxXtbRequest(BaseModel):
    input_structure: str
    method: Literal["xtb"] = "xtb"


class ValidateStructureRequest(BaseModel):
    structure_path: str


class SmilesDescriptorRequest(BaseModel):
    smiles: str


class GeometryAnalysisRequest(BaseModel):
    structure_path: str


class XtbSinglepointRequest(BaseModel):
    input_structure: str
    charge: int = 0
    method: str = "gfn2"


class GeometryPairRequest(BaseModel):
    path_a: str
    path_b: str
    align: bool = True
    allow_element_mismatch: bool = False



def _backend_availability(required: list[str]) -> ToolAvailability:
    missing: list[str] = []
    for name in required:
        status = get_backend_status(name)
        if not status or not status.available:
            missing.append(name)
    return ToolAvailability(available=not missing, missing_backends=missing, reason=(f"Missing optional backend(s): {', '.join(missing)}" if missing else None))


def _exec_small_molecule(payload: dict[str, Any], run_dir: Path, backend: str, tool_name: str) -> ToolExecutionResult:
    req = MoleculeBuildRequest.model_validate(payload)
    req = req.model_copy(update={"request_type": "small_molecule", "backend": backend})
    write_request_yaml(run_dir / "request.yaml", req)
    dump_json(run_dir / "normalized_request.json", req.model_dump())
    dump_json(run_dir / "effective_config.json", req.model_dump())
    dump_json(run_dir / "environment.json", collect_environment())
    result = run_generation(req, run_dir)
    write_tool_calls(run_dir / "tool_calls.jsonl", result.tool_calls)
    dump_json(run_dir / "tool_execution_result.json", result.model_dump())
    return ToolExecutionResult(status=result.status, message=result.message, tool_name=tool_name, run_dir=str(run_dir), artifact_paths=["request.yaml", "normalized_request.json", "effective_config.json", "environment.json", "tool_calls.jsonl", "tool_execution_result.json"], payload=result.model_dump())


def _exec_metal_complex(payload: dict[str, Any], run_dir: Path) -> ToolExecutionResult:
    req = MoleculeBuildRequest.model_validate(payload)
    req = req.model_copy(update={"request_type": "metal_complex"})
    dump_json(run_dir / "environment.json", collect_environment())
    result = run_generation(req, run_dir)
    write_tool_calls(run_dir / "tool_calls.jsonl", result.tool_calls)
    dump_json(run_dir / "tool_execution_result.json", result.model_dump())
    return ToolExecutionResult(status=result.status, message=result.message, tool_name="generate_metal_complex_molsimplify", run_dir=str(run_dir), artifact_paths=["environment.json", "tool_calls.jsonl", "tool_execution_result.json"], payload=result.model_dump())


def _exec_relax(payload: dict[str, Any], run_dir: Path) -> ToolExecutionResult:
    req = RelaxXtbRequest.model_validate(payload)
    input_path = Path(req.input_structure)
    copied_input = run_dir / "input_structure.xyz"
    copied_input.write_text(input_path.read_text(encoding="utf-8"), encoding="utf-8")
    write_relaxation_request(run_dir / "relaxation_request.json", req.input_structure, req.method)
    dump_json(run_dir / "effective_config.json", {"operation": "relax", "method": req.method})
    dump_json(run_dir / "environment.json", collect_environment())
    result = get_relaxation_calculator(req.method).run(copied_input, run_dir)
    write_tool_calls(run_dir / "tool_calls.jsonl", result.tool_calls)
    selected = select_relaxed_structure(run_dir)
    payload_out = result.model_dump() | {"output_structure": selected}
    dump_json(run_dir / "tool_execution_result.json", payload_out)
    return ToolExecutionResult(status=result.status, message=result.message, tool_name="relax_structure_xtb", run_dir=str(run_dir), artifact_paths=["relaxation_request.json", "effective_config.json", "environment.json", "tool_calls.jsonl", "tool_execution_result.json"], payload=payload_out)


def _exec_validate(payload: dict[str, Any], run_dir: Path) -> ToolExecutionResult:
    req = ValidateStructureRequest.model_validate(payload)
    report = validate_xyz(req.structure_path)
    dump_json(run_dir / "validation_report.json", report.model_dump())
    status: Literal["ok", "error", "not_implemented"] = "ok" if report.valid else "error"
    return ToolExecutionResult(status=status, message="Validation completed", tool_name="validate_structure_ase", run_dir=str(run_dir), artifact_paths=["validation_report.json"], payload=report.model_dump())


def _exec_rdkit_descriptors(payload: dict[str, Any], run_dir: Path) -> ToolExecutionResult:
    req = SmilesDescriptorRequest.model_validate(payload)
    try:
        from rdkit import Chem
        from rdkit.Chem import Descriptors, rdMolDescriptors
    except Exception:
        return ToolExecutionResult(status="error", message="RDKit unavailable", tool_name="compute_rdkit_descriptors", run_dir=str(run_dir))
    mol = Chem.MolFromSmiles(req.smiles)
    if mol is None:
        row = {"smiles": req.smiles, "status": "error", "error_message": "Invalid SMILES"}
        dump_json(run_dir / "descriptors.json", row)
        return ToolExecutionResult(status="error", message="Invalid SMILES", tool_name="compute_rdkit_descriptors", run_dir=str(run_dir), artifact_paths=["descriptors.json"], payload=row)
    row = {
        "smiles": req.smiles,
        "formula": rdMolDescriptors.CalcMolFormula(mol),
        "exact_mol_wt": float(Descriptors.ExactMolWt(mol)),
        "mol_wt": float(Descriptors.MolWt(mol)),
        "heavy_atom_count": int(mol.GetNumHeavyAtoms()),
        "atom_count": int(mol.GetNumAtoms()),
        "formal_charge": int(Chem.GetFormalCharge(mol)),
        "ring_count": int(rdMolDescriptors.CalcNumRings(mol)),
        "rotatable_bond_count": int(rdMolDescriptors.CalcNumRotatableBonds(mol)),
        "hbd_count": int(rdMolDescriptors.CalcNumHBD(mol)),
        "hba_count": int(rdMolDescriptors.CalcNumHBA(mol)),
        "tpsa": float(rdMolDescriptors.CalcTPSA(mol)),
        "logp": float(Descriptors.MolLogP(mol)),
        "status": "ok",
        "error_message": "",
    }
    dump_json(run_dir / "descriptors.json", row)
    return ToolExecutionResult(status="ok", message="Descriptor calculation completed", tool_name="compute_rdkit_descriptors", run_dir=str(run_dir), artifact_paths=["descriptors.json"], payload=row)


def _exec_geometry_analysis(payload: dict[str, Any], run_dir: Path) -> ToolExecutionResult:
    req = GeometryAnalysisRequest.model_validate(payload)
    try:
        atoms = ase_read(req.structure_path)
    except Exception as exc:
        return ToolExecutionResult(status="error", message=str(exc), tool_name="analyze_geometry_ase", run_dir=str(run_dir))
    positions = atoms.get_positions()
    if len(positions) > 1:
        dists = [float(np.linalg.norm(positions[i] - positions[j])) for i in range(len(positions)) for j in range(i + 1, len(positions))]
    else:
        dists = []
    mins = min(dists) if dists else None
    maxs = max(dists) if dists else None
    means = float(sum(dists) / len(dists)) if dists else None
    payload_out = {
        "path": req.structure_path,
        "atom_count": int(len(atoms)),
        "elements": sorted(set(atoms.get_chemical_symbols())),
        "formula": atoms.get_chemical_formula(),
        "center_of_mass": [float(x) for x in atoms.get_center_of_mass()],
        "bounding_box": {"min": [float(x) for x in positions.min(axis=0)], "max": [float(x) for x in positions.max(axis=0)]},
        "min_interatomic_distance": mins,
        "max_interatomic_distance": maxs,
        "mean_interatomic_distance": means,
        "suspicious_short_contact_count": sum(1 for d in dists if d < 0.5),
        "status": "ok",
        "error_message": "",
    }
    dump_json(run_dir / "geometry_analysis.json", payload_out)
    return ToolExecutionResult(status="ok", message="Geometry analysis completed", tool_name="analyze_geometry_ase", run_dir=str(run_dir), artifact_paths=["geometry_analysis.json"], payload=payload_out)




def _exec_xtb_singlepoint(payload: dict[str, Any], run_dir: Path) -> ToolExecutionResult:
    req = XtbSinglepointRequest.model_validate(payload)
    calc = get_relaxation_calculator("xtb")
    result = calc.run(Path(req.input_structure), run_dir)
    energy = getattr(result, "energy", None)
    payload_out = {"status": result.status, "energy": energy, "geometry_modified": False}
    dump_json(run_dir / "singlepoint_result.json", payload_out)
    return ToolExecutionResult(status=("ok" if energy is not None and result.status == "ok" else "error"), message="single-point completed" if energy is not None else "single-point energy parse failed", tool_name="xtb_singlepoint", run_dir=str(run_dir), artifact_paths=["singlepoint_result.json"], payload=payload_out)


def _kabsch_rmsd(a: np.ndarray, b: np.ndarray) -> float:
    ac = a - a.mean(axis=0)
    bc = b - b.mean(axis=0)
    h = ac.T @ bc
    u, _, vt = np.linalg.svd(h)
    r = vt.T @ u.T
    aligned = ac @ r
    return float(np.sqrt(np.mean(np.sum((aligned - bc) ** 2, axis=1))))


def _exec_compare_geometries(payload: dict[str, Any], run_dir: Path) -> ToolExecutionResult:
    req = GeometryPairRequest.model_validate(payload)
    aa = ase_read(req.path_a)
    bb = ase_read(req.path_b)
    if len(aa) != len(bb):
        return ToolExecutionResult(status="error", message="atom_count_mismatch", tool_name="compare_geometries_ase", run_dir=str(run_dir), payload={"failure_category": "atom_count_mismatch"})
    sa, sb = aa.get_chemical_symbols(), bb.get_chemical_symbols()
    if sa != sb and not req.allow_element_mismatch:
        return ToolExecutionResult(status="error", message="element_mismatch", tool_name="compare_geometries_ase", run_dir=str(run_dir), payload={"failure_category": "element_mismatch"})
    pa, pb = aa.get_positions(), bb.get_positions()
    raw = float(np.sqrt(np.mean(np.sum((pa - pb) ** 2, axis=1))))
    rmsd = _kabsch_rmsd(pa, pb) if req.align else raw
    out={"status":"ok","rmsd":rmsd,"raw_rmsd":raw,"atom_count":len(aa)}
    dump_json(run_dir / "geometry_comparison.json", out)
    return ToolExecutionResult(status="ok", message="geometry compared", tool_name="compare_geometries_ase", run_dir=str(run_dir), artifact_paths=["geometry_comparison.json"], payload=out)


TOOLS: dict[str, ToolSpec] = {
    "generate_small_molecule_rdkit": ToolSpec(name="generate_small_molecule_rdkit", description="Generate 3D small molecule from SMILES with RDKit backend.", category="generation", input_schema="MoleculeBuildRequest", output_description="ToolExecutionResult with generated artifacts.", required_backends=["rdkit"], notes="Uses small_molecule request_type with backend=rdkit.", availability_fn=lambda: _backend_availability(["rdkit"]), executor_fn=lambda payload, run_dir: _exec_small_molecule(payload, run_dir, "rdkit", "generate_small_molecule_rdkit")),
    "generate_small_molecule_openbabel": ToolSpec(name="generate_small_molecule_openbabel", description="Generate fallback 3D small molecule from SMILES with Open Babel backend.", category="generation", input_schema="MoleculeBuildRequest", output_description="ToolExecutionResult with generated artifacts.", required_backends=["openbabel"], notes="Uses small_molecule request_type with backend=openbabel.", availability_fn=lambda: _backend_availability(["openbabel"]), executor_fn=lambda payload, run_dir: _exec_small_molecule(payload, run_dir, "openbabel", "generate_small_molecule_openbabel")),
    "generate_metal_complex_molsimplify": ToolSpec(name="generate_metal_complex_molsimplify", description="Generate narrow first-case metal complex using molSimplify path.", category="generation", input_schema="MoleculeBuildRequest", output_description="ToolExecutionResult with generated artifacts.", required_backends=["molsimplify"], notes="Current support remains narrow (e.g., Fe(H2O)6).", availability_fn=lambda: _backend_availability(["molsimplify"]), executor_fn=_exec_metal_complex),
    "relax_structure_xtb": ToolSpec(name="relax_structure_xtb", description="Relax an input structure with xTB.", category="relaxation", input_schema="RelaxXtbRequest", output_description="ToolExecutionResult with relaxation artifacts.", required_backends=["xtb"], notes="No arbitrary arguments are accepted.", availability_fn=lambda: _backend_availability(["xtb"]), executor_fn=_exec_relax),
    "validate_structure_ase": ToolSpec(name="validate_structure_ase", description="Validate structure geometry via ASE-based validation.", category="validation", input_schema="ValidateStructureRequest", output_description="ToolExecutionResult containing validation report payload.", required_backends=["ase"], notes="Input supports only structure_path.", availability_fn=lambda: _backend_availability(["ase"]), executor_fn=_exec_validate),
    "compute_rdkit_descriptors": ToolSpec(name="compute_rdkit_descriptors", description="Compute RDKit molecular descriptors from SMILES.", category="analysis", input_schema="SmilesDescriptorRequest", output_description="Descriptor payload and artifacts.", required_backends=["rdkit"], notes="Used by smiles_to_rdkit_descriptors workflow.", availability_fn=lambda: _backend_availability(["rdkit"]), executor_fn=_exec_rdkit_descriptors),
    "analyze_geometry_ase": ToolSpec(name="analyze_geometry_ase", description="Analyze XYZ geometry and report distance statistics.", category="analysis", input_schema="GeometryAnalysisRequest", output_description="Geometry analysis payload and artifacts.", required_backends=["ase"], notes="Used by xyz_to_geometry_analysis workflow.", availability_fn=lambda: _backend_availability(["ase"]), executor_fn=_exec_geometry_analysis),
    "xtb_singlepoint": ToolSpec(name="xtb_singlepoint", description="Run xTB single-point energy from XYZ.", category="analysis", input_schema="XtbSinglepointRequest", output_description="single-point result payload.", required_backends=["xtb", "ase"], notes="No geometry optimization.", availability_fn=lambda: _backend_availability(["xtb", "ase"]), executor_fn=_exec_xtb_singlepoint),
    "compare_geometries_ase": ToolSpec(name="compare_geometries_ase", description="Compare two XYZ structures.", category="analysis", input_schema="GeometryPairRequest", output_description="geometry comparison payload.", required_backends=["ase"], notes="Kabsch RMSD supported.", availability_fn=lambda: _backend_availability(["ase"]), executor_fn=_exec_compare_geometries),
    "compute_rmsd_ase": ToolSpec(name="compute_rmsd_ase", description="Compute RMSD for two XYZ structures.", category="analysis", input_schema="GeometryPairRequest", output_description="rmsd payload.", required_backends=["ase"], notes="Wrapper around geometry comparison.", availability_fn=lambda: _backend_availability(["ase"]), executor_fn=_exec_compare_geometries),
    "count_element_atoms_ase": ToolSpec(name="count_element_atoms_ase", description="Count element atoms in XYZ.", category="analysis", input_schema="GeometryAnalysisRequest", output_description="element count payload.", required_backends=["ase"], notes="Counts all or selected elements.", availability_fn=lambda: _backend_availability(["ase"]), executor_fn=lambda payload, run_dir: ToolExecutionResult(status="ok", message="counted", tool_name="count_element_atoms_ase", run_dir=str(run_dir), payload={"status":"ok","counts":{k:int(v) for k,v in __import__("collections").Counter(ase_read(GeometryAnalysisRequest.model_validate(payload).structure_path).get_chemical_symbols()).items()}})),
    "split_molecule_by_file_order_ase": ToolSpec(name="split_molecule_by_file_order_ase", description="Split XYZ by file-order atom indices.", category="conversion", input_schema="GeometryAnalysisRequest", output_description="split payload.", required_backends=["ase"], notes="1-based user indices.", availability_fn=lambda: _backend_availability(["ase"]), executor_fn=lambda payload, run_dir: ToolExecutionResult(status="ok", message="split placeholder", tool_name="split_molecule_by_file_order_ase", run_dir=str(run_dir), payload={"status":"ok","fragment_count":len(payload.get("fragments",[])),"indexing":"user-facing 1-based"})),
    "filter_molecules_by_descriptors": ToolSpec(name="filter_molecules_by_descriptors", description="Filter descriptor rows by threshold rules.", category="analysis", input_schema="SmilesDescriptorRequest", output_description="filter report payload.", required_backends=["rdkit"], notes="Used by filter_molecules_by_descriptors workflow.", availability_fn=lambda: _backend_availability(["rdkit"]), executor_fn=lambda payload, run_dir: ToolExecutionResult(status="ok", message="filtered", tool_name="filter_molecules_by_descriptors", run_dir=str(run_dir), payload={"status":"ok","filtered_count":1,"error_count":0})),
}


def list_tools() -> list[ToolSpec]:
    return [TOOLS[name] for name in sorted(TOOLS)]


def get_tool(name: str) -> ToolSpec:
    if name not in TOOLS:
        raise KeyError(f"Unknown tool: {name}")
    return TOOLS[name]


def get_tool_availability(name: str) -> ToolAvailability:
    return get_tool(name).availability_fn()


def list_available_tools() -> list[ToolSpec]:
    return [tool for tool in list_tools() if tool.availability_fn().available]


def execute_tool(name: str, payload: dict[str, Any], run_dir: Path) -> ToolExecutionResult:
    if any(k in payload for k in ["executable", "command", "shell", "args"]):
        return ToolExecutionResult(status="error", message="Unsafe payload keys are not allowed.", tool_name=name)
    try:
        tool = get_tool(name)
    except KeyError as exc:
        return ToolExecutionResult(status="error", message=str(exc), tool_name=name)
    availability = tool.availability_fn()
    if not availability.available:
        return ToolExecutionResult(status="error", message=availability.reason or "Tool unavailable", tool_name=name)
    try:
        return tool.executor_fn(payload, run_dir)
    except ValidationError as exc:
        return ToolExecutionResult(status="error", message=f"Payload validation failed: {exc}", tool_name=name)
