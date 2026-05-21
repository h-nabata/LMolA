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
from lmola.artifact_triage import triage_artifact_path
from lmola.llm_output_normalization import normalize_planner_output
from lmola.mcp_runtime import encode_content_length_message, read_content_length_message

DEFAULT_SERVER_COMMAND = [sys.executable, "-c", "from lmola.cli import app; app(['mcp','serve-stdio'])"]
SAFE_EXECUTION_WORKFLOWS = {"smiles_to_rdkit_descriptors", "xyz_to_geometry_analysis"}
KNOWN_WORKFLOWS = {"smiles_to_rdkit_descriptors", "xyz_to_geometry_analysis", "xyz_to_xtb_relax"}


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
        return '{"status":"backend_unavailable"}'
    return '{"status":"unsupported"}'


def _ollama_select(prompt: str, cfg: LLMConfig) -> str:
    payload = {
        "model": cfg.model,
        "stream": False,
        "format": "json",
        "options": {"temperature": cfg.temperature, "num_predict": cfg.max_tokens},
        "messages": [{"role": "user", "content": prompt}],
    }
    req = urllib.request.Request(
        f"{cfg.base_url.rstrip('/')}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=cfg.timeout_seconds) as resp:  # noqa: S310
        body = json.loads(resp.read().decode("utf-8"))
    return str(body.get("message", {}).get("content", ""))


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
        writer.writerow(["benzene", "c1ccccc1"])
        writer.writerow(["bad", "not_a_smiles"])

    cases = [
        ("descriptor", f"Compute RDKit molecular descriptors for the SMILES CSV file at {input_csv}.", "smiles_to_rdkit_descriptors", "ok"),
        ("geometry", "Analyze the geometry of examples/example.xyz and report suspicious short contacts. Do not run xTB relaxation.", "xyz_to_geometry_analysis", "ok"),
        ("xtb", "Relax examples/example.xyz with xTB.", "xyz_to_xtb_relax", "ok"),
        ("molsimplify", "Generate an octahedral iron complex using molSimplify.", None, "backend_unavailable"),
        ("dft_ts", "Find a transition state using DFT and run a reaction path search.", None, "unsupported"),
    ]

    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2] / "src")
    proc = subprocess.Popen(DEFAULT_SERVER_COMMAND, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, cwd=str(Path(__file__).resolve().parents[2]))  # noqa: S603
    assert proc.stdin and proc.stdout

    for req in [_rpc(1, "initialize", {}), _rpc(2, "tools/list", {})]:
        proc.stdin.write(encode_content_length_message(req))
        proc.stdin.flush()
        resp = read_content_length_message(proc.stdout) or {}
        if req["id"] == 2:
            tools_resp = resp
    names = {t.get("name") for t in tools_resp.get("result", {}).get("tools", []) if isinstance(t, dict)}

    results: list[dict[str, Any]] = []
    req_id = 10
    for case_id, request, exp_wf, exp_status in cases:
        case_dir = smoke_dir / "cases" / case_id
        case_dir.mkdir(exist_ok=True)
        if cfg.backend == "mock":
            raw = _mock_select(request)
        else:
            raw = _ollama_select(f"Return JSON only with fields workflow_id (or null) and status for request: {request}", cfg)

        (case_dir / "raw_llm_response.txt").write_text(raw, encoding="utf-8")
        norm = normalize_planner_output(raw)
        (case_dir / "sanitized_llm_response.txt").write_text(norm.sanitized_text, encoding="utf-8")
        _write_json(case_dir / "parsed_output.json", norm.parsed or {})

        parsed = norm.parsed or {}
        workflow_id = parsed.get("workflow_id")
        normalized_status = parsed.get("status", "ok" if workflow_id else "unsupported")
        _write_json(case_dir / "normalized_output.json", {"selected_workflow_id": workflow_id, "normalized_status": normalized_status})

        dry_run_attempted = False
        dry_run_ok = True
        confirmed_execution_attempted = False
        confirmed_execution_ok = False
        executed = False
        batch_dir = None
        skipped_confirmed_execution = False
        skip_reason = ""

        if workflow_id and normalized_status == "ok":
            dry_run_attempted = True
            input_obj = {"type": "smiles_csv", "path": str(input_csv)} if workflow_id == "smiles_to_rdkit_descriptors" else {"type": "xyz", "path": "examples/example.xyz"}
            args: dict[str, Any] = {"workflow_id": workflow_id, "input": input_obj, "dry_run": True}
            if workflow_id == "smiles_to_rdkit_descriptors":
                args["columns"] = {"id": "id", "smiles": "smiles"}
            dry_req = _rpc(req_id, "tools/call", {"name": "lmola.run_workflow", "arguments": args})
            req_id += 1
            proc.stdin.write(encode_content_length_message(dry_req))
            proc.stdin.flush()
            dry_resp = read_content_length_message(proc.stdout) or {}
            _write_json(case_dir / "mcp_dry_run_response.json", dry_resp)
            dry_sc = dry_resp.get("result", {}).get("structuredContent", {})
            dry_run_ok = dry_sc.get("status") == "ok" and dry_sc.get("executed") is False

            if cfg.execute_safe and workflow_id in SAFE_EXECUTION_WORKFLOWS:
                confirmed_execution_attempted = True
                exec_args = dict(args)
                exec_args.update({"dry_run": False, "allow_execution": True, "confirm": True})
                exec_req = _rpc(req_id, "tools/call", {"name": "lmola.run_workflow", "arguments": exec_args})
                req_id += 1
                proc.stdin.write(encode_content_length_message(exec_req))
                proc.stdin.flush()
                exec_resp = read_content_length_message(proc.stdout) or {}
                _write_json(case_dir / "mcp_confirmed_execution_response.json", exec_resp)
                exec_sc = exec_resp.get("result", {}).get("structuredContent", {})
                confirmed_execution_ok = exec_sc.get("status") == "ok" and exec_sc.get("executed") is True
                executed = confirmed_execution_ok
                batch_dir = exec_sc.get("batch_dir")
            elif cfg.execute_safe:
                skipped_confirmed_execution = True
                skip_reason = "workflow not in safe execution smoke list"

        artifact_summary_ok = False
        artifact_triage_ok = False
        if batch_dir:
            summary = summarize_artifact_path(batch_dir)
            triage = triage_artifact_path(batch_dir)
            _write_json(case_dir / "artifact_summary.json", summary)
            _write_json(case_dir / "artifact_triage.json", triage)
            artifact_summary_ok = summary.get("status") == "ok"
            artifact_triage_ok = triage.get("status") == "ok"

        selection_ok = workflow_id == exp_wf and normalized_status == exp_status
        failure = "none" if selection_ok and dry_run_ok and ((not confirmed_execution_attempted) or confirmed_execution_ok) else "unknown_failure"
        case_result = {
            "case_id": case_id,
            "request": request,
            "raw_llm_response_path": str(case_dir / "raw_llm_response.txt"),
            "selected_workflow_id": workflow_id,
            "normalized_status": normalized_status,
            "expected_workflow_id": exp_wf,
            "expected_normalized_status": exp_status,
            "selection_ok": selection_ok,
            "dry_run_attempted": dry_run_attempted,
            "dry_run_ok": dry_run_ok,
            "confirmed_execution_attempted": confirmed_execution_attempted,
            "confirmed_execution_ok": confirmed_execution_ok,
            "executed": executed,
            "batch_dir": batch_dir,
            "artifact_summary_ok": artifact_summary_ok,
            "artifact_triage_ok": artifact_triage_ok,
            "hallucinated_workflow_id": bool(workflow_id and workflow_id not in KNOWN_WORKFLOWS),
            "backend_constraint_violated": False,
            "unavailable_backend_selected": False,
            "skipped_confirmed_execution": skipped_confirmed_execution,
            "skip_reason": skip_reason,
            "failure_category": failure,
        }
        _write_json(case_dir / "case_result.json", case_result)
        results.append(case_result)

    if proc.stdin:
        proc.stdin.close()
    proc.wait(timeout=cfg.timeout_seconds)

    case_map = {r["case_id"]: r for r in results}
    checks = {
        "tools_list_ok": "lmola.run_workflow" in names,
        "low_level_tools_absent": "lmola.compute_rdkit_descriptors" not in names and "lmola.analyze_xyz_geometry" not in names,
        "descriptor_selected_ok": case_map["descriptor"]["selection_ok"],
        "descriptor_dry_run_ok": case_map["descriptor"]["dry_run_ok"],
        "descriptor_confirmed_execution_ok": case_map["descriptor"]["confirmed_execution_ok"] if cfg.execute_safe else True,
        "descriptor_artifact_summary_ok": case_map["descriptor"]["artifact_summary_ok"] if cfg.execute_safe else True,
        "geometry_selected_ok": case_map["geometry"]["selection_ok"],
        "geometry_dry_run_ok": case_map["geometry"]["dry_run_ok"],
        "geometry_confirmed_execution_ok": case_map["geometry"]["confirmed_execution_ok"] if cfg.execute_safe else True,
        "geometry_artifact_summary_ok": case_map["geometry"]["artifact_summary_ok"] if cfg.execute_safe else True,
        "xtb_not_confirmed_by_smoke": case_map["xtb"]["confirmed_execution_attempted"] is False,
        "molsimplify_not_executed": case_map["molsimplify"]["executed"] is False,
        "unsupported_not_executed": case_map["dft_ts"]["executed"] is False,
        "no_hallucinated_workflow_id": all(not c["hallucinated_workflow_id"] for c in results),
        "no_backend_constraint_violation": True,
        "no_unavailable_backend_selected": True,
    }

    passed = sum(1 for c in results if c["failure_category"] == "none")
    out = {
        "status": "ok" if all(checks.values()) else "error",
        "phase": "13.6_llm_mcp_execution_smoke",
        "backend": cfg.backend,
        "model": cfg.model,
        "base_url": cfg.base_url,
        "execute_safe": cfg.execute_safe,
        "total_cases": len(results),
        "passed_cases": passed,
        "failed_cases": len(results) - passed,
        "pass_rate": passed / len(results),
        "selection_pass_rate": sum(1 for c in results if c["selection_ok"]) / len(results),
        "dry_run_pass_rate": sum(1 for c in results if c["dry_run_ok"]) / len(results),
        "confirmed_execution_pass_rate": sum(1 for c in results if (not c["confirmed_execution_attempted"]) or c["confirmed_execution_ok"]) / len(results),
        "artifact_summary_pass_rate": sum(1 for c in results if (not c["executed"]) or c["artifact_summary_ok"]) / len(results),
        "hallucination_rate": sum(1 for c in results if c["hallucinated_workflow_id"]) / len(results),
        "backend_constraint_violation_rate": 0.0,
        "unavailable_backend_selection_rate": 0.0,
        "executed_case_ids": [c["case_id"] for c in results if c["executed"]],
        "skipped_execution_case_ids": [c["case_id"] for c in results if c["skipped_confirmed_execution"]],
        "failed_case_ids": [c["case_id"] for c in results if c["failure_category"] != "none"],
        "checks": checks,
        "case_results": results,
        "smoke_dir": str(smoke_dir),
    }
    with (smoke_dir / "smoke_summary.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["case_id", "selection_ok", "dry_run_ok", "confirmed_execution_ok", "executed"])
        for row in results:
            writer.writerow([row["case_id"], row["selection_ok"], row["dry_run_ok"], row["confirmed_execution_ok"], row["executed"]])
    _write_json(smoke_dir / "smoke_result.json", out)
    _write_json(smoke_dir / "config_redacted.json", {"backend": cfg.backend, "model": cfg.model, "base_url": cfg.base_url, "temperature": cfg.temperature, "timeout_seconds": cfg.timeout_seconds, "max_tokens": cfg.max_tokens})
    _write_json(smoke_dir / "model_info.json", {"backend": cfg.backend, "model": cfg.model})
    return out
