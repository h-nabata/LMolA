from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

from lmola.io.converters import dump_json
from lmola.tools.registry import execute_tool, get_tool
from lmola.workflows.catalog import get_workflow_entry
from lmola.workflows.schemas import BatchItemResult, WorkflowExecutionResult, WorkflowRequest, WorkflowSummary


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}


def _validate_safe_step_params(params: dict[str, Any]) -> None:
    blocked = {"command", "executable", "shell", "args"}
    if blocked.intersection(params):
        raise ValueError("Unsafe command-like fields are not allowed in workflow step params")


def _resolve_artifact_path(run_dir: str | None, artifact: str | None) -> str | None:
    if not run_dir or not artifact:
        return None
    art = Path(artifact)
    if art.is_absolute():
        return str(art)
    return str((Path(run_dir) / art).resolve())


def _load_items(req: WorkflowRequest) -> list[dict[str, str]]:
    if req.input.type in {"smiles", "xyz"}:
        if not req.input.value:
            raise ValueError("input.value is required for smiles/xyz input types")
        return [{"id": "item_0001", "value": req.input.value}]
    if not req.input.path:
        raise ValueError("input.path is required for list/csv input types")
    path = Path(req.input.path)
    if req.input.type == "smiles_csv":
        with path.open("r", encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        id_col = (req.columns or {}).get("id", "id")
        smiles_col = (req.columns or {}).get("smiles", "smiles")
        if rows and (id_col not in rows[0] or smiles_col not in rows[0]):
            raise ValueError(f"CSV missing required columns: {id_col}, {smiles_col}")
        return [{"id": r.get(id_col) or f"item_{i+1:04d}", "value": r.get(smiles_col, "")} for i, r in enumerate(rows)]
    if req.input.type == "xyz_list":
        with path.open("r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
        return [{"id": f"item_{i+1:04d}", "value": line} for i, line in enumerate(lines)]
    raise ValueError(f"Unsupported input.type: {req.input.type}")


def run_workflow_yaml(workflow_yaml_path: str) -> WorkflowExecutionResult:
    source_path = Path(workflow_yaml_path)
    try:
        raw = _load_yaml(source_path)
        req = WorkflowRequest.model_validate(raw)
        entry = get_workflow_entry(req.workflow_id)
        if req.input.type not in entry.input_types:
            raise ValueError(f"Input type {req.input.type} is not supported by {req.workflow_id}")
        steps = req.steps or [{"tool": t} for t in entry.tools]
        for step in steps:
            get_tool(step["tool"] if isinstance(step, dict) else step.tool)
            params = step.get("params", {}) if isinstance(step, dict) else (step.params or {})
            _validate_safe_step_params(params)
    except Exception as exc:
        return WorkflowExecutionResult(status="error", message=f"Workflow validation failed: {exc}")

    batch_id = f"batch_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"
    batch_dir = Path("outputs") / batch_id
    items_dir = batch_dir / "items"
    items_dir.mkdir(parents=True, exist_ok=True)
    (batch_dir / "workflow.yaml").write_text(source_path.read_text(encoding="utf-8"), encoding="utf-8")
    dump_json(batch_dir / "normalized_workflow.json", req.model_dump())

    item_inputs = _load_items(req)
    results: list[BatchItemResult] = []

    for idx, item in enumerate(item_inputs, start=1):
        item_dir = items_dir / f"item_{idx:04d}"
        item_dir.mkdir(parents=True, exist_ok=True)
        r = BatchItemResult(batch_id=batch_id, item_index=idx, item_id=item["id"], input_type=req.input.type, input_value=item["value"], workflow_id=req.workflow_id)
        current_structure_path: str | None = item["value"] if req.input.type in {"xyz", "xyz_list"} else None

        try:
            for step in steps:
                step_tool = step["tool"] if isinstance(step, dict) else step.tool
                step_params = dict(step.get("params", {}) if isinstance(step, dict) else (step.params or {}))

                if step_tool.startswith("generate_small_molecule"):
                    step_params.setdefault("request_type", "small_molecule")
                    step_params.setdefault("smiles", item["value"])
                elif step_tool == "validate_structure_ase":
                    step_params.setdefault("structure_path", current_structure_path)
                elif step_tool == "relax_structure_xtb":
                    step_params.setdefault("input_structure", current_structure_path)
                    step_params.setdefault("method", "xtb")

                step_run_dir = item_dir / step_tool
                step_run_dir.mkdir(exist_ok=True)
                out = execute_tool(step_tool, step_params, step_run_dir)

                if step_tool.startswith("generate_small_molecule"):
                    r.generate_status = out.status
                    r.generate_run_dir = out.run_dir
                    r.primary_structure = out.payload.get("primary_structure")
                    r.primary_structure_path = _resolve_artifact_path(out.run_dir, r.primary_structure)
                    current_structure_path = r.primary_structure_path
                    if out.payload.get("generated_files"):
                        for gf in out.payload["generated_files"]:
                            gf_str = str(gf)
                            if gf_str.endswith("conformer_ensemble.json"):
                                r.conformer_ensemble_path = _resolve_artifact_path(out.run_dir, gf_str) or gf_str
                            elif gf_str.endswith(".sdf"):
                                r.sdf_path = _resolve_artifact_path(out.run_dir, gf_str) or gf_str
                    if out.status != "ok":
                        raise RuntimeError(f"{step_tool}: {out.message}")

                elif step_tool == "validate_structure_ase":
                    r.validation_status = out.status
                    r.validation_report_path = str((step_run_dir / "validation_report.json").resolve())
                    if out.status != "ok":
                        messages = out.payload.get("messages", []) if isinstance(out.payload, dict) else []
                        details = "; ".join(messages) if messages else out.message
                        raise RuntimeError(f"{step_tool}: {details}")

                elif step_tool == "relax_structure_xtb":
                    r.relax_status = out.status
                    r.relax_run_dir = out.run_dir
                    r.relaxed_structure = out.payload.get("output_structure")
                    r.relaxed_structure_path = _resolve_artifact_path(out.run_dir, r.relaxed_structure)

                    tool_exec = step_run_dir / "tool_execution_result.json"
                    tool_legacy = step_run_dir / "tool_result.json"
                    if tool_exec.exists():
                        payload = json.loads(tool_exec.read_text(encoding="utf-8"))
                    elif tool_legacy.exists():
                        payload = json.loads(tool_legacy.read_text(encoding="utf-8"))
                    else:
                        payload = {}
                    r.energy = payload.get("energy")
                    r.energy_units = payload.get("energy_units")

                    if out.status != "ok":
                        raise RuntimeError(f"{step_tool}: {out.message}")

                elif out.status != "ok":
                    raise RuntimeError(f"{step_tool}: {out.message}")

        except Exception as exc:
            r.failed_step = step_tool
            r.error_message = str(exc)
            results.append(r)
            if req.outputs.fail_fast:
                break
            continue

        results.append(r)

    summary_rows = [x.model_dump() for x in results]
    if req.outputs.summary_csv:
        with (batch_dir / "summary.csv").open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(BatchItemResult.model_fields))
            writer.writeheader()
            writer.writerows(summary_rows)
    if req.outputs.summary_json:
        dump_json(batch_dir / "summary.json", summary_rows)

    ok_count = sum(1 for r in results if not r.error_message)
    error_count = len(results) - ok_count
    message = "Workflow executed" if error_count == 0 else "Workflow executed with item errors"
    summary = WorkflowSummary(batch_id=batch_id, workflow_id=req.workflow_id, item_count=len(results), ok_count=ok_count, error_count=error_count)
    workflow_result_payload = {
        "status": "ok",
        "message": message,
        "batch_id": batch_id,
        "workflow_id": req.workflow_id,
        "item_count": len(results),
        "ok_count": ok_count,
        "error_count": error_count,
        "summary_csv": str(batch_dir / "summary.csv"),
        "summary_json": str(batch_dir / "summary.json"),
        "batch_dir": str(batch_dir),
        "summary": summary.model_dump(),
    }
    dump_json(batch_dir / "workflow_result.json", workflow_result_payload)
    (batch_dir / "run.log").write_text(f"{message}.\n", encoding="utf-8")
    (batch_dir / "README_batch.md").write_text("# LMolA Batch Workflow Run\n", encoding="utf-8")

    return WorkflowExecutionResult(status="ok", message=message, batch_dir=str(batch_dir), summary_csv=str(batch_dir / "summary.csv"), summary_json=str(batch_dir / "summary.json"), summary=summary)
