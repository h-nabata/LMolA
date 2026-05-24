from __future__ import annotations

import json
from pathlib import Path

from lmola.agent.planner_eval import run_planner_eval
from lmola.workflows.runner import run_workflow_yaml
from lmola.artifact_summary import summarize_artifact_path


def test_phase14_planner_eval_cases_with_mock(monkeypatch) -> None:
    monkeypatch.setenv("LMOLA_LLM_ENABLED", "1")
    monkeypatch.setenv("LMOLA_LLM_BACKEND", "mock")
    result = run_planner_eval("examples/planner_phase14_workflow_expansion_eval_cases.yaml")
    assert result.failed_cases == 0
    rows = json.loads(Path(result.summary_json).read_text(encoding="utf-8"))
    by_case = {r["case_id"]: r for r in rows}
    assert by_case["compare_two_geometries"]["selected_workflow_id"] == "compare_two_geometries"
    assert by_case["rmsd"]["selected_workflow_id"] == "xyz_to_rmsd"


def test_phase14_1_japanese_planner_eval_cases_with_mock(monkeypatch) -> None:
    monkeypatch.setenv("LMOLA_LLM_ENABLED", "1")
    monkeypatch.setenv("LMOLA_LLM_BACKEND", "mock")
    result = run_planner_eval("examples/planner_phase14_1_japanese_eval_cases.yaml")
    assert result.failed_cases == 0


def test_split_positive_and_invalid_examples() -> None:
    pos = run_workflow_yaml("examples/workflow_split_molecule_by_file_order.yaml")
    assert pos.status == "ok"
    assert pos.summary is not None
    assert pos.summary.ok_count == 1
    assert pos.summary.error_count == 0

    invalid = run_workflow_yaml("examples/workflow_split_molecule_by_file_order_invalid.yaml")
    assert invalid.status == "ok"
    assert invalid.summary is not None
    assert invalid.summary.error_count > 0


def test_xtb_singlepoint_success_and_summary(tmp_path: Path, monkeypatch) -> None:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    xtb = bindir / "xtb"
    xtb.write_text("#!/usr/bin/env bash\necho ' normal termination of xtb'\necho '| TOTAL ENERGY      -76.123456'\n", encoding="utf-8")
    xtb.chmod(0o755)
    import os
    monkeypatch.setenv("PATH", f"{bindir}:{os.environ.get('PATH','')}")

    out = run_workflow_yaml("examples/workflow_xyz_to_xtb_singlepoint.yaml")
    assert out.status == "ok"
    assert out.summary is not None
    assert out.summary.ok_count == 1
    assert out.summary.error_count == 0

    batch = Path(out.batch_dir)
    payload = json.loads((batch / "items" / "item_0001" / "xtb_singlepoint" / "singlepoint_result.json").read_text(encoding="utf-8"))
    assert payload["status"] == "ok"
    assert payload["geometry_modified"] is False
    assert payload["normal_termination"] is True
    assert payload["energy"] is not None

    summary = summarize_artifact_path(batch / "items" / "item_0001" / "xtb_singlepoint" / "singlepoint_result.json")
    assert summary["artifact_kind"] == "singlepoint_result"
    assert summary["energy"] is not None
    batch_summary = summarize_artifact_path(batch)
    serialized = json.dumps(batch_summary, sort_keys=True)
    assert '"geometry_modified": false' in serialized
    assert '"energy"' in serialized
