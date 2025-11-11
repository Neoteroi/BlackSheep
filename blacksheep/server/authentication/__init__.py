from typing import TYPE_CHECKING

from guardpost import (
    AuthenticationHandler,
    AuthenticationStrategy,
    AuthorizationError,
    RateLimiter,
    RateLimitExceededError,
)

from blacksheep import Response, TextContent
from blacksheep.middlewares import MiddlewareCategory

if TYPE_CHECKING:
    from blacksheep.server.application import Application

__all__ = (
    "AuthenticationStrategy",
    "AuthenticationHandler",
    "AuthenticateChallenge",
    "get_authentication_middleware",
    "handle_authentication_challenge",
)


def get_authentication_middleware(strategy: AuthenticationStrategy):
    async def authentication_middleware(request, handler):
        await strategy.authenticate(request, getattr(handler, "auth_schemes", None))
        return await handler(request)

    return authentication_middleware


class AuthenticateChallenge(AuthorizationError):
    header_name = b"WWW-Authenticate"

    def __init__(
        self, scheme: str, realm: str | None, parameters: dict[str, str | None]
    ):
        self.scheme = scheme
        self.realm = realm
        self.parameters = parameters

    def _get_header_value(self) -> bytes:
        if not self.realm and not self.parameters:
            return self.scheme.encode()

        parts = bytearray(self.scheme.encode())
        if self.realm:
            parts.extend(f' realm="{self.realm}"'.encode())

        if self.parameters:
            parts.extend(b", ")
            parts.extend(
                b", ".join(
                    [
                        f'{key}="{value}"'.encode()
                        for key, value in self.parameters.items()
                    ]
                )
            )
        return bytes(parts)

    def get_header(self) -> tuple[bytes, bytes]:
        return self.header_name, self._get_header_value()


async def handle_authentication_challenge(
    app, request, exception: AuthenticateChallenge
):
    return Response(401, [exception.get_header()], content=TextContent("Unauthorized"))


async def handle_rate_limited_auth(app, request, exception: RateLimitExceededError):
    return Response(
        429,
        [],
        content=TextContent(
            "The request is blocked because of "
            "too many authentication attempts. Try again later."
        ),
    )


def use_authentication(
    app: "Application",
    strategy: AuthenticationStrategy | None = None,
    rate_limiter: RateLimiter | None = None,
) -> AuthenticationStrategy:
    if app.started:
        raise RuntimeError(
            "The application is already running, configure authentication "
            "before starting the application"
        )

    if app._authentication_strategy:
        return app._authentication_strategy

    if not strategy:
        strategy = AuthenticationStrategy(
            container=app.services,
            rate_limiter=rate_limiter,
            logger=app.logger,
        )

    app._authentication_strategy = strategy

    app.middlewares.append(
        get_authentication_middleware(strategy),
        MiddlewareCategory.AUTH,
    )
    return strategy
