from __future__ import annotations

import re
from typing import Any

_GEOMETRY_ALIASES = {
    "octahedral": "octahedral",
    "八面体": "octahedral",
    "square planar": "square_planar",
    "square-planar": "square_planar",
    "平面四角形": "square_planar",
    "tetrahedral": "tetrahedral",
    "四面体": "tetrahedral",
}
_GEOMETRY_COORDINATION = {"octahedral": 6, "square_planar": 4, "tetrahedral": 4}
_DENTICITY = {"ammonia": 1, "nh3": 1, "chloride": 1, "ethylenediamine": 2}
_NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
}
_ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6}
_SUPPORTED_METALS = {"Fe", "Co", "Pt", "Zn", "Pd", "Ni", "Cu", "Mn", "Cr", "Ru", "Rh", "Ir"}


def _count_token_to_int(value: str | None) -> int | None:
    if not value:
        return None
    value_l = value.lower()
    if value_l.isdigit():
        return int(value_l)
    return _NUMBER_WORDS.get(value_l)


def _oxidation_state(raw: str) -> int | None:
    m = re.search(r"\(([ivx]+)\)", raw, flags=re.IGNORECASE)
    if not m:
        return None
    return _ROMAN.get(m.group(1).upper())


def _metal(raw: str) -> str | None:
    for m in re.finditer(r"(?<![A-Za-z])([A-Z][a-z]?)\s*(?:\([IVXivx]+\))?\s*(?:complex|錯体|の)", raw):
        symbol = m.group(1)
        if symbol in _SUPPORTED_METALS:
            return symbol
    m = re.search(r"\b(?:metal|core)\s*[:=]\s*([A-Z][a-z]?)\b", raw)
    if m and m.group(1) in _SUPPORTED_METALS:
        return m.group(1)
    return None


def _geometry(raw: str) -> tuple[str | None, str | None]:
    lower = raw.lower()
    if "banana-shaped" in lower or "banana shaped" in lower:
        return None, "unsupported or unknown coordination geometry: banana-shaped"
    for alias, canonical in _GEOMETRY_ALIASES.items():
        if alias in lower or alias in raw:
            return canonical, None
    return None, None


def _ligand_entry(name: str, count: int | None = None, smiles: str | None = None) -> dict[str, Any]:
    entry: dict[str, Any] = {"name": name, "source": "user_explicit"}
    if count is not None:
        entry["count"] = count
    denticity = _DENTICITY.get(name.lower())
    if denticity is not None:
        entry["denticity"] = denticity
    if smiles:
        entry["smiles"] = smiles
    return entry


def _extract_ligands(raw: str) -> list[dict[str, Any]]:
    ligands: list[dict[str, Any]] = []
    text = raw.lower()
    specs = [("ammonia", r"(?:(six|one|two|three|four|five|\d+)\s+)?ammonia(?:\s+ligands?)?"), ("NH3", r"(?:(six|one|two|three|four|five|\d+)\s+)?nh3(?:\s+ligands?)?"), ("chloride", r"(?:(six|one|two|three|four|five|\d+)\s+)?chloride(?:\s+ligands?)?"), ("ethylenediamine", r"(?:(six|one|two|three|four|five|\d+)\s+)?ethylenediamine(?:\s+ligands?)?")]
    for name, pattern in specs:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if m:
            ligands.append(_ligand_entry(name, _count_token_to_int(m.group(1))))
    ja_am = re.search(r"アンモニア\s*(\d+)\s*個", raw)
    if ja_am and not any(ligand["name"].lower() == "ammonia" for ligand in ligands):
        ligands.append(_ligand_entry("ammonia", int(ja_am.group(1))))
    # Japanese mixed examples use English ligand names with Japanese counters; fill counts when English regex missed them.
    for name in ["chloride", "ethylenediamine"]:
        m = re.search(name + r"\s*(\d+)\s*個", raw, flags=re.IGNORECASE)
        if m:
            existing = next((ligand for ligand in ligands if ligand["name"].lower() == name), None)
            if existing:
                existing["count"] = int(m.group(1))
            else:
                ligands.append(_ligand_entry(name, int(m.group(1))))
    smi = re.search(r"ligand\s+SMILES\s*[:=]?\s*([A-Za-z0-9@+\-\[\]\(\)=#$\\/%.]+)", raw, flags=re.IGNORECASE)
    if smi:
        ligands.append(_ligand_entry("ligand_smiles", None, smi.group(1)))
    return ligands


def parse_molsimplify_prompt(raw: str) -> dict[str, Any]:
    prompt = raw or ""
    lower = prompt.lower()
    requested = "molsimplify" in lower or "molsimplify" in prompt or ("metal complex" in lower and any(v in lower for v in ["build", "generate", "create"])) or "金属錯体" in prompt
    artifact_issue = None
    if "molsimplify_build_report" in lower and ("geometry input" in lower or "primary structure" in lower or "primary_structure" in lower):
        requested = True
        artifact_issue = "molsimplify_build_report is not geometry and must not be used as primary_structure input."
    if "dry-run" in lower and "molsimplify_complex_structure" in lower and ("primary structure" in lower or "primary_structure" in lower or "xtb" in lower):
        requested = True
        artifact_issue = "dry-run molsimplify_complex_structure preview is not an existing generated structure artifact or geometry."
    if not requested:
        return {"requested": False}
    geometry, issue = _geometry(prompt)
    ligands = _extract_ligands(prompt)
    metal = _metal(prompt)
    ox = _oxidation_state(prompt)
    charge_m = re.search(r"charge\s*(-?\d+)", lower)
    spin_state = None
    multiplicity = None
    if "quintet" in lower:
        spin_state, multiplicity = "quintet", 5
    mult_m = re.search(r"multiplicity\s*(\d+)", lower)
    if mult_m:
        multiplicity = int(mult_m.group(1))
    output_format = None
    if re.search(r"output\s+xyz|xyz\s*(?:format)?[.!。]?\s*$", lower):
        output_format = "xyz"
    else:
        output_format = "xyz"
    missing: list[str] = []
    if not metal and not artifact_issue:
        missing.append("metal")
    if not ligands and not artifact_issue:
        missing.append("ligands")
    if not geometry and not artifact_issue and not issue:
        missing.append("coordination_geometry_or_coordination_number")
    return {
        "requested": True,
        "artifact_issue": artifact_issue,
        "geometry_issue": issue,
        "metal": metal,
        "oxidation_state": ox,
        "charge": int(charge_m.group(1)) if charge_m else None,
        "spin_state": spin_state,
        "multiplicity": multiplicity,
        "coordination_geometry": geometry,
        "coordination_number": _GEOMETRY_COORDINATION.get(geometry) if geometry else None,
        "ligands": ligands,
        "output_format": output_format,
        "missing": missing,
    }
