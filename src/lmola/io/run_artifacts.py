from __future__ import annotations

import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

import yaml
from pydantic import BaseModel

from lmola import __version__
from lmola.schemas import ToolCallRecord
from lmola.tools.molsimplify_tool import detect_molsimplify_cli, detect_molsimplify_import
from lmola.tools.openbabel_tool import detect_openbabel_cli, detect_openbabel_import, get_openbabel_version


def _importable(name: str) -> bool:
    try:
        __import__(name)
        return True
    except Exception:
        return False


def _tool_version_from_command(cmd: list[str]) -> str | None:
    try:
        cp = subprocess.run(cmd, capture_output=True, text=True)
    except (OSError, ValueError):
        return None
    if cp.returncode != 0:
        return None
    line = (cp.stdout or cp.stderr).strip().splitlines()
    return line[0] if line else None


def collect_environment() -> dict:
    xtb_exe = shutil.which("xtb")
    obabel_exe = detect_openbabel_cli()
    return {
        "python_version": sys.version,
        "platform": platform.platform(),
        "lmola_version": __version__,
        "tools": {
            "molSimplify": {
                "importable": detect_molsimplify_import(),
                "cli": detect_molsimplify_cli(),
            },
            "ASE": {"importable": _importable("ase")},
            "RDKit": {"importable": _importable("rdkit")},
            "Open Babel": {
                "importable": detect_openbabel_import(),
                "cli": obabel_exe,
                "version": get_openbabel_version(obabel_exe),
            },
            "xTB": {
                "cli": xtb_exe,
                "version": _tool_version_from_command([xtb_exe, "--version"]) if xtb_exe else None,
            },
        },
    }


def write_tool_calls(path: Path, records: list[ToolCallRecord]) -> None:
    lines = [json.dumps(record.model_dump()) for record in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def write_request_yaml(path: Path, request: BaseModel) -> None:
    path.write_text(yaml.safe_dump(request.model_dump(), sort_keys=False), encoding="utf-8")
