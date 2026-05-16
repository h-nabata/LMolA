from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import uuid

import yaml
from pydantic import BaseModel, Field, ValidationError

from lmola.config import is_local_llm_url_allowed, load_app_config, redacted_llm_config
from lmola.io.converters import dump_json
from lmola.io.run_artifacts import collect_environment
from lmola.tools.llm_client import make_llm_client
from lmola.tools.registry import list_tools
from lmola.workflows.catalog import FUTURE_TASK_TYPES, TASK_TAXONOMY, list_workflows
from lmola.workflows.schemas import WorkflowRequest


class WorkflowPlanningResult(BaseModel):
    status: str
    message: str
    natural_language_request: str
    selected_workflow_id: str | None = None
    raw_llm_response: str | None = None
    parsed_workflow: dict | None = None
    workflow_json: dict | None = None
    workflow_yaml: str | None = None
    validation_errors: list[str] = Field(default_factory=list)
    plan_dir: str | None = None
    config_redacted: dict | None = None


NOT_CONFIGURED_MSG = "Local LLM planning is disabled. Enable llm.enabled to use workflow planning."


def _create_plan_dir(base: str = "outputs") -> Path:
    plan_id = datetime.now(timezone.utc).strftime("plan_%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:6]
    path = Path(base) / plan_id
    path.mkdir(parents=True, exist_ok=False)
    return path


def _build_planner_prompt(request: str) -> str:
    catalog = [w.model_dump() for w in list_workflows()]
    tool_names = sorted(t.name for t in list_tools())
    supported_input_types = ["smiles", "smiles_csv", "xyz", "xyz_list"]
    return (
        "You are LMolA local workflow planner. Output only JSON.\\n"
        "Do not output prose, markdown, code fences, shell commands, or Python code.\\n"
        "Never execute tools. Never claim execution happened.\\n"
        "Use only workflow_id values from workflow catalog.\\n"
        "Use only tool names from typed tool registry.\\n"
        "Use only supported input types.\\n"
        "Do not invent tools, chemistry backends, package installation, environment changes, or cloud API calls.\\n"
        "If task unsupported, return: {\"status\":\"unsupported\",\"reason\":\"...\",\"suggested_supported_workflows\":[...]}\\n\\n"
        f"Task taxonomy: {json.dumps(TASK_TAXONOMY)}\\n"
        f"Future/unsupported task types: {json.dumps(FUTURE_TASK_TYPES)}\\n"
        f"Workflow catalog: {json.dumps(catalog, indent=2)}\\n"
        f"Typed tools: {json.dumps(tool_names)}\\n"
        f"Supported input types: {json.dumps(supported_input_types)}\\n"
        "Minimal valid workflow example:\\n"
        "{\"workflow_id\":\"smiles_to_3d_rdkit\",\"input\":{\"type\":\"smiles_csv\",\"path\":\"examples/smiles_list.csv\"},\"columns\":{\"id\":\"id\",\"smiles\":\"smiles\"},\"outputs\":{\"summary_csv\":true,\"summary_json\":true}}\\n\\n"
        f"Natural language request: {request}"
    )


def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3:
            stripped = "\n".join(lines[1:-1]).strip()
    return stripped


def _parse_planner_output(raw: str) -> dict:
    cleaned = _strip_code_fences(raw)
    try:
        return json.loads(cleaned)
    except Exception:
        parsed = yaml.safe_load(cleaned)
        if isinstance(parsed, dict):
            return parsed
        raise ValueError("Planner output is neither valid JSON nor YAML object.")


def plan_workflow_request(request_text: str, write_artifacts: bool = True) -> WorkflowPlanningResult:
    cfg = load_app_config()
    plan_dir = _create_plan_dir() if write_artifacts else None
    prompt = _build_planner_prompt(request_text)

    if plan_dir:
        (plan_dir / "natural_language_request.txt").write_text(request_text, encoding="utf-8")
        (plan_dir / "planner_prompt.txt").write_text(prompt, encoding="utf-8")
        dump_json(plan_dir / "effective_config.json", cfg.model_dump())
        dump_json(plan_dir / "environment.json", collect_environment())

    if not cfg.llm.enabled:
        result = WorkflowPlanningResult(status="error", message=NOT_CONFIGURED_MSG, natural_language_request=request_text, plan_dir=str(plan_dir) if plan_dir else None, config_redacted=redacted_llm_config(cfg.llm))
        if plan_dir:
            dump_json(plan_dir / "planning_result.json", result.model_dump())
        return result

    allowed, reason = is_local_llm_url_allowed(cfg.llm)
    if not allowed:
        result = WorkflowPlanningResult(status="error", message=f"Unsafe LLM endpoint: {reason}", natural_language_request=request_text, plan_dir=str(plan_dir) if plan_dir else None, config_redacted=redacted_llm_config(cfg.llm))
        if plan_dir:
            dump_json(plan_dir / "planning_result.json", result.model_dump())
        return result

    llm_result = make_llm_client(cfg.llm).complete_json(prompt, request_text)
    raw = llm_result.raw_response or (llm_result.error_message or "")
    if plan_dir:
        (plan_dir / "llm_response.raw.txt").write_text(raw, encoding="utf-8")
    if llm_result.status != "ok":
        result = WorkflowPlanningResult(status="error", message=llm_result.error_message or "LLM request failed", natural_language_request=request_text, raw_llm_response=raw, plan_dir=str(plan_dir) if plan_dir else None, config_redacted=redacted_llm_config(cfg.llm))
        if plan_dir:
            dump_json(plan_dir / "planning_result.json", result.model_dump())
        return result

    try:
        parsed = _parse_planner_output(raw)
    except Exception as exc:
        result = WorkflowPlanningResult(status="error", message="Failed to parse planner output", natural_language_request=request_text, raw_llm_response=raw, validation_errors=[str(exc)], plan_dir=str(plan_dir) if plan_dir else None, config_redacted=redacted_llm_config(cfg.llm))
        if plan_dir:
            dump_json(plan_dir / "planning_result.json", result.model_dump())
        return result

    if parsed.get("status") == "unsupported":
        result = WorkflowPlanningResult(status="error", message=parsed.get("reason", "Requested task is not supported by the current workflow catalog."), natural_language_request=request_text, raw_llm_response=raw, parsed_workflow=parsed, plan_dir=str(plan_dir) if plan_dir else None, config_redacted=redacted_llm_config(cfg.llm))
        if plan_dir:
            dump_json(plan_dir / "planning_result.json", result.model_dump())
        return result

    if "command" in parsed or "commands" in parsed:
        result = WorkflowPlanningResult(status="error", message="Planner output includes forbidden command fields.", natural_language_request=request_text, raw_llm_response=raw, parsed_workflow=parsed, validation_errors=["Forbidden fields: command/commands"], plan_dir=str(plan_dir) if plan_dir else None, config_redacted=redacted_llm_config(cfg.llm))
        if plan_dir:
            dump_json(plan_dir / "planning_result.json", result.model_dump())
        return result

    try:
        req = WorkflowRequest.model_validate(parsed)
    except ValidationError as exc:
        result = WorkflowPlanningResult(status="error", message="Planned workflow failed validation", natural_language_request=request_text, raw_llm_response=raw, parsed_workflow=parsed, validation_errors=[str(exc)], plan_dir=str(plan_dir) if plan_dir else None, config_redacted=redacted_llm_config(cfg.llm))
        if plan_dir:
            dump_json(plan_dir / "planning_result.json", result.model_dump())
        return result

    workflow_json = req.model_dump()
    workflow_yaml = yaml.safe_dump(workflow_json, sort_keys=False)
    result = WorkflowPlanningResult(status="ok", message="Workflow plan created and validated.", natural_language_request=request_text, selected_workflow_id=req.workflow_id, raw_llm_response=raw, parsed_workflow=parsed, workflow_json=workflow_json, workflow_yaml=workflow_yaml, plan_dir=str(plan_dir) if plan_dir else None, config_redacted=redacted_llm_config(cfg.llm))

    if plan_dir:
        dump_json(plan_dir / "planned_workflow.json", workflow_json)
        (plan_dir / "planned_workflow.yaml").write_text(workflow_yaml, encoding="utf-8")
        dump_json(plan_dir / "planning_result.json", result.model_dump())
        (plan_dir / "README_plan.md").write_text("# LMolA plan\n\nPlanning-only artifacts for workflow proposal.\n", encoding="utf-8")
    return result
