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
  model: qwen2.5:7b-instruct
  timeout_seconds: 60
```

If not configured, `lmola run-agent` fails safely with a clear message and does not call cloud APIs.
GPU is optional; CPU-only workflows remain supported for doctor/validate/generate/tests.


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

## Local LLM workflow planning (Phase 10.0)

LMolA now supports local-first workflow planning from natural language via:

```bash
lmola workflow plan "Generate structures from examples/smiles_list.csv and relax them with xTB."
```

Key points:
- Local LLMs only in this phase (`mock`, `ollama`, `openai_compatible_local`).
- Cloud hosted APIs are not enabled.
- LLM output is planning-only workflow JSON/YAML; it does not execute tools directly.
- Planned workflows are validated with `WorkflowRequest` before acceptance.
- Default behavior is dry-run planning (no execution).
- Unsupported tasks return structured safe errors.

Example local configs:

```yaml
llm:
  enabled: true
  backend: ollama
  base_url: http://127.0.0.1:11434
  model: qwen2.5:7b
  temperature: 0
  timeout_seconds: 60
```

```yaml
llm:
  enabled: true
  backend: openai_compatible_local
  base_url: http://127.0.0.1:1234/v1
  model: local-model-name
  temperature: 0
  timeout_seconds: 60
```

Typical planning artifacts are written under `outputs/plan_.../` and include:
- `planned_workflow.yaml`
- `planned_workflow.json`
- `planning_result.json`

Generated and relaxed structures always require researcher review.
