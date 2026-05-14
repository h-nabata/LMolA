from __future__ import annotations

from lmola.schemas import MoleculeBuildRequest


def choose_structure_generation_backend(request: MoleculeBuildRequest, available_backends: set[str]) -> str:
    explicit = (request.backend or "").strip().lower()
    if explicit:
        return explicit

    if request.request_type == "small_molecule":
        if "rdkit" in available_backends:
            return "rdkit"
        if "openbabel" in available_backends:
            return "openbabel"
        return ""

    if request.request_type == "metal_complex":
        return "molsimplify" if "molsimplify" in available_backends else ""

    return ""


def explain_backend_choice(request: MoleculeBuildRequest, available_backends: set[str]) -> str:
    explicit = (request.backend or "").strip().lower()
    if explicit:
        return f"Using explicitly requested backend '{explicit}'."

    chosen = choose_structure_generation_backend(request, available_backends)
    if request.request_type == "small_molecule":
        if chosen == "rdkit":
            return "Small-molecule request defaulted to RDKit (preferred) because it is available."
        if chosen == "openbabel":
            return "Small-molecule request fell back to Open Babel because RDKit is unavailable."
        return "No available backend for small_molecule request; expected RDKit or Open Babel."

    if request.request_type == "metal_complex":
        if chosen == "molsimplify":
            return "Metal-complex request defaulted to molSimplify."
        return "No available backend for metal_complex request; expected molSimplify."

    return "No backend selection rule matched request_type."
