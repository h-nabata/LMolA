from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from lmola.artifact_summary import summarize_artifact_path

BACKEND_HINT_TOKENS = ("backend", "import", "executable", "not found", "unavailable", "missing")
FAILURE_LIKE = {"error", "failed", "fail"}
SUCCESS_LIKE = {"ok", "success"}


def _base(path: Path, kind: str) -> dict[str, Any]:
    return {
        "status": "ok",
        "artifact_kind": kind,
        "path": str(path),
        "has_failure": False,
        "failure_category": "none",
        "severity": "info",
        "summary": "No failure detected.",
        "evidence": [],
        "affected_items": [],
        "failed_steps": [],
        "backend_hints": [],
        "safe_next_actions": ["Inspect artifact details and logs for context."],
        "not_recommended_actions": ["Do not bypass confirmation or allowlist safety controls."],
    }


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _is_failure(value: Any) -> bool:
    return _norm(value) in FAILURE_LIKE


def _extract_rows_from_summary_json(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        for key in ("items", "rows", "results"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return [r for r in rows if isinstance(r, dict)]
    return []


def _extract_rows(batch_path: Path, summary: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    rows: list[tuple[str, dict[str, Any]]] = []
    csv_path = batch_path / "summary.csv"
    if csv_path.exists():
        with csv_path.open(encoding="utf-8") as fh:
            rows.extend(("summary.csv", dict(r)) for r in csv.DictReader(fh))
    json_path = batch_path / "summary.json"
    json_rows = _extract_rows_from_summary_json(json_path)
    if json_rows:
        if rows:
            seen = {json.dumps(r, sort_keys=True, default=str) for _, r in rows}
            for row in json_rows:
                token = json.dumps(row, sort_keys=True, default=str)
                if token not in seen:
                    rows.append(("summary.json", row))
        else:
            rows.extend(("summary.json", r) for r in json_rows)
    if not rows and isinstance(summary.get("items"), list):
        rows.extend(("summary_payload", r) for r in summary["items"] if isinstance(r, dict))
    return rows


def _row_failed_steps(row: dict[str, Any]) -> set[str]:
    steps: set[str] = set()
    if _is_failure(row.get("generate_status")):
        steps.add("generate")
    if _is_failure(row.get("validation_status")):
        steps.add("validation")
    if _is_failure(row.get("relax_status")):
        steps.add("relax")
    failed_step = _norm(row.get("failed_step"))
    if failed_step.startswith("gen"):
        steps.add("generate")
    elif failed_step.startswith("val"):
        steps.add("validation")
    elif failed_step.startswith("relax"):
        steps.add("relax")
    elif failed_step:
        steps.add("unknown")
    status = _norm(row.get("status"))
    if not steps and status in FAILURE_LIKE:
        steps.add("unknown")
    return steps


def classify_failure(summary: dict[str, Any]) -> dict[str, Any]:
    kind = summary.get("artifact_kind", "unknown_lmola_artifact")
    if kind == "batch_dir":
        return triage_batch_dir(summary.get("path", ""), precomputed=summary)
    if kind == "mcp_audit":
        return triage_mcp_audit(summary.get("path", ""), precomputed=summary)
    if kind == "agent_smoke_dir":
        return triage_agent_smoke_dir(summary.get("path", ""), precomputed=summary)
    if kind == "plan_dir":
        return triage_plan_dir(summary.get("path", ""), precomputed=summary)
    out = _base(Path(summary.get("path", ".")), "unknown_lmola_artifact")
    out["summary"] = "Unsupported LMolA artifact kind for triage."
    return out


def triage_batch_dir(batch_dir: str | Path, *, max_items: int = 20, max_text_chars: int = 4000, precomputed: dict[str, Any] | None = None) -> dict[str, Any]:
    s = precomputed or summarize_artifact_path(batch_dir, max_items=max_items, max_text_chars=max_text_chars)
    if s.get("status") == "error":
        return s
    batch_path = Path(s["path"])
    out = _base(batch_path, "batch_dir")
    categories: set[str] = set()
    failed_steps: set[str] = set()
    affected: set[str] = set()
    rows = _extract_rows(batch_path, s)

    for idx, (source, row) in enumerate(rows):
        steps = _row_failed_steps(row)
        if not steps:
            continue
        item_id = row.get("item_id") or row.get("id") or f"item_index:{idx}"
        message = str(row.get("error_message") or row.get("message") or "item failed")
        for step in sorted(steps):
            out["evidence"].append({"source": source, "item_id": str(item_id), "step": step, "message": message})
            failed_steps.add(step)
        affected.add(str(item_id))
        if "generate" in steps:
            categories.add("generation_failure")
        if "validation" in steps:
            categories.add("validation_failure")
        if "relax" in steps:
            categories.add("relaxation_failure")
        if any(tok in message.lower() for tok in BACKEND_HINT_TOKENS):
            out["backend_hints"].append(message[:240])
            categories.add("backend_unavailable")

    error_count = int(s.get("error_count", 0) or 0)
    workflow_result = s.get("workflow_result", {}) if isinstance(s.get("workflow_result"), dict) else {}
    workflow_error_count = int(workflow_result.get("error_count", 0) or 0)
    total_error_count = max(error_count, workflow_error_count)

    if not categories and total_error_count == 0:
        out["summary"] = "Batch summary indicates all items succeeded."
        out["safe_next_actions"] = ["Inspect representative generated/relaxed artifacts.", "Review canonical workflow before confirmed execution."]
        return out

    out["has_failure"] = True
    out["severity"] = "error"
    out["affected_items"] = sorted(affected)
    out["failed_steps"] = sorted(step for step in failed_steps if step != "unknown")

    if len({c for c in categories if c != "backend_unavailable"}) > 1:
        out["failure_category"] = "partial_batch_failure"
    elif "backend_unavailable" in categories and len(categories) == 1:
        out["failure_category"] = "backend_unavailable"
    elif "generation_failure" in categories and categories <= {"generation_failure", "backend_unavailable"}:
        out["failure_category"] = "generation_failure"
    elif "validation_failure" in categories and categories <= {"validation_failure", "backend_unavailable"}:
        out["failure_category"] = "validation_failure"
    elif "relaxation_failure" in categories and categories <= {"relaxation_failure", "backend_unavailable"}:
        out["failure_category"] = "relaxation_failure"
    else:
        out["failure_category"] = "unknown_failure"

    if total_error_count > 0 and not out["evidence"]:
        out["failure_category"] = "unknown_failure"
        out["evidence"].append(
            {
                "source": "workflow_result.json",
                "item_id": None,
                "step": "unknown",
                "message": f"workflow_result reported error_count={total_error_count}; item-level failures not detected.",
            }
        )

    out["summary"] = f"Batch has failures; classified as {out['failure_category']}."
    out["safe_next_actions"] = ["Inspect failed items and run.log excerpts.", "Review validation reports and workflow_result.json details."]
    out["not_recommended_actions"].append("Do not infer chemical correctness beyond artifact status fields.")
    return out


def triage_mcp_audit(audit_path: str | Path, *, max_items: int = 20, max_text_chars: int = 4000, precomputed: dict[str, Any] | None = None) -> dict[str, Any]:
    s = precomputed or summarize_artifact_path(audit_path, max_items=max_items, max_text_chars=max_text_chars)
    if s.get("status") == "error":
        return s
    out = _base(Path(s["path"]), "mcp_audit")
    et = s.get("error_type")
    if s.get("status") == "ok" and s.get("dry_run") is True and s.get("executed") is False and not et:
        out["summary"] = "Dry-run MCP audit succeeded without execution."
        return out
    mapping = {
        "confirmation_required": "safety_rejection",
        "execution_not_allowed": "safety_rejection",
        "tool_not_allowed": "safety_rejection",
        "unsafe_path": "safety_rejection",
        "validation_error": "workflow_validation_failure",
    }
    out["has_failure"] = True
    out["severity"] = "error"
    out["failure_category"] = mapping.get(et, "unknown_failure")
    out["summary"] = s.get("message") or f"MCP audit reported {et or 'failure'}."
    out["evidence"].append({"source": "mcp_audit", "message": out["summary"], "item_id": None, "step": None})
    out["safe_next_actions"] = ["Review canonical workflow and request payload.", "Use confirm=true only after explicit review for non-dry-run execution."]
    return out


def triage_agent_smoke_dir(agent_smoke_dir: str | Path, *, max_items: int = 20, max_text_chars: int = 4000, precomputed: dict[str, Any] | None = None) -> dict[str, Any]:
    s = precomputed or summarize_artifact_path(agent_smoke_dir, max_items=max_items, max_text_chars=max_text_chars)
    if s.get("status") == "error":
        return s
    out = _base(Path(s["path"]), "agent_smoke_dir")
    checks = s.get("checks", {}) or {}
    if str(s.get("status")) == "ok" and checks.get("analysis_status_ok", True):
        out["summary"] = "Agent smoke artifact indicates success."
    if s.get("repair_attempted") and not s.get("repair_successful"):
        out.update({"has_failure": True, "failure_category": "tool_call_schema_failure", "severity": "error", "summary": "Tool-call repair failed."})
    if checks.get("tool_selection_final_valid") is False:
        out.update({"has_failure": True, "failure_category": "tool_call_schema_failure", "severity": "error", "summary": "Tool-call schema validation failed."})
    if checks.get("analysis_parse_ok") is False or checks.get("analysis_schema_ok") is False:
        out.update({"has_failure": True, "failure_category": "llm_parse_failure", "severity": "error", "summary": "LLM analysis parse/schema check failed."})
    return out


def triage_plan_dir(plan_dir: str | Path, *, max_items: int = 20, max_text_chars: int = 4000, precomputed: dict[str, Any] | None = None) -> dict[str, Any]:
    s = precomputed or summarize_artifact_path(plan_dir, max_items=max_items, max_text_chars=max_text_chars)
    if s.get("status") == "error":
        return s
    out = _base(Path(s["path"]), "plan_dir")
    parsed = s.get("parsed_workflow", {}) if isinstance(s.get("parsed_workflow"), dict) else {}
    if s.get("validation_errors"):
        out.update({"has_failure": True, "failure_category": "workflow_validation_failure", "severity": "error", "summary": "Plan validation errors present."})
    elif parsed.get("status") == "unsupported":
        out.update({"has_failure": True, "failure_category": "unsupported_task", "severity": "warning", "summary": "Planner marked request as unsupported."})
    return out


def triage_artifact_path(path: str | Path, *, max_items: int = 20, max_text_chars: int = 4000) -> dict[str, Any]:
    summary = summarize_artifact_path(path, max_items=max_items, max_text_chars=max_text_chars)
    if summary.get("status") == "error":
        return summary
    return classify_failure(summary)
