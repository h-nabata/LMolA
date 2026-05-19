from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path

import typer
from rich import print

from lmola.agent.planner import plan_request
from lmola.agent.workflow_planner import plan_workflow_request
from lmola.agent.planner_eval import compare_planner_evals, run_planner_eval
from lmola.agent.prompts import SYSTEM_PROMPT
from lmola.backends.registry import list_backend_statuses
from lmola.config import load_app_config, load_request_yaml, redacted_llm_config
from lmola.io.converters import dump_json
from lmola.io.files import create_run_dir
from lmola.io.logging import write_log
from lmola.io.run_artifacts import collect_environment, write_request_yaml, write_tool_calls
from lmola.mcp_preview import (
    export_mcp_preview_bundle,
    export_mcp_tools_preview,
    render_preview,
    validate_mcp_preview_bundle,
    write_mcp_preview,
)
from lmola.mcp_agent_smoke import run_mcp_agent_smoke
from lmola.mcp_client_smoke import render_smoke_result, run_mcp_client_smoke
from lmola.mcp_runtime import RUNTIME_PHASE, call_mcp_tool, handle_jsonrpc_message, list_mcp_tools_runtime, run_mcp_stdio_server
from lmola.artifact_summary import summarize_artifact_path
from lmola.relaxation import get_relaxation_calculator, select_relaxed_structure, write_relaxation_request
from lmola.tools.llm_client import make_llm_client
from lmola.tools.molsimplify_tool import detect_molsimplify_cli, detect_molsimplify_import, run_generation
from lmola.tools.openbabel_tool import run_openbabel_conversion
from lmola.validation.geometry_checks import validate_xyz
from lmola.tools.registry import get_tool, get_tool_availability, list_tools
from lmola.workflows import get_workflow_entry, list_workflows, run_workflow_yaml
from lmola.schema_export import (
    export_all_schemas,
    export_model_schemas,
    export_tool_registry_schema,
    export_workflow_catalog_schema,
    write_schema_artifacts,
    export_planner_schema_bundle,
)

app = typer.Typer(help="LMolA CLI (pre-alpha)")


tools_app = typer.Typer(help="Typed tool registry introspection")
app.add_typer(tools_app, name="tools")

workflow_app = typer.Typer(help="Deterministic workflow catalog and runner")
app.add_typer(workflow_app, name="workflow")

schema_app = typer.Typer(help="Schema exports")
app.add_typer(schema_app, name="schema")

mcp_app = typer.Typer(help="MCP-compatible descriptor preview (static)")
app.add_typer(mcp_app, name="mcp")
artifacts_app = typer.Typer(help="Read-only LMolA artifact summarization")
app.add_typer(artifacts_app, name="artifacts")



def _emit_schema(payload: dict, fmt: str) -> None:
    if fmt == "yaml":
        typer.echo(__import__("yaml").safe_dump(payload, sort_keys=True))
    else:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@mcp_app.command("preview-tools")
def mcp_preview_tools(fmt: str = typer.Option("json", "--format")) -> None:
    typer.echo(render_preview(export_mcp_tools_preview(), fmt))


@mcp_app.command("preview")
def mcp_preview(fmt: str = typer.Option("json", "--format"), out: str = typer.Option("", "--out")) -> None:
    if out:
        typer.echo(json.dumps(write_mcp_preview(Path(out)), indent=2, sort_keys=True))
        return
    typer.echo(render_preview(export_mcp_preview_bundle(), fmt))


@mcp_app.command("validate-preview")
def mcp_validate_preview(path: str) -> None:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    data = {"tools": payload["tools"]} if "tools" in payload and "schema_version" not in payload else payload
    errors = validate_mcp_preview_bundle(data)
    result = {"status": "ok" if not errors else "error", "tool_count": len(data.get("tools", [])), "errors": errors}
    typer.echo(json.dumps(result, indent=2, sort_keys=True))
    if errors:
        raise typer.Exit(code=1)




@mcp_app.command("runtime-tools")
def mcp_runtime_tools(fmt: str = typer.Option("json", "--format")) -> None:
    typer.echo(render_preview({"runtime_phase": RUNTIME_PHASE, "server_runtime": True, "jsonrpc": False, "transport": "none/test_helper", "tools": list_mcp_tools_runtime()}, fmt))


@mcp_app.command("call-tool")
def mcp_call_tool(tool_name: str, args_json: str = typer.Option("{}", "--args-json")) -> None:
    payload = call_mcp_tool(tool_name, json.loads(args_json))
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))
    if payload.get("status") == "error":
        raise typer.Exit(code=1)


@mcp_app.command("serve-stdio")
def mcp_serve_stdio() -> None:
    run_mcp_stdio_server()


@mcp_app.command("serve-readonly")
def mcp_serve_readonly() -> None:
    run_mcp_stdio_server()


@mcp_app.command("jsonrpc")
def mcp_jsonrpc(request_json: str = typer.Option(..., "--request-json")) -> None:
    response = handle_jsonrpc_message(json.loads(request_json))
    typer.echo(json.dumps(response, indent=2, sort_keys=True))


@artifacts_app.command("summarize")
def artifacts_summarize(path: str, fmt: str = typer.Option("json", "--format"), max_items: int = typer.Option(20, "--max-items"), max_text_chars: int = typer.Option(4000, "--max-text-chars")) -> None:
    payload = summarize_artifact_path(path, max_items=max_items, max_text_chars=max_text_chars)
    if fmt != "json":
        raise typer.BadParameter("Only --format json is currently supported.")
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))
    if payload.get("status") == "error":
        raise typer.Exit(code=1)



@mcp_app.command("agent-smoke")
def mcp_agent_smoke(
    backend: str = typer.Option("mock", "--backend"),
    model: str = typer.Option("", "--model"),
    base_url: str = typer.Option("http://127.0.0.1:11434", "--base-url"),
    task: str = typer.Option("Generate structures from examples/smiles_list.csv and relax them with xTB. Use dry-run only.", "--task"),
    fmt: str = typer.Option("json", "--format"),
    timeout_seconds: float = typer.Option(20.0, "--timeout-seconds"),
    temperature: float = typer.Option(0.0, "--temperature"),
    max_tokens: int = typer.Option(800, "--max-tokens"),
    out_dir: str = typer.Option("", "--out-dir"),
    allow_confirmed_execution: bool = typer.Option(False, "--allow-confirmed-execution"),
    confirm_execution: bool = typer.Option(False, "--confirm-execution"),
) -> None:
    result = run_mcp_agent_smoke(
        task=task,
        backend=backend,
        model=model,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
        temperature=temperature,
        max_tokens=max_tokens,
        out_dir=out_dir,
        allow_confirmed_execution=allow_confirmed_execution,
        confirm_execution=confirm_execution,
    )
    typer.echo(render_smoke_result(result, fmt))
    if result.get("status") != "ok":
        raise typer.Exit(code=1)

@mcp_app.command("client-smoke")
def mcp_client_smoke(fmt: str = typer.Option("json", "--format"), timeout_seconds: float = typer.Option(10.0, "--timeout-seconds")) -> None:
    result = run_mcp_client_smoke(timeout_seconds=timeout_seconds)
    typer.echo(render_smoke_result(result, fmt))
    if result.get("status") != "ok":
        raise typer.Exit(code=1)

@schema_app.command("export")
def schema_export(fmt: str = typer.Option("json", "--format"), out: str = typer.Option("", "--out")) -> None:
    if out:
        typer.echo(json.dumps(write_schema_artifacts(out), indent=2, sort_keys=True))
        return
    _emit_schema(export_all_schemas(), fmt)


@schema_app.command("export-models")
def schema_export_models(fmt: str = typer.Option("json", "--format")) -> None:
    _emit_schema(export_model_schemas(), fmt)


@tools_app.command("export-schema")
def tools_export_schema(fmt: str = typer.Option("json", "--format")) -> None:
    _emit_schema(export_tool_registry_schema(), fmt)


@workflow_app.command("export-catalog")
def workflow_export_catalog(fmt: str = typer.Option("json", "--format")) -> None:
    _emit_schema(export_workflow_catalog_schema(compact=False), fmt)


@workflow_app.command("planner-context")
def workflow_planner_context(fmt: str = typer.Option("json", "--format")) -> None:
    _emit_schema(export_planner_schema_bundle(), fmt)
@workflow_app.command("list")
def workflow_list() -> None:
    payload = [w.model_dump() for w in list_workflows()]
    print(json.dumps(payload, indent=2))


@workflow_app.command("inspect")
def workflow_inspect(workflow_id: str) -> None:
    try:
        entry = get_workflow_entry(workflow_id)
    except KeyError as exc:
        raise typer.BadParameter(str(exc)) from exc
    print(json.dumps(entry.model_dump(), indent=2))




@workflow_app.command("plan")
def workflow_plan(request: str) -> None:
    result = plan_workflow_request(request, write_artifacts=True)
    print(result.model_dump_json(indent=2))
    if result.status != "ok":
        raise typer.Exit(code=1)


@workflow_app.command("eval-planner")
def workflow_eval_planner(eval_cases_yaml: str) -> None:
    result = run_planner_eval(eval_cases_yaml)
    payload = {
        "status": result.status,
        "message": result.message,
        "eval_dir": result.eval_dir,
        "total_cases": result.total_cases,
        "passed_cases": result.passed_cases,
        "failed_cases": result.failed_cases,
        "pass_rate": result.pass_rate,
        "summary_csv": result.summary_csv,
        "summary_json": result.summary_json,
    }
    print(json.dumps(payload, indent=2))
    if result.status != "ok":
        raise typer.Exit(code=1)


@workflow_app.command("compare-planner-evals")
def workflow_compare_planner_evals(eval_dir_a: str, eval_dir_b: str) -> None:
    print(json.dumps(compare_planner_evals(eval_dir_a, eval_dir_b), indent=2))


@workflow_app.command("run")
def workflow_run(workflow_yaml: str) -> None:
    result = run_workflow_yaml(workflow_yaml)
    print(result.model_dump_json(indent=2))
    if result.status != "ok":
        raise typer.Exit(code=1)




@tools_app.command("list")
def tools_list() -> None:
    payload = [
        {
            "name": t.name,
            "category": t.category,
            "input_schema": t.input_schema,
            "required_backends": t.required_backends,
        }
        for t in list_tools()
    ]
    print(json.dumps(payload, indent=2))


@tools_app.command("inspect")
def tools_inspect(tool_name: str) -> None:
    try:
        tool = get_tool(tool_name)
    except KeyError as exc:
        raise typer.BadParameter(str(exc)) from exc
    availability = get_tool_availability(tool_name)
    payload = {
        "name": tool.name,
        "description": tool.description,
        "category": tool.category,
        "input_schema": tool.input_schema,
        "output_description": tool.output_description,
        "required_backends": tool.required_backends,
        "notes": tool.notes,
        "availability": availability.model_dump(),
    }
    print(json.dumps(payload, indent=2))


@app.command()
def doctor() -> None:
    cfg = load_app_config()
    molsimplify_cli = detect_molsimplify_cli()
    backend_statuses = list_backend_statuses()
    python_cuda_detected = _detect_python_cuda()
    report = {
        "molsimplify_importable": detect_molsimplify_import(),
        "molsimplify_cli": bool(molsimplify_cli),
        "molsimplify_executable": molsimplify_cli,
        "ase_importable": backend_statuses["ase"].importable,
        "rdkit_importable": backend_statuses["rdkit"].importable,
        "openbabel_importable": backend_statuses["openbabel"].importable,
        "openbabel_cli": bool(backend_statuses["openbabel"].executable),
        "openbabel_executable": backend_statuses["openbabel"].executable,
        "openbabel_version": backend_statuses["openbabel"].version,
        "xtb_importable": backend_statuses["xtb"].importable,
        "xtb_cli": bool(backend_statuses["xtb"].executable),
        "xtb_executable": backend_statuses["xtb"].executable,
        "llm_config_present": cfg.llm.model is not None or cfg.llm.base_url is not None,
        "llm_enabled": cfg.llm.enabled,
        "llm_backend": cfg.llm.backend,
        "python_cuda_detected": python_cuda_detected,
        "gpu_cuda_detected": python_cuda_detected,
        "gpu_detection_scope": "python_environment",
        "backends": {name: status.__dict__ for name, status in backend_statuses.items()},
    }
    if report["gpu_cuda_detected"] is not None:
        report["gpu_cuda_detected_deprecated"] = report["gpu_cuda_detected"]
    if cfg.llm.enabled and cfg.llm.backend in {"ollama", "openai_compatible_local"} and cfg.llm.base_url:
        try:
            c = make_llm_client(cfg.llm)
            res = c.complete_json("Return {}", "{}")
            report[f"{cfg.llm.backend}_reachable"] = res.status == "ok" or bool(res.raw_response)
        except Exception:
            report[f"{cfg.llm.backend}_reachable"] = False
    if cfg.llm.enabled and cfg.llm.backend == "ollama":
        report.update(_collect_ollama_diagnostics(cfg.llm.base_url, cfg.llm.model, cfg.llm.timeout_seconds))
    typer.echo(json.dumps(report, indent=2))


def _detect_python_cuda() -> bool:
    try:
        torch = import_module("torch")
    except Exception:
        return False
    try:
        return bool(torch.cuda.is_available())
    except Exception:
        return False


def _collect_ollama_diagnostics(base_url: str | None, model: str | None, timeout_seconds: int) -> dict:
    report = {
        "ollama_reachable": False,
        "ollama_base_url": base_url,
        "ollama_configured_model": model,
        "ollama_configured_model_available": None,
        "ollama_available_models": None,
        "ollama_loaded_models": None,
        "ollama_error": None,
        "ollama_ps_error": None,
    }
    if not base_url:
        report["ollama_error"] = "No Ollama base URL configured."
        return report

    from httpx import Client

    try:
        with Client(timeout=timeout_seconds) as client:
            resp = client.get(f"{base_url.rstrip('/')}/api/tags")
            resp.raise_for_status()
            payload = resp.json()
            models = [m.get("name") for m in payload.get("models", []) if isinstance(m, dict) and m.get("name")]
            report["ollama_reachable"] = True
            report["ollama_available_models"] = models
            if model:
                report["ollama_configured_model_available"] = model in models
    except Exception as exc:
        report["ollama_error"] = str(exc)
        return report

    try:
        with Client(timeout=timeout_seconds) as client:
            resp = client.get(f"{base_url.rstrip('/')}/api/ps")
            resp.raise_for_status()
            payload = resp.json()
            loaded = [m.get("name") for m in payload.get("models", []) if isinstance(m, dict) and m.get("name")]
            report["ollama_loaded_models"] = loaded
    except Exception as exc:
        report["ollama_ps_error"] = str(exc)
    return report


@app.command()
def validate(structure: str) -> None:
    rep = validate_xyz(structure)
    print(rep.model_dump_json(indent=2))




@app.command()
def convert(input_path: str, to: str = typer.Option("", "--to"), output: str = typer.Option("", "--output")) -> None:
    run_dir = create_run_dir()
    src = Path(input_path)
    if not src.exists():
        raise typer.BadParameter(f"Input file not found: {input_path}")
    copied = run_dir / src.name
    copied.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    if output:
        out = run_dir / Path(output).name
    elif to:
        out = run_dir / f"{src.stem}.{to.lower()}"
    else:
        raise typer.BadParameter("Specify --to or --output")

    dump_json(run_dir / "environment.json", collect_environment())
    result = run_openbabel_conversion(run_dir, copied, out, gen3d=src.suffix.lower() in {".smi", ".smiles"} and out.suffix.lower() == ".xyz")
    write_tool_calls(run_dir / "tool_calls.jsonl", result.tool_calls)
    payload = result.model_dump() | {"run_dir": str(run_dir), "artifact_files": ["environment.json", "tool_calls.jsonl", "conversion_result.json", "README_run.md"]}

    if out.suffix.lower() == ".xyz" and out.exists():
        validation = validate_xyz(str(out))
        dump_json(run_dir / "validation_report.json", validation.model_dump())
        payload["validation_report_path"] = "validation_report.json"
        payload["artifact_files"].append("validation_report.json")

    dump_json(run_dir / "conversion_result.json", payload)
    (run_dir / "README_run.md").write_text("\n".join(["# LMolA conversion run", "", f"status: {result.status}", f"message: {result.message}"]), encoding="utf-8")
    print(f"Created run directory: {run_dir}")


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
    artifact_files = [
        "request.yaml",
        "normalized_request.json",
        "effective_config.json",
        "environment.json",
        "tool_calls.jsonl",
        "tool_result.json",
        "run.log",
        "README_run.md",
    ]
    payload = tool_result.model_dump() | {"run_dir": str(run_dir), "artifact_files": artifact_files}
    dump_json(run_dir / "tool_result.json", payload)
    write_log(run_dir / "run.log", tool_result.message)

    validation_note = "Validation not attempted: no XYZ structure generated."
    xyz_candidates = sorted(run_dir.rglob("*.xyz"))
    if xyz_candidates:
        validation = validate_xyz(str(xyz_candidates[0]))
        dump_json(run_dir / "validation_report.json", validation.model_dump())
        artifact_files.append("validation_report.json")
        validation_note = f"Validated: {xyz_candidates[0].name}"
    (run_dir / "README_run.md").write_text("\n".join(["# LMolA run summary", "", f"status: {tool_result.status}", f"message: {tool_result.message}", validation_note]), encoding="utf-8")
    dump_json(run_dir / "tool_result.json", payload | {"artifact_files": sorted(set(artifact_files))})
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

    artifact_files = [
        "effective_config.json",
        "environment.json",
        "input_structure.xyz",
        "relaxation_request.json",
        "tool_calls.jsonl",
    ]

    selected_structure = select_relaxed_structure(run_dir)
    validation_report_path = None
    validation_note = "Validation not attempted: no XYZ structure candidate found."
    if selected_structure:
        validation = validate_xyz(str(run_dir / selected_structure))
        validation_report_path = "validation_report.json"
        dump_json(run_dir / validation_report_path, validation.model_dump())
        artifact_files.append(validation_report_path)
        validation_note = f"Validated: {selected_structure}"

    result_payload = {
        **result.model_dump(),
        "status": result.status,
        "method": method,
        "message": result.message,
        "input_structure": "input_structure.xyz",
        "output_structure": selected_structure if selected_structure != "input_structure.xyz" else None,
        "generated_files": result.generated_files,
        "artifact_files": artifact_files,
        "validation_report_path": validation_report_path,
        "run_dir": str(run_dir),
    }
    dump_json(run_dir / "relaxation_result.json", result_payload)
    artifact_files.append("relaxation_result.json")
    write_log(run_dir / "run.log", result.message)
    artifact_files.append("run.log")

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
    artifact_files.append("README_run.md")
    dump_json(run_dir / "relaxation_result.json", result_payload | {"artifact_files": sorted(set(artifact_files))})
    print(json.dumps({"status": result.status, "message": result.message, "method": method, "run_dir": str(run_dir)}, indent=2))
