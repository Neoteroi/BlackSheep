from typing import Awaitable, Callable

from rodi import GetServiceContext

from blacksheep.messages import Request, Response


async def dependency_injection_middleware(
    request: Request, handler: Callable[[Request], Awaitable[Response]]
) -> Response:
    with GetServiceContext() as context:
        request.services_context = context  # type: ignore
        return await handler(request)
