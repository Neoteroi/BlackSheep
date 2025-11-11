from typing import TYPE_CHECKING, Any, Awaitable, Callable, Sequence

from guardpost import ForbiddenError, RateLimitExceededError
from guardpost.authorization import (
    AuthorizationStrategy,
    Policy,
    Requirement,
    UnauthorizedError,
)
from guardpost.common import AuthenticatedRequirement

from blacksheep import Request, Response, TextContent
from blacksheep.middlewares import MiddlewareCategory
from blacksheep.server.authentication import (
    AuthenticateChallenge,
    handle_authentication_challenge,
    handle_rate_limited_auth,
)

if TYPE_CHECKING:
    from blacksheep.server.application import Application


__all__ = (
    "auth",
    "AuthorizationStrategy",
    "AuthorizationWithoutAuthenticationError",
    "allow_anonymous",
    "get_authorization_middleware",
    "Requirement",
    "handle_unauthorized",
    "Policy",
    "use_authorization",
)


def auth(
    policy: str | None = "authenticated",
    *,
    roles: Sequence[str] | None = None,
    authentication_schemes: Sequence[str] | None = None,
) -> Callable[..., Any]:
    """
    Configures authorization for a decorated request handler, optionally with a policy.
    If no policy is specified, the default policy to require authenticated users is
    used.

    :param policy: optional, name of the policy to use for authorization.
    :param roles: optional set of sufficient roles (any one is enough). If both a
        policy and roles are specified, both are checked.
    :param authentication_schemes: optional, authentication schemes to use
        for this handler. If not specified, all configured authentication handlers
        are used.
    """

    def decorator(f):
        f.auth = True
        f.auth_policy = policy
        f.auth_roles = list(roles) if roles else None
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


def get_authorization_middleware(
    strategy: AuthorizationStrategy,
) -> Callable[[Request, Callable[..., Any]], Awaitable[Response]]:
    async def authorization_middleware(request, handler):
        user = request.user

        if getattr(handler, "allow_anonymous", False) is True:
            return await handler(request)

        roles = getattr(handler, "auth_roles", None)
        if hasattr(handler, "auth"):
            # function decorated by auth;
            await strategy.authorize(handler.auth_policy, user, request, roles)
        else:
            # function not decorated by auth; use the default policy.
            # this is necessary to support configuring authorization rules globally
            # without configuring every single request handler
            await strategy.authorize(None, user, request, roles)

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
) -> tuple[bytes, bytes | None]:
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


def use_authorization(
    app: "Application", strategy: AuthorizationStrategy | None = None
) -> AuthorizationStrategy:
    if app.started:
        raise RuntimeError(
            "The application is already running, configure authorization "
            "before starting the application"
        )

    if not app._authentication_strategy:
        raise AuthorizationWithoutAuthenticationError()

    if app._authorization_strategy:
        return app._authorization_strategy

    if not strategy:
        strategy = AuthorizationStrategy(container=app.services)

    if strategy.default_policy is None:
        # by default, a default policy is configured with no requirements,
        # meaning that request handlers allow anonymous users by default, unless
        # they are decorated with @auth()
        strategy.default_policy = Policy("default")
        strategy.add(Policy("authenticated", AuthenticatedRequirement()))

    app._authorization_strategy = strategy
    app.exceptions_handlers.update(
        {  # type: ignore
            AuthenticateChallenge: handle_authentication_challenge,
            UnauthorizedError: handle_unauthorized,
            ForbiddenError: handle_forbidden,
            RateLimitExceededError: handle_rate_limited_auth,
        }
    )

    app.middlewares.append(
        get_authorization_middleware(strategy), MiddlewareCategory.AUTHZ, 0
    )
    return strategy
