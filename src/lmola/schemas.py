from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class LigandSpec(BaseModel):
    name: str
    count: int = Field(gt=0)


class BuildOptions(BaseModel):
    expected_elements: list[str] = Field(default_factory=list)


class MetalComplexRequest(BaseModel):
    request_type: Literal["metal_complex"]
    metal: str
    oxidation_state: int
    ligands: list[LigandSpec]
    build_options: BuildOptions = Field(default_factory=BuildOptions)


class MoleculeBuildRequest(BaseModel):
    request_type: str
    metal: str | None = None
    oxidation_state: int | None = None
    ligands: list[LigandSpec] = Field(default_factory=list)
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
    stdout: str = ""
    stderr: str = ""
    returncode: int | None = None
    command: list[str] = Field(default_factory=list)
    cwd: str = ""
    generated_files: list[str] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)


class ValidationReport(BaseModel):
    valid: bool
    messages: list[str]
    atom_count: int = 0
    detected_elements: list[str] = Field(default_factory=list)


class AgentRunRecord(BaseModel):
    status: str
    message: str
    request_text: str
