# Phase 13.5: MCP confirmed execution smoke

This phase adds `lmola mcp confirmed-execution-smoke --format json` to verify MCP runtime execution policy for safe high-level workflows.

Key checks:
- `dry_run=true` is safe (`executed=false`).
- `dry_run=false` requires both `allow_execution=true` and `confirm=true`.
- only allowlisted high-level workflows execute.
- low-level chemistry tools are not exposed as runtime MCP tools.
- executed artifact directories can be summarized (`lmola.summarize_artifacts`) and triaged (`lmola.triage_artifacts`).

Smoke writes artifacts under:
- `outputs/mcp_execution_smoke/smoke_YYYYMMDD_HHMMSS_<id>/`

Outputs include requests/responses plus descriptor/geometry execution + summary + triage JSON snapshots.
