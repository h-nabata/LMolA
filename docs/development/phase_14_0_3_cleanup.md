# Phase 14.0.3 cleanup

## xTB singlepoint artifact-summary contract

This phase tightens the singlepoint artifact contract for `xyz_to_xtb_singlepoint`:

- `singlepoint_result.json` must explicitly include:
  - `artifact_kind: xtb_singlepoint`
  - `status`
  - `energy`
  - `energy_unit`
  - `method`
  - `geometry_modified: false`
  - `normal_termination`
  - `input_path`
  - `run_dir`
- `lmola.summarize_artifacts` for a singlepoint result includes key top-level fields:
  - `energy`, `energy_unit`, `geometry_modified`, `normal_termination`, `method`
- `lmola.summarize_artifacts` for a batch directory now includes `singlepoint_summary` when
  `workflow_id == xyz_to_xtb_singlepoint`, preserving visibility of `geometry_modified=false`.
- Successful singlepoint artifacts remain triaged as non-failures (`failure_category=none`).

## Descriptor-filter wording and HBD/HBA mapping

Planner prompt wording is expanded so descriptor-threshold intents map deterministically to:

- `workflow_id: filter_molecules_by_descriptors`

Added explicit descriptor examples for:

- `MolWt`, `NumHDonors`, `NumHAcceptors` thresholds
- HBD/HBA-like requests (hydrogen-bond donor/acceptor rule wording)

Mock planner heuristics are tightened to catch natural-language cues such as:

- HBD/HBA
- hydrogen bond donor/acceptor
- donor/acceptor rule
- Lipinski-like
- filter/select/threshold + SMILES CSV context

## Remaining limitations

- Optional Ollama/Qwen planner benchmark still depends on local model availability.
- No default/unit test requires Ollama, Qwen model downloads, GPU, or network execution.

## Qwen benchmark status

- Baseline issue targeted in this phase: `filter_by_hbd_hba_like_rule` mapping.
- Validation is covered by prompt+mock planner updates and planner eval regression tests.
