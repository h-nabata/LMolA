from lmola.backends.registry import _parse_xtb_version, get_backend_status, list_backend_statuses
from lmola.cli import app
from typer.testing import CliRunner


runner = CliRunner()


def test_registry_lists_expected_backends() -> None:
    statuses = list_backend_statuses()
    expected = {"ase", "rdkit", "openbabel", "molsimplify", "xtb", "local_llm", "mock_llm"}
    assert expected.issubset(statuses.keys())


def test_missing_optional_backends_are_non_fatal() -> None:
    for name in ["rdkit", "openbabel", "molsimplify", "xtb"]:
        status = get_backend_status(name)
        assert status is not None
        assert isinstance(status.available, bool)


def test_doctor_includes_backend_status() -> None:
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert '"backends"' in result.stdout
    assert '"rdkit"' in result.stdout
    assert '"xtb_cli"' in result.stdout
    assert '"xtb_executable"' in result.stdout


def test_xtb_version_parser_ignores_separator_lines() -> None:
    output = "-----------------------------------------------------------\n* xtb version 6.7.1 (abc)\n-----------------------------------------------------------"
    assert _parse_xtb_version(output) == "6.7.1"


def test_xtb_version_parser_returns_none_without_semver() -> None:
    output = "-----------------------------------------------------------\nxtb release\n-----------------------------------------------------------"
    assert _parse_xtb_version(output) is None
