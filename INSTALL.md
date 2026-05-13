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
