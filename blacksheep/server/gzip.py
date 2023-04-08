import gzip

from blacksheep.server.normalization import ensure_response
from blacksheep import Request, Response, Content
from blacksheep.server.application import Application

from typing import Callable, Awaitable, Optional


class GzipMiddleware:
    """
    The gzip compression middleware for all requests with a body larger than
    the specified minimum size and with the "gzip" encoding in the "Accept-Encoding"
    header.

    Parameters
    ----------
    min_size: int
        The minimum size of the response body to compress.
    comp_level: int
        The compression level to use.
    """

    def __init__(self, min_size: int = 500, comp_level: int = 5):
        self.min_size = min_size
        self.comp_level = comp_level

    def should_handle(self, request: Request, response: Response) -> bool:
        """
        Returns True if the response should be compressed.
        """
        return (
            b"gzip" in (request.headers.get_single(b"accept-encoding") or "")
            and response is not None
            and response.content is not None
            and response.content.body is not None
            and len(response.content.body) > self.min_size
        )

    async def __call__(
        self, request: Request, handler: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = ensure_response(await handler(request))
        if not self.should_handle(request, response):
            return response

        response.with_content(
            Content(
                content_type=response.content.type,
                data=gzip.compress(response.content.body, self.comp_level),
            )
        )
        response.add_header(b"content-encoding", b"gzip")
        response.add_header(
            b"content-length", str(len(response.content.body)).encode("ascii")
        )
        return response


def use_gzip_commpression(
    app: Application,
    handler: Optional[GzipMiddleware] = None,
):
    """
    Configures the application to use gzip compression for all responses with gzip
    in accept-encoding header.
    """
    if handler is None:
        handler = GzipMiddleware()

    app.middlewares.append(handler)

    return handler
