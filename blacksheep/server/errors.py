import html
import traceback

from blacksheep.contents import HTMLContent
from blacksheep.messages import Request, Response
from blacksheep.server.asgi import get_request_url
from blacksheep.server.resources import get_resource_file_content


def _load_error_page_template() -> str:
    error_css = get_resource_file_content("error.css")
    error_template = get_resource_file_content("error.html")
    assert "/*STYLES*/" in error_template

    # since later it is used in format_map...
    error_css = error_css.replace("{", "{{").replace("}", "}}")
    return error_template.replace("/*STYLES*/", error_css)


class ServerErrorDetailsHandler:
    """
    This class is responsible of producing a detailed response when the Application is
    configured to show error details to the client, and an unhandled exception happens.
    """

    def __init__(self) -> None:
        self._error_page_template = _load_error_page_template()

    def produce_response(self, request: Request, exc: Exception) -> Response:
        tb = traceback.format_exception(exc.__class__, exc, exc.__traceback__)
        info = ""
        for item in tb:
            info += f"<li><pre>{html.escape(item)}</pre></li>"

        content = HTMLContent(
            self._error_page_template.format_map(
                {
                    "info": info,
                    "exctype": exc.__class__.__name__,
                    "excmessage": str(exc),
                    "method": request.method,
                    "path": request.url.value.decode(),
                    "full_url": get_request_url(request),
                }
            )
        )

        return Response(500, content=content)
