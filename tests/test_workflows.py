from pathlib import Path

from typer.testing import CliRunner

from lmola.cli import app
from lmola.workflows.catalog import WORKFLOW_CATALOG
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


def test_workflow_run_writes_summary_and_continues_on_errors(tmp_path: Path) -> None:
    csv_path = tmp_path / "in.csv"
    csv_path.write_text("id,smiles\none,CCO\ntwo,INVALID\n", encoding="utf-8")
    wf = tmp_path / "workflow.yaml"
    wf.write_text(
        f"workflow_id: smiles_to_3d_rdkit\ninput:\n  type: smiles_csv\n  path: {csv_path}\ncolumns:\n  id: id\n  smiles: smiles\n",
        encoding="utf-8",
    )
    result = runner.invoke(app, ["workflow", "run", str(wf)])
    assert result.exit_code == 0
    assert "summary.csv" in result.stdout
