# LMolA Core Specification (Pre-alpha)

This document is normative. LMolA is a local-first, model-independent, contract-driven safety runtime for agent-assisted computational chemistry. Public interfaces and schemas are **provisional** during Pre-alpha.

## 1. Request boundary and status

1. Runtime execution MUST originate from a schema-valid structured workflow request. Natural language MAY be accepted before this boundary.
2. LLM or external-agent output MUST be treated as untrusted input and MUST be parsed, validated, normalized as applicable, and canonicalized against LMolA contracts. It MUST NOT be executed directly and MUST NOT grant permission.
3. Missing or ambiguous required information MUST produce clarification or a safe stop. Implementations MUST NOT invent execution-critical values outside documented deterministic rules.
4. Outcomes SHOULD distinguish at least success, partial completion, error, unsupported intent, and backend unavailability where applicable. `unsupported` MUST identify an absent supported contract; `backend_unavailable` MUST identify a supported operation whose required backend is unavailable. These outcomes MUST NOT silently fall back to an unrelated backend or workflow.
5. Partial or error output MUST NOT be represented as complete success.

## 2. Execution invariant

1. `dry_run` MUST remain the safe default.
2. Real MCP workflow execution MUST require all of: `dry_run=false`, `allow_execution=true`, `confirm=true`, a valid request, an allowlisted workflow, compatible artifacts, and satisfied backend/adapter constraints.
3. `allow_execution` and `confirm` MUST be explicit. An LLM, runtime agent, backend, compatibility hint, or prior result MUST NOT set or imply them autonomously.
4. The deterministic execution gate MUST remain LMolA-controlled and MUST run before backend side effects.
5. Only cataloged, execution-allowlisted workflows MAY execute. Failure of an allowlist or contract check MUST stop safely.
6. The MCP runtime MUST expose high-level LMolA operations only. It MUST NOT expose low-level chemistry backend tools or arbitrary command execution.

## 3. Contracts and conformance

1. A workflow contract SHOULD declare identity, task and operation, typed input/output ports, required and optional backends, execution policy, side effects, risk/cost information, geometry modification, and artifact outputs.
2. A backend capability record SHOULD declare availability, supported tasks or operations, and integration limitations.
3. Adapter metadata SHOULD declare adapter/backend identity, optional dependency, supported operations, input/output artifact types, geometry modification, risk class, limitations, smoke result, and conformance status.
4. An adapter MUST accept only contracted inputs and MUST report unsupported operations or unavailable dependencies clearly. Optional dependencies MUST remain optional; their absence MUST NOT break default tests or trigger unrelated fallback.
5. New backend functionality SHOULD begin with capability, adapter, workflow, parameter, and artifact contracts before execution code or MCP exposure.

## 4. Artifacts and geometry roles

1. Artifact contracts MUST identify semantic artifact type and SHOULD identify production conditions, geometry role, modification status, and compatible consumers.
2. Geometry artifacts MAY be routed only to workflows whose input contract accepts that geometry type.
3. Results, reports, tables, diagnostics, audit records, manifests, and previews MUST NOT be reused as geometry. Examples include single-point results, relaxation-result metadata, analysis reports, descriptor tables, and dry-run plans.
4. A dry-run expected-output preview MUST NOT be represented as an existing generated artifact.
5. Geometry-modifying workflows MUST declare `geometry_modified=true`; read-only or result-only workflows MUST NOT imply new geometry unless they explicitly produce a geometry artifact.
6. Compatibility hints and next-action recommendations MUST be informational and MUST NOT bypass validation or execution gates.

## 5. Provenance and audit

1. Executed workflows SHOULD produce a manifest that records workflow identity, overall status, artifact identities, types, paths, per-artifact status, producing operation, schema versions, and geometry-modification information when known.
2. MCP calls SHOULD produce audit records sufficient to distinguish planning, dry-run, denied execution, and confirmed execution without recording secrets.
3. Summaries and triage MUST preserve material failure and partial-status information.
4. Generated records MUST NOT contain credentials or unnecessary machine-specific information.

## 6. Versioning, compatibility, and deprecation

1. Persisted contract and manifest formats MUST carry a schema version where the current implementation defines one.
2. Readers SHOULD reject or clearly report unsupported schema versions rather than guess their meaning.
3. During Pre-alpha, interfaces MAY change. Breaking contract or schema changes SHOULD be documented, tested, and accompanied by migration or explicit incompatibility guidance where practical.
4. Deprecated interfaces SHOULD be announced before removal when practical, but no stable public API is promised before a later maturity declaration.

## 7. Researcher-review boundary

Successful validation or execution establishes only that LMolA's implemented checks and backend invocation completed as reported. It MUST NOT be presented as proof of chemical or physical correctness. Scientific interpretation, method suitability, and downstream use MUST remain subject to researcher review.
