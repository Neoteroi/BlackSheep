from dataclasses import asdict, is_dataclass
from typing import Any

from .abc import ModelHandler


class DefaultModelHandler(ModelHandler):
    def model_to_view_params(self, model: Any) -> Any:
        if isinstance(model, dict):
            return model
        if is_dataclass(model):
            return asdict(model)
        if hasattr(model, "__dict__"):
            return model.__dict__
        return model
