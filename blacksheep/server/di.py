from typing import TYPE_CHECKING, Awaitable, Callable

from rodi import ActivationScope, Container

from blacksheep.messages import Request, Response

if TYPE_CHECKING:
    from blacksheep.server.application import Application


async def di_scope_middleware(
    request: Request, handler: Callable[[Request], Awaitable[Response]]
) -> Response:
    """
    This middleware ensures that a single scope is used for Dependency Injection,
    across request handlers and other parts of the application that require activating
    services (e.g. authentication handlers).

    This middleware is not necessary in most cases, but in some circumstances it can be
    necessary.
    """
    with ActivationScope() as scope:
        scope.scoped_services[Request] = request  # type: ignore
        scope.scoped_services["__request__"] = request  # type: ignore
        request._di_scope = scope  # type: ignore
        return await handler(request)


def request_factory(context) -> Request:
    # The following scoped service is set in a middleware, since in fact we are
    # mixing runtime data with composition data.
    return context.scoped_services[Request]


def register_http_context(app: "Application"):
    """
    Makes the `Request` object accessible through dependency injection for the
    application container.
    This method requires using `rodi` as solution for dependency injection, since
    other implementations might not support scoped services and factories using the
    activation scope.

    This is not a recommended pattern, but it might be desired in certain situations.
    """
    assert isinstance(app.services, Container), "This method requires rodi."

    if di_scope_middleware not in app.middlewares:

        @app.on_middlewares_configuration
        def enable_request_accessor(_):
            app.middlewares.insert(0, di_scope_middleware)

    app.services.add_scoped_by_factory(request_factory)
