from lmola.schemas import AgentRunRecord

def plan_request(request_text: str) -> AgentRunRecord:
    return AgentRunRecord(status="not_implemented", message="LLM agent mode is not configured in pre-alpha scaffold", request_text=request_text)
