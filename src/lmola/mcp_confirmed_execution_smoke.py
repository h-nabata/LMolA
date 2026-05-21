from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from lmola.mcp_runtime import encode_content_length_message, read_content_length_message

DEFAULT_SERVER_COMMAND = [sys.executable, "-c", "from lmola.cli import app; app(['mcp','serve-stdio'])"]


def _rpc(req_id: int, method: str, params: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def run_mcp_confirmed_execution_smoke(*, timeout_seconds: float = 20.0, server_command: list[str] | None = None) -> dict[str, Any]:
    smoke_dir = Path("outputs/mcp_execution_smoke") / f"smoke_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"
    smoke_dir.mkdir(parents=True, exist_ok=True)

    input_csv = smoke_dir / "smiles_input.csv"
    with input_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "smiles"])
        writer.writerow(["ethanol", "CCO"])
        writer.writerow(["benzene", "c1ccccc1"])
        writer.writerow(["bad_smiles", "not_a_smiles"])

    requests = [
        _rpc(1, "initialize", {}),
        _rpc(2, "tools/list", {}),
        _rpc(3, "tools/call", {"name": "lmola.run_workflow", "arguments": {"workflow_id": "smiles_to_rdkit_descriptors", "input": {"type": "smiles_csv", "path": str(input_csv)}, "columns": {"id": "id", "smiles": "smiles"}, "dry_run": True}}),
        _rpc(4, "tools/call", {"name": "lmola.run_workflow", "arguments": {"workflow_id": "smiles_to_rdkit_descriptors", "input": {"type": "smiles_csv", "path": str(input_csv)}, "columns": {"id": "id", "smiles": "smiles"}, "dry_run": False, "confirm": True}}),
        _rpc(5, "tools/call", {"name": "lmola.run_workflow", "arguments": {"workflow_id": "smiles_to_rdkit_descriptors", "input": {"type": "smiles_csv", "path": str(input_csv)}, "columns": {"id": "id", "smiles": "smiles"}, "dry_run": False, "allow_execution": True}}),
        _rpc(6, "tools/call", {"name": "lmola.run_workflow", "arguments": {"workflow_id": "smiles_to_rdkit_descriptors", "input": {"type": "smiles_csv", "path": str(input_csv)}, "columns": {"id": "id", "smiles": "smiles"}, "dry_run": False, "allow_execution": True, "confirm": True, "confirmation_text": "I confirm execution of this allowlisted local descriptor workflow."}}),
        _rpc(7, "tools/call", {"name": "lmola.summarize_artifacts", "arguments": {"path": ""}}),
        _rpc(8, "tools/call", {"name": "lmola.triage_artifacts", "arguments": {"path": ""}}),
        _rpc(9, "tools/call", {"name": "lmola.run_workflow", "arguments": {"workflow_id": "xyz_to_geometry_analysis", "input": {"type": "xyz", "path": "examples/example.xyz"}, "dry_run": False, "allow_execution": True, "confirm": True, "confirmation_text": "I confirm execution of this allowlisted local geometry analysis workflow."}}),
        _rpc(10, "tools/call", {"name": "lmola.summarize_artifacts", "arguments": {"path": ""}}),
        _rpc(11, "tools/call", {"name": "lmola.triage_artifacts", "arguments": {"path": ""}}),
        _rpc(12, "tools/call", {"name": "lmola.run_workflow", "arguments": {"workflow_id": "nonexistent_workflow", "input": {"type": "smiles", "value": "CCO"}, "dry_run": False, "allow_execution": True, "confirm": True}}),
        _rpc(13, "tools/call", {"name": "lmola.compute_rdkit_descriptors", "arguments": {}}),
        _rpc(14, "tools/call", {"name": "lmola.analyze_xyz_geometry", "arguments": {}}),
    ]

    responses: list[dict[str, Any]] = []
    by_id: dict[int, dict[str, Any]] = {}
    checks: dict[str, bool] = {k: False for k in ["run_workflow_present", "low_level_tools_absent", "dry_run_safe", "missing_allow_rejected", "missing_confirm_rejected", "descriptor_exec_ok", "descriptor_summary_ok", "descriptor_triage_ok", "geometry_exec_ok", "geometry_summary_ok", "geometry_triage_ok", "fake_workflow_rejected", "low_level_tool_rejected"]}

    env = os.environ.copy()
    src_path = str(Path(__file__).resolve().parents[2] / "src")
    env["PYTHONPATH"] = src_path + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    proc = subprocess.Popen(server_command or DEFAULT_SERVER_COMMAND, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, cwd=str(Path(__file__).resolve().parents[2]))  # noqa: S603
    try:
        assert proc.stdin is not None and proc.stdout is not None
        for req in requests[:6]:
            proc.stdin.write(encode_content_length_message(req))
            proc.stdin.flush()
            resp = read_content_length_message(proc.stdout) or {}
            responses.append(resp)
            by_id[req["id"]] = resp

        tools = by_id[2].get("result", {}).get("tools", [])
        names = {t.get("name") for t in tools if isinstance(t, dict)}
        checks["run_workflow_present"] = "lmola.run_workflow" in names
        checks["low_level_tools_absent"] = "lmola.compute_rdkit_descriptors" not in names and "lmola.analyze_xyz_geometry" not in names
        dry = by_id[3].get("result", {}).get("structuredContent", {})
        checks["dry_run_safe"] = dry.get("status") == "ok" and dry.get("executed") is False
        checks["missing_allow_rejected"] = by_id[4].get("result", {}).get("structuredContent", {}).get("error_type") == "execution_not_allowed"
        checks["missing_confirm_rejected"] = by_id[5].get("result", {}).get("structuredContent", {}).get("error_type") == "confirmation_required"
        dsc = by_id[6].get("result", {}).get("structuredContent", {})
        d_batch = dsc.get("batch_dir")
        checks["descriptor_exec_ok"] = dsc.get("status") == "ok" and dsc.get("executed") is True and bool(dsc.get("batch_dir"))

        requests[6]["params"]["arguments"]["path"] = d_batch
        requests[7]["params"]["arguments"]["path"] = d_batch
        for req in requests[6:9]:
            proc.stdin.write(encode_content_length_message(req))
            proc.stdin.flush()
            resp = read_content_length_message(proc.stdout) or {}
            responses.append(resp)
            by_id[req["id"]] = resp
        desc_sum = by_id[7].get("result", {}).get("structuredContent", {})
        desc_tri = by_id[8].get("result", {}).get("structuredContent", {})
        geo = by_id[9].get("result", {}).get("structuredContent", {})
        g_batch = geo.get("batch_dir")
        requests[9]["params"]["arguments"]["path"] = g_batch
        requests[10]["params"]["arguments"]["path"] = g_batch
        for req in [requests[9], requests[10]]:
            proc.stdin.write(encode_content_length_message(req))
            proc.stdin.flush()
            resp = read_content_length_message(proc.stdout) or {}
            responses.append(resp)
            by_id[req["id"]] = resp
        for req in requests[11:]:
            proc.stdin.write(encode_content_length_message(req))
            proc.stdin.flush()
            resp = read_content_length_message(proc.stdout) or {}
            responses.append(resp)
            by_id[req["id"]] = resp

        checks["descriptor_summary_ok"] = desc_sum.get("status") == "ok" and desc_sum.get("item_count") == 3
        checks["descriptor_triage_ok"] = desc_tri.get("status") == "ok"
        checks["geometry_exec_ok"] = geo.get("status") == "ok" and geo.get("executed") is True and bool(geo.get("batch_dir"))
        gsum = by_id[10].get("result", {}).get("structuredContent", {})
        gtri = by_id[11].get("result", {}).get("structuredContent", {})
        checks["geometry_summary_ok"] = gsum.get("status") == "ok" and gsum.get("item_count") == 1
        checks["geometry_triage_ok"] = gtri.get("status") == "ok"
        fake = by_id[12].get("result", {}).get("structuredContent", {})
        checks["fake_workflow_rejected"] = fake.get("status") == "error"
        low1 = by_id[13].get("error", {}).get("code") == -32601
        low2 = by_id[14].get("error", {}).get("code") == -32601
        checks["low_level_tool_rejected"] = low1 and low2

        if d_batch:
            _write_json(smoke_dir / "descriptor_execution_response.json", dsc)
            _write_json(smoke_dir / "descriptor_artifact_summary.json", desc_sum)
            _write_json(smoke_dir / "descriptor_artifact_triage.json", desc_tri)
        if g_batch:
            _write_json(smoke_dir / "geometry_execution_response.json", geo)
            _write_json(smoke_dir / "geometry_artifact_summary.json", gsum)
            _write_json(smoke_dir / "geometry_artifact_triage.json", gtri)
    finally:
        if proc.stdin:
            proc.stdin.close()
        proc.wait(timeout=timeout_seconds)

    _write_json(smoke_dir / "requests.json", requests)
    _write_json(smoke_dir / "responses.json", responses)

    with (smoke_dir / "smoke_summary.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["check", "passed"])
        for k, v in checks.items():
            writer.writerow([k, str(v).lower()])

    checks["dry_run_no_execution"] = checks["dry_run_safe"]
    checks["descriptor_confirmed_execution_ok"] = checks["descriptor_exec_ok"]
    checks["geometry_confirmed_execution_ok"] = checks["geometry_exec_ok"]
    result = {"status": "ok" if all(v for k,v in checks.items() if k not in {"dry_run_no_execution","descriptor_confirmed_execution_ok","geometry_confirmed_execution_ok"}) else "error", "checks": checks, "smoke_dir": str(smoke_dir)}
    _write_json(smoke_dir / "smoke_result.json", result)
    return result
