# Descriptor and geometry workflows

## smiles_to_rdkit_descriptors
Inputs: `smiles`, `smiles_csv`.
Outputs: `descriptors.csv`, `descriptors.json`, plus `summary.csv` and `summary.json`.

Example YAML:
```yaml
workflow_id: smiles_to_rdkit_descriptors
input:
  type: smiles_csv
  path: examples/smiles_list.csv
columns:
  id: id
  smiles: smiles
```

Invalid SMILES are handled per-row with `status=error` and `error_message`; batch execution continues unless `fail_fast=true`.

## xyz_to_geometry_analysis
Inputs: `xyz`, `xyz_list`. For `xyz`, both inline `input.value` and file `input.path` are supported.
Outputs: `geometry_analysis.json` (and `geometry_analysis.csv` for list inputs), plus `summary.csv` and `summary.json`.

Example YAML:
```yaml
workflow_id: xyz_to_geometry_analysis
input:
  type: xyz
  path: examples/example.xyz
```

Geometry analysis is diagnostic and should not be treated as full chemical validation.
Limitations: this phase does not add heavy external backends.
