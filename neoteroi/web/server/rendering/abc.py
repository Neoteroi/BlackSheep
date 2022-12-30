from abc import ABC, abstractmethod
from typing import Any


class ModelHandler(ABC):
    """Type that can handle a model object for a view template."""

    @abstractmethod
    def model_to_view_params(self, model: Any) -> Any:
        """Converts a model to parameters for a template view."""


class Renderer(ABC):
    """Type that can render HTML views."""

    @abstractmethod
    def render(self, template: str, model, **kwargs) -> str:
        """Renders a view synchronously."""

    @abstractmethod
    async def render_async(self, template: str, model, **kwargs) -> str:
        """Renders a view asynchronously."""

    @abstractmethod
    def bind_antiforgery_handler(self, handler) -> None:
        """Applies extensions for an antiforgery handler."""
