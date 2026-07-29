"""Offline unified evaluation runner and aggregation."""

from __future__ import annotations

import json
import platform
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from lmola import __version__
from lmola.adapters.contracts import ADAPTER_CONTRACT_SCHEMA_VERSION
from lmola.artifact_contracts import ARTIFACT_CONTRACT_SCHEMA_VERSION
from lmola.artifact_manifest import ARTIFACT_MANIFEST_SCHEMA_VERSION

from .models import (
    ArtifactReference,
    CaseResult,
    EvaluationProvenance,
    EvaluationRunResult,
    HardGateResult,
    ProfileResult,
    SuiteResult,
    UtilityMetric,
)
from .registry import REGISTRY_VERSION, SuiteDefinition, get_profile, list_suites

GATE_IDS = (
    "unsafe_execution_attempt_rate",
    "result_artifact_as_geometry_error_rate",
    "low_level_tool_exposure_rate",
    "backend_constraint_violation_rate",
    "forced_selection_on_ambiguous_prompt_rate",
)
METRIC_IDS = (
    "schema_parse_rate",
    "workflow_selection_rate",
    "parameter_binding_rate",
    "clarification_rate",
    "unsupported_handling_rate",
    "backend_unavailable_handling_rate",
    "multi_step_completion_rate",
    "cross_run_consistency",
    "mean_case_latency_seconds",
)
RATE_KEYS = {
    "schema_parse_rate": ("catalog_parse_pass_rate", "normalization_pass_rate", "pass_rate"),
    "workflow_selection_rate": ("selection_pass_rate", "initial_selection_pass_rate", "pass_rate"),
    "parameter_binding_rate": ("binding_pass_rate", "parameter_binding_pass_rate", "pass_rate"),
    "clarification_rate": ("clarification_pass_rate", "required_question_pass_rate", "pass_rate"),
    "unsupported_handling_rate": ("unsupported_handling_pass_rate", "pass_rate"),
    "backend_unavailable_handling_rate": ("backend_unavailable_handling_pass_rate", "smoke_consistency_pass_rate"),
    "multi_step_completion_rate": ("second_step_decision_pass_rate", "pass_rate"),
}


def _git_commit() -> str | None:
    try:
        value = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
        ).stdout.strip()
        return value if len(value) == 40 else None
    except OSError:
        return None


def _cases(raw: dict) -> list[dict]:
    return raw.get("cases") or raw.get("case_results") or []


def _passed(case: dict) -> bool:
    if "passed" in case:
        return bool(case["passed"])
    return case.get("failure_category", "none") == "none" and case.get("status") != "fail"


def _gate_rate(raw: dict, gate_id: str) -> float | None:
    aliases = {
        "unsafe_execution_attempt_rate": ("unsafe_execution_attempt_rate", "unsafe_next_execution_attempt_rate"),
        "result_artifact_as_geometry_error_rate": ("result_artifact_as_geometry_error_rate",),
        "low_level_tool_exposure_rate": ("low_level_tool_exposure_rate",),
        "backend_constraint_violation_rate": ("backend_constraint_violation_rate",),
        "forced_selection_on_ambiguous_prompt_rate": ("forced_selection_on_ambiguous_prompt_rate",),
    }
    for key in aliases[gate_id]:
        if key in raw:
            return float(raw[key])
    return None


def aggregate_gates(raw_runs: list[tuple[str, int, dict]]) -> list[HardGateResult]:
    results = []
    for gate_id in GATE_IDS:
        evidence = [(suite, repeat, raw, _gate_rate(raw, gate_id)) for suite, repeat, raw in raw_runs]
        evidence = [item for item in evidence if item[3] is not None]
        evaluated = sum(len(_cases(raw)) or int(raw.get("total_cases", 0)) for _, _, raw, _ in evidence)
        violating_cases = []
        for suite, repeat, raw, rate in evidence:
            if rate and rate > 0:
                violating_cases.extend(f"{suite}:{c.get('case_id', 'suite')}#r{repeat}" for c in _cases(raw))
        violations = len(violating_cases) if violating_cases else int(any(rate and rate > 0 for *_, rate in evidence))
        missing = evaluated == 0
        status = "fail" if missing or violations else "pass"
        results.append(HardGateResult(
            gate_id=gate_id, status=status, required=True, evaluated_case_count=evaluated,
            violation_count=violations, violation_rate=(violations / evaluated if evaluated else None),
            evidence_suite_ids=sorted({suite for suite, *_ in evidence}),
            evidence_case_ids=sorted(violating_cases),
            message="Required gate has no evidence; failed closed." if missing else ("One or more violations detected." if violations else "No violations detected."),
        ))
    return results


def _metrics(raw_runs: list[tuple[str, int, dict]], cases: list[CaseResult]) -> list[UtilityMetric]:
    metrics = []
    suite_defs = {s.suite_id: s for s in list_suites()}
    for metric_id in METRIC_IDS[:-2]:
        evidence = []
        values = []
        for suite_id, _, raw in raw_runs:
            suite_definition = suite_defs.get(suite_id)
            if suite_definition is None or metric_id not in suite_definition.metric_ids:
                continue
            for key in RATE_KEYS[metric_id]:
                if key in raw:
                    denom = float(raw.get("total_cases", len(_cases(raw))))
                    values.append((float(raw[key]) * denom, denom))
                    evidence.append(suite_id)
                    break
        numerator = sum(n for n, _ in values) if values else None
        denominator = sum(d for _, d in values) if values else None
        metrics.append(UtilityMetric(metric_id=metric_id, numerator=numerator, denominator=denominator,
            value=(numerator / denominator if denominator else None), applicability="applicable" if denominator else "not_applicable",
            evidence_suite_ids=sorted(set(evidence))))
    grouped: dict[tuple[str, str], list[str]] = {}
    for case in cases:
        grouped.setdefault((case.suite_id, case.case_id), []).append(case.status)
    stable = sum(1 for statuses in grouped.values() if len(set(statuses)) == 1)
    metrics.append(UtilityMetric(metric_id="cross_run_consistency", numerator=stable, denominator=len(grouped),
        value=stable / len(grouped) if grouped else None, applicability="applicable" if grouped else "not_applicable",
        evidence_suite_ids=sorted({case.suite_id for case in cases})))
    latency = sum(case.latency_seconds for case in cases)
    metrics.append(UtilityMetric(metric_id="mean_case_latency_seconds", numerator=latency, denominator=len(cases),
        value=latency / len(cases) if cases else None, applicability="applicable" if cases else "not_applicable",
        evidence_suite_ids=sorted({case.suite_id for case in cases})))
    return metrics


def run_evaluation(*, profile_id: str = "safety-core", backend: str = "mock", model: str | None = None,
                   repeat: int = 1, output_root: str | Path = "outputs/evaluations",
                   suites: list[SuiteDefinition] | None = None) -> EvaluationRunResult:
    if backend != "mock":
        raise ValueError("Real Ollama and OpenAI-compatible evaluation is deferred to Phase 18.2")
    if repeat < 1:
        raise ValueError("repeat must be at least 1")
    started = datetime.now(UTC)
    run_id = f"eval_{started.strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}"
    run_root = Path(output_root) / run_id
    run_root.mkdir(parents=True)
    (run_root / "suite_results").mkdir()
    (run_root / "cases").mkdir()
    selected = suites or [s for s in list_suites() if s.suite_id in get_profile(profile_id).suite_ids]
    raw_runs: list[tuple[str, int, dict]] = []
    suite_results = []
    all_cases = []
    for suite in sorted(selected, key=lambda item: item.suite_id):
        normalized_cases = []
        for repeat_index in range(1, repeat + 1):
            before = perf_counter()
            raw = suite.evaluator()
            elapsed = perf_counter() - before
            raw_runs.append((suite.suite_id, repeat_index, raw))
            raw_cases = _cases(raw)
            each_latency = elapsed / max(len(raw_cases), 1)
            for position, item in enumerate(raw_cases or [{"case_id": "suite"}], 1):
                case_id = str(item.get("case_id", f"case_{position}"))
                case = CaseResult(suite_id=suite.suite_id, case_id=case_id, repeat_index=repeat_index,
                    status="pass" if _passed(item) else "fail", latency_seconds=each_latency,
                    evidence={"legacy_status": str(item.get("status", raw.get("status", "unknown")))})
                normalized_cases.append(case)
                all_cases.append(case)
                case_dir = run_root / "cases" / suite.suite_id
                case_dir.mkdir(parents=True, exist_ok=True)
                evidence_path = case_dir / f"{case_id}.repeat-{repeat_index}.json"
                safe_evidence = {
                    "case_id": case_id,
                    "repeat_index": repeat_index,
                    "status": case.status,
                    "source_suite_id": str(raw.get("suite_id", raw.get("phase", suite.suite_id))),
                }
                evidence_path.write_text(json.dumps(safe_evidence, indent=2, sort_keys=True) + "\n")
                case.artifacts.append(ArtifactReference(path=evidence_path.relative_to(run_root).as_posix(), artifact_type="case_evidence"))
        passed = sum(c.status == "pass" for c in normalized_cases)
        failed = sum(c.status == "fail" for c in normalized_cases)
        result = SuiteResult(suite_id=suite.suite_id, status="pass" if not failed else "fail", cases=normalized_cases,
            total=len(normalized_cases), passed=passed, failed=failed, skipped=0)
        suite_results.append(result)
        (run_root / "suite_results" / f"{suite.suite_id}.json").write_text(
            json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True) + "\n")
    gates = aggregate_gates(raw_runs)
    failed = sum(c.status == "fail" for c in all_cases)
    status = "fail" if failed or any(g.required and g.status != "pass" for g in gates) else "pass"
    completed = datetime.now(UTC)
    profile = ProfileResult(profile_id=profile_id, suite_ids=[s.suite_id for s in sorted(selected, key=lambda x: x.suite_id)], status=status)
    result = EvaluationRunResult(run_id=run_id, profile_id=profile_id, profile=profile, status=status,
        started_at=started, completed_at=completed, backend=backend, model=model, repeat=repeat,
        suite_count=len(suite_results), total=len(all_cases), passed=len(all_cases)-failed, failed=failed, skipped=0,
        suite_results=suite_results, hard_gate_results=gates, utility_metrics=_metrics(raw_runs, all_cases),
        provenance=EvaluationProvenance(lmola_version=__version__, git_commit=_git_commit(), python_version=platform.python_version(),
            evaluation_registry_version=REGISTRY_VERSION, planner_schema_version="lmola.models.v1",
            workflow_schema_version="lmola.workflow_request.v1", adapter_schema_version=ADAPTER_CONTRACT_SCHEMA_VERSION,
            artifact_schema_version=f"{ARTIFACT_CONTRACT_SCHEMA_VERSION};{ARTIFACT_MANIFEST_SCHEMA_VERSION}"),
        artifacts=[ArtifactReference(path="evaluation_result.json", artifact_type="evaluation_report"),
                   ArtifactReference(path="evaluation_config.json", artifact_type="evaluation_config")])
    config = {"schema_version": REGISTRY_VERSION, "profile_id": profile_id, "backend": backend, "model": model, "repeat": repeat}
    (run_root / "evaluation_config.json").write_text(json.dumps(config, indent=2, sort_keys=True) + "\n")
    (run_root / "evaluation_result.json").write_text(json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True) + "\n")
    return result


def validate_result(path: str | Path) -> EvaluationRunResult:
    return EvaluationRunResult.model_validate_json(Path(path).read_text(encoding="utf-8"))
