from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import typer
from rich import print

from lmola.agent.planner import plan_request
from lmola.config import load_request_yaml
from lmola.io.converters import dump_json
from lmola.io.files import create_run_dir
from lmola.io.logging import write_log
from lmola.tools.molsimplify_tool import (
    detect_molsimplify_cli,
    detect_molsimplify_import,
    run_generation_stub,
)
from lmola.validation.geometry_checks import validate_xyz

app = typer.Typer(help="LMola CLI (pre-alpha)")


def _is_importable(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


@app.command()
def doctor() -> None:
    report = {
        "molsimplify_importable": detect_molsimplify_import(),
        "molsimplify_cli": bool(detect_molsimplify_cli()),
        "ase_importable": _is_importable("ase"),
        "rdkit_importable": _is_importable("rdkit"),
        "openbabel_importable": _is_importable("openbabel"),
        "xtb_importable": _is_importable("xtb"),
        "ollama_endpoint_configured": bool(
            Path.home().joinpath(".lmola", "ollama_endpoint.txt").exists()
        ),
    }
    print(json.dumps(report, indent=2))


@app.command()
def validate(structure: str) -> None:
    rep = validate_xyz(structure)
    print(rep.model_dump_json(indent=2))


@app.command()
def generate(input_yaml: str) -> None:
    req = load_request_yaml(input_yaml)
    run_dir = create_run_dir()
    request_src = Path(input_yaml)
    request_dst = run_dir / "request.yaml"
    request_dst.write_text(request_src.read_text(encoding="utf-8"), encoding="utf-8")
    dump_json(run_dir / "normalized_request.json", req.model_dump())
    tool_result = run_generation_stub()
    dump_json(run_dir / "tool_result.json", tool_result.model_dump())
    write_log(run_dir / "run.log", tool_result.message)
    (run_dir / "README_run.md").write_text("Pre-alpha run scaffold.", encoding="utf-8")
    print(f"Created run directory: {run_dir}")


@app.command("run-agent")
def run_agent(request: str) -> None:
    rec = plan_request(request)
    print(rec.model_dump_json(indent=2))


@app.command("inspect-run")
def inspect_run(run_dir: str) -> None:
    path = Path(run_dir)
    output = {"run_dir": str(path), "files": sorted(entry.name for entry in path.glob("*"))}
    print(json.dumps(output, indent=2))


@app.command()
def relax(structure: str) -> None:
    print(
        json.dumps(
            {
                "status": "not_implemented",
                "message": "xTB relaxation is optional and not yet implemented",
                "input": structure,
            },
            indent=2,
        )
    )
