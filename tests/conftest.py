from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def clean_lmola_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    for env_name in (
        "LMOLA_LLM_ENABLED",
        "LMOLA_LLM_BACKEND",
        "LMOLA_LLM_BASE_URL",
        "LMOLA_LLM_MODEL",
    ):
        monkeypatch.delenv(env_name, raising=False)
