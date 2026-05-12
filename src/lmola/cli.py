from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import typer
from rich import print

from lmola.agent.planner import plan_request
from lmola.agent.prompts import SYSTEM_PROMPT
from lmola.config import load_app_config, load_request_yaml, redacted_llm_config
from lmola.io.converters import dump_json
from lmola.io.files import create_run_dir
from lmola.io.logging import write_log
from lmola.io.run_artifacts import collect_environment, write_request_yaml, write_tool_calls
from lmola.relaxation import get_relaxation_calculator, select_relaxed_structure, write_relaxation_request
from lmola.tools.llm_client import make_llm_client
from lmola.tools.molsimplify_tool import detect_molsimplify_cli, detect_molsimplify_import, run_generation
from lmola.validation.geometry_checks import validate_xyz

app = typer.Typer(help="LMolA CLI (pre-alpha)")


def _is_importable(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


@app.command()
def doctor() -> None:
    cfg = load_app_config()
    report = {
        "molsimplify_importable": detect_molsimplify_import(),
        "molsimplify_cli": bool(detect_molsimplify_cli()),
        "ase_importable": _is_importable("ase"),
        "rdkit_importable": _is_importable("rdkit"),
        "openbabel_importable": _is_importable("openbabel"),
        "xtb_importable": _is_importable("xtb"),
        "llm_config_present": cfg.llm.model is not None or cfg.llm.base_url is not None,
        "llm_enabled": cfg.llm.enabled,
        "llm_backend": cfg.llm.backend,
        "gpu_cuda_detected": _is_importable("torch") and False,
    }
    if cfg.llm.enabled and cfg.llm.backend in {"ollama", "openai_compatible_local"} and cfg.llm.base_url:
        try:
            c = make_llm_client(cfg.llm)
            res = c.complete_json("Return {}", "{}")
            report[f"{cfg.llm.backend}_reachable"] = res.status == "ok" or bool(res.raw_response)
        except Exception:
            report[f"{cfg.llm.backend}_reachable"] = False
    print(json.dumps(report, indent=2))


@app.command()
def validate(structure: str) -> None:
    rep = validate_xyz(structure)
    print(rep.model_dump_json(indent=2))


@app.command()
def generate(input_yaml: str) -> None:
    req = load_request_yaml(input_yaml)
    run_dir = create_run_dir()
    write_request_yaml(run_dir / "request.yaml", req)
    dump_json(run_dir / "normalized_request.json", req.model_dump())
    dump_json(run_dir / "effective_config.json", req.model_dump())
    dump_json(run_dir / "environment.json", collect_environment())

    tool_result = run_generation(req, run_dir)
    write_tool_calls(run_dir / "tool_calls.jsonl", tool_result.tool_calls)
    dump_json(run_dir / "tool_result.json", tool_result.model_dump())
    write_log(run_dir / "run.log", tool_result.message)

    validation_note = "Validation not attempted: no XYZ structure generated."
    xyz_candidates = sorted(run_dir.rglob("*.xyz"))
    if xyz_candidates:
        validation = validate_xyz(str(xyz_candidates[0]))
        dump_json(run_dir / "validation_report.json", validation.model_dump())
        validation_note = f"Validated: {xyz_candidates[0].name}"
    (run_dir / "README_run.md").write_text("\n".join(["# LMolA run summary", "", f"status: {tool_result.status}", f"message: {tool_result.message}", validation_note]), encoding="utf-8")
    print(f"Created run directory: {run_dir}")


@app.command("run-agent")
def run_agent(request: str) -> None:
    rec, llm_result, parsed_request = plan_request(request)
    run_dir = create_run_dir()
    (run_dir / "natural_language_request.txt").write_text(request, encoding="utf-8")
    (run_dir / "llm_prompt.txt").write_text(f"{SYSTEM_PROMPT}\n\nUser request:\n{request}\n", encoding="utf-8")
    dump_json(run_dir / "llm_config_redacted.json", redacted_llm_config(load_app_config().llm))
    dump_json(run_dir / "environment.json", collect_environment())

    if llm_result:
        if llm_result.parsed_json is not None:
            dump_json(run_dir / "llm_response.json", llm_result.parsed_json)
        else:
            (run_dir / "llm_response.txt").write_text(llm_result.raw_response or llm_result.error_message or "", encoding="utf-8")
    if rec.status != "ok":
        write_log(run_dir / "run.log", rec.message)
        (run_dir / "README_run.md").write_text("\n".join(["# LMolA run summary", "", "status: error", f"message: {rec.message}"]), encoding="utf-8")
        print(rec.message)
        print(f"Created run directory: {run_dir}")
        raise typer.Exit(code=1)

    if parsed_request:
        write_request_yaml(run_dir / "request.yaml", parsed_request)
        dump_json(run_dir / "parsed_request.json", parsed_request.model_dump())
        dump_json(run_dir / "normalized_request.json", parsed_request.model_dump())
        dump_json(run_dir / "effective_config.json", parsed_request.model_dump())
        tool_result = run_generation(parsed_request, run_dir)
        write_tool_calls(run_dir / "tool_calls.jsonl", tool_result.tool_calls)
        dump_json(run_dir / "tool_result.json", tool_result.model_dump())
        write_log(run_dir / "run.log", tool_result.message)
        (run_dir / "README_run.md").write_text("\n".join(["# LMolA run summary", "", f"status: {tool_result.status}", f"message: {tool_result.message}"]), encoding="utf-8")
    print(f"Created run directory: {run_dir}")


@app.command("inspect-run")
def inspect_run(run_dir: str) -> None:
    path = Path(run_dir)
    output = {"run_dir": str(path), "files": sorted(entry.name for entry in path.glob("*"))}
    print(json.dumps(output, indent=2))


@app.command()
def relax(structure: str, method: str = "xtb") -> None:
    run_dir = create_run_dir()
    input_path = Path(structure)
    copied_input = run_dir / "input_structure.xyz"
    if input_path.exists():
        copied_input.write_text(input_path.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        copied_input.write_text(f"# source path not found: {structure}\n", encoding="utf-8")

    write_relaxation_request(run_dir / "relaxation_request.json", structure, method)
    dump_json(run_dir / "effective_config.json", {"operation": "relax", "method": method})
    dump_json(run_dir / "environment.json", collect_environment())

    calculator = get_relaxation_calculator(method)
    result = calculator.run(copied_input, run_dir)
    write_tool_calls(run_dir / "tool_calls.jsonl", result.tool_calls)

    selected_structure = select_relaxed_structure(run_dir)
    validation_report_path = None
    validation_note = "Validation not attempted: no XYZ structure candidate found."
    if selected_structure:
        validation = validate_xyz(str(run_dir / selected_structure))
        validation_report_path = "validation_report.json"
        dump_json(run_dir / validation_report_path, validation.model_dump())
        validation_note = f"Validated: {selected_structure}"

    result_payload = {
        **result.model_dump(),
        "status": result.status,
        "method": method,
        "message": result.message,
        "input_structure": "input_structure.xyz",
        "output_structure": selected_structure if selected_structure != "input_structure.xyz" else None,
        "generated_files": sorted(str(p.relative_to(run_dir)) for p in run_dir.rglob("*") if p.is_file()),
        "validation_report_path": validation_report_path,
        "run_dir": str(run_dir),
    }
    dump_json(run_dir / "relaxation_result.json", result_payload)
    write_log(run_dir / "run.log", result.message)

    (run_dir / "README_run.md").write_text(
        "\n".join(
            [
                "# LMolA run summary",
                "",
                f"status: {result.status}",
                f"message: {result.message}",
                f"method: {method}",
                "exit_policy: pre-alpha CLI returns JSON and avoids traceback; status is encoded in output payload.",
                "structure_selection_note: relaxed structure detection is heuristic; richer xTB parsing is future work.",
                validation_note,
            ]
        ),
        encoding="utf-8",
    )
    print(json.dumps({"status": result.status, "message": result.message, "method": method, "run_dir": str(run_dir)}, indent=2))
