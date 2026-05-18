from __future__ import annotations

from pathlib import Path

from lmola.workflows.schemas import WorkflowExecutionResult, WorkflowSummary
from lmola.mcp_runtime import (
    MCP_EXECUTION_ALLOWLIST,
    call_mcp_tool,
    decode_content_length_message,
    encode_content_length_message,
    handle_jsonrpc_message,
    list_mcp_tools_runtime,
    read_content_length_message,
)


def test_runtime_tools_allowlist_shape() -> None:
    tools = list_mcp_tools_runtime()
    names = {t["name"] for t in tools}
    assert "lmola.list_workflows" in names
    assert "lmola.inspect_workflow" in names
    assert "lmola.validate_workflow" in names
    assert "lmola.plan_workflow" in names
    assert "lmola.run_workflow" in names
    assert "lmola.relax_structure_xtb" not in names
    assert "lmola.generate_small_molecule_rdkit" not in names
    plan_tool = next(t for t in tools if t["name"] == "lmola.plan_workflow")
    meta = plan_tool.get("_meta", {}).get("lmola", {})
    assert meta.get("dry_run_only") is True
    assert meta.get("executes_workflow") is False
    assert meta.get("writes_batch_artifacts") is False
    run_tool = next(t for t in tools if t["name"] == "lmola.run_workflow")
    run_meta = run_tool.get("_meta", {}).get("lmola", {})
    assert run_meta.get("requires_confirmation") is True
    assert run_meta.get("side_effects") is True
    assert run_meta.get("writes_batch_artifacts") is True
    assert sorted(run_meta.get("mcp_execution_allowlist", [])) == sorted(MCP_EXECUTION_ALLOWLIST)
    notes = run_meta.get("safe_execution_notes", "")
    assert "Phase 11.5" not in notes
    assert "allowlisted workflows" in notes
    assert "dry_run=false" in notes
    for t in tools:
        assert "name" in t and "description" in t and "inputSchema" in t
        assert t.get("_meta", {}).get("lmola", {}).get("runtime_enabled") is True


def test_call_readonly_tools_and_errors(monkeypatch) -> None:
    monkeypatch.setenv("LMOLA_LLM_ENABLED", "1")
    monkeypatch.setenv("LMOLA_LLM_BACKEND", "mock")
    assert call_mcp_tool("lmola.list_workflows", {"compact": True})["status"] == "ok"
    inspect = call_mcp_tool("lmola.inspect_workflow", {"workflow_id": "smiles_to_xtb_relax"})
    assert inspect["status"] == "ok"
    assert inspect["workflow"]["workflow_id"] == "smiles_to_xtb_relax"
    bad = call_mcp_tool("lmola.inspect_workflow", {"workflow_id": "bad"})
    assert bad["status"] == "error"

    assert call_mcp_tool("lmola.get_planner_context", {})["planner_context"]["schema_version"] == "lmola.planner_context.v1"
    assert call_mcp_tool("lmola.get_schema_bundle", {})["schema_bundle"]["schema_version"] == "lmola.schema_bundle.v1"

    valid = call_mcp_tool(
        "lmola.validate_workflow",
        {
            "workflow_id": "smiles_to_xtb_relax",
            "input": {"type": "smiles_csv", "path": "examples/smiles_list.csv"},
            "columns": {"id": "id", "smiles": "smiles"},
        },
    )
    assert valid["status"] == "ok"
    assert [s["tool"] for s in valid["canonical_workflow_json"]["steps"]] == [
        "generate_small_molecule_rdkit",
        "validate_structure_ase",
        "relax_structure_xtb",
    ]

    planned = call_mcp_tool("lmola.plan_workflow", {"request": "Generate structures from examples/smiles_list.csv and relax them with xTB."})
    assert planned["status"] == "ok"
    planning = planned["planning_result"]
    assert planning["selected_workflow_id"] == "smiles_to_xtb_relax"
    assert planning["executed"] is False
    assert planning["batch_dir"] is None
    assert [s["tool"] for s in planning["canonical_workflow_json"]["steps"]] == [
        "generate_small_molecule_rdkit",
        "validate_structure_ase",
        "relax_structure_xtb",
    ]

    unsupported = call_mcp_tool("lmola.plan_workflow", {"request": "Find a transition state using DFT and run NEB."})
    assert unsupported["status"] == "ok"
    assert unsupported["planning_result"]["normalized_status"] == "unsupported"

    invalid = call_mcp_tool("lmola.validate_workflow", {"workflow_id": "smiles_to_xtb_relax", "input": {"type": "xyz", "value": "x"}})
    assert invalid["status"] == "error"
    assert invalid["error_type"] == "validation_error"

    invalid_request = call_mcp_tool("lmola.plan_workflow", {"request": ""})
    assert invalid_request["status"] == "error"
    assert invalid_request["error_type"] == "invalid_arguments"

    run_dry = call_mcp_tool(
        "lmola.run_workflow",
        {"workflow_id": "smiles_to_xtb_relax", "input": {"type": "smiles_csv", "path": "examples/smiles_list.csv"}, "columns": {"id": "id", "smiles": "smiles"}},
    )
    assert run_dry["status"] == "ok"
    assert run_dry["dry_run"] is True
    assert run_dry["executed"] is False
    assert run_dry["canonical_workflow_json"]["workflow_id"] == "smiles_to_xtb_relax"
    assert Path(run_dry["audit_path"]).exists()
    assert call_mcp_tool("lmola.relax_structure_xtb", {"input_structure": "examples/example.xyz"})["error_type"] == "tool_not_allowed"


def test_runtime_plan_validate_do_not_create_batch_dirs(monkeypatch) -> None:
    monkeypatch.setenv("LMOLA_LLM_ENABLED", "1")
    monkeypatch.setenv("LMOLA_LLM_BACKEND", "mock")
    outputs = Path("outputs")
    before = len(list(outputs.glob("batch_*"))) if outputs.exists() else 0
    call_mcp_tool("lmola.plan_workflow", {"request": "Generate structures from examples/smiles_list.csv and relax them with xTB."})
    call_mcp_tool(
        "lmola.validate_workflow",
        {
            "workflow_id": "smiles_to_xtb_relax",
            "input": {"type": "smiles_csv", "path": "examples/smiles_list.csv"},
            "columns": {"id": "id", "smiles": "smiles"},
        },
    )
    after = len(list(outputs.glob("batch_*"))) if outputs.exists() else 0
    assert after == before


def test_run_workflow_dryrun_and_denied_do_not_create_mcp_runs() -> None:
    mcp_runs = Path("outputs/mcp_runs")
    before = len(list(mcp_runs.glob("batch_*"))) if mcp_runs.exists() else 0
    call_mcp_tool(
        "lmola.run_workflow",
        {"workflow_id": "smiles_to_xtb_relax", "input": {"type": "smiles_csv", "path": "examples/smiles_list.csv"}},
    )
    call_mcp_tool(
        "lmola.run_workflow",
        {"workflow_id": "smiles_to_xtb_relax", "input": {"type": "smiles_csv", "path": "examples/smiles_list.csv"}, "dry_run": False},
    )
    after = len(list(mcp_runs.glob("batch_*"))) if mcp_runs.exists() else 0
    assert after == before


def test_run_workflow_confirmation_and_allowlist_errors() -> None:
    no_confirm = call_mcp_tool(
        "lmola.run_workflow",
        {"workflow_id": "smiles_to_xtb_relax", "input": {"type": "smiles_csv", "path": "examples/smiles_list.csv"}, "dry_run": False, "allow_execution": True},
    )
    assert no_confirm["error_type"] == "confirmation_required"
    no_allow = call_mcp_tool(
        "lmola.run_workflow",
        {"workflow_id": "smiles_to_xtb_relax", "input": {"type": "smiles_csv", "path": "examples/smiles_list.csv"}, "dry_run": False, "confirm": True},
    )
    assert no_allow["error_type"] == "execution_not_allowed"
    blocked = call_mcp_tool(
        "lmola.run_workflow",
        {"workflow_id": "not_real_workflow", "input": {"type": "smiles_csv", "path": "examples/smiles_list.csv"}, "dry_run": False, "allow_execution": True, "confirm": True},
    )
    assert blocked["error_type"] in {"workflow_not_allowlisted", "validation_error"}


def test_run_workflow_execution_path_with_monkeypatched_runner(monkeypatch, tmp_path: Path) -> None:
    def _fake_run(req, output_root=None):  # noqa: ANN001
        run_dir = (output_root or tmp_path) / "batch_fake"
        run_dir.mkdir(parents=True, exist_ok=True)
        return WorkflowExecutionResult(
            status="ok",
            message="ok",
            batch_dir=str(run_dir),
            summary_csv=str(run_dir / "summary.csv"),
            summary_json=str(run_dir / "summary.json"),
            summary=WorkflowSummary(batch_id="batch_fake", workflow_id=req.workflow_id, item_count=1, ok_count=1, error_count=0),
        )

    monkeypatch.setattr("lmola.mcp_runtime.run_workflow_request", _fake_run)
    out_root = Path("/tmp/lmola_mcp_runs") / "test_run_workflow_execution_path"
    result = call_mcp_tool(
        "lmola.run_workflow",
        {
            "workflow_id": "smiles_to_3d_rdkit",
            "input": {"type": "smiles", "value": "CCO"},
            "dry_run": False,
            "allow_execution": True,
            "confirm": True,
            "output_root": str(out_root),
        },
    )
    assert result["status"] == "ok"
    assert result["executed"] is True
    assert Path(result["audit_path"]).exists()


def test_jsonrpc_minimal_methods() -> None:
    init = handle_jsonrpc_message({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert init and init["result"]["serverInfo"]["name"] == "lmola"
    assert init["result"]["protocolVersion"] == "2024-11-05"
    listed = handle_jsonrpc_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    assert listed and "tools" in listed["result"]
    assert "runtime_phase" in listed["result"]
    assert "lmola.run_workflow" in {t["name"] for t in listed["result"]["tools"]}
    assert "lmola.relax_structure_xtb" not in {t["name"] for t in listed["result"]["tools"]}
    called = handle_jsonrpc_message({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "lmola.list_workflows", "arguments": {"compact": True}}})
    assert called and called["result"]["structuredContent"]["status"] == "ok"
    assert called["result"]["isError"] is False
    unknown_method = handle_jsonrpc_message({"jsonrpc": "2.0", "id": 4, "method": "x/unknown", "params": {}})
    assert unknown_method and unknown_method["error"]["code"] == -32601
    bad_params = handle_jsonrpc_message({"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": []})
    assert bad_params and bad_params["error"]["code"] == -32602
    unknown_tool = handle_jsonrpc_message({"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "lmola.relax_structure_xtb", "arguments": {}}})
    assert unknown_tool and unknown_tool["error"]["code"] == -32601


def test_jsonrpc_run_workflow_safety_paths() -> None:
    dry = handle_jsonrpc_message(
        {"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "lmola.run_workflow", "arguments": {"workflow_id": "smiles_to_xtb_relax", "input": {"type": "smiles_csv", "path": "examples/smiles_list.csv"}}}}
    )
    assert dry and dry["result"]["structuredContent"]["executed"] is False
    assert dry["result"]["structuredContent"]["batch_dir"] is None
    no_confirm = handle_jsonrpc_message(
        {"jsonrpc": "2.0", "id": 8, "method": "tools/call", "params": {"name": "lmola.run_workflow", "arguments": {"workflow_id": "smiles_to_xtb_relax", "input": {"type": "smiles_csv", "path": "examples/smiles_list.csv"}, "dry_run": False, "allow_execution": True}}}
    )
    assert no_confirm and no_confirm["result"]["isError"] is True
    assert no_confirm["result"]["structuredContent"]["error_type"] == "confirmation_required"


def test_content_length_roundtrip() -> None:
    payload = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    encoded = encode_content_length_message(payload)
    decoded = decode_content_length_message(encoded)
    assert decoded == payload
    import io

    msg = read_content_length_message(io.BytesIO(encoded))
    assert msg == payload
