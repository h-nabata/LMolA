from __future__ import annotations

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from lmola.cli import app
from lmola.llm.request_normalization import normalize_request


def test_japanese_request_normalization_core_cases() -> None:
    sp = normalize_request("xTBの単一点計算。構造最適化しない。", language="ja")
    assert "xyz_to_xtb_singlepoint" in sp["workflow_hints"]
    assert "do_not_optimize_geometry" in sp["safety_constraints"]

    d = normalize_request("分子量とHBD/HBAでフィルタ", language="ja")
    assert "filter_molecules_by_descriptors" in d["workflow_hints"]

    r = normalize_request("RMSDのみ", language="ja")
    assert "xyz_to_rmsd" in r["workflow_hints"]

    c = normalize_request("2つの構造を比較して原子ごとの変位", language="ja")
    assert "compare_two_geometries" in c["workflow_hints"]

    m = normalize_request("molSimplifyで錯体生成", language="ja")
    assert any("backend_unavailable" in n for n in m["notes"])

    u = normalize_request("DFTで遷移状態を探索", language="ja")
    assert any("unsupported" in n for n in u["notes"])


def test_japanese_normalization_cli() -> None:
    res = CliRunner().invoke(app, ["workflow", "normalize-request", "--language", "ja", "--request", "単一点計算、構造最適化しない", "--format", "json"])
    assert res.exit_code == 0
    payload = json.loads(res.stdout)
    assert payload["status"] == "ok"
    assert "xyz_to_xtb_singlepoint" in payload["workflow_hints"]


def test_japanese_orchestration_case_file_and_smoke() -> None:
    p = Path("examples/orchestration_phase14_japanese_cases.yaml")
    assert p.exists()
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    ids = {c["case_id"] for c in data["cases"]}
    required = {
        "ja_descriptor_then_triage",
        "ja_geometry_then_xtb_singlepoint",
        "ja_geometry_then_relax_dry_run",
        "ja_unavailable_backend_stop",
        "ja_unsupported_research_task_stop",
    }
    assert required.issubset(ids)

    res = CliRunner().invoke(app, ["mcp", "llm-orchestration-smoke", "--backend", "mock", "--execute-safe", "--cases", str(p), "--format", "json"])
    assert res.exit_code == 0
    payload = json.loads(res.stdout)
    assert payload["status"] == "ok"
    assert payload["pass_rate"] == 1.0
    assert payload["normalization_pass_rate"] == 1.0


def test_agents_role_separation_docs() -> None:
    agents = Path("AGENTS.md").read_text(encoding="utf-8")
    assert "development agents" in agents.lower()
    assert "not the runtime prompt" in agents.lower()
    assert "docs/agents/runtime_chemistry_agent.md" in agents

    runtime = Path("docs/agents/runtime_chemistry_agent.md")
    assert runtime.exists()
    text = runtime.read_text(encoding="utf-8").lower()
    assert "never bypass execution gates" in text
    assert "high-level" in text
    assert "artifact triage" in text
    assert "unsupported" in text
    assert "backend_unavailable" in text
