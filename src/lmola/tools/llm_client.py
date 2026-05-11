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
            model=self.cfg.model or "mock-model",
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
