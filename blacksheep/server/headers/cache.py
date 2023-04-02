"""
This module provides functions to configure Cache-Control headers for responses and
request handlers, including a decorator and a middleware.
"""

import inspect
from functools import wraps
from typing import Optional

from blacksheep import Request, Response
from blacksheep.server.normalization import ensure_response


def write_cache_control_response_header(
    *,
    max_age: Optional[int] = None,
    shared_max_age: Optional[int] = None,
    no_cache: Optional[bool] = None,
    no_store: Optional[bool] = None,
    must_revalidate: Optional[bool] = None,
    proxy_revalidate: Optional[bool] = None,
    private: Optional[bool] = None,
    public: Optional[bool] = None,
    must_understand: Optional[bool] = None,
    no_transform: Optional[bool] = None,
    immutable: Optional[bool] = None,
    stale_while_revalidate: Optional[int] = None,
    stale_if_error: Optional[int] = None,
) -> bytes:
    """
    Writes the value of a Cache-Control response header, applying the given directives.

    Parameters
    ----------
    max_age: int | None
        max age in seconds
    shared_max_age: int | None
        optional shared max age in seconds
    no_cache: bool | None
        enables no-cache
    no_store: bool | None
        enables no-store
    must_revalidate: bool | None
        enables must-revalidate
    proxy_revalidate: bool | None
        enables proxy-revalidate
    private: bool | None
        enables private
    public: bool | None
        enables public
    must_understand: bool | None
        enables must-understand
    no_transform: bool | None
        enables no-transform
    immutable: bool | None
        enables immutable
    stale_while_revalidate: int | None
        enables stale-while-revalidate, in seconds
    stale_if_error: int | None
        enables stale-if-error, in seconds

    For detailed information on Cache-Control header, please refer to:
    https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Cache-Control
    """
    value = bytearray()

    if private and public:
        raise ValueError("A cache cannot be private and public at the same time.")

    def extend(part: bytes):
        if len(value):
            value.extend(b", ")
        value.extend(part)

    if private:
        extend(b"private")

    if public:
        extend(b"public")

    if max_age is not None:
        extend(f"max-age={max_age}".encode("ascii"))

    if shared_max_age is not None:
        extend(f"s-maxage={shared_max_age}".encode("ascii"))

    if no_cache:
        extend(b"no-cache")

    if must_revalidate:
        extend(b"must-revalidate")

    if proxy_revalidate:
        extend(b"proxy-revalidate")

    if no_store:
        extend(b"no-store")

    if must_understand:
        extend(b"must-understand")

    if no_transform:
        extend(b"no-transform")

    if immutable:
        extend(b"immutable")

    if stale_while_revalidate is not None:
        extend(f"stale-while-revalidate={stale_while_revalidate}".encode("ascii"))

    if stale_if_error is not None:
        extend(f"stale-if-error={stale_if_error}".encode("ascii"))

    return bytes(value)


class CacheControlHeaderValue:
    """
    Class used to represent a Cache-Control response header value.

    Parameters
    ----------
    max_age: int | None
        max age in seconds
    shared_max_age: int | None
        optional shared max age in seconds
    no_cache: bool | None
        enables no-cache
    no_store: bool | None
        enables no-store
    must_revalidate: bool | None
        enables must-revalidate
    proxy_revalidate: bool | None
        enables proxy-revalidate
    private: bool | None
        enables private
    public: bool | None
        enables public
    must_understand: bool | None
        enables must-understand
    no_transform: bool | None
        enables no-transform
    immutable: bool | None
        enables immutable
    stale_while_revalidate: int | None
        enables stale-while-revalidate, in seconds
    stale_if_error: int | None
        enables stale-if-error, in seconds

    For detailed information on Cache-Control header, please refer to:
    https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Cache-Control
    """

    def __init__(
        self,
        *,
        max_age: Optional[int] = None,
        shared_max_age: Optional[int] = None,
        no_cache: Optional[bool] = None,
        no_store: Optional[bool] = None,
        must_revalidate: Optional[bool] = None,
        proxy_revalidate: Optional[bool] = None,
        private: Optional[bool] = None,
        public: Optional[bool] = None,
        must_understand: Optional[bool] = None,
        no_transform: Optional[bool] = None,
        immutable: Optional[bool] = None,
        stale_while_revalidate: Optional[int] = None,
        stale_if_error: Optional[int] = None,
    ) -> None:
        self.value: bytes = write_cache_control_response_header(
            max_age=max_age,
            shared_max_age=shared_max_age,
            no_cache=no_cache,
            no_store=no_store,
            must_revalidate=must_revalidate,
            proxy_revalidate=proxy_revalidate,
            private=private,
            public=public,
            must_understand=must_understand,
            no_transform=no_transform,
            immutable=immutable,
            stale_while_revalidate=stale_while_revalidate,
            stale_if_error=stale_if_error,
        )


def cache_control(
    max_age: Optional[int] = None,
    shared_max_age: Optional[int] = None,
    no_cache: Optional[bool] = None,
    no_store: Optional[bool] = None,
    must_revalidate: Optional[bool] = None,
    proxy_revalidate: Optional[bool] = None,
    private: Optional[bool] = None,
    public: Optional[bool] = None,
    must_understand: Optional[bool] = None,
    no_transform: Optional[bool] = None,
    immutable: Optional[bool] = None,
    stale_while_revalidate: Optional[int] = None,
    stale_if_error: Optional[int] = None,
):
    """
    Cache control decorator, applying a Cache-Control header to all successful
    responses.

    Parameters
    ----------
    max_age: int | None
        max age in seconds
    shared_max_age: int | None
        optional shared max age in seconds
    no_cache: bool | None
        enables no-cache
    no_store: bool | None
        enables no-store
    must_revalidate: bool | None
        enables must-revalidate
    proxy_revalidate: bool | None
        enables proxy-revalidate
    private: bool | None
        enables private
    public: bool | None
        enables public
    must_understand: bool | None
        enables must-understand
    no_transform: bool | None
        enables no-transform
    immutable: bool | None
        enables immutable
    stale_while_revalidate: int | None
        enables stale-while-revalidate, in seconds
    stale_if_error: int | None
        enables stale-if-error, in seconds

    For detailed information on Cache-Control header, please refer to:
    https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Cache-Control
    """
    header_value: bytes = write_cache_control_response_header(
        max_age=max_age,
        shared_max_age=shared_max_age,
        no_cache=no_cache,
        no_store=no_store,
        must_revalidate=must_revalidate,
        proxy_revalidate=proxy_revalidate,
        private=private,
        public=public,
        must_understand=must_understand,
        no_transform=no_transform,
        immutable=immutable,
        stale_while_revalidate=stale_while_revalidate,
        stale_if_error=stale_if_error,
    )

    def decorator(next_handler):
        if inspect.iscoroutinefunction(next_handler):

            @wraps(next_handler)
            async def async_wrapped(*args, **kwargs):
                response = ensure_response(await next_handler(*args, **kwargs))
                response.add_header(b"cache-control", header_value)
                return response

            return async_wrapped
        else:

            @wraps(next_handler)
            def wrapped(*args, **kwargs):
                response = ensure_response(next_handler(*args, **kwargs))
                response.add_header(b"cache-control", header_value)
                return response

            return wrapped

    return decorator


class CacheControlMiddleware:
    """
    The Cache-Control middleware lets configure a Cache-Control header globally, for
    all GET requests resulting in responses with status code 200 that don't have a
    cache-control header defined.

    Parameters
    ----------
    max_age: int | None
        max age in seconds
    shared_max_age: int | None
        optional shared max age in seconds
    no_cache: bool | None
        enables no-cache
    no_store: bool | None
        enables no-store
    must_revalidate: bool | None
        enables must-revalidate
    proxy_revalidate: bool | None
        enables proxy-revalidate
    private: bool | None
        enables private
    public: bool | None
        enables public
    must_understand: bool | None
        enables must-understand
    no_transform: bool | None
        enables no-transform
    immutable: bool | None
        enables immutable
    stale_while_revalidate: int | None
        enables stale-while-revalidate, in seconds
    stale_if_error: int | None
        enables stale-if-error, in seconds
    """

    def __init__(
        self,
        *,
        max_age: Optional[int] = None,
        shared_max_age: Optional[int] = None,
        no_cache: Optional[bool] = None,
        no_store: Optional[bool] = None,
        must_revalidate: Optional[bool] = None,
        proxy_revalidate: Optional[bool] = None,
        private: Optional[bool] = None,
        public: Optional[bool] = None,
        must_understand: Optional[bool] = None,
        no_transform: Optional[bool] = None,
        immutable: Optional[bool] = None,
        stale_while_revalidate: Optional[int] = None,
        stale_if_error: Optional[int] = None,
    ) -> None:
        self._header_value: bytes = write_cache_control_response_header(
            max_age=max_age,
            shared_max_age=shared_max_age,
            no_cache=no_cache,
            no_store=no_store,
            must_revalidate=must_revalidate,
            proxy_revalidate=proxy_revalidate,
            private=private,
            public=public,
            must_understand=must_understand,
            no_transform=no_transform,
            immutable=immutable,
            stale_while_revalidate=stale_while_revalidate,
            stale_if_error=stale_if_error,
        )

    def should_handle(self, request: Request, response: Response) -> bool:
        """
        Returns a value indicating whether the Cache-Control header should be set in
        the given response object, that was created for the given request.
        """
        return request.method == "GET" and response.status == 200

    async def __call__(self, request, handler):
        response = await handler(request)
        if (
            self.should_handle(request, response)
            and not response.headers[b"cache-control"]
        ):
            response.add_header(b"cache-control", self._header_value)

        return response
