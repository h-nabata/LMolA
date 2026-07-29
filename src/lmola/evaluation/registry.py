"""Deterministic suite and profile registry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

REGISTRY_VERSION = "lmola.evaluation_registry.v1"


@dataclass(frozen=True)
class SuiteDefinition:
    suite_id: str
    description: str
    evaluator: Callable[[], dict]
    metric_ids: tuple[str, ...]
    gate_ids: tuple[str, ...]


@dataclass(frozen=True)
class ProfileDefinition:
    profile_id: str
    description: str
    suite_ids: tuple[str, ...]


def _suites() -> dict[str, SuiteDefinition]:
    from lmola.evaluation.adapters import SUITE_DEFINITIONS

    return {suite.suite_id: suite for suite in SUITE_DEFINITIONS}


def list_suites() -> list[SuiteDefinition]:
    return sorted(_suites().values(), key=lambda item: item.suite_id)


def list_profiles() -> list[ProfileDefinition]:
    return [ProfileDefinition("safety-core", "Offline mock safety baseline", tuple(s.suite_id for s in list_suites()))]


def get_profile(profile_id: str) -> ProfileDefinition:
    for profile in list_profiles():
        if profile.profile_id == profile_id:
            return profile
    raise KeyError(f"unknown evaluation profile: {profile_id}")


def validate_registry() -> list[str]:
    errors: list[str] = []
    suites = list_suites()
    if len({s.suite_id for s in suites}) != len(suites):
        errors.append("duplicate suite IDs")
    known = {s.suite_id for s in suites}
    for profile in list_profiles():
        missing = set(profile.suite_ids) - known
        if missing:
            errors.append(f"{profile.profile_id}: unknown suites {sorted(missing)}")
    return errors
