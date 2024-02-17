from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Optional

from blacksheep.messages import Request, Response
from blacksheep.server.files.static import get_response_for_static_content
from blacksheep.server.resources import get_resource_file_content
from blacksheep.utils.time import utcnow

SWAGGER_UI_JS_URL = (
    "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"
)
SWAGGER_UI_CSS_URL = "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css"
SWAGGER_UI_FONT = None

REDOC_UI_JS_URL = "https://cdn.jsdelivr.net/npm/redoc@next/bundles/redoc.standalone.js"
REDOC_UI_CSS_URL = None
REDOC_UI_FONT_URL = (
    "https://fonts.googleapis.com/css?family=Montserrat:300,400,700|Roboto:300,400,700"
)


@dataclass
class UIFilesOptions:
    js_url: str
    css_url: Optional[str] = None
    fonts_url: Optional[str] = None


@dataclass
class UIOptions:
    spec_url: str
    page_title: str


class UIProvider(ABC):
    ui_files: UIFilesOptions
    ui_path: str

    def __init__(
        self,
        ui_path: str,
        ui_files: Optional[UIFilesOptions] = None,
    ) -> None:
        super().__init__()
        self.ui_path = ui_path
        self.ui_files = ui_files if ui_files else self.default_ui_files

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

    @property
    def default_ui_files(self) -> UIFilesOptions: ...


class SwaggerUIProvider(UIProvider):
    def __init__(
        self,
        ui_path: str = "/docs",
        ui_files_options: Optional[UIFilesOptions] = None,
    ) -> None:
        super().__init__(ui_path, ui_files_options)

        self._ui_html: bytes = b""

    def get_openapi_ui_html(self, options: UIOptions) -> str:
        """
        Returns the HTML response to serve the Swagger UI.
        """
        return (
            get_resource_file_content("swagger-ui.html")
            .replace("##SPEC_URL##", options.spec_url)
            .replace("##PAGE_TITLE##", options.page_title)
            .replace("##JS_URL##", self.ui_files.js_url)
            .replace("##CSS_URL##", self.ui_files.css_url or "")
        )

    def build_ui(self, options: UIOptions) -> None:
        self._ui_html = self.get_openapi_ui_html(options).encode("utf8")

    def get_ui_handler(self) -> Callable[[Request], Response]:
        current_time = utcnow().timestamp()

        def get_open_api_ui(request: Request) -> Response:
            return get_response_for_static_content(
                request, b"text/html; charset=utf-8", self._ui_html, current_time
            )

        return get_open_api_ui

    @property
    def default_ui_files(self) -> UIFilesOptions:
        return UIFilesOptions(SWAGGER_UI_JS_URL, SWAGGER_UI_CSS_URL, SWAGGER_UI_FONT)


class ReDocUIProvider(UIProvider):
    def __init__(
        self, ui_path: str = "/redocs", ui_files: Optional[UIFilesOptions] = None
    ) -> None:
        super().__init__(ui_path, ui_files)

        self._ui_html: bytes = b""

    def get_openapi_ui_html(self, options: UIOptions) -> str:
        """
        Returns the HTML response to serve the Swagger UI.
        """
        return (
            get_resource_file_content("redoc-ui.html")
            .replace("##SPEC_URL##", options.spec_url)
            .replace("##PAGE_TITLE##", options.page_title)
            .replace("##JS_URL##", self.ui_files.js_url)
            .replace("##FONT_URL##", self.ui_files.fonts_url or "")
        )

    def build_ui(self, options: UIOptions) -> None:
        self._ui_html = self.get_openapi_ui_html(options).encode("utf8")

    def get_ui_handler(self) -> Callable[[Request], Response]:
        current_time = utcnow().timestamp()

        def get_open_api_ui(request: Request) -> Response:
            return get_response_for_static_content(
                request, b"text/html; charset=utf-8", self._ui_html, current_time
            )

        return get_open_api_ui

    @property
    def default_ui_files(self) -> UIFilesOptions:
        return UIFilesOptions(REDOC_UI_JS_URL, REDOC_UI_CSS_URL, REDOC_UI_FONT_URL)
