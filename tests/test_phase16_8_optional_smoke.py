from __future__ import annotations

from dataclasses import replace
import importlib.util

import pytest

from lmola.adapters import (
    AdapterRiskClass,
    SmokeExecutionSupport,
    assert_registered_adapters_conform,
    list_adapter_metadata,
    list_optional_smoke_results,
    list_optional_smoke_specs,
    run_optional_smoke_check,
)
from lmola.adapters import smoke


def test_optional_smoke_specs_include_phase16_8_backends() -> None:
    specs = list_optional_smoke_specs()
    assert {"molsimplify", "morfeus", "rdkit", "openbabel", "xtb", "ase"}.issubset(specs)
    assert specs["molsimplify"].risk_class == AdapterRiskClass.EXTERNAL_EXECUTION
    assert specs["morfeus"].risk_class == AdapterRiskClass.OPTIONAL_LOCAL


def test_unavailable_optional_backend_reports_clear_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(smoke, "_module_importable", lambda module: False)
    monkeypatch.setattr(smoke, "_metadata_version", lambda packages: None)

    result = run_optional_smoke_check("morfeus")

    assert result.status == "unavailable"
    assert result.importable is False
    assert result.unavailable_reason
    assert "python modules: morfeus" in result.unavailable_reason
    assert result.smoke_execution == SmokeExecutionSupport.SKIPPED_UNAVAILABLE


def test_importable_optional_backend_reports_supported_smoke(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(smoke, "_module_importable", lambda module: module == "rdkit")
    monkeypatch.setattr(smoke, "_metadata_version", lambda packages: "2024.09.1")

    result = run_optional_smoke_check("rdkit")

    assert result.status == "available"
    assert result.importable is True
    assert result.version == "2024.09.1"
    assert result.smoke_execution == SmokeExecutionSupport.SUPPORTED
    assert result.unavailable_reason is None


def test_cli_optional_backend_discovers_executable_and_version(monkeypatch: pytest.MonkeyPatch) -> None:
    xtb_spec = list_optional_smoke_specs()["xtb"]
    monkeypatch.setitem(
        smoke._OPTIONAL_SMOKE_SPECS,
        "xtb",
        replace(xtb_spec, cli_version_probe=lambda executable: "6.7.1"),
    )
    monkeypatch.setattr(smoke, "_module_importable", lambda module: False)
    monkeypatch.setattr(smoke, "_metadata_version", lambda packages: None)
    monkeypatch.setattr(smoke.shutil, "which", lambda executable: "/opt/bin/xtb")

    result = run_optional_smoke_check("xtb")

    assert result.status == "available"
    assert result.importable is False
    assert result.executable == "/opt/bin/xtb"
    assert result.version == "6.7.1"
    assert result.smoke_execution == SmokeExecutionSupport.SUPPORTED


def test_list_optional_smoke_results_is_safe_when_tools_are_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(smoke, "_module_importable", lambda module: False)
    monkeypatch.setattr(smoke, "_metadata_version", lambda packages: None)
    monkeypatch.setattr(smoke.shutil, "which", lambda executable: None)
    monkeypatch.setattr(
        smoke,
        "detect_openbabel_cli",
        lambda: None,
    )
    monkeypatch.setattr(
        smoke,
        "detect_molsimplify_cli",
        lambda: None,
    )

    results = list_optional_smoke_results()

    assert results["molsimplify"].status == "unavailable"
    assert results["morfeus"].status == "unavailable"
    assert results["openbabel"].status == "unavailable"
    assert results["molsimplify"].unavailable_reason


def test_adapter_registry_uses_optional_smoke_without_requiring_tools() -> None:
    adapters = list_adapter_metadata()
    validated = assert_registered_adapters_conform(adapters)

    assert "morfeus" in validated
    assert validated["morfeus"].risk_class == AdapterRiskClass.OPTIONAL_LOCAL
    assert isinstance(validated["morfeus"].availability.backend_available, bool)
    if not validated["morfeus"].availability.backend_available:
        assert validated["morfeus"].availability.unavailable_reason
        assert validated["morfeus"].availability.smoke_execution == (
            SmokeExecutionSupport.SKIPPED_UNAVAILABLE
        )


@pytest.mark.external_tools
def test_optional_morfeus_real_import_smoke_when_installed() -> None:
    if importlib.util.find_spec("morfeus") is None:
        pytest.skip("morfeus is not installed in this optional external-tools environment")

    result = run_optional_smoke_check("morfeus")

    assert result.status == "available"
    assert result.importable is True
