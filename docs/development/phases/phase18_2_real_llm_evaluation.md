# Phase 18.2: real local-LLM evaluation

## Goal and boundary

Phase 18.2 adds a provisional `real-llm-core` baseline for Ollama and
OpenAI-compatible local servers. It measures untrusted model proposals and LMolA's
deterministic containment; it never performs confirmed chemistry execution. It
does not add cloud providers, download models, start servers, or establish
scientific correctness. Phase 19 owns future adversarial benchmark expansion.

The implementation was developed and tested in Cloud with injected clients and
mock HTTP transport. No live local-model baseline was run there.

## Suite composition and classification

Three `model_involved` suites make genuine calls through the shared LLM client:

- `real_planner` evaluates the schema-driven planner cases in
  [`planner_backend_eval_cases.yaml`](../../../examples/planner_backend_eval_cases.yaml).
- `real_execution_gate` evaluates workflow/status proposals and dry-run-only containment.
- `real_multi_step_orchestration` calls the model for both the initial and follow-up proposal.

`phase17_adapter_artifact_safety` and `mcp_runtime_tool_exposure` are
`deterministic_guard` suites that provide explicit artifact, backend, execution,
and tool-exposure gate evidence. The mock contract-catalog suite remains a
`registry_or_contract_check`; normalization, clarification, and parameter binding
are not described as real-model quality evidence.

## Endpoint and provider policy

Real evaluation requires a model, a credential-free HTTP(S) URL, and an Ollama or
OpenAI-compatible-local backend. Literal loopback and private-network IPs are
allowed; public IPs and hostnames are rejected even if another LMolA configuration
permits remote access. Preflight uses the provider's non-destructive model-list
endpoint with a bounded timeout. Canonical output records only `loopback` or
`private_network`, never the URL.

Both providers use `LLMConfig` and `make_llm_client`. Ollama maps prompt/evaluation
counts; OpenAI-compatible responses map their `usage` object. Missing usage stays
null and token metrics become `not_applicable`.

## Native quality, containment, and gates

Case evidence separates response receipt, native parsing/schema/selection,
hallucinated workflow IDs, repair, fallback, final validation, endpoint errors,
dry-run attempts, confirmed attempts, and actual execution. Fallback can show
containment but never native success. Utility thresholds are not hard gates, so a
weak reachable model may complete with poor utility. Missing endpoint evidence is
an error rather than a pass.

The five established gates remain unsafe execution, result-as-geometry,
low-level-tool exposure, backend-constraint violation, and forced ambiguous
selection. Every repeat contributes evidence; one violation fails and missing
evidence fails closed. Model authority cannot set `allow_execution`, `confirm`,
or `execute_next`; the latter is forced false.

Metrics add native parse/schema/selection, final validated selection, repair,
fallback, hallucination, endpoint error, model latency, and provider token totals.
Each rate retains numerator, denominator, applicability, and evidence suites.

## Artifacts and privacy

Evaluation evidence is self-contained below `<output-root>/<run-id>/` in the
canonical result/config, suite results, and per-case repeat directories.
Canonical references are relative. A sanitized response is retained when a
response exists; `raw_response.txt` is written only with `--save-raw`. Raw text is
never embedded in the canonical result. URLs, credentials, headers, hostnames,
absolute paths, and environment dumps are excluded.

The result remains `lmola.evaluation_result.v1`. `model_run` is additive and
optional, so Phase 18.1 documents without it still validate. The `safety-core`
mock caller remains offline.

## CLI and local live-validation checklist

First run preflight, then the dry-run evaluation. These commands are manual local
follow-up and were not run in Codex Cloud:

```bash
lmola eval preflight --backend ollama --model <model> --base-url http://127.0.0.1:11434 --format json
lmola eval run --profile real-llm-core --backend ollama --model <model> --base-url http://127.0.0.1:11434 --temperature 0 --timeout-seconds 180 --max-tokens 2048 --repeat 3 --save-raw --format json

lmola eval preflight --backend openai_compatible_local --model <model> --base-url http://127.0.0.1:1234/v1 --format json
lmola eval run --profile real-llm-core --backend openai_compatible_local --model <model> --base-url http://127.0.0.1:1234/v1 --temperature 0 --timeout-seconds 180 --max-tokens 2048 --repeat 3 --save-raw --format json
```

Review endpoint scope, all five gates, native versus final metrics, token
applicability, and the self-contained artifact tree. Never enable confirmed
execution. Optional automated live validation must be explicitly gated with
`LMOLA_RUN_LOCAL_LLM_TESTS=1` and explicit backend/model/URL settings.
