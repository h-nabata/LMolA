# AGENTS.md

This file is for repository development agents such as Codex Desktop / Codex CLI.
It governs code changes, tests, safety boundaries, and repository conventions.
This file is for Codex/development agents and is not the runtime chemistry-agent prompt (not the runtime prompt for chemistry task execution).
Runtime chemistry agent instructions live in `docs/agents/runtime_chemistry_agent.md`.

This repository is maintained with a conservative, Codex-friendly workflow.

## Scope

LMolA is a local-first, offline-capable computational chemistry workflow agent.
Default development and tests must not require cloud APIs, GPU access, Ollama,
xTB, molSimplify, RDKit, Open Babel, or network access.

## Project Identity

LMolA is not a collection of arbitrary computational chemistry wrappers.
LMolA is a fail-safe runtime layer for LLM-assisted computational chemistry.

The core responsibilities are:

1. Intent normalization
   Convert human or LLM instructions into computationally checkable intermediate representations.

2. Contract validation
   Validate workflow, backend, parameter, and artifact compatibility before execution.

3. Safety gating
   Keep execution permission deterministic and outside the LLM.
   LLM outputs may suggest workflows or next actions, but must not authorize execution.

4. Provenance / manifest
   Record what was planned, what was executed, what artifacts were produced, and what can be safely done next.

5. Benchmark / regression
   Measure workflow selection, ambiguity handling, artifact routing, unsafe execution attempts, and result-as-geometry errors across models.

Do not prioritize backend feature chasing over these responsibilities.

## Backend / Adapter Policy

Backend integration should be adapter-driven.

For each backend, prefer explicit metadata and contract coverage:

- adapter_id
- backend_name
- backend_family
- backend_type
- optional_dependency
- availability / smoke result
- supported_operations
- input_artifact_types
- output_artifact_types
- geometry_modified
- risk_class
- known_limitations
- conformance_status

Do not wrap every backend feature merely because the backend supports it.

Optional backends must remain optional.
Unavailable optional backends must fail clearly or skip cleanly in marked external-tool tests.
Default tests must not require optional external chemistry programs.

Heavy engines such as ORCA, Gaussian, GAMESS, SIESTA, Quantum ESPRESSO, and VASP must not be added unless the phase explicitly requests heavy-engine adapter specification.

## Artifact Safety

Result, report, table, and diagnostic artifacts must not be treated as geometry artifacts.

For example, structured result artifacts such as `xtb_singlepoint_result` must not be routed as XYZ geometry inputs.

Geometry-modifying workflows must clearly declare `geometry_modified=true`.
Read-only or result-only workflows must not imply geometry availability unless they explicitly produce a geometry artifact.

## Risk Classes

When adding or refining backend metadata, prefer conservative risk classification.

Suggested classes:

- `read_only`
- `local_validation`
- `local_conversion`
- `light_generation`
- `light_execution`
- `geometry_modifying`
- `external_execution`
- `heavy_external`
- `destructive_or_unbounded`

Risk class should inform dry-run planning, confirmation requirements, artifact compatibility, and future execution policies.

## Safety Constraints

- Do not add cloud-required behavior by default.
- Do not open TCP ports, add HTTP/SSE servers, or require background services for default tests.
- Do not execute LLM output directly.
- Keep execution permission deterministic and controlled by LMolA-side validation, allowlists, and confirmation gates.
- Do not relax `lmola.run_workflow` confirmation policy.
- Preserve safe defaults for execution gates and never weaken or bypass them:
  - `dry_run` remains the safe default behavior.
  - `allow_execution` must remain explicitly required for real execution.
  - `confirm` must remain explicitly required for real execution.
- Development agents must not auto-enable `allow_execution`/`confirm`, and must not bypass `dry_run`-first behavior.
- Optional external tools must fail clearly when unavailable.
- Do not log secrets, API keys, credentials, or raw environment dumps.
- Do not use `shell=True`.
- Do not expose low-level chemistry tools as direct runtime/MCP tools.

## Default Checks

Run these before proposing a change when the local environment supports them:

```bash
ruff check .
pytest -m "not external_tools" -q
lmola --help
lmola doctor
lmola validate examples/example.xyz
```

If a check cannot be run because dependencies are unavailable, record that clearly
in the PR instead of broadening default requirements.

## Development Workflow for Phase Tasks

For phase-level tasks, development agents should normally follow this workflow:

1. Confirm the repository path and current branch.
2. Start from `main` unless the user explicitly says otherwise.
3. Confirm the working tree is clean.
   If only untracked `pr_body.md` exists, it may be deleted.
   If tracked source, tests, docs, config, or project files are dirty, stop and report.
4. Run `git pull --ff-only`.
5. Run baseline checks before implementation when available.
6. Create a task branch with a descriptive name.
7. Keep the implementation minimal and scoped to the phase.
8. Add or update tests and concise documentation.
9. Run verification checks.
10. Commit only after local checks pass.
11. Create a PR against `main`.
12. Do not force-merge pending or failing checks.
13. If checks are pending, prefer auto-merge.
14. If checks fail, report the failing checks and likely causes.

Development agents may automate branch creation, commits, push, PR creation, and check inspection, but must not overwrite user changes or bypass safety gates.

## Change Discipline

- Keep changes minimal, reviewable, and scoped to the task.
- Do not change application code when working only on workflow/support files.
- Do not change `pyproject.toml` unless the task explicitly requires it.
- Do not change CI unless strictly necessary.
- Put development notes under `docs/development/`; avoid long phase logs in `README.md`.
- Preserve existing public interfaces unless the task explicitly requests a compatibility change.

## PR Expectations

Every PR should include:

- Summary
- Files changed
- Tests run
- Risk
- Follow-up tasks
