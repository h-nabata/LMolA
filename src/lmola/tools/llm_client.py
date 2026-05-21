from __future__ import annotations

import json
import time
from typing import Protocol

import httpx
from pydantic import BaseModel

from lmola.config import LLMConfig


class LLMResult(BaseModel):
    status: str
    backend: str
    model: str | None = None
    raw_response: str = ""
    parsed_json: dict | None = None
    error_message: str | None = None
    elapsed_seconds: float | None = None


class BaseLLMClient(Protocol):
    def complete_json(self, system_prompt: str, user_prompt: str) -> LLMResult: ...


class MockLLMClient:
    def __init__(self, cfg: LLMConfig):
        self.cfg = cfg

    def complete_json(self, system_prompt: str, user_prompt: str) -> LLMResult:
        if "LMolA local workflow planner" in system_prompt:
            payload = _mock_workflow_plan(user_prompt)
        else:
            payload = {
                "request_type": "metal_complex",
                "metal": "Fe",
                "oxidation_state": 2,
                "ligands": [{"name": "H2O", "count": 6}],
                "build_options": {"expected_elements": ["Fe", "O", "H"]},
            }
        return LLMResult(
            status="ok",
            backend="mock",
            model=self.cfg.model or "mock-workflow-planner",
            raw_response=json.dumps(payload),
            parsed_json=payload,
            elapsed_seconds=0.0,
        )


class OllamaClient:
    def __init__(self, cfg: LLMConfig):
        self.cfg = cfg

    def complete_json(self, system_prompt: str, user_prompt: str) -> LLMResult:
        t0 = time.time()
        try:
            with httpx.Client(timeout=self.cfg.timeout_seconds) as client:
                r = client.post(
                    f"{self.cfg.base_url.rstrip('/')}/api/chat",
                    json={
                        "model": self.cfg.model,
                        "format": "json",
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "options": {"temperature": self.cfg.temperature or 0.0},
                        "stream": False,
                    },
                )
                r.raise_for_status()
                body = r.json()
                content = body.get("message", {}).get("content", "")
                return _result_from_raw("ollama", self.cfg.model, content, t0)
        except Exception as exc:
            return LLMResult(status="error", backend="ollama", model=self.cfg.model, error_message=str(exc))


class OpenAICompatibleLocalClient:
    def __init__(self, cfg: LLMConfig):
        self.cfg = cfg

    def complete_json(self, system_prompt: str, user_prompt: str) -> LLMResult:
        t0 = time.time()
        try:
            with httpx.Client(timeout=self.cfg.timeout_seconds) as client:
                r = client.post(
                    f"{self.cfg.base_url.rstrip('/')}/chat/completions",
                    json={
                        "model": self.cfg.model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "temperature": self.cfg.temperature or 0.0,
                        "max_tokens": self.cfg.max_tokens,
                        "response_format": {"type": "json_object"},
                    },
                )
                r.raise_for_status()
                content = r.json()["choices"][0]["message"]["content"]
                return _result_from_raw("openai_compatible_local", self.cfg.model, content, t0)
        except Exception as exc:
            return LLMResult(status="error", backend="openai_compatible_local", model=self.cfg.model, error_message=str(exc))


def _result_from_raw(backend: str, model: str | None, content: str, t0: float) -> LLMResult:
    try:
        parsed = json.loads(content)
        return LLMResult(status="ok", backend=backend, model=model, raw_response=content, parsed_json=parsed, elapsed_seconds=time.time()-t0)
    except Exception as exc:
        return LLMResult(status="error", backend=backend, model=model, raw_response=content, error_message=f"Invalid JSON from LLM: {exc}")


def make_llm_client(cfg: LLMConfig) -> BaseLLMClient:
    if cfg.backend == "mock":
        return MockLLMClient(cfg)
    if cfg.backend == "ollama":
        return OllamaClient(cfg)
    if cfg.backend == "openai_compatible_local":
        return OpenAICompatibleLocalClient(cfg)
    raise ValueError(f"Unsupported backend: {cfg.backend}")


def _mock_workflow_plan(request: str) -> dict:
    key = request.strip()
    if key == "Generate 3D structures from examples/smiles_list.csv using RDKit.":
        return {"workflow_id": "smiles_to_3d_rdkit", "input": {"type": "smiles_csv", "path": "examples/smiles_list.csv"}, "columns": {"id": "id", "smiles": "smiles"}, "outputs": {"summary_csv": True, "summary_json": True}}
    if key == "Generate structures from examples/smiles_list.csv and relax them with xTB.":
        return {"workflow_id": "smiles_to_xtb_relax", "input": {"type": "smiles_csv", "path": "examples/smiles_list.csv"}, "columns": {"id": "id", "smiles": "smiles"}, "outputs": {"summary_csv": True, "summary_json": True}}
    if key == "Generate conformers from examples/smiles_list.csv using RDKit.":
        return {"workflow_id": "smiles_to_conformers_rdkit", "input": {"type": "smiles_csv", "path": "examples/smiles_list.csv"}, "columns": {"id": "id", "smiles": "smiles"}, "outputs": {"summary_csv": True, "summary_json": True}}
    if key == "Generate 3D structures from examples/smiles_list.csv using Open Babel.":
        return {"workflow_id": "smiles_to_3d_openbabel", "input": {"type": "smiles_csv", "path": "examples/smiles_list.csv"}, "columns": {"id": "id", "smiles": "smiles"}, "outputs": {"summary_csv": True, "summary_json": True}}
    if key == "Validate examples/example.xyz and relax it with xTB.":
        return {"workflow_id": "xyz_to_xtb_relax", "input": {"type": "xyz", "path": "examples/example.xyz"}, "outputs": {"summary_csv": True, "summary_json": True}}
    if key == "Validate examples/example.xyz.":
        return {"workflow_id": "validate_xyz", "input": {"type": "xyz", "path": "examples/example.xyz"}, "outputs": {"summary_csv": True, "summary_json": True}}
    if key == "Compute RDKit molecular descriptors for examples/smiles_list.csv.":
        return {"workflow_id": "smiles_to_rdkit_descriptors", "input": {"type": "smiles_csv", "path": "examples/smiles_list.csv"}, "columns": {"id": "id", "smiles": "smiles"}, "outputs": {"summary_csv": True, "summary_json": True}}
    if key == "Compute basic molecular descriptors for ethanol SMILES CCO.":
        return {"workflow_id": "smiles_to_rdkit_descriptors", "input": {"type": "smiles", "value": "CCO"}, "outputs": {"summary_csv": True, "summary_json": True}}
    if key == "Analyze the geometry of examples/example.xyz and report suspicious short contacts.":
        return {"workflow_id": "xyz_to_geometry_analysis", "input": {"type": "xyz", "path": "examples/example.xyz"}, "outputs": {"summary_csv": True, "summary_json": True}}
    if key == "Generate an octahedral iron complex using molSimplify.":
        return {"status": "backend_unavailable", "reason": "molsimplify backend is unavailable in this environment.", "missing_backends": ["molsimplify"]}
    return {"status": "unsupported", "reason": "Requested task is not supported by the current workflow catalog.", "suggested_supported_workflows": ["smiles_to_3d_rdkit", "smiles_to_xtb_relax"]}
