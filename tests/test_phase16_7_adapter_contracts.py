from __future__ import annotations

import pytest

from lmola.adapters import (
    AdapterArtifactContract,
    AdapterAvailability,
    AdapterConformanceError,
    AdapterMetadata,
    AdapterRiskClass,
    ArtifactRole,
    SmokeExecutionSupport,
    assert_adapter_conformance,
    assert_registered_adapters_conform,
    list_adapter_metadata,
    validate_adapter_metadata,
)


class DummyAdapter:
    def get_metadata(self) -> AdapterMetadata:
        return AdapterMetadata(
            adapter_id="dummy_safe",
            display_name="Dummy Safe Adapter",
            backend_name="python",
            capabilities=["metadata_validation"],
            availability=AdapterAvailability(
                backend_available=True,
                importable=True,
                smoke_execution=SmokeExecutionSupport.SUPPORTED,
            ),
            risk_class=AdapterRiskClass.SAFE_LOCAL,
            artifact_contracts=[
                AdapterArtifactContract(
                    name="result_json",
                    role=ArtifactRole.STRUCTURED_JSON_RESULT,
                    description="Structured dummy result payload.",
                )
            ],
        )


def test_risk_class_values_are_explicit() -> None:
    assert AdapterRiskClass.SAFE_LOCAL.value == "SAFE_LOCAL"
    assert AdapterRiskClass.OPTIONAL_LOCAL.value == "OPTIONAL_LOCAL"
    assert AdapterRiskClass.EXTERNAL_EXECUTION.value == "EXTERNAL_EXECUTION"
    assert AdapterRiskClass.HEAVY_ENGINE.value == "HEAVY_ENGINE"
    assert AdapterRiskClass.NETWORK_OR_CLOUD.value == "NETWORK_OR_CLOUD"


def test_dummy_adapter_passes_conformance() -> None:
    metadata = assert_adapter_conformance(DummyAdapter())
    assert metadata.adapter_id == "dummy_safe"
    assert metadata.availability.backend_available is True
    assert metadata.artifact_contracts[0].role == ArtifactRole.STRUCTURED_JSON_RESULT


def test_metadata_mapping_passes_conformance() -> None:
    metadata = assert_adapter_conformance(
        {
            "adapter_id": "dummy_optional",
            "display_name": "Dummy Optional Adapter",
            "backend_name": "optional-lib",
            "capabilities": ["availability_probe"],
            "availability": {
                "backend_available": False,
                "importable": False,
                "unavailable_reason": "optional-lib is not installed",
                "smoke_execution": "skipped_unavailable",
            },
            "risk_class": "OPTIONAL_LOCAL",
        }
    )
    assert metadata.availability.unavailable_reason == "optional-lib is not installed"
    assert metadata.availability.smoke_execution == SmokeExecutionSupport.SKIPPED_UNAVAILABLE


def test_unavailable_backend_requires_clear_reason() -> None:
    with pytest.raises(ValueError, match="unavailable adapters must provide unavailable_reason"):
        AdapterAvailability(backend_available=False, importable=False)


def test_malformed_adapter_fails_with_useful_error() -> None:
    malformed = {
        "adapter_id": "Bad Adapter ID",
        "display_name": "",
        "backend_name": "bad",
        "capabilities": [],
        "availability": {
            "backend_available": False,
            "importable": False,
            "unavailable_reason": "missing dependency",
        },
        "risk_class": "OPTIONAL_LOCAL",
    }
    errors = validate_adapter_metadata(malformed)
    assert any("adapter_id must match" in error for error in errors)
    assert any("display_name must be non-empty" in error for error in errors)
    assert any("capabilities must contain" in error for error in errors)
    with pytest.raises(AdapterConformanceError, match="adapter_id must match"):
        assert_adapter_conformance(malformed)


def test_registered_adapter_conformance_helper_detects_id_mismatch() -> None:
    adapter = DummyAdapter()
    with pytest.raises(AdapterConformanceError, match="adapter_id mismatch"):
        assert_registered_adapters_conform({"different_id": adapter})


def test_current_backend_adapters_conform_without_optional_tools() -> None:
    adapters = list_adapter_metadata()
    validated = assert_registered_adapters_conform(adapters)
    assert {"ase", "rdkit", "openbabel", "molsimplify", "morfeus", "xtb", "local_llm", "mock_llm"}.issubset(
        validated
    )
    assert validated["rdkit"].risk_class == AdapterRiskClass.OPTIONAL_LOCAL
    assert isinstance(validated["rdkit"].availability.backend_available, bool)
    if not validated["rdkit"].availability.backend_available:
        assert validated["rdkit"].availability.unavailable_reason
