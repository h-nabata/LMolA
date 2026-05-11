from lmola.agent.planner import plan_request

def test_planner_placeholder() -> None:
    rec = plan_request("build complex")
    assert rec.status == "not_implemented"
