from pathlib import Path

from typer.testing import CliRunner

from lmola.agent.workflow_planner import _build_planner_prompt, plan_workflow_request
from lmola.cli import app

runner = CliRunner()


def _enable_mock(monkeypatch) -> None:
    monkeypatch.setenv("LMOLA_LLM_ENABLED", "1")
    monkeypatch.setenv("LMOLA_LLM_BACKEND", "mock")


def test_prompt_includes_catalog_and_tools() -> None:
    prompt = _build_planner_prompt("Generate 3D structures")
    assert "smiles_to_3d_rdkit" in prompt
    assert "smiles_to_xtb_relax" in prompt
    assert "generate_small_molecule_rdkit" in prompt
    assert "validate_structure_ase" in prompt


def test_mock_planner_smiles_to_3d(monkeypatch) -> None:
    _enable_mock(monkeypatch)
    result = plan_workflow_request("Generate 3D structures from examples/smiles_list.csv using RDKit.", write_artifacts=False)
    assert result.status == "ok"
    assert result.selected_workflow_id == "smiles_to_3d_rdkit"


def test_mock_planner_xtb(monkeypatch) -> None:
    _enable_mock(monkeypatch)
    result = plan_workflow_request("Generate structures from examples/smiles_list.csv and relax them with xTB.", write_artifacts=False)
    assert result.status == "ok"
    assert result.selected_workflow_id == "smiles_to_xtb_relax"


def test_mock_planner_conformers(monkeypatch) -> None:
    _enable_mock(monkeypatch)
    result = plan_workflow_request("Generate conformers from examples/smiles_list.csv using RDKit.", write_artifacts=False)
    assert result.status == "ok"
    assert result.selected_workflow_id == "smiles_to_conformers_rdkit"


def test_mock_planner_validate_xyz(monkeypatch) -> None:
    _enable_mock(monkeypatch)
    result = plan_workflow_request("Validate examples/example.xyz.", write_artifacts=False)
    assert result.status == "ok"
    assert result.selected_workflow_id == "validate_xyz"


def test_unsupported_request_safe_error(monkeypatch) -> None:
    _enable_mock(monkeypatch)
    result = plan_workflow_request("Run DFT on this molecule.", write_artifacts=False)
    assert result.status == "error"
    assert "not supported" in result.message


def test_plan_cli_writes_artifacts(monkeypatch) -> None:
    _enable_mock(monkeypatch)
    result = runner.invoke(app, ["workflow", "plan", "Validate examples/example.xyz."])
    assert result.exit_code == 0
    assert '"status": "ok"' in result.stdout
    assert '"plan_dir":' in result.stdout
    plan_dir = result.stdout.split('"plan_dir": ')[1].split(',')[0].strip().strip('"')
    base = Path(plan_dir)
    assert (base / "planned_workflow.json").exists()
    assert (base / "planned_workflow.yaml").exists()
    assert (base / "planning_result.json").exists()


def test_public_remote_endpoint_blocked(monkeypatch) -> None:
    monkeypatch.setenv("LMOLA_LLM_ENABLED", "1")
    monkeypatch.setenv("LMOLA_LLM_BACKEND", "ollama")
    monkeypatch.setenv("LMOLA_LLM_BASE_URL", "https://example.com")
    result = plan_workflow_request("Validate examples/example.xyz.", write_artifacts=False)
    assert result.status == "error"
    assert "Unsafe LLM endpoint" in result.message
