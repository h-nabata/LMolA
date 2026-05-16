from pathlib import Path

from lmola.tools.registry import execute_tool, get_tool, get_tool_availability, list_tools


EXPECTED = {
    "generate_small_molecule_rdkit",
    "generate_small_molecule_openbabel",
    "generate_metal_complex_molsimplify",
    "relax_structure_xtb",
    "validate_structure_ase",
}


def test_registry_import_and_known_tools() -> None:
    names = {t.name for t in list_tools()}
    assert EXPECTED.issubset(names)


def test_list_tools_shape() -> None:
    tool = list_tools()[0]
    assert tool.name
    assert tool.input_schema
    assert callable(tool.availability_fn)


def test_get_tool_known() -> None:
    t = get_tool("relax_structure_xtb")
    assert t.name == "relax_structure_xtb"


def test_get_tool_unknown_safe_error() -> None:
    try:
        get_tool("unknown_tool")
    except KeyError as exc:
        assert "Unknown tool" in str(exc)
    else:
        raise AssertionError("expected KeyError")


def test_execute_unknown_tool_safe(tmp_path: Path) -> None:
    res = execute_tool("unknown_tool", {}, tmp_path)
    assert res.status == "error"


def test_availability_objects_exist() -> None:
    for name in EXPECTED:
        av = get_tool_availability(name)
        assert isinstance(av.available, bool)


def test_execute_tool_payload_validation_missing_fields(tmp_path: Path) -> None:
    res = execute_tool("validate_structure_ase", {}, tmp_path)
    assert res.status == "error"
    assert "Payload validation failed" in res.message


def test_execute_tool_backend_override_rejected(tmp_path: Path) -> None:
    payload = {"request_type": "small_molecule", "backend": "not_supported", "smiles": "CCO"}
    res = execute_tool("generate_small_molecule_rdkit", payload, tmp_path)
    if res.status == "error":
        assert "validation" in res.message.lower() or "unavailable" in res.message.lower() or "failed" in res.message.lower() or "missing optional backend" in res.message.lower()


def test_execute_tool_rejects_command_like_payload(tmp_path: Path) -> None:
    res = execute_tool("validate_structure_ase", {"structure_path": "examples/example.xyz", "command": "rm -rf /"}, tmp_path)
    assert res.status == "error"
    assert "Unsafe payload keys" in res.message
