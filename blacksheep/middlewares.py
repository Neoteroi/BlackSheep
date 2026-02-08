"""
This module contains high-level middlewares functions that can be used both by client
and server code.
"""

from enum import Enum
from typing import Any, Awaitable, Callable, Iterable, overload

from blacksheep.messages import Response
from blacksheep.normalization import copy_special_attributes


def middleware_partial(handler, next_handler):
    async def middleware_wrapper(request):
        return await handler(request, next_handler)

    return middleware_wrapper


def get_middlewares_chain(middlewares, handler):
    fn = handler
    for middleware in reversed(middlewares):
        if not middleware:
            continue
        wrapper_fn = middleware_partial(middleware, fn)
        setattr(wrapper_fn, "root_fn", handler)
        copy_special_attributes(fn, wrapper_fn)
        fn = wrapper_fn
    return fn


class MiddlewareCategory(Enum):
    INIT = 10  # CORS, security headers, configuration that must happen early
    SESSION = 20  # Session handling
    AUTH = 30  # Authentication
    AUTHZ = 40  # Authorization
    BUSINESS = 50  # User business logic middlewares
    MESSAGE = 60  # Request/Response modification (default headers, etc.)


class CategorizedMiddleware:
    def __init__(
        self,
        middleware,
        category: MiddlewareCategory = MiddlewareCategory.BUSINESS,
        priority: int = 0,
    ):
        self.middleware = middleware
        self.category = category
        self.priority = priority


class MiddlewareList:
    """
    A list-like container for middlewares that supports categorized and
    prioritized insertion.
    """

    def __init__(self):
        self._middlewares: list[CategorizedMiddleware] = []
        self._is_sorted = True
        self._configured = False

    @overload
    def append(self, middleware: Callable[..., Awaitable[Response]]) -> None: ...

    @overload
    def append(
        self,
        middleware: Callable[..., Awaitable[Response]],
        category: MiddlewareCategory,
        priority: int = 0,
    ) -> None: ...

    def append(
        self,
        middleware: Callable[..., Awaitable[Response]],
        category: MiddlewareCategory = MiddlewareCategory.BUSINESS,
        priority: int = 0,
    ) -> None:
        """
        Add a middleware to the application.

        Args:
            middleware: The middleware function
            category: Where in the pipeline to place this middleware (default: BUSINESS)
            priority: Order within the category (lower = earlier, default: 0)
        """
        if self._configured:
            raise RuntimeError("Cannot add middlewares after configuration is complete")

        self._middlewares.append(CategorizedMiddleware(middleware, category, priority))
        self._is_sorted = False

    def insert(
        self, index: int, middleware: Callable[..., Awaitable[Response]]
    ) -> None:
        """Insert middleware at specific index (legacy support)"""
        if self._configured:
            raise RuntimeError("Cannot add middlewares after configuration is complete")

        # Convert to categorized middleware for consistency
        # This method defaults to MiddlewareCategory.INIT for backward compatibility,
        # as in the past insert was the only way to insert middlewares early in the
        # chain.
        self._middlewares.insert(
            index, CategorizedMiddleware(middleware, MiddlewareCategory.INIT, -1)
        )
        self._is_sorted = False

    def extend(self, middlewares) -> None:
        """Extend with multiple middlewares"""
        for middleware in middlewares:
            self.append(middleware)

    def clear(self) -> None:
        """Clear all middlewares"""
        self._middlewares.clear()
        self._is_sorted = True

    def _ensure_sorted(self) -> None:
        """Sort middlewares by category and priority if needed"""
        if not self._is_sorted:
            self._middlewares.sort(key=lambda m: (m.category.value, m.priority))
            self._is_sorted = True

    def _mark_configured(self) -> None:
        """Mark as configured to prevent further modifications"""
        self._configured = True
        self._ensure_sorted()

    def items(self) -> Iterable[CategorizedMiddleware]:
        yield from self._middlewares

    def __iter__(self):
        self._ensure_sorted()
        return iter(m.middleware for m in self._middlewares)

    def __len__(self) -> int:
        return len(self._middlewares)

    def __bool__(self) -> bool:
        return len(self._middlewares) > 0

    def __getitem__(self, index):
        self._ensure_sorted()
        return self._middlewares[index].middleware

    def to_list(self) -> list[Callable[..., Awaitable[Response]]]:
        """Get the sorted list of middleware functions"""
        self._ensure_sorted()
        return [m.middleware for m in self._middlewares]


class ASGIMiddlewareWrapper:
    """
    Wrapper to make standard ASGI middlewares compatible with BlackSheep.
    
    This adapter allows using ASGI middlewares (such as SentryAsgiMiddleware,
    OpenTelemetry middlewares, etc.) with BlackSheep applications by wrapping
    the application at the ASGI protocol level.
    
    ASGI middlewares operate at the protocol level with raw scope/receive/send
    callables, while BlackSheep's internal middlewares work with typed Request
    and Response objects. This wrapper bridges that gap by intercepting at the
    ASGI level before BlackSheep's request handling.
    
    Usage:
        ```python
        from blacksheep import Application
        from blacksheep.middlewares import use_asgi_middleware
        from sentry_sdk.integrations.asgi import SentryAsgiMiddleware
        
        app = Application()
        
        # Configure routes...
        
        # Wrap with ASGI middleware
        app = use_asgi_middleware(app, SentryAsgiMiddleware)
        ```
    
    Multiple ASGI middlewares can be chained by wrapping multiple times:
        ```python
        app = use_asgi_middleware(app, Middleware1)
        app = use_asgi_middleware(app, Middleware2)
        ```
    
    Args:
        app: The BlackSheep application (or another ASGI application)
        middleware_class: The ASGI middleware class to wrap with
        **middleware_kwargs: Additional keyword arguments to pass to the
            middleware constructor
    
    Note:
        ASGI middlewares wrapped this way will execute before BlackSheep's
        internal middleware chain. For precise ordering requirements, consider
        the execution order when mixing ASGI and BlackSheep middlewares.
    """

    def __init__(
        self,
        app: Any,
        middleware_class: type,
        **middleware_kwargs: Any,
    ):
        self.app = app
        self.middleware = middleware_class(app, **middleware_kwargs)

    @property
    def started(self) -> bool:
        """Delegate to the wrapped app's started property."""
        return getattr(self.app, "started", True)

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        """
        ASGI application interface.
        
        Delegates to the wrapped ASGI middleware, which will eventually
        call the wrapped BlackSheep application.
        """
        await self.middleware(scope, receive, send)


def use_asgi_middleware(
    app: Any,
    middleware_class: type,
    **middleware_kwargs: Any,
) -> ASGIMiddlewareWrapper:
    """
    Wraps a BlackSheep application with a standard ASGI middleware.
    
    This helper function provides a convenient way to add ASGI middleware
    compatibility to BlackSheep applications. It wraps the application at
    the ASGI protocol level, allowing standard ASGI middlewares to intercept
    requests before they reach BlackSheep's internal processing.
    
    Args:
        app: The BlackSheep application to wrap
        middleware_class: The ASGI middleware class (e.g., SentryAsgiMiddleware)
        **middleware_kwargs: Additional keyword arguments to pass to the
            middleware constructor
    
    Returns:
        The wrapped application (ASGIMiddlewareWrapper instance)
    
    Example:
        ```python
        from blacksheep import Application
        from blacksheep.middlewares import use_asgi_middleware
        from sentry_sdk.integrations.asgi import SentryAsgiMiddleware
        
        app = Application()
        
        @app.route("/")
        async def home():
            return "Hello, World!"
        
        # Wrap with Sentry ASGI middleware
        app = use_asgi_middleware(app, SentryAsgiMiddleware)
        ```
    
    Multiple middlewares can be chained:
        ```python
        app = use_asgi_middleware(app, Middleware1)
        app = use_asgi_middleware(app, Middleware2)
        # Execution order: Middleware2 -> Middleware1 -> app
        ```
    
    Note:
        The wrapped ASGI middlewares execute at the ASGI protocol level,
        before BlackSheep converts the ASGI scope into a Request object.
        This means ASGI middlewares see the raw ASGI messages, not
        BlackSheep's typed Request/Response objects.
    """
    return ASGIMiddlewareWrapper(app, middleware_class, **middleware_kwargs)
