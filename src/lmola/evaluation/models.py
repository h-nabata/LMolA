"""Provisional, versioned models for unified evaluation results."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, Field, field_validator

EVALUATION_RESULT_SCHEMA_VERSION = "lmola.evaluation_result.v1"


class ArtifactReference(BaseModel):
    path: str
    artifact_type: Literal["evaluation_report", "evaluation_config", "suite_result", "case_evidence"]

    @field_validator("path")
    @classmethod
    def relative_path_only(cls, value: str) -> str:
        path = PurePosixPath(value)
        if Path(value).is_absolute() or path.is_absolute() or ".." in path.parts:
            raise ValueError("evaluation artifact paths must be relative to the run root")
        return value


class CaseResult(BaseModel):
    suite_id: str
    case_id: str
    repeat_index: int = Field(ge=1)
    status: Literal["pass", "fail", "skipped"]
    latency_seconds: float = Field(ge=0)
    evidence: dict[str, bool | int | float | str | None] = Field(default_factory=dict)
    artifacts: list[ArtifactReference] = Field(default_factory=list)


class SuiteResult(BaseModel):
    suite_id: str
    status: Literal["pass", "fail", "skipped"]
    cases: list[CaseResult]
    total: int
    passed: int
    failed: int
    skipped: int


class ProfileResult(BaseModel):
    profile_id: str
    suite_ids: list[str]
    status: Literal["pass", "fail", "incomplete"]


class UtilityMetric(BaseModel):
    metric_id: str
    numerator: float | None
    denominator: float | None
    value: float | None
    applicability: Literal["applicable", "not_applicable"]
    evidence_suite_ids: list[str]


class HardGateResult(BaseModel):
    gate_id: str
    status: Literal["pass", "fail", "not_applicable"]
    required: bool
    evaluated_case_count: int
    violation_count: int
    violation_rate: float | None
    evidence_suite_ids: list[str]
    evidence_case_ids: list[str]
    message: str


class EvaluationProvenance(BaseModel):
    lmola_version: str
    git_commit: str | None
    python_version: str
    evaluation_registry_version: str
    planner_schema_version: str
    workflow_schema_version: str
    adapter_schema_version: str
    artifact_schema_version: str
    interface_status: Literal["provisional"] = "provisional"


class EvaluationRunResult(BaseModel):
    schema_version: Literal["lmola.evaluation_result.v1"] = EVALUATION_RESULT_SCHEMA_VERSION
    run_id: str
    profile_id: str
    profile: ProfileResult
    status: Literal["pass", "fail", "incomplete"]
    started_at: datetime
    completed_at: datetime
    backend: str
    model: str | None = None
    repeat: int = Field(ge=1)
    suite_count: int
    total: int
    passed: int
    failed: int
    skipped: int
    suite_results: list[SuiteResult]
    hard_gate_results: list[HardGateResult]
    utility_metrics: list[UtilityMetric]
    provenance: EvaluationProvenance
    artifacts: list[ArtifactReference]
