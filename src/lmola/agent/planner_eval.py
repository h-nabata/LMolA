from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
import uuid

import yaml
from pydantic import BaseModel, Field

from lmola.agent.workflow_planner import plan_workflow_request
from lmola.config import load_app_config
from lmola.io.converters import dump_json
from lmola.io.run_artifacts import collect_environment


class PlannerEvalCase(BaseModel):
    id: str
    request: str
    expected_status: str = "ok"
    expected_workflow_id: str | None = None
    expected_tools: list[str] | None = None
    notes: str | None = None


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
    if not row.get("parse_ok", False):
        return "parse_failure"
    if not row.get("validation_ok", False):
        return "schema_validation_failure"
    if row.get("expected_status") == "unsupported" and not row.get("unsupported_handled", False):
        return "unsupported_not_handled"
    if not row.get("workflow_match", True):
        return "wrong_workflow"
    if not row.get("tools_match", True):
        return "tool_mismatch"
    if str(row.get("actual_status", "")).lower() in {"endpoint_error", "client_error"}:
        return "endpoint_error"
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

        started = datetime.now(timezone.utc)
        planning = plan_workflow_request(case.request, write_artifacts=True)
        elapsed = (datetime.now(timezone.utc) - started).total_seconds()

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

        unsupported_handled = False
        if case.expected_status == "unsupported":
            unsupported_handled = planning.status == "error" and not canonicalization_ok and selected_workflow_id is None

        if case.expected_status == "ok":
            case_passed = planning.status == "ok" and workflow_match and tools_match
        elif case.expected_status == "unsupported":
            case_passed = unsupported_handled
        else:
            case_passed = planning.status == "error"

        if case_passed:
            passed += 1

        row = {
            "suite_id": suite.suite_id,
            "case_id": case.id,
            "request": case.request,
            "expected_status": case.expected_status,
            "actual_status": actual_status,
            "expected_workflow_id": case.expected_workflow_id,
            "selected_workflow_id": selected_workflow_id,
            "workflow_match": workflow_match,
            "expected_tools": case.expected_tools,
            "canonical_tools": canonical_tools,
            "tools_match": tools_match,
            "parse_ok": parse_ok,
            "validation_ok": validation_ok,
            "canonicalization_ok": canonicalization_ok,
            "unsupported_handled": unsupported_handled,
            "executed": planning_payload.get("executed", False),
            "plan_dir": planning_payload.get("plan_dir"),
            "case_dir": str(case_dir),
            "error_message": None if planning.status == "ok" else planning.message,
            "elapsed_seconds": elapsed,
            "passed": case_passed,
        }
        row["failure_category"] = _classify_failure(row)
        rows.append(row)
        dump_json(case_dir / "case_result.json", row)

    summary_json = eval_dir / "eval_summary.json"
    summary_csv = eval_dir / "eval_summary.csv"
    dump_json(summary_json, rows)
    with summary_csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ["suite_id", "case_id"])
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
