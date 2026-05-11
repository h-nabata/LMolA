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
- `lmola relax STRUCTURE.xyz`

## Offline/local-first policy
No cloud APIs by default. No automatic model downloads.

## molSimplify integration status
Detection/probing stub only; generation command execution intentionally unimplemented in pre-alpha.

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
