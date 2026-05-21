from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from lmola.cli import app


def _run(*args: str):
    runner = CliRunner()
    return runner.invoke(app, ["mcp", "llm-execution-smoke", *args])


def test_llm_execution_smoke_exists() -> None:
    res = _run("--help")
    assert res.exit_code == 0
    assert "--execute-safe" in res.stdout


def test_mock_llm_execution_smoke_execute_safe_and_aliases() -> None:
    res = _run("--backend", "mock", "--execute-safe", "--format", "json")
    assert res.exit_code == 0
    payload = json.loads(res.stdout)
    assert payload["status"] == "ok"
    assert "descriptor" in payload["executed_case_ids"]
    assert "geometry" in payload["executed_case_ids"]
    assert payload["case_id_aliases"]["descriptor_request"] == "descriptor"
    assert payload["case_id_aliases"]["geometry_request"] == "geometry"
    smoke_dir = Path(payload["smoke_dir"])
    assert (smoke_dir / "cases" / "descriptor").exists()
    assert (smoke_dir / "cases" / "geometry").exists()


def test_confirmed_execution_smoke_alias_keys_stable() -> None:
    runner = CliRunner()
    res = runner.invoke(app, ["mcp", "confirmed-execution-smoke", "--format", "json"])
    assert res.exit_code == 0
    assert "dry_run_no_execution" in res.stdout
    assert "descriptor_confirmed_execution_ok" in res.stdout
    assert "geometry_confirmed_execution_ok" in res.stdout
