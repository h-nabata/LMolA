from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class WorkflowInput(BaseModel):
    type: Literal["smiles", "smiles_csv", "xyz", "xyz_list"]
    path: str | None = None
    value: str | None = None


class WorkflowStep(BaseModel):
    tool: str
    params: dict[str, Any] | None = None


class WorkflowOutputs(BaseModel):
    summary_csv: bool = True
    summary_json: bool = True
    keep_intermediate_runs: bool = True
    fail_fast: bool = False


class WorkflowRequest(BaseModel):
    workflow_id: str
    input: WorkflowInput
    columns: dict[str, str] | None = None
    steps: list[WorkflowStep] | None = None
    outputs: WorkflowOutputs = Field(default_factory=WorkflowOutputs)
    metadata: dict[str, Any] | None = None


class BatchItemResult(BaseModel):
    batch_id: str
    item_index: int
    item_id: str
    input_type: str
    input_value: str
    workflow_id: str
    generate_status: str | None = None
    generate_run_dir: str | None = None
    primary_structure: str | None = None
    conformer_ensemble_path: str | None = None
    validation_status: str | None = None
    validation_report_path: str | None = None
    relax_status: str | None = None
    relax_run_dir: str | None = None
    relaxed_structure: str | None = None
    energy: float | None = None
    energy_units: str | None = None
    error_message: str | None = None


class WorkflowSummary(BaseModel):
    batch_id: str
    workflow_id: str
    item_count: int
    ok_count: int
    error_count: int


class WorkflowExecutionResult(BaseModel):
    status: str
    message: str
    batch_dir: str | None = None
    summary_csv: str | None = None
    summary_json: str | None = None
    summary: WorkflowSummary | None = None
