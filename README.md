# LMolA (Pre-alpha)

> LMolA is a local-first, model-independent, contract-driven safety runtime for agent-assisted computational chemistry.

## What LMolA is

LMolA turns human, LLM, or external-agent intent into computationally checkable workflow requests. It sits below scientific agents and orchestrators: LMolA normalizes intent, binds parameters, validates contracts, produces dry-run plans, applies deterministic execution gates, and records artifacts and provenance.

## What LMolA is not

LMolA is not a fully autonomous chemistry agent, a collection of arbitrary backend wrappers, a production-ready scientific authority, a replacement for researcher review, or a guarantee of chemical or physical correctness.

## Core safety model

```text
intent -> normalize / clarify / bind -> validate contracts -> dry-run plan
       -> deterministic execution gate -> execute -> manifest -> safe follow-up
```

LLM output is treated as untrusted input: it is parsed, schema-validated, and canonicalized, never executed directly. Real MCP workflow execution requires an allowlisted workflow plus `dry_run=false`, `allow_execution=true`, and `confirm=true`. Low-level chemistry tools are not directly exposed by the MCP runtime.

Artifact roles are explicit. Results, reports, tables, diagnostics, and previews are not interchangeable with geometry artifacts. In particular, a dry-run preview is not evidence that an output exists.

## Current implemented capabilities

- Deterministic YAML/JSON workflows and schema/catalog exports.
- Natural-language normalization, clarification, parameter binding, workflow planning, and mock or configured local-LLM evaluation.
- Contract validation across workflows, backends, adapters, parameters, and artifacts.
- Dry-run execution plans and deterministic authorization gates.
- ASE-backed validation and geometry analysis; optional RDKit, Open Babel, molSimplify, Morfeus, and xTB capabilities within cataloged workflows.
- Artifact manifests, summaries, failure triage, compatibility hints, and safe next-action recommendations.
- Local stdio MCP runtime for high-level planning, validation, gated workflow execution, and read-only inspection.

## Architecture overview

Upper-level agents decide what to request; LMolA owns validation and authorization; adapters mediate backend execution. Backend availability never grants execution permission. See [ARCHITECTURE.md](ARCHITECTURE.md) and the normative [SPEC.md](SPEC.md).

## Quick start

```bash
python -m pip install -e ".[dev]"
lmola doctor
lmola validate examples/example.xyz
lmola workflow list
lmola workflow dry-run-plan --prompt "Validate examples/example.xyz"
```

See [INSTALL.md](INSTALL.md) and [EXAMPLES.md](EXAMPLES.md) for installation profiles and runnable examples.

## Backends and optional dependencies

The base development and test path does not require external chemistry programs, GPU access, model downloads, or cloud APIs. ASE provides the base parsing/validation path. RDKit, Open Babel, molSimplify, Morfeus, xTB, and local model servers are optional; unavailable dependencies report or skip cleanly rather than silently falling back to unrelated capabilities. Adapter metadata describes availability, supported operations, artifact roles, geometry modification, limitations, and risk.

## Natural-language and real-LLM planning

`lmola workflow plan` and related normalization, clarification, and binding commands produce validated candidates without allowing a model to authorize execution. Offline tests use the mock backend. Configured Ollama and OpenAI-compatible **local** endpoints can be evaluated explicitly; no cloud API or automatic model download is required by default.

## MCP stdio integration

Run `lmola mcp serve-stdio` for the local Content-Length-framed JSON-RPC runtime. It exposes high-level LMolA contract, planning, workflow, artifact, and audit operations—not direct backend tools—and opens no network port. Start with dry-run calls. See [MCP client notes](docs/mcp/lmola_mcp_client_notes.md).

## Evaluation and tests

```bash
ruff check .
pytest -m "not external_tools" -q
lmola workflow eval-planner examples/planner_eval_cases.yaml
```

Mock evaluations cover planning and safety regressions. Real local-LLM evaluations are opt-in. Tests marked `external_tools` are optional and require their corresponding installed tools.

## Maturity and limitations

LMolA is **Pre-alpha**. Interfaces and schemas remain provisional and may change with explicit compatibility notes. Passing validation or completing a backend run does not establish scientific correctness; inputs, methods, outputs, and follow-up decisions require researcher review.

## Documentation

- [Documentation map](docs/README.md)
- [Architecture](ARCHITECTURE.md) · [Specification](SPEC.md)
- [Examples](EXAMPLES.md) · [Installation](INSTALL.md)
- [Runtime chemistry-agent guidance](docs/agents/runtime_chemistry_agent.md)
- [Contributing](CONTRIBUTING.md) · [Changelog](CHANGELOG.md)

License: [MIT](LICENSE). Citation metadata: [CITATION.cff](CITATION.cff).
