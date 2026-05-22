# Phase 14.0.2 cleanup

## Planner mapping: compare vs RMSD
- Added explicit planner prompt disambiguation for `compare_two_geometries` vs `xyz_to_rmsd`.
- Broad comparison requests (atom-count match, element-order match, per-atom displacement, structural comparison) map to `compare_two_geometries`.
- RMSD-only requests map to `xyz_to_rmsd`.

## Split-by-file-order validation and positive example
- Strict 1-based validation remains unchanged (invalid/duplicate/out-of-range indices still fail).
- Positive example now uses valid non-overlapping fragments for `examples/example.xyz` (`oxygen: [1]`, `hydrogens: [2-3]`).
- Added an explicit invalid fixture for regression checks.

## xTB singlepoint stabilization
- Added dedicated xTB singlepoint execution path without `--opt`.
- Singlepoint contract now reports:
  - `artifact_kind: xtb_singlepoint`
  - `status`
  - `energy` and `energy_unit`
  - `geometry_modified: false`
  - `normal_termination`
  - `method`, `run_dir`, `input_path`
- Energy parser now covers common xTB patterns including `| TOTAL ENERGY`, `TOTAL ENERGY`, `total E`, and `final singlepoint energy`.
- If normal run occurs but energy is not parsed, result is marked with `error_type=energy_parse_failed`.

## Remaining limitations
- Optional Qwen/Ollama performance still depends on local model availability/quality.
- xTB output format variants beyond known patterns may still require parser extension.
