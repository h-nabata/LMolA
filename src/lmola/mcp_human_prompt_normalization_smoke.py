from __future__ import annotations

from typing import Any

from lmola.human_prompt_eval import run_human_prompt_eval


def run_mcp_human_prompt_normalization_smoke(**kwargs: Any) -> dict[str, Any]:
    cases = kwargs.get("cases", "examples/phase16_0_human_prompt_normalization_cases.yaml")
    return run_human_prompt_eval(cases, **kwargs)
