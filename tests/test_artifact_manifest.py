from __future__ import annotations

from pathlib import Path

from lmola.artifact_manifest import ArtifactManifest, inspect_manifest, get_compatibility
from lmola.workflows.runner import run_workflow_yaml
from lmola.mcp_runtime import call_mcp_tool, list_mcp_tools_runtime


def test_manifest_generated_for_singlepoint() -> None:
    result = run_workflow_yaml("examples/workflow_xyz_to_xtb_singlepoint.yaml")
    m = Path(result.batch_dir) / "artifact_manifest.json"
    assert m.exists()
    payload = inspect_manifest(result.batch_dir)
    assert payload["status"] == "ok"
    manifest = ArtifactManifest.model_validate(payload["manifest"])
    assert manifest.schema_version == "lmola.artifact_manifest.v1"


def test_compatibility_and_non_geometry_singlepoint_result(tmp_path: Path) -> None:
    result = run_workflow_yaml("examples/workflow_xyz_to_xtb_singlepoint.yaml")
    comp = get_compatibility(result.batch_dir)
    assert comp["status"] == "ok"
    flat = [w["workflow_id"] for a in comp["artifact_next_compatible_workflows"] for w in a["next_compatible_workflows"] if a["artifact_type"] == "xtb_singlepoint_result"]
    assert "xyz_to_xtb_relax" not in flat


def test_cli_style_errors_for_unsafe_and_missing() -> None:
    assert inspect_manifest("/etc/passwd")["error_type"] == "unsafe_path"
    missing = inspect_manifest("outputs")
    assert missing["status"] == "error"


def test_mcp_tools_present_and_callable() -> None:
    names = {t["name"] for t in list_mcp_tools_runtime()}
    assert "lmola.inspect_artifact_manifest" in names
    assert "lmola.get_artifact_compatibility" in names
    out = call_mcp_tool("lmola.inspect_artifact_manifest", {"path": "outputs"})
    assert out["status"] == "error"
