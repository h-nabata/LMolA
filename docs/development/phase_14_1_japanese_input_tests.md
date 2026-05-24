# Phase 14.1 Japanese input tests

Added a Japanese planner evaluation suite for Phase 14 workflows:

- xTB single-point without geometry optimization
- broad two-geometry comparison
- RMSD
- element counting
- file-order splitting
- descriptor-threshold filtering
- unsupported DFT TS/NEB handling

The mock planner now covers these Japanese smoke cases so default tests can validate
Japanese request routing without requiring Ollama, GPU, network, or real LLM access.
