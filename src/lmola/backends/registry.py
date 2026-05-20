from __future__ import annotations

from dataclasses import dataclass

from lmola.backends.capabilities import list_backend_capabilities, resolve_backend_capability


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


BackendCapability = BackendStatus


def _to_status(backend_id: str) -> BackendStatus | None:
    cap = resolve_backend_capability(backend_id)
    if not cap:
        return None
    importable = None if not cap.python_modules else (cap.status == "available" and any(cap.python_modules))
    executable = next((v for v in cap.executable_paths.values() if v), None) if cap.executable_paths else None
    return BackendStatus(name=cap.backend_id, category=cap.category, available=cap.status == "available", importable=importable, executable=executable, version=cap.version, notes=cap.notes or "", optional_extra=cap.optional_extra)


def list_backend_statuses() -> dict[str, BackendStatus]:
    return {k: _to_status(k) for k in list_backend_capabilities()}


def get_backend_status(name: str) -> BackendStatus | None:
    return _to_status(name)


def _parse_xtb_version(output: str) -> str | None:
    from lmola.backends.capabilities import _parse_xtb_version as _inner
    return _inner(output)
