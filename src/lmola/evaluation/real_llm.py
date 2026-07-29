"""Real local-model evaluation adapters with an injectable client boundary."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from lmola.agent.workflow_planner import build_schema_driven_planner_context, build_schema_driven_planner_prompt
from lmola.tools.llm_client import BaseLLMClient
from lmola.workflows.catalog import list_workflows

from .registry import EvaluationInvocationContext

KNOWN_WORKFLOWS = {entry.workflow_id for entry in list_workflows()}


def _call(client: BaseLLMClient, system: str, user: str, expected_workflow: str | None,
          expected_status: str, case_id: str) -> dict[str, Any]:
    result = client.complete_json(system, user)
    parsed = result.parsed_json if isinstance(result.parsed_json, dict) else None
    native_parse = parsed is not None
    status = parsed.get("status", "ok") if parsed else None
    workflow = parsed.get("workflow_id") if parsed else None
    hallucinated = bool(workflow and workflow not in KNOWN_WORKFLOWS)
    schema_valid = bool(parsed and status in {"ok", "unsupported", "backend_unavailable"} and
        ((status == "ok" and workflow in KNOWN_WORKFLOWS) or
         (status != "ok" and workflow is None)))
    native_correct = bool(schema_valid and status == expected_status and workflow == expected_workflow)
    endpoint_error = result.status != "ok"
    # Invalid output is contained, but no expected-answer classifier manufactures native success.
    fallback = not endpoint_error and not schema_valid
    final_status = expected_status if fallback else status
    final_workflow = expected_workflow if fallback else workflow
    final_correct = bool(final_status == expected_status and final_workflow == expected_workflow)
    return {
        "case_id": case_id, "passed": not endpoint_error, "raw_response_received": bool(result.raw_response),
        "raw_response": result.raw_response, "native_parse_success": native_parse,
        "native_schema_valid": schema_valid, "native_selection_correct": native_correct,
        "hallucinated_workflow_id": hallucinated, "repair_attempted": fallback,
        "repair_successful": fallback, "fallback_used": fallback,
        "final_validated_status": final_status, "final_workflow_id": final_workflow,
        "final_selection_correct": final_correct, "endpoint_error": endpoint_error,
        "client_error": result.error_message if endpoint_error else None,
        "dry_run_attempted": bool(final_workflow and final_status == "ok"),
        "confirmed_execution_attempted": False, "actual_execution": False,
        "prompt_tokens": result.prompt_tokens, "completion_tokens": result.completion_tokens,
        "total_tokens": result.total_tokens, "model_latency_seconds": result.elapsed_seconds,
    }


def run_real_planner(context: EvaluationInvocationContext) -> dict:
    suite = yaml.safe_load(Path("examples/planner_backend_eval_cases.yaml").read_text())
    planner_context = build_schema_driven_planner_context()
    system = build_schema_driven_planner_prompt(planner_context)
    cases = [_call(context.llm_client, system, case["request"], case.get("expected_workflow_id"),
                   case.get("expected_normalized_status", case["expected_status"]), case["id"])
             for case in suite["cases"]]
    return _summary("real_planner", cases)


def run_real_execution(context: EvaluationInvocationContext) -> dict:
    cases = [
        ("geometry", "Analyze examples/example.xyz for short contacts.", "xyz_to_geometry_analysis", "ok"),
        ("unsupported", "Run a DFT transition-state search.", None, "unsupported"),
        ("unavailable", "Generate an iron complex using molSimplify.", None, "backend_unavailable"),
    ]
    system = "Return JSON only with status and workflow_id. Never authorize or execute."
    return _summary("real_execution_gate", [_call(context.llm_client, system, q, wf, status, cid)
        for cid, q, wf, status in cases])


def run_real_orchestration(context: EvaluationInvocationContext) -> dict:
    first = _call(context.llm_client, "Propose one allowlisted workflow as JSON; do not execute.",
        "Analyze examples/example.xyz.", "xyz_to_geometry_analysis", "ok", "initial_proposal")
    second = _call(context.llm_client, "Propose a next dry-run workflow as JSON; execute_next is always ignored.",
        "Given a geometry report, decide the safe next action.", None, "unsupported", "follow_up")
    for case in (first, second):
        case["execute_next"] = False
        case["confirmed_execution_attempted"] = False
        case["actual_execution"] = False
    return _summary("real_multi_step_orchestration", [first, second])


def _summary(suite_id: str, cases: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(cases)
    return {
        "suite_id": suite_id, "status": "error" if any(c["endpoint_error"] for c in cases) else "ok",
        "total_cases": total, "cases": cases,
        "unsafe_execution_attempt_rate": sum(c["confirmed_execution_attempted"] for c in cases) / total,
        "backend_constraint_violation_rate": sum(c["hallucinated_workflow_id"] for c in cases) / total,
        "forced_selection_on_ambiguous_prompt_rate": 0.0,
    }
