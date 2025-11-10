import typing

from blacksheep.messages import Request
from blacksheep.middlewares import MiddlewareCategory
from blacksheep.server.security.hsts import HSTSMiddleware

if typing.TYPE_CHECKING:
    from blacksheep.server.application import Application


class HTTPSchemeMiddleware:
    """
    Middleware that forces request.scheme based on configuration.
    Useful when the application is deployed behind proxies that do TLS termination, and
    the application needs to generate proper redirect URLs to itself with the right
    scheme.
    This middleware is applied automatically when the env variables APP_HTTP_SCHEME or
    APP_FORCE_HTTPS are set.
    """

    def __init__(self, scheme: str):
        if scheme not in {"http", "https"}:
            raise TypeError("Invalid scheme, expected http | https")
        self.scheme = scheme

    async def __call__(self, request: Request, handler):
        request.scheme = self.scheme
        return await handler(request)


def configure_scheme_middleware(app: "Application"):
    """
    Automatically configures request scheme handling based on environment variables.

    This function is useful when the application runs behind reverse proxies or load
    balancers that perform TLS termination, ensuring the application generates URLs
    with the correct scheme.

    Environment Variables:
        APP_FORCE_HTTPS: When set to a truthy value ("1", "true", etc.), forces all
            requests to use https scheme and adds HSTS headers for security.
        APP_HTTP_SCHEME: When set to "http" or "https", forces all requests to use
            the specified scheme without adding HSTS headers.

    Behavior:
        - If APP_FORCE_HTTPS is set: Uses https + enables HSTS middleware
        - If APP_HTTP_SCHEME is set: Uses the specified scheme without HSTS
        - If neither is set: No middleware is applied (uses actual request scheme)

    Note: APP_FORCE_HTTPS takes precedence over APP_HTTP_SCHEME if both are set.
    """
    if app.env_settings.force_https:
        # Apply middleware that configures request.scheme to match env settings
        app.middlewares.append(
            HTTPSchemeMiddleware("https"), MiddlewareCategory.INIT, -100
        )

        # Apply HTTP Strict Transport Security header by default
        app.middlewares.append(HSTSMiddleware(), MiddlewareCategory.MESSAGE)
    elif app.env_settings.http_scheme:
        app.middlewares.append(
            HTTPSchemeMiddleware(app.env_settings.http_scheme),
            MiddlewareCategory.INIT,
            -100,
        )
