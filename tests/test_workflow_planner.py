from pathlib import Path

from typer.testing import CliRunner

from lmola.agent.workflow_planner import _build_planner_prompt, build_schema_driven_planner_context, plan_workflow_request
from lmola.cli import app

runner = CliRunner()


def _enable_mock(monkeypatch) -> None:
    monkeypatch.setenv("LMOLA_LLM_ENABLED", "1")
    monkeypatch.setenv("LMOLA_LLM_BACKEND", "mock")


def test_prompt_includes_catalog_and_contract() -> None:
    context = build_schema_driven_planner_context()
    prompt = _build_planner_prompt("Generate 3D structures")
    assert all(wf_id in prompt for wf_id in context["allowed_workflow_ids"])
    assert "unsupported" in prompt
    assert "JSON only" in prompt
    assert "Never execute shell commands" in prompt


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
    assert result.workflow_json is None
    assert result.canonical_workflow_json is None
    assert result.validation_errors == []


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
    assert (base / "canonical_workflow.json").exists()
    assert (base / "canonical_workflow.yaml").exists()
    assert (base / "planning_result.json").exists()
    assert (base / "planner_context_compact.json").exists()
    assert (base / "planner_prompt.txt").exists()


def test_canonical_expands_catalog_steps(monkeypatch) -> None:
    _enable_mock(monkeypatch)
    result = plan_workflow_request("Generate structures from examples/smiles_list.csv and relax them with xTB.", write_artifacts=False)
    assert result.status == "ok"
    assert result.workflow_json is not None
    assert result.workflow_json.get("steps") is None
    assert result.canonical_workflow_json is not None
    step_tools = [step["tool"] for step in result.canonical_workflow_json["steps"]]
    assert step_tools == ["generate_small_molecule_rdkit", "validate_structure_ase", "relax_structure_xtb"]


def test_planning_result_contains_planned_and_canonical_paths(monkeypatch) -> None:
    _enable_mock(monkeypatch)
    result = runner.invoke(app, ["workflow", "plan", "Generate structures from examples/smiles_list.csv and relax them with xTB."])
    assert result.exit_code == 0
    plan_dir = result.stdout.split('"plan_dir": ')[1].split(',')[0].strip().strip('"')
    payload = __import__("json").loads((Path(plan_dir) / "planning_result.json").read_text(encoding="utf-8"))
    assert payload["executed"] is False
    assert payload["planned_workflow_path_json"].endswith("planned_workflow.json")
    assert payload["planned_workflow_path_yaml"].endswith("planned_workflow.yaml")
    assert payload["canonical_workflow_path_json"].endswith("canonical_workflow.json")
    assert payload["canonical_workflow_path_yaml"].endswith("canonical_workflow.yaml")
    assert payload["planner_prompt_mode"] == "schema_driven"
    assert payload["planner_context_schema_version"] == "lmola.planner_context.v1"


def test_public_remote_endpoint_blocked(monkeypatch) -> None:
    monkeypatch.setenv("LMOLA_LLM_ENABLED", "1")
    monkeypatch.setenv("LMOLA_LLM_BACKEND", "ollama")
    monkeypatch.setenv("LMOLA_LLM_BASE_URL", "https://example.com")
    result = plan_workflow_request("Validate examples/example.xyz.", write_artifacts=False)
    assert result.status == "error"
    assert "Unsafe LLM endpoint" in result.message
