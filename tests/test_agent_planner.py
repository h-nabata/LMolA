from lmola.agent.planner import NOT_CONFIGURED_MSG, plan_request


def test_planner_not_configured(clean_lmola_config) -> None:
    rec, llm, req = plan_request("build complex")
    assert rec.status == "error"
    assert rec.message == NOT_CONFIGURED_MSG
    assert llm is None
    assert req is None
