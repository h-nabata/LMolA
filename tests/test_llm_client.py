from lmola.config import LLMConfig
from lmola.tools.llm_client import MockLLMClient


def test_mock_llm_returns_valid_json() -> None:
    res = MockLLMClient(LLMConfig(enabled=True, backend="mock")).complete_json("sys", "user")
    assert res.status == "ok"
    assert res.parsed_json is not None
    assert res.parsed_json["request_type"] == "metal_complex"
