# Phase 18.1: unified evaluation

## Purpose and non-goals

Phase 18.1 provides a provisional, deterministic, offline evaluation interface for
LMolA's existing mock safety evaluators. It does not connect to an LLM, download a
model, execute optional chemistry backends, or replace legacy evaluator commands.
Real Ollama and OpenAI-compatible adapters are deferred to Phase 18.2.

## Canonical result and registry

`lmola.evaluation_result.v1` contains run and profile identity, UTC timestamps,
backend/model details, repeat and case totals, normalized suite/case results,
utility metrics, hard gates, safe provenance, and relative artifact references.
The interface is provisional while LMolA is Pre-alpha. The versioned registry
provides eight suites: human-prompt normalization, parameter binding,
clarification, contract-catalog selection, execution gating, multi-step
orchestration, Phase 17 adapter/artifact safety, and MCP runtime exposure. The
`safety-core` profile runs all eight in stable identifier order through thin
adapters that call existing Python functions.

Historical evaluators not represented by this focused baseline remain future
migration work. Their existing commands and result shapes are unchanged.

## Safety gates and utility metrics

Required gates cover unsafe execution attempts, result-as-geometry errors,
low-level tool exposure, backend constraint violations, and forced selection of
ambiguous prompts. Every gate names its evidence suites and violating cases. Any
violation in any repeat fails the gate; a required gate without evidence fails
closed. `not_applicable` remains distinct from `pass` for optional future gates.

Evidence-based utility metrics are schema parsing, workflow selection, parameter
binding, clarification, unsupported handling, unavailable-backend handling,
multi-step completion, cross-run consistency, and mean case latency. A metric
without observations is explicitly `not_applicable`, never a fabricated perfect
score. Token counts are intentionally outside this mock baseline.

## Repeats and artifacts

`repeat >= 1` reruns each suite and retains each case with a one-based repeat
index. Cross-run consistency compares normalized case statuses, while gate
aggregation uses all repeats without averaging away violations.

Each run is self-contained beneath the configured output root:

```text
<output-root>/<run-id>/
  evaluation_result.json
  evaluation_config.json
  suite_results/<suite-id>.json
  cases/<suite-id>/<case-id>.repeat-<n>.json
```

Persisted references are relative to the run root. Evaluation reports, configs,
and evidence are non-geometry artifacts. Provenance includes only package/schema
versions, Python version, and an optional Git commit; it omits hostnames,
executable and home paths, credentials, and environment dictionaries.

## CLI and Phase 18.2 boundary

Use `lmola eval list-suites --format json`, `lmola eval list-profiles --format
json`, `lmola eval run --profile safety-core --backend mock --repeat 1 --format
json`, and `lmola eval validate-result <evaluation-result.json> --format json`.
Validation and required-gate failures return nonzero. Phase 18.1 accepts only
`mock`; other model backends receive a Phase 18.2 deferral error. Phase 18.2 may
add backend adapters while retaining this result schema, registry boundary,
repeat behavior, and deterministic safety aggregation.
