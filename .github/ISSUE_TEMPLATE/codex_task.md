---
name: Codex task
about: Conservative task template for Codex-assisted LMolA development
title: "[Codex] "
labels: codex
assignees: ""
---

## Task

Describe the requested change.

## Scope

- In scope:
- Out of scope:

## Safety Constraints

- LMolA remains local-first and offline-capable.
- Do not add cloud-required behavior by default.
- Do not require xTB, molSimplify, RDKit, Open Babel, Ollama, GPU, or cloud APIs for default tests.
- LLM output must never be executed directly.
- Optional external tools must fail clearly when unavailable.
- Keep changes minimal and reviewable.

## Expected Checks

- [ ] `ruff check .`
- [ ] `pytest -m "not external_tools" -q`
- [ ] `lmola --help`
- [ ] `lmola doctor`
- [ ] `lmola validate examples/example.xyz`

If a check cannot be run, explain why in the PR.

## Notes

Add relevant files, examples, or phase context.
