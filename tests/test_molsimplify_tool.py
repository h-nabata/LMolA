from pathlib import Path
import stat

from lmola.schemas import MoleculeBuildRequest
from lmola.tools.molsimplify_tool import detect_molsimplify_cli, run_generation


def test_run_generation_unavailable_supported_case(tmp_path: Path) -> None:
    req = MoleculeBuildRequest.model_validate(
        {
            "request_type": "metal_complex",
            "metal": "Fe",
            "oxidation_state": 2,
            "ligands": [{"name": "H2O", "count": 6}],
        }
    )
    result = run_generation(req, tmp_path)
    assert result.cwd == str(tmp_path)
    assert isinstance(result.command, list)
    assert isinstance(result.generated_files, list)
    if result.status == "error":
        assert "unavailable" in result.message


def test_run_generation_unsupported_case(tmp_path: Path) -> None:
    req = MoleculeBuildRequest.model_validate(
        {
            "request_type": "metal_complex",
            "metal": "Co",
            "oxidation_state": 2,
            "ligands": [{"name": "H2O", "count": 6}],
        }
    )
    result = run_generation(req, tmp_path)
    assert result.status == "not_implemented"


def test_detect_molsimplify_cli_env_override(tmp_path: Path, monkeypatch) -> None:
    fake_exe = tmp_path / "molsimplify"
    fake_exe.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_exe.chmod(fake_exe.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("LMOLA_MOLSIMPLIFY_EXECUTABLE", str(fake_exe))
    assert detect_molsimplify_cli() == str(fake_exe.resolve())
