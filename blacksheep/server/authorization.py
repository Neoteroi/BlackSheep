from typing import Optional, Sequence

from guardpost.asynchronous.authorization import (
    AsyncRequirement,
    AuthorizationStrategy,
    Policy,
)
from guardpost.synchronous.authorization import Requirement, UnauthorizedError

from blacksheep import Response, TextContent

__all__ = (
    "auth",
    "AuthorizationStrategy",
    "AuthorizationWithoutAuthenticationError",
    "allow_anonymous",
    "get_authorization_middleware",
    "Requirement",
    "AsyncRequirement",
    "handle_unauthorized",
    "Policy",
)


def auth(
    policy: Optional[str] = None,
    *,
    authentication_schemes: Optional[Sequence[str]] = None
):
    """
    Configures authorization for a decorated request handler,
    optionally with a policy.
    If no policy is specified, the default policy of the configured
    AuthorizationStrategy is used.

    :param policy: optional, name of the policy to use for authorization.
    :param authentication_schemes: optional, authentication schemes to use
    for this handler. If not specified, all configured authentication handlers
    are used.
    """

    def decorator(f):
        f.auth = True
        f.auth_policy = policy
        f.auth_schemes = authentication_schemes
        return f

    return decorator


def allow_anonymous():
    """
    Configures a decorated request handler, to make it usable for all users:
    anonymous and authenticated users.
    """

    def decorator(f):
        f.allow_anonymous = True
        return f

    return decorator


def get_authorization_middleware(strategy: AuthorizationStrategy):
    async def authorization_middleware(request, handler):
        identity = request.identity

        if hasattr(handler, "allow_anonymous"):
            return await handler(request)

        if hasattr(handler, "auth"):
            # function decorated by auth;
            await strategy.authorize(handler.auth_policy, identity)
        else:
            # function not decorated by auth; use the default policy
            await strategy.authorize(None, identity)

        return await handler(request)

    return authorization_middleware


class AuthorizationWithoutAuthenticationError(RuntimeError):
    def __init__(self):
        super().__init__(
            "Cannot use an authorization strategy without an authentication "
            "strategy. Use `use_authentication` method to configure it."
        )


def _get_www_authenticated_header_value_from_generic_unauthorized_error(
    error: UnauthorizedError,
):
    parts = [error.scheme]
    if error.error:
        parts.append(', error="{}"')


def get_www_authenticated_header_from_generic_unauthorized_error(error):
    if not error.scheme:
        return None

    return b"WWW-Authenticate", error.scheme.decode()


async def handle_unauthorized(app, request, http_exception: UnauthorizedError):
    www_authenticate = get_www_authenticated_header_from_generic_unauthorized_error(
        http_exception
    )
    return Response(
        401,
        [www_authenticate] if www_authenticate else None,
        content=TextContent("Unauthorized"),
    )
