from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any
from lmola.workflows.catalog import get_workflow_entry

MAX_FILE_BYTES = 2_000_000


def _err(error_type: str, message: str, path: Path) -> dict[str, Any]:
    return {"status": "error", "error_type": error_type, "message": message, "path": str(path)}


def _safe_path(path: str | Path) -> Path:
    p = Path(path).expanduser().resolve()
    repo = Path.cwd().resolve()
    allowed = [repo / "outputs", repo / "examples", Path("/tmp")]
    if not any(p == root or root in p.parents for root in allowed):
        raise ValueError("unsafe_path")
    if str(p).startswith("/tmp") and "lmola" not in str(p):
        raise ValueError("unsafe_path")
    return p


def _read_json(path: Path) -> dict[str, Any] | list[Any] | None:
    if not path.exists():
        return None
    if path.stat().st_size > MAX_FILE_BYTES:
        return {"_error": "file_too_large"}
    return json.loads(path.read_text(encoding="utf-8"))


def _read_text_excerpt(path: Path, max_text_chars: int) -> str | None:
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[:max_text_chars]


def _canonical_tools_and_warnings(canonical: Any) -> tuple[list[str], list[str]]:
    warnings: list[str] = []
    raw_steps = canonical.get("steps") if isinstance(canonical, dict) else []
    if raw_steps is None or not isinstance(raw_steps, list):
        if isinstance(canonical, dict):
            warnings.append("canonical workflow steps are missing or null")
        steps: list[Any] = []
    else:
        steps = raw_steps
    tools = [s.get("tool") for s in steps if isinstance(s, dict) and s.get("tool")]
    return tools, warnings


def _catalog_tools_for_workflow_id(workflow_id: Any) -> list[str]:
    if not isinstance(workflow_id, str) or not workflow_id:
        return []
    try:
        return list(get_workflow_entry(workflow_id).tools)
    except Exception:  # noqa: BLE001
        return []


def detect_artifact_kind(path: str | Path) -> str:
    p = Path(path)
    if p.is_dir() and p.name.startswith("batch_"):
        return "batch_dir"
    if p.is_dir() and p.name.startswith("agent_smoke_"):
        return "agent_smoke_dir"
    if p.is_dir() and p.name.startswith("plan_"):
        return "plan_dir"
    if p.is_file() and p.name.startswith("mcp_run_") and p.suffix == ".json":
        return "mcp_audit"
    if p.name == "summary.json":
        return "summary_json"
    if p.name == "summary.csv":
        return "summary_csv"
    if p.name == "workflow_result.json":
        return "workflow_result_json"
    if p.name == "descriptors.json":
        return "descriptors_json"
    if p.name == "descriptors.csv":
        return "descriptors_csv"
    if p.name == "geometry_analysis.json":
        return "geometry_analysis_json"
    if p.name == "geometry_analysis.csv":
        return "geometry_analysis_csv"
    if p.name == "canonical_workflow.json":
        return "canonical_workflow_json"
    if p.name.endswith("validation_report.json"):
        return "validation_report"
    return "unknown_lmola_artifact"


def summarize_mcp_audit(audit_path: str | Path, *, max_text_chars: int = 4000) -> dict[str, Any]:
    p = Path(audit_path)
    payload = _read_json(p)
    if not isinstance(payload, dict):
        return _err("invalid_artifact", "Invalid MCP audit JSON.", p)
    canonical = payload.get("canonical_workflow_json") or {}
    tools, warnings = _canonical_tools_and_warnings(canonical)
    out = {
        "status": "ok",
        "artifact_kind": "mcp_audit",
        "path": str(p),
        "tool": payload.get("tool"),
        "workflow_id": payload.get("workflow_id"),
        "dry_run": payload.get("dry_run"),
        "allow_execution": payload.get("allow_execution"),
        "confirm": payload.get("confirm"),
        "execution_allowed": payload.get("execution_allowed"),
        "executed": payload.get("executed"),
        "batch_dir": payload.get("batch_dir"),
        "summary_csv": payload.get("summary_csv"),
        "summary_json": payload.get("summary_json"),
        "canonical_tools": tools,
        "error_type": payload.get("error_type"),
        "message": payload.get("message"),
        "warnings": warnings,
        "next_recommended_actions": [],
    }
    if out["dry_run"]:
        out["next_recommended_actions"].append("Review canonical workflow before confirmed execution.")
    if payload.get("status") == "error":
        out["next_recommended_actions"].append("Inspect validation/confirmation policy fields in this audit.")
    return out


def summarize_batch_dir(batch_dir: str | Path, *, max_items: int = 20, max_text_chars: int = 4000) -> dict[str, Any]:
    p = Path(batch_dir)
    summary_json = _read_json(p / "summary.json")
    workflow_result = _read_json(p / "workflow_result.json")
    canonical = _read_json(p / "canonical_workflow.json") or _read_json(p / "normalized_workflow.json") or {}
    tools, canonical_warnings = _canonical_tools_and_warnings(canonical)
    workflow_id = (workflow_result or {}).get("workflow_id") if isinstance(workflow_result, dict) else None
    if not tools:
        fallback_tools = _catalog_tools_for_workflow_id((canonical or {}).get("workflow_id") if isinstance(canonical, dict) else workflow_id)
        if fallback_tools:
            tools = fallback_tools
            canonical_warnings.append("canonical workflow steps were missing or null; canonical_tools inferred from workflow catalog.")
    items: list[dict[str, Any]] = []
    if isinstance(summary_json, dict) and isinstance(summary_json.get("items"), list):
        items = [i for i in summary_json["items"] if isinstance(i, dict)]
    elif (p / "summary.csv").exists():
        with (p / "summary.csv").open(encoding="utf-8") as fh:
            items = [dict(r) for r in csv.DictReader(fh)]
    truncated = items[:max_items]
    failed = [i for i in truncated if str(i.get("status", i.get("relax_status", ""))).lower() not in {"ok", "success", ""}]

    workflow_summary = {}
    if isinstance(workflow_result, dict):
        maybe_summary = workflow_result.get("summary")
        if isinstance(maybe_summary, dict):
            workflow_summary = maybe_summary
    source_counts = workflow_summary if workflow_summary else (workflow_result if isinstance(workflow_result, dict) else {})

    def _to_int(v: Any) -> int | None:
        try:
            return int(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    item_count = _to_int(source_counts.get("item_count"))
    ok_count = _to_int(source_counts.get("ok_count"))
    error_count = _to_int(source_counts.get("error_count"))

    if item_count is None or ok_count is None or error_count is None:
        item_count = len(items)
        ok_count = sum(1 for i in items if str(i.get("status", i.get("relax_status", ""))).lower() in {"ok", "success"})
        error_count = sum(1 for i in items if str(i.get("status", i.get("relax_status", ""))).lower() not in {"ok", "success", ""})

    artifact_files = sorted([x.name for x in p.iterdir()]) if p.exists() else []
    artifact_types = []
    artifact_subkind = None
    if "descriptors.csv" in artifact_files or "descriptors.json" in artifact_files or workflow_id == "smiles_to_rdkit_descriptors":
        artifact_subkind = "descriptor_batch"
        artifact_types.append("rdkit_descriptors")
    if "geometry_analysis.json" in artifact_files or "geometry_analysis.csv" in artifact_files or workflow_id == "xyz_to_geometry_analysis":
        artifact_subkind = "geometry_analysis_batch"
        artifact_types.append("geometry_analysis")
    next_actions = (
        [
            "Inspect summary.csv, relaxed structures, and representative item artifacts.",
            "Review canonical workflow before confirmed execution of related tasks.",
        ]
        if error_count == 0
        else ["Inspect failed_items, run.log, and validation reports for triage."]
    )
    return {
        "status": "ok",
        "artifact_kind": "batch_dir",
        "path": str(p),
        "batch_id": p.name,
        "workflow_id": workflow_id,
        "item_count": item_count,
        "ok_count": ok_count,
        "error_count": error_count,
        "success_rate": (ok_count / item_count) if item_count else None,
        "artifact_subkind": artifact_subkind,
        "artifact_types": artifact_types,
        "summary_csv": str(p / "summary.csv") if (p / "summary.csv").exists() else None,
        "summary_json": str(p / "summary.json") if (p / "summary.json").exists() else None,
        "workflow_result": workflow_result if isinstance(workflow_result, dict) else {},
        "canonical_tools": tools,
        "items": truncated,
        "failed_items": failed,
        "artifact_files": artifact_files,
        "warnings": ([w for w in canonical_warnings] + (["items_truncated"] if len(items) > max_items else [])),
        "next_recommended_actions": next_actions,
        "run_log_excerpt": _read_text_excerpt(p / "run.log", max_text_chars),
    }


def summarize_agent_smoke_dir(agent_smoke_dir: str | Path, *, max_text_chars: int = 4000) -> dict[str, Any]:
    p = Path(agent_smoke_dir)
    result = _read_json(p / "agent_smoke_result.json") or {}
    final = _read_json(p / "tool_selection_final.json") or {}
    analysis = _read_json(p / "result_analysis_parsed.json") or {}
    response = _read_json(p / "mcp_tool_call_response.json") or {}
    canonical = response.get("result", {}).get("structuredContent", {}).get("canonical_workflow_json", {}) if isinstance(response, dict) else {}
    tools, warnings = _canonical_tools_and_warnings(canonical)
    return {
        "status": "ok",
        "artifact_kind": "agent_smoke_dir",
        "path": str(p),
        "backend": result.get("backend"),
        "model": result.get("model"),
        "task": result.get("task"),
        "selected_tool_name": final.get("tool_name"),
        "selected_workflow_id": (final.get("arguments", {}) or {}).get("workflow_id"),
        "execution_mode": result.get("execution_mode", analysis.get("execution_mode")),
        "executed": bool(result.get("executed", False)),
        "tool_selection_repaired": bool(result.get("tool_selection_repaired", False)),
        "repair_attempted": bool(result.get("repair_attempted", False)),
        "repair_successful": bool(result.get("repair_successful", False)),
        "checks": result.get("checks", {}),
        "canonical_tools": tools or analysis.get("canonical_tools", []),
        "analysis": analysis if isinstance(analysis, dict) else {},
        "warnings": warnings,
        "next_recommended_actions": ["Review mcp_tool_call_response and audit_path summary before confirmed execution."],
        "raw_response_excerpt": _read_text_excerpt(p / "tool_selection_raw_response.txt", max_text_chars),
    }


def summarize_plan_dir(plan_dir: str | Path, *, max_text_chars: int = 4000) -> dict[str, Any]:
    p = Path(plan_dir)
    planning = _read_json(p / "planning_result.json") or {}
    canonical = _read_json(p / "canonical_workflow.json") or {}
    tools, warnings = _canonical_tools_and_warnings(canonical)
    return {
        "status": "ok",
        "artifact_kind": "plan_dir",
        "path": str(p),
        "natural_language_request": planning.get("request"),
        "selected_workflow_id": (planning.get("parsed_workflow") or {}).get("workflow_id"),
        "parsed_workflow": planning.get("parsed_workflow", {}),
        "validation_errors": planning.get("validation_errors", []),
        "canonical_tools": tools,
        "executed": False,
        "warnings": warnings,
        "next_recommended_actions": ["Validate canonical workflow and run dry-run execution first."],
        "planner_prompt_excerpt": _read_text_excerpt(p / "planner_prompt.txt", max_text_chars),
    }


def summarize_validation_report(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    payload = _read_json(p)
    if not isinstance(payload, dict):
        return _err("invalid_artifact", "Invalid validation report.", p)
    return {"status": "ok", "artifact_kind": "validation_report", "path": str(p), "report": payload}


def summarize_artifact_path(path: str | Path, *, max_items: int = 20, max_text_chars: int = 4000) -> dict[str, Any]:
    try:
        p = _safe_path(path)
    except ValueError:
        return _err("unsafe_path", "Path is outside allowed LMolA artifact roots.", Path(path))
    if not p.exists():
        return _err("not_found", "Path does not exist.", p)
    kind = detect_artifact_kind(p)
    if kind == "batch_dir":
        return summarize_batch_dir(p, max_items=max_items, max_text_chars=max_text_chars)
    if kind == "mcp_audit":
        return summarize_mcp_audit(p, max_text_chars=max_text_chars)
    if kind == "agent_smoke_dir":
        return summarize_agent_smoke_dir(p, max_text_chars=max_text_chars)
    if kind == "plan_dir":
        return summarize_plan_dir(p, max_text_chars=max_text_chars)
    if kind == "validation_report":
        return summarize_validation_report(p)
    if kind in {"summary_json", "workflow_result_json", "canonical_workflow_json"}:
        payload = _read_json(p)
        return {"status": "ok", "artifact_kind": kind, "path": str(p), "payload": payload}
    if kind in {"descriptors_json", "geometry_analysis_json"}:
        payload = _read_json(p)
        rows = payload if isinstance(payload, list) else []
        ok_count = sum(1 for r in rows if isinstance(r, dict) and str(r.get("status", "")).lower() == "ok")
        error_count = sum(1 for r in rows if isinstance(r, dict) and str(r.get("status", "")).lower() == "error")
        return {"status": "ok", "artifact_kind": kind, "path": str(p), "item_count": len(rows), "ok_count": ok_count, "error_count": error_count, "items": rows[:max_items]}
    if kind == "summary_csv":
        with p.open(encoding="utf-8") as fh:
            rows = [r for r in csv.DictReader(fh)]
        return {"status": "ok", "artifact_kind": kind, "path": str(p), "item_count": len(rows), "items": rows[:max_items]}
    if kind in {"descriptors_csv", "geometry_analysis_csv"}:
        with p.open(encoding="utf-8") as fh:
            rows = [r for r in csv.DictReader(fh)]
        ok_count = sum(1 for r in rows if str(r.get("status", "")).lower() == "ok")
        error_count = sum(1 for r in rows if str(r.get("status", "")).lower() == "error")
        return {"status": "ok", "artifact_kind": kind, "path": str(p), "item_count": len(rows), "ok_count": ok_count, "error_count": error_count, "items": rows[:max_items]}
    return {"status": "ok", "artifact_kind": "unknown_lmola_artifact", "path": str(p), "message": "Unsupported LMolA artifact path."}
