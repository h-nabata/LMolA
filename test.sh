#!/usr/bin/env bash
set -euo pipefail

python -m pip install -e ".[dev]" >/tmp/lmola_phase16_pip_install.log 2>&1

bind_cli() {
  local prompt="$1"
  lmola workflow bind-parameters --prompt "$prompt" --language en --format json
}

check_safety() {
  local label="$1"
  local json_path="$2"
  python - "$label" "$json_path" <<'PY'
import json,sys
label,path=sys.argv[1],sys.argv[2]
p=json.load(open(path))
print(f"{label}_keys:", sorted(p.keys()))
print(f"{label}_status:", p.get("status"))
print(f"{label}_schema:", p.get("schema_version"))
print(f"{label}_safety:", p.get("safety"))
s=p.get("safety") or {}
for k,v in {
  "execution_allowed": False,
  "dry_run_recommended": True,
  "requires_confirmation": True,
  "requires_allow_execution": True,
}.items():
  if k not in s:
    raise SystemExit(f"{label}: missing safety field {k}")
  if s.get(k) is not v:
    raise SystemExit(f"{label}: safety.{k} must be {v}, actual={s.get(k)}")
PY
}

bind_cli "Run an xTB single point for examples/water.xyz with charge 0 and multiplicity 1. Do not optimize geometry." > /tmp/bind_singlepoint_water_filename.json
check_safety "singlepoint" /tmp/bind_singlepoint_water_filename.json
python - <<'PY'
import json
p=json.load(open('/tmp/bind_singlepoint_water_filename.json'))
solv=((p.get('bound_parameters') or {}).get('solvent') or {})
sv=(solv.get('solvent') or {}).get('value')
sm=(solv.get('model') or {}).get('value')
print('solvent_value:', sv)
print('solvent_model:', sm)
if sv is not None: raise SystemExit('water.xyz filename must not be interpreted as solvent=water')
if sm is not None: raise SystemExit('water.xyz filename must not set solvent model')
PY

bind_cli "Run an xTB single point for examples/mol.xyz in ALPB water without optimizing geometry." > /tmp/bind_singlepoint_alpb_water.json
check_safety "alpb_water" /tmp/bind_singlepoint_alpb_water.json
python - <<'PY'
import json
p=json.load(open('/tmp/bind_singlepoint_alpb_water.json'))
solv=((p.get('bound_parameters') or {}).get('solvent') or {})
sv=(solv.get('solvent') or {}).get('value')
sm=(solv.get('model') or {}).get('value')
print('status:', p.get('status'))
print('solvent_value:', sv)
print('solvent_model:', sm)
if p.get('status')!='ok': raise SystemExit('status should be ok')
if str(sv).lower()!='water': raise SystemExit('explicit ALPB water prompt should bind solvent=water')
if str(sm).lower()!='alpb': raise SystemExit('explicit ALPB water prompt should bind model=alpb')
PY

lmola workflow eval-parameter-binding examples/phase16_1_parameter_binding_cases.yaml --backend mock --format json > /tmp/eval_parameter_binding.json
lmola mcp parameter-binding-smoke --backend mock --cases examples/phase16_1_parameter_binding_cases.yaml --format json > /tmp/mcp_parameter_binding.json
