from lmola.config import load_request_yaml

def test_load_request_yaml() -> None:
    req = load_request_yaml("examples/fe_h2o6.yaml")
    assert req.request_type == "metal_complex"
