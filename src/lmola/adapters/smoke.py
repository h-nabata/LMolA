from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from importlib import metadata
import importlib.util
import shutil
from typing import Literal

from pydantic import BaseModel, Field

from lmola.adapters.contracts import AdapterRiskClass, SmokeExecutionSupport
from lmola.backends.capabilities import _xtb_version
from lmola.tools.molsimplify_tool import detect_molsimplify_cli
from lmola.tools.openbabel_tool import detect_openbabel_cli, get_openbabel_version


SmokeStatus = Literal["available", "unavailable", "error"]


class OptionalSmokeResult(BaseModel):
    backend_id: str
    display_name: str
    status: SmokeStatus
    risk_class: AdapterRiskClass
    importable: bool | None = None
    executable: str | None = None
    version: str | None = None
    unavailable_reason: str | None = None
    smoke_execution: SmokeExecutionSupport
    checks: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class OptionalSmokeSpec:
    backend_id: str
    display_name: str
    risk_class: AdapterRiskClass
    python_modules: tuple[str, ...] = ()
    executables: tuple[str, ...] = ()
    version_packages: tuple[str, ...] = ()
    optional_extra: str | None = None
    executable_probe: Callable[[], str | None] | None = None
    cli_version_probe: Callable[[str | None], str | None] | None = None
    checks: tuple[str, ...] = field(default_factory=tuple)


_OPTIONAL_SMOKE_SPECS: dict[str, OptionalSmokeSpec] = {
    "ase": OptionalSmokeSpec(
        backend_id="ase",
        display_name="Atomic Simulation Environment",
        risk_class=AdapterRiskClass.OPTIONAL_LOCAL,
        python_modules=("ase",),
        version_packages=("ase",),
        checks=("import", "version"),
    ),
    "rdkit": OptionalSmokeSpec(
        backend_id="rdkit",
        display_name="RDKit",
        risk_class=AdapterRiskClass.OPTIONAL_LOCAL,
        python_modules=("rdkit",),
        version_packages=("rdkit",),
        optional_extra="rdkit",
        checks=("import", "version"),
    ),
    "openbabel": OptionalSmokeSpec(
        backend_id="openbabel",
        display_name="Open Babel",
        risk_class=AdapterRiskClass.EXTERNAL_EXECUTION,
        python_modules=("openbabel", "openbabel.pybel"),
        executables=("obabel", "babel"),
        version_packages=("openbabel",),
        optional_extra="openbabel",
        executable_probe=detect_openbabel_cli,
        cli_version_probe=get_openbabel_version,
        checks=("import", "executable_discovery", "version"),
    ),
    "xtb": OptionalSmokeSpec(
        backend_id="xtb",
        display_name="xTB",
        risk_class=AdapterRiskClass.EXTERNAL_EXECUTION,
        python_modules=("xtb",),
        executables=("xtb",),
        version_packages=("xtb",),
        cli_version_probe=_xtb_version,
        checks=("import", "executable_discovery", "version"),
    ),
    "molsimplify": OptionalSmokeSpec(
        backend_id="molsimplify",
        display_name="molSimplify",
        risk_class=AdapterRiskClass.EXTERNAL_EXECUTION,
        python_modules=("molSimplify",),
        executables=("molsimplify", "molSimplify"),
        version_packages=("molSimplify", "molsimplify"),
        optional_extra="molsimplify",
        executable_probe=detect_molsimplify_cli,
        checks=("import", "executable_discovery", "version"),
    ),
    "morfeus": OptionalSmokeSpec(
        backend_id="morfeus",
        display_name="Morfeus",
        risk_class=AdapterRiskClass.OPTIONAL_LOCAL,
        python_modules=("morfeus",),
        version_packages=("morfeus",),
        checks=("import", "version"),
    ),
}


def list_optional_smoke_specs() -> dict[str, OptionalSmokeSpec]:
    return dict(sorted(_OPTIONAL_SMOKE_SPECS.items()))


def _module_importable(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except ModuleNotFoundError:
        return False


def _first_importable(modules: tuple[str, ...]) -> bool | None:
    if not modules:
        return None
    return any(_module_importable(module) for module in modules)


def _first_executable(spec: OptionalSmokeSpec) -> str | None:
    if spec.executable_probe:
        return spec.executable_probe()
    for executable in spec.executables:
        path = shutil.which(executable)
        if path:
            return path
    return None


def _metadata_version(packages: tuple[str, ...]) -> str | None:
    for package in packages:
        try:
            return metadata.version(package)
        except metadata.PackageNotFoundError:
            continue
    return None


def _unavailable_reason(spec: OptionalSmokeSpec, importable: bool | None, executable: str | None) -> str:
    missing: list[str] = []
    if spec.python_modules and not importable:
        missing.append(f"python modules: {', '.join(spec.python_modules)}")
    if spec.executables and not executable:
        missing.append(f"executables: {', '.join(spec.executables)}")
    if not missing:
        missing.append("optional backend probe did not report availability")
    if spec.optional_extra:
        missing.append(f"optional extra: {spec.optional_extra}")
    return "; ".join(missing)


def run_optional_smoke_check(backend_id: str) -> OptionalSmokeResult:
    spec = _OPTIONAL_SMOKE_SPECS[backend_id]
    checks = list(spec.checks)
    importable = _first_importable(spec.python_modules)
    executable = _first_executable(spec)
    available = bool(importable or executable)
    version = _metadata_version(spec.version_packages)
    if version is None and spec.cli_version_probe and executable:
        version = spec.cli_version_probe(executable)
    if not available:
        return OptionalSmokeResult(
            backend_id=spec.backend_id,
            display_name=spec.display_name,
            status="unavailable",
            risk_class=spec.risk_class,
            importable=importable,
            executable=executable,
            version=version,
            unavailable_reason=_unavailable_reason(spec, importable, executable),
            smoke_execution=SmokeExecutionSupport.SKIPPED_UNAVAILABLE,
            checks=checks,
        )
    return OptionalSmokeResult(
        backend_id=spec.backend_id,
        display_name=spec.display_name,
        status="available",
        risk_class=spec.risk_class,
        importable=importable,
        executable=executable,
        version=version,
        smoke_execution=SmokeExecutionSupport.SUPPORTED,
        checks=checks,
    )


def list_optional_smoke_results() -> dict[str, OptionalSmokeResult]:
    return {
        backend_id: run_optional_smoke_check(backend_id)
        for backend_id in sorted(_OPTIONAL_SMOKE_SPECS)
    }
