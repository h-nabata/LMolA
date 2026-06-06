from __future__ import annotations

from lmola.adapters.contracts import (
    AdapterArtifactContract,
    AdapterAvailability,
    AdapterMetadata,
    AdapterOperationProfile,
    AdapterRiskClass,
    ArtifactRole,
)
from lmola.adapters.smoke import list_optional_smoke_specs, run_optional_smoke_check
from lmola.backends.capabilities import BackendCapability, list_backend_capabilities, resolve_backend_capability


_RISK_BY_INTEGRATION_TYPE = {
    "mock": AdapterRiskClass.SAFE_LOCAL,
    "python_import": AdapterRiskClass.OPTIONAL_LOCAL,
    "cli": AdapterRiskClass.EXTERNAL_EXECUTION,
    "hybrid": AdapterRiskClass.EXTERNAL_EXECUTION,
    "external": AdapterRiskClass.NETWORK_OR_CLOUD,
}


_BACKEND_FAMILY = {
    "ase": ("structure_io_validation", "python_library"),
    "rdkit": ("cheminformatics", "optional_python_library"),
    "openbabel": ("format_conversion", "optional_cli"),
    "xtb": ("semiempirical_quantum", "local_external_engine"),
    "molsimplify": ("metal_complex_generation", "optional_cli"),
    "morfeus": ("steric_descriptors", "optional_python_library"),
    "local_llm": ("llm", "external_service"),
    "mock_llm": ("test_double", "in_process"),
}


_KNOWN_LIMITATIONS = {
    "ase": [
        "Limited to validation, geometry analysis, and structure bookkeeping in LMolA.",
        "Not exposed as a general calculator execution layer.",
    ],
    "rdkit": [
        "Optional backend; absence must not fail default tests.",
        "LMolA exposes descriptors and light structure/conformer generation only.",
    ],
    "openbabel": [
        "Optional CLI backend; absence must not fail default tests.",
        "LMolA exposes conversion and light 3D generation only.",
    ],
    "xtb": [
        "External local execution remains behind dry_run, allow_execution, and confirm gates.",
        "Single-point result artifacts are not geometry artifacts.",
    ],
}


_OPERATION_PROFILES: dict[str, list[AdapterOperationProfile]] = {
    "ase": [
        AdapterOperationProfile(
            operation_id="structure_validation",
            display_name="XYZ validation",
            workflow_ids=["validate_xyz"],
            task_type="validation",
            execution_mode="in_process",
            operation_risk="local_validation",
            input_artifact_types=["xyz_geometry"],
            output_artifact_types=["validation_report", "validated_xyz"],
            geometry_modified=False,
            parameter_binding_keys=["input_files.primary_structure"],
            smoke_strategy="import/version probe only",
            known_limitations=["Read-only validation; no calculator execution."],
        ),
        AdapterOperationProfile(
            operation_id="geometry_analysis",
            display_name="Geometry analysis",
            workflow_ids=[
                "xyz_to_geometry_analysis",
                "compare_two_geometries",
                "xyz_to_rmsd",
                "count_element_atoms",
                "split_molecule_by_file_order",
            ],
            task_type="geometry_analysis",
            execution_mode="in_process",
            operation_risk="local_validation",
            input_artifact_types=["xyz_geometry"],
            output_artifact_types=[
                "geometry_analysis_report",
                "geometry_comparison_report",
                "rmsd_report",
                "element_count_report",
                "molecule_split_report",
            ],
            geometry_modified=False,
            parameter_binding_keys=["input_files.primary_structure", "atom_selection.element", "atom_selection.atom_ranges"],
            smoke_strategy="import/version probe only",
            known_limitations=["Analysis/report outputs are not reusable geometry artifacts."],
        ),
    ],
    "rdkit": [
        AdapterOperationProfile(
            operation_id="descriptor_calculation",
            display_name="RDKit descriptors and filtering",
            workflow_ids=["smiles_to_rdkit_descriptors", "filter_molecules_by_descriptors"],
            task_type="descriptor_calculation",
            execution_mode="in_process",
            operation_risk="local_validation",
            input_artifact_types=["smiles", "smiles_csv"],
            output_artifact_types=["rdkit_descriptor_table", "descriptor_filter_report"],
            geometry_modified=False,
            parameter_binding_keys=["input_files.smiles_input", "input_files.smiles_table", "descriptor_thresholds"],
            smoke_strategy="import/version probe only",
            known_limitations=["Descriptor tables and filter reports are not geometry artifacts."],
        ),
        AdapterOperationProfile(
            operation_id="conformer_generation",
            display_name="RDKit conformer generation",
            workflow_ids=["smiles_to_3d_rdkit", "smiles_to_conformers_rdkit"],
            task_type="conformer_generation",
            execution_mode="in_process",
            operation_risk="light_generation",
            input_artifact_types=["smiles", "smiles_csv"],
            output_artifact_types=["generated_xyz", "conformer_ensemble"],
            geometry_modified=True,
            parameter_binding_keys=["num_conformers", "random_seed", "output_format"],
            smoke_strategy="import/version probe only; no generation in default smoke",
            known_limitations=["No broad RDKit API wrapping; only existing LMolA workflows are in scope."],
        ),
    ],
    "openbabel": [
        AdapterOperationProfile(
            operation_id="format_conversion",
            display_name="Open Babel structure conversion",
            workflow_ids=["openbabel_convert_structure"],
            task_type="conversion",
            execution_mode="cli",
            operation_risk="local_conversion",
            input_artifact_types=["xyz_geometry", "smiles", "sdf"],
            output_artifact_types=["converted_structure", "openbabel_conversion_report"],
            geometry_modified=False,
            parameter_binding_keys=["input_format", "output_format", "smiles_input"],
            smoke_strategy="executable discovery/version probe only",
            known_limitations=["Pure conversion is non-geometry-modifying unless 3D generation is explicitly requested."],
        ),
        AdapterOperationProfile(
            operation_id="smiles_3d_generation",
            display_name="Open Babel light 3D generation",
            workflow_ids=["smiles_to_3d_openbabel"],
            task_type="structure_generation",
            execution_mode="cli",
            operation_risk="light_generation",
            input_artifact_types=["smiles", "smiles_csv"],
            output_artifact_types=["generated_xyz"],
            geometry_modified=True,
            parameter_binding_keys=["smiles_input", "output_format", "generate_3d"],
            smoke_strategy="executable discovery/version probe only; no generation in default smoke",
            known_limitations=["No broad Open Babel feature wrapping."],
        ),
    ],
    "xtb": [
        AdapterOperationProfile(
            operation_id="singlepoint_energy",
            display_name="xTB single-point energy",
            workflow_ids=["xyz_to_xtb_singlepoint"],
            task_type="property_calculation",
            execution_mode="cli",
            operation_risk="external_execution",
            input_artifact_types=["xyz_geometry", "validated_xyz", "optimized_geometry", "converted_structure"],
            output_artifact_types=["xtb_singlepoint_result"],
            geometry_modified=False,
            parameter_binding_keys=["input_files.primary_structure", "charge", "multiplicity", "solvent.name", "solvent.model"],
            smoke_strategy="import/executable/version probe only; no calculation in default smoke",
            known_limitations=["Result artifact is not geometry and must not be used as primary_structure."],
        ),
        AdapterOperationProfile(
            operation_id="geometry_optimization",
            display_name="xTB relaxation",
            workflow_ids=["xyz_to_xtb_relax", "smiles_to_xtb_relax"],
            task_type="relaxation",
            execution_mode="cli",
            operation_risk="geometry_modifying_external_execution",
            input_artifact_types=["xyz_geometry", "validated_xyz", "generated_xyz", "converted_structure"],
            output_artifact_types=["optimized_geometry", "relaxed_xyz", "xtb_relax_result"],
            geometry_modified=True,
            parameter_binding_keys=[
                "input_files.primary_structure",
                "charge",
                "multiplicity",
                "geometry_optimization_controls.force_threshold",
                "geometry_optimization_controls.max_steps",
            ],
            smoke_strategy="import/executable/version probe only; no optimization in default smoke",
            known_limitations=["Real execution remains gated by dry_run=false, allow_execution=true, confirm=true."],
        ),
    ],
}


def _availability_from_capability(capability: BackendCapability) -> AdapterAvailability:
    if capability.backend_id not in list_optional_smoke_specs():
        backend_available = capability.status == "available"
        importable = None if not capability.python_modules else backend_available
        executable = next((path for path in capability.executable_paths.values() if path), None)
        return AdapterAvailability(
            registered=True,
            backend_available=backend_available,
            importable=importable,
            executable=executable,
            unavailable_reason=None if backend_available else "backend probe did not report availability",
        )

    smoke_result = run_optional_smoke_check(capability.backend_id)
    backend_available = smoke_result.status == "available"
    executable = next((path for path in capability.executable_paths.values() if path), None)
    if smoke_result.executable:
        executable = smoke_result.executable
    importable = None
    if capability.python_modules:
        importable = smoke_result.importable
    return AdapterAvailability(
        registered=True,
        backend_available=backend_available,
        importable=importable,
        executable=executable,
        unavailable_reason=smoke_result.unavailable_reason,
        smoke_execution=smoke_result.smoke_execution,
    )


def _artifact_contracts_from_capability(
    capability: BackendCapability,
) -> list[AdapterArtifactContract]:
    contracts: list[AdapterArtifactContract] = []
    if capability.supported_input_types:
        contracts.append(
            AdapterArtifactContract(
                name="declared_inputs",
                role=ArtifactRole.INPUT_FILE,
                description="Input artifact types accepted by this adapter.",
                required=True,
            )
        )
    if capability.supported_output_types:
        role = ArtifactRole.STRUCTURED_JSON_RESULT
        if any(output in {"xyz", "sdf", "relaxed_xyz", "conformer_ensemble"} for output in capability.supported_output_types):
            role = ArtifactRole.OUTPUT_FILE
        contracts.append(
            AdapterArtifactContract(
                name="declared_outputs",
                role=role,
                description="Output artifact types produced by this adapter.",
                required=False,
            )
        )
    if capability.integration_type in {"cli", "hybrid", "external"}:
        contracts.append(
            AdapterArtifactContract(
                name="execution_diagnostics",
                role=ArtifactRole.DIAGNOSTICS,
                description="Diagnostics describing command, process, or service boundaries.",
                required=False,
            )
        )
    return contracts


def adapter_metadata_from_backend_capability(capability: BackendCapability) -> AdapterMetadata:
    risk_class = _RISK_BY_INTEGRATION_TYPE.get(
        capability.integration_type, AdapterRiskClass.OPTIONAL_LOCAL
    )
    backend_family, backend_type = _BACKEND_FAMILY.get(
        capability.backend_id, (capability.category, capability.integration_type)
    )
    smoke_version = None
    if capability.backend_id in list_optional_smoke_specs():
        smoke_version = run_optional_smoke_check(capability.backend_id).version
    return AdapterMetadata(
        adapter_id=capability.backend_id,
        display_name=capability.display_name,
        backend_name=capability.backend_id,
        backend_family=backend_family,
        backend_type=backend_type,
        backend_version=smoke_version or capability.version,
        optional_dependency=capability.optional_extra is not None,
        capabilities=sorted(set(capability.supported_tasks or capability.required_for)),
        availability=_availability_from_capability(capability),
        risk_class=risk_class,
        execution_modes=list(capability.execution_modes),
        known_limitations=list(_KNOWN_LIMITATIONS.get(capability.backend_id, [])),
        conformance_status="ok",
        operation_profiles=list(_OPERATION_PROFILES.get(capability.backend_id, [])),
        artifact_contracts=_artifact_contracts_from_capability(capability),
    )


def resolve_adapter_metadata(adapter_id: str) -> AdapterMetadata | None:
    capability = resolve_backend_capability(adapter_id)
    if capability is None:
        return None
    return adapter_metadata_from_backend_capability(capability)


def list_adapter_metadata() -> dict[str, AdapterMetadata]:
    return {
        adapter_id: adapter_metadata_from_backend_capability(capability)
        for adapter_id, capability in list_backend_capabilities().items()
    }
