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
