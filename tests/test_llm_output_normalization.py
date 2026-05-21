from lmola.llm_output_normalization import normalize_planner_output


def test_normalizer_clean_json():
    out = normalize_planner_output('{"workflow_id":"w","input":{"type":"smiles","value":"CCO"}}')
    assert out.parsed["workflow_id"] == "w"


def test_normalizer_fenced_and_think():
    raw = "<think>reasoning</think>\n```json\n{\"status\":\"unsupported\",\"reason\":\"x\"}\n```"
    out = normalize_planner_output(raw)
    assert out.thought_block_detected is True
    assert out.thought_block_stripped is True
    assert out.parsed["status"] == "unsupported"


def test_normalizer_prose_wrapper():
    out = normalize_planner_output('Here is JSON: {"status":"backend_unavailable","backend_id":"molsimplify"}')
    assert out.parsed["status"] == "backend_unavailable"
