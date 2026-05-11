from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from lmola.schemas import MoleculeBuildRequest


class LLMConfig(BaseModel):
    enabled: bool = False
    backend: str = "mock"
    base_url: str | None = None
    model: str | None = None
    timeout_seconds: int = Field(default=60, gt=0)
    temperature: float | None = None
    max_tokens: int | None = Field(default=None, gt=0)


class AppConfig(BaseModel):
    llm: LLMConfig = Field(default_factory=LLMConfig)


def load_request_yaml(path: str) -> MoleculeBuildRequest:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return MoleculeBuildRequest.model_validate(data)


def _find_config_path() -> Path | None:
    candidates = [Path.cwd() / ".lmola" / "config.yaml", Path.home() / ".lmola" / "config.yaml"]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def load_app_config() -> AppConfig:
    path = _find_config_path()
    payload: dict = {}
    if path:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cfg = AppConfig.model_validate(payload)

    if "LMOLA_LLM_ENABLED" in os.environ:
        cfg.llm.enabled = os.environ["LMOLA_LLM_ENABLED"].lower() in {"1", "true", "yes"}
    if os.getenv("LMOLA_LLM_BACKEND"):
        cfg.llm.backend = os.environ["LMOLA_LLM_BACKEND"]
    if os.getenv("LMOLA_LLM_BASE_URL"):
        cfg.llm.base_url = os.environ["LMOLA_LLM_BASE_URL"]
    if os.getenv("LMOLA_LLM_MODEL"):
        cfg.llm.model = os.environ["LMOLA_LLM_MODEL"]

    return cfg


def redacted_llm_config(cfg: LLMConfig) -> dict:
    return cfg.model_dump()
