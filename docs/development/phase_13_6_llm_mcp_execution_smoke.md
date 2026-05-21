# Phase 13.6: LLM-in-the-loop MCP execution smoke

`lmola mcp llm-execution-smoke` verifies an integrated safe operation loop:

1. LLM selects workflow from natural-language request.
2. LMolA normalizes/validates the selection.
3. MCP `lmola.run_workflow` dry-run executes first.
4. Confirmed execution is LMolA-controlled only (never LLM-controlled).
5. Artifacts are summarized/triaged for executed safe workflows.

## Safety model

- LLM chooses workflow only.
- LMolA keeps `dry_run=True` by default.
- LMolA sets `allow_execution=True` and `confirm=True` only when all deterministic gates pass.
- Safe execution list (Phase 13.6 smoke):
  - `smiles_to_rdkit_descriptors`
  - `xyz_to_geometry_analysis`
- Requests outside the safe list (e.g. xTB relax) are dry-run only.
- Unsupported/backend-unavailable requests are not executed.

## Command

```bash
lmola mcp llm-execution-smoke \
  --backend ollama \
  --base-url http://127.0.0.1:11434 \
  --model qwen2.5-coder:14b \
  --temperature 0 \
  --timeout-seconds 180 \
  --max-tokens 2048 \
  --execute-safe \
  --format json
```

Default CI/tests use `--backend mock` and do not require Ollama.

## Output artifacts

Outputs are written under:

`outputs/llm_execution_smoke/smoke_YYYYMMDD_HHMMSS_<id>/`

Includes per-case raw/sanitized/parsed/normalized LLM artifacts, MCP dry-run/confirmed responses, artifact summary/triage outputs, case result JSONs, and top-level smoke result CSV/JSON.

## Limitations

- Optional Ollama path depends on local model/runtime availability.
- Safe execution list intentionally narrow for smoke hardening.
