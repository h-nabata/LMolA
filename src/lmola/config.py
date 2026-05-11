from __future__ import annotations
import yaml
from lmola.schemas import MoleculeBuildRequest

def load_request_yaml(path: str) -> MoleculeBuildRequest:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return MoleculeBuildRequest.model_validate(data)
