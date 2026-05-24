from __future__ import annotations

from typing import Any


def _contains_any(text: str, patterns: list[str]) -> bool:
    return any(p in text for p in patterns)


def normalize_request(request: str, language: str = "auto") -> dict[str, Any]:
    raw = (request or "").strip()
    text = raw.lower()
    lang = "ja" if language == "ja" or any("\u3040" <= ch <= "\u30ff" or "\u4e00" <= ch <= "\u9fff" for ch in raw) else "en"

    intents: list[str] = []
    hints: list[str] = []
    safety: list[str] = []
    notes: list[str] = []
    execution_preference = "unspecified"

    if _contains_any(text, ["dry-run", "ドライラン", "実行しない", "準備だけ"]):
        execution_preference = "dry_run"
    elif _contains_any(text, ["実行してよい", "安全な範囲で実行"]):
        execution_preference = "execute_safe"
        notes.append("execution permission is still controlled by deterministic external confirmation gates")

    if _contains_any(text, ["dft", "遷移状態", "反応経路", "neb"]):
        intents.append("unsupported_research_task")
        notes.append("unsupported: advanced quantum chemistry research request")
    if _contains_any(text, ["molsimplify", "錯体生成"]):
        intents.append("backend_unavailable_check")
        notes.append("backend_unavailable if molSimplify backend is not available")

    singlepoint_requested = _contains_any(
        text,
        ["単一点計算", "一点計算", "シングルポイント", "single point", "singlepoint"],
    )
    no_optimize_requested = _contains_any(
        text,
        ["構造最適化しない", "最適化は行わない", "入力構造を変更しない", "構造を変更しない"],
    )
    relax_requested = _contains_any(text, ["構造最適化", "最適化してください", "xtb最適化", "緩和", "relax"])

    if singlepoint_requested:
        intents.append("xtb_singlepoint")
        hints.append("xyz_to_xtb_singlepoint")
        safety.extend(["do_not_optimize_geometry", "geometry_modified=false"])
    if no_optimize_requested:
        safety.append("do_not_optimize_geometry")
    if relax_requested and not singlepoint_requested and not no_optimize_requested:
        intents.append("xtb_relax")
        hints.append("xyz_to_xtb_relax")
    if _contains_any(text, ["rmsdだけ", "rmsdのみ"]):
        intents.append("rmsd_only")
        hints.append("xyz_to_rmsd")
    if _contains_any(text, ["構造を比較", "2つの構造を比較", "原子ごとの変位"]):
        intents.append("compare_geometries")
        hints.append("compare_two_geometries")
    if _contains_any(text, ["元素数", "原子数", "fe原子の数", "炭素原子の数"]):
        intents.append("count_atoms")
        hints.append("count_element_atoms")
    if _contains_any(text, ["ファイル順", "原子番号", "1番から3番", "4番から最後"]):
        intents.append("split_by_file_order")
        hints.append("split_molecule_by_file_order")
    if _contains_any(text, ["分子量", "水素結合ドナー", "水素結合アクセプター", "hbd", "hba", "ドナー数", "アクセプター数"]):
        intents.append("descriptor_filter")
        hints.append("filter_molecules_by_descriptors")
    if _contains_any(text, ["失敗行", "エラー行", "失敗した項目を確認"]):
        intents.append("failed_rows_triage")
        hints.append("inspect_failed_rows")

    if "xyz_to_xtb_singlepoint" in hints and "xyz_to_xtb_relax" in hints and "do_not_optimize_geometry" in safety:
        hints = [h for h in hints if h != "xyz_to_xtb_relax"]
        notes.append("singlepoint intent kept; relax removed due to explicit do_not_optimize_geometry safety constraint")

    hints = sorted(set(hints))
    intents = sorted(set(intents))
    safety = sorted(set(safety))
    normalized_request = (
        f"language={lang}; intents={','.join(intents) if intents else 'none'}; "
        f"workflow_hints={','.join(hints) if hints else 'none'}; "
        f"execution_preference={execution_preference}; safety_constraints={','.join(safety) if safety else 'none'}"
    )
    return {
        "status": "ok",
        "language": lang,
        "normalized_request": normalized_request,
        "detected_intents": intents,
        "workflow_hints": hints,
        "safety_constraints": safety,
        "execution_preference": execution_preference,
        "notes": notes,
    }
