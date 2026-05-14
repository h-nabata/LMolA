from lmola.io.structures import detect_structure_format, select_primary_structure_output


def test_detect_structure_format() -> None:
    assert detect_structure_format("a/b/molecule.xyz") == "xyz"


def test_select_primary_structure_output_prefers_molecule_xyz() -> None:
    generated = ["other.sdf", "molecule.sdf", "molecule.xyz"]
    assert select_primary_structure_output(generated) == "molecule.xyz"


def test_select_primary_structure_output_fallback_xyz() -> None:
    assert select_primary_structure_output(["a.xyz", "b.xyz"]) == "a.xyz"
