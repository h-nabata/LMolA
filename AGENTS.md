# AGENTS.md

This file is for repository development agents such as Codex Desktop / Codex CLI.
It governs code changes, tests, safety boundaries, and repository conventions.
It is not the runtime prompt for chemistry task execution.
Runtime chemistry agent instructions live in `docs/agents/runtime_chemistry_agent.md`.

This repository is maintained with a conservative, Codex-friendly workflow.

## Scope

LMolA is a local-first, offline-capable computational chemistry workflow agent.
Default development and tests must not require cloud APIs, GPU access, Ollama,
xTB, molSimplify, RDKit, Open Babel, or network access.

## Safety Constraints

- Do not add cloud-required behavior by default.
- Do not open TCP ports, add HTTP/SSE servers, or require background services for default tests.
- Do not execute LLM output directly.
- Keep execution permission deterministic and controlled by LMolA-side validation, allowlists, and confirmation gates.
- Do not relax `lmola.run_workflow` confirmation policy.
- Keep dry-run behavior safe by default.
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
