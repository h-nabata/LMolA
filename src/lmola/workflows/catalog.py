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
}


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
