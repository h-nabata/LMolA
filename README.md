# LMolA (Pre-alpha)

Local molecular structure agents.

## Overview
LMolA is a local-first, offline-capable Python toolkit scaffold for orchestrating molecular structure generation requests, structure validation, and optional relaxation workflows for computational chemistry research.

## What LMolA does
- Validates deterministic YAML/JSON molecular build requests.
- Provides a safe CLI scaffold for generation, validation, and run inspection.
- Probes optional external tool availability (molSimplify, RDKit, Open Babel, xTB, local LLM endpoint).

## What LMolA does not do
- It does not have production structure generation yet.
- It does not let LLMs directly generate 3D structures.
- It does not perform synthesis planning or hazardous procedure generation.

## Design philosophy
- Deterministic-first: YAML/JSON interfaces first.
- Offline/local-first: no cloud API required.
- Safe-by-default: optional integrations fail clearly.

## Installation
See [INSTALL.md](INSTALL.md).

## Backend installation profiles

| Backend | Purpose | Extra | Recommended install route | Required for default tests? |
|---|---|---|---|---|
| ASE | structure parsing/validation | base dependency | pip via base install | Yes |
| RDKit | future structure generation | `rdkit`, `chem-light` | Prefer conda/mamba (`conda-forge`) or `pip install -e ".[rdkit]"` | No |
| Open Babel | future conversion/gen3d | `openbabel` | Prefer conda/mamba first; pip bindings can be environment-sensitive | No |
| molSimplify | inorganic generation (optional) | `molsimplify`, `chem-inorganic` | `pip install -e ".[molsimplify]"` or conda/mamba/source install | No |
| xTB | relaxation executable | none (CLI tool) | Install `xtb` via conda-forge/mamba; not a Python dependency | No (`external_tools` only) |
| local LLM (Ollama/OpenAI-compatible local) | NL request parsing | none | Local endpoint + `.lmola/config.yaml` | No |
| mock LLM | test/offline fallback | none | Built-in | No |

Optional extras policy:
- Keep base install lightweight.
- Install only what you need: `pip install -e ".[dev]"`, then add `.[rdkit]`, `.[openbabel]`, or `.[molsimplify]` as needed.
- `all` intentionally excludes fragile chemistry stacks.


## Quick start
```bash
pip install -e ".[dev]"
lmola doctor
lmola validate examples/example.xyz
lmola generate examples/generic_octahedral.yaml
```

## YAML input example
```yaml
request_type: metal_complex
metal: Fe
oxidation_state: 2
ligands:
  - name: H2O
    count: 6
```

## CLI commands
- `lmola doctor`
- `lmola validate STRUCTURE.xyz`
- `lmola generate INPUT.yaml`
- `lmola run-agent "prompt"`
- `lmola inspect-run outputs/run_xxx`
- `lmola relax STRUCTURE.xyz --method xtb`

## Offline/local-first policy
No cloud APIs by default. No automatic model downloads.

## molSimplify integration status (optional)
LMolA supports a narrow first external generation case only:
- `request_type: metal_complex`
- `metal: Fe`, `oxidation_state: 2`
- one ligand entry `H2O`/`h2o` with `count: 6`

`molSimplify` is optional and never auto-installed. Default tests and CI do not require molSimplify.

Install options:
- LMolA extra (keeps molSimplify optional): `pip install -e ".[molsimplify]"`
- quick pip route: `pip install molSimplify`
- robust chemistry environment: use conda/mamba for base environment management, then install LMolA and molSimplify
- newest molSimplify behavior: install from the molSimplify GitHub source

Notes:
- `molSimplify` is kept in a dedicated optional extra and is **not** in base dependencies.
- `all` does not include `molSimplify`, avoiding heavy chemistry dependencies in general-purpose installs.

Manual run:
```bash
lmola generate examples/fe_h2o6.yaml
```

Manual external verification:
```bash
pytest -m external_tools -q
```

Behavior:
- If molSimplify is unavailable, LMolA safely records `status: error` and run artifacts.
- If molSimplify is available, LMolA executes the CLI, records command/cwd/returncode and stdout/stderr artifacts, and attempts XYZ validation when a structure is generated.

Optional executable override:
- Set `LMOLA_MOLSIMPLIFY_EXECUTABLE=/path/to/molsimplify` to force a specific executable.
- Otherwise LMolA detects from `PATH` (`molsimplify`, then `molSimplify`).

## Validation workflow
ASE-backed file parsing and lightweight geometry/chemistry checks with JSON report output.

## Optional LLM mode
Natural-language mode is intentionally unimplemented unless local endpoint configuration is explicitly provided.

## Limitations
This is a safe scaffold and not chemically complete automation.

## Safety and responsible use
LMolA is for computational model construction and validation only, not experimental synthesis guidance.

## Citation
See [CITATION.cff](CITATION.cff).

## License
MIT (see [LICENSE](LICENSE)).

## Phase 4.0 local LLM mode (experimental)
LMolA supports optional local-first natural language request translation only. Deterministic YAML/JSON generate remains primary.

Supported backends in Phase 4.0:
- `ollama` (local Ollama endpoint, default base URL commonly `http://localhost:11434`)
- `openai_compatible_local` (local OpenAI-compatible servers such as LM Studio, vLLM, llama.cpp server)
- `mock` (tests only)

Not supported in Phase 4.0:
- OpenAI cloud API
- Anthropic cloud API
- automatic model downloads
- arbitrary tool execution from LLM output

Create `.lmola/config.yaml`:
```yaml
llm:
  enabled: true
  backend: ollama
  base_url: http://localhost:11434
  model: qwen2.5-coder:14b-instruct
  timeout_seconds: 180
```

If not configured, `lmola run-agent` fails safely with a clear message and does not call cloud APIs.
GPU is optional; CPU-only workflows remain supported for doctor/validate/generate/tests.

Doctor diagnostics notes:
- `python_cuda_detected` / `gpu_cuda_detected` reports CUDA visibility in the LMolA Python environment (`gpu_detection_scope=python_environment`).
- This does **not** guarantee Ollama runtime GPU usage.
- To check Ollama GPU usage directly, run: `ollama ps`, `nvidia-smi`, `watch -n 1 nvidia-smi`.
- To confirm model configuration and availability, compare: `lmola doctor` and `ollama list`.


## Relaxation workflow (Phase 5.1)
`xTB` is optional and never auto-installed. Run:
```bash
lmola relax examples/example.xyz --method xtb
```
If xTB is unavailable, LMolA does **not** traceback; it writes artifacts and reports `status: error` in JSON output (pre-alpha exit policy).

Expected relax artifacts:
- `input_structure.xyz`
- `relaxation_request.json`
- `effective_config.json`
- `environment.json`
- `tool_calls.jsonl`
- `relaxation_result.json`
- `run.log`
- `README_run.md`
- `validation_report.json` (when validation runs)

Structure selection is heuristic (`xtbopt.xyz` preferred). Rich xTB parsing is future work.

## Test policy for external tools
Default tests must not require xTB, molSimplify, RDKit, Open Babel, Ollama, GPU, or cloud APIs. Tests requiring real external tools are marked `external_tools` and are skipped by default.

Run default tests (no external tools):
```bash
pytest -m "not external_tools" -q
```

Run real xTB verification only when xTB is installed:
```bash
pytest -m external_tools -q
```

Expected behavior:
- If xTB is unavailable, relax returns `status: error` with a clear unavailability message and still writes artifacts.
- If xTB is available, LMolA invokes xTB without `shell=True`, records command/cwd/returncode, and captures stdout/stderr artifacts.

## Scientific-use reminder
Relaxed structures are computational models and require researcher review before downstream scientific use.


RDKit small-molecule generation is optional and supports SMILES->3D initial structures via `lmola generate examples/ethanol_smiles.yaml` and minimal conformer ensembles via `lmola generate examples/ethanol_conformers.yaml`. Conformer energies are force-field estimates only (UFF/MMFF) and are not quantum-chemical energies. Ensemble generation may fail for some SMILES, and generated conformers require researcher review.


## Open Babel (Phase 8.0)
Open Babel is optional and CLI-first (`obabel`). RDKit remains the primary small-organic SMILES-to-3D backend; Open Babel is a fallback and conversion backend. Generated structures must be reviewed by researchers and may differ from RDKit.

- Install via conda/mamba (recommended): `conda install -c conda-forge openbabel` or `mamba install -c conda-forge openbabel`.
- Optional extra: `pip install -e ".[openbabel]"` (bindings may be environment-sensitive).
- Generate fallback 3D: `lmola generate examples/ethanol_openbabel.yaml`
- Convert formats: `lmola convert examples/example.xyz --to sdf` and `lmola convert examples/example.sdf --to xyz`.

## Backend selection policy (Phase 8.5)
- **small_molecule (SMILES):** prefer `rdkit`; fallback to `openbabel` when RDKit is unavailable.
- **metal_complex:** prefer `molsimplify`.
- **relaxation:** `xtb` is currently supported.
- **validation:** ASE-based sanity checks are used when XYZ outputs are present.

### Expected structure outputs
- Primary generated structure should be `molecule.xyz` where available.
- `molecule.sdf` may be produced when requested/supported.
- xTB relaxation should produce `xtbopt.xyz`.
- Validation runs write `validation_report.json`.

> Generated structures are initial computational models and must be reviewed by a researcher before scientific use.

## Typed Tool Registry

LMolA now includes a typed, schema-validated tool registry intended as a stable interface between future local LLM agents and existing LMolA chemistry backends. Agents should call registered tools rather than arbitrary shell commands.

Current tools wrap existing RDKit, Open Babel, molSimplify, xTB, and ASE-backed functionality. Optional dependencies remain optional: if a backend is missing, the corresponding tool is reported unavailable instead of failing the whole system.

This is groundwork for future local LLM and multi-agent orchestration; autonomous agent behavior and environment switching are not implemented in this phase.

## Minimal Workflow Layer (Phase 9.5)

LMolA now supports deterministic, schema-validated workflow YAML execution (no LLM planning in this phase).

### Task taxonomy
- structure_generation
- conformer_generation
- conversion
- validation
- relaxation
- batch_processing
- summarization

### Workflow catalog
- smiles_to_3d_rdkit
- smiles_to_conformers_rdkit
- smiles_to_3d_openbabel
- smiles_to_xtb_relax
- xyz_to_xtb_relax
- validate_xyz

### Run workflows
- `lmola workflow list`
- `lmola workflow inspect smiles_to_xtb_relax`
- `lmola workflow run examples/workflow_smiles_to_xtb.yaml`

Future local LLM agents are expected to translate natural language into workflow YAML. LMolA then validates and executes deterministically.

Warning: generated structures are initial computational models and require researcher review.


## Workflow summary schema (Phase 9.5.2 cleanup)

`summary.csv` is intended for human inspection. `summary.json` is intended for downstream automation and future local LLM/agent consumption once planner integration is added.

Field conventions:
- `primary_structure`: backend-relative artifact name (for example `molecule.xyz`).
- `primary_structure_path`: resolved filesystem path to `primary_structure`.
- `relaxed_structure`: backend-relative artifact name (for example `xtbopt.xyz`).
- `relaxed_structure_path`: resolved filesystem path to `relaxed_structure`.
- `conformer_ensemble_path`: path to `conformer_ensemble.json` only (when present).
- `sdf_path`: path to `.sdf` output when produced; this is separate from conformer ensemble metadata.

Status policy:
- `ok_count`: items where all required workflow steps succeeded.
- `error_count`: items where one or more required workflow steps failed.
- Workflow engine completion may still return `status: ok` with message `Workflow executed with item errors` when item-level failures occur.

This remains deterministic execution of explicit YAML only. Real LLM workflow planning, autonomous agent execution, CREST conformer search, and reaction-path planning are not implemented in this phase.

## Local LLM workflow planning (Phase 10.1)

LMolA now supports local-first workflow planning from natural language via:

```bash
lmola workflow plan "Generate structures from examples/smiles_list.csv and relax them with xTB."
```

Key points:
- Local-first planning in this phase (`mock`, `ollama`, `openai_compatible_local`).
- No single serving platform is required (Ollama or any OpenAI-compatible local server can be used).
- Cloud hosted APIs are not enabled.
- LLM output is planning-only and never executed directly.
- `planned_workflow.*` is the validated LLM proposal (may keep `steps: null`).
- `canonical_workflow.*` is catalog-expanded and execution-ready.
- Default behavior is dry-run planning (no execution). If execution is added, it must require explicit `--execute`.
- Unsupported tasks return structured safe errors.

Example local configs:

```yaml
llm:
  enabled: true
  backend: ollama
  base_url: http://127.0.0.1:11434
  model: qwen2.5-coder:14b
  temperature: 0
  timeout_seconds: 180
```

```yaml
llm:
  enabled: true
  backend: openai_compatible_local
  base_url: http://127.0.0.1:1234/v1
  model: local-model-name
  temperature: 0
  timeout_seconds: 180
```

Typical planning artifacts are written under `outputs/plan_.../` and include:
- `natural_language_request.txt`
- `planner_prompt.txt`
- `llm_response.raw.txt`
- `planned_workflow.yaml`
- `planned_workflow.json`
- `canonical_workflow.yaml`
- `canonical_workflow.json`
- `planning_result.json`
- `README_plan.md`

Generated and relaxed structures always require researcher review.


## Real local LLM planner evaluation (Phase 10.6)

Use planner evaluation to measure planning quality only (no workflow execution):

```bash
lmola workflow eval-planner examples/planner_eval_cases.yaml
```

- Uses the same planner pipeline as `lmola workflow plan`.
- Writes `eval_summary.csv`, `eval_summary.json`, and `eval_result.json` under `outputs/eval_...`.
- Supports `mock`, `ollama`, and `openai_compatible_local` via existing LLM config.
- For LM Studio / vLLM / llama.cpp server / text-generation-webui, use `openai_compatible_local` when they expose a local OpenAI-compatible endpoint.
- Default tests use mock only.
- Security remains unchanged: endpoint safety checks apply and public remote endpoints are blocked unless unsafe override is explicitly enabled.

Example Ollama config:

```yaml
llm:
  enabled: true
  backend: ollama
  base_url: http://127.0.0.1:11434
  model: qwen2.5-coder:14b
  temperature: 0
  timeout_seconds: 180
  max_tokens: 2048
```

Example OpenAI-compatible local config:

```yaml
llm:
  enabled: true
  backend: openai_compatible_local
  base_url: http://127.0.0.1:1234/v1
  model: local-model-name
  temperature: 0
  timeout_seconds: 180
  max_tokens: 2048
```

Evaluation metrics include `workflow_match`, `tools_match`, `parse_ok`, `validation_ok`, `canonicalization_ok`, `unsupported_handled`, and overall `pass_rate`.


### Phase 10.6 baseline interpretation notes

- `qwen2.5-coder:14b` is used as a structured JSON/workflow planner, not a chemistry correctness authority.
- Chemical correctness, charge/spin checks, canonicalization, and unsupported-task refusal remain deterministic LMolA responsibilities.
- `eval-planner` measures planning only and does not execute chemistry workflows.
- Mock backend remains the default in automated tests; expected mock pass rate is `1.0` for the baseline suite.
- Real local LLM pass rate may be lower; failures are reported and classified with `failure_category` (not hidden).
- Prompt optimization is intentionally deferred to later schema-driven phases.

Manual qwen2.5-coder baseline run:

1. Copy `examples/config_ollama_qwen2_5_coder_14b.yaml` into `.lmola/config.yaml` and adjust only if needed.
2. Run `lmola doctor` and confirm `llm_backend=ollama` and `ollama_reachable=true`.
3. Run `lmola workflow plan "Generate structures from examples/smiles_list.csv and relax them with xTB."`.
4. Run `lmola workflow eval-planner examples/planner_eval_cases.yaml`.
5. Inspect `eval_summary.csv` and `eval_result.json` in the generated `outputs/eval_*` directory.

## Schema-driven LMolA agents

LMolA agents should generate `WorkflowRequest` JSON as the stable interface. LLM choice is independent from schema exports. Ollama with `qwen2.5-coder:14b` is one tested local engine, but schema export is LLM-engine agnostic.

- Exported artifacts are generated from internal Pydantic models, Tool Registry, and Workflow Catalog.
- LLM output is never executed directly; it is parsed, validated, canonicalized, and then optionally executed by deterministic LMolA code.
- YAML remains convenient for humans; JSON is preferred for LLM output and schema validation.

Commands:
- `lmola schema export --format json`
- `lmola schema export --out outputs/schema_test`
- `lmola tools export-schema --format json`
- `lmola workflow export-catalog --format json`
- `lmola workflow export-catalog --format yaml`

Schema export contract:
- `schema_bundle.json` uses `models` as a direct `{model_name: json_schema}` mapping.
- `model_schemas.json` remains the standalone model schema bundle (`schema_version=lmola.models.v1`).
- `--out` writes files directly into the exact requested directory (creating it if needed).

Roadmap:
- Phase 11.1: schema-driven planner prompts.
- Phase 11.5: MCP-compatible descriptor preview.
- Phase 12: MCP adapter.

## MCP-compatible descriptor preview (Phase 11.5)

LMolA now supports **static MCP-compatible descriptor preview export** (tools/list-style shape) to stabilize descriptor conversion before runtime adapter work.

- This does **not** start an MCP server.
- This does **not** implement JSON-RPC transport.
- This does **not** implement runtime `tools/call`.
- Standard descriptor fields are: `name`, `description`, `inputSchema`.
- LMolA-specific metadata is namespaced under `_meta.lmola`.
- High-level workflow descriptors are preferred for external agents.
- Low-level chemistry tool descriptors are included for advanced integrations and are marked as low-level.
- `lmola.run_workflow` is marked with side effects and requires confirmation metadata for future runtime integration.

Commands:
- `lmola mcp preview-tools --format json`
- `lmola mcp preview-tools --format yaml`
- `lmola mcp preview --out outputs/mcp_preview_manual_test`
- `lmola mcp validate-preview outputs/mcp_preview_manual_test/mcp_preview_bundle.json`

## Schema-driven planner prompt (Phase 11.1)
- Planner prompts are generated from LMolA schema/catalog context (`planner_context_compact`) and are LLM-engine independent.
- The planner asks the LLM to return JSON only: either a supported `WorkflowRequest` object or `{"status":"unsupported","reason":"..."}`.
- LMolA parses, validates, and canonicalizes planner output; LLM output is never executed directly.
- Ollama/qwen2.5-coder:14b is a tested local backend, not a schema dependency.
- `lmola workflow plan` stores debug artifacts: `planner_context_compact.json` and `planner_prompt.txt` in `plan_dir`.
- Full MCP descriptor generation remains Phase 11.5, and MCP server/runtime remains Phase 12.

## Phase 12.0 read-only MCP runtime adapter

LMolA now includes a **minimal MCP-compatible read-only runtime adapter** over local stdio JSON-RPC.

- Local stdio only (`serve-readonly`), no TCP listener or port binding.
- Runtime `tools/list` is stricter than static preview descriptors.
- Runtime exposes only safe read-only tools in Phase 12.0:
  - `lmola.list_workflows`
  - `lmola.inspect_workflow`
  - `lmola.get_schema_bundle`
  - `lmola.get_tool_registry_schema`
  - `lmola.get_workflow_catalog`
  - `lmola.get_planner_context`
  - `lmola.validate_workflow`
- Runtime **does not** expose `lmola.run_workflow` yet.
- Runtime **does not** expose low-level chemistry execution tools.
- Runtime validation canonicalizes workflows without executing chemistry workflows.
- Static preview (`lmola mcp preview*`) remains available and may include future tools.

Commands:
- `lmola mcp preview-tools --format json`
- `lmola mcp preview --out outputs/mcp_preview_manual_test`
- `lmola mcp runtime-tools --format json`
- `lmola mcp call-tool lmola.list_workflows --args-json '{"compact": true}'`
- `lmola mcp call-tool lmola.inspect_workflow --args-json '{"workflow_id": "smiles_to_xtb_relax"}'`
- `lmola mcp call-tool lmola.validate_workflow --args-json '{"workflow_id":"smiles_to_xtb_relax","input":{"type":"smiles_csv","path":"examples/smiles_list.csv"},"columns":{"id":"id","smiles":"smiles"}}'`
- `lmola mcp serve-readonly`

Execution-capable MCP workflow calls remain deferred to a later phase with explicit safety policy and confirmation controls.


## Phase 12.4 MCP-compatible stdio runtime

LMolA MCP runtime now supports a **minimal JSON-RPC stdio adapter** in runtime phase `12.4_stdio_compatibility`.

- `lmola mcp runtime-tools` is the actual callable `tools/list` equivalent for current runtime phase.
- Runtime now includes `lmola.run_workflow` with strict confirmation + allowlist policy.
- `lmola mcp serve-stdio` provides local stdio transport using Content-Length framed JSON-RPC messages (`initialize`, `tools/list`, `tools/call`).
- No network listener is opened and no TCP ports are bound.
- `tools/list` reflects runtime-callable tools for the active phase (not static preview-only candidates).
- Execution is disabled by default (`dry_run=true`).
- Real execution requires all of: `dry_run=false`, `allow_execution=true`, `confirm=true`.
- Only allowlisted workflows can execute via MCP runtime.
- Low-level chemistry tools remain unavailable as direct MCP runtime tools.
- All `lmola.run_workflow` MCP calls (including denied/dry-run) write audit records under `outputs/mcp_audit/`.
- `plan_workflow` and `validate_workflow` remain execution-free and must not create batch directories.
- `lmola mcp preview-tools` remains a static descriptor preview and may include future candidates (for example `lmola.run_workflow`).
- Runtime-enabled tools include `lmola.plan_workflow`, `lmola.validate_workflow`, and `lmola.run_workflow`.
- `lmola.plan_workflow` converts natural language to validated workflow JSON, returns `executed=false`, `batch_dir=null`, and does not execute chemistry tools.
- `lmola.validate_workflow` canonicalizes a supplied `WorkflowRequest` without execution.
- `lmola.run_workflow` remains gated by confirmation + allowlist policy; low-level chemistry tools remain disabled at runtime (`tool_not_allowed`).
- `actual_status` vs `normalized_status`: unsupported planning requests can report `actual_status=error` with `normalized_status=unsupported` for safer evaluation/debugging.
- `write_artifacts` defaults to false for MCP planning; if enabled, plan artifacts are planner debug artifacts only (not workflow execution artifacts).

Commands:
- `lmola mcp runtime-tools --format json`
- `lmola mcp serve-stdio`
- `lmola mcp jsonrpc --request-json '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}'`
- `lmola mcp jsonrpc --request-json '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'`
- `lmola mcp jsonrpc --request-json '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"lmola.list_workflows","arguments":{"compact":true}}}'`
- `lmola mcp call-tool lmola.plan_workflow --args-json '{"request":"Generate structures from examples/smiles_list.csv and relax them with xTB."}'`
- `lmola mcp call-tool lmola.validate_workflow --args-json '{"workflow_id":"smiles_to_xtb_relax","input":{"type":"smiles_csv","path":"examples/smiles_list.csv"},"columns":{"id":"id","smiles":"smiles"}}'`
- `lmola mcp call-tool lmola.run_workflow --args-json '{"workflow_id":"smiles_to_xtb_relax","input":{"type":"smiles_csv","path":"examples/smiles_list.csv"}}'`
- `before=$(find outputs/mcp_runs -maxdepth 1 -type d -name "batch_*" | wc -l); lmola mcp call-tool lmola.run_workflow --args-json '{"workflow_id":"smiles_to_xtb_relax","input":{"type":"smiles_csv","path":"examples/smiles_list.csv"},"columns":{"id":"id","smiles":"smiles"},"dry_run":false,"allow_execution":true,"confirm":true}'; after=$(find outputs/mcp_runs -maxdepth 1 -type d -name "batch_*" | wc -l); echo "before=$before after=$after"`

`lmola mcp jsonrpc --request-json ...` is a one-shot helper for local testing; `serve-stdio` is the persistent stdio adapter entrypoint.

## External MCP client integration smoke (Phase 12.5)

LMolA can be launched as a local stdio MCP-compatible server:

- `lmola mcp serve-stdio`

Phase 12.5 adds an internal client smoke command:

- `lmola mcp client-smoke --format json`

This smoke does **not** require Claude Desktop or any external GUI MCP client. It validates the same Content-Length framed JSON-RPC transport pattern used by external clients.

For real client integration, configure:

- command: `/path/to/lmola` (or `/path/to/conda/env/bin/lmola`)
- args: `["mcp", "serve-stdio"]`
- cwd: `/path/to/LMolA`

See:

- `docs/mcp/claude_desktop_config.example.json`
- `docs/mcp/lmola_mcp_client_notes.md`
