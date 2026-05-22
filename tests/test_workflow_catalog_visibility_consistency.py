from lmola.mcp_runtime import call_mcp_tool, list_mcp_tools_runtime
from lmola.workflows.catalog import list_workflows

LOW_LEVEL_BLOCKLIST = {
    "lmola.xtb_singlepoint",
    "lmola.compare_two_geometries",
    "lmola.compute_rmsd",
    "lmola.count_element_atoms",
    "lmola.split_molecule_by_file_order",
    "lmola.filter_molecules_by_descriptors",
    "lmola.generate_small_molecule_rdkit",
    "lmola.relax_structure_xtb",
    "lmola.validate_structure_ase",
}


def test_workflow_catalog_visible_across_surfaces() -> None:
    ids = [w.workflow_id for w in list_workflows()]
    planner = call_mcp_tool("lmola.get_planner_context", {})["planner_context"]
    schema = call_mcp_tool("lmola.get_workflow_catalog", {})["workflow_catalog"]
    listed = call_mcp_tool("lmola.list_workflows", {"compact": True})["workflows"]
    tool_meta = list_mcp_tools_runtime()
    run_tool = next(t for t in tool_meta if t["name"] == "lmola.run_workflow")

    assert set(ids).issubset(set(planner.get("allowed_workflow_ids", [])))
    assert set(ids).issubset({w["workflow_id"] for w in planner.get("workflows", [])})
    assert set(ids).issubset(set(schema.get("workflow_ids", [])))
    assert set(ids).issubset({w["workflow_id"] for w in listed})
    assert set(ids).issubset(set(run_tool.get("_meta", {}).get("lmola", {}).get("supported_workflow_ids", [])))

    for wf in ids:
        out = call_mcp_tool("lmola.inspect_workflow", {"workflow_id": wf})
        assert out["status"] == "ok"
        assert out["workflow"]["workflow_id"] == wf


def test_low_level_tools_not_exposed_in_runtime() -> None:
    names = {t["name"] for t in list_mcp_tools_runtime()}
    assert names.isdisjoint(LOW_LEVEL_BLOCKLIST)
