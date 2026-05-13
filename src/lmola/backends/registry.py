from __future__ import annotations

from dataclasses import dataclass
import importlib.util
from importlib import metadata
import shutil
import subprocess


@dataclass(frozen=True)
class BackendCapability:
    name: str
    category: str
    module_name: str | None = None
    executable: str | None = None
    optional_extra: str | None = None
    notes: str = ""


@dataclass(frozen=True)
class BackendStatus:
    name: str
    category: str
    available: bool
    importable: bool | None
    executable: str | None
    version: str | None
    notes: str
    optional_extra: str | None


_BACKENDS: tuple[BackendCapability, ...] = (
    BackendCapability("ase", "validation", module_name="ase", notes="Core parser/validation dependency."),
    BackendCapability("rdkit", "structure_generation", module_name="rdkit", optional_extra="rdkit"),
    BackendCapability("openbabel", "conversion", module_name="openbabel", optional_extra="openbabel"),
    BackendCapability("molsimplify", "structure_generation", module_name="molSimplify", executable="molsimplify", optional_extra="molsimplify"),
    BackendCapability("xtb", "relaxation", module_name="xtb", executable="xtb", notes="Python module optional; xtb CLI is primary."),
    BackendCapability("local_llm", "llm", notes="Configured via LMOLA_LLM_* or .lmola/config.yaml (ollama/openai_compatible_local)."),
    BackendCapability("mock_llm", "llm", notes="Always available for tests and offline fallback."),
)


def _importable(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def _version_for_module(module_name: str) -> str | None:
    try:
        return metadata.version(module_name)
    except metadata.PackageNotFoundError:
        return None


def _xtb_version(executable: str | None) -> str | None:
    if not executable:
        return None
    try:
        completed = subprocess.run([executable, "--version"], capture_output=True, text=True, check=False)
    except Exception:
        return None
    line = (completed.stdout or completed.stderr).strip().splitlines()
    return line[0].strip() if line else None


def _status(cap: BackendCapability) -> BackendStatus:
    importable = _importable(cap.module_name) if cap.module_name else None
    executable = shutil.which(cap.executable) if cap.executable else None
    version = None

    if cap.name == "xtb":
        version = _xtb_version(executable)
    elif cap.module_name and importable:
        version = _version_for_module(cap.module_name)

    if cap.name == "local_llm":
        available = True
    elif cap.name == "mock_llm":
        available = True
    else:
        available = bool(importable) or bool(executable)

    return BackendStatus(
        name=cap.name,
        category=cap.category,
        available=available,
        importable=importable,
        executable=executable,
        version=version,
        notes=cap.notes,
        optional_extra=cap.optional_extra,
    )


def list_backend_statuses() -> dict[str, BackendStatus]:
    return {cap.name: _status(cap) for cap in _BACKENDS}


def get_backend_status(name: str) -> BackendStatus | None:
    for cap in _BACKENDS:
        if cap.name == name:
            return _status(cap)
    return None
