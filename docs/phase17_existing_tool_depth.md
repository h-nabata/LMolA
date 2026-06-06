# Phase 17 existing tool depth

Phase 17 deepens LMolA's existing xTB, ASE, OpenBabel, and RDKit integrations as
fail-safe runtime components. It does not add broad backend coverage, new heavy
engine execution, network services, or new default optional dependencies.

## Purpose

The goal is to make existing tool behavior explicit through adapter metadata,
operation profiles, artifact contracts, smoke checks, dry-run planning, and
conformance tests. This helps planners and future adapters reason about what
LMolA can safely scaffold without exposing low-level tool APIs.

## Adapter mapping

- xTB: local external execution for `singlepoint_energy` and
  `geometry_optimization`. Real execution remains gated by `dry_run=false`,
  `allow_execution=true`, and `confirm=true`.
- ASE: local validation and geometry analysis only. It is not a general
  calculator execution layer.
- OpenBabel: optional CLI conversion and light 3D generation. Missing CLI tools
  report unavailable and do not fail default tests.
- RDKit: optional in-process descriptor calculation and light
  structure/conformer generation. Missing imports report unavailable and do not
  fail default tests.

## Risk classes

The top-level adapter risk class remains conservative:

- ASE and RDKit: `OPTIONAL_LOCAL`
- OpenBabel and xTB: `EXTERNAL_EXECUTION`

Operation profiles add narrower labels such as `local_validation`,
`local_conversion`, `light_generation`, `external_execution`, and
`geometry_modifying_external_execution`.

## Artifact policy

Result/report/table artifacts stay distinct from geometry artifacts:

- `xtb_singlepoint_result` is not geometry.
- `xtb_relax_result` is relaxation metadata, not reusable geometry.
- `relaxed_xyz` and `optimized_geometry` are geometry artifacts.
- `geometry_analysis_report`, `rdkit_descriptor_table`,
  `descriptor_filter_report`, and `openbabel_conversion_report` are not geometry.
- `converted_structure` is geometry-like structure output, but pure conversion is
  non-geometry-modifying unless 3D generation is explicitly requested.

## Parameter binding boundary

Phase 17 only binds controls already represented by existing workflows:

- input structure, SMILES, or SMILES CSV
- xTB charge, multiplicity, solvent/model, max steps, and force threshold
- OpenBabel input/output format and explicit 3D generation request
- RDKit descriptor/filter and conformer count/seed where already supported
- ASE atom/geometry analysis inputs

It does not add new backend capabilities solely because the backend supports
them.

## Tests

Default tests use mock-safe adapter metadata, smoke, dry-run, artifact, schema,
and MCP gate checks. Optional real-tool tests remain under `external_tools` and
may skip when tools are absent.

## Future work

Future official backend MCP servers or heavy-engine adapters should consume this
metadata model first. Heavy engines such as ORCA, Gaussian, GAMESS, SIESTA, QE,
and VASP remain specification-only until explicit adapter contracts, artifact
boundaries, and execution policies are added.
