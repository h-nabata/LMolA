# Installation

## venv
```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[dev]"
```

Optional molSimplify routes:
```bash
# LMolA optional extra
pip install -e ".[molsimplify]"

# quick pip-based testing
pip install molSimplify
```

For newest molSimplify behavior, install from source:
```bash
pip install git+https://github.com/hjkgrp/molSimplify.git
```

## conda/mamba
```bash
mamba create -n lmola python=3.11 -y
conda activate lmola
pip install -e ".[dev]"
```

Robust chemistry environment route (recommended for heavier stacks):
```bash
mamba create -n lmola-chem python=3.11 -y
conda activate lmola-chem
pip install -e ".[dev]"
pip install -e ".[molsimplify]"
```

Notes:
- `molSimplify` remains optional and is not part of LMolA base dependencies.
- `pip install -e ".[dev]"` does not require molSimplify.


## Optional backend profiles

Base developer install:
```bash
pip install -e ".[dev]"
```

RDKit:
```bash
pip install -e ".[rdkit]"
```
Recommended: conda/mamba from conda-forge for robust solver support.

Open Babel:
```bash
pip install -e ".[openbabel]"
```
Recommended: conda/mamba first; pip bindings may be environment-sensitive.

molSimplify:
```bash
pip install -e ".[molsimplify]"
```
Alternative routes: `pip install molSimplify` or source install from GitHub.

xTB:
- Install with conda-forge/mamba (CLI executable).
- xTB is intentionally **not** a Python dependency in LMolA.

Aggregated optional profiles:
```bash
pip install -e ".[chem-light]"      # currently RDKit-focused
pip install -e ".[chem-inorganic]"  # currently molSimplify-focused
```

| Backend | Purpose | Extra | Recommended install route | Required for default tests? |
|---|---|---|---|---|
| ASE | structure parsing/validation | base dependency | pip base install | Yes |
| RDKit | SMILES->3D + minimal conformer ensembles | `rdkit`, `chem-light` | conda/mamba preferred; pip extra available | No |
| Open Babel | conversion and light 3D generation | `openbabel` | conda/mamba preferred; pip may be sensitive | No |
| molSimplify | inorganic generation (optional) | `molsimplify`, `chem-inorganic` | pip extra, conda/mamba, or source | No |
| xTB | relaxation | none | conda-forge/mamba executable | No (`external_tools`) |
| local LLM | NL parsing | none | local endpoint config | No |
| mock LLM | tests/fallback | none | built-in | No |


RDKit small-molecule generation is optional and supports SMILES->3D initial structures via `lmola generate examples/ethanol_smiles.yaml` and minimal conformer ensembles via `lmola generate examples/ethanol_conformers.yaml`. Conformer energies are force-field estimates only (UFF/MMFF) and are not quantum-chemical energies. Ensemble generation may fail for some SMILES, and generated conformers require researcher review.


## Open Babel (Phase 8.0)
Open Babel is optional and CLI-first (`obabel`). RDKit remains the primary small-organic SMILES-to-3D backend; Open Babel is a fallback and conversion backend. Generated structures must be reviewed by researchers and may differ from RDKit.

- Install via conda/mamba (recommended): `conda install -c conda-forge openbabel` or `mamba install -c conda-forge openbabel`.
- Optional extra: `pip install -e ".[openbabel]"` (bindings may be environment-sensitive).
- Generate fallback 3D: `lmola generate examples/ethanol_openbabel.yaml`
- Convert formats: `lmola convert examples/example.xyz --to sdf` and `lmola convert examples/example.sdf --to xyz`.
