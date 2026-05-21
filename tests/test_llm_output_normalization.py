from lmola.llm_output_normalization import normalize_planner_output


def test_normalizer_clean_json():
    out = normalize_planner_output('{"workflow_id":"w","input":{"type":"smiles","value":"CCO"},"status":"ok"}')
    assert out.parsed["workflow_id"] == "w"


def test_normalizer_fenced_and_think():
    raw = "<think>reasoning</think>\n```json\n{\"status\":\"unsupported\",\"reason\":\"x\",\"workflow_id\":null}\n```"
    out = normalize_planner_output(raw)
    assert out.thought_block_detected is True
    assert out.thought_block_stripped is True
    assert out.parsed["status"] == "unsupported"


def test_normalizer_prose_wrapper():
    out = normalize_planner_output('Here is JSON: {"status":"backend_unavailable","workflow_id":null,"reason":"molsimplify backend unavailable"}')
    assert out.parsed["status"] == "backend_unavailable"


def test_normalizer_multiple_json_prefers_planner_shape():
    out = normalize_planner_output('{"foo":1}\n{"status":"ok","workflow_id":"xyz_to_geometry_analysis","input":{"type":"xyz","path":"x.xyz"}}')
    assert out.parsed["workflow_id"] == "xyz_to_geometry_analysis"
