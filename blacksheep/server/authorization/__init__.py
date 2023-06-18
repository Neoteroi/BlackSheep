from typing import Any, Awaitable, Callable, Optional, Sequence, Tuple

from guardpost.asynchronous.authorization import AsyncRequirement, AuthorizationStrategy
from guardpost.authorization import Policy, UnauthorizedError
from guardpost.synchronous.authorization import Requirement

from blacksheep import Request, Response, TextContent

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
    policy: Optional[str] = "authenticated",
    *,
    authentication_schemes: Optional[Sequence[str]] = None
) -> Callable[..., Any]:
    """
    Configures authorization for a decorated request handler, optionally with a policy.
    If no policy is specified, the default policy to require authenticated users is
    used.

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


def allow_anonymous(value: bool = True) -> Callable[..., Any]:
    """
    If used without arguments, configures a decorated request handler to make it
    usable for all users: anonymous and authenticated users.

    Otherwise, enables anonymous access according to the given flag value.
    """

    def decorator(f):
        f.allow_anonymous = value
        return f

    return decorator


class ForbiddenError(UnauthorizedError):
    """
    Specific kind of authorization error, used to indicate that the application
    understands a request but refuses to authorize it. In other words, the user context
    is valid but the user is not authorized to perform a certain operation.
    """


def get_authorization_middleware(
    strategy: AuthorizationStrategy,
) -> Callable[[Request, Callable[..., Any]], Awaitable[Response]]:
    async def authorization_middleware(request, handler):
        identity = request.identity

        if getattr(handler, "allow_anonymous", False) is True:
            return await handler(request)

        try:
            if hasattr(handler, "auth"):
                # function decorated by auth;
                await strategy.authorize(handler.auth_policy, identity)
            else:
                # function not decorated by auth; use the default policy.
                # this is necessary to support configuring authorization rules globally
                # without configuring every single request handler
                await strategy.authorize(None, identity)
        except UnauthorizedError as unauthorized_error:
            if identity and identity.is_authenticated():
                raise ForbiddenError(
                    unauthorized_error.failed,
                    unauthorized_error.failed_requirements,
                    unauthorized_error.scheme,
                    unauthorized_error.error,
                    unauthorized_error.error_description,
                )
            raise

        return await handler(request)

    return authorization_middleware


class AuthorizationWithoutAuthenticationError(RuntimeError):
    def __init__(self):
        super().__init__(
            "Cannot use an authorization strategy without an authentication "
            "strategy. Use `use_authentication` method to configure it."
        )


def get_www_authenticated_header_from_generic_unauthorized_error(
    error: UnauthorizedError,
) -> Optional[Tuple[bytes, bytes]]:
    if not error.scheme:
        return None

    return b"WWW-Authenticate", error.scheme.encode()


async def handle_unauthorized(
    app: Any, request: Request, http_exception: UnauthorizedError
) -> Response:
    www_authenticate = get_www_authenticated_header_from_generic_unauthorized_error(
        http_exception
    )
    return Response(
        401,
        [www_authenticate] if www_authenticate else None,
        content=TextContent("Unauthorized"),
    )


async def handle_forbidden(
    app: Any, request: Request, http_exception: UnauthorizedError
):
    return Response(
        403,
        None,
        content=TextContent("Forbidden"),
    )
