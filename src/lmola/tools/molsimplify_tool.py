from __future__ import annotations
import importlib.util
import shutil
import subprocess
from lmola.schemas import ToolResult

def detect_molsimplify_import() -> bool:
    return importlib.util.find_spec("molSimplify") is not None

def detect_molsimplify_cli() -> str | None:
    return shutil.which("molsimplify") or shutil.which("molSimplify")

def probe_molsimplify_help() -> ToolResult:
    exe = detect_molsimplify_cli()
    if not exe:
        return ToolResult(status="error", message="molSimplify CLI not found")
    cp = subprocess.run([exe, "--help"], capture_output=True, text=True)
    return ToolResult(status="ok" if cp.returncode == 0 else "error", message="Probed molSimplify help", stdout=cp.stdout[:2000], stderr=cp.stderr[:2000], returncode=cp.returncode, command=[exe, "--help"])

def run_generation_stub() -> ToolResult:
    return ToolResult(status="not_implemented", message="molSimplify generation execution is intentionally unimplemented in pre-alpha scaffold")
