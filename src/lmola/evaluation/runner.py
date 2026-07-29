"""Offline unified evaluation runner and aggregation."""

from __future__ import annotations

import json
import inspect
import platform
import re
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
    ModelRunMetadata,
)
from .registry import EvaluationInvocationContext, REGISTRY_VERSION, SuiteDefinition, get_profile, list_suites
from lmola.config import LLMConfig
from lmola.tools.llm_client import BaseLLMClient, make_llm_client
from .preflight import endpoint_scope, preflight_local_llm

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
    "native_parse_rate", "native_schema_valid_rate", "native_workflow_selection_rate",
    "final_validated_selection_rate", "repair_attempt_rate", "repair_success_rate",
    "fallback_rate", "hallucinated_workflow_rate", "endpoint_error_rate",
    "model_case_latency_seconds", "prompt_tokens_total", "completion_tokens_total", "total_tokens",
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


def _sanitize_model_response(value: str) -> str:
    value = re.sub(r"https?://[^\s\"']+", "<redacted-local-endpoint>", value)
    value = re.sub(r"(?i)(authorization|api[_-]?key|token)\s*[:=]\s*[^,}\s]+", r"\1:<redacted>", value)
    return value


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
    suite_defs = {s.suite_id: s for s in list_suites(include_real=True)}
    for metric_id in (
        "schema_parse_rate", "workflow_selection_rate", "parameter_binding_rate", "clarification_rate",
        "unsupported_handling_rate", "backend_unavailable_handling_rate", "multi_step_completion_rate",
    ):
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
    real_keys = {
        "native_parse_rate": "native_parse_success", "native_schema_valid_rate": "native_schema_valid",
        "native_workflow_selection_rate": "native_selection_correct",
        "final_validated_selection_rate": "final_selection_correct", "repair_attempt_rate": "repair_attempted",
        "repair_success_rate": "repair_successful", "fallback_rate": "fallback_used",
        "hallucinated_workflow_rate": "hallucinated_workflow_id", "endpoint_error_rate": "endpoint_error",
    }
    model_cases = [c for c in cases if "native_parse_success" in c.evidence]
    for metric_id, key in real_keys.items():
        numerator = sum(bool(c.evidence.get(key)) for c in model_cases)
        denominator = len(model_cases)
        metrics.append(UtilityMetric(metric_id=metric_id, numerator=numerator if denominator else None,
            denominator=denominator or None, value=numerator / denominator if denominator else None,
            applicability="applicable" if denominator else "not_applicable",
            evidence_suite_ids=sorted({c.suite_id for c in model_cases})))
    latencies = [c.evidence.get("model_latency_seconds") for c in model_cases if c.evidence.get("model_latency_seconds") is not None]
    metrics.append(UtilityMetric(metric_id="model_case_latency_seconds", numerator=sum(latencies) if latencies else None,
        denominator=len(latencies) or None, value=sum(latencies) / len(latencies) if latencies else None,
        applicability="applicable" if latencies else "not_applicable", evidence_suite_ids=sorted({c.suite_id for c in model_cases})))
    for metric_id, key in (("prompt_tokens_total", "prompt_tokens"), ("completion_tokens_total", "completion_tokens"), ("total_tokens", "total_tokens")):
        values = [c.evidence[key] for c in model_cases if c.evidence.get(key) is not None]
        metrics.append(UtilityMetric(metric_id=metric_id, numerator=sum(values) if values else None,
            denominator=len(values) or None, value=sum(values) if values else None,
            applicability="applicable" if values else "not_applicable", evidence_suite_ids=sorted({c.suite_id for c in model_cases if c.evidence.get(key) is not None})))
    return metrics


def run_evaluation(*, profile_id: str = "safety-core", backend: str = "mock", model: str | None = None,
                   repeat: int = 1, output_root: str | Path = "outputs/evaluations",
                   suites: list[SuiteDefinition] | None = None, base_url: str | None = None,
                   temperature: float = 0.0, timeout_seconds: int = 180, max_tokens: int | None = 2048,
                   save_raw: bool = False, llm_client: BaseLLMClient | None = None,
                   skip_preflight: bool = False) -> EvaluationRunResult:
    real = profile_id == "real-llm-core"
    if profile_id == "safety-core" and backend != "mock":
        raise ValueError("Phase 18.2 local-model support uses --profile real-llm-core; safety-core is offline")
    if real and backend not in {"ollama", "openai_compatible_local"}:
        raise ValueError("real-llm-core requires ollama or openai_compatible_local")
    if repeat < 1:
        raise ValueError("repeat must be at least 1")
    started = datetime.now(UTC)
    run_id = f"eval_{started.strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}"
    run_root = Path(output_root) / run_id
    run_root.mkdir(parents=True)
    (run_root / "suite_results").mkdir()
    (run_root / "cases").mkdir()
    scope = None
    if real:
        cfg = LLMConfig(enabled=True, backend=backend, model=model, base_url=base_url,
            temperature=temperature, timeout_seconds=timeout_seconds, max_tokens=max_tokens)
        scope = endpoint_scope(base_url or "")
        if llm_client is None and not skip_preflight:
            preflight_local_llm(cfg)
        llm_client = llm_client or make_llm_client(cfg)
    context = EvaluationInvocationContext(backend=backend, model=model, endpoint_scope=scope,
        temperature=temperature, timeout_seconds=timeout_seconds, max_tokens=max_tokens, repeat=repeat,
        save_raw=save_raw, run_root=run_root, base_url=base_url, llm_client=llm_client)
    selected = suites or [s for s in list_suites(include_real=True) if s.suite_id in get_profile(profile_id).suite_ids]
    raw_runs: list[tuple[str, int, dict]] = []
    suite_results = []
    all_cases = []
    for suite in sorted(selected, key=lambda item: item.suite_id):
        normalized_cases = []
        for repeat_index in range(1, repeat + 1):
            before = perf_counter()
            accepts_context = bool(inspect.signature(suite.evaluator).parameters)
            raw = suite.evaluator(context) if accepts_context else suite.evaluator()
            elapsed = perf_counter() - before
            raw_runs.append((suite.suite_id, repeat_index, raw))
            raw_cases = _cases(raw)
            each_latency = elapsed / max(len(raw_cases), 1)
            for position, item in enumerate(raw_cases or [{"case_id": "suite"}], 1):
                case_id = str(item.get("case_id", f"case_{position}"))
                evidence = {k: v for k, v in item.items() if k not in {"raw_response", "client_error"}}
                case = CaseResult(suite_id=suite.suite_id, case_id=case_id, repeat_index=repeat_index,
                    status="pass" if _passed(item) else "fail", latency_seconds=each_latency,
                    evidence=evidence or {"legacy_status": str(item.get("status", raw.get("status", "unknown")))})
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
                if item.get("raw_response"):
                    repeat_dir = case_dir / case_id / f"repeat-{repeat_index}"
                    repeat_dir.mkdir(parents=True, exist_ok=True)
                    sanitized = repeat_dir / "sanitized_response.txt"
                    sanitized.write_text(_sanitize_model_response(str(item["raw_response"])), encoding="utf-8")
                    if save_raw:
                        (repeat_dir / "raw_response.txt").write_text(str(item["raw_response"]), encoding="utf-8")
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
    if real:
        result.model_run = ModelRunMetadata(backend=backend, model=model or "", endpoint_scope=scope,
            temperature=temperature, timeout_seconds=timeout_seconds, max_tokens=max_tokens,
            usage_available=any(m.metric_id == "total_tokens" and m.applicability == "applicable" for m in result.utility_metrics))
    config = {"schema_version": REGISTRY_VERSION, "profile_id": profile_id, "backend": backend, "model": model,
              "endpoint_scope": scope, "temperature": temperature, "timeout_seconds": timeout_seconds,
              "max_tokens": max_tokens, "repeat": repeat, "save_raw": save_raw}
    (run_root / "evaluation_config.json").write_text(json.dumps(config, indent=2, sort_keys=True) + "\n")
    (run_root / "evaluation_result.json").write_text(json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True) + "\n")
    return result


def validate_result(path: str | Path) -> EvaluationRunResult:
    return EvaluationRunResult.model_validate_json(Path(path).read_text(encoding="utf-8"))
