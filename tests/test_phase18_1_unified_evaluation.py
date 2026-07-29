import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from lmola.cli import app
from lmola.evaluation.models import ArtifactReference, EvaluationRunResult
from lmola.evaluation.registry import SuiteDefinition, list_profiles, list_suites, validate_registry
from lmola.evaluation.runner import GATE_IDS, METRIC_IDS, aggregate_gates, run_evaluation, validate_result
from lmola.schema_export import export_all_schemas


@pytest.fixture(scope="module")
def safety_run(tmp_path_factory):
    return run_evaluation(repeat=2, output_root=tmp_path_factory.mktemp("evaluation"))


def test_registry_is_valid_and_identifiers_are_unique():
    suites = list_suites()
    profiles = list_profiles()
    assert validate_registry() == []
    assert len({suite.suite_id for suite in suites}) == len(suites) == 8
    assert [profile.profile_id for profile in profiles] == ["safety-core"]
    assert len(set(METRIC_IDS)) == len(METRIC_IDS)
    assert len(set(GATE_IDS)) == len(GATE_IDS) == 5


def test_safety_core_result_and_evidence(safety_run):
    assert safety_run.status == "pass"
    assert EvaluationRunResult.model_validate(safety_run.model_dump()) == safety_run
    assert safety_run.repeat == 2
    assert all(gate.status == "pass" and gate.evaluated_case_count for gate in safety_run.hard_gate_results)
    assert all(gate.evidence_suite_ids for gate in safety_run.hard_gate_results)
    assert next(m for m in safety_run.utility_metrics if m.metric_id == "cross_run_consistency").value == 1.0


def test_one_repeat_violation_fails_all_or_nothing_gate():
    clean = {"total_cases": 1, "cases": [{"case_id": "case", "passed": True}], "unsafe_execution_attempt_rate": 0.0}
    bad = {**clean, "unsafe_execution_attempt_rate": 1.0}
    gate = aggregate_gates([("execution_gate", 1, clean), ("execution_gate", 2, bad)])[0]
    assert gate.status == "fail"
    assert gate.violation_count > 0


def test_missing_required_evidence_fails_closed_and_not_applicable_is_distinct():
    gate = aggregate_gates([])[0]
    assert gate.status == "fail"
    assert gate.violation_rate is None
    schema = gate.model_json_schema()
    assert "not_applicable" in schema["properties"]["status"]["enum"]


def test_artifacts_are_relative_private_and_valid(safety_run):
    result_path = Path(safety_run.artifacts[0].path)
    assert not result_path.is_absolute()
    with pytest.raises(ValidationError):
        ArtifactReference(path="/private/evaluation.json", artifact_type="evaluation_report")
    serialized = json.dumps(safety_run.model_dump(mode="json")).lower()
    for forbidden in ("hostname", "home_directory", "environment_variables", "api_key", "credential"):
        assert forbidden not in serialized


def test_validate_result_and_deterministic_structure(safety_run, tmp_path):
    path = tmp_path / "result.json"
    path.write_text(safety_run.model_dump_json(), encoding="utf-8")
    assert validate_result(path).schema_version == "lmola.evaluation_result.v1"
    assert [s.suite_id for s in safety_run.suite_results] == sorted(s.suite_id for s in safety_run.suite_results)
    assert all([c.repeat_index for c in suite.cases] == sorted(c.repeat_index for c in suite.cases) for suite in safety_run.suite_results)


def test_injected_failing_suite_fails_run(tmp_path):
    def failing():
        return {"status": "error", "total_cases": 1, "cases": [{"case_id": "synthetic", "passed": False}],
                **{gate: (1.0 if gate == "unsafe_execution_attempt_rate" else 0.0) for gate in GATE_IDS}}

    suite = SuiteDefinition("synthetic", "test only", failing, (), GATE_IDS)
    result = run_evaluation(output_root=tmp_path, suites=[suite])
    assert result.status == "fail"


def test_schema_export_and_cli_deferral():
    assert "EvaluationRunResult" in export_all_schemas()["models"]
    runner = CliRunner()
    assert runner.invoke(app, ["eval", "list-suites", "--format", "json"]).exit_code == 0
    deferred = runner.invoke(app, ["eval", "run", "--backend", "ollama", "--format", "json"])
    assert deferred.exit_code != 0
    assert "Phase 18.2" in deferred.stdout
