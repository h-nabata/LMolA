# Phase 13.4: Artifact summarizer consistency + expanded catalog benchmark

## Scope
- Fix top-level artifact summary count propagation for batch artifacts.
- Add descriptor/geometry artifact-type hints for new workflows.
- Add expanded planner benchmark suite covering all 8 high-level workflows and unsupported/unavailable cases.
- Add benchmark markdown report output under benchmark artifact directory.

## Default benchmark command

```bash
lmola workflow benchmark-planner examples/planner_expanded_catalog_eval_cases.yaml --backend mock --format json
```

## Optional Qwen/Ollama benchmark

```bash
lmola workflow benchmark-planner examples/planner_expanded_catalog_eval_cases.yaml \
  --backend ollama \
  --base-url http://127.0.0.1:11434 \
  --model qwen2.5-coder:14b \
  --temperature 0 \
  --timeout-seconds 180 \
  --max-tokens 2048 \
  --format json
```

This optional benchmark is not required for default tests/CI.
