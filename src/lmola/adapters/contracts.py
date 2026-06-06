from __future__ import annotations

from enum import StrEnum
import re
from typing import Any, Mapping, Protocol

from pydantic import BaseModel, Field, ValidationError, model_validator


ADAPTER_CONTRACT_SCHEMA_VERSION = "lmola.adapter_contract.v1"


class AdapterRiskClass(StrEnum):
    SAFE_LOCAL = "SAFE_LOCAL"
    OPTIONAL_LOCAL = "OPTIONAL_LOCAL"
    EXTERNAL_EXECUTION = "EXTERNAL_EXECUTION"
    HEAVY_ENGINE = "HEAVY_ENGINE"
    NETWORK_OR_CLOUD = "NETWORK_OR_CLOUD"


class SmokeExecutionSupport(StrEnum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    SKIPPED_UNAVAILABLE = "skipped_unavailable"


class ArtifactRole(StrEnum):
    INPUT_FILE = "input_file"
    OUTPUT_FILE = "output_file"
    LOG_FILE = "log_file"
    STRUCTURED_JSON_RESULT = "structured_json_result"
    TRAJECTORY = "trajectory"
    DIAGNOSTICS = "diagnostics"


class AdapterAvailability(BaseModel):
    registered: bool = True
    backend_available: bool
    importable: bool | None = None
    executable: str | None = None
    unavailable_reason: str | None = None
    smoke_execution: SmokeExecutionSupport = SmokeExecutionSupport.UNSUPPORTED

    @model_validator(mode="after")
    def _check_unavailable_reason(self) -> AdapterAvailability:
        if not self.backend_available and not self.unavailable_reason:
            raise ValueError("unavailable adapters must provide unavailable_reason")
        if self.backend_available and self.smoke_execution == SmokeExecutionSupport.SKIPPED_UNAVAILABLE:
            raise ValueError("available adapters cannot report skipped_unavailable smoke execution")
        return self


class AdapterArtifactContract(BaseModel):
    name: str
    role: ArtifactRole
    description: str
    required: bool = False
    file_extensions: list[str] = Field(default_factory=list)
    media_types: list[str] = Field(default_factory=list)


class AdapterMetadata(BaseModel):
    schema_version: str = ADAPTER_CONTRACT_SCHEMA_VERSION
    adapter_id: str
    display_name: str
    backend_name: str
    backend_version: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    availability: AdapterAvailability
    risk_class: AdapterRiskClass
    artifact_contracts: list[AdapterArtifactContract] = Field(default_factory=list)


class AdapterLike(Protocol):
    def get_metadata(self) -> AdapterMetadata | Mapping[str, Any]:
        ...


class AdapterConformanceError(ValueError):
    pass


_ADAPTER_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")


def _metadata_from_adapter(adapter: AdapterMetadata | Mapping[str, Any] | AdapterLike) -> AdapterMetadata:
    if isinstance(adapter, AdapterMetadata):
        return adapter
    if isinstance(adapter, Mapping):
        return AdapterMetadata.model_validate(adapter)
    get_metadata = getattr(adapter, "get_metadata", None)
    if callable(get_metadata):
        return _metadata_from_adapter(get_metadata())
    metadata = getattr(adapter, "metadata", None)
    if metadata is not None:
        return _metadata_from_adapter(metadata)
    raise TypeError("adapter must be AdapterMetadata, mapping, or expose get_metadata()/metadata")


def validate_adapter_metadata(adapter: AdapterMetadata | Mapping[str, Any] | AdapterLike) -> list[str]:
    errors: list[str] = []
    try:
        metadata = _metadata_from_adapter(adapter)
    except (TypeError, ValidationError, ValueError) as exc:
        return [str(exc)]

    if metadata.schema_version != ADAPTER_CONTRACT_SCHEMA_VERSION:
        errors.append(
            f"{metadata.adapter_id}: schema_version must be {ADAPTER_CONTRACT_SCHEMA_VERSION}"
        )
    if not _ADAPTER_ID_RE.match(metadata.adapter_id):
        errors.append(f"{metadata.adapter_id}: adapter_id must match {_ADAPTER_ID_RE.pattern}")
    for field_name in ("display_name", "backend_name"):
        if not getattr(metadata, field_name).strip():
            errors.append(f"{metadata.adapter_id}: {field_name} must be non-empty")
    if not metadata.capabilities:
        errors.append(f"{metadata.adapter_id}: capabilities must contain at least one capability")
    if not metadata.availability.registered:
        errors.append(f"{metadata.adapter_id}: availability.registered must be true")
    if metadata.availability.backend_available is False and not metadata.availability.unavailable_reason:
        errors.append(f"{metadata.adapter_id}: unavailable backend must include unavailable_reason")
    for artifact in metadata.artifact_contracts:
        if not artifact.name.strip():
            errors.append(f"{metadata.adapter_id}: artifact contract name must be non-empty")
        if not artifact.description.strip():
            errors.append(f"{metadata.adapter_id}: artifact {artifact.name} needs a description")
    return errors


def assert_adapter_conformance(
    adapter: AdapterMetadata | Mapping[str, Any] | AdapterLike,
) -> AdapterMetadata:
    errors = validate_adapter_metadata(adapter)
    if errors:
        raise AdapterConformanceError("; ".join(errors))
    return _metadata_from_adapter(adapter)


def assert_registered_adapters_conform(
    adapters: Mapping[str, AdapterMetadata | Mapping[str, Any] | AdapterLike],
) -> dict[str, AdapterMetadata]:
    validated: dict[str, AdapterMetadata] = {}
    errors: list[str] = []
    for registry_id, adapter in adapters.items():
        try:
            metadata = assert_adapter_conformance(adapter)
        except AdapterConformanceError as exc:
            errors.append(f"{registry_id}: {exc}")
            continue
        if metadata.adapter_id != registry_id:
            errors.append(f"{registry_id}: adapter_id mismatch ({metadata.adapter_id})")
            continue
        validated[registry_id] = metadata
    if errors:
        raise AdapterConformanceError("; ".join(errors))
    return validated
