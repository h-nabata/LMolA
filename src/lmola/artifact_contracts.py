from __future__ import annotations

from pydantic import BaseModel, Field

from lmola.workflows.catalog import WORKFLOW_CATALOG

ARTIFACT_CONTRACT_SCHEMA_VERSION = "lmola.artifact_contract.v1"
ARTIFACT_REGISTRY_SCHEMA_VERSION = "lmola.artifact_registry.v1"


class ArtifactContract(BaseModel):
    schema_version: str = ARTIFACT_CONTRACT_SCHEMA_VERSION
    artifact_type: str
    category: str
    description: str
    produced_by: list[str] = Field(default_factory=list)
    consumed_by: list[str] = Field(default_factory=list)
    file_extensions: list[str] = Field(default_factory=list)
    media_types: list[str] = Field(default_factory=list)
    required_fields: list[str] = Field(default_factory=list)
    optional_fields: list[str] = Field(default_factory=list)
    semantic_tags: list[str] = Field(default_factory=list)
    geometry_role: str | None = None
    geometry_modified: bool | None = None
    llm_summary_hint: str
    safety_notes: list[str] = Field(default_factory=list)
    compatible_input_data_types: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ArtifactRegistry(BaseModel):
    schema_version: str = ARTIFACT_REGISTRY_SCHEMA_VERSION
    artifact_contract_schema_version: str = ARTIFACT_CONTRACT_SCHEMA_VERSION
    artifact_contracts: dict[str, ArtifactContract] = Field(default_factory=dict)


_DEF = {
"xyz_geometry": dict(category="structure",description="Input XYZ geometry.",produced_by=[],consumed_by=["validate_xyz","xyz_to_xtb_singlepoint","xyz_to_xtb_relax","compare_two_geometries","xyz_to_rmsd","count_element_atoms","split_molecule_by_file_order","xyz_to_geometry_analysis"],file_extensions=[".xyz"],media_types=["chemical/x-xyz"],required_fields=["path"],semantic_tags=["xyz","geometry","input"],geometry_role="raw_geometry",geometry_modified=False,llm_summary_hint="Raw XYZ structure, not validated or optimized."),
"validated_xyz": dict(category="structure",description="Validated XYZ geometry.",produced_by=["validate_xyz"],consumed_by=["xyz_to_xtb_singlepoint","xyz_to_xtb_relax"],file_extensions=[".xyz"],media_types=["chemical/x-xyz"],required_fields=["status","geometry_modified"],semantic_tags=["validated","xyz","geometry"],geometry_role="validated_geometry",geometry_modified=False,llm_summary_hint="Validated XYZ structure safe for downstream calculations."),
"generated_xyz": dict(category="structure",description="Generated 3D geometry from SMILES.",produced_by=["smiles_to_3d_rdkit","smiles_to_3d_openbabel"],consumed_by=["smiles_to_xtb_relax"],file_extensions=[".xyz"],media_types=["chemical/x-xyz"],required_fields=["status","geometry_modified"],semantic_tags=["generated","xyz","geometry"],geometry_role="generated_geometry",geometry_modified=True,llm_summary_hint="Generated geometry candidate; may require validation/relaxation."),
"relaxed_xyz": dict(category="structure",description="Relaxed/optimized XYZ geometry.",produced_by=["xyz_to_xtb_relax","smiles_to_xtb_relax"],consumed_by=["compare_two_geometries","xyz_to_rmsd"],file_extensions=[".xyz"],media_types=["chemical/x-xyz"],required_fields=["status","geometry_modified"],semantic_tags=["relaxed","xyz","geometry"],geometry_role="relaxed_geometry",geometry_modified=True,llm_summary_hint="Relaxed geometry output from optimization workflow."),
"xtb_singlepoint_result": dict(category="result",description="xTB single-point energy result payload.",produced_by=["xyz_to_xtb_singlepoint"],consumed_by=[],file_extensions=[".json"],media_types=["application/json"],required_fields=["status","geometry_modified"],optional_fields=["energy","energy_unit","method"],semantic_tags=["xtb","singlepoint","energy"],geometry_role="non_geometry",geometry_modified=False,llm_summary_hint="Energy/report data only; this is not an optimized geometry."),
"xtb_relax_result": dict(category="result",description="xTB relaxation result payload with optimization metadata.",produced_by=["smiles_to_xtb_relax","xyz_to_xtb_relax"],consumed_by=[],file_extensions=[".json"],media_types=["application/json"],required_fields=["status","geometry_modified"],semantic_tags=["xtb","relaxation","result"],geometry_role="non_geometry",geometry_modified=False,llm_summary_hint="Relaxation report/metadata only; this is not a reusable geometry artifact."),
"geometry_analysis_report": dict(category="report",description="Geometry analysis statistics report.",produced_by=["xyz_to_geometry_analysis"],consumed_by=[],file_extensions=[".json",".csv"],media_types=["application/json","text/csv"],required_fields=["status"],semantic_tags=["geometry_analysis"],geometry_role="non_geometry",geometry_modified=False,llm_summary_hint="Report of distance and geometry statistics."),
"rmsd_report": dict(category="report",description="RMSD comparison report between two structures.",produced_by=["xyz_to_rmsd"],consumed_by=[],file_extensions=[".json"],media_types=["application/json"],required_fields=["status","rmsd"],semantic_tags=["rmsd","geometry_comparison"],geometry_role="geometry_pair",geometry_modified=False,llm_summary_hint="RMSD comparison report; does not modify structures."),
"geometry_comparison_report": dict(category="report",description="General geometry comparison report.",produced_by=["compare_two_geometries"],consumed_by=[],file_extensions=[".json"],media_types=["application/json"],required_fields=["status"],semantic_tags=["geometry_comparison"],geometry_role="geometry_pair",geometry_modified=False,llm_summary_hint="Comparison report for two geometries including RMSD-like metrics."),
"element_count_report": dict(category="report",description="Element count report.",produced_by=["count_element_atoms"],consumed_by=[],file_extensions=[".json"],media_types=["application/json"],required_fields=["status"],semantic_tags=["element_count"],geometry_role="non_geometry",geometry_modified=False,llm_summary_hint="Counts atoms by element symbol."),
"molecule_split_report": dict(category="report",description="Molecule split/fragmentation report.",produced_by=["split_molecule_by_file_order"],consumed_by=[],file_extensions=[".json"],media_types=["application/json"],required_fields=["status"],semantic_tags=["molecule_split"],geometry_role="non_geometry",geometry_modified=False,llm_summary_hint="Report of fragment split results from input geometry."),
"rdkit_descriptor_table": dict(category="table",description="RDKit descriptor table.",produced_by=["smiles_to_rdkit_descriptors"],consumed_by=["filter_molecules_by_descriptors"],file_extensions=[".csv",".json"],media_types=["text/csv","application/json"],required_fields=["status"],semantic_tags=["rdkit","descriptors"],geometry_role="non_geometry",geometry_modified=False,llm_summary_hint="Tabular descriptor values, not geometry."),
"descriptor_filter_report": dict(category="report",description="Descriptor-based filtering report.",produced_by=["filter_molecules_by_descriptors"],consumed_by=[],file_extensions=[".json",".csv"],media_types=["application/json","text/csv"],required_fields=["status"],semantic_tags=["descriptor_filtering"],geometry_role="non_geometry",geometry_modified=False,llm_summary_hint="Filtering outcome report based on descriptor thresholds."),
"conformer_ensemble": dict(category="structure",description="Conformer ensemble structure set.",produced_by=["smiles_to_conformers_rdkit"],consumed_by=[],file_extensions=[".xyz",".sdf"],media_types=["chemical/x-xyz","chemical/x-mdl-sdfile"],required_fields=["status","geometry_modified"],semantic_tags=["conformer","ensemble"],geometry_role="generated_geometry",geometry_modified=True,llm_summary_hint="Set of generated conformer geometries."),
"optimized_geometry": dict(category="structure",description="Geometry produced by structure optimization workflows.",produced_by=["xyz_to_xtb_relax","smiles_to_xtb_relax"],consumed_by=["validate_xyz","xyz_to_geometry_analysis","xyz_to_rmsd","compare_two_geometries","xyz_to_xtb_singlepoint","xyz_to_xtb_relax"],file_extensions=[".xyz"],media_types=["chemical/x-xyz"],required_fields=["status","geometry_modified"],semantic_tags=["optimized","relaxed","geometry"],geometry_role="relaxed_geometry",geometry_modified=True,llm_summary_hint="Optimized structure artifact that can be reused as geometry input.",compatible_input_data_types=["primary_structure"],notes=["This is a structure artifact and remains distinct from xtb_relax_result metadata/report artifacts."]),
"converted_structure": dict(category="structure",description="Converted molecular structure produced by format conversion.",produced_by=["openbabel_convert_structure"],consumed_by=["validate_xyz","xyz_to_xtb_singlepoint","xyz_to_xtb_relax","xyz_to_geometry_analysis","compare_two_geometries","xyz_to_rmsd"],file_extensions=[".xyz",".sdf",".mol",".pdb"],media_types=["chemical/x-xyz","chemical/x-mdl-sdfile","chemical/x-mdl-molfile","chemical/x-pdb"],required_fields=["status","geometry_modified"],semantic_tags=["conversion","structure","format"],geometry_role="converted_geometry",geometry_modified=False,llm_summary_hint="Format-converted structure artifact; geometry is unchanged unless conversion explicitly generates 3D.",compatible_input_data_types=["primary_structure"],notes=["Pure format conversion does not modify geometry.","When conversion generates 3D coordinates from connectivity-only input, workflow output descriptors may set geometry_modified=true while artifact_type remains converted_structure."]),
"validation_report": dict(category="report",description="Validation report for XYZ input.",produced_by=["validate_xyz"],consumed_by=[],file_extensions=[".json"],media_types=["application/json"],required_fields=["status"],semantic_tags=["validation"],geometry_role="non_geometry",geometry_modified=False,llm_summary_hint="Validation status and errors/warnings for geometry input."),
"workflow_summary": dict(category="summary",description="Workflow-level execution summary metadata.",produced_by=["workflow_meta"],consumed_by=[],file_extensions=[".json",".csv"],media_types=["application/json","text/csv"],required_fields=["status"],semantic_tags=["workflow","summary"],geometry_role="non_geometry",geometry_modified=None,llm_summary_hint="Top-level workflow run summary and counters."),
"triage_report": dict(category="diagnostic",description="Artifact triage diagnostic report.",produced_by=["workflow_meta"],consumed_by=[],file_extensions=[".json"],media_types=["application/json"],required_fields=["status"],semantic_tags=["triage","diagnostic"],geometry_role="non_geometry",geometry_modified=False,llm_summary_hint="Failure triage/diagnostic summary for artifacts."),
"mcp_audit": dict(category="audit",description="MCP workflow execution audit event.",produced_by=["workflow_meta"],consumed_by=[],file_extensions=[".json"],media_types=["application/json"],required_fields=["status"],semantic_tags=["mcp","audit","safety"],geometry_role="non_geometry",geometry_modified=False,llm_summary_hint="Audit trail for MCP calls and execution gating.")
}


def export_artifact_registry(*, compact: bool = False) -> dict:
    contracts = {k: ArtifactContract(artifact_type=k, **v).model_dump() for k, v in sorted(_DEF.items())}
    registry = ArtifactRegistry(artifact_contracts=contracts).model_dump()
    if compact:
        registry["artifact_contracts"] = {
            k: {
                "category": v["category"],
                "geometry_modified": v["geometry_modified"],
                "geometry_role": v["geometry_role"],
                "semantic_tags": v["semantic_tags"],
                "llm_summary_hint": v["llm_summary_hint"],
                "produced_by": v["produced_by"],
            }
            for k, v in contracts.items()
        }
    return registry


def validate_artifact_contract_registry() -> dict:
    registry = export_artifact_registry(compact=False)
    contracts = registry["artifact_contracts"]
    missing: list[str] = []
    invalid: list[str] = []
    ref_errors: list[str] = []
    meta_allowed = {"workflow_meta"}
    required_fields = {"schema_version", "artifact_type", "category", "description", "produced_by", "consumed_by", "semantic_tags", "geometry_modified", "llm_summary_hint"}

    for at, payload in contracts.items():
        if payload.get("artifact_type") != at:
            invalid.append(at)
        if not required_fields.issubset(payload.keys()):
            invalid.append(at)
        for wf in payload.get("produced_by", []):
            if wf not in WORKFLOW_CATALOG and wf not in meta_allowed:
                ref_errors.append(f"{at}: produced_by unknown workflow_id '{wf}'")

    referenced = {entry.contract.get("artifact_outputs", [{}])[0].get("artifact_type") for entry in WORKFLOW_CATALOG.values()}
    for at in sorted(x for x in referenced if x):
        if at not in contracts:
            missing.append(at)

    status = "ok" if not missing and not invalid and not ref_errors else "error"
    return {"status": status, "schema_version": ARTIFACT_REGISTRY_SCHEMA_VERSION, "artifact_count": len(contracts), "missing_artifact_contracts": sorted(set(missing)), "invalid_artifact_contracts": sorted(set(invalid)), "workflow_artifact_reference_errors": sorted(set(ref_errors)), "warnings": []}
