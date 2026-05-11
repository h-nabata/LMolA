from __future__ import annotations

from pydantic import ValidationError

from lmola.agent.prompts import SYSTEM_PROMPT
from lmola.config import is_local_llm_url_allowed, load_app_config
from lmola.schemas import AgentRunRecord, MoleculeBuildRequest
from lmola.tools.llm_client import LLMResult, make_llm_client


NOT_CONFIGURED_MSG = (
    "Local LLM mode is not configured. Configure Ollama or a local OpenAI-compatible "
    "endpoint to enable run-agent."
)


def plan_request(request_text: str) -> tuple[AgentRunRecord, LLMResult | None, MoleculeBuildRequest | None]:
    cfg = load_app_config()
    if not cfg.llm.enabled:
        return AgentRunRecord(status="error", message=NOT_CONFIGURED_MSG, request_text=request_text), None, None
    allowed, reason = is_local_llm_url_allowed(cfg.llm)
    if not allowed:
        return AgentRunRecord(status="error", message=f"Unsafe LLM endpoint: {reason}", request_text=request_text), None, None

    client = make_llm_client(cfg.llm)
    result = client.complete_json(SYSTEM_PROMPT, request_text)
    if result.status != "ok" or result.parsed_json is None:
        msg = result.error_message or "LLM request failed"
        return AgentRunRecord(status="error", message=msg, request_text=request_text), result, None

    try:
        parsed_request = MoleculeBuildRequest.model_validate(result.parsed_json)
    except ValidationError as exc:
        return AgentRunRecord(status="error", message=f"LLM JSON validation failed: {exc}", request_text=request_text), result, None

    return AgentRunRecord(status="ok", message="Parsed natural language request", request_text=request_text), result, parsed_request
