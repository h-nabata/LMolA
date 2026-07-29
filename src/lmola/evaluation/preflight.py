"""Strict local endpoint validation and non-destructive provider preflight."""

from __future__ import annotations

import ipaddress
from typing import Callable
from urllib.parse import urlparse

import httpx

from lmola.config import LLMConfig


def endpoint_scope(base_url: str) -> str:
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("base URL must be credential-free HTTP(S) with a hostname")
    host = parsed.hostname
    if host == "localhost":
        return "loopback"
    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise ValueError("local model endpoints must use a loopback or private IP address") from exc
    if address.is_loopback:
        return "loopback"
    if address.is_private:
        return "private_network"
    raise ValueError("public remote model endpoints are forbidden for evaluation")


def preflight_local_llm(cfg: LLMConfig, request: Callable[..., object] | None = None) -> dict:
    if cfg.backend not in {"ollama", "openai_compatible_local"}:
        raise ValueError("backend must be ollama or openai_compatible_local")
    if not cfg.model:
        raise ValueError("model identifier is required")
    if not cfg.base_url:
        raise ValueError("base URL is required")
    scope = endpoint_scope(cfg.base_url)
    url = cfg.base_url.rstrip("/") + ("/api/tags" if cfg.backend == "ollama" else "/models")
    try:
        if request is None:
            response = httpx.get(url, timeout=min(cfg.timeout_seconds, 10))
        else:
            response = request(url=url, timeout=min(cfg.timeout_seconds, 10))
        if hasattr(response, "raise_for_status"):
            response.raise_for_status()
    except Exception as exc:
        raise ValueError(f"local model preflight failed: {type(exc).__name__}") from exc
    return {"status": "ok", "backend": cfg.backend, "model": cfg.model,
            "endpoint_scope": scope, "interface_status": "provisional"}
