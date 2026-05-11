from lmola.schemas import MoleculeBuildRequest

def test_schema_parse() -> None:
    obj = MoleculeBuildRequest.model_validate({"request_type":"metal_complex","metal":"Fe","oxidation_state":2,"ligands":[{"name":"H2O","count":6}]})
    assert obj.metal == "Fe"
