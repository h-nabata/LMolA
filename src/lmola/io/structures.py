from __future__ import annotations

import shutil
from pathlib import Path


def detect_structure_format(path: str | Path) -> str | None:
    suffix = Path(path).suffix.lower().lstrip(".")
    return suffix or None


def copy_structure_input(src: Path, run_dir: Path) -> Path:
    copied = run_dir / src.name
    shutil.copy2(src, copied)
    return copied


def validate_xyz_if_present(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        from ase.io import read

        atoms = read(str(path))
    except Exception:
        return False
    return bool(getattr(atoms, "positions", None) is not None and len(atoms) > 0)


def write_xyz_from_atoms_like_data(symbols: list[str], positions: list[tuple[float, float, float]], path: Path, comment: str = "LMolA generated structure") -> None:
    if len(symbols) != len(positions):
        raise ValueError("symbols and positions must have the same length")
    lines = [str(len(symbols)), comment]
    for symbol, (x, y, z) in zip(symbols, positions, strict=False):
        lines.append(f"{symbol} {x:.8f} {y:.8f} {z:.8f}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def list_structure_outputs(run_dir: Path) -> list[str]:
    names: list[str] = []
    for ext in ("*.xyz", "*.sdf"):
        names.extend(str(p.relative_to(run_dir)) for p in sorted(run_dir.rglob(ext)))
    return sorted(set(names))


def select_primary_structure_output(generated_files: list[str], preferred_names: list[str] | None = None) -> str | None:
    preferred = preferred_names or ["molecule.xyz", "molecule.sdf", "xtbopt.xyz", "input_structure.xyz"]
    generated_set = set(generated_files)
    for name in preferred:
        if name in generated_set:
            return name
    xyz = sorted(p for p in generated_files if p.lower().endswith(".xyz"))
    if xyz:
        return xyz[0]
    sdf = sorted(p for p in generated_files if p.lower().endswith(".sdf"))
    return sdf[0] if sdf else None
