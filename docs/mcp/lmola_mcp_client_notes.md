# LMolA MCP stdio Client Notes

LMolA provides a local stdio MCP runtime:

```bash
lmola mcp serve-stdio
```

It uses Content-Length-framed JSON-RPC over stdin/stdout and opens no network port. Configure an external client with the `lmola` executable, arguments `["mcp", "serve-stdio"]`, and a repository or project working directory. Use portable client-specific paths; LMolA and its dependencies must be installed in the selected environment.

## Runtime surface

Start with `initialize` and `tools/list`. The high-level runtime operations support:

- workflow/catalog, schema, backend-capability, adapter-contract, and planner-context discovery;
- natural-language normalization, clarification, parameter binding, planning, validation, and canonicalization;
- dry-run execution-plan creation and allowlisted workflow execution;
- artifact contract and manifest inspection, compatibility, summary, failure triage, and safe next-action recommendation.

Use `lmola mcp runtime-tools --format json` to inspect the callable surface. Static preview commands describe interfaces and are not proof that a capability is executable. Low-level chemistry/backend tools and arbitrary commands are not directly exposed.

## Safe interaction sequence

1. List or inspect workflows and contracts.
2. Normalize or plan the request; resolve clarification before proceeding.
3. Validate the structured workflow.
4. Call `lmola.run_workflow` in its default dry-run mode and review expected steps, backends, artifacts, and warnings.
5. Only a human-controlled caller may request real execution after review.
6. Inspect the resulting manifest and audit record; summarize or triage artifacts before recommending a compatible next action.

Plans supplied by an MCP client or external agent must pass the same LMolA checks. Expected outputs in a dry-run are previews, not generated artifacts.

## Execution gates and records

Real `lmola.run_workflow` execution requires all of `dry_run=false`, `allow_execution=true`, `confirm=true`, a valid request, an allowlisted workflow, compatible artifacts, and available required backends. A model must not provide authorization.

MCP audit records are written below `outputs/mcp_audit/`; confirmed workflow output is written below `outputs/mcp_runs/`. Partial and error records must not be presented as complete success. Backend completion does not establish scientific correctness; researcher review remains required.

For a protocol smoke test, run `lmola mcp client-smoke --format json`. Confirmed/external-tool checks are optional and must not be enabled merely to test connectivity.
