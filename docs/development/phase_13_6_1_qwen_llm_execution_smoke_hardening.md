# Phase 13.6.1: Qwen/Ollama LLM execution smoke hardening

## Why Qwen failed before
Real-model responses could include `<think>` blocks, prose wrappers, fenced JSON, non-contract status values (`pending`, `completed`, `error`), or unrelated JSON snippets.

## Strict JSON contract
The smoke planner prompt now enforces one-object JSON-only output with:
- `status` in `{ok, unsupported, backend_unavailable}`
- `workflow_id` in compact allowed workflow catalog, or `null` for unsupported/unavailable
- no markdown/prose/comments/extra keys
- explicit examples for descriptor, geometry, xtb, molSimplify unavailable, and DFT TS unsupported

## Parser, repair, and fallback policy
- Parser strips `<think>...</think>` and extracts/scans multiple balanced JSON candidates.
- Candidate scoring prefers objects with planner fields (`status`, `workflow_id`, `input`).
- Deterministic repair maps `completed/success/done -> ok` only with allowed workflow IDs, maps availability and unsupported errors to contract statuses.
- Smoke-only fallback classifier is used only when strict parse/repair still fails. It is explicitly reported via `fallback_used=true` and `fallback_used_cases`.

## Execution safety gates
- LLM-provided execution flags are ignored.
- Confirmed execution is only attempted when `--execute-safe` is set and workflow is in safe list:
  - `smiles_to_rdkit_descriptors`
  - `xyz_to_geometry_analysis`
- xTB case remains dry-run-only in smoke execution.
- unsupported/unavailable cases are never executed.

## Optional Qwen test
Run only when local Ollama model is available:

```bash
LMOLA_RUN_OLLAMA_TESTS=1 pytest -m external_tools -q -rs
lmola mcp llm-execution-smoke --backend ollama --base-url http://127.0.0.1:11434 --model qwen2.5-coder:14b --temperature 0 --timeout-seconds 180 --max-tokens 2048 --execute-safe --format json
```

## Inspect failed-case raw outputs
- Open smoke root: `smoke_dir` from result JSON.
- For a failed case: `cases/<case_id>/raw_llm_response.txt` and `cases/<case_id>/normalized_output.json`.
- Focus on `fallback_used`, `repair_attempted`, `repair_successful`, `selected_workflow_id`, `normalized_status`.
