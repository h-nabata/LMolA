from __future__ import annotations

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from lmola.cli import app
from lmola.llm.request_normalization import normalize_request


def test_japanese_request_normalization_core_cases() -> None:
    sp = normalize_request("examples/example.xyz に対してxTB単一点エネルギー計算を行ってください。構造最適化は行わず、入力構造を変更しないでください。", language="ja")
    assert sp["normalized_intent"]["method"] == "xtb"
    assert sp["normalized_intent"]["operation"] == "singlepoint_energy"
    assert "do_not_optimize_geometry" in sp["normalized_intent"]["constraints"]
    assert "xyz_to_xtb_singlepoint" in sp["workflow_hints"]
    assert "xyz_to_xtb_relax" not in sp["workflow_hints"]

    sp2 = normalize_request("xTB singlepoint calculation", language="en")
    assert sp2["normalized_intent"]["operation"] == "singlepoint_energy"
    assert "xyz_to_xtb_singlepoint" in sp2["workflow_hints"]

    sp3 = normalize_request("xTB one-point energy calculation", language="en")
    assert sp3["normalized_intent"]["operation"] == "singlepoint_energy"
    assert "xyz_to_xtb_singlepoint" in sp3["workflow_hints"]

    relax = normalize_request("examples/example.xyz をxTBで構造最適化", language="ja")
    assert relax["normalized_intent"]["operation"] == "geometry_optimization"
    assert "xyz_to_xtb_relax" in relax["workflow_hints"]

    generic = normalize_request("xTB計算をしてください", language="ja")
    assert generic["normalized_intent"]["method"] == "xtb"
    assert generic["normalized_intent"]["operation"] is None
    assert "xyz_to_xtb_relax" not in generic["workflow_hints"]

    d = normalize_request("mols.csv について分子量とHBD/HBAでフィルタ", language="ja")
    assert d["normalized_intent"]["operation"] == "descriptor_filtering"
    assert "filter_molecules_by_descriptors" in d["workflow_hints"]

    r = normalize_request("RMSDのみ", language="ja")
    assert r["normalized_intent"]["operation"] == "rmsd_calculation"
    assert "xyz_to_rmsd" in r["workflow_hints"]

    c = normalize_request("2つの構造を比較して原子ごとの変位", language="ja")
    assert c["normalized_intent"]["operation"] == "structure_comparison"
    assert "compare_two_geometries" in c["workflow_hints"]

    e = normalize_request("Fe原子の数を数えて", language="ja")
    assert e["normalized_intent"]["operation"] == "element_counting"
    assert "count_element_atoms" in e["workflow_hints"]

    s = normalize_request("ファイル順で1番から3番と4番から最後に分割", language="ja")
    assert s["normalized_intent"]["operation"] == "molecule_splitting"
    assert "split_molecule_by_file_order" in s["workflow_hints"]

    m = normalize_request("molSimplifyで錯体生成", language="ja")
    assert m["normalized_intent"]["method"] == "molsimplify"
    assert m["normalized_intent"]["operation"] == "metal_complex_generation"
    assert any("backend_unavailable" in n for n in m["notes"])

    u = normalize_request("DFTで遷移状態を探索", language="ja")
    assert u["normalized_intent"]["method"] == "dft"
    assert u["normalized_intent"]["operation"] in {"transition_state_search", "reaction_path_search"}
    assert any("unsupported" in n for n in u["notes"])


def test_japanese_normalization_cli() -> None:
    res = CliRunner().invoke(app, ["workflow", "normalize-request", "--language", "ja", "--request", "単一点計算、構造最適化しない", "--format", "json"])
    assert res.exit_code == 0
    payload = json.loads(res.stdout)
    assert payload["status"] in {"ok", "ambiguous"}
    assert payload["raw_request"]
    assert payload["normalized_intent"]["operation"] == "singlepoint_energy"
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
    for case in payload["case_results"]:
        assert case["raw_request"]
        assert case["normalized_request"]


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
