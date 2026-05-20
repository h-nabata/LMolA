from __future__ import annotations

import os

import pytest

from lmola.agent.planner_eval import run_planner_eval


@pytest.mark.ollama
def test_ollama_backend_eval_optional(monkeypatch) -> None:
    if os.getenv("LMOLA_RUN_OLLAMA_TESTS") != "1":
        pytest.skip("Set LMOLA_RUN_OLLAMA_TESTS=1 to enable optional Ollama planner benchmark test.")
    monkeypatch.setenv("LMOLA_LLM_ENABLED", "1")
    monkeypatch.setenv("LMOLA_LLM_BACKEND", "ollama")
    monkeypatch.setenv("LMOLA_LLM_BASE_URL", os.getenv("LMOLA_OLLAMA_BASE_URL", "http://127.0.0.1:11434"))
    monkeypatch.setenv("LMOLA_LLM_MODEL", os.getenv("LMOLA_OLLAMA_MODEL", "qwen2.5-coder:14b"))
    result = run_planner_eval("examples/planner_backend_eval_cases.yaml")
    assert result.total_cases >= 1
