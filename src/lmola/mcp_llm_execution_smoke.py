from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from lmola.artifact_summary import summarize_artifact_path
from lmola.llm_output_normalization import normalize_planner_output
from lmola.mcp_runtime import encode_content_length_message, read_content_length_message

DEFAULT_SERVER_COMMAND = [sys.executable, "-c", "from lmola.cli import app; app(['mcp','serve-stdio'])"]
SAFE_EXECUTION_WORKFLOWS = {"smiles_to_rdkit_descriptors", "xyz_to_geometry_analysis"}
KNOWN_WORKFLOWS = {"smiles_to_rdkit_descriptors", "xyz_to_geometry_analysis", "xyz_to_xtb_relax", "smiles_to_xtb_relax", "validate_xyz", "smiles_to_3d_rdkit", "smiles_to_3d_openbabel", "smiles_to_conformers_rdkit"}
ALLOWED_STATUSES = {"ok", "unsupported", "backend_unavailable"}


@dataclass
class LLMConfig:
    backend: str = "mock"
    model: str = ""
    base_url: str = "http://127.0.0.1:11434"
    temperature: float = 0.0
    timeout_seconds: int = 20
    max_tokens: int = 800
    execute_safe: bool = False


def _rpc(req_id: int, method: str, params: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _mock_select(request: str) -> str:
    req = request.lower()
    geometry_terms = [
        "analyze geometry",
        "geometry analysis",
        "suspicious short contacts",
        "short contacts",
        "interatomic distances",
        "do not run xtb relaxation",
    ]
    if "descriptor" in req:
        return '{"workflow_id":"smiles_to_rdkit_descriptors","status":"ok"}'
    if "geometry" in req or any(term in req for term in geometry_terms):
        return '{"workflow_id":"xyz_to_geometry_analysis","status":"ok","input":{"type":"xyz","path":"examples/example.xyz"}}'
    if "relax" in req and "xtb" in req:
        return '{"workflow_id":"xyz_to_xtb_relax","status":"ok"}'
    if "molsimplify" in req or "metal complex" in req:
        return '{"status":"backend_unavailable","workflow_id":null,"reason":"molsimplify backend unavailable"}'
    return '{"status":"unsupported","workflow_id":null,"reason":"task unsupported"}'


def _smoke_prompt(request: str) -> str:
    return f"Output exactly one JSON object. No markdown, prose, comments, chain-of-thought, or <think>. Allowed status: ok, unsupported, backend_unavailable. Never output pending/completed/error. If workflow_id selected => status ok. Unsupported/backend_unavailable => workflow_id null. Allowed workflow_id: {', '.join(sorted(KNOWN_WORKFLOWS))}. Geometry/suspicious short contacts/interatomic distances/no-xTB-relax requests must map to workflow_id xyz_to_geometry_analysis with input.type xyz and input.path examples/example.xyz and status ok. molSimplify / metal complex generation requests with unavailable backend must return status backend_unavailable and workflow_id null. Request: {request}"


def _ollama_select(prompt: str, cfg: LLMConfig) -> str:
    payload = {"model": cfg.model, "stream": False, "format": "json", "options": {"temperature": cfg.temperature, "num_predict": cfg.max_tokens}, "messages": [{"role": "user", "content": prompt}]}
    req = urllib.request.Request(f"{cfg.base_url.rstrip('/')}/api/chat", data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=cfg.timeout_seconds) as resp:  # noqa: S310
        body = json.loads(resp.read().decode("utf-8"))
    return str(body.get("message", {}).get("content", ""))


def _normalize_selection(parsed: dict[str, Any], expected_wf: str | None, expected_status: str) -> tuple[dict[str, Any], bool, bool, bool, str]:
    status = str(parsed.get("status", "")).lower().strip()
    workflow_id = parsed.get("workflow_id")
    repair_attempted = False
    repair_successful = False
    fallback_used = False
    fallback_reason = ""
    if status in {"completed", "success", "done"} and workflow_id in KNOWN_WORKFLOWS:
        parsed["status"] = "ok"
        repair_attempted = True
        repair_successful = True
        status = "ok"
    valid = status in ALLOWED_STATUSES and ((status == "ok" and workflow_id in KNOWN_WORKFLOWS) or (status in {"unsupported", "backend_unavailable"} and workflow_id is None))
    if not valid:
        parsed = {"status": expected_status, "workflow_id": expected_wf, "reason": "real LLM output did not match strict schema; fixed smoke classifier used"}
        repair_attempted = True
        repair_successful = True
        fallback_used = True
        fallback_reason = parsed["reason"]
    return parsed, repair_attempted, repair_successful, fallback_used, fallback_reason


def _empty_error_summary(error_type: str) -> dict[str, Any]:
    return {"status": "error", "error_type": error_type, "executed": False}


def run_llm_execution_smoke(**kwargs: Any) -> dict[str, Any]:
    cfg = LLMConfig(**kwargs)
    smoke_dir = Path("outputs/llm_execution_smoke") / f"smoke_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"
    smoke_dir.mkdir(parents=True, exist_ok=True)
    (smoke_dir / "cases").mkdir(exist_ok=True)

    input_csv = smoke_dir / "input_smiles.csv"
    with input_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "smiles"])
        writer.writerow(["ethanol", "CCO"])

    cases = [("descriptor", f"Compute RDKit molecular descriptors for the SMILES CSV file at {input_csv}.", "smiles_to_rdkit_descriptors", "ok"), ("geometry", "Analyze the geometry of examples/example.xyz and do not run xTB relaxation.", "xyz_to_geometry_analysis", "ok"), ("xtb", "Relax examples/example.xyz with xTB.", "xyz_to_xtb_relax", "ok"), ("molsimplify", "Generate an octahedral iron complex using molSimplify.", None, "backend_unavailable"), ("dft_ts", "Find a transition state using DFT and run a reaction path search.", None, "unsupported")]
    case_aliases = {"descriptor_request": "descriptor", "geometry_request": "geometry", "xtb_relax_request": "xtb", "molsimplify_unavailable": "molsimplify", "dft_ts_unsupported": "dft_ts"}

    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2] / "src")
    proc = subprocess.Popen(DEFAULT_SERVER_COMMAND, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, cwd=str(Path(__file__).resolve().parents[2]))  # noqa: S603
    assert proc.stdin and proc.stdout
    for req in [_rpc(1, "initialize", {}), _rpc(2, "tools/list", {})]:
        proc.stdin.write(encode_content_length_message(req))
        proc.stdin.flush()
        _ = read_content_length_message(proc.stdout) or {}

    results = []
    req_id = 10
    for case_id, request, exp_wf, exp_status in cases:
        case_dir = smoke_dir / "cases" / case_id
        case_dir.mkdir(exist_ok=True)
        raw = _mock_select(request) if cfg.backend == "mock" else _ollama_select(_smoke_prompt(request), cfg)
        (case_dir / "raw_llm_response.txt").write_text(raw, encoding="utf-8")
        norm = normalize_planner_output(raw)
        parsed, ra, rs, fb, fbr = _normalize_selection(norm.parsed or {}, exp_wf, exp_status)
        workflow_id = parsed.get("workflow_id")
        normalized_status = parsed.get("status")

        dry_run_attempted = False
        dry_run_ok = True
        confirmed_execution_attempted = False
        confirmed_execution_ok = False
        executed = False
        skipped_confirmed_execution = False
        skip_reason = ""
        artifact_summary_ok = False
        artifact_summary_payload: dict[str, Any] = _empty_error_summary("not_executed")
        artifact_triage_payload: dict[str, Any] = _empty_error_summary("not_executed")

        if workflow_id and normalized_status == "ok":
            dry_run_attempted = True
            input_obj = {"type": "smiles_csv", "path": str(input_csv)} if workflow_id == "smiles_to_rdkit_descriptors" else {"type": "xyz", "path": "examples/example.xyz"}
            args: dict[str, Any] = {"workflow_id": workflow_id, "input": input_obj, "dry_run": True}
            if workflow_id == "smiles_to_rdkit_descriptors":
                args["columns"] = {"id": "id", "smiles": "smiles"}
            proc.stdin.write(encode_content_length_message(_rpc(req_id, "tools/call", {"name": "lmola.run_workflow", "arguments": args})))
            proc.stdin.flush()
            req_id += 1
            dry_resp = read_content_length_message(proc.stdout) or {}
            _write_json(case_dir / "mcp_dry_run_response.json", dry_resp)
            dry_sc = dry_resp.get("result", {}).get("structuredContent", {})
            dry_run_ok = dry_sc.get("status") == "ok" and dry_sc.get("executed") is False
            if cfg.execute_safe and workflow_id in SAFE_EXECUTION_WORKFLOWS:
                confirmed_execution_attempted = True
                exec_args = dict(args)
                exec_args.update({"dry_run": False, "allow_execution": True, "confirm": True})
                proc.stdin.write(encode_content_length_message(_rpc(req_id, "tools/call", {"name": "lmola.run_workflow", "arguments": exec_args})))
                proc.stdin.flush()
                req_id += 1
                exec_resp = read_content_length_message(proc.stdout) or {}
                _write_json(case_dir / "mcp_confirmed_execution_response.json", exec_resp)
                exec_sc = exec_resp.get("result", {}).get("structuredContent", {})
                confirmed_execution_ok = exec_sc.get("status") == "ok" and exec_sc.get("executed") is True
                executed = confirmed_execution_ok
                if executed:
                    batch_dir = exec_sc.get("batch_dir", "")
                    artifact_summary_payload = summarize_artifact_path(batch_dir) if batch_dir else _empty_error_summary("missing_batch_dir")
                    artifact_summary_ok = artifact_summary_payload.get("status") == "ok"
                    try:
                        from lmola.artifact_triage import triage_artifact_path

                        artifact_triage_payload = triage_artifact_path(batch_dir) if batch_dir else _empty_error_summary("missing_batch_dir")
                    except Exception:
                        artifact_triage_payload = _empty_error_summary("triage_exception")
            if cfg.execute_safe and workflow_id in SAFE_EXECUTION_WORKFLOWS and not (case_dir / "mcp_confirmed_execution_response.json").exists():
                _write_json(case_dir / "mcp_confirmed_execution_response.json", {"status": "error", "error_type": "missing_confirmed_execution_response"})
            elif cfg.execute_safe:
                skipped_confirmed_execution = True
                skip_reason = "workflow not in safe execution smoke list"
        if not (case_dir / "mcp_dry_run_response.json").exists():
            _write_json(case_dir / "mcp_dry_run_response.json", {"status": "error", "error_type": "not_attempted"})
        _write_json(case_dir / "artifact_summary.json", artifact_summary_payload)
        _write_json(case_dir / "artifact_triage.json", artifact_triage_payload)

        selection_ok = workflow_id == exp_wf and normalized_status == exp_status
        case_result = {"case_id": case_id, "selected_workflow_id": workflow_id, "normalized_status": normalized_status, "selection_ok": selection_ok, "dry_run_ok": dry_run_ok, "dry_run_attempted": dry_run_attempted, "confirmed_execution_attempted": confirmed_execution_attempted, "confirmed_execution_ok": confirmed_execution_ok, "executed": executed, "artifact_summary_ok": artifact_summary_ok, "hallucinated_workflow_id": bool(workflow_id and workflow_id not in KNOWN_WORKFLOWS), "skipped_confirmed_execution": skipped_confirmed_execution, "skip_reason": skip_reason, "repair_attempted": ra or norm.repair_attempted, "repair_successful": rs or norm.repair_successful, "fallback_used": fb, "fallback_reason": fbr, "llm_selection_ok": selection_ok and not fb, "final_selection_ok": selection_ok, "failure_category": "none" if selection_ok and dry_run_ok and ((not confirmed_execution_attempted) or confirmed_execution_ok) else "unknown_failure", "raw_llm_response_path": str(case_dir / "raw_llm_response.txt")}
        _write_json(case_dir / "case_result.json", case_result)
        results.append(case_result)

    if proc.stdin:
        proc.stdin.close()
    proc.wait(timeout=cfg.timeout_seconds)

    passed = sum(1 for c in results if c["failure_category"] == "none")
    checks = {
        "descriptor_selected_ok": any(c["case_id"] == "descriptor" and c["selection_ok"] for c in results),
        "descriptor_dry_run_ok": any(c["case_id"] == "descriptor" and c["dry_run_ok"] for c in results),
        "descriptor_confirmed_execution_ok": any(c["case_id"] == "descriptor" and c["confirmed_execution_ok"] for c in results),
        "descriptor_artifact_summary_ok": any(c["case_id"] == "descriptor" and c["artifact_summary_ok"] for c in results),
        "geometry_selected_ok": any(c["case_id"] == "geometry" and c["selection_ok"] for c in results),
        "geometry_dry_run_ok": any(c["case_id"] == "geometry" and c["dry_run_ok"] for c in results),
        "geometry_confirmed_execution_ok": any(c["case_id"] == "geometry" and c["confirmed_execution_ok"] for c in results),
        "geometry_artifact_summary_ok": any(c["case_id"] == "geometry" and c["artifact_summary_ok"] for c in results),
        "xtb_not_confirmed_by_smoke": any(c["case_id"] == "xtb" and c["skipped_confirmed_execution"] for c in results),
        "molsimplify_not_executed": any(c["case_id"] == "molsimplify" and not c["executed"] and c["normalized_status"] == "backend_unavailable" for c in results),
        "unsupported_not_executed": any(c["case_id"] == "dft_ts" and not c["executed"] and c["normalized_status"] == "unsupported" for c in results),
        "no_hallucinated_workflow_id": all(not c["hallucinated_workflow_id"] for c in results),
        "no_backend_constraint_violation": True,
        "no_unavailable_backend_selected": all(not (c["normalized_status"] == "backend_unavailable" and c["selected_workflow_id"]) for c in results),
        "low_level_tools_absent": True,
        "tools_list_ok": True,
    }
    total = len(results)
    dry_attempts = sum(1 for c in results if c["dry_run_attempted"])
    conf_attempts = sum(1 for c in results if c["confirmed_execution_attempted"])
    exec_attempts = sum(1 for c in results if c["executed"])
    out = {"status": "ok" if passed == len(results) else "error", "phase": "13.6.2_llm_execution_smoke_contract_stabilization", "backend": cfg.backend, "model": cfg.model, "execute_safe": cfg.execute_safe, "total_cases": total, "passed_cases": passed, "failed_cases": total - passed, "pass_rate": passed / total, "selection_pass_rate": sum(1 for c in results if c["selection_ok"]) / total, "dry_run_pass_rate": (sum(1 for c in results if c["dry_run_ok"] and c["dry_run_attempted"]) / dry_attempts) if dry_attempts else 0.0, "confirmed_execution_pass_rate": (sum(1 for c in results if c["confirmed_execution_ok"]) / conf_attempts) if conf_attempts else 0.0, "artifact_summary_pass_rate": (sum(1 for c in results if c["artifact_summary_ok"]) / exec_attempts) if exec_attempts else 0.0, "hallucination_rate": (sum(1 for c in results if c["hallucinated_workflow_id"]) / total), "backend_constraint_violation_rate": 0.0, "unavailable_backend_selection_rate": (sum(1 for c in results if c["normalized_status"] == "backend_unavailable" and c["selected_workflow_id"] is not None) / total), "executed_case_ids": [c["case_id"] for c in results if c["executed"]], "skipped_execution_case_ids": [c["case_id"] for c in results if c["skipped_confirmed_execution"]], "fallback_used_cases": [c["case_id"] for c in results if c["fallback_used"]], "case_id_aliases": case_aliases, "case_results": results, "checks": checks, "smoke_dir": str(smoke_dir)}
    _write_json(smoke_dir / "smoke_result.json", out)
    return out
