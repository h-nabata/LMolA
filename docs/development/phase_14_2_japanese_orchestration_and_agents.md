# Phase 14.2: Japanese orchestration benchmark formalization and AGENTS role separation

## Summary
- Added deterministic request normalization (`lmola.llm.request_normalization.normalize_request`) for Japanese/English intent hints and safety constraints.
- Added CLI: `lmola workflow normalize-request --language ja --request ... --format json`.
- Added Japanese orchestration case file: `examples/orchestration_phase14_japanese_cases.yaml`.
- Extended orchestration smoke command to accept `--cases` and surface normalization visibility (`raw_request`, `normalized_request`, `normalization_pass_rate`).
- Separated development guidance (`AGENTS.md`) from runtime chemistry agent guidance (`docs/agents/runtime_chemistry_agent.md`).

## Safety
- Normalization does not grant execution permissions.
- Execution remains externally gated by workflow runtime checks and confirmation parameters.
- Dry-run-first behavior preserved.

## Limitations
- Mock orchestration path is deterministic and intended for safety regression checks.
- Optional local LLM diagnostics remain environment-dependent.
