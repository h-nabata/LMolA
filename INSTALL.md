# Installation

## venv
```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[dev]"
```

## conda/mamba
```bash
mamba create -n lmola python=3.11 -y
conda activate lmola
pip install -e ".[dev]"
```
