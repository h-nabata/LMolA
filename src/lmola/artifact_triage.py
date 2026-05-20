from __future__ import annotations

from pathlib import Path
from typing import Any

from lmola.artifact_summary import summarize_artifact_path

BACKEND_HINT_TOKENS = ("backend", "import", "executable", "not found", "unavailable")


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
    out = _base(Path(s["path"]), "batch_dir")
    failed = s.get("failed_items", []) or []
    error_count = int(s.get("error_count", 0) or 0)
    if error_count == 0:
        out["summary"] = "Batch summary indicates all items succeeded."
        out["safe_next_actions"] = ["Inspect representative generated/relaxed artifacts.", "Review canonical workflow before confirmed execution."]
        return out
    categories: set[str] = set()
    for item in failed:
        msg = str(item.get("error_message", ""))
        step = None
        if str(item.get("generate_status", "")).lower() == "error":
            categories.add("generation_failure")
            step = "generate"
        if str(item.get("validation_status", "")).lower() == "error":
            categories.add("validation_failure")
            step = "validate"
        if str(item.get("relax_status", "")).lower() == "error":
            categories.add("relaxation_failure")
            step = "relax"
        if any(t in msg.lower() for t in BACKEND_HINT_TOKENS):
            categories.add("backend_unavailable")
            out["backend_hints"].append(msg[:240])
        out["evidence"].append({"source": "summary.json", "message": msg or "item failed", "item_id": item.get("id") or item.get("item_id"), "step": step})
    out["has_failure"] = True
    out["severity"] = "error"
    out["affected_items"] = [e.get("item_id") for e in out["evidence"] if e.get("item_id")]
    out["failed_steps"] = sorted({e.get("step") for e in out["evidence"] if e.get("step")})
    if len(categories) > 1:
        out["failure_category"] = "partial_batch_failure"
    elif categories:
        out["failure_category"] = next(iter(categories))
    else:
        out["failure_category"] = "unknown_failure"
    out["summary"] = f"Batch has {error_count} failed item(s); classified as {out['failure_category']}."
    out["safe_next_actions"] = ["Inspect failed_items and run.log excerpts.", "Review per-item validation reports where present."]
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
