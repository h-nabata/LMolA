# LMolA Examples

All paths below are repository-relative. Start with the base development install from [INSTALL.md](INSTALL.md). Generated structures and computed results require researcher review.

## Deterministic YAML

```bash
lmola validate examples/example.xyz
lmola generate examples/generic_octahedral.yaml
lmola workflow run examples/workflow_smiles_to_3d_rdkit.yaml
```

Other inputs include `examples/fe_h2o6.yaml`, `examples/ethanol_smiles.yaml`, `examples/ethanol_conformers.yaml`, and `examples/smiles_list.csv`. Generation may require the backend named by the workflow: molSimplify for the narrow inorganic example, RDKit for RDKit SMILES workflows, or Open Babel for Open Babel generation/conversion. Missing optional tools report unavailable or fail safely.

Inspect available deterministic contracts before use:

```bash
lmola workflow list
lmola workflow inspect validate_xyz
lmola workflow validate-contracts
```

## Natural-language dry-run planning

```bash
lmola workflow normalize-request --prompt "Validate examples/example.xyz"
lmola workflow clarify-parameters --prompt "Relax my structure"
lmola workflow bind-parameters --prompt "Validate examples/example.xyz"
lmola workflow dry-run-plan --prompt "Validate examples/example.xyz"
lmola workflow plan "Generate structures from examples/smiles_list.csv and relax them with xTB."
```

These commands create or inspect structured proposals; they do not let LLM output authorize execution. The mock backend supports offline evaluation. Ollama and OpenAI-compatible local endpoints are opt-in and must be configured explicitly. Dry-run expected artifacts do not yet exist.

## MCP stdio

```bash
lmola mcp runtime-tools --format json
lmola mcp serve-stdio
# In another suitable client context:
lmola mcp client-smoke --format json
```

The stdio runtime exposes high-level LMolA planning, validation, dry-run, gated workflow, audit, and artifact operations—not low-level backend tools. See [MCP client notes](docs/mcp/lmola_mcp_client_notes.md).

## Optional confirmed execution

Real MCP execution requires an allowlisted, valid workflow and all deterministic gates: `dry_run=false`, `allow_execution=true`, and `confirm=true`. Runtime agents must not set these values autonomously. Review a dry-run first.

Optional direct CLI examples include:

```bash
lmola relax examples/example.xyz --method xtb
lmola generate examples/ethanol_smiles.yaml
lmola convert examples/example.xyz --to sdf
```

They require xTB, RDKit, or Open Babel respectively where applicable. Successful execution does not prove scientific correctness.

## Evaluation

```bash
pytest -m "not external_tools" -q
lmola workflow eval-planner examples/planner_eval_cases.yaml
lmola workflow eval-clarifications examples/phase16_2_clarification_cases.yaml
lmola workflow eval-dry-run-plans examples/phase16_3_dry_run_plan_cases.yaml
```

Default tests and mock evaluation require no optional chemistry executable or real model. Run `pytest -m external_tools -q` only in an environment where the relevant optional tools are intentionally installed. Real local-LLM evaluation is also opt-in and evaluates planning behavior, not scientific authority.
