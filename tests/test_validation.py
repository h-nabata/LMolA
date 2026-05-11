from lmola.validation.geometry_checks import validate_xyz

def test_validate_xyz() -> None:
    rep = validate_xyz("examples/example.xyz")
    assert rep.atom_count == 3
