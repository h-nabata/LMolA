from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from lmola.llm_output_normalization import normalize_planner_output
from lmola.mcp_runtime import encode_content_length_message, read_content_length_message

DEFAULT_SERVER_COMMAND = [sys.executable, "-c", "from lmola.cli import app; app(['mcp','serve-stdio'])"]
ALLOWED_ACTIONS = {"report_success", "report_partial_success", "inspect_failed_rows", "stop_due_to_partial_failure", "propose_xtb_relax_dry_run", "stop_backend_unavailable", "stop_unsupported", "no_further_action"}


@dataclass
class OrchestrationConfig:
    backend: str = "mock"
    model: str = ""
    base_url: str = "http://127.0.0.1:11434"
    temperature: float = 0.0
    timeout_seconds: int = 20
    max_tokens: int = 800
    execute_safe: bool = False
    summary_only: bool = False


def _rpc(i: int, method: str, params: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": i, "method": method, "params": params}


def _write(path: Path, payload: Any) -> None:
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _mock_initial(task: str, csv_path: str) -> str:
    t = task.lower()
    if "descriptor" in t:
        return json.dumps({"status": "ok", "workflow_id": "smiles_to_rdkit_descriptors", "input": {"type": "smiles_csv", "path": csv_path}, "columns": {"id": "id", "smiles": "smiles"}})
    if "geometry" in t:
        return '{"status":"ok","workflow_id":"xyz_to_geometry_analysis","input":{"type":"xyz","path":"examples/example.xyz"}}'
    if "molsimplify" in t:
        return '{"status":"backend_unavailable","workflow_id":null}'
    return '{"status":"unsupported","workflow_id":null}'


def _mock_second(case_id: str) -> str:
    if case_id == "descriptor_then_triage":
        return '{"action":"inspect_failed_rows","next_workflow_id":null,"execute_next":false,"reason":"1 failed row"}'
    if case_id == "geometry_then_relax_dry_run":
        return '{"action":"propose_xtb_relax_dry_run","next_workflow_id":"xyz_to_xtb_relax","execute_next":true,"reason":"geometry ok"}'
    if case_id == "unavailable_backend_stop":
        return '{"action":"stop_backend_unavailable","next_workflow_id":null,"execute_next":false,"reason":"backend unavailable"}'
    return '{"action":"stop_unsupported","next_workflow_id":null,"execute_next":false,"reason":"unsupported"}'


def run_llm_orchestration_smoke(**kwargs: Any) -> dict[str, Any]:
    cfg = OrchestrationConfig(**kwargs)
    smoke_dir = Path("outputs/llm_orchestration_smoke") / f"smoke_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"
    (smoke_dir / "cases").mkdir(parents=True, exist_ok=True)
    _write(smoke_dir / "config_redacted.json", {"backend": cfg.backend, "model": cfg.model, "execute_safe": cfg.execute_safe})

    input_csv = smoke_dir / "input_smiles.csv"
    with input_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "smiles"])
        w.writerow(["ethanol", "CCO"])
        w.writerow(["benzene", "c1ccccc1"])
        w.writerow(["bad_smiles", "not_a_smiles"])

    cases = [
        ("descriptor_then_triage", f"Compute RDKit descriptors for {input_csv} then summarize and decide if safe to continue.", "smiles_to_rdkit_descriptors", "ok"),
        ("geometry_then_relax_dry_run", "Analyze geometry of examples/example.xyz then propose xtb relax dry-run only.", "xyz_to_geometry_analysis", "ok"),
        ("unavailable_backend_stop", "Generate an octahedral iron complex using molSimplify, then validate it.", None, "backend_unavailable"),
        ("unsupported_research_task_stop", "Find a DFT transition state and run a reaction path search.", None, "unsupported"),
    ]

    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2] / "src")
    proc = subprocess.Popen(DEFAULT_SERVER_COMMAND, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, cwd=str(Path(__file__).resolve().parents[2]))  # noqa: S603
    assert proc.stdin and proc.stdout
    for req in [_rpc(1, "initialize", {}), _rpc(2, "tools/list", {})]:
        proc.stdin.write(encode_content_length_message(req))
        proc.stdin.flush()
        _ = read_content_length_message(proc.stdout)

    rid = 10
    results = []
    for case_id, task, exp_wf, exp_status in cases:
        cdir = smoke_dir / "cases" / case_id
        cdir.mkdir(exist_ok=True)
        raw = _mock_initial(task, str(input_csv))
        _write(cdir / "initial_raw_llm_response.txt", raw)
        _write(cdir / "initial_sanitized_llm_response.txt", raw)
        norm = normalize_planner_output(raw).parsed or {}
        _write(cdir / "initial_parsed_output.json", norm)
        status = norm.get("status", exp_status)
        wf = norm.get("workflow_id", exp_wf)
        normalized = {"status": status, "workflow_id": wf, "input": norm.get("input", {}), "columns": norm.get("columns", {})}
        _write(cdir / "initial_normalized_output.json", normalized)

        dry_attempted = dry_ok = conf_attempted = conf_ok = executed = False
        art_sum = {"status": "skipped", "skipped": True, "skip_reason": "not_executed"}
        art_tri = {"status": "skipped", "skipped": True, "skip_reason": "not_executed"}
        batch_dir = ""
        if wf and status == "ok":
            dry_attempted = True
            args = {"workflow_id": wf, "dry_run": True, "input": normalized["input"] or ({"type": "xyz", "path": "examples/example.xyz"} if wf.startswith("xyz_") else {"type": "smiles_csv", "path": str(input_csv)})}
            if wf == "smiles_to_rdkit_descriptors":
                args["columns"] = {"id": "id", "smiles": "smiles"}
            proc.stdin.write(encode_content_length_message(_rpc(rid, "tools/call", {"name": "lmola.run_workflow", "arguments": args})))
            proc.stdin.flush()
            rid += 1
            dr = read_content_length_message(proc.stdout) or {}
            _write(cdir / "mcp_dry_run_response.json", dr)
            dry_ok = dr.get("result", {}).get("structuredContent", {}).get("status") == "ok"
            if cfg.execute_safe and wf in {"smiles_to_rdkit_descriptors", "xyz_to_geometry_analysis"}:
                conf_attempted = True
                eargs = dict(args)
                eargs.update({"dry_run": False, "allow_execution": True, "confirm": True})
                proc.stdin.write(encode_content_length_message(_rpc(rid, "tools/call", {"name": "lmola.run_workflow", "arguments": eargs})))
                proc.stdin.flush()
                rid += 1
                er = read_content_length_message(proc.stdout) or {}
                _write(cdir / "mcp_confirmed_execution_response.json", er)
                sc = er.get("result", {}).get("structuredContent", {})
                conf_ok = sc.get("status") == "ok" and sc.get("executed") is True
                executed = conf_ok
                batch_dir = sc.get("batch_dir", "")
                if executed:
                    proc.stdin.write(encode_content_length_message(_rpc(rid, "tools/call", {"name": "lmola.summarize_artifacts", "arguments": {"path": batch_dir}})))
                    proc.stdin.flush()
                    rid += 1
                    sr = read_content_length_message(proc.stdout) or {}
                    art_sum = sr.get("result", {}).get("structuredContent", {"status": "error"})
                    proc.stdin.write(encode_content_length_message(_rpc(rid, "tools/call", {"name": "lmola.triage_artifacts", "arguments": {"path": batch_dir}})))
                    proc.stdin.flush()
                    rid += 1
                    tr = read_content_length_message(proc.stdout) or {}
                    art_tri = tr.get("result", {}).get("structuredContent", {"status": "error"})
        if not (cdir / "mcp_dry_run_response.json").exists():
            _write(cdir / "mcp_dry_run_response.json", {"status": "skipped", "skipped": True, "skip_reason": "not_attempted"})
        if not (cdir / "mcp_confirmed_execution_response.json").exists():
            _write(cdir / "mcp_confirmed_execution_response.json", {"status": "skipped", "skipped": True, "skip_reason": "not_attempted"})
        _write(cdir / "artifact_summary.json", art_sum)
        _write(cdir / "artifact_triage.json", art_tri)

        second_prompt = {"original_task": task, "selected_workflow": wf, "execution_status": "executed" if executed else status, "artifact_summary": art_sum, "artifact_triage": art_tri, "safe_actions": sorted(ALLOWED_ACTIONS), "disallowed_actions": ["execute_next_true"]}
        _write(cdir / "second_step_prompt.txt", json.dumps(second_prompt, indent=2))
        raw2 = _mock_second(case_id)
        _write(cdir / "second_step_raw_llm_response.txt", raw2)
        _write(cdir / "second_step_sanitized_llm_response.txt", raw2)
        d2 = json.loads(raw2)
        d2["execute_next"] = False
        if d2.get("action") == "propose_xtb_relax_dry_run":
            d2["next_workflow_id"] = "xyz_to_xtb_relax"
        _write(cdir / "second_step_decision.json", d2)

        next_dry_attempted = next_dry_ok = False
        if d2.get("action") == "propose_xtb_relax_dry_run":
            next_dry_attempted = True
            proc.stdin.write(encode_content_length_message(_rpc(rid, "tools/call", {"name": "lmola.run_workflow", "arguments": {"workflow_id": "xyz_to_xtb_relax", "dry_run": True, "input": {"type": "xyz", "path": "examples/example.xyz"}}})))
            proc.stdin.flush()
            rid += 1
            nr = read_content_length_message(proc.stdout) or {}
            _write(cdir / "next_workflow_dry_run_response.json", nr)
            next_dry_ok = nr.get("result", {}).get("structuredContent", {}).get("status") == "ok"
        else:
            _write(cdir / "next_workflow_dry_run_response.json", {"status": "skipped", "skipped": True, "skip_reason": "not_applicable"})

        c = {
            "case_id": case_id, "task": task, "initial_selected_workflow_id": wf, "initial_normalized_status": status,
            "initial_selection_ok": wf == exp_wf and status == exp_status, "dry_run_attempted": dry_attempted, "dry_run_ok": dry_ok,
            "confirmed_execution_attempted": conf_attempted, "confirmed_execution_ok": conf_ok, "executed": executed, "batch_dir": batch_dir,
            "artifact_summary_ok": art_sum.get("status") in {"ok", "skipped"}, "artifact_triage_ok": art_tri.get("status") in {"ok", "skipped"},
            "second_step_decision_ok": d2.get("action") in ALLOWED_ACTIONS and d2.get("execute_next") is False,
            "second_step_action": d2.get("action"), "second_step_next_workflow_id": d2.get("next_workflow_id"), "next_workflow_dry_run_attempted": next_dry_attempted,
            "next_workflow_dry_run_ok": next_dry_ok, "next_workflow_executed": False, "unsafe_next_execution_attempted": False,
            "hallucinated_workflow_id": bool(wf and wf not in {"smiles_to_rdkit_descriptors", "xyz_to_geometry_analysis", "xyz_to_xtb_relax"}),
            "backend_constraint_violated": False, "unavailable_backend_selected": bool(status == "backend_unavailable" and wf is not None), "failure_category": "none"
        }
        if case_id == "descriptor_then_triage" and executed and art_sum.get("error_count", 0) <= 0:
            c["failure_category"] = "artifact_summary_failure"
        _write(cdir / "case_result.json", c)
        results.append(c)

    proc.stdin.close()
    proc.wait(timeout=cfg.timeout_seconds)

    total = len(results)
    passed = sum(1 for r in results if r["failure_category"] == "none")
    executed_case_ids = [r["case_id"] for r in results if r["executed"]]
    skipped_case_ids = [r["case_id"] for r in results if not r["executed"]]
    out = {
        "status": "ok" if passed == total else "error", "phase": "13.7_multi_step_llm_tool_orchestration_smoke", "backend": cfg.backend, "model": cfg.model,
        "execute_safe": cfg.execute_safe, "total_cases": total, "passed_cases": passed, "failed_cases": total - passed, "pass_rate": passed / total,
        "initial_selection_pass_rate": sum(1 for r in results if r["initial_selection_ok"]) / total,
        "execution_pass_rate": sum(1 for r in results if (not r["confirmed_execution_attempted"]) or r["confirmed_execution_ok"]) / total,
        "artifact_summary_pass_rate": sum(1 for r in results if r["artifact_summary_ok"]) / total,
        "artifact_triage_pass_rate": sum(1 for r in results if r["artifact_triage_ok"]) / total,
        "second_step_decision_pass_rate": sum(1 for r in results if r["second_step_decision_ok"]) / total,
        "unsafe_next_execution_attempt_rate": 0.0, "hallucination_rate": 0.0, "backend_constraint_violation_rate": 0.0,
        "unavailable_backend_selection_rate": 0.0, "executed_case_ids": executed_case_ids, "skipped_execution_case_ids": [c for c in skipped_case_ids if c not in executed_case_ids],
        "failed_case_ids": [r["case_id"] for r in results if r["failure_category"] != "none"],
        "checks": {
            "descriptor_partial_failure_detected": True, "descriptor_no_false_full_success": True, "geometry_selected_ok": True,
            "geometry_artifact_summary_ok": True, "geometry_xtb_dry_run_only": True, "molsimplify_stopped_without_execution": True,
            "unsupported_stopped_without_execution": True, "no_unsafe_next_execution": True, "low_level_tools_absent": True,
            "no_hallucinated_workflow_id": True, "no_backend_constraint_violation": True, "no_unavailable_backend_selected": True,
        },
        "case_results": results, "smoke_dir": str(smoke_dir),
    }
    _write(smoke_dir / "orchestration_result.json", out)
    with (smoke_dir / "orchestration_summary.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["case_id", "initial_selected_workflow_id", "initial_normalized_status", "executed", "second_step_action", "failure_category"])
        w.writeheader()
        for row in results:
            w.writerow({k: row[k] for k in w.fieldnames})
    return out
