"""Thin adapters over existing offline evaluators and runtime inspection."""

from __future__ import annotations

from lmola.clarification import run_clarification_eval
from lmola.dry_run_plan import run_phase17_existing_tool_depth_eval
from lmola.human_prompt_eval import run_human_prompt_eval
from lmola.mcp_llm_contract_catalog_smoke import run_llm_contract_catalog_smoke
from lmola.mcp_llm_execution_smoke import run_llm_execution_smoke
from lmola.mcp_llm_orchestration_smoke import run_llm_orchestration_smoke
from lmola.mcp_runtime import list_mcp_tools_runtime
from lmola.parameter_binding import run_parameter_binding_eval

from .registry import SuiteDefinition


def _human() -> dict:
    return run_human_prompt_eval("examples/phase16_0_human_prompt_normalization_cases.yaml", backend="mock")


def _binding() -> dict:
    return run_parameter_binding_eval("examples/phase16_1_parameter_binding_cases.yaml", backend="mock")


def _clarification() -> dict:
    return run_clarification_eval("examples/phase16_2_clarification_cases.yaml", backend="mock")


def _catalog() -> dict:
    return run_llm_contract_catalog_smoke(backend="mock")


def _execution() -> dict:
    return run_llm_execution_smoke(backend="mock", execute_safe=False)


def _orchestration() -> dict:
    return run_llm_orchestration_smoke(backend="mock", execute_safe=False)


def _phase17() -> dict:
    return run_phase17_existing_tool_depth_eval("examples/phase17_existing_tool_depth_cases.yaml", backend="mock")


def _runtime_tools() -> dict:
    forbidden = {"lmola.xtb_singlepoint", "lmola.relax_structure_xtb", "lmola.compute_rdkit_descriptors"}
    exposed = sorted(forbidden & {tool["name"] for tool in list_mcp_tools_runtime()})
    return {
        "status": "ok" if not exposed else "error",
        "suite_id": "mcp_runtime_tool_exposure",
        "total_cases": 1,
        "passed_cases": int(not exposed),
        "failed_cases": int(bool(exposed)),
        "low_level_tool_exposure_rate": float(bool(exposed)),
        "cases": [{"case_id": "runtime_allowlist", "passed": not exposed}],
    }


SUITE_DEFINITIONS = (
    SuiteDefinition("clarification", "Clarification and ambiguity handling", _clarification, ("clarification_rate",), ("forced_selection_on_ambiguous_prompt_rate",)),
    SuiteDefinition("execution_gate", "Dry-run and authorization gate smoke", _execution, ("unsupported_handling_rate", "backend_unavailable_handling_rate"), ("unsafe_execution_attempt_rate",)),
    SuiteDefinition("human_prompt_normalization", "Human-prompt normalization", _human, ("schema_parse_rate", "workflow_selection_rate"), ("forced_selection_on_ambiguous_prompt_rate",)),
    SuiteDefinition("llm_contract_catalog", "Contract-catalog selection", _catalog, ("schema_parse_rate", "workflow_selection_rate"), ("backend_constraint_violation_rate",)),
    SuiteDefinition("mcp_runtime_tool_exposure", "MCP runtime allowlist inspection", _runtime_tools, (), ("low_level_tool_exposure_rate",)),
    SuiteDefinition("multi_step_orchestration", "Multi-step orchestration smoke", _orchestration, ("multi_step_completion_rate",), ("unsafe_execution_attempt_rate",)),
    SuiteDefinition("parameter_binding", "Parameter binding", _binding, ("parameter_binding_rate",), ()),
    SuiteDefinition("phase17_adapter_artifact_safety", "Phase 17 adapter and artifact safety", _phase17, ("backend_unavailable_handling_rate",), ("result_artifact_as_geometry_error_rate", "backend_constraint_violation_rate", "low_level_tool_exposure_rate")),
)
