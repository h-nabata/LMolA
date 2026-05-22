from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import uuid

import yaml
from pydantic import BaseModel, Field, ValidationError

from lmola.llm_output_normalization import normalize_planner_output

from lmola.config import is_local_llm_url_allowed, load_app_config, redacted_llm_config
from lmola.io.converters import dump_json
from lmola.io.run_artifacts import collect_environment
from lmola.tools.llm_client import make_llm_client
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
    canonical_workflow_json: dict | None = None
    canonical_workflow_yaml: str | None = None
    planned_workflow_path_json: str | None = None
    planned_workflow_path_yaml: str | None = None
    canonical_workflow_path_json: str | None = None
    canonical_workflow_path_yaml: str | None = None
    validation_errors: list[str] = Field(default_factory=list)
    plan_dir: str | None = None
    config_redacted: dict | None = None
    executed: bool = False
    execution_result: dict | None = None
    batch_dir: str | None = None
    summary_csv: str | None = None
    summary_json: str | None = None
    planner_prompt_mode: str | None = None
    planner_context_schema_version: str | None = None
    planner_context_workflow_count: int | None = None
    planner_context_allowed_workflow_ids: list[str] | None = None


NOT_CONFIGURED_MSG = "Local LLM planning is disabled. Enable llm.enabled to use workflow planning."


def _create_plan_dir(base: str = "outputs") -> Path:
    plan_id = datetime.now(timezone.utc).strftime("plan_%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:6]
    path = Path(base) / plan_id
    path.mkdir(parents=True, exist_ok=False)
    return path


def build_schema_driven_planner_context() -> dict:
    from lmola.schema_export import export_planner_schema_bundle

    return export_planner_schema_bundle()


def build_schema_driven_planner_prompt(context: dict) -> str:
    supported_example = {
        "workflow_id": "<one of allowed_workflow_ids>",
        "input": {"type": "<one of allowed input types>", "path": "<input file path>"},
        "columns": {"id": "id", "smiles": "smiles"},
        "outputs": {"summary_csv": True, "summary_json": True},
    }
    supported_value_example = {"input": {"type": "smiles", "value": "CCO"}}
    unsupported_example = {"status": "unsupported", "reason": "short reason"}
    backend_unavailable_example = {"status": "backend_unavailable", "reason": "xTB backend is unavailable", "missing_backends": ["xtb"]}
    compare_example = {"status":"ok","workflow_id":"compare_two_geometries","input":{"type":"xyz_pair","paths":["examples/geometry_a.xyz","examples/geometry_b.xyz"]},"metadata":{"align":True,"atom_mapping":"file_order","output_per_atom_displacements":True},"reason":"Broad geometry comparison requested."}
    rmsd_only_example = {"status":"ok","workflow_id":"xyz_to_rmsd","input":{"type":"xyz_pair","paths":["examples/geometry_a.xyz","examples/geometry_b.xyz"]},"metadata":{"align":True,"atom_mapping":"file_order"},"reason":"RMSD-only calculation requested."}
    return (
        "You are LMolA local workflow planner.\\n"
        "You are the LMolA schema-driven workflow planner.\\n"
        "Output exactly one JSON object. JSON only.\\n"
        "Do not output Markdown, prose, code fences, comments, shell commands, tool command lines, or Python code.\\n"
        "Never execute tools. Never execute shell commands. Never claim execution happened.\\n"
        "Do not invent workflow IDs or tool names.\\n"
        "Do not invent backend IDs.\\n"
        "Use only workflows from allowed_workflow_ids and input types from allowed_input_types.\\n"
        "The selected workflow_id must support the selected input.type.\\n"
        "Choose only implemented workflows in catalog entries.\\n"
        "Prefer ready workflows when multiple workflows match the request.\\n"
        "Do not select workflows where readiness.ready is false or missing_backends is non-empty.\\n"
        "If request explicitly requires unavailable backend, return backend_unavailable with missing_backends.\\n"
        "If a known backend in backend_capabilities is unavailable, do not return generic unsupported; return backend_unavailable.\\n"
        "Do not turn unavailable workflows into executable plans.\\n"
        "Check each workflow's input_types before selecting a workflow.\\n"
        "For XYZ inputs, do not select SMILES-only workflows.\\n"
        "For CREST/DFT/TS/NEB tasks not in catalog, return unsupported.\\n"
        "If no workflow matches, return unsupported JSON. Do not force nearest workflow.\\n"
        "For supported tasks, include workflow_id and input.\\n"
        "For smiles_csv input, include columns when obvious: {\"id\":\"id\",\"smiles\":\"smiles\"}.\\n"
        "If the user names a file, prefer input.path. input.value is allowed for direct values like a single SMILES string.\\n\\n"
        f"Planner context schema version: {context.get('schema_version')}\\n"
        f"Allowed workflow IDs: {json.dumps(context.get('allowed_workflow_ids', []))}\\n"
        f"Allowed input types: {json.dumps(context.get('allowed_input_types', []))}\\n"
        f"Compact workflow list: {json.dumps(context.get('workflows', []), indent=2)}\\n"
        f"Output contract supported_task: {json.dumps(context.get('output_contract', {}).get('supported_task', {}))}\\n"
        f"Output contract unsupported_task: {json.dumps(context.get('output_contract', {}).get('unsupported_task', {}))}\\n"
        f"Supported task output example: {json.dumps(supported_example)}\\n"
        f"Value input example: {json.dumps(supported_value_example)}\\n"
        "Disambiguation rule: choose compare_two_geometries for broad structure comparison (atom-count match, element-order match, per-atom displacement, structural comparison, or compare geometries).\n"
        "Disambiguation rule: choose xyz_to_rmsd only for RMSD-only requests.\n"
        "Do not choose xyz_to_rmsd when the user asks for a general comparison.\n"
        f"Unsupported task output example: {json.dumps(unsupported_example)}"
        f"Backend unavailable output example: {json.dumps(backend_unavailable_example)}"
        f"Comparison output example: {json.dumps(compare_example)}"
        f"RMSD-only output example: {json.dumps(rmsd_only_example)}"
    )


def build_planner_messages(request_text: str, context: dict) -> list[dict]:
    return [
        {"role": "system", "content": build_schema_driven_planner_prompt(context)},
        {"role": "user", "content": request_text},
    ]



def _build_planner_prompt(request: str) -> str:
    context = build_schema_driven_planner_context()
    return build_schema_driven_planner_prompt(context) + f"\n\nNatural language request: {request}"

def _parse_planner_output(raw: str) -> dict:
    norm = normalize_planner_output(raw)
    if norm.parsed is None:
        raise ValueError("Planner output is neither valid JSON nor YAML object.")
    return norm.parsed


def _canonicalize_workflow(req: WorkflowRequest) -> dict:
    from lmola.workflows.catalog import get_workflow_entry

    entry = get_workflow_entry(req.workflow_id)
    if req.input.type not in entry.input_types:
        raise ValueError(f"Input type {req.input.type} is not supported by {req.workflow_id}")
    steps = req.steps or [{"tool": tool_name} for tool_name in entry.tools]
    return {
        "workflow_id": req.workflow_id,
        "input": req.input.model_dump(),
        "columns": req.columns,
        "steps": [s if isinstance(s, dict) else s.model_dump() for s in steps],
        "outputs": req.outputs.model_dump(),
        "metadata": req.metadata,
    }


def plan_workflow_request(request_text: str, write_artifacts: bool = True) -> WorkflowPlanningResult:
    cfg = load_app_config()
    plan_dir = _create_plan_dir() if write_artifacts else None
    context = build_schema_driven_planner_context()
    messages = build_planner_messages(request_text, context)
    prompt = messages[0]["content"] + f"\n\nNatural language request: {request_text}"

    if plan_dir:
        (plan_dir / "natural_language_request.txt").write_text(request_text, encoding="utf-8")
        dump_json(plan_dir / "planner_context_compact.json", context)
        (plan_dir / "planner_prompt.txt").write_text(prompt, encoding="utf-8")
        dump_json(plan_dir / "effective_config.json", cfg.model_dump())
        dump_json(plan_dir / "environment.json", collect_environment())

    if not cfg.llm.enabled:
        result = WorkflowPlanningResult(status="error", message=NOT_CONFIGURED_MSG, natural_language_request=request_text, plan_dir=str(plan_dir) if plan_dir else None, config_redacted=redacted_llm_config(cfg.llm), planner_prompt_mode="schema_driven", planner_context_schema_version=context.get("schema_version"), planner_context_workflow_count=len(context.get("workflows", [])), planner_context_allowed_workflow_ids=context.get("allowed_workflow_ids", []))
        if plan_dir:
            dump_json(plan_dir / "planning_result.json", result.model_dump())
        return result

    allowed, reason = is_local_llm_url_allowed(cfg.llm)
    if not allowed:
        result = WorkflowPlanningResult(status="error", message=f"Unsafe LLM endpoint: {reason}", natural_language_request=request_text, plan_dir=str(plan_dir) if plan_dir else None, config_redacted=redacted_llm_config(cfg.llm), planner_prompt_mode="schema_driven", planner_context_schema_version=context.get("schema_version"), planner_context_workflow_count=len(context.get("workflows", [])), planner_context_allowed_workflow_ids=context.get("allowed_workflow_ids", []))
        if plan_dir:
            dump_json(plan_dir / "planning_result.json", result.model_dump())
        return result

    llm_result = make_llm_client(cfg.llm).complete_json(prompt, request_text)
    raw = llm_result.raw_response or (llm_result.error_message or "")
    if plan_dir:
        (plan_dir / "llm_response.raw.txt").write_text(raw, encoding="utf-8")
    if llm_result.status != "ok":
        result = WorkflowPlanningResult(status="error", message=llm_result.error_message or "LLM request failed", natural_language_request=request_text, raw_llm_response=raw, plan_dir=str(plan_dir) if plan_dir else None, config_redacted=redacted_llm_config(cfg.llm), planner_prompt_mode="schema_driven", planner_context_schema_version=context.get("schema_version"), planner_context_workflow_count=len(context.get("workflows", [])), planner_context_allowed_workflow_ids=context.get("allowed_workflow_ids", []))
        if plan_dir:
            dump_json(plan_dir / "planning_result.json", result.model_dump())
        return result

    try:
        parsed = _parse_planner_output(raw)
    except Exception as exc:
        result = WorkflowPlanningResult(status="error", message="Failed to parse planner output", natural_language_request=request_text, raw_llm_response=raw, validation_errors=[str(exc)], plan_dir=str(plan_dir) if plan_dir else None, config_redacted=redacted_llm_config(cfg.llm), planner_prompt_mode="schema_driven", planner_context_schema_version=context.get("schema_version"), planner_context_workflow_count=len(context.get("workflows", [])), planner_context_allowed_workflow_ids=context.get("allowed_workflow_ids", []))
        if plan_dir:
            dump_json(plan_dir / "planning_result.json", result.model_dump())
        return result

    if parsed.get("status") in {"unsupported", "backend_unavailable"}:
        result = WorkflowPlanningResult(status="error", message=parsed.get("reason", "Requested task is not supported by the current workflow catalog."), natural_language_request=request_text, raw_llm_response=raw, parsed_workflow=parsed, plan_dir=str(plan_dir) if plan_dir else None, config_redacted=redacted_llm_config(cfg.llm), planner_prompt_mode="schema_driven", planner_context_schema_version=context.get("schema_version"), planner_context_workflow_count=len(context.get("workflows", [])), planner_context_allowed_workflow_ids=context.get("allowed_workflow_ids", []))
        if plan_dir:
            dump_json(plan_dir / "planning_result.json", result.model_dump())
        return result

    if "command" in parsed or "commands" in parsed:
        result = WorkflowPlanningResult(status="error", message="Planner output includes forbidden command fields.", natural_language_request=request_text, raw_llm_response=raw, parsed_workflow=parsed, validation_errors=["Forbidden fields: command/commands"], plan_dir=str(plan_dir) if plan_dir else None, config_redacted=redacted_llm_config(cfg.llm), planner_prompt_mode="schema_driven", planner_context_schema_version=context.get("schema_version"), planner_context_workflow_count=len(context.get("workflows", [])), planner_context_allowed_workflow_ids=context.get("allowed_workflow_ids", []))
        if plan_dir:
            dump_json(plan_dir / "planning_result.json", result.model_dump())
        return result

    try:
        req = WorkflowRequest.model_validate(parsed)
    except ValidationError as exc:
        result = WorkflowPlanningResult(status="error", message="Planned workflow failed validation", natural_language_request=request_text, raw_llm_response=raw, parsed_workflow=parsed, validation_errors=[str(exc)], plan_dir=str(plan_dir) if plan_dir else None, config_redacted=redacted_llm_config(cfg.llm), planner_prompt_mode="schema_driven", planner_context_schema_version=context.get("schema_version"), planner_context_workflow_count=len(context.get("workflows", [])), planner_context_allowed_workflow_ids=context.get("allowed_workflow_ids", []))
        if plan_dir:
            dump_json(plan_dir / "planning_result.json", result.model_dump())
        return result

    workflow_json = req.model_dump()
    workflow_yaml = yaml.safe_dump(workflow_json, sort_keys=False)
    if plan_dir:
        planned_json_path = plan_dir / "planned_workflow.json"
        planned_yaml_path = plan_dir / "planned_workflow.yaml"
        dump_json(planned_json_path, workflow_json)
        planned_yaml_path.write_text(workflow_yaml, encoding="utf-8")
    try:
        canonical_workflow_json = _canonicalize_workflow(req)
    except Exception as exc:
        result = WorkflowPlanningResult(
            status="error",
            message="Planned workflow failed canonicalization",
            natural_language_request=request_text,
            selected_workflow_id=req.workflow_id,
            raw_llm_response=raw,
            parsed_workflow=parsed,
            workflow_json=workflow_json,
            workflow_yaml=workflow_yaml,
            canonical_workflow_json=None,
            canonical_workflow_yaml=None,
            validation_errors=[str(exc)],
            plan_dir=str(plan_dir) if plan_dir else None,
            config_redacted=redacted_llm_config(cfg.llm),
            planner_prompt_mode="schema_driven",
            planner_context_schema_version=context.get("schema_version"),
            planner_context_workflow_count=len(context.get("workflows", [])),
            planner_context_allowed_workflow_ids=context.get("allowed_workflow_ids", []),
        )
        if plan_dir:
            result.planned_workflow_path_json = str(plan_dir / "planned_workflow.json")
            result.planned_workflow_path_yaml = str(plan_dir / "planned_workflow.yaml")
            dump_json(plan_dir / "planning_result.json", result.model_dump())
        return result
    canonical_workflow_yaml = yaml.safe_dump(canonical_workflow_json, sort_keys=False)
    result = WorkflowPlanningResult(status="ok", message="Workflow plan created and validated.", natural_language_request=request_text, selected_workflow_id=req.workflow_id, raw_llm_response=raw, parsed_workflow=parsed, workflow_json=workflow_json, workflow_yaml=workflow_yaml, canonical_workflow_json=canonical_workflow_json, canonical_workflow_yaml=canonical_workflow_yaml, plan_dir=str(plan_dir) if plan_dir else None, config_redacted=redacted_llm_config(cfg.llm), planner_prompt_mode="schema_driven", planner_context_schema_version=context.get("schema_version"), planner_context_workflow_count=len(context.get("workflows", [])), planner_context_allowed_workflow_ids=context.get("allowed_workflow_ids", []))

    if plan_dir:
        planned_json_path = plan_dir / "planned_workflow.json"
        planned_yaml_path = plan_dir / "planned_workflow.yaml"
        canonical_json_path = plan_dir / "canonical_workflow.json"
        canonical_yaml_path = plan_dir / "canonical_workflow.yaml"
        dump_json(canonical_json_path, canonical_workflow_json)
        canonical_yaml_path.write_text(canonical_workflow_yaml, encoding="utf-8")
        result.planned_workflow_path_json = str(planned_json_path)
        result.planned_workflow_path_yaml = str(planned_yaml_path)
        result.canonical_workflow_path_json = str(canonical_json_path)
        result.canonical_workflow_path_yaml = str(canonical_yaml_path)
        dump_json(plan_dir / "planning_result.json", result.model_dump())
        (plan_dir / "README_plan.md").write_text(
            "# LMolA Plan\n\n"
            f"- Request: {request_text}\n"
            f"- Selected workflow: {req.workflow_id}\n"
            "- Validation: success\n"
            "- Execution: not executed (planning-only dry run)\n\n"
            "## Artifact meaning\n"
            "- `planned_workflow.*`: validated LLM proposal (may keep `steps: null`).\n"
            "- `canonical_workflow.*`: catalog-expanded execution candidate with resolved steps.\n\n"
            "## Manual execution\n"
            f"Run: `lmola workflow run {canonical_yaml_path}`\n",
            encoding="utf-8",
        )
    return result
