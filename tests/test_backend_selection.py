from lmola.backends.selection import choose_structure_generation_backend, explain_backend_choice
from lmola.schemas import MoleculeBuildRequest


def _req(**kwargs):
    payload = {"request_type": "small_molecule", "smiles": "CCO"}
    payload.update(kwargs)
    return MoleculeBuildRequest.model_validate(payload)


def test_explicit_backend_respected() -> None:
    req = _req(backend="openbabel")
    assert choose_structure_generation_backend(req, {"rdkit", "openbabel"}) == "openbabel"


def test_small_molecule_prefers_rdkit() -> None:
    req = _req()
    assert choose_structure_generation_backend(req, {"rdkit", "openbabel"}) == "rdkit"


def test_small_molecule_fallback_openbabel() -> None:
    req = _req()
    assert choose_structure_generation_backend(req, {"openbabel"}) == "openbabel"


def test_metal_complex_prefers_molsimplify() -> None:
    req = MoleculeBuildRequest.model_validate({"request_type": "metal_complex", "metal": "Fe", "oxidation_state": 2, "ligands": [{"name": "h2o", "count": 6}]})
    assert choose_structure_generation_backend(req, {"molsimplify"}) == "molsimplify"
    assert "molSimplify" in explain_backend_choice(req, {"molsimplify"})
