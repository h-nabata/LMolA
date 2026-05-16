import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from lmola.cli import app
from lmola.tools.registry import ToolExecutionResult
from lmola.workflows.catalog import WORKFLOW_CATALOG
from lmola.workflows.runner import run_workflow_yaml
from lmola.workflows.schemas import WorkflowRequest

runner = CliRunner()


def test_workflow_schema_parses_example() -> None:
    import yaml

    data = yaml.safe_load(Path("examples/workflow_smiles_to_3d_rdkit.yaml").read_text(encoding="utf-8"))
    req = WorkflowRequest.model_validate(data)
    assert req.workflow_id == "smiles_to_3d_rdkit"


def test_workflow_catalog_ids_present() -> None:
    expected = {"smiles_to_3d_rdkit", "smiles_to_conformers_rdkit", "smiles_to_3d_openbabel", "smiles_to_xtb_relax", "xyz_to_xtb_relax", "validate_xyz"}
    assert expected.issubset(set(WORKFLOW_CATALOG))


def test_workflow_list_cli() -> None:
    result = runner.invoke(app, ["workflow", "list"])
    assert result.exit_code == 0
    assert "smiles_to_xtb_relax" in result.stdout


def test_workflow_inspect_cli() -> None:
    result = runner.invoke(app, ["workflow", "inspect", "smiles_to_xtb_relax"])
    assert result.exit_code == 0
    assert "input_types" in result.stdout


def test_workflow_run_malformed_yaml_fails(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("workflow_id: [", encoding="utf-8")
    result = runner.invoke(app, ["workflow", "run", str(bad)])
    assert result.exit_code != 0
    assert "validation failed" in result.stdout.lower()


def test_workflow_run_unknown_workflow_fails(tmp_path: Path) -> None:
    wf = tmp_path / "unknown.yaml"
    wf.write_text("workflow_id: nope\ninput:\n  type: smiles\n  value: CCO\n", encoding="utf-8")
    result = runner.invoke(app, ["workflow", "run", str(wf)])
    assert result.exit_code != 0


def test_workflow_run_unsupported_input_fails(tmp_path: Path) -> None:
    wf = tmp_path / "badinput.yaml"
    wf.write_text("workflow_id: smiles_to_3d_rdkit\ninput:\n  type: xyz\n  value: CCO\n", encoding="utf-8")
    result = runner.invoke(app, ["workflow", "run", str(wf)])
    assert result.exit_code != 0


def test_workflow_step_rejects_command_like_params(tmp_path: Path) -> None:
    wf = tmp_path / "unsafe.yaml"
    wf.write_text(
        "workflow_id: smiles_to_3d_rdkit\ninput:\n  type: smiles\n  value: CCO\nsteps:\n  - tool: generate_small_molecule_rdkit\n    params:\n      command: rm -rf /\n",
        encoding="utf-8",
    )
    result = runner.invoke(app, ["workflow", "run", str(wf)])
    assert result.exit_code != 0


def test_workflow_path_resolution_and_validation_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    csv_path = tmp_path / "in.csv"
    csv_path.write_text("id,smiles\none,CCO\n", encoding="utf-8")
    wf = tmp_path / "workflow.yaml"
    wf.write_text(f"workflow_id: smiles_to_3d_rdkit\ninput:\n  type: smiles_csv\n  path: {csv_path}\n", encoding="utf-8")

    calls: list[tuple[str, dict]] = []

    def fake_execute(tool: str, payload: dict, run_dir: Path) -> ToolExecutionResult:
        calls.append((tool, payload))
        if tool == "generate_small_molecule_rdkit":
            (run_dir / "molecule.xyz").write_text("3\n\nH 0 0 0\nH 0 0 1\nO 0 1 0\n", encoding="utf-8")
            return ToolExecutionResult(status="ok", message="generated", tool_name=tool, run_dir=str(run_dir), payload={"primary_structure": "molecule.xyz", "generated_files": ["molecule.xyz"]})
        if tool == "validate_structure_ase":
            path = Path(payload["structure_path"])
            valid = path.exists()
            messages = [] if valid else ["read_failed: missing"]
            (run_dir / "validation_report.json").write_text(json.dumps({"valid": valid, "messages": messages}), encoding="utf-8")
            return ToolExecutionResult(status="ok" if valid else "error", message="Validation completed", tool_name=tool, run_dir=str(run_dir), payload={"valid": valid, "messages": messages})
        raise AssertionError("unexpected")

    monkeypatch.setattr("lmola.workflows.runner.execute_tool", fake_execute)
    result = run_workflow_yaml(str(wf))
    assert result.status == "ok"
    assert result.summary is not None and result.summary.ok_count == 1
    assert calls[1][0] == "validate_structure_ase"
    assert Path(calls[1][1]["structure_path"]).name == "molecule.xyz"
    assert Path(calls[1][1]["structure_path"]).exists()

    summary = json.loads(Path(result.summary_json or "").read_text(encoding="utf-8"))
    assert summary[0]["validation_status"] == "ok"
    assert summary[0]["primary_structure"] == "molecule.xyz"
    assert Path(summary[0]["primary_structure_path"]).exists()


def test_workflow_validation_failure_reports_actual_message(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    wf = tmp_path / "workflow.yaml"
    wf.write_text("workflow_id: smiles_to_3d_rdkit\ninput:\n  type: smiles\n  value: CCO\n", encoding="utf-8")

    def fake_execute(tool: str, payload: dict, run_dir: Path) -> ToolExecutionResult:
        if tool == "generate_small_molecule_rdkit":
            return ToolExecutionResult(status="ok", message="generated", tool_name=tool, run_dir=str(run_dir), payload={"primary_structure": "molecule.xyz"})
        return ToolExecutionResult(status="error", message="Validation completed", tool_name=tool, run_dir=str(run_dir), payload={"valid": False, "messages": ["read_failed: [Errno 2] missing file"]})

    monkeypatch.setattr("lmola.workflows.runner.execute_tool", fake_execute)
    result = run_workflow_yaml(str(wf))
    assert result.summary is not None
    assert result.summary.error_count == 1
    summary = json.loads(Path(result.summary_json or "").read_text(encoding="utf-8"))
    assert "read_failed" in (summary[0]["error_message"] or "")
    assert summary[0]["validation_status"] == "error"


def test_workflow_relax_reads_tool_execution_result(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    wf = tmp_path / "workflow.yaml"
    wf.write_text("workflow_id: smiles_to_xtb_relax\ninput:\n  type: smiles\n  value: CCO\n", encoding="utf-8")

    def fake_execute(tool: str, payload: dict, run_dir: Path) -> ToolExecutionResult:
        if tool == "generate_small_molecule_rdkit":
            p = run_dir / "molecule.xyz"
            p.write_text("3\n\nH 0 0 0\nH 0 0 1\nO 0 1 0\n", encoding="utf-8")
            return ToolExecutionResult(status="ok", message="generated", tool_name=tool, run_dir=str(run_dir), payload={"primary_structure": "molecule.xyz"})
        if tool == "validate_structure_ase":
            return ToolExecutionResult(status="ok", message="Validation completed", tool_name=tool, run_dir=str(run_dir), payload={"valid": True, "messages": []})
        t = run_dir / "tool_execution_result.json"
        t.write_text(json.dumps({"energy": -1.23, "energy_units": "Eh"}), encoding="utf-8")
        (run_dir / "xtbopt.xyz").write_text("3\n\nH 0 0 0\nH 0 0 1\nO 0 1 0\n", encoding="utf-8")
        return ToolExecutionResult(status="ok", message="relaxed", tool_name=tool, run_dir=str(run_dir), payload={"output_structure": "xtbopt.xyz"})

    monkeypatch.setattr("lmola.workflows.runner.execute_tool", fake_execute)
    result = run_workflow_yaml(str(wf))
    assert result.summary is not None and result.summary.ok_count == 1
    summary = json.loads(Path(result.summary_json or "").read_text(encoding="utf-8"))
    assert summary[0]["relax_status"] == "ok"
    assert summary[0]["energy"] == -1.23
    assert Path(summary[0]["relaxed_structure_path"]).exists()


def test_conformer_ensemble_field_not_overloaded_with_sdf(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    wf = tmp_path / "workflow.yaml"
    wf.write_text("workflow_id: smiles_to_3d_rdkit\ninput:\n  type: smiles\n  value: CCO\n", encoding="utf-8")

    def fake_execute(tool: str, payload: dict, run_dir: Path) -> ToolExecutionResult:
        if tool == "generate_small_molecule_rdkit":
            (run_dir / "molecule.xyz").write_text("3\n\nH 0 0 0\nH 0 0 1\nO 0 1 0\n", encoding="utf-8")
            (run_dir / "molecule.sdf").write_text("$$$$\n", encoding="utf-8")
            (run_dir / "conformer_ensemble.json").write_text("{}", encoding="utf-8")
            return ToolExecutionResult(status="ok", message="generated", tool_name=tool, run_dir=str(run_dir), payload={"primary_structure": "molecule.xyz", "generated_files": ["molecule.xyz", "molecule.sdf", "conformer_ensemble.json"]})
        (run_dir / "validation_report.json").write_text('{"valid": true, "messages": []}', encoding="utf-8")
        return ToolExecutionResult(status="ok", message="Validation completed", tool_name=tool, run_dir=str(run_dir), payload={"valid": True, "messages": []})

    monkeypatch.setattr("lmola.workflows.runner.execute_tool", fake_execute)
    result = run_workflow_yaml(str(wf))
    summary = json.loads(Path(result.summary_json or "").read_text(encoding="utf-8"))
    row = summary[0]
    assert row["conformer_ensemble_path"] and row["conformer_ensemble_path"].endswith("conformer_ensemble.json")
    assert row["sdf_path"] and row["sdf_path"].endswith("molecule.sdf")
    assert "molecule.sdf" not in (row["conformer_ensemble_path"] or "")


def test_workflow_result_json_metadata_and_counts(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    csv_path = tmp_path / "in.csv"
    csv_path.write_text("id,smiles\none,CCO\ntwo,BAD\n", encoding="utf-8")
    wf = tmp_path / "workflow.yaml"
    wf.write_text(f"workflow_id: smiles_to_3d_rdkit\ninput:\n  type: smiles_csv\n  path: {csv_path}\n", encoding="utf-8")

    def fake_execute(tool: str, payload: dict, run_dir: Path) -> ToolExecutionResult:
        if tool == "generate_small_molecule_rdkit" and payload.get("smiles") == "BAD":
            return ToolExecutionResult(status="error", message="bad smiles", tool_name=tool, run_dir=str(run_dir), payload={})
        if tool == "generate_small_molecule_rdkit":
            (run_dir / "molecule.xyz").write_text("3\n\nH 0 0 0\nH 0 0 1\nO 0 1 0\n", encoding="utf-8")
            return ToolExecutionResult(status="ok", message="generated", tool_name=tool, run_dir=str(run_dir), payload={"primary_structure": "molecule.xyz"})
        (run_dir / "validation_report.json").write_text('{"valid": true, "messages": []}', encoding="utf-8")
        return ToolExecutionResult(status="ok", message="Validation completed", tool_name=tool, run_dir=str(run_dir), payload={"valid": True, "messages": []})

    monkeypatch.setattr("lmola.workflows.runner.execute_tool", fake_execute)
    result = run_workflow_yaml(str(wf))
    batch_dir = Path(result.batch_dir or "")
    payload = json.loads((batch_dir / "workflow_result.json").read_text(encoding="utf-8"))
    assert payload["batch_dir"] == str(batch_dir)
    assert payload["summary_csv"] == str(batch_dir / "summary.csv")
    assert payload["summary_json"] == str(batch_dir / "summary.json")
    assert payload["workflow_id"] == "smiles_to_3d_rdkit"
    assert payload["item_count"] == 2
    assert payload["ok_count"] == 1
    assert payload["error_count"] == 1
    assert payload["message"] == "Workflow executed with item errors"


def test_ok_status_paths_exist_in_summary(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    wf = tmp_path / "workflow.yaml"
    wf.write_text("workflow_id: smiles_to_xtb_relax\ninput:\n  type: smiles\n  value: CCO\n", encoding="utf-8")

    def fake_execute(tool: str, payload: dict, run_dir: Path) -> ToolExecutionResult:
        if tool == "generate_small_molecule_rdkit":
            (run_dir / "molecule.xyz").write_text("3\n\nH 0 0 0\nH 0 0 1\nO 0 1 0\n", encoding="utf-8")
            return ToolExecutionResult(status="ok", message="generated", tool_name=tool, run_dir=str(run_dir), payload={"primary_structure": "molecule.xyz", "generated_files": ["molecule.xyz"]})
        if tool == "validate_structure_ase":
            (run_dir / "validation_report.json").write_text('{"valid": true, "messages": []}', encoding="utf-8")
            return ToolExecutionResult(status="ok", message="Validation completed", tool_name=tool, run_dir=str(run_dir), payload={"valid": True, "messages": []})
        (run_dir / "xtbopt.xyz").write_text("3\n\nH 0 0 0\nH 0 0 1\nO 0 1 0\n", encoding="utf-8")
        (run_dir / "tool_execution_result.json").write_text('{"energy": -1.0, "energy_units": "Eh"}', encoding="utf-8")
        return ToolExecutionResult(status="ok", message="relaxed", tool_name=tool, run_dir=str(run_dir), payload={"output_structure": "xtbopt.xyz"})

    monkeypatch.setattr("lmola.workflows.runner.execute_tool", fake_execute)
    result = run_workflow_yaml(str(wf))
    row = json.loads(Path(result.summary_json or "").read_text(encoding="utf-8"))[0]
    assert row["generate_status"] == "ok" and Path(row["primary_structure_path"]).exists()
    assert row["validation_status"] == "ok" and Path(row["validation_report_path"]).exists()
    assert row["relax_status"] == "ok" and Path(row["relaxed_structure_path"]).exists()
