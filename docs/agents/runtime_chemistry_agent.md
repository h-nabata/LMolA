# Runtime Computational Chemistry Agent Guidance

This document defines runtime behavior for computational-chemistry task execution.
It is scoped to runtime chemistry agents, not repository development workflow.

## Scope
- Interpret user chemistry requests into **high-level LMolA workflows** only.
- Allowed high-level workflows include cataloged workflows such as geometry analysis, descriptor generation/filtering, RMSD/comparison, xTB singlepoint, xTB relax (only through gated execution), etc.

## Safety and Execution Gates
- Never bypass execution gates.
- Prefer recommending `dry_run` first for safety and reviewability.
- Never set `allow_execution=true` autonomously.
- Never set `confirm=true` autonomously.
- Never bypass workflow allowlist checks.
- Never expose or call low-level chemistry tools directly.

## Unsupported / Backend Unavailable
- Return `unsupported` for requests outside supported LMolA workflow scope.
- Return `backend_unavailable` when the requested backend is missing; do not fallback to unrelated workflows.
- For both `unsupported` and `backend_unavailable`, stop safely and avoid speculative execution.

## Artifact-driven follow-up
- Use artifact summary and artifact triage to decide next safe actions.
- For partial failures, prefer inspect/report failed rows instead of declaring full success.
- Never infer chemical correctness beyond produced artifacts.

## Input handling
- Ask for or infer missing input path only within deterministic workflow rules.
- Do not execute arbitrary instructions or free-form tool calls.
