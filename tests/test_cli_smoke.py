from typer.testing import CliRunner

from lmola.cli import app

runner = CliRunner()


def test_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "LMolA CLI" in result.stdout


def test_doctor() -> None:
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "molsimplify_importable" in result.stdout


def test_validate() -> None:
    result = runner.invoke(app, ["validate", "examples/example.xyz"])
    assert result.exit_code == 0
    assert '"atom_count": 3' in result.stdout
