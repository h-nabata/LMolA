from __future__ import annotations
import numpy as np
from ase.io import read
from lmola.schemas import ValidationReport

def validate_xyz(path: str, expected_elements: list[str] | None = None) -> ValidationReport:
    msgs: list[str] = []
    try:
        atoms = read(path)
    except Exception as exc:
        return ValidationReport(valid=False, messages=[f"read_failed: {exc}"], atom_count=0, detected_elements=[])
    symbols = atoms.get_chemical_symbols()
    if len(symbols) == 0:
        msgs.append("no_atoms")
    if any(not s for s in symbols):
        msgs.append("missing_element_symbol")
    if expected_elements:
        missing = sorted(set(expected_elements) - set(symbols))
        if missing:
            msgs.append(f"missing_expected_elements: {missing}")
    pos = atoms.get_positions()
    if len(pos) > 1:
        dmin = np.inf
        for i in range(len(pos)):
            for j in range(i+1, len(pos)):
                d = float(np.linalg.norm(pos[i]-pos[j]))
                dmin = min(dmin, d)
        if dmin < 0.35:
            msgs.append(f"extremely_short_distance: {dmin:.3f}")
    return ValidationReport(valid=len(msgs)==0, messages=msgs, atom_count=len(symbols), detected_elements=sorted(set(symbols)))
