from __future__ import annotations

import importlib.util
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from lmola.schemas import MoleculeBuildRequest, ToolCallRecord, ToolResult


def detect_molsimplify_import() -> bool:
    return importlib.util.find_spec("molSimplify") is not None


def detect_molsimplify_cli() -> str | None:
    return shutil.which("molsimplify") or shutil.which("molSimplify")


def probe_molsimplify_help() -> ToolResult:
    exe = detect_molsimplify_cli()
    if not exe:
        return ToolResult(status="error", message="molSimplify CLI not found")
    cp = subprocess.run([exe, "--help"], capture_output=True, text=True)
    return ToolResult(
        status="ok" if cp.returncode == 0 else "error",
        message="Probed molSimplify help",
        stdout=cp.stdout[:2000],
        stderr=cp.stderr[:2000],
        returncode=cp.returncode,
        command=[exe, "--help"],
    )


def _is_supported_first_case(req: MoleculeBuildRequest) -> bool:
    if req.request_type != "metal_complex" or req.metal != "Fe" or req.oxidation_state != 2:
        return False
    if len(req.ligands) != 1:
        return False
    lig = req.ligands[0]
    return lig.name.lower() == "h2o" and lig.count == 6


def _record(tool: str, status: str, cwd: Path, command: list[str] | None = None, returncode: int | None = None, stdout: str = "", stderr: str = "") -> ToolCallRecord:
    return ToolCallRecord(
        timestamp=datetime.now(timezone.utc).isoformat(),
        tool=tool,
        command=command or [],
        cwd=str(cwd),
        returncode=returncode,
        stdout_excerpt=stdout[:2000],
        stderr_excerpt=stderr[:2000],
        status=status,
    )


def run_generation(req: MoleculeBuildRequest, run_dir: Path) -> ToolResult:
    if not _is_supported_first_case(req):
        return ToolResult(
            status="not_implemented",
            message=(
                "Only the first supported molSimplify case is implemented: "
                "metal_complex Fe(II) with one ligand entry h2o x6."
            ),
            cwd=str(run_dir),
            tool_calls=[_record("molsimplify", "not_implemented", run_dir)],
        )

    exe = detect_molsimplify_cli()
    if not exe:
        return ToolResult(
            status="error",
            message="molSimplify CLI is unavailable. Install molSimplify to enable structure generation.",
            cwd=str(run_dir),
            tool_calls=[_record("molsimplify", "error", run_dir)],
        )

    command = [
        exe,
        "legacy",
        "-core",
        "Fe",
        "-geometry",
        "oct",
        "-lig",
        "h2o",
        "-ligocc",
        "6",
        "-oxstate",
        "2",
        "-coord",
        "6",
    ]
    before = {p.resolve() for p in run_dir.rglob("*") if p.is_file()}
    cp = subprocess.run(command, cwd=run_dir, capture_output=True, text=True)
    after = [p.resolve() for p in run_dir.rglob("*") if p.is_file()]
    generated = sorted(str(p.relative_to(run_dir)) for p in after if p not in before)
    status = "ok" if cp.returncode == 0 else "error"
    return ToolResult(
        status=status,
        message="molSimplify generation command executed",
        stdout=cp.stdout[:20000],
        stderr=cp.stderr[:20000],
        returncode=cp.returncode,
        command=command,
        cwd=str(run_dir),
        generated_files=generated,
        tool_calls=[_record("molsimplify", status, run_dir, command, cp.returncode, cp.stdout, cp.stderr)],
    )
