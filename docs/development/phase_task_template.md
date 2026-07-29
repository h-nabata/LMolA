# Codex Phase Task Template

Use the platform-provided checkout and task branch. Before editing, read `AGENTS.md`, `docs/development/codex_phase_workflow.md`, and `[PHASE_SPEC_PATH]`; `AGENTS.md` is authoritative if instructions overlap.

## Phase

**[PHASE_NAME]**

## Goal

[Describe the concrete outcome and why it advances LMolA's contract-driven safety runtime.]

## In scope

- [Allowed change 1]
- [Allowed change 2]
- [Files or subsystems to inspect]

## Out of scope

- [Explicit non-goal 1]
- [Runtime, dependency, backend, schema, or CI boundary]

## Acceptance criteria

- [Observable result 1]
- [Safety/contract result 2]
- [Documentation/test result 3]

## Additional verification

Run the default checks required by `AGENTS.md`, plus:

```bash
[PHASE_SPECIFIC_COMMAND]
```

Review the complete diff, allowed file scope, relative links where relevant, and public-repository privacy. Document genuine environment limitations; do not weaken requirements to make checks pass.

## Delivery

Commit message: `[COMMIT_MESSAGE]`

PR title: `[PR_TITLE]`

Create a PR against `[BASE_BRANCH]` using the available platform integration. Include summary, files, tests, risk, privacy review, and follow-up. Do not merge unless explicitly requested.
