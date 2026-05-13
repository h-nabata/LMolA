from lmola.schemas import MoleculeBuildRequest

def test_schema_parse() -> None:
    obj = MoleculeBuildRequest.model_validate({"request_type":"metal_complex","metal":"Fe","oxidation_state":2,"ligands":[{"name":"H2O","count":6}]})
    assert obj.metal == "Fe"


def test_small_molecule_num_conformers_parse() -> None:
    obj = MoleculeBuildRequest.model_validate(
        {
            "request_type": "small_molecule",
            "backend": "rdkit",
            "smiles": "CCO",
            "build_options": {"num_conformers": 5, "prune_rms_thresh": 0.25, "max_embed_attempts": 20},
        }
    )
    assert obj.build_options.num_conformers == 5
    assert obj.build_options.prune_rms_thresh == 0.25
    assert obj.build_options.max_embed_attempts == 20
