# Phase 16.8 optional external smoke checks

Phase 16.8 adds conditional smoke checks for optional chemistry backends. These
checks are probes only: they do not install packages, use the network, open
servers, or run expensive calculations.

## What gets checked

`lmola.adapters.smoke` defines optional smoke specs for:

- ASE
- RDKit
- Open Babel
- xTB
- molSimplify
- Morfeus

Each smoke check may report:

- import availability for Python modules
- package version via installed metadata when available
- executable discovery for CLI-backed tools
- CLI version extraction only when a safe version probe already exists

No structure generation, optimization, descriptor calculation, or simulation is
performed by these smoke checks.

## Availability and risk classes

Smoke results feed the Phase 16.7 adapter availability model:

- Absent optional tools return `status="unavailable"` and
  `smoke_execution="skipped_unavailable"` with a clear reason.
- Present optional libraries or executables return `status="available"` and
  `smoke_execution="supported"`.
- `OPTIONAL_LOCAL` is used for import-only local libraries.
- `EXTERNAL_EXECUTION` is used for local CLI/process-boundary integrations.

This keeps adapter conformance testable without making RDKit, Open Babel, xTB,
ASE, Morfeus, molSimplify, or other optional tools mandatory.

## Test policy

Default tests mock probe behavior and must pass when optional tools are absent.
Tests that require real optional tools must use the existing `external_tools`
pytest marker and skip when the backend is absent.

This prepares Phase 17 by making existing tool-depth expansion consume a common
availability and smoke-reporting contract before adding deeper behavior.
