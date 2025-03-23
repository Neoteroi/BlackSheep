from typing import Awaitable, Callable, Optional

from blacksheep import Response
from blacksheep.server.responses import moved_permanently


def default_trailing_slash_exclude(path: str) -> bool:
    return "/api/" in path


def get_trailing_slash_middleware(
    exclude: Optional[Callable[[str], bool]] = None,
) -> Callable[..., Awaitable[Response]]:
    """
    Returns a middleware that redirects requests that do not end with a trailing slash
    to the same URL with a trailing slash, with a HTTP 301 Moved Permanently response.
    This is useful for endpoints that serve HTML documents, to ensure that relative
    URLs in the response body are correctly resolved.
    To filter certain requests from being redirected, pass a callable that returns
    True if the request should be excluded from redirection, by path.
    The default exclude function excludes all requests whose path contains "/api/".
    """
    if exclude is None:
        exclude = default_trailing_slash_exclude

    async def trailing_slash_middleware(request, handler):
        path = request.path

        if exclude and exclude(path):
            return await handler(request)

        if not path.endswith("/") and "." not in path.split("/")[-1]:
            return moved_permanently(f"/{path.strip('/')}/")
        return await handler(request)

    return trailing_slash_middleware
