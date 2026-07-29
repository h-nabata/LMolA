import json
import os
import httpx
import pytest

from lmola.config import LLMConfig
from lmola.evaluation.models import EvaluationRunResult
from lmola.evaluation.preflight import endpoint_scope, preflight_local_llm
from lmola.evaluation.registry import get_profile, list_suites
from lmola.evaluation.runner import GATE_IDS, run_evaluation
from lmola.tools.llm_client import OllamaClient, OpenAICompatibleLocalClient, LLMResult


class FakeClient:
    def __init__(self, responses=None):
        self.calls = []
        self.responses = iter(responses or [])

    def complete_json(self, system_prompt, user_prompt):
        self.calls.append((system_prompt, user_prompt))
        try:
            payload = next(self.responses)
        except StopIteration:
            payload = {"status": "unsupported", "workflow_id": None}
        return LLMResult(status="ok", backend="fake", model="fixture", raw_response=json.dumps(payload),
                         parsed_json=payload, prompt_tokens=2, completion_tokens=3, total_tokens=5,
                         elapsed_seconds=0.01)


def test_registry_classifies_real_profile():
    definitions = {s.suite_id: s for s in list_suites(include_real=True)}
    profile = get_profile("real-llm-core")
    assert {definitions[s].classification for s in profile.suite_ids} == {"model_involved", "deterministic_guard"}
    assert sum(definitions[s].classification == "model_involved" for s in profile.suite_ids) == 3


def test_endpoint_policy_and_injected_preflight():
    assert endpoint_scope("http://127.0.0.1:11434") == "loopback"
    assert endpoint_scope("http://10.0.0.2:1234/v1") == "private_network"
    with pytest.raises(ValueError, match="public remote"):
        endpoint_scope("https://8.8.8.8/v1")
    cfg = LLMConfig(backend="ollama", model="fixture", base_url="http://127.0.0.1:11434")
    assert preflight_local_llm(cfg, request=lambda **_: object())["endpoint_scope"] == "loopback"


def test_provider_usage_mapping(monkeypatch):
    def handler(request):
        if request.url.path.endswith("api/chat"):
            return httpx.Response(200, json={"message": {"content": "{}"}, "prompt_eval_count": 4, "eval_count": 6})
        return httpx.Response(200, json={"id": "local-request", "choices": [{"message": {"content": "{}"}}],
                                         "usage": {"prompt_tokens": 7, "completion_tokens": 8, "total_tokens": 15}})
    transport = httpx.MockTransport(handler)
    original = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: original(transport=transport, **kwargs))
    ollama = OllamaClient(LLMConfig(backend="ollama", model="m", base_url="http://127.0.0.1"))
    openai = OpenAICompatibleLocalClient(LLMConfig(backend="openai_compatible_local", model="m", base_url="http://127.0.0.1/v1"))
    assert (ollama.complete_json("s", "u").prompt_tokens, ollama.complete_json("s", "u").total_tokens) == (4, 10)
    result = openai.complete_json("s", "u")
    assert (result.prompt_tokens, result.completion_tokens, result.total_tokens) == (7, 8, 15)


def test_real_run_is_offline_contained_and_private(tmp_path):
    fake = FakeClient([{}] * 14)
    result = run_evaluation(profile_id="real-llm-core", backend="ollama", model="fixture",
        base_url="http://127.0.0.1:11434", output_root=tmp_path, llm_client=fake, skip_preflight=True)
    assert result.status == "pass"
    assert len(fake.calls) == 14
    assert {g.gate_id for g in result.hard_gate_results if g.status == "pass"} == set(GATE_IDS)
    assert all(not c.evidence.get("confirmed_execution_attempted") and not c.evidence.get("actual_execution")
               for s in result.suite_results for c in s.cases)
    native = next(m for m in result.utility_metrics if m.metric_id == "native_workflow_selection_rate")
    final = next(m for m in result.utility_metrics if m.metric_id == "final_validated_selection_rate")
    fallback = next(m for m in result.utility_metrics if m.metric_id == "fallback_rate")
    assert native.value < final.value and fallback.value > 0
    run_root = next(tmp_path.iterdir())
    canonical = (run_root / "evaluation_result.json").read_text()
    assert "http://" not in canonical and str(tmp_path) not in canonical
    assert not list(run_root.rglob("raw_response.txt"))
    assert list(run_root.rglob("sanitized_response.txt"))


def test_raw_is_opt_in_and_old_v1_validates(tmp_path):
    result = run_evaluation(profile_id="real-llm-core", backend="openai_compatible_local", model="fixture",
        base_url="http://127.0.0.1:1234/v1", output_root=tmp_path, llm_client=FakeClient(),
        skip_preflight=True, save_raw=True)
    run_root = next(tmp_path.iterdir())
    assert list(run_root.rglob("raw_response.txt"))
    old = result.model_dump()
    old.pop("model_run")
    assert EvaluationRunResult.model_validate(old).model_run is None


def test_endpoint_error_is_not_a_pass(tmp_path):
    class ErrorClient:
        def complete_json(self, *_):
            return LLMResult(status="error", backend="fake", error_message="unreachable")
    result = run_evaluation(profile_id="real-llm-core", backend="ollama", model="fixture",
        base_url="http://127.0.0.1:11434", output_root=tmp_path, llm_client=ErrorClient(), skip_preflight=True)
    assert result.status == "fail"
    assert next(m for m in result.utility_metrics if m.metric_id == "endpoint_error_rate").value == 1.0


@pytest.mark.ollama
def test_optional_live_local_model_preflight():
    if os.getenv("LMOLA_RUN_LOCAL_LLM_TESTS") != "1":
        pytest.skip("set LMOLA_RUN_LOCAL_LLM_TESTS=1 for explicit local validation")
    backend = os.environ["LMOLA_LLM_BACKEND"]
    model = os.environ["LMOLA_LLM_MODEL"]
    base_url = os.environ["LMOLA_LLM_BASE_URL"]
    assert preflight_local_llm(LLMConfig(enabled=True, backend=backend, model=model,
                                         base_url=base_url))["status"] == "ok"
