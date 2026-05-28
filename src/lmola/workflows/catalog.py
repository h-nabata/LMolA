from __future__ import annotations

from pydantic import BaseModel, Field

from lmola.backends.capabilities import list_backend_capabilities

TASK_TAXONOMY: list[str] = [
    "structure_generation",
    "conformer_generation",
    "conversion",
    "validation",
    "relaxation",
    "batch_processing",
    "summarization",
    "descriptor_calculation",
    "geometry_analysis",
    "property_calculation",
    "steric_descriptor_calculation",
    "metal_complex_generation",
]

FUTURE_TASK_TYPES: list[str] = [
    "conformer_search",
    "reaction_path",
    "transition_state_search",
    "property_calculation",
    "surface_modeling",
    "metal_complex_generation",
    "workflow_planning",
]


class WorkflowCatalogEntry(BaseModel):
    workflow_id: str
    task_type: str
    input_types: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    required_backends: list[str] = Field(default_factory=list)
    description: str = ""
    contract: dict = Field(default_factory=dict)


class WorkflowPortContract(BaseModel):
    name: str
    role: str
    data_types: list[str] = Field(default_factory=list)
    required: bool
    multiple: bool
    description: str
    geometry_modified: bool | None = None


class WorkflowExecutionPolicy(BaseModel):
    dry_run_default: bool = True
    requires_allow_execution: bool = True
    requires_confirm: bool = True
    mcp_allowlisted: bool = True
    low_level_direct_call_allowed: bool = False


class WorkflowArtifactOutputDescriptor(BaseModel):
    name: str
    artifact_type: str
    produced_on: str
    description: str
    geometry_modified: bool | None = None


class WorkflowContract(BaseModel):
    schema_version: str = "lmola.workflow_contract.v1"
    workflow_id: str
    task_type: str
    operation: str
    method: str | None = None
    input_ports: list[WorkflowPortContract]
    output_ports: list[WorkflowPortContract]
    required_backends: list[str] = Field(default_factory=list)
    optional_backends: list[str] = Field(default_factory=list)
    execution_policy: WorkflowExecutionPolicy = Field(default_factory=WorkflowExecutionPolicy)
    geometry_modified: bool | None = None
    side_effects: list[str] = Field(default_factory=list)
    cost_class: str = "unknown"
    safe_for_confirmed_smoke: bool = True
    artifact_outputs: list[WorkflowArtifactOutputDescriptor] = Field(default_factory=list)
    llm_use_when: list[str] = Field(default_factory=list)
    llm_do_not_use_when: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


def _default_execution_policy() -> WorkflowExecutionPolicy:
    return WorkflowExecutionPolicy(
        dry_run_default=True,
        requires_allow_execution=True,
        requires_confirm=True,
        mcp_allowlisted=True,
        low_level_direct_call_allowed=False,
    )


WORKFLOW_CATALOG: dict[str, WorkflowCatalogEntry] = {
    "smiles_to_3d_rdkit": WorkflowCatalogEntry(
        workflow_id="smiles_to_3d_rdkit",
        task_type="structure_generation",
        input_types=["smiles", "smiles_csv"],
        tools=["generate_small_molecule_rdkit", "validate_structure_ase"],
        required_backends=["rdkit", "ase"],
        description="Generate 3D small-molecule structures from SMILES using RDKit.",
    ),
    "smiles_to_conformers_rdkit": WorkflowCatalogEntry(
        workflow_id="smiles_to_conformers_rdkit",
        task_type="conformer_generation",
        input_types=["smiles", "smiles_csv"],
        tools=["generate_small_molecule_rdkit", "validate_structure_ase"],
        required_backends=["rdkit", "ase"],
        description="Generate conformer ensembles from SMILES using RDKit.",
    ),
    "smiles_to_3d_openbabel": WorkflowCatalogEntry(
        workflow_id="smiles_to_3d_openbabel",
        task_type="structure_generation",
        input_types=["smiles", "smiles_csv"],
        tools=["generate_small_molecule_openbabel", "validate_structure_ase"],
        required_backends=["openbabel", "ase"],
        description="Generate 3D small-molecule structures from SMILES using Open Babel.",
    ),
    "smiles_to_xtb_relax": WorkflowCatalogEntry(
        workflow_id="smiles_to_xtb_relax",
        task_type="relaxation",
        input_types=["smiles", "smiles_csv"],
        tools=["generate_small_molecule_rdkit", "validate_structure_ase", "relax_structure_xtb"],
        required_backends=["rdkit", "ase", "xtb"],
        description="Generate structures from SMILES and run xTB relaxation.",
    ),
    "xyz_to_xtb_relax": WorkflowCatalogEntry(
        workflow_id="xyz_to_xtb_relax",
        task_type="relaxation",
        input_types=["xyz", "xyz_list"],
        tools=["validate_structure_ase", "relax_structure_xtb"],
        required_backends=["ase", "xtb"],
        description="Validate XYZ and run xTB relaxation.",
    ),
    "validate_xyz": WorkflowCatalogEntry(
        workflow_id="validate_xyz",
        task_type="validation",
        input_types=["xyz", "xyz_list"],
        tools=["validate_structure_ase"],
        required_backends=["ase"],
        description="Validate XYZ geometry and consistency.",
    ),
    "smiles_to_rdkit_descriptors": WorkflowCatalogEntry(
        workflow_id="smiles_to_rdkit_descriptors",
        task_type="descriptor_calculation",
        input_types=["smiles", "smiles_csv"],
        tools=["compute_rdkit_descriptors"],
        required_backends=["rdkit"],
        description="Compute basic molecular descriptors from SMILES using RDKit.",
    ),
    "xyz_to_xtb_singlepoint": WorkflowCatalogEntry(
        workflow_id="xyz_to_xtb_singlepoint",
        task_type="property_calculation",
        input_types=["xyz", "xyz_list"],
        tools=["xtb_singlepoint"],
        required_backends=["ase", "xtb"],
        description="Run xTB single-point energy calculation from XYZ without geometry optimization.",
    ),
    "compare_two_geometries": WorkflowCatalogEntry(
        workflow_id="compare_two_geometries",
        task_type="geometry_analysis",
        input_types=["xyz_pair"],
        tools=["compare_geometries_ase"],
        required_backends=["ase"],
        description="Compare two XYZ geometries by atom count, element ordering, and RMSD.",
    ),
    "xyz_to_rmsd": WorkflowCatalogEntry(
        workflow_id="xyz_to_rmsd",
        task_type="geometry_analysis",
        input_types=["xyz_pair"],
        tools=["compute_rmsd_ase"],
        required_backends=["ase"],
        description="Compute RMSD between two XYZ geometries.",
    ),
    "count_element_atoms": WorkflowCatalogEntry(
        workflow_id="count_element_atoms",
        task_type="geometry_analysis",
        input_types=["xyz", "xyz_list"],
        tools=["count_element_atoms_ase"],
        required_backends=["ase"],
        description="Count atoms by element symbol for XYZ input(s).",
    ),
    "split_molecule_by_file_order": WorkflowCatalogEntry(
        workflow_id="split_molecule_by_file_order",
        task_type="conversion",
        input_types=["xyz"],
        tools=["split_molecule_by_file_order_ase"],
        required_backends=["ase"],
        description="Split XYZ into named fragments using 1-based atom indices in file order.",
    ),
    "filter_molecules_by_descriptors": WorkflowCatalogEntry(
        workflow_id="filter_molecules_by_descriptors",
        task_type="descriptor_calculation",
        input_types=["smiles_csv"],
        tools=["compute_rdkit_descriptors", "filter_molecules_by_descriptors"],
        required_backends=["rdkit"],
        description="Compute RDKit descriptors and filter rows by descriptor threshold rules.",
    ),
    "openbabel_convert_structure": WorkflowCatalogEntry(
        workflow_id="openbabel_convert_structure",
        task_type="conversion",
        input_types=["xyz", "smiles", "sdf"],
        tools=["generate_small_molecule_openbabel"],
        required_backends=["openbabel"],
        description="Convert structures and SMILES formats using Open Babel.",
    ),
    "xyz_to_geometry_analysis": WorkflowCatalogEntry(
        workflow_id="xyz_to_geometry_analysis",
        task_type="geometry_analysis",
        input_types=["xyz", "xyz_list"],
        tools=["analyze_geometry_ase"],
        required_backends=["ase"],
        description="Analyze XYZ geometry and interatomic distance statistics using ASE.",
    ),

    "molsimplify_build_metal_complex": WorkflowCatalogEntry(
        workflow_id="molsimplify_build_metal_complex",
        task_type="metal_complex_generation",
        input_types=["metal_complex_build_request"],
        tools=[],
        required_backends=["molsimplify"],
        description="Pilot high-level workflow contract for molSimplify metal-complex generation from structured build requests.",
    ),
    "xyz_to_morfeus_buried_volume": WorkflowCatalogEntry(
        workflow_id="xyz_to_morfeus_buried_volume",
        task_type="steric_descriptor_calculation",
        input_types=["xyz"],
        tools=[],
        required_backends=["morfeus"],
        description="Pilot high-level workflow contract for Morfeus buried-volume steric descriptor reports from XYZ structures.",
    ),
    "xyz_to_morfeus_cone_angle": WorkflowCatalogEntry(
        workflow_id="xyz_to_morfeus_cone_angle",
        task_type="steric_descriptor_calculation",
        input_types=["xyz"],
        tools=[],
        required_backends=["morfeus"],
        description="Pilot high-level workflow contract for Morfeus cone-angle steric descriptor reports from XYZ structures.",
    ),
    "xyz_to_morfeus_sterimol": WorkflowCatalogEntry(
        workflow_id="xyz_to_morfeus_sterimol",
        task_type="steric_descriptor_calculation",
        input_types=["xyz"],
        tools=[],
        required_backends=["morfeus"],
        description="Pilot high-level workflow contract for Morfeus Sterimol steric descriptor reports from XYZ structures.",
    ),
}

_WORKFLOW_CONTRACT_DEFS: dict[str, dict] = {
    "smiles_to_3d_rdkit": {"operation": "structure_generation", "method": "rdkit", "geometry_modified": True, "artifact_type": "generated_xyz"},
    "smiles_to_conformers_rdkit": {"operation": "conformer_generation", "method": "rdkit", "geometry_modified": True, "artifact_type": "conformer_ensemble"},
    "smiles_to_3d_openbabel": {"operation": "structure_generation", "method": "openbabel", "geometry_modified": True, "artifact_type": "generated_xyz"},
    "smiles_to_xtb_relax": {"operation": "geometry_optimization", "method": "xtb", "geometry_modified": True, "artifact_type": "xtb_relax_result"},
    "xyz_to_xtb_relax": {"operation": "geometry_optimization", "method": "xtb", "geometry_modified": True, "artifact_type": "optimized_geometry"},
    "validate_xyz": {"operation": "structure_validation", "method": None, "geometry_modified": False, "artifact_type": "validation_report"},
    "smiles_to_rdkit_descriptors": {"operation": "descriptor_calculation", "method": "rdkit", "geometry_modified": False, "artifact_type": "rdkit_descriptor_table"},
    "xyz_to_xtb_singlepoint": {"operation": "singlepoint_energy", "method": "xtb", "geometry_modified": False, "artifact_type": "xtb_singlepoint_result"},
    "compare_two_geometries": {"operation": "structure_comparison", "method": None, "geometry_modified": False, "artifact_type": "geometry_comparison_report"},
    "xyz_to_rmsd": {"operation": "rmsd_calculation", "method": None, "geometry_modified": False, "artifact_type": "rmsd_report"},
    "count_element_atoms": {"operation": "element_counting", "method": None, "geometry_modified": False, "artifact_type": "element_count_report"},
    "split_molecule_by_file_order": {"operation": "molecule_splitting", "method": None, "geometry_modified": False, "artifact_type": "molecule_split_report"},
    "filter_molecules_by_descriptors": {"operation": "descriptor_filtering", "method": "rdkit", "geometry_modified": False, "artifact_type": "descriptor_filter_report"},
    "xyz_to_geometry_analysis": {"operation": "geometry_analysis", "method": None, "geometry_modified": False, "artifact_type": "geometry_analysis_report"},
    "openbabel_convert_structure": {"operation": "format_conversion", "method": "openbabel", "geometry_modified": False, "artifact_type": "converted_structure"},
    "molsimplify_build_metal_complex": {"operation": "metal_complex_generation", "method": "molsimplify", "geometry_modified": True, "artifact_type": "molsimplify_complex_structure"},
    "xyz_to_morfeus_buried_volume": {"operation": "steric_descriptor_calculation", "method": "morfeus", "geometry_modified": False, "artifact_type": "morfeus_buried_volume_report"},
    "xyz_to_morfeus_cone_angle": {"operation": "steric_descriptor_calculation", "method": "morfeus", "geometry_modified": False, "artifact_type": "morfeus_cone_angle_report"},
    "xyz_to_morfeus_sterimol": {"operation": "steric_descriptor_calculation", "method": "morfeus", "geometry_modified": False, "artifact_type": "morfeus_sterimol_report"},
}

for _wf_id, _entry in WORKFLOW_CATALOG.items():
    _meta = _WORKFLOW_CONTRACT_DEFS[_wf_id]
    _entry.contract = WorkflowContract(
        workflow_id=_wf_id,
        task_type=_entry.task_type,
        operation=_meta["operation"],
        method=_meta["method"],
        input_ports=[WorkflowPortContract(name="input", role="input", data_types=list(_entry.input_types), required=True, multiple="list" in ",".join(_entry.input_types) or "pair" in ",".join(_entry.input_types), description=f"Accepted input types for {_wf_id}.", geometry_modified=False)],
        output_ports=[WorkflowPortContract(name="result", role="output", data_types=[_meta["artifact_type"], "workflow_summary"], required=True, multiple=False, description=f"Primary workflow output for {_wf_id}.", geometry_modified=_meta["geometry_modified"])],
        required_backends=list(_entry.required_backends),
        execution_policy=_default_execution_policy(),
        geometry_modified=_meta["geometry_modified"],
        side_effects=["writes_batch_artifacts"],
        cost_class="medium" if "xtb" in _entry.workflow_id else "low",
        artifact_outputs=[WorkflowArtifactOutputDescriptor(name="primary_output", artifact_type=_meta["artifact_type"], produced_on="success", description="Primary produced artifact.", geometry_modified=_meta["geometry_modified"])],
        llm_use_when=[f"Use for {_meta['operation'].replace('_', ' ')} tasks."],
        llm_do_not_use_when=["Do not use when user requests a different operation."] + (["Do not expose low-level molSimplify tools; use only this high-level workflow ID.", "Do not treat dry-run molSimplify previews as existing geometry inputs."] if _wf_id == "molsimplify_build_metal_complex" else []) + (["Do not use for geometry optimization or relaxation requests."] if _wf_id == "xyz_to_xtb_singlepoint" else []) + (["Do not use when user explicitly says do not modify geometry."] if _wf_id in {"xyz_to_xtb_relax", "smiles_to_xtb_relax"} else []) + (["Do not treat Morfeus report outputs as geometry inputs."] if _wf_id.startswith("xyz_to_morfeus_") else []),
        notes=["Phase 16.6 molSimplify pilot high-level contract; build reports are not geometries and dry-run previews are not existing generated structures." if _wf_id == "molsimplify_build_metal_complex" else ("Phase 16.5 Morfeus pilot high-level contract." if _wf_id.startswith("xyz_to_morfeus_") else "Phase 15.0 typed workflow contract foundation.")],
    ).model_dump()


def list_workflows() -> list[WorkflowCatalogEntry]:
    return [WORKFLOW_CATALOG[k] for k in sorted(WORKFLOW_CATALOG)]


def get_workflow_entry(workflow_id: str) -> WorkflowCatalogEntry:
    if workflow_id not in WORKFLOW_CATALOG:
        raise KeyError(f"Unknown workflow_id: {workflow_id}")
    return WORKFLOW_CATALOG[workflow_id]


def check_workflow_backend_readiness(workflow_id: str) -> dict:
    entry = get_workflow_entry(workflow_id)
    caps = list_backend_capabilities()
    required = list(entry.required_backends)
    available = [b for b in required if b in caps and caps[b].status == "available"]
    missing = [b for b in required if b not in available]
    return {
        "workflow_id": workflow_id,
        "ready": len(missing) == 0,
        "required_backends": required,
        "available_backends": available,
        "missing_backends": missing,
        "warnings": [f"Missing backend: {b}" for b in missing],
    }


def validate_workflow_contracts() -> dict:
    missing: list[str] = []
    invalid: list[str] = []
    for wf_id, entry in WORKFLOW_CATALOG.items():
        if not entry.contract:
            missing.append(wf_id)
            continue
        try:
            contract = WorkflowContract.model_validate(entry.contract)
            if contract.workflow_id != wf_id or sorted(contract.required_backends) != sorted(entry.required_backends):
                invalid.append(wf_id)
        except Exception:
            invalid.append(wf_id)
    status = "ok" if not missing and not invalid else "error"
    return {"status": status, "schema_version": "lmola.workflow_contract.v1", "workflow_count": len(WORKFLOW_CATALOG), "missing_contracts": sorted(missing), "invalid_contracts": sorted(invalid), "warnings": []}
