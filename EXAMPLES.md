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
