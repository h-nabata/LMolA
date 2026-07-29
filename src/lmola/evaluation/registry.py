"""Deterministic suite and profile registry."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field

REGISTRY_VERSION = "lmola.evaluation_registry.v1"


class EvaluationInvocationContext(BaseModel):
    """Provisional invocation boundary; secrets and the URL are never serialized."""
    model_config = ConfigDict(arbitrary_types_allowed=True)
    backend: str = "mock"
    model: str | None = None
    endpoint_scope: Literal["loopback", "private_network"] | None = None
    temperature: float = 0.0
    timeout_seconds: int = Field(default=180, gt=0)
    max_tokens: int | None = Field(default=2048, gt=0)
    repeat: int = Field(default=1, ge=1)
    save_raw: bool = False
    run_root: Path | None = Field(default=None, exclude=True)
    base_url: str | None = Field(default=None, exclude=True, repr=False)
    llm_client: Any = Field(default=None, exclude=True, repr=False)


@dataclass(frozen=True)
class SuiteDefinition:
    suite_id: str
    description: str
    evaluator: Callable[..., dict]
    metric_ids: tuple[str, ...]
    gate_ids: tuple[str, ...]
    classification: Literal["model_involved", "deterministic_guard", "registry_or_contract_check"] = "deterministic_guard"
    supported_backends: tuple[str, ...] = ("mock",)


@dataclass(frozen=True)
class ProfileDefinition:
    profile_id: str
    description: str
    suite_ids: tuple[str, ...]


def _suites() -> dict[str, SuiteDefinition]:
    from lmola.evaluation.adapters import SUITE_DEFINITIONS

    return {suite.suite_id: suite for suite in SUITE_DEFINITIONS}


def list_suites(*, include_real: bool = False) -> list[SuiteDefinition]:
    suites = _suites().values()
    if not include_real:
        suites = (suite for suite in suites if "mock" in suite.supported_backends)
    return sorted(suites, key=lambda item: item.suite_id)


def list_profiles(*, include_real: bool = False) -> list[ProfileDefinition]:
    suites = list_suites(include_real=True)
    profiles = [
        ProfileDefinition("safety-core", "Offline mock safety baseline", tuple(s.suite_id for s in suites if "mock" in s.supported_backends)),
        ProfileDefinition("real-llm-core", "Local-model quality and deterministic containment baseline",
            tuple(s.suite_id for s in suites if s.suite_id in {"real_planner", "real_execution_gate", "real_multi_step_orchestration", "phase17_adapter_artifact_safety", "mcp_runtime_tool_exposure"})),
    ]
    return profiles if include_real else profiles[:1]


def get_profile(profile_id: str) -> ProfileDefinition:
    for profile in list_profiles(include_real=True):
        if profile.profile_id == profile_id:
            return profile
    raise KeyError(f"unknown evaluation profile: {profile_id}")


def validate_registry() -> list[str]:
    errors: list[str] = []
    suites = list_suites(include_real=True)
    if len({s.suite_id for s in suites}) != len(suites):
        errors.append("duplicate suite IDs")
    known = {s.suite_id for s in suites}
    for profile in list_profiles(include_real=True):
        missing = set(profile.suite_ids) - known
        if missing:
            errors.append(f"{profile.profile_id}: unknown suites {sorted(missing)}")
    return errors
