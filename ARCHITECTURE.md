# LMolA Architecture

## Goals

LMolA is a local-first, model-independent, contract-driven safety runtime for agent-assisted computational chemistry. Its architecture makes intent checkable, keeps authorization deterministic, preserves artifact meaning, records provenance, and allows optional backends to remain optional.

## Layers and ownership

```text
Upper-level orchestration: Human / LLM / external scientific agent
  -> CLI, Python APIs, or local MCP stdio
LMolA safety/runtime:
  -> normalization
  -> clarification and parameter binding
  -> workflow selection and canonicalization
  -> workflow / backend / adapter / artifact validation
  -> dry-run plan
  -> deterministic authorization gate and workflow allowlist
Backend execution:
  -> allowlisted workflow runner -> adapter -> optional chemistry backend
LMolA safety/runtime:
  -> artifact manifest / provenance / audit
  -> summary / triage / compatibility / safe next-action recommendation
Upper-level orchestration: researcher reviews evidence and decides what follows
```

An upper-level agent may propose intent or a structured plan, but cannot cross the execution boundary. LMolA validates and authorizes; a backend only performs the operation selected by an allowlisted workflow.

## Request-to-artifact data flow

1. The CLI, a Python caller, or the MCP stdio server accepts natural language or a structured `WorkflowRequest`.
2. Natural-language handling normalizes the request, identifies missing or ambiguous fields, produces clarification questions where necessary, and binds supported parameters.
3. A planner proposes a workflow. LMolA parses its output, validates its schema, and canonicalizes it against the workflow catalog.
4. Registries establish workflow ports, backend capabilities, adapter metadata, parameter support, output artifact contracts, geometry modification, risk, and known limitations.
5. A dry-run plan reports resolved inputs, steps, expected artifacts, backend readiness, gates, and safe stopping conditions. Previewed outputs do not yet exist.
6. The deterministic gate rejects non-allowlisted, invalid, unavailable, unconfirmed, or otherwise unsafe execution. MCP execution requires `dry_run=false`, `allow_execution=true`, and `confirm=true`.
7. The runner invokes registered workflow steps through adapters; it does not execute raw LLM text or arbitrary shell instructions.
8. Results are recorded in workflow results, MCP audit records, and versioned artifact manifests. Summaries and triage distinguish success, partial output, and error.
9. Compatibility hints and next actions are informational, artifact-driven recommendations. They do not grant permission.

## Interfaces

- **CLI:** deterministic generation, conversion, validation and relaxation commands; workflow discovery, planning, contract checks and evaluation; schema, tool and MCP utilities; artifact summary and triage.
- **Python:** provisional modules expose schemas, catalogs, registries, planners, runners, manifests, and inspection functions. They share the same contracts and safety assumptions.
- **MCP stdio:** a local, Content-Length-framed JSON-RPC server exposes high-level LMolA operations. It has planning, validation, dry-run, gated execution, audit, artifact inspection and next-action operations. It does not expose low-level backend calls and does not open a TCP port.

## Contracts and registries

The workflow catalog is the canonical allowlisted set of supported compositions. Each populated workflow contract describes input/output ports, backends, execution policy, geometry modification, side effects, cost, artifacts, and LLM-use guidance. The backend capability registry reports availability and supported tasks; adapter metadata adds operation-level inputs, outputs, risks, smoke results, conformance, and limitations.

Artifact contracts preserve semantic type and geometry role. Geometry outputs such as validated, generated, or relaxed XYZ can be eligible for geometry-consuming workflows. A result, report, table, diagnostic, manifest, or preview cannot be routed as geometry merely because it has a path or came from a successful run.

Schema and compact contract exports let model-specific or external clients consume the same runtime definitions rather than duplicating constants.

## Planning and deterministic execution boundary

Planning is non-authorizing. Mock and real local-LLM planners produce proposals inside a structured boundary; LMolA owns parsing, normalization, clarification, parameter binding, validation, and canonicalization. Ambiguity, unsupported intent, missing backends, or invalid artifacts cause a safe stop or clarification rather than speculative execution.

`dry_run` is the default. For real MCP execution, all explicit gate values and allowlist checks must pass. Backend availability, an LLM recommendation, an external plan, or a previous successful run cannot substitute for authorization.

## Evidence and follow-up

Manifests record schema versions, workflow identity, run status, artifacts, their status and provenance, geometry modification, and compatibility hints. Audit records capture MCP calls without turning them into execution permission. Read-only summaries compress outputs; triage identifies failures; compatibility and next-action recommendations describe safe candidates. Partial and error manifests remain partial or erroneous and cannot be reported as complete success.

## Evaluation

- Default tests and mock evaluations exercise schemas, planning, ambiguity handling, routing, gates, manifests, adapters, MCP behavior, and regressions without optional tools.
- Real local-LLM evaluation measures proposal quality and safety behavior; it does not make a model authoritative.
- `external_tools` tests optionally check installed chemistry backends and skip cleanly when unavailable.

## Trust boundaries

Untrusted inputs include human text, model output, external-agent plans, artifact paths and contents, and backend output. Validated structure does not imply authorization; authorization does not imply backend availability; backend success does not imply scientific correctness. Researcher review is outside and above the runtime boundary.

## Extension points

New capabilities begin with workflow and artifact contracts, backend capability records, adapter metadata and conformance, risk classification, dry-run representation, deterministic gating, manifest coverage, and tests. Model providers may integrate at the planning boundary. New interfaces should call high-level workflows rather than expose adapters directly.

## Non-goals

LMolA is not a fully autonomous agent, arbitrary tool wrapper, network service by default, production-ready scientific authority, replacement for researcher review, or guarantee of chemical or physical correctness. Broad heavy-engine coverage and direct low-level MCP execution are not architectural goals.
