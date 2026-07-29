# Contributing to LMolA

LMolA is a local-first, model-independent, contract-driven safety runtime for agent-assisted computational chemistry. Contributions should preserve its deterministic safety boundary and Pre-alpha scope.

## Start here

- [`AGENTS.md`](AGENTS.md) is authoritative for repository-agent safety and workflow policy.
- [`ARCHITECTURE.md`](ARCHITECTURE.md) explains implemented layers and trust boundaries.
- [`SPEC.md`](SPEC.md) states normative runtime invariants.
- [`docs/development/codex_phase_workflow.md`](docs/development/codex_phase_workflow.md) describes the reusable phase workflow.
- [`docs/README.md`](docs/README.md) maps the rest of the documentation.

Keep changes minimal and reviewable. Do not add cloud-required behavior, weaken execution gates, or treat model output as authorization. Use deterministic YAML/JSON examples and add tests with behavior changes.

## Backend and adapter contributions

A backend addition begins with capability metadata, adapter metadata and conformance, a cataloged workflow contract, parameter constraints, and artifact contracts. Define semantic inputs/outputs, geometry modification, optional-dependency behavior, risk, limitations, dry-run representation, provenance, and tests before expanding execution. Do not expose low-level backend calls through the MCP runtime.

## Checks

The default suite must run without optional external chemistry tools:

```bash
ruff check .
pytest -m "not external_tools" -q
lmola --help
lmola doctor
lmola validate examples/example.xyz
```

Tests that genuinely invoke optional installations belong under the `external_tools` marker and must skip clearly when unavailable:

```bash
pytest -m external_tools -q
```

Document environment limitations rather than making optional tools default requirements. Before submitting, review the diff, relative Markdown links, generated files, and public-repository privacy.
