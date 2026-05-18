# LMolA external MCP client notes

LMolA can run as a local stdio MCP server:

- `lmola mcp serve-stdio`

Phase 12.5 also adds an internal smoke client:

- `lmola mcp client-smoke --format json`

This smoke client launches `lmola mcp serve-stdio` and sends Content-Length framed JSON-RPC requests for:

- `initialize`
- `tools/list`
- `tools/call lmola.list_workflows`
- `tools/call lmola.validate_workflow`
- `tools/call lmola.run_workflow` (dry-run)
- `tools/call lmola.run_workflow` (missing confirmation safety path)
- unknown tool handling

## External client configuration

Use local placeholders and adjust paths to your own environment:

- command: `/path/to/conda/env/bin/lmola`
- args: `["mcp", "serve-stdio"]`
- cwd: `/path/to/LMolA`

The selected conda environment must contain LMolA and its dependencies.

No network port is opened for this integration path (stdio only).

## Safe first tests

- `initialize`
- `tools/list`
- `lmola.list_workflows`
- `lmola.validate_workflow`
- `lmola.run_workflow` with dry-run (default)

## Safety notes

- `lmola.run_workflow` can execute only when all are true: `dry_run=false`, `allow_execution=true`, and `confirm=true`.
- Workflow execution remains allowlisted.
- Low-level chemistry tools are not exposed as direct MCP runtime tools.
- Confirmed execution may run RDKit/Open Babel/xTB depending on workflow.
- MCP audit logs are written under `outputs/mcp_audit/`.
- Confirmed MCP workflow outputs are written under `outputs/mcp_runs/`.
- `lmola mcp runtime-tools --format json` is the callable runtime `tools/list` equivalent.
- `lmola mcp preview-tools --format json` is static descriptor preview and may include descriptor-only/future entries.
