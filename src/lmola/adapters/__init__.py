from __future__ import annotations

from lmola.adapters.contracts import (
    AdapterArtifactContract,
    AdapterAvailability,
    AdapterConformanceError,
    AdapterMetadata,
    AdapterOperationProfile,
    AdapterRiskClass,
    ArtifactRole,
    SmokeExecutionSupport,
    assert_adapter_conformance,
    assert_registered_adapters_conform,
    validate_adapter_metadata,
)
from lmola.adapters.registry import list_adapter_metadata, resolve_adapter_metadata
from lmola.adapters.smoke import (
    OptionalSmokeResult,
    OptionalSmokeSpec,
    list_optional_smoke_results,
    list_optional_smoke_specs,
    run_optional_smoke_check,
)

__all__ = [
    "AdapterArtifactContract",
    "AdapterAvailability",
    "AdapterConformanceError",
    "AdapterMetadata",
    "AdapterOperationProfile",
    "AdapterRiskClass",
    "ArtifactRole",
    "SmokeExecutionSupport",
    "OptionalSmokeResult",
    "OptionalSmokeSpec",
    "assert_adapter_conformance",
    "assert_registered_adapters_conform",
    "list_adapter_metadata",
    "list_optional_smoke_results",
    "list_optional_smoke_specs",
    "resolve_adapter_metadata",
    "run_optional_smoke_check",
    "validate_adapter_metadata",
]
