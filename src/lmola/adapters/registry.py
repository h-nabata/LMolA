from __future__ import annotations

from lmola.adapters.contracts import (
    AdapterArtifactContract,
    AdapterAvailability,
    AdapterMetadata,
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
    smoke_version = None
    if capability.backend_id in list_optional_smoke_specs():
        smoke_version = run_optional_smoke_check(capability.backend_id).version
    return AdapterMetadata(
        adapter_id=capability.backend_id,
        display_name=capability.display_name,
        backend_name=capability.backend_id,
        backend_version=smoke_version or capability.version,
        capabilities=sorted(set(capability.supported_tasks or capability.required_for)),
        availability=_availability_from_capability(capability),
        risk_class=risk_class,
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
