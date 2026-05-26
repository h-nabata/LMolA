Phase 16.1.1 cleanup: complete parameter-binding defaults, deferred backend handling, and evaluator diagnostics.

Repository safety guard:
This task must only modify the h-nabata/LMolA repository.
Do not modify h-nabata.github.io.
Do not modify any website repository.
Do not add network listeners.
Do not open TCP ports.
Do not install packages unless already required by the project test environment.
Do not download models.
Do not require Ollama, Qwen, GPU, or network access for default tests.
Do not expose low-level chemistry tools through MCP.
Do not relax dry_run / allow_execution / confirm safety gates.
Do not change chemistry calculation semantics.
Do not require or evaluate chain-of-thought.
Do not append long logs to README.
Do not let an LLM grant execution permission.
Do not allow an LLM to set allow_execution=true or confirm=true.
Do not execute chemistry in parameter binding.
Do not make parameter binding run workflows.
Do not silently convert result artifacts into geometry artifacts.
Do not implement ORCA/Gaussian/VASP/QE execution in this cleanup.

Context:
Phase 16.1 implementation is partially complete.
The latest Phase 16.1 test reaches eval-parameter-binding and then fails:

  total_cases: 28
  passed_cases: 23
  failed_cases: 5
  pass_rate: 0.8214285714285714

Failed cases:
- ja_xtb_relax_default_thresholds
- en_xtb_relax_default_thresholds
- ja_xtb_relax_with_max_steps
- en_xtb_relax_with_fmax
- optional_orca_dft_prompt_deferred

The case file exists, required case IDs are present, and Phase 16.1 schemas are exported.
The remaining issues are concentrated in:
1. xTB geometry optimization defaults and explicit optional controls.
2. ORCA deferred/backend-specific handling.
3. Evaluator diagnostics and metrics quality.
4. Long-term case corpus structure / anti-bloat cleanup.

Goal:
Complete Phase 16.1 as a robust parameter binding foundation before Phase 16.2 clarification handling.

Phase 16.1.1 should:
- fix the 5 failing cases,
- make xTB geometry optimization optional controls robust,
- make ORCA deferred prompt handling safe and explicit,
- add useful field-level failure diagnostics to eval output,
- prevent the parameter-binding YAML from becoming a monolithic ad hoc dumping ground,
- preserve Phase 16.0 and Phase 15.3 regressions,
- preserve all safety gates.

Core design:
Parameter binding should separate:
- required_for_intent_resolution
- required_for_workflow_execution
- assumed_defaults
- clarification_recommended
- optional_backend_controls
- unsupported_parameters
- backend_specific

Do not treat optional backend controls such as fmax/max_steps as hard missing when the workflow/backend has a safe default.
Do treat operation ambiguity, missing input files, missing second structure for RMSD, and result-artifact-as-geometry situations conservatively.

A. Fix xTB geometry optimization parameter binding.

The following prompts/cases must pass:
- ja_xtb_relax_default_thresholds
- en_xtb_relax_default_thresholds
- ja_xtb_relax_with_max_steps
- en_xtb_relax_with_fmax

Expected behavior for xTB relaxation default threshold cases:
Prompt examples:
- "Optimize examples/mol.xyz with xTB."
- Japanese equivalent.

Expected:
- status = ok
- operation = geometry_optimization
- requested_backend = xtb
- input_kind = xyz
- input_files contains role=primary_structure
- optimize_geometry = true
- singlepoint_only = false
- geometry_modification_allowed = true
- candidate_workflows may include xyz_to_xtb_relax if available
- force_threshold is not hard missing
- max_steps is not hard missing
- force_threshold and/or max_steps appear in assumed_defaults
- missing_parameters does not contain force_threshold or max_steps
- charge/multiplicity may be assumed default or clarification_recommended, but must not be high-confidence user_explicit unless explicitly stated
- safety.execution_allowed = false
- safety.dry_run_recommended = true
- safety.requires_confirmation = true
- safety.requires_allow_execution = true

Expected behavior for explicit max_steps cases:
Prompt examples:
- "Optimize examples/mol.xyz with xTB for at most 200 steps."
- Japanese equivalent.

Expected:
- operation = geometry_optimization
- geometry_optimization_controls.max_steps.value = 200
- geometry_optimization_controls.max_steps.source = user_explicit
- max_steps should not appear as a missing parameter
- force_threshold may remain assumed_default if unspecified

Expected behavior for explicit fmax/force threshold cases:
Prompt examples:
- "Optimize examples/mol.xyz with xTB using fmax 0.05."
- "Optimize examples/mol.xyz with xTB using force threshold 0.05 eV/A."

Expected:
- operation = geometry_optimization
- geometry_optimization_controls.force_threshold.value = 0.05 or equivalent numeric value
- geometry_optimization_controls.force_threshold.source = user_explicit
- force_threshold should not appear as missing
- max_steps may remain assumed_default if unspecified

Implementation requirements:
- Recognize max_steps variants:
  - max steps
  - maximum steps
  - at most N steps
  - N steps
  - 最大 N ステップ
- Recognize fmax/force threshold variants:
  - fmax 0.05
  - force threshold 0.05
  - convergence force 0.05
  - force convergence 0.05
  - 収束閾値
  - 力の閾値
- Do not overfit only to the exact case text. Use small normalization helpers.

B. Fix ORCA deferred parameter binding.

The failing case:
- optional_orca_dft_prompt_deferred

Prompt concept:
"Prepare an ORCA B3LYP def2-SVP single point for examples/mol.xyz with charge 0 and multiplicity 1."

Expected:
- requested_backend = orca
- method_family = dft
- operation = singlepoint_energy
- input_kind = xyz
- input_files contains primary_structure
- electronic_state.charge.value = 0
- electronic_state.multiplicity.value = 1
- backend_specific may include:
  - orca.functional = B3LYP
  - orca.basis = def2-SVP
  or equivalent normalized keys
- status should be unsupported or needs_clarification if ORCA workflow execution is not implemented
- candidate_workflows must not include hallucinated ORCA workflow IDs
- do not claim execution is possible
- unsupported_parameters or warnings should mention ORCA backend/adapter/workflow is not available or deferred
- safety.execution_allowed = false
- safety.dry_run_recommended = true

Important:
Do not implement an ORCA runner in Phase 16.1.1.
This is only parameter binding and safe deferred handling.

C. Add evaluator diagnostics.

The current eval output only says which cases failed.
Improve eval-parameter-binding and parameter-binding-smoke output so failures are actionable.

For each case, include:
- case_id
- passed
- status
- expected_status
- actual_status
- failed_checks: list[dict]

Each failed check should include:
- field
- expected
- actual
- message

Example:
{
  "field": "geometry_optimization_controls.force_threshold",
  "expected": "assumed_default or user_explicit",
  "actual": {"value": null, "status": "missing"},
  "message": "force_threshold must not be hard missing for xTB relaxation when backend defaults exist."
}

For suite-level output, include:
- failed_case_ids
- failure_reasons or failed_case_summaries
- checks_total
- checks_passed
- checks_failed

D. Improve metrics.

Currently all pass-rate metrics appear identical, suggesting case-level pass/fail may be reused for all categories.
Make field/category metrics more meaningful where practical.

At minimum, compute independent counts for:
- binding_pass_rate
- input_file_binding_pass_rate
- electronic_state_binding_pass_rate
- solvent_binding_pass_rate
- periodic_binding_pass_rate
- atom_selection_binding_pass_rate
- default_policy_pass_rate
- missing_parameter_pass_rate
- clarification_recommended_pass_rate
- unsupported_parameter_pass_rate
- safety_pass_rate

It is acceptable if some categories are "not applicable" for some cases.
Do not count not-applicable checks as failures.
If a category has no applicable checks, return 1.0 or include an explicit applicable_count=0 field.

E. Stabilize case corpus metadata and avoid YAML bloat.

Keep examples/phase16_1_parameter_binding_cases.yaml for backward compatibility in this phase, because existing scripts expect it.

However, add top-level metadata:
- schema_version: lmola.parameter_binding_cases.v1
- suite_id: parameter_binding_core_v1
- description
- tags: [phase16_1, parameter_binding, core]
- cases: [...]

If the file currently has a bare list of cases, migrate it to the above mapping structure and update the loader to support both old and new forms.

Each case should have:
- case_id
- language
- prompt
- tags
- expected_status
- expected_operation
- expected_input_kind
- expected_input_file_roles
- expected_backend
- expected_charge
- expected_multiplicity
- expected_spin
- expected_spin_representation
- expected_solvent
- expected_solvent_model
- expected_periodic
- expected_pbc_axes
- expected_atom_selection
- expected_atom_ranges
- expected_requested_outputs_contains
- expected_constraints_contains
- expected_assumed_defaults_contains
- expected_missing_parameters_contains
- expected_clarification_recommended_contains
- expected_unsupported_parameters_contains
- forbidden_candidate_workflows
- expected_candidate_workflows_contains
- expected_safety
- notes

Use [] for list fields and null for scalar fields when not applicable.

Add tags to cases:
- core
- xtb
- defaults
- explicit_controls
- solvent
- pbc
- atom_selection
- rmsd
- comparison
- artifact
- deferred_backend
- morfeus
- orca
- unsupported
- ambiguity
as appropriate.

Do not keep adding all future backend cases to this one file indefinitely.
Add a short documentation note or code comment that this file is the Phase 16.1 core/smoke corpus and that future backend-specific cases should move to:
- tests/evals/parameter_binding/core_v1.yaml
- tests/evals/parameter_binding/xtb_v1.yaml
- tests/evals/parameter_binding/deferred_backends_v1.yaml
- tests/evals/parameter_binding/morfeus_v1.yaml
or equivalent future locations.

Do not actually require a large migration in this cleanup unless it is straightforward.
Backward compatibility matters more.

F. Preserve and extend schema export.

lmola schema export --format json should still include:
- parameter_value_schema
- input_file_binding_schema
- electronic_state_binding_schema
- solvent_binding_schema
- periodic_binding_schema
- atom_selection_binding_schema
- calculation_controls_binding_schema
- geometry_optimization_controls_schema
- bound_parameter_set_schema
- parameter_binding_result_schema
- parameter_binding_eval_schema

Also ensure serialized schema/export text includes:
- lmola.parameter_binding.v1
- lmola.parameter_binding_eval.v1
- lmola.parameter_binding_cases.v1
- bound_parameters
- missing_parameters
- assumed_defaults
- clarification_recommended
- unsupported_parameters
- backend_specific
- failed_checks
- failure_reasons
- execution_allowed
- dry_run_recommended

G. Preserve CLI/MCP surfaces.

The following must work:
- lmola workflow bind-parameters --prompt TEXT --language en --format json
- lmola workflow eval-parameter-binding examples/phase16_1_parameter_binding_cases.yaml --backend mock --format json
- lmola mcp parameter-binding-smoke --backend mock --cases examples/phase16_1_parameter_binding_cases.yaml --format json
- lmola mcp call-tool lmola.bind_human_prompt_parameters --args-json '{"prompt":"...","language":"en","compact":false}'

All are read-only.
None should execute chemistry or workflows.
All should preserve:
- execution_allowed=false
- dry_run_recommended=true
- requires_confirmation=true
- requires_allow_execution=true

H. Preserve regressions.

Do not break:
- lmola workflow eval-human-prompts examples/phase16_0_human_prompt_normalization_cases.yaml --backend mock --format json
- lmola mcp human-prompt-normalization-smoke --backend mock --format json
- lmola mcp llm-contract-catalog-smoke --backend mock --format json
- lmola workflow normalize-request for Japanese/English singlepoint, generic xTB ambiguity, RMSD
- lmola.normalize_human_prompt
- runtime hiding of low-level tools
- ruff check .

I. Required targeted behavior.

1. xTB relax default:
Prompt:
Optimize examples/mol.xyz with xTB.

Expected:
- status=ok
- operation=geometry_optimization
- requested_backend=xtb
- optimize_geometry=true
- force_threshold and max_steps not hard missing
- assumed_defaults contains force_threshold and/or max_steps
- execution_allowed=false

2. xTB max steps:
Prompt:
Optimize examples/mol.xyz with xTB for at most 200 steps.

Expected:
- max_steps.value=200
- max_steps.source=user_explicit
- max_steps.status=bound
- max_steps not in missing_parameters

3. xTB fmax:
Prompt:
Optimize examples/mol.xyz with xTB using fmax 0.05.

Expected:
- force_threshold.value=0.05
- force_threshold.source=user_explicit
- force_threshold.status=bound
- force_threshold not in missing_parameters

4. ORCA deferred:
Prompt:
Prepare an ORCA B3LYP def2-SVP single point for examples/mol.xyz with charge 0 and multiplicity 1.

Expected:
- requested_backend=orca
- method_family=dft
- operation=singlepoint_energy
- charge=0
- multiplicity=1
- backend_specific contains orca/B3LYP/def2-SVP information if possible
- status=unsupported or needs_clarification if ORCA workflow unavailable
- no hallucinated executable ORCA workflow
- execution_allowed=false

J. Verification commands to run before reporting back.

1. Case metadata and required field check:
python - <<'PY'
from pathlib import Path

text = Path("examples/phase16_1_parameter_binding_cases.yaml").read_text(encoding="utf-8")

required = [
    "schema_version",
    "lmola.parameter_binding_cases.v1",
    "suite_id",
    "parameter_binding_core_v1",
    "tags",
    "cases",
    "expected_input_kind",
    "expected_input_file_roles",
    "expected_status",
    "expected_operation",
    "expected_safety",
    "execution_allowed",
    "dry_run_recommended",
    "expected_assumed_defaults_contains",
    "expected_missing_parameters_contains",
    "expected_clarification_recommended_contains",
    "expected_unsupported_parameters_contains",
    "forbidden_candidate_workflows",
    "expected_candidate_workflows_contains",
]

missing = [x for x in required if x not in text]
print("missing:", missing)
if missing:
    raise SystemExit(f"case file missing {missing}")
PY

2. Schema export:
lmola schema export --format json > /tmp/schema_phase16_1_1.json

python - <<'PY'
import json
from pathlib import Path

p = json.loads(Path("/tmp/schema_phase16_1_1.json").read_text())
text = json.dumps(p)

required = [
    "parameter_value_schema",
    "input_file_binding_schema",
    "electronic_state_binding_schema",
    "solvent_binding_schema",
    "periodic_binding_schema",
    "atom_selection_binding_schema",
    "calculation_controls_binding_schema",
    "geometry_optimization_controls_schema",
    "bound_parameter_set_schema",
    "parameter_binding_result_schema",
    "parameter_binding_eval_schema",
    "lmola.parameter_binding.v1",
    "lmola.parameter_binding_eval.v1",
    "bound_parameters",
    "assumed_defaults",
    "clarification_recommended",
    "backend_specific",
    "failed_checks",
    "execution_allowed",
]

missing = [x for x in required if x not in text]
print("missing:", missing)
if missing:
    raise SystemExit(f"schema export missing {missing}")
PY

3. Mock eval:
lmola workflow eval-parameter-binding examples/phase16_1_parameter_binding_cases.yaml --backend mock --format json > /tmp/eval_parameter_binding_phase16_1_1.json

python - <<'PY'
import json
from pathlib import Path

p = json.loads(Path("/tmp/eval_parameter_binding_phase16_1_1.json").read_text())

for key in [
    "status",
    "total_cases",
    "passed_cases",
    "failed_cases",
    "pass_rate",
    "binding_pass_rate",
    "input_file_binding_pass_rate",
    "electronic_state_binding_pass_rate",
    "solvent_binding_pass_rate",
    "periodic_binding_pass_rate",
    "atom_selection_binding_pass_rate",
    "default_policy_pass_rate",
    "missing_parameter_pass_rate",
    "clarification_recommended_pass_rate",
    "unsupported_parameter_pass_rate",
    "safety_pass_rate",
    "unsafe_execution_attempt_rate",
    "result_artifact_as_geometry_error_rate",
    "forced_selection_on_ambiguous_prompt_rate",
    "failed_case_ids",
]:
    print(key, p.get(key))

if p.get("status") != "ok":
    print(json.dumps(p, indent=2, ensure_ascii=False)[:8000])
    raise SystemExit("eval-parameter-binding status is not ok")
if float(p.get("pass_rate", 0)) != 1.0:
    print(json.dumps(p, indent=2, ensure_ascii=False)[:8000])
    raise SystemExit("eval-parameter-binding pass_rate is not 1.0")
if int(p.get("total_cases") or 0) < 24:
    raise SystemExit("expected at least 24 cases")

for metric in [
    "unsafe_execution_attempt_rate",
    "result_artifact_as_geometry_error_rate",
    "forced_selection_on_ambiguous_prompt_rate",
]:
    if float(p.get(metric, 0)) != 0.0:
        raise SystemExit(f"{metric} should be 0")

cases = p.get("cases") or []
if not cases:
    raise SystemExit("eval output missing cases")
for case in cases:
    if "case_id" not in case:
        raise SystemExit("case output missing case_id")
    if "passed" not in case:
        raise SystemExit("case output missing passed")
    if not case.get("passed") and "failed_checks" not in case:
        raise SystemExit("failed case output should include failed_checks")
PY

4. Targeted CLI checks:
python - <<'PY'
import json
import subprocess

def bind(prompt: str, language: str = "en") -> dict:
    raw = subprocess.check_output(
        [
            "lmola",
            "workflow",
            "bind-parameters",
            "--prompt",
            prompt,
            "--language",
            language,
            "--format",
            "json",
        ],
        text=True,
    )
    return json.loads(raw)

def val(x):
    if isinstance(x, dict) and "value" in x:
        return x.get("value")
    return x

def src(x):
    if isinstance(x, dict):
        return x.get("source")
    return None

def status_of(x):
    if isinstance(x, dict):
        return x.get("status")
    return None

def safety_ok(p):
    s = p.get("safety") or {}
    assert s.get("execution_allowed") is False
    assert s.get("dry_run_recommended") is True
    assert s.get("requires_confirmation") is True
    assert s.get("requires_allow_execution") is True

p = bind("Optimize examples/mol.xyz with xTB.")
bp = p.get("bound_parameters") or {}
controls = bp.get("calculation_controls") or {}
geom = bp.get("geometry_optimization_controls") or {}
missing = p.get("missing_parameters") or []
assumed = p.get("assumed_defaults") or []
print("relax_default:", p.get("status"), val(controls.get("operation")), missing, assumed, geom)
safety_ok(p)
assert p.get("status") == "ok"
assert val(controls.get("operation")) == "geometry_optimization"
assert val(controls.get("optimize_geometry")) is True
assert not any("force_threshold" in str(x) or "max_steps" in str(x) for x in missing)
assert any("force_threshold" in str(x) or "max_steps" in str(x) for x in assumed)

p = bind("Optimize examples/mol.xyz with xTB for at most 200 steps.")
bp = p.get("bound_parameters") or {}
geom = bp.get("geometry_optimization_controls") or {}
max_steps = geom.get("max_steps")
missing = p.get("missing_parameters") or []
print("relax_max_steps:", p.get("status"), max_steps, missing)
safety_ok(p)
assert p.get("status") == "ok"
assert val(max_steps) == 200
assert src(max_steps) == "user_explicit"
assert status_of(max_steps) == "bound"
assert not any("max_steps" in str(x) for x in missing)

p = bind("Optimize examples/mol.xyz with xTB using fmax 0.05.")
bp = p.get("bound_parameters") or {}
geom = bp.get("geometry_optimization_controls") or {}
force_threshold = geom.get("force_threshold")
missing = p.get("missing_parameters") or []
print("relax_fmax:", p.get("status"), force_threshold, missing)
safety_ok(p)
assert p.get("status") == "ok"
assert abs(float(val(force_threshold)) - 0.05) < 1e-12
assert src(force_threshold) == "user_explicit"
assert status_of(force_threshold) == "bound"
assert not any("force_threshold" in str(x) or "fmax" in str(x).lower() for x in missing)

p = bind("Prepare an ORCA B3LYP def2-SVP single point for examples/mol.xyz with charge 0 and multiplicity 1.")
bp = p.get("bound_parameters") or {}
controls = bp.get("calculation_controls") or {}
electronic = bp.get("electronic_state") or {}
backend_specific = bp.get("backend_specific") or {}
candidates = [c.get("workflow_id") for c in p.get("candidate_workflows") or []]
print("orca_deferred:", p.get("status"), val(controls.get("requested_backend")), val(controls.get("operation")), val(electronic.get("charge")), val(electronic.get("multiplicity")), backend_specific, candidates)
safety_ok(p)
assert p.get("status") in {"unsupported", "needs_clarification", "ambiguous"}
assert val(controls.get("requested_backend")) == "orca"
assert val(controls.get("operation")) == "singlepoint_energy"
assert val(electronic.get("charge")) == 0
assert val(electronic.get("multiplicity")) == 1
assert not any("orca" in str(c).lower() and "workflow" in str(c).lower() for c in candidates)
assert "xyz_to_xtb_relax" not in candidates
PY

5. MCP smoke:
lmola mcp parameter-binding-smoke --backend mock --cases examples/phase16_1_parameter_binding_cases.yaml --format json > /tmp/mcp_parameter_binding_phase16_1_1.json

python - <<'PY'
import json
from pathlib import Path

p = json.loads(Path("/tmp/mcp_parameter_binding_phase16_1_1.json").read_text())

print("status:", p.get("status"))
print("pass_rate:", p.get("pass_rate"))
print("failed_case_ids:", p.get("failed_case_ids"))

if p.get("status") != "ok":
    raise SystemExit("parameter-binding-smoke status is not ok")
if float(p.get("pass_rate", 0)) != 1.0:
    raise SystemExit("parameter-binding-smoke pass_rate is not 1.0")
PY

6. Runtime safety:
lmola mcp runtime-tools --format json > /tmp/runtime_tools_phase16_1_1.json

python - <<'PY'
import json
from pathlib import Path

p = json.loads(Path("/tmp/runtime_tools_phase16_1_1.json").read_text())
tools = p.get("tools", p if isinstance(p, list) else [])
names = [t.get("name") for t in tools]

required = ["lmola.bind_human_prompt_parameters"]
missing = [x for x in required if x not in names]
print("missing_runtime_tools:", missing)
if missing:
    raise SystemExit(f"missing runtime tools: {missing}")

low_level = [
    "lmola.generate_small_molecule_rdkit",
    "lmola.generate_small_molecule_openbabel",
    "lmola.generate_metal_complex_molsimplify",
    "lmola.relax_structure_xtb",
    "lmola.validate_structure_ase",
    "lmola.xtb_singlepoint",
    "lmola.compute_rmsd",
    "lmola.compare_two_geometries",
    "lmola.count_element_atoms",
    "lmola.split_molecule_by_file_order",
    "lmola.filter_molecules_by_descriptors",
]
exposed = [x for x in low_level if x in names]
print("exposed_low_level_tools:", exposed)
if exposed:
    raise SystemExit(f"low-level tools exposed: {exposed}")
PY

7. Planner context:
lmola mcp call-tool lmola.get_planner_context --args-json '{}' > /tmp/planner_context_phase16_1_1.json

python - <<'PY'
import json
from pathlib import Path

p = json.loads(Path("/tmp/planner_context_phase16_1_1.json").read_text())
text = json.dumps(p, ensure_ascii=False)

required = [
    "parameter binding",
    "bind_human_prompt_parameters",
    "missing_parameters",
    "assumed_defaults",
    "clarification_recommended",
    "backend_specific",
    "execution_allowed",
]

missing = [x for x in required if x not in text]
print("planner_context_missing:", missing)
print("planner_context_size:", len(text))
if missing:
    raise SystemExit(f"planner context missing: {missing}")
if len(text) > 450000:
    raise SystemExit("planner context too large")
PY

8. Regressions:
lmola workflow eval-human-prompts examples/phase16_0_human_prompt_normalization_cases.yaml --backend mock --format json > /tmp/phase16_0_regression.json
lmola mcp human-prompt-normalization-smoke --backend mock --format json > /tmp/phase16_0_mcp_regression.json
lmola mcp llm-contract-catalog-smoke --backend mock --format json > /tmp/phase15_3_regression.json

python - <<'PY'
import json
from pathlib import Path

for label, path in [
    ("phase16_0_eval", "/tmp/phase16_0_regression.json"),
    ("phase16_0_mcp", "/tmp/phase16_0_mcp_regression.json"),
    ("phase15_3", "/tmp/phase15_3_regression.json"),
]:
    p = json.loads(Path(path).read_text())
    print(label, p.get("status"), p.get("pass_rate"), p.get("failed_case_ids"))
    if p.get("status") != "ok":
        raise SystemExit(f"{label} status not ok")
    if float(p.get("pass_rate", 0)) != 1.0:
        raise SystemExit(f"{label} pass_rate not 1.0")
PY

9. Lint/tests:
ruff check .
pytest -m "not external_tools" -q
pytest -m external_tools -q -rs

10. Optional Qwen:
If the user-provided Phase 16.1 test script exists as test.sh, run:
  RUN_QWEN=1 bash test.sh > test_phase16-1-qwen.txt

Otherwise, run:
  lmola mcp parameter-binding-smoke \
    --backend ollama \
    --base-url http://127.0.0.1:11434 \
    --model qwen2.5-coder:14b \
    --temperature 0 \
    --timeout-seconds 600 \
    --max-tokens 2048 \
    --cases examples/phase16_1_parameter_binding_cases.yaml \
    --format json

Report back:
- files changed
- 5 failing cases fixed
- case YAML schema metadata added
- whether file loader supports both old list-form and new mapping-form cases
- failure diagnostics added
- metric calculation improved
- xTB relax default handling summary
- max_steps/fmax binding examples
- ORCA deferred binding example
- safety policy unchanged confirmation
- ruff/test summary
