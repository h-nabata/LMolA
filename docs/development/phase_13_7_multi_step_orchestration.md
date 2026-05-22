# Phase 13.7: Multi-step LLM tool orchestration smoke

This phase adds `lmola mcp llm-orchestration-smoke --format json` to verify controlled multi-step orchestration over high-level MCP tools.

## First-step LLM selection

The first step maps a natural language task to a high-level workflow/status JSON result. The smoke covers:
- descriptor_then_triage
- geometry_then_relax_dry_run
- unavailable_backend_stop
- unsupported_research_task_stop

## Deterministic MCP execution gates

Execution policy remains deterministic:
- `lmola.run_workflow` dry-run is always allowed.
- confirmed execution only occurs when `--execute-safe` is set and workflow is in the safe allowlist.
- confirmed execution requires `dry_run=false`, `allow_execution=true`, and `confirm=true`.
- second-step requests never trigger confirmed execution in this phase.

## Artifact summary and triage feedback

For executed workflows, the smoke reads:
- `lmola.summarize_artifacts`
- `lmola.triage_artifacts`

Outputs are used as structured context for next-action reasoning.

## Second-step decision contract

The second LLM step emits strict JSON:
- `action` in a fixed safe-action set
- `next_workflow_id` (`xyz_to_xtb_relax` only for the relax proposal action, else null)
- `execute_next` normalized to `false` unconditionally
- short `reason`

If the model emits prose/markdown/thought text, only structured JSON is consumed.

## Safe next-action list

Allowed actions:
- `report_success`
- `report_partial_success`
- `inspect_failed_rows`
- `stop_due_to_partial_failure`
- `propose_xtb_relax_dry_run`
- `stop_backend_unavailable`
- `stop_unsupported`
- `no_further_action`

## Limitations

- This smoke does not expose or call low-level chemistry tools directly.
- xTB next-step execution is intentionally blocked (dry-run only).
- default tests use mock backend and do not require Ollama/GPU/network.
