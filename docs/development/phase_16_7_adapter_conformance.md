# Phase 16.7 adapter conformance foundation

Phase 16.7 adds the shared adapter contract used by future chemistry adapters.
It is intentionally metadata-first: it does not add new engine execution paths and
does not make optional chemistry packages required for default tests.

## Adapter requirements

An adapter must expose `AdapterMetadata`, either directly, as a mapping, through a
`metadata` attribute, or through `get_metadata()`. Required metadata:

- `adapter_id`: stable lowercase identifier suitable for registries.
- `display_name`: user-facing adapter name.
- `backend_name`: underlying library, executable, service, or engine name.
- `backend_version`: version string when it can be discovered safely.
- `capabilities`: non-empty list of supported task/capability labels.
- `availability`: registered/backend availability and smoke support status.
- `risk_class`: explicit `AdapterRiskClass`.
- `artifact_contracts`: lightweight declarations of expected input, output, log,
  JSON result, trajectory, or diagnostic artifacts.

Use `assert_adapter_conformance()` for one adapter and
`assert_registered_adapters_conform()` for a registry mapping. These helpers raise
`AdapterConformanceError` with actionable messages.

## Risk classes

- `SAFE_LOCAL`: local deterministic or near-deterministic Python-only operations.
- `OPTIONAL_LOCAL`: optional importable Python libraries or local integrations;
  absence must be represented as unavailable, not as a hard failure.
- `EXTERNAL_EXECUTION`: local executables or engines invoked across a process
  boundary; command and artifact boundaries must be declared.
- `HEAVY_ENGINE`: heavyweight simulation or quantum chemistry engines such as
  ORCA, Gaussian, VASP, or Quantum ESPRESSO. Phase 16.7 is specification-only for
  these unless an adapter already exists.
- `NETWORK_OR_CLOUD`: network or cloud integration. It must not run by default
  and requires explicit future opt-in policy.

## Availability reporting

`AdapterAvailability` separates registration from backend availability:

- `registered`: the adapter is known to LMolA.
- `backend_available`: import/executable/service probe result.
- `importable`: Python importability when relevant.
- `executable`: resolved executable path when relevant.
- `unavailable_reason`: required when `backend_available` is false.
- `smoke_execution`: `supported`, `unsupported`, or `skipped_unavailable`.

Default tests should be able to validate adapter metadata even when optional
backends such as RDKit, Open Babel, molSimplify, xTB, ASE, morfeus, tblite, ORCA,
Gaussian, VASP, or QE are absent.

## Artifact contract foundation

`AdapterArtifactContract` is deliberately lightweight. Future adapters can
declare expected artifacts by role:

- `input_file`
- `output_file`
- `log_file`
- `structured_json_result`
- `trajectory`
- `diagnostics`

This foundation complements the existing workflow artifact registry without
requiring full per-engine artifact handling in Phase 16.7.

## Roadmap fit

- Phase 16.8 can add optional external smoke checks that report
  `smoke_execution` without becoming default requirements.
- Phase 17 can expand existing tools while making their adapter metadata
  explicit.
- Phase 18 can add lightweight adapters against this contract.
- Phase 19+ can specify heavy-engine adapters with `HEAVY_ENGINE` risk class and
  strict command/artifact boundaries before any real execution support.
