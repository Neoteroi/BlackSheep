import asyncio
import gzip
from concurrent.futures import Executor
from typing import Awaitable, Callable, Iterable

from blacksheep import Content, Request, Response
from blacksheep.server.application import Application
from blacksheep.server.headers.cache import add_vary_header
from blacksheep.server.normalization import ensure_response


class GzipMiddleware:
    """
    The gzip compression middleware for all requests with a body larger than
    the specified minimum size and with the "gzip" encoding in the "Accept-Encoding"
    header. The middleware runs compression asynchronously in a separate executor.

    Parameters
    ----------
    min_size: int
        The minimum size of the response body to compress.
    comp_level: int
        The compression level to use.
    handled_types: Iterable[bytes | None]
        The list of content types to compress.
    executor: Executor
        The executor instance to use for compression. If not specified, a
        default executor is used. If you specify an executor, you are responsible
        for shutting it down.
    """

    handled_types: list[bytes] = [
        b"json",
        b"xml",
        b"yaml",
        b"html",
        b"text/plain",
        b"application/javascript",
        b"text/css",
        b"text/csv",
    ]

    def __init__(
        self,
        min_size: int = 500,
        comp_level: int = 5,
        handled_types: Iterable[bytes] | None = None,
        executor: Executor | None = None,
    ):
        self.min_size = min_size
        self.comp_level = comp_level
        self._executor = executor

        if handled_types is not None:
            self.handled_types = self._normalize_types(handled_types)

    def _normalize_types(self, types: Iterable[bytes]) -> list[bytes]:
        """
        Normalizes the types to bytes.
        """
        normalized_types = []
        for _type in types:
            if isinstance(_type, str):
                normalized_types.append(_type.encode("ascii"))
            else:
                normalized_types.append(_type)
        return normalized_types

    def is_handled_response_content(self, response: Response | None) -> bool:
        """
        Returns True if the response content is of a type and size that is
        eligible for compression, regardless of the request.
        """
        if response is None or response.content is None:
            return False

        def _is_handled_type(content_type) -> bool:
            content_type = content_type.lower()
            return any(_type in content_type for _type in self.handled_types)

        body_pass: bool = (
            response.content.body is not None
            and len(response.content.body) > self.min_size
        )

        content_type_pass: bool = response.content.type is not None and (
            _is_handled_type(response.content.type)
        )

        return body_pass and content_type_pass

    def should_handle(self, request: Request, response: Response) -> bool:
        """
        Returns True if the response should be compressed.
        """

        def is_handled_encoding() -> bool:
            return b"gzip" in (request.get_first_header(b"accept-encoding") or b"")

        return is_handled_encoding() and self.is_handled_response_content(response)

    async def __call__(
        self, request: Request, handler: Callable[[Request], Awaitable[Response]]
    ) -> Response | None:
        response = ensure_response(await handler(request))

        if response is None or response.content is None:
            return response

        if self.is_handled_response_content(response):
            # The response depends on Accept-Encoding even when it is not compressed
            # for this request, so caches must not serve it to other clients.
            add_vary_header(response, [b"Accept-Encoding"])

        if not self.should_handle(request, response):
            return response

        loop = asyncio.get_running_loop()
        compressed_body = await loop.run_in_executor(
            self._executor,
            gzip.compress,
            response.content.body,
            self.comp_level,
        )

        response.with_content(
            Content(
                content_type=response.content.type,
                data=compressed_body,
            )
        )
        response.add_header(b"content-encoding", b"gzip")
        return response


def use_gzip_compression(
    app: Application,
    handler: GzipMiddleware | None = None,
) -> GzipMiddleware:
    """
    Configures the application to use gzip compression for all responses with gzip
    in accept-encoding header.
    """
    if handler is None:
        handler = GzipMiddleware()

    app.middlewares.append(handler)  # type: ignore

    return handler
