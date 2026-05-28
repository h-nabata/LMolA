from __future__ import annotations

import re
from typing import Any


def _contains_any(text: str, patterns: list[str]) -> bool:
    return any(p in text for p in patterns)


def _xyz_paths(raw: str) -> list[str]:
    return re.findall(r"[\w./\\-]+\.xyz\b", raw, flags=re.IGNORECASE)


def _has_xyz_path(raw: str) -> bool:
    return bool(_xyz_paths(raw))


def _has_csv_path(raw: str) -> bool:
    return bool(re.search(r"[\w./\\-]+\.csv\b", raw, flags=re.IGNORECASE))


def _is_explicit_rmsd_request(text: str) -> bool:
    return any(
        token in text
        for token in [
            "rmsd",
            "root mean square deviation",
            "root-mean-square deviation",
            "calculate rmsd",
            "rmsd between",
            "rmsd of two xyz files",
        ]
    )


def _append_evidence(evidence: list[dict[str, str]], field: str, value: str, source_text: str) -> None:
    if source_text:
        evidence.append({"field": field, "value": value, "source_text": source_text})


def _derive_workflow_hints(intent: dict[str, Any]) -> list[str]:
    method = intent.get("method")
    operation = intent.get("operation")
    input_kind = intent.get("input_kind")
    constraints = set(intent.get("constraints", []))

    hints: list[str] = []
    if method == "xtb" and operation == "singlepoint_energy" and input_kind == "xyz":
        hints.append("xyz_to_xtb_singlepoint")
    if (
        method == "xtb"
        and operation == "geometry_optimization"
        and input_kind == "xyz"
        and "do_not_optimize_geometry" not in constraints
    ):
        hints.append("xyz_to_xtb_relax")
    if operation == "descriptor_filtering" and input_kind == "smiles_csv":
        hints.append("filter_molecules_by_descriptors")
    if operation == "rmsd_calculation":
        hints.append("xyz_to_rmsd")
    if operation == "structure_comparison" and input_kind == "xyz_pair":
        hints.append("compare_two_geometries")
    if operation == "element_counting":
        hints.append("count_element_atoms")
    if operation == "molecule_splitting":
        hints.append("split_molecule_by_file_order")
    if operation == "geometry_analysis":
        hints.append("xyz_to_geometry_analysis")
    if operation == "structure_validation":
        hints.append("validate_xyz")
    if operation == "descriptor_calculation" and input_kind in {"smiles", "smiles_csv"}:
        hints.append("smiles_to_rdkit_descriptors")
    if operation == "conformer_generation" and input_kind in {"smiles", "smiles_csv"}:
        hints.append("smiles_to_conformers_rdkit")
    if operation == "format_conversion":
        hints.append("openbabel_convert_structure")
    if operation == "unsupported":
        return []
    return sorted(set(hints))


def normalize_request(request: str, language: str = "auto") -> dict[str, Any]:
    raw = (request or "").strip()
    text = raw.lower()
    lang = "ja" if language == "ja" or any("\u3040" <= ch <= "\u30ff" or "\u4e00" <= ch <= "\u9fff" for ch in raw) else "en"

    notes: list[str] = []
    safety: list[str] = []
    evidence: list[dict[str, str]] = []
    status = "ok"
    execution_preference = "unspecified"

    if _contains_any(text, ["dry-run", "ドライラン", "実行しない", "準備だけ"]):
        execution_preference = "dry_run"
        _append_evidence(evidence, "execution_preference", "dry_run", "dry-run")
    elif _contains_any(text, ["実行してよい", "安全な範囲で実行"]):
        execution_preference = "execute_safe"
        notes.append("execution permission is still controlled by deterministic external confirmation gates")

    method: str | None = None
    operation: str | None = None
    input_kind = "unknown"

    if _contains_any(text, ["xtb"]):
        method = "xtb"
        _append_evidence(evidence, "method", "xtb", "xtb")
    elif _contains_any(text, ["molsimplify", "錯体生成"]):
        method = "molsimplify"
        _append_evidence(evidence, "method", "molsimplify", "molsimplify")
    elif _contains_any(text, ["dft", "遷移状態", "反応経路", "neb", "ts search"]):
        method = "dft"
        _append_evidence(evidence, "method", "dft", "dft/ts/neb")


    if method is None and _contains_any(text, ["単一点", "シングルポイント", "single point", "singlepoint", "one-point"]):
        method = "xtb"
        _append_evidence(evidence, "method", "xtb", "singlepoint")
    xyz_paths = _xyz_paths(raw)
    if len(xyz_paths) >= 2:
        input_kind = "xyz_pair"
    elif len(xyz_paths) == 1:
        input_kind = "xyz"
    elif _has_csv_path(raw):
        input_kind = "smiles_csv"
    elif _contains_any(text, ["smiles ", "smiles:", "smiles", "スマイルズ"]) and not _has_xyz_path(raw):
        input_kind = "smiles"

    no_optimize_requested = _contains_any(text, ["構造最適化しない", "最適化は行わない", "入力構造を変更しない", "構造を変更しない", "without optimization", "without changing geometry"])
    if no_optimize_requested:
        safety.append("do_not_optimize_geometry")
        _append_evidence(evidence, "constraints", "do_not_optimize_geometry", "no optimization")
    if _contains_any(text, ["入力構造を変更しない", "構造を変更しない", "without changing geometry"]):
        safety.append("do_not_modify_input_geometry")

    singlepoint_requested = _contains_any(text, ["単一点", "一点エネルギー", "シングルポイント", "single point", "singlepoint", "single-point", "one-point"])
    energy_requested = _contains_any(text, ["エネルギー計算", "energy calculation"])
    relax_requested = _contains_any(text, ["構造最適化", "xtb最適化", "緩和", "relax geometry", "geometry optimization"])

    if _contains_any(text, ["dft", "遷移状態", "反応経路", "neb", "ts search"]):
        operation = "transition_state_search" if _contains_any(text, ["遷移状態", "ts search"]) else "reaction_path_search"
        status = "ambiguous"
        notes.append("unsupported: advanced quantum chemistry research request")
    elif _contains_any(text, ["molsimplify", "錯体生成", "八面体鉄錯体"]):
        operation = "metal_complex_generation"
        status = "ambiguous"
        notes.append("backend_unavailable if molSimplify backend is not available")
    elif _contains_any(text, ["分子量", "水素結合ドナー", "水素結合アクセプター", "hbd", "hba", "lipinski", "donor", "acceptor"]):
        operation = "descriptor_filtering"
        if input_kind == "unknown" or "csv" in text:
            input_kind = "smiles_csv"
    elif _contains_any(text, ["rmsdだけ", "rmsdのみ", "rmsd only"]) or _is_explicit_rmsd_request(text):
        operation = "rmsd_calculation"
        if input_kind == "unknown" and (_contains_any(text, ["2つ", "two", "two geometries", "2 geometries", "二つ"]) or " between " in f" {text} "):
            input_kind = "xyz_pair"
        elif input_kind == "unknown":
            input_kind = "xyz"
    elif _contains_any(text, ["構造を比較", "2つの構造を比較", "原子ごとの変位", "two geometries"]):
        operation = "structure_comparison"
        if input_kind == "unknown" and not _contains_any(text, ["2つ", "two", "二つ"]):
            input_kind = "unknown"
            notes.append("pair input implied but no explicit XYZ paths found")
        else:
            input_kind = "xyz_pair"

    elif _contains_any(text, ["validate", "valid xyz", "is a valid xyz", "検証", "妥当", "有効なxyz"]):
        operation = "structure_validation"
        if input_kind == "unknown":
            input_kind = "xyz"
    elif _contains_any(text, ["analyze the geometry", "geometry analysis", "ジオメトリ解析"]) or ("幾何" in text and "最適化" not in text):
        operation = "geometry_analysis"
        if input_kind == "unknown":
            input_kind = "xyz"
    elif _contains_any(text, ["rdkit descriptor", "descriptors", "記述子"]) and "filter" not in text:
        operation = "descriptor_calculation"
        if input_kind == "unknown":
            input_kind = "smiles_csv" if _has_csv_path(raw) else "smiles"
    elif _contains_any(text, ["conformer", "配座", "コンフォマー"]) and _contains_any(text, ["rdkit", "smiles", "スマイルズ"]):
        operation = "conformer_generation"
        if input_kind == "unknown":
            input_kind = "smiles_csv" if _has_csv_path(raw) else "smiles"
    elif _contains_any(text, ["openbabel", "open babel", "convert", "変換"]):
        operation = "format_conversion"
    elif _contains_any(text, ["元素数", "原子数", "fe原子の数", "炭素原子数", "指定元素"]):
        operation = "element_counting"
        if input_kind == "unknown":
            input_kind = "xyz"
    elif _contains_any(text, ["ファイル順", "原子番号", "1番から3番", "4番から最後", "ファイルオーダー"]):
        operation = "molecule_splitting"
        if input_kind == "unknown":
            input_kind = "xyz"
    elif method == "xtb":
        if (singlepoint_requested or (energy_requested and no_optimize_requested)):
            operation = "singlepoint_energy"
            if input_kind == "unknown":
                input_kind = "xyz"
        elif relax_requested and not no_optimize_requested:
            operation = "geometry_optimization"
            if input_kind == "unknown":
                input_kind = "xyz"
        else:
            status = "ambiguous"

    if operation:
        _append_evidence(evidence, "operation", operation, operation)

    intent = {
        "method": method,
        "operation": operation,
        "input_kind": input_kind,
        "constraints": sorted(set(safety)),
        "execution_preference": execution_preference,
        "evidence": evidence,
    }
    hints = _derive_workflow_hints(intent)

    normalized_request = (
        f"language={lang}; method={method or 'none'}; operation={operation or 'none'}; "
        f"input_kind={input_kind}; workflow_hints={','.join(hints) if hints else 'none'}; "
        f"execution_preference={execution_preference}; safety_constraints={','.join(sorted(set(safety))) if safety else 'none'}"
    )
    return {
        "status": status,
        "language": lang,
        "raw_request": raw,
        "normalized_request": normalized_request,
        "normalized_intent": intent,
        "detected_intents": sorted({f for f in [method, operation] if f}),
        "workflow_hints": hints,
        "safety_constraints": sorted(set(safety)),
        "execution_preference": execution_preference,
        "notes": notes,
    }
