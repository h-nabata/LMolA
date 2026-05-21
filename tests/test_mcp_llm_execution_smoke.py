from __future__ import annotations

from typer.testing import CliRunner

from lmola.cli import app


def _run(*args: str):
    runner = CliRunner()
    return runner.invoke(app, ["mcp", "llm-execution-smoke", *args])


def test_llm_execution_smoke_exists() -> None:
    res = _run("--help")
    assert res.exit_code == 0
    assert "--execute-safe" in res.stdout


def test_mock_llm_execution_smoke_dry_run_only() -> None:
    res = _run("--backend", "mock", "--format", "json")
    assert res.exit_code == 0
    assert '"status": "ok"' in res.stdout
    assert '"executed_case_ids": []' in res.stdout


def test_mock_llm_execution_smoke_execute_safe() -> None:
    res = _run("--backend", "mock", "--execute-safe", "--format", "json")
    assert res.exit_code == 0
    assert '"status": "ok"' in res.stdout
    assert "descriptor" in res.stdout and "geometry" in res.stdout
    assert "xtb_not_confirmed_by_smoke" in res.stdout


def test_confirmed_execution_smoke_alias_keys_stable() -> None:
    runner = CliRunner()
    res = runner.invoke(app, ["mcp", "confirmed-execution-smoke", "--format", "json"])
    assert res.exit_code == 0
    assert "dry_run_no_execution" in res.stdout
    assert "descriptor_confirmed_execution_ok" in res.stdout
    assert "geometry_confirmed_execution_ok" in res.stdout
