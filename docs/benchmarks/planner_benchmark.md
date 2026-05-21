# Planner benchmark

Use `lmola workflow benchmark-planner <eval_cases_yaml> --backend mock` to run benchmark mode.
Per-case artifacts are written under `outputs/benchmarks/<benchmark_id>/cases/<case_id>/`.

Benchmark outputs include:
- `benchmark_result.json`
- `benchmark_summary.csv`
- `benchmark_report.md`
- per-case artifacts under `cases/<case_id>/`.

For expanded-catalog runs use `examples/planner_expanded_catalog_eval_cases.yaml`.
