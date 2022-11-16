from typing import Any, List

from blacksheep.server.rendering.abc import ModelHandler, Renderer
from blacksheep.server.rendering.models import DefaultModelHandler


def default_renderer() -> Renderer:
    from blacksheep.server.rendering.jinja2 import JinjaRenderer

    return JinjaRenderer()


class HTMLSettings:
    def __init__(self):
        self._renderer: Renderer | None = None
        self._model_handlers: List[ModelHandler] = [DefaultModelHandler()]

    def use(self, renderer: Renderer):
        self._renderer = renderer

    @property
    def model_handlers(self) -> List[ModelHandler]:
        return self._model_handlers

    @property
    def renderer(self) -> Renderer:
        if self._renderer is None:
            self._renderer = default_renderer()
        return self._renderer

    def model_to_params(self, model: Any) -> Any:
        for handler in self.model_handlers:
            try:
                return handler.model_to_view_params(model)
            except NotImplementedError:
                continue


html_settings = HTMLSettings()
