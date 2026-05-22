# Phase 14.0.1 Cleanup

## Source of truth
Workflow catalog (`lmola.workflows.catalog`) is the canonical source for high-level workflow IDs and definitions.
Planner context, schema export, `list_workflows`/`inspect_workflow`, and MCP runtime metadata should mirror catalog entries.

## Synchronization changes
- Added runtime metadata field `supported_workflow_ids` on `lmola.run_workflow` from catalog.
- Added visibility consistency tests to ensure all catalog workflows are visible through planner/schema/runtime surfaces.
- Added guard test that low-level chemistry tools are not exposed as MCP runtime tools.

## Validation fixes
- `split_molecule_by_file_order_ase` now validates 1-based indices strictly and rejects invalid/duplicate/empty fragment cases with explicit error types.

## Artifact summary contracts
- `compare_two_geometries` produces `geometry_comparison` payload including atom count match, element-order match, RMSD, centroid shift, and displacement metrics.
- `xyz_to_rmsd` produces `rmsd_result` payload.
- Batch artifact summary now includes `comparison_summary` for geometry-comparison workflows.
- `xyz_to_xtb_singlepoint` includes `artifact_kind`, `task=singlepoint`, `geometry_modified=false`, and parse-failure error typing.

## Remaining limitations
- Execution allowlist for confirmed execution remains intentionally narrower than full catalog.
- External backend availability (xtb/molsimplify) still depends on local installation.
