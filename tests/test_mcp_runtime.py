from __future__ import annotations

from pathlib import Path

from lmola.mcp_runtime import call_mcp_tool, handle_jsonrpc_message, list_mcp_tools_runtime


def test_runtime_tools_allowlist_shape() -> None:
    tools = list_mcp_tools_runtime()
    names = {t["name"] for t in tools}
    assert "lmola.list_workflows" in names
    assert "lmola.inspect_workflow" in names
    assert "lmola.validate_workflow" in names
    assert "lmola.plan_workflow" in names
    assert "lmola.run_workflow" not in names
    assert "lmola.relax_structure_xtb" not in names
    assert "lmola.generate_small_molecule_rdkit" not in names
    plan_tool = next(t for t in tools if t["name"] == "lmola.plan_workflow")
    meta = plan_tool.get("_meta", {}).get("lmola", {})
    assert meta.get("dry_run_only") is True
    assert meta.get("executes_workflow") is False
    assert meta.get("writes_batch_artifacts") is False
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

    assert call_mcp_tool("lmola.run_workflow", {"workflow_id": "smiles_to_xtb_relax"})["error_type"] == "tool_not_allowed"
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


def test_jsonrpc_minimal_methods() -> None:
    init = handle_jsonrpc_message({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert init and init["result"]["serverInfo"]["name"] == "lmola-mcp-runtime"
    listed = handle_jsonrpc_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    assert listed and "tools" in listed["result"]
    assert "runtime_phase" in listed["result"]
    called = handle_jsonrpc_message({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "lmola.list_workflows", "arguments": {"compact": True}}})
    assert called and called["result"]["structuredContent"]["status"] == "ok"
    unknown_method = handle_jsonrpc_message({"jsonrpc": "2.0", "id": 4, "method": "x/unknown", "params": {}})
    assert unknown_method and unknown_method["error"]["code"] == -32601
