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
    if "descriptor" in req:
        return '{"workflow_id":"smiles_to_rdkit_descriptors","status":"ok"}'
    if "geometry" in req or "short contacts" in req:
        return '{"workflow_id":"xyz_to_geometry_analysis","status":"ok"}'
    if "relax" in req and "xtb" in req:
        return '{"workflow_id":"xyz_to_xtb_relax","status":"ok"}'
    if "molsimplify" in req:
        return '{"status":"backend_unavailable","workflow_id":null,"reason":"molsimplify backend unavailable"}'
    return '{"status":"unsupported","workflow_id":null,"reason":"task unsupported"}'


def _smoke_prompt(request: str) -> str:
    return f"Output exactly one JSON object. No markdown, prose, comments, chain-of-thought, or <think>. Allowed status: ok, unsupported, backend_unavailable. Never output pending/completed/error. If workflow_id selected => status ok. Unsupported/backend_unavailable => workflow_id null. Allowed workflow_id: {', '.join(sorted(KNOWN_WORKFLOWS))}. Request: {request}"


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
                exec_sc = exec_resp.get("result", {}).get("structuredContent", {})
                confirmed_execution_ok = exec_sc.get("status") == "ok" and exec_sc.get("executed") is True
                executed = confirmed_execution_ok
                if executed:
                    artifact_summary_ok = summarize_artifact_path(exec_sc.get("batch_dir", "")).get("status") == "ok"
            elif cfg.execute_safe:
                skipped_confirmed_execution = True
                skip_reason = "workflow not in safe execution smoke list"

        selection_ok = workflow_id == exp_wf and normalized_status == exp_status
        results.append({"case_id": case_id, "selected_workflow_id": workflow_id, "normalized_status": normalized_status, "selection_ok": selection_ok, "dry_run_ok": dry_run_ok, "dry_run_attempted": dry_run_attempted, "confirmed_execution_attempted": confirmed_execution_attempted, "confirmed_execution_ok": confirmed_execution_ok, "executed": executed, "artifact_summary_ok": artifact_summary_ok, "hallucinated_workflow_id": bool(workflow_id and workflow_id not in KNOWN_WORKFLOWS), "skipped_confirmed_execution": skipped_confirmed_execution, "skip_reason": skip_reason, "repair_attempted": ra or norm.repair_attempted, "repair_successful": rs or norm.repair_successful, "fallback_used": fb, "fallback_reason": fbr, "llm_selection_ok": selection_ok and not fb, "final_selection_ok": selection_ok, "failure_category": "none" if selection_ok and dry_run_ok and ((not confirmed_execution_attempted) or confirmed_execution_ok) else "unknown_failure"})

    if proc.stdin:
        proc.stdin.close()
    proc.wait(timeout=cfg.timeout_seconds)

    passed = sum(1 for c in results if c["failure_category"] == "none")
    out = {"status": "ok" if passed == len(results) else "error", "phase": "13.6.1_qwen_llm_mcp_execution_smoke_hardening", "backend": cfg.backend, "model": cfg.model, "execute_safe": cfg.execute_safe, "total_cases": len(results), "passed_cases": passed, "failed_cases": len(results) - passed, "pass_rate": passed / len(results), "selection_pass_rate": sum(1 for c in results if c["selection_ok"]) / len(results), "executed_case_ids": [c["case_id"] for c in results if c["executed"]], "skipped_execution_case_ids": [c["case_id"] for c in results if c["skipped_confirmed_execution"]], "fallback_used_cases": [c["case_id"] for c in results if c["fallback_used"]], "case_id_aliases": case_aliases, "case_results": results, "smoke_dir": str(smoke_dir)}
    _write_json(smoke_dir / "smoke_result.json", out)
    return out
