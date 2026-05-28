from __future__ import annotations

from importlib import metadata
import importlib.util
import re
import shutil
import subprocess
from typing import Literal

from pydantic import BaseModel, Field

from lmola.tools.openbabel_tool import detect_openbabel_cli, get_openbabel_version


class BackendCapability(BaseModel):
    backend_id: str
    display_name: str
    category: str
    integration_type: Literal["python_import", "cli", "hybrid", "mock", "external"]
    status: Literal["available", "unavailable", "unknown"] = "unknown"
    required_for: list[str] = Field(default_factory=list)
    optional_extra: str | None = None
    python_modules: list[str] = Field(default_factory=list)
    executables: list[str] = Field(default_factory=list)
    executable_paths: dict[str, str | None] = Field(default_factory=dict)
    version: str | None = None
    supported_input_types: list[str] = Field(default_factory=list)
    supported_output_types: list[str] = Field(default_factory=list)
    supported_tasks: list[str] = Field(default_factory=list)
    execution_modes: list[str] = Field(default_factory=list)
    notes: str | None = None
    safety_notes: list[str] = Field(default_factory=list)
    artifact_contract: dict | None = None


_BASE: dict[str, BackendCapability] = {
    "ase": BackendCapability(backend_id="ase", display_name="Atomic Simulation Environment", category="validation", integration_type="python_import", python_modules=["ase"], required_for=["validate_xyz", "xyz_to_geometry_analysis", "xyz_to_xtb_singlepoint", "compare_two_geometries", "xyz_to_rmsd", "count_element_atoms", "split_molecule_by_file_order"], supported_input_types=["xyz", "xyz_list", "smiles", "smiles_csv"], supported_output_types=["validation_report_json", "geometry_analysis_json"], supported_tasks=["validation", "structure_io", "geometry_analysis"], execution_modes=["in_process"], safety_notes=["Read-only geometry validation by default."]),
    "rdkit": BackendCapability(backend_id="rdkit", display_name="RDKit", category="structure_generation", integration_type="python_import", optional_extra="rdkit", python_modules=["rdkit"], required_for=["smiles_to_3d_rdkit", "smiles_to_conformers_rdkit", "smiles_to_xtb_relax", "smiles_to_rdkit_descriptors", "filter_molecules_by_descriptors"], supported_input_types=["smiles", "smiles_csv"], supported_output_types=["xyz", "sdf", "conformer_ensemble", "descriptors_csv", "descriptors_json"], supported_tasks=["structure_generation", "conformer_generation", "descriptor_calculation"], execution_modes=["in_process"]),
    "openbabel": BackendCapability(backend_id="openbabel", display_name="Open Babel", category="conversion", integration_type="hybrid", optional_extra="openbabel", python_modules=["openbabel"], executables=["obabel"], required_for=["smiles_to_3d_openbabel"], supported_input_types=["smiles", "smiles_csv"], supported_output_types=["xyz", "sdf"], supported_tasks=["conversion", "structure_generation"], execution_modes=["cli"]),
    "xtb": BackendCapability(backend_id="xtb", display_name="xTB", category="relaxation", integration_type="hybrid", python_modules=["xtb"], executables=["xtb"], required_for=["smiles_to_xtb_relax", "xyz_to_xtb_relax", "xyz_to_xtb_singlepoint"], supported_input_types=["xyz", "xyz_list", "smiles", "smiles_csv"], supported_output_types=["relaxed_xyz", "energy"], supported_tasks=["relaxation"], execution_modes=["cli"]),
    "molsimplify": BackendCapability(backend_id="molsimplify", display_name="molSimplify", category="structure_generation", integration_type="hybrid", optional_extra="molsimplify", python_modules=["molSimplify"], executables=["molsimplify"], supported_input_types=["text"], supported_output_types=["xyz"], required_for=["molsimplify_build_metal_complex"], supported_tasks=["metal_complex_generation"], execution_modes=["cli", "in_process"]),
    "local_llm": BackendCapability(backend_id="local_llm", display_name="Local LLM", category="llm", integration_type="external", required_for=["plan_workflow"], supported_tasks=["workflow_planning", "artifact_analysis"], execution_modes=["http_client"], safety_notes=["No implicit chemistry execution."]),
    "mock_llm": BackendCapability(backend_id="mock_llm", display_name="Mock LLM", category="llm", integration_type="mock", status="available", required_for=["tests"], supported_tasks=["workflow_planning", "artifact_analysis"], execution_modes=["in_process"]),
}


def _importable(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _module_version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def _parse_xtb_version(output: str) -> str | None:
    for line in output.splitlines():
        m = re.search(r"\b(\d+\.\d+(?:\.\d+)*)\b", line)
        if m:
            return m.group(1)
    return None


def _xtb_version(executable: str | None) -> str | None:
    if not executable:
        return None
    try:
        c = subprocess.run([executable, "--version"], capture_output=True, text=True, check=False)
    except Exception:
        return None
    return _parse_xtb_version(f"{c.stdout}\n{c.stderr}")


def resolve_backend_capability(backend_id: str) -> BackendCapability | None:
    base = _BASE.get(backend_id)
    if not base:
        return None
    cap = base.model_copy(deep=True)
    importable = any(_importable(m) for m in cap.python_modules) if cap.python_modules else None
    paths = {exe: shutil.which(exe) for exe in cap.executables}
    if backend_id == "openbabel":
        paths = {"obabel": detect_openbabel_cli()}
    has_exe = any(v for v in paths.values())
    if backend_id in {"local_llm", "mock_llm"}:
        cap.status = "available"
    elif importable or has_exe:
        cap.status = "available"
    else:
        cap.status = "unavailable"
    cap.executable_paths = paths
    if backend_id == "xtb":
        cap.version = _xtb_version(paths.get("xtb"))
    elif backend_id == "openbabel":
        cap.version = get_openbabel_version(paths.get("obabel"))
    elif cap.python_modules and importable:
        cap.version = _module_version(cap.python_modules[0])
    if backend_id == "molsimplify" and cap.status == "unavailable":
        cap.notes = "planned, not implemented in default LMolA environment"
    return cap


def list_backend_capabilities() -> dict[str, BackendCapability]:
    return {k: resolve_backend_capability(k) for k in sorted(_BASE)}


def backend_capability_schema() -> dict:
    return BackendCapability.model_json_schema()
