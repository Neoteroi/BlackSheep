from typing import Awaitable, Callable

from rodi import ActivationScope, set_scope

from blacksheep.messages import Request, Response


async def di_scope_middleware(
    request: Request, handler: Callable[[Request], Awaitable[Response]]
) -> Response:
    """
    This middleware ensures that a single scope is used for Dependency Injection,
    across request handlers and other parts of the application that require activating
    services (e.g. authentication handlers).

    This middleware is not necessary in most cases, as having a scope for the request
    handler is generally sufficient for most scenarios.
    """
    with ActivationScope() as scope:
        scope.scoped_services[Request] = request  # type: ignore
        scope.scoped_services["__request__"] = request  # type: ignore
        set_scope(request, scope)
        return await handler(request)
