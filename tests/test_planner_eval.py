import json
from pathlib import Path

from typer.testing import CliRunner

from lmola.agent.planner_eval import load_eval_suite, run_planner_eval
from lmola.cli import app

runner = CliRunner()


def _enable_mock(monkeypatch) -> None:
    monkeypatch.setenv("LMOLA_LLM_ENABLED", "1")
    monkeypatch.setenv("LMOLA_LLM_BACKEND", "mock")


def test_eval_suite_schema_parses_example() -> None:
    suite = load_eval_suite("examples/planner_eval_cases.yaml")
    assert suite.suite_id == "planner_eval_phase_10_5"
    assert len(suite.cases) >= 6


def test_eval_planner_cli_with_mock(monkeypatch) -> None:
    _enable_mock(monkeypatch)
    result = runner.invoke(app, ["workflow", "eval-planner", "examples/planner_eval_cases.yaml"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    eval_dir = Path(payload["eval_dir"])
    assert (eval_dir / "eval_result.json").exists()
    assert (eval_dir / "eval_summary.csv").exists()
    assert (eval_dir / "eval_summary.json").exists()


def test_eval_writes_case_results_and_metrics(monkeypatch) -> None:
    _enable_mock(monkeypatch)
    result = run_planner_eval("examples/planner_eval_cases.yaml")
    assert result.total_cases == 6
    assert result.failed_cases == 0
    assert result.backend == "mock"
    assert "qwen2.5" not in str(result.model)
    eval_dir = Path(result.eval_dir)
    rows = json.loads((eval_dir / "eval_summary.json").read_text(encoding="utf-8"))
    xtb = [r for r in rows if r["case_id"] == "smiles_to_xtb_relax"][0]
    assert xtb["workflow_match"] is True
    assert xtb["tools_match"] is True
    unsupported = [r for r in rows if r["case_id"] == "unsupported_ts_search"][0]
    assert unsupported["unsupported_handled"] is True
    assert unsupported["passed"] is True
    assert unsupported["failure_category"] == "none"
    for r in rows:
        assert r["executed"] is False
        assert r["failure_category"] == "none"
        case_path = Path(r["case_dir"])
        assert case_path.joinpath("case_result.json").exists()
        assert case_path.joinpath("planning_result.json").exists()
        assert case_path.joinpath("planner_context_compact.json").exists()

    eval_result = json.loads((eval_dir / "eval_result.json").read_text(encoding="utf-8"))
    for key in ["backend", "model", "base_url", "temperature", "timeout_seconds", "max_tokens", "suite_id", "summary_csv", "summary_json", "planner_prompt_mode", "planner_context_schema_version"]:
        assert key in eval_result


def test_eval_endpoint_failure_safe(monkeypatch) -> None:
    monkeypatch.setenv("LMOLA_LLM_ENABLED", "1")
    monkeypatch.setenv("LMOLA_LLM_BACKEND", "openai_compatible_local")
    monkeypatch.setenv("LMOLA_LLM_BASE_URL", "http://127.0.0.1:9/v1")
    result = run_planner_eval("examples/planner_eval_cases.yaml")
    assert result.status == "error"
    assert result.failed_cases > 0


def test_eval_public_remote_endpoint_blocked(monkeypatch) -> None:
    monkeypatch.setenv("LMOLA_LLM_ENABLED", "1")
    monkeypatch.setenv("LMOLA_LLM_BACKEND", "ollama")
    monkeypatch.setenv("LMOLA_LLM_BASE_URL", "https://example.com")
    result = run_planner_eval("examples/planner_eval_cases.yaml")
    assert result.status == "error"
    assert result.failed_cases > 0


def test_qwen_example_config_yaml_parses() -> None:
    import yaml

    payload = yaml.safe_load(Path("examples/config_ollama_qwen2_5_coder_14b.yaml").read_text(encoding="utf-8"))
    assert payload["llm"]["backend"] == "ollama"
    assert payload["llm"]["model"] == "qwen2.5-coder:14b"


def test_eval_marks_canonicalization_failure(monkeypatch, tmp_path) -> None:
    _enable_mock(monkeypatch)
    from lmola.agent import workflow_planner as wp
    from lmola.tools.llm_client import LLMResult

    bad = '{"workflow_id":"smiles_to_conformers_rdkit","input":{"type":"xyz","path":"examples/example.xyz"}}'

    class _BadClient:
        def complete_json(self, system_prompt: str, user_prompt: str) -> LLMResult:
            return LLMResult(status="ok", backend="mock", raw_response=bad)

    monkeypatch.setattr(wp, "make_llm_client", lambda _cfg: _BadClient())
    suite = tmp_path / "suite.yaml"
    suite.write_text(
        "suite_id: canon_fail\ncases:\n  - id: c1\n    request: bad combo\n    expected_status: ok\n    expected_workflow_id: smiles_to_conformers_rdkit\n",
        encoding="utf-8",
    )
    result = run_planner_eval(str(suite))
    eval_dir = Path(result.eval_dir)
    assert (eval_dir / "eval_result.json").exists()
    rows = json.loads((eval_dir / "eval_summary.json").read_text(encoding="utf-8"))
    assert rows[0]["failure_category"] == "canonicalization_failure"


def test_eval_continues_on_unexpected_exception(monkeypatch, tmp_path) -> None:
    _enable_mock(monkeypatch)
    from lmola.agent import planner_eval as pe

    real = pe.plan_workflow_request
    seen = {"n": 0}

    def _flaky(request_text: str, write_artifacts: bool = True):
        seen["n"] += 1
        if seen["n"] == 1:
            raise RuntimeError("boom")
        return real(request_text, write_artifacts=write_artifacts)

    monkeypatch.setattr(pe, "plan_workflow_request", _flaky)
    suite = tmp_path / "suite2.yaml"
    suite.write_text(
        "suite_id: unexpected\ncases:\n  - id: bad\n    request: first\n    expected_status: ok\n  - id: good\n    request: Validate examples/example.xyz.\n    expected_status: ok\n    expected_workflow_id: validate_xyz\n",
        encoding="utf-8",
    )
    result = run_planner_eval(str(suite))
    eval_dir = Path(result.eval_dir)
    assert (eval_dir / "eval_result.json").exists()
    rows = json.loads((eval_dir / "eval_summary.json").read_text(encoding="utf-8"))
    assert len(rows) == 2
    assert rows[0]["failure_category"] == "unexpected_error"
