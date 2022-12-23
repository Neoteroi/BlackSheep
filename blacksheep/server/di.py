from typing import Awaitable, Callable

from rodi import ActivationScope, set_scope

from blacksheep.messages import Request, Response


async def di_scope_middleware(
    request: Request, handler: Callable[[Request], Awaitable[Response]]
) -> Response:
    with ActivationScope() as scope:
        scope.scoped_services["__request__"] = request  # type: ignore
        set_scope(request, scope)
        request.services_context = scope  # type: ignore
        return await handler(request)
