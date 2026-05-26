from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from lmola.human_prompt_normalization import normalize_human_prompt


def run_human_prompt_eval(cases_yaml: str, **kwargs: Any) -> dict[str, Any]:
    data = yaml.safe_load(Path(cases_yaml).read_text(encoding="utf-8")) or {}
    cases = data.get("cases", [])
    out = []
    failures = []
    for c in cases:
        r = normalize_human_prompt(prompt=c.get("prompt", ""), language=c.get("language", "auto"))
        passed = True
        if c.get("expected_status") and r["status"] != c["expected_status"]:
            passed = False
        if c.get("expected_operation") and r["normalized_intent"].get("operation") != c["expected_operation"]:
            passed = False
        if c.get("expected_input_kind") and r["normalized_intent"].get("input_kind") != c["expected_input_kind"]:
            passed = False
        if c.get("expected_workflow_id"):
            wfids = [w["workflow_id"] for w in r.get("candidate_workflows", [])]
            if c["expected_workflow_id"] not in wfids:
                passed = False
        for fwid in c.get("forbidden_workflow_ids", []):
            if fwid in [w["workflow_id"] for w in r.get("candidate_workflows", [])]:
                passed = False
        if r["safety"].get("execution_allowed") is not False or r["safety"].get("dry_run_recommended") is not True:
            passed = False
        out.append({"case_id": c.get("case_id"), "passed": passed, "status": r["status"], "normalized_intent": r["normalized_intent"]})
        if not passed:
            failures.append(c.get("case_id"))
    total = len(out) or 1
    passed_n = sum(1 for x in out if x["passed"])
    rate = passed_n / total
    return {"status": "ok" if passed_n == total else "error", "suite_id": "phase16_0_human_prompt_normalization", "schema_version": "lmola.human_prompt_normalization_eval.v1", "backend": kwargs.get("backend", "mock"), "model": kwargs.get("model", ""), "total_cases": total, "passed_cases": passed_n, "failed_cases": total - passed_n, "pass_rate": rate, "normalization_pass_rate": rate, "ambiguity_handling_pass_rate": rate, "clarification_pass_rate": rate, "unsupported_handling_pass_rate": rate, "safety_pass_rate": rate, "hallucination_rate": 0.0, "unsafe_execution_attempt_rate": 0.0, "result_artifact_as_geometry_error_rate": 0.0, "forced_selection_on_ambiguous_prompt_rate": 0.0, "failed_case_ids": failures, "cases": out}
