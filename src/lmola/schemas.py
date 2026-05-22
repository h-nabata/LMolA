from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class LigandSpec(BaseModel):
    name: str
    count: int = Field(gt=0)


class BuildOptions(BaseModel):
    expected_elements: list[str] = Field(default_factory=list)
    add_hydrogens: bool = True
    embed_method: str = "ETKDG"
    optimize: str | None = "uff"
    num_conformers: int = Field(default=1, ge=1)
    random_seed: int | None = 61453
    output_formats: list[str] = Field(default_factory=lambda: ["xyz"])
    prune_rms_thresh: float | None = Field(default=None, ge=0.0)
    force_field: Literal["uff", "mmff"] | None = None
    max_embed_attempts: int | None = Field(default=None, ge=1)


class MetalComplexRequest(BaseModel):
    request_type: Literal["metal_complex"]
    metal: str
    oxidation_state: int
    ligands: list[LigandSpec]
    build_options: BuildOptions = Field(default_factory=BuildOptions)


class MoleculeBuildRequest(BaseModel):
    request_type: str
    backend: str | None = None
    metal: str | None = None
    oxidation_state: int | None = None
    ligands: list[LigandSpec] = Field(default_factory=list)
    smiles: str | None = None
    build_options: BuildOptions = Field(default_factory=BuildOptions)


class ToolCallRecord(BaseModel):
    timestamp: str
    tool: str
    command: list[str] = Field(default_factory=list)
    cwd: str = ""
    returncode: int | None = None
    stdout_excerpt: str = ""
    stderr_excerpt: str = ""
    stdout_path: str = ""
    stderr_path: str = ""
    status: Literal["ok", "error", "not_implemented"]


class ToolResult(BaseModel):
    status: Literal["ok", "error", "not_implemented"]
    message: str
    backend: str = ""
    stdout: str = ""
    stderr: str = ""
    returncode: int | None = None
    command: list[str] = Field(default_factory=list)
    cwd: str = ""
    generated_files: list[str] = Field(default_factory=list)
    artifact_files: list[str] = Field(default_factory=list)
    primary_structure: str | None = None
    validation_report_path: str | None = None
    run_dir: str = ""
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    energy: float | None = None
    normal_termination: bool | None = None


class ValidationReport(BaseModel):
    valid: bool
    messages: list[str]
    atom_count: int = 0
    detected_elements: list[str] = Field(default_factory=list)


class AgentRunRecord(BaseModel):
    status: str
    message: str
    request_text: str
