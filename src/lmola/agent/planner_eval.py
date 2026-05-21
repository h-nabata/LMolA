from __future__ import annotations

import csv
import os
import fnmatch
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
import uuid
import shutil

import yaml
from pydantic import BaseModel, Field

from lmola.agent.workflow_planner import plan_workflow_request
from lmola.backends.capabilities import list_backend_capabilities
from lmola.config import load_app_config
from lmola.io.converters import dump_json
from lmola.io.run_artifacts import collect_environment


class PlannerEvalCase(BaseModel):
    id: str
    request: str
    expected_status: str = "ok"
    expected_workflow_id: str | None = None
    expected_tools: list[str] | None = None
    expected_required_backends: list[str] | None = None
    expected_normalized_status: str | None = None
    notes: str | None = None
    case_type: str | None = None
    difficulty: str | None = None
    expected_failure_modes: list[str] | None = None


class PlannerEvalSuite(BaseModel):
    suite_id: str
    description: str | None = None
    cases: list[PlannerEvalCase] = Field(default_factory=list)


class PlannerEvalRunResult(BaseModel):
    status: str
    message: str
    suite_id: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    pass_rate: float
    eval_dir: str
    summary_csv: str
    summary_json: str
    backend: str
    model: str | None = None
    base_url: str | None = None
    temperature: float | None = None
    timeout_seconds: int | None = None
    max_tokens: int | None = None
    cases: list[dict] = Field(default_factory=list)
    planner_prompt_mode: str | None = None
    planner_context_schema_version: str | None = None
    planner_context_workflow_count: int | None = None
    planner_context_allowed_workflow_ids: list[str] = Field(default_factory=list)


def _classify_failure(row: dict) -> str:
    if row.get("passed"):
        return "none"
    if str(row.get("actual_status", "")).lower() in {"endpoint_error", "client_error"}:
        return "endpoint_error"
    if not row.get("parse_ok", False):
        return "parse_failure"
    if not row.get("validation_ok", False):
        return "schema_validation_failure"
    if not row.get("canonicalization_ok", False):
        return "canonicalization_failure"
    if row.get("expected_status") == "unsupported" and not row.get("unsupported_handled", False):
        return "unsupported_not_handled"
    if not row.get("workflow_match", True):
        return "wrong_workflow"
    if not row.get("tools_match", True):
        return "tool_mismatch"
    if "endpoint" in str(row.get("error_message", "")).lower() or "connection" in str(row.get("error_message", "")).lower():
        return "endpoint_error"
    if row.get("actual_status") == "error":
        return "unexpected_error"
    return "unknown"


def _create_eval_dir(base: str = "outputs") -> Path:
    eval_id = datetime.now(timezone.utc).strftime("eval_%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:6]
    path = Path(base) / eval_id
    path.mkdir(parents=True, exist_ok=False)
    return path


def load_eval_suite(path: str | Path) -> PlannerEvalSuite:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return PlannerEvalSuite.model_validate(data)


def _canonical_tools_from_result(planning_result: dict) -> list[str] | None:
    canonical = planning_result.get("canonical_workflow_json")
    if not isinstance(canonical, dict):
        return None
    steps = canonical.get("steps") or []
    tools: list[str] = []
    for step in steps:
        if isinstance(step, dict) and isinstance(step.get("tool"), str):
            tools.append(step["tool"])
    return tools


def _normalize_token(text: str) -> str:
    return "".join(ch for ch in text.lower() if ch.isalnum())


def _backend_aliases(backend_id: str, display_name: str) -> set[str]:
    aliases = {_normalize_token(backend_id), _normalize_token(display_name)}
    if backend_id == "molsimplify":
        aliases.update({_normalize_token("mol simplify"), _normalize_token("molSimplify"), _normalize_token("MolSimplify")})
    return aliases


def _infer_unavailable_backend(texts: list[str]) -> str | None:
    caps = list_backend_capabilities()
    normalized_haystack = " ".join(_normalize_token(t) for t in texts if t)
    for backend_id, cap in caps.items():
        if cap.status != "unavailable":
            continue
        if any(alias and alias in normalized_haystack for alias in _backend_aliases(backend_id, cap.display_name)):
            return backend_id
    return None


def run_planner_eval(eval_cases_yaml: str) -> PlannerEvalRunResult:
    cfg = load_app_config()
    suite = load_eval_suite(eval_cases_yaml)
    eval_dir = _create_eval_dir()
    cases_dir = eval_dir / "cases"
    cases_dir.mkdir(parents=True, exist_ok=True)

    (eval_dir / "eval_cases.yaml").write_text(Path(eval_cases_yaml).read_text(encoding="utf-8"), encoding="utf-8")
    dump_json(eval_dir / "environment.json", collect_environment())
    dump_json(eval_dir / "effective_config.json", cfg.model_dump())

    rows: list[dict] = []
    passed = 0

    for case in suite.cases:
        case_dir = cases_dir / case.id
        case_dir.mkdir(parents=True, exist_ok=True)
        (case_dir / "natural_language_request.txt").write_text(case.request, encoding="utf-8")

        started_perf = perf_counter()
        try:
            planning = plan_workflow_request(case.request, write_artifacts=True)
        except Exception as exc:
            elapsed = max(0.0, perf_counter() - started_perf)
            row = {
                "suite_id": suite.suite_id,
                "case_id": case.id,
                "request": case.request,
                "expected_status": case.expected_status,
                "actual_status": "error",
                "normalized_status": "error",
                "expected_workflow_id": case.expected_workflow_id,
                "selected_workflow_id": None,
                "workflow_match": False,
                "expected_tools": case.expected_tools,
                "canonical_tools": None,
                "tools_match": False,
                "parse_ok": None,
                "validation_ok": False,
                "canonicalization_ok": False,
                "unsupported_handled": False,
                "executed": False,
                "plan_dir": None,
                "case_dir": str(case_dir),
                "error_message": str(exc),
                "elapsed_seconds": elapsed,
                "passed": False,
            }
            row["failure_category"] = "unexpected_error"
            rows.append(row)
            dump_json(case_dir / "case_result.json", row)
            continue
        elapsed = max(0.0, perf_counter() - started_perf)

        if planning.plan_dir:
            pdir = Path(planning.plan_dir)
            raw = pdir / "llm_response.raw.txt"
            if raw.exists():
                (case_dir / "llm_response.raw.txt").write_text(raw.read_text(encoding="utf-8"), encoding="utf-8")
            for name in ["planned_workflow.json", "planned_workflow.yaml", "canonical_workflow.json", "canonical_workflow.yaml", "planning_result.json", "planner_context_compact.json", "planner_prompt.txt"]:
                src = pdir / name
                if src.exists():
                    (case_dir / name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

        planning_payload = planning.model_dump()
        dump_json(case_dir / "planning_result.json", planning_payload)
        (case_dir / "raw_llm_response.txt").write_text(planning_payload.get("raw_llm_response") or "", encoding="utf-8")
        sanitized = planning_payload.get("parsed_workflow") or {}
        (case_dir / "sanitized_llm_response.txt").write_text(yaml.safe_dump(sanitized, sort_keys=False), encoding="utf-8")
        dump_json(case_dir / "json_candidates.json", [])
        dump_json(case_dir / "parsed_output.json", planning_payload.get("parsed_workflow") or {})

        parse_ok = planning_payload.get("parsed_workflow") is not None
        validation_ok = planning_payload.get("workflow_json") is not None
        canonicalization_ok = planning_payload.get("canonical_workflow_json") is not None
        selected_workflow_id = planning_payload.get("selected_workflow_id")
        actual_status = "ok" if planning.status == "ok" else "error"
        msg = (planning.message or "").lower()
        if planning.status != "ok" and ("endpoint" in msg or "connection" in msg or "refused" in msg or "timeout" in msg):
            actual_status = "endpoint_error"

        workflow_match = case.expected_workflow_id == selected_workflow_id if case.expected_workflow_id is not None else selected_workflow_id is None
        canonical_tools = _canonical_tools_from_result(planning_payload)
        tools_match = True
        if case.expected_tools is not None:
            tools_match = canonical_tools == case.expected_tools

        parsed_status = (planning_payload.get("parsed_workflow") or {}).get("status")
        unsupported_handled = False
        backend_unavailable_handled = False
        if case.expected_status == "unsupported":
            unsupported_handled = planning.status == "error" and not canonicalization_ok and selected_workflow_id is None
        if parsed_status == "backend_unavailable":
            backend_unavailable_handled = planning.status == "error" and selected_workflow_id is None
        inferred_unavailable = _infer_unavailable_backend([case.request, str((planning_payload.get("parsed_workflow") or {}).get("reason") or ""), planning.message or ""])
        if planning.status != "ok" and inferred_unavailable and parsed_status in {None, "unsupported", "backend_unavailable"}:
            normalized_status = "backend_unavailable"
            backend_unavailable_handled = planning.status == "error" and selected_workflow_id is None
            unsupported_handled = False
        elif parsed_status in {"unsupported", "backend_unavailable"}:
            normalized_status = parsed_status
        elif unsupported_handled:
            normalized_status = "unsupported"
        else:
            normalized_status = actual_status
        expected_normalized_status = case.expected_normalized_status or case.expected_status
        selected_required_backends = (planning_payload.get("canonical_workflow_json") or {}).get("steps")
        selected_required_backends = None
        selected_readiness_ready = None
        selected_missing_backends = None
        if selected_workflow_id:
            from lmola.workflows.catalog import check_workflow_backend_readiness, get_workflow_entry
            selected_required_backends = get_workflow_entry(selected_workflow_id).required_backends
            readiness = check_workflow_backend_readiness(selected_workflow_id)
            selected_readiness_ready = readiness.get("ready")
            selected_missing_backends = readiness.get("missing_backends")
        required_backends_match = True if case.expected_required_backends is None else (selected_required_backends == case.expected_required_backends)
        backend_readiness_ok = selected_readiness_ready is True if normalized_status == "ok" and selected_workflow_id else True
        unavailable_backend_selected = bool(selected_workflow_id and selected_missing_backends)
        hallucinated_workflow_id = bool(selected_workflow_id and selected_workflow_id not in planning_payload.get("planner_context_allowed_workflow_ids", []))
        backend_constraint_violated = bool(normalized_status == "ok" and unavailable_backend_selected)

        if case.expected_status == "ok":
            case_passed = planning.status == "ok" and workflow_match and tools_match
        elif case.expected_status in {"unsupported", "backend_unavailable"}:
            case_passed = normalized_status == case.expected_status
        else:
            case_passed = planning.status == "error"
        if case.expected_normalized_status is not None:
            case_passed = case_passed and normalized_status == case.expected_normalized_status

        if case_passed:
            passed += 1

        row = {
            "suite_id": suite.suite_id,
            "case_id": case.id,
            "request": case.request,
            "expected_status": case.expected_status,
            "actual_status": actual_status,
            "normalized_status": normalized_status,
            "expected_workflow_id": case.expected_workflow_id,
            "selected_workflow_id": selected_workflow_id,
            "workflow_match": workflow_match,
            "expected_tools": case.expected_tools,
            "expected_required_backends": case.expected_required_backends,
            "canonical_tools": canonical_tools,
            "selected_required_backends": selected_required_backends,
            "required_backends_match": required_backends_match,
            "selected_readiness_ready": selected_readiness_ready,
            "selected_missing_backends": selected_missing_backends,
            "backend_readiness_ok": backend_readiness_ok,
            "tools_match": tools_match,
            "parse_ok": parse_ok,
            "validation_ok": validation_ok,
            "canonicalization_ok": canonicalization_ok,
            "unsupported_handled": unsupported_handled,
            "backend_unavailable_handled": backend_unavailable_handled,
            "expected_normalized_status": expected_normalized_status,
            "executed": planning_payload.get("executed", False),
            "plan_dir": planning_payload.get("plan_dir"),
            "case_dir": str(case_dir),
            "error_message": None if planning.status == "ok" else planning.message,
            "elapsed_seconds": elapsed,
            "hallucinated_workflow_id": hallucinated_workflow_id,
            "unavailable_backend_selected": unavailable_backend_selected,
            "backend_constraint_violated": backend_constraint_violated,
            "passed": case_passed,
        }
        row["failure_category"] = _classify_failure(row)
        dump_json(
            case_dir / "normalized_output.json",
            {
                "normalized_status": normalized_status,
                "selected_workflow_id": selected_workflow_id,
                "expected_normalized_status": expected_normalized_status,
            },
        )
        rows.append(row)
        dump_json(case_dir / "case_result.json", row)

    summary_json = eval_dir / "eval_summary.json"
    summary_csv = eval_dir / "eval_summary.csv"
    dump_json(summary_json, rows)
    with summary_csv.open("w", newline="", encoding="utf-8") as fh:
        fieldnames = sorted({k for row in rows for k in row.keys()}) if rows else ["suite_id", "case_id"]
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    total = len(rows)
    failed = total - passed
    pass_rate = (passed / total) if total else 0.0
    status = "ok" if failed == 0 else "error"
    message = "Planner evaluation completed." if status == "ok" else "Planner evaluation completed with failures."

    from lmola.schema_export import export_planner_schema_bundle

    planner_context = export_planner_schema_bundle()

    result = PlannerEvalRunResult(
        status=status,
        message=message,
        suite_id=suite.suite_id,
        total_cases=total,
        passed_cases=passed,
        failed_cases=failed,
        pass_rate=pass_rate,
        eval_dir=str(eval_dir),
        summary_csv=str(summary_csv),
        summary_json=str(summary_json),
        backend=cfg.llm.backend,
        model=cfg.llm.model,
        base_url=cfg.llm.base_url,
        temperature=cfg.llm.temperature,
        timeout_seconds=cfg.llm.timeout_seconds,
        max_tokens=cfg.llm.max_tokens,
        cases=rows,
        planner_prompt_mode="schema_driven",
        planner_context_schema_version=planner_context.get("schema_version"),
        planner_context_workflow_count=len(planner_context.get("workflows", [])),
        planner_context_allowed_workflow_ids=planner_context.get("allowed_workflow_ids", []),
    )
    dump_json(eval_dir / "eval_result.json", result.model_dump())
    (eval_dir / "README_eval.md").write_text("# LMolA planner evaluation\n\nThis evaluation measures planning quality only. Workflows are not executed.\n", encoding="utf-8")
    return result


def compare_planner_evals(eval_dir_a: str, eval_dir_b: str) -> dict:
    dir_a = Path(eval_dir_a)
    dir_b = Path(eval_dir_b)
    result_a = yaml.safe_load((dir_a / "eval_result.json").read_text(encoding="utf-8"))
    result_b = yaml.safe_load((dir_b / "eval_result.json").read_text(encoding="utf-8"))
    rows_a = yaml.safe_load((dir_a / "eval_summary.json").read_text(encoding="utf-8")) or []
    rows_b = yaml.safe_load((dir_b / "eval_summary.json").read_text(encoding="utf-8")) or []
    by_case_a = {row["case_id"]: row for row in rows_a}
    by_case_b = {row["case_id"]: row for row in rows_b}
    case_ids = sorted(set(by_case_a) | set(by_case_b))
    per_case: list[dict] = []
    for case_id in case_ids:
        a = by_case_a.get(case_id, {})
        b = by_case_b.get(case_id, {})
        per_case.append({
            "case_id": case_id,
            "a": {k: a.get(k) for k in ["passed", "workflow_match", "tools_match", "parse_ok", "validation_ok", "unsupported_handled", "failure_category"]},
            "b": {k: b.get(k) for k in ["passed", "workflow_match", "tools_match", "parse_ok", "validation_ok", "unsupported_handled", "failure_category"]},
        })
    return {
        "a": {
            "eval_dir": str(dir_a),
            "backend": result_a.get("backend"),
            "model": result_a.get("model"),
            "pass_rate": result_a.get("pass_rate"),
            "passed_cases": result_a.get("passed_cases"),
            "failed_cases": result_a.get("failed_cases"),
        },
        "b": {
            "eval_dir": str(dir_b),
            "backend": result_b.get("backend"),
            "model": result_b.get("model"),
            "pass_rate": result_b.get("pass_rate"),
            "passed_cases": result_b.get("passed_cases"),
            "failed_cases": result_b.get("failed_cases"),
        },
        "per_case": per_case,
    }


def run_planner_benchmark(eval_cases_yaml: str, backend: str | None = None, model: str | None = None, base_url: str | None = None, temperature: float | None = None, timeout_seconds: int | None = None, max_tokens: int | None = None, repeat: int = 1, case_filter: str | None = None, save_raw: bool = True) -> dict:
    bench_id = datetime.now(timezone.utc).strftime("benchmark_%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:6]
    bench_dir = Path("outputs") / "benchmarks" / bench_id
    bench_dir.mkdir(parents=True, exist_ok=False)

    env_overrides = {}
    if backend:
        env_overrides["LMOLA_LLM_BACKEND"] = backend
    if model:
        env_overrides["LMOLA_LLM_MODEL"] = model
    if base_url:
        env_overrides["LMOLA_LLM_BASE_URL"] = base_url
    env_overrides["LMOLA_LLM_ENABLED"] = "1"
    old_env = {k: os.environ.get(k) for k in env_overrides}
    os.environ.update(env_overrides)
    try:
        suite = load_eval_suite(eval_cases_yaml)
        if case_filter:
            suite.cases = [c for c in suite.cases if fnmatch.fnmatch(c.id, case_filter) or case_filter in c.id]
        runs = []
        for _ in range(max(1, repeat)):
            r = run_planner_eval(eval_cases_yaml)
            rows = r.cases
            if case_filter:
                rows = [row for row in rows if fnmatch.fnmatch(row["case_id"], case_filter) or case_filter in row["case_id"]]
            runs.append(rows)
        latest = runs[-1]
        total = len(latest)
        passed = sum(1 for r in latest if r.get("passed"))
        parse_success_rate = sum(1 for r in latest if r.get("parse_ok"))/total if total else 0.0
        schema_valid_rate = sum(1 for r in latest if r.get("validation_ok"))/total if total else 0.0
        workflow_selection_accuracy = sum(1 for r in latest if r.get("workflow_match"))/total if total else 0.0
        hallucination_rate = sum(1 for r in latest if r.get("hallucinated_workflow_id"))/total if total else 0.0
        bcv_rate = sum(1 for r in latest if r.get("backend_constraint_violated"))/total if total else 0.0
        unavail_sel_rate = sum(1 for r in latest if r.get("unavailable_backend_selected"))/total if total else 0.0
        mean_elapsed = sum(float(r.get("elapsed_seconds") or 0.0) for r in latest)/total if total else 0.0
        status_rows = [r for r in latest if r.get("expected_normalized_status") in {"unsupported", "backend_unavailable"}]
        unsupported_rows = [r for r in status_rows if r.get("expected_normalized_status") == "unsupported"]
        bu_rows = [r for r in status_rows if r.get("expected_normalized_status") == "backend_unavailable"]
        rep_rates = [sum(1 for r in rr if r.get("passed")) / len(rr) if rr else 0.0 for rr in runs]
        by_case = {}
        for rr in runs:
            for r in rr:
                by_case.setdefault(r["case_id"], []).append(bool(r.get("passed")))
        case_results = []
        unstable = []
        for r in latest:
            seq = by_case.get(r["case_id"], [bool(r.get("passed"))])
            pass_count = sum(seq)
            fail_count = len(seq) - pass_count
            stability = pass_count / len(seq) if seq else 0.0
            if len(set(seq)) > 1:
                unstable.append(r["case_id"])
            row_with_repeat = dict(r)
            row_with_repeat.update({"pass_count": pass_count, "fail_count": fail_count, "stability": stability})
            case_results.append(row_with_repeat)
        out = {
            "status": "ok" if passed == total else "error",
            "benchmark_id": bench_id,
            "suite_id": suite.suite_id,
            "backend": backend or load_app_config().llm.backend,
            "model": model or load_app_config().llm.model,
            "base_url": base_url or load_app_config().llm.base_url,
            "total_cases": total,
            "passed_cases": passed,
            "failed_cases": total - passed,
            "pass_rate": passed / total if total else 0.0,
            "workflow_selection_accuracy": workflow_selection_accuracy,
            "schema_valid_rate": schema_valid_rate,
            "parse_success_rate": parse_success_rate,
            "repair_attempt_rate": 0.0,
            "repair_success_rate": 0.0,
            "unsupported_accuracy": (sum(1 for r in unsupported_rows if r.get("normalized_status") == "unsupported") / len(unsupported_rows) if unsupported_rows else 0.0),
            "backend_unavailable_accuracy": (sum(1 for r in bu_rows if r.get("normalized_status") == "backend_unavailable") / len(bu_rows) if bu_rows else 0.0),
            "hallucination_rate": hallucination_rate,
            "backend_constraint_violation_rate": bcv_rate,
            "unavailable_backend_selection_rate": unavail_sel_rate,
            "mean_elapsed_seconds": mean_elapsed,
            "pass_rate_mean": sum(rep_rates) / len(rep_rates) if rep_rates else 0.0,
            "pass_rate_min": min(rep_rates) if rep_rates else 0.0,
            "pass_rate_max": max(rep_rates) if rep_rates else 0.0,
            "unstable_cases": unstable,
            "case_results": case_results,
            "summary_csv": str(bench_dir / "benchmark_summary.csv"),
            "summary_json": str(bench_dir / "benchmark_result.json"),
            "benchmark_dir": str(bench_dir),
        }
        dump_json(bench_dir / "benchmark_result.json", out)
        dump_json(bench_dir / "benchmark_config_redacted.json", {"llm": load_app_config().llm.model_dump()})
        dump_json(bench_dir / "model_info.json", {"backend": out["backend"], "model": out["model"], "base_url": out["base_url"], "temperature": temperature, "timeout_seconds": timeout_seconds, "max_tokens": max_tokens})
        with (bench_dir / "benchmark_summary.csv").open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=sorted({k for r in case_results for k in r.keys()}))
            writer.writeheader()
            for row in case_results:
                writer.writerow(row)
        cases_root = bench_dir / "cases"
        cases_root.mkdir(parents=True, exist_ok=True)
        for row in case_results:
            source_dir = Path(str(row.get("case_dir") or ""))
            if not source_dir.exists():
                continue
            target_dir = cases_root / str(row.get("case_id"))
            target_dir.mkdir(parents=True, exist_ok=True)
            for name in [
                "raw_llm_response.txt",
                "sanitized_llm_response.txt",
                "json_candidates.json",
                "parsed_output.json",
                "normalized_output.json",
                "case_result.json",
            ]:
                src = source_dir / name
                if src.exists():
                    shutil.copyfile(src, target_dir / name)
                elif name.endswith(".txt"):
                    (target_dir / name).write_text("", encoding="utf-8")
                elif name.endswith(".json"):
                    dump_json(target_dir / name, {} if name != "json_candidates.json" else [])
        return out
    finally:
        for k, v in old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
