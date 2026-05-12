from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess

from lmola.schemas import ToolCallRecord, ToolResult


class RelaxationCalculator:
    method: str

    def check_available(self) -> tuple[bool, str]:
        raise NotImplementedError

    def run(self, structure_path: Path, run_dir: Path) -> ToolResult:
        raise NotImplementedError


class XtbRelaxationCalculator(RelaxationCalculator):
    method = "xtb"

    def __init__(self) -> None:
        self.executable = shutil.which("xtb")

    def check_available(self) -> tuple[bool, str]:
        if self.executable:
            return True, "xTB executable detected"
        return False, "xTB executable is unavailable"

    def run(self, structure_path: Path, run_dir: Path) -> ToolResult:
        available, message = self.check_available()
        if not available:
            return ToolResult(status="error", message=message)

        cmd = [str(self.executable), str(structure_path.name), "--opt"]
        cp = subprocess.run(cmd, cwd=run_dir, capture_output=True, text=True)

        (run_dir / "xtb.stdout.txt").write_text(cp.stdout or "", encoding="utf-8")
        (run_dir / "xtb.stderr.txt").write_text(cp.stderr or "", encoding="utf-8")

        generated_files = sorted(str(p.relative_to(run_dir)) for p in run_dir.rglob("*") if p.is_file())
        status = "ok" if cp.returncode == 0 else "error"
        result_message = "xTB relaxation completed" if cp.returncode == 0 else "xTB relaxation failed"
        tool_call = ToolCallRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            tool="xtb",
            command=cmd,
            cwd=str(run_dir),
            returncode=cp.returncode,
            stdout_excerpt=(cp.stdout or "")[:500],
            stderr_excerpt=(cp.stderr or "")[:500],
            stdout_path="xtb.stdout.txt",
            stderr_path="xtb.stderr.txt",
            status=status,
        )
        return ToolResult(
            status=status,
            message=result_message,
            stdout=cp.stdout or "",
            stderr=cp.stderr or "",
            returncode=cp.returncode,
            command=cmd,
            cwd=str(run_dir),
            generated_files=generated_files,
            tool_calls=[tool_call],
        )


class UnsupportedRelaxationCalculator(RelaxationCalculator):
    def __init__(self, method: str) -> None:
        self.method = method

    def check_available(self) -> tuple[bool, str]:
        return False, f"Unsupported relaxation method: {self.method}"

    def run(self, structure_path: Path, run_dir: Path) -> ToolResult:
        del structure_path, run_dir
        return ToolResult(status="error", message=f"Unsupported relaxation method: {self.method}")


def get_relaxation_calculator(method: str) -> RelaxationCalculator:
    key = method.strip().lower()
    if key == "xtb":
        return XtbRelaxationCalculator()
    return UnsupportedRelaxationCalculator(method)


def write_relaxation_request(path: Path, structure: str, method: str) -> None:
    payload = {
        "operation": "relax",
        "input_structure": structure,
        "method": method,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
