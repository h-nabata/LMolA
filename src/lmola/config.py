from __future__ import annotations

import os
import ipaddress
from urllib.parse import urlparse
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
    allow_remote: bool = False
    unsafe_allow_remote: bool = False


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
    if "LMOLA_LLM_ALLOW_REMOTE" in os.environ:
        cfg.llm.allow_remote = os.environ["LMOLA_LLM_ALLOW_REMOTE"].lower() in {"1", "true", "yes"}
    if "LMOLA_LLM_UNSAFE_ALLOW_REMOTE" in os.environ:
        cfg.llm.unsafe_allow_remote = os.environ["LMOLA_LLM_UNSAFE_ALLOW_REMOTE"].lower() in {"1", "true", "yes"}

    return cfg


def redacted_llm_config(cfg: LLMConfig) -> dict:
    payload = cfg.model_dump()
    for key in list(payload.keys()):
        if "key" in key.lower() or "token" in key.lower() or "secret" in key.lower():
            payload[key] = "***REDACTED***"
    return payload


def is_local_llm_url_allowed(cfg: LLMConfig) -> tuple[bool, str]:
    if cfg.backend not in {"ollama", "openai_compatible_local"}:
        return True, "URL safety checks apply only to local HTTP backends."
    if not cfg.base_url:
        return False, "Local LLM base_url is required for this backend."
    parsed = urlparse(cfg.base_url)
    if parsed.scheme not in {"http", "https"}:
        return False, "Local LLM base_url must use http or https."
    host = parsed.hostname
    if not host:
        return False, "Local LLM base_url must include a hostname."
    if host in {"localhost", "127.0.0.1", "::1"}:
        return True, "Loopback address allowed."
    try:
        addr = ipaddress.ip_address(host)
        if addr.is_private:
            return True, "Private network address allowed for local deployments."
        if addr.is_loopback:
            return True, "Loopback address allowed."
        if cfg.allow_remote or cfg.unsafe_allow_remote:
            return True, "Remote address allowed by explicit override."
        return False, "Public remote LLM URLs are blocked unless allow_remote or unsafe_allow_remote is set."
    except ValueError:
        if cfg.allow_remote or cfg.unsafe_allow_remote:
            return True, "Remote hostname allowed by explicit override."
        return False, "Non-local hostnames are blocked unless allow_remote or unsafe_allow_remote is set."
