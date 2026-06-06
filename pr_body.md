## Summary

- Add Phase 17 adapter depth metadata for xTB, ASE, OpenBabel, and RDKit.
- Refine artifact and dry-run planning contracts for existing-tool operations without adding broad backend execution.
- Add Phase 17 mock evaluation cases, tests, and developer documentation.

## Design notes

- Adapter metadata now includes backend family/type, optional dependency status, execution modes, known limitations, conformance status, and operation-level profiles.
- Operation profiles distinguish read-only validation, local descriptor/conformer/conversion work, and xTB external execution paths.
- xTB singlepoint and relax are represented separately; `xtb_singlepoint_result` remains a non-geometry result artifact.
- Optional backend smoke and availability behavior stays graceful when RDKit, OpenBabel, molSimplify, or morfeus are absent.
- Runtime/MCP low-level chemistry tool exposure remains blocked.

## Tests

- `ruff check .`
- `pytest -m "not external_tools" -q`
- `lmola doctor`
- `lmola validate examples/example.xyz`
- `pytest -m external_tools -q -rs`

## Safety / scope notes

- No optional chemistry backend was added as a default dependency.
- No heavy-engine execution was added.
- No network listeners, model downloads, GPU requirements, or cloud-required behavior were added.
- Execution gates remain dry-run first and still require explicit `allow_execution` and `confirm` for real execution.

## Next step

- Phase 18 should add lightweight adapters only where the Phase 17 metadata, artifact contracts, smoke checks, and safety gates are sufficient to keep default tests offline and optional-tool independent.
