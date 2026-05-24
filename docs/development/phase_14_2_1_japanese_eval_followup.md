# Phase 14.2.1 Japanese eval follow-up

Added `examples/planner_phase14_japanese_eval_cases.yaml` as the canonical
Phase 14 Japanese input eval path expected by regression tooling.

Coverage includes:
- `filter_molecules_by_descriptors`
- `xyz_to_xtb_singlepoint`
- `compare_two_geometries`
- `xyz_to_rmsd`
- `count_element_atoms`
- `split_molecule_by_file_order`
- `backend_unavailable` for molSimplify
- `unsupported` for DFT/TS/reaction-path requests

This is additive and does not modify existing English Phase 14 eval suites or
planner safety gate behavior.
