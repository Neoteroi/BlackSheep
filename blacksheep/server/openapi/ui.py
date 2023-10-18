from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Optional

from blacksheep.messages import Request, Response
from blacksheep.server.files.static import get_response_for_static_content
from blacksheep.server.resources import get_resource_file_content
from blacksheep.utils.time import utcnow

SWAGGER_UI_CDN = (
    "https://cdn.jsdelivr.net/npm/swagger-ui-dist@3.30.0/swagger-ui-bundle.js"
)
SWAGGER_UI_CSS = "https://cdn.jsdelivr.net/npm/swagger-ui-dist@3.30.0/swagger-ui.css"
SWAGGER_UI_FONT = None

REDOC_UI_CDN = "https://cdn.jsdelivr.net/npm/redoc@next/bundles/redoc.standalone.js"
REDOC_UI_CSS = None
REDOC_UI_FONT = (
    "https://fonts.googleapis.com/css?family=Montserrat:300,400,700|Roboto:300,400,700"
)


@dataclass
class CdnOptions:
    js_cdn_url: str
    css_cdn_url: Optional[str] = None
    fontset_cdn_url: Optional[str] = None


@dataclass
class UIOptions:
    spec_url: str
    page_title: str


class UIProvider(ABC):
    cdn: CdnOptions
    ui_path: str

    _default_cdn: CdnOptions

    def __init__(
        self,
        ui_path: str,
        cdn: Optional[CdnOptions] = None,
    ) -> None:
        super().__init__()
        self.ui_path = ui_path
        self.cdn = cdn if cdn else self._default_cdn

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
    _default_cdn = CdnOptions(SWAGGER_UI_CDN, SWAGGER_UI_CSS, SWAGGER_UI_FONT)

    def __init__(
        self,
        ui_path: str = "/docs",
        cdn: Optional[CdnOptions] = None,
    ) -> None:
        super().__init__(ui_path, cdn)

        self._ui_html: bytes = b""

    def get_openapi_ui_html(self, options: UIOptions) -> str:
        """
        Returns the HTML response to serve the Swagger UI.
        """
        return (
            get_resource_file_content("swagger-ui.html")
            .replace("##SPEC_URL##", options.spec_url)
            .replace("##PAGE_TITLE##", options.page_title)
            .replace("##JS_CDN##", self.cdn.js_cdn_url)
            .replace("##CSS_CDN##", self.cdn.css_cdn_url)
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


class ReDocUIProvider(UIProvider):
    _default_cdn = CdnOptions(REDOC_UI_CDN, REDOC_UI_CSS, REDOC_UI_FONT)

    def __init__(
        self, ui_path: str = "/redocs", cdn: Optional[CdnOptions] = None
    ) -> None:
        super().__init__(ui_path, cdn)

        self._ui_html: bytes = b""

    def get_openapi_ui_html(self, options: UIOptions) -> str:
        """
        Returns the HTML response to serve the Swagger UI.
        """
        return (
            get_resource_file_content("redoc-ui.html")
            .replace("##SPEC_URL##", options.spec_url)
            .replace("##PAGE_TITLE##", options.page_title)
            .replace("##JS_CDN##", self.cdn.js_cdn_url)
            .replace("##FONT_CDN##", self.cdn.fontset_cdn_url)
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
