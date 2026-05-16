# Examples

- Fe(II) hexaaqua complex: `examples/fe_h2o6.yaml`
- Co ammine chloride complex: `examples/co_nh3_cl.yaml`
- Generic octahedral metal complex: `examples/generic_octahedral.yaml`
- LLM-free YAML workflow: `lmola generate <file.yaml>`
- Future natural-language mode: `lmola run-agent "..."` (placeholder)

## Local LLM examples (Phase 4.0)
`run-agent` converts natural language to structured JSON validated by LMolA schemas before deterministic generation.

Without config:
```bash
lmola run-agent "Generate an octahedral Fe(II) complex with six water ligands."
```
returns a safe configuration error.

With local config enabled (`ollama` or `openai_compatible_local`), LMolA requests strict JSON only and rejects invalid JSON.


## Relaxation example (optional xTB)
```bash
lmola relax examples/example.xyz --method xtb
```
If `xtb` is not installed, LMolA still creates a run directory and writes a safe error result.

Real xTB tests are marked `external_tools` and skipped by default.

Reminder: relaxed structures are computational models and should be reviewed by researchers.


Manual external xTB verification:
```bash
pytest -m external_tools -q
```

## molSimplify external verification (optional)
LMolA currently supports a deliberately narrow molSimplify generation case:
- Fe(II) with six water ligands (`examples/fe_h2o6.yaml`).

Run generation:
```bash
lmola generate examples/fe_h2o6.yaml
```

Run external-tool tests:
```bash
pytest -m external_tools -q
```

Notes:
- molSimplify is optional; default tests do not require it.
- If molSimplify is unavailable, generation safely records an error result and artifacts.
- If molSimplify is available, LMolA records tool call metadata and validates generated XYZ when detected.
- Generated structures are initial computational models and require researcher review.


## RDKit small-molecule examples (optional)

Single-conformer example:
```bash
lmola generate examples/ethanol_smiles.yaml
```

Minimal conformer-ensemble example:
```bash
lmola generate examples/ethanol_conformers.yaml
```

Notes:
- RDKit is optional and can be installed with `pip install -e ".[rdkit]"` (or conda/mamba).
- Conformer energies are force-field estimates only (UFF/MMFF), not quantum-chemical energies.
- Ensemble generation may fail for some SMILES; generated conformers require researcher review.


## Open Babel (Phase 8.0)
Open Babel is optional and CLI-first (`obabel`). RDKit remains the primary small-organic SMILES-to-3D backend; Open Babel is a fallback and conversion backend. Generated structures must be reviewed by researchers and may differ from RDKit.

- Install via conda/mamba (recommended): `conda install -c conda-forge openbabel` or `mamba install -c conda-forge openbabel`.
- Optional extra: `pip install -e ".[openbabel]"` (bindings may be environment-sensitive).
- Generate fallback 3D: `lmola generate examples/ethanol_openbabel.yaml`
- Convert formats: `lmola convert examples/example.xyz --to sdf` and `lmola convert examples/example.sdf --to xyz`.

## Backend policy reminders
- Ethanol SMILES examples prefer RDKit and can fallback to Open Babel.
- Transition-metal examples (for example Fe(H2O)6) target molSimplify.
- Relaxation examples use xTB.
- Validation output is expected in `validation_report.json` when performed.

## Typed Tool Registry

Use `lmola tools list` to enumerate registered typed tools and `lmola tools inspect TOOL_NAME` for schema and availability details. The registry exposes only explicit, schema-validated capabilities and does not allow arbitrary command execution.

## Workflow examples

- Batch input CSV: `examples/smiles_list.csv` with at least `id` and `smiles` columns.
- Example deterministic workflows:
  - `examples/workflow_smiles_to_3d_rdkit.yaml`
  - `examples/workflow_smiles_to_xtb.yaml`

Batch outputs include `summary.csv` and `summary.json` with per-item status and artifact paths.

Not yet included: autonomous planning, LLM workflow generation, multi-agent execution, CREST conformer search, and reaction path search.


## Workflow summary fields

For workflow batch runs:
- `summary.csv` is for quick human review.
- `summary.json` is for programmatic consumption and future planner/agent interfaces.

Important fields include:
- `batch_id`, `item_id`, `input_value`, `workflow_id`
- `generate_status`, `primary_structure`, `primary_structure_path`
- `conformer_ensemble_path` (only for `conformer_ensemble.json`)
- `sdf_path` (if `.sdf` output exists)
- `validation_status`, `validation_report_path`
- `relax_status`, `relaxed_structure`, `relaxed_structure_path`
- `energy`, `energy_units`, `failed_step`, `error_message`

## Local LLM workflow planning

```bash
lmola workflow plan "Generate structures from examples/smiles_list.csv and relax them with xTB."
lmola workflow plan "Generate conformers from examples/smiles_list.csv using RDKit."
lmola workflow plan "Validate examples/example.xyz."
```

Each command creates a plan directory with:
- `natural_language_request.txt`
- `planner_prompt.txt`
- `llm_response.raw.txt`
- `planned_workflow.yaml` / `planned_workflow.json` (validated LLM proposal)
- `canonical_workflow.yaml` / `canonical_workflow.json` (catalog-expanded execution candidate)
- `planning_result.json`
- `README_plan.md`


## Real local LLM planner evaluation (Phase 10.5)

Use planner evaluation to measure planning quality only (no workflow execution):

```bash
lmola workflow eval-planner examples/planner_eval_cases.yaml
```

- Uses the same planner pipeline as `lmola workflow plan`.
- Writes `eval_summary.csv`, `eval_summary.json`, and `eval_result.json` under `outputs/eval_...`.
- Supports `mock`, `ollama`, and `openai_compatible_local` via existing LLM config.
- For LM Studio / vLLM / llama.cpp server / text-generation-webui, use `openai_compatible_local` when they expose a local OpenAI-compatible endpoint.
- Default tests use mock only.
- Security remains unchanged: endpoint safety checks apply and public remote endpoints are blocked unless unsafe override is explicitly enabled.

Example Ollama config:

```yaml
llm:
  enabled: true
  backend: ollama
  base_url: http://127.0.0.1:11434
  model: qwen2.5:7b
  temperature: 0
  timeout_seconds: 60
  max_tokens: 2048
```

Example OpenAI-compatible local config:

```yaml
llm:
  enabled: true
  backend: openai_compatible_local
  base_url: http://127.0.0.1:1234/v1
  model: local-model-name
  temperature: 0
  timeout_seconds: 60
  max_tokens: 2048
```

Evaluation metrics include `workflow_match`, `tools_match`, `parse_ok`, `validation_ok`, `canonicalization_ok`, `unsupported_handled`, and overall `pass_rate`.
