from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from blacksheep.messages import Request, Response
from blacksheep.server.files.static import get_response_for_static_content
from blacksheep.server.resources import get_resource_file_content


@dataclass
class UIOptions:
    spec_url: str
    page_title: str


class UIProvider(ABC):
    def __init__(self, ui_path: str) -> None:
        super().__init__()
        self.ui_path = ui_path

    @abstractmethod
    def build_ui(self, options: UIOptions) -> None:
        """
        Prepares the UI that will be served by the UI route.
        """

    @abstractmethod
    def get_ui_handler(self) -> Callable[[Request], Response]:
        """
        Returns a request handler for the route that serves a UI.
        """


class SwaggerUIProvider(UIProvider):
    def __init__(self, ui_path: str = "/docs") -> None:
        super().__init__(ui_path)

        self._ui_html: bytes = b""

    def get_openapi_ui_html(self, options: UIOptions) -> str:
        """
        Returns the HTML response to serve the Swagger UI.
        """
        return (
            get_resource_file_content("swagger-ui.html")
            .replace("##SPEC_URL##", options.spec_url)
            .replace("##PAGE_TITLE##", options.page_title)
        )

    def build_ui(self, options: UIOptions) -> None:
        self._ui_html = self.get_openapi_ui_html(options).encode("utf8")

    def get_ui_handler(self) -> Callable[[Request], Response]:
        current_time = datetime.utcnow().timestamp()

        def get_open_api_ui(request: Request) -> Response:
            return get_response_for_static_content(
                request, b"text/html; charset=utf-8", self._ui_html, current_time
            )

        return get_open_api_ui


class ReDocUIProvider(UIProvider):
    def __init__(self, ui_path: str = "/redocs") -> None:
        super().__init__(ui_path)

        self._ui_html: bytes = b""

    def get_openapi_ui_html(self, options: UIOptions) -> str:
        """
        Returns the HTML response to serve the Swagger UI.
        """
        return (
            get_resource_file_content("redoc-ui.html")
            .replace("##SPEC_URL##", options.spec_url)
            .replace("##PAGE_TITLE##", options.page_title)
        )

    def build_ui(self, options: UIOptions) -> None:
        self._ui_html = self.get_openapi_ui_html(options).encode("utf8")

    def get_ui_handler(self) -> Callable[[Request], Response]:
        current_time = datetime.utcnow().timestamp()

        def get_open_api_ui(request: Request) -> Response:
            return get_response_for_static_content(
                request, b"text/html; charset=utf-8", self._ui_html, current_time
            )

        return get_open_api_ui
