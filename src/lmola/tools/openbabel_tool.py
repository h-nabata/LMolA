from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from lmola.schemas import MoleculeBuildRequest, ToolCallRecord, ToolResult

UNAVAILABLE_MESSAGE = "Open Babel CLI is unavailable. Install Open Babel to enable conversion or fallback 3D generation."


def detect_openbabel_import() -> bool:
    if importlib.util.find_spec("openbabel") is not None:
        return True
    try:
        return importlib.util.find_spec("openbabel.pybel") is not None
    except ModuleNotFoundError:
        return False


def _is_openbabel_babel(candidate: str | None) -> bool:
    if not candidate:
        return False
    try:
        cp = subprocess.run([candidate, "-V"], capture_output=True, text=True, check=False)
    except OSError:
        return False
    out = "\n".join([cp.stdout or "", cp.stderr or ""]).lower()
    return "open babel" in out


def detect_openbabel_cli() -> str | None:
    override = os.environ.get("LMOLA_OBABEL_EXECUTABLE")
    if override:
        candidate = Path(override).expanduser()
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate.resolve())
        return None
    obabel = shutil.which("obabel")
    if obabel:
        return obabel
    babel = shutil.which("babel")
    if _is_openbabel_babel(babel):
        return babel
    return None


def get_openbabel_version(executable: str | None = None) -> str | None:
    exe = executable or detect_openbabel_cli()
    if not exe:
        return None
    for args in ([exe, "-V"], [exe, "--version"]):
        try:
            cp = subprocess.run(args, capture_output=True, text=True, check=False)
        except OSError:
            continue
        text = "\n".join([cp.stdout or "", cp.stderr or ""]).strip()
        if cp.returncode == 0 and text:
            return text.splitlines()[0].strip()
    return None


def _record(status: str, run_dir: Path, command: list[str] | None = None, returncode: int | None = None, stdout: str = "", stderr: str = "") -> ToolCallRecord:
    return ToolCallRecord(
        timestamp=datetime.now(timezone.utc).isoformat(),
        tool="openbabel",
        command=command or [],
        cwd=str(run_dir),
        returncode=returncode,
        stdout_excerpt=stdout[:2000],
        stderr_excerpt=stderr[:2000],
        status=status,
    )


def _unavailable_result(run_dir: Path) -> ToolResult:
    return ToolResult(
        status="error",
        message=UNAVAILABLE_MESSAGE,
        command=[],
        cwd=str(run_dir),
        generated_files=[],
        tool_calls=[_record("error", run_dir)],
    )


def _run_and_collect(command: list[str], run_dir: Path, generated_before: set[Path], message: str) -> ToolResult:
    cp = subprocess.run(command, cwd=run_dir, shell=False, capture_output=True, text=True, check=False)
    stdout_name = "openbabel.stdout.txt"
    stderr_name = "openbabel.stderr.txt"
    (run_dir / stdout_name).write_text(cp.stdout or "", encoding="utf-8")
    (run_dir / stderr_name).write_text(cp.stderr or "", encoding="utf-8")
    after = {p.resolve() for p in run_dir.rglob("*") if p.is_file()}
    generated = sorted(str(p.relative_to(run_dir)) for p in after if p not in generated_before)
    status = "ok" if cp.returncode == 0 else "error"
    rec = _record(status, run_dir, command, cp.returncode, cp.stdout, cp.stderr).model_copy(update={"stdout_path": stdout_name, "stderr_path": stderr_name})
    return ToolResult(status=status, message=message, stdout=cp.stdout[:20000], stderr=cp.stderr[:20000], returncode=cp.returncode, command=command, cwd=str(run_dir), generated_files=generated, tool_calls=[rec])


def run_openbabel_conversion(run_dir: Path, input_path: Path, output_path: Path, gen3d: bool = False) -> ToolResult:
    exe = detect_openbabel_cli()
    if not exe:
        return _unavailable_result(run_dir)
    before = {p.resolve() for p in run_dir.rglob("*") if p.is_file()}
    command = [exe, str(input_path), "-O", str(output_path)]
    if gen3d:
        command.append("--gen3d")
    return _run_and_collect(command, run_dir, before, "Open Babel conversion command executed")


def run_openbabel_gen3d(req: MoleculeBuildRequest, run_dir: Path) -> ToolResult:
    exe = detect_openbabel_cli()
    if not exe:
        return _unavailable_result(run_dir)
    if not req.smiles:
        return ToolResult(status="error", message="Open Babel backend requires a SMILES string.", cwd=str(run_dir), tool_calls=[_record("error", run_dir)])

    smi = run_dir / "input.smi"
    smi.write_text(f"{req.smiles}\n", encoding="utf-8")
    formats = {fmt.lower() for fmt in req.build_options.output_formats}
    primary = "xyz" if "xyz" in formats else sorted(formats)[0]
    command = [exe, str(smi), "-ismi", f"-o{primary}", "-O", f"molecule.{primary}", "--gen3d"]
    if req.build_options.add_hydrogens:
        command.append("-h")
    before = {p.resolve() for p in run_dir.rglob("*") if p.is_file()}
    result = _run_and_collect(command, run_dir, before, "Open Babel fallback 3D generation executed")
    if result.status != "ok":
        return result

    generated = set(result.generated_files)
    tool_calls = list(result.tool_calls)
    for fmt in sorted(formats - {primary}):
        extra = run_openbabel_conversion(run_dir, run_dir / f"molecule.{primary}", run_dir / f"molecule.{fmt}")
        generated.update(extra.generated_files)
        tool_calls.extend(extra.tool_calls)
        if extra.status != "ok":
            return result.model_copy(update={"status": "error", "message": "Open Babel generated primary output, but secondary conversion failed.", "generated_files": sorted(generated), "tool_calls": tool_calls})
    return result.model_copy(update={"generated_files": sorted(generated), "tool_calls": tool_calls})
