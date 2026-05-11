from lmola.agent.planner import NOT_CONFIGURED_MSG, plan_request

def test_planner_not_configured(clean_lmola_config) -> None:
    rec, llm, req = plan_request("build complex")
    assert rec.status == "error"
    assert rec.message == NOT_CONFIGURED_MSG
    assert llm is None
    assert req is None


def test_planner_rejects_public_remote(clean_lmola_config, monkeypatch) -> None:
    monkeypatch.setenv("LMOLA_LLM_ENABLED", "1")
    monkeypatch.setenv("LMOLA_LLM_BACKEND", "ollama")
    monkeypatch.setenv("LMOLA_LLM_BASE_URL", "https://example.com")
    rec, llm, req = plan_request("build complex")
    assert rec.status == "error"
    assert "Unsafe LLM endpoint" in rec.message
    assert llm is None
    assert req is None
