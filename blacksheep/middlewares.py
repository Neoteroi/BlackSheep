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


# ============================================================================
# Enhanced Approach: ASGI Context Preservation
# ============================================================================
# The following classes and functions enable ASGI middlewares to be inserted
# anywhere in the BlackSheep middleware chain by preserving ASGI context.


class ASGIContext:
    """
    Container for ASGI protocol context (scope, receive, send).
    
    This class is attached to Request objects to preserve the raw ASGI
    context, enabling ASGI middlewares to be invoked at any point in
    the BlackSheep middleware chain.
    
    The context caches body chunks to allow re-reading if needed by
    ASGI middlewares that are called after the body has been consumed.
    """
    
    def __init__(self, scope: dict, receive: Callable, send: Callable):
        self.scope = scope
        self._receive = receive
        self._send = send
        self._body_chunks: list[bytes] = []
        self._body_consumed = False
        self._body_index = 0
    
    async def receive(self) -> dict:
        """
        Wrapped receive that caches body for potential re-reading.
        
        This allows ASGI middlewares inserted later in the chain to
        still access the request body even if it was already consumed.
        """
        if self._body_consumed and self._body_index < len(self._body_chunks):
            # Re-reading cached body
            chunk = self._body_chunks[self._body_index]
            self._body_index += 1
            more_body = self._body_index < len(self._body_chunks)
            return {
                "type": "http.request",
                "body": chunk,
                "more_body": more_body,
            }
        
        message = await self._receive()
        
        if message.get("type") == "http.request":
            # Cache body chunk
            body = message.get("body", b"")
            if body:
                self._body_chunks.append(body)
            
            # Mark if this is the last chunk
            if not message.get("more_body", False):
                self._body_consumed = True
        
        return message
    
    async def send(self, message: dict) -> None:
        """Forward send to original callable."""
        await self._send(message)


def enable_asgi_context(app: Any) -> Any:
    """
    Enables ASGI context preservation on Request objects.
    
    This wrapper intercepts ASGI calls to the application and attaches
    an ASGIContext to each HTTP request's scope. This preserved context
    allows ASGI middlewares to be inserted anywhere in the BlackSheep
    middleware chain using `asgi_middleware_adapter()`.
    
    Args:
        app: The BlackSheep application to wrap
    
    Returns:
        The wrapped application (same object, but with modified __call__)
    
    Example:
        ```python
        from blacksheep import Application
        from blacksheep.middlewares import (
            enable_asgi_context,
            asgi_middleware_adapter,
        )
        from sentry_sdk.integrations.asgi import SentryAsgiMiddleware
        
        app = Application()
        app = enable_asgi_context(app)  # Enable ASGI context preservation
        
        # Now ASGI middlewares can be inserted anywhere!
        app.middlewares.append(some_blacksheep_middleware)
        app.middlewares.append(asgi_middleware_adapter(SentryAsgiMiddleware))
        app.middlewares.append(another_blacksheep_middleware)
        ```
    
    Note:
        This approach has more overhead than `use_asgi_middleware()` due to
        context preservation and conversions. Use `use_asgi_middleware()` for
        simple cases where ASGI middlewares only need to wrap the entire app.
    """
    original_call = app.__call__
    
    async def wrapped_call(scope: dict, receive: Callable, send: Callable):
        if scope["type"] == "http":
            # Store ASGI context for this request
            asgi_context = ASGIContext(scope, receive, send)
            scope["_blacksheep_asgi_context"] = asgi_context
            
            # Use the context's wrapped receive for body caching
            receive = asgi_context.receive
        
        return await original_call(scope, receive, send)
    
    app.__call__ = wrapped_call
    return app


def asgi_middleware_adapter(
    asgi_middleware_class: type,
    **middleware_kwargs: Any,
) -> Callable[..., Awaitable[Response]]:
    """
    Converts an ASGI middleware into a BlackSheep middleware.
    
    This adapter allows inserting ASGI middlewares at any point in the
    BlackSheep middleware chain, as long as ASGI context is preserved
    on the Request (by wrapping the app with `enable_asgi_context()`).
    
    The adapter handles the conversion between BlackSheep's Request/Response
    objects and ASGI's scope/receive/send protocol.
    
    Args:
        asgi_middleware_class: The ASGI middleware class
        **middleware_kwargs: Arguments to pass to middleware constructor
    
    Returns:
        A BlackSheep-compatible middleware function
    
    Example:
        ```python
        from blacksheep import Application
        from blacksheep.middlewares import (
            enable_asgi_context,
            asgi_middleware_adapter,
        )
        from sentry_sdk.integrations.asgi import SentryAsgiMiddleware
        
        app = Application()
        app = enable_asgi_context(app)
        
        # Mix BlackSheep and ASGI middlewares freely
        async def logging_middleware(request, handler):
            print(f"Request: {request.url}")
            return await handler(request)
        
        app.middlewares.append(logging_middleware)
        app.middlewares.append(asgi_middleware_adapter(SentryAsgiMiddleware))
        ```
    
    Raises:
        RuntimeError: If ASGI context is not found on the request (forgot to
            call `enable_asgi_context()` on the app)
    
    Note:
        This approach has performance overhead due to conversions between
        BlackSheep and ASGI formats. For simple cases where ASGI middleware
        only needs to wrap the entire app, use `use_asgi_middleware()` instead.
    """
    
    async def blacksheep_middleware(request, handler: Callable):
        # Extract ASGI context from request
        asgi_context = request.scope.get("_blacksheep_asgi_context")
        
        if asgi_context is None:
            raise RuntimeError(
                "ASGI context not found on request. "
                "Did you forget to wrap your app with enable_asgi_context()? "
                "Example: app = enable_asgi_context(app)"
            )
        
        # Container to capture the response from ASGI middleware
        response_data: dict = {}
        
        # Wrapper for send that captures response
        async def send_wrapper(message: dict):
            if message["type"] == "http.response.start":
                response_data["status"] = message["status"]
                response_data["headers"] = message.get("headers", [])
            elif message["type"] == "http.response.body":
                body = message.get("body", b"")
                if "body" not in response_data:
                    response_data["body"] = body
                else:
                    response_data["body"] += body
        
        # Create a fake ASGI app that wraps the rest of the BlackSheep chain
        async def fake_asgi_app(scope: dict, receive: Callable, send: Callable):
            # Call the next BlackSheep middleware/handler
            response = await handler(request)
            
            # Convert BlackSheep Response to ASGI messages
            headers = []
            if response.headers:
                for header in response.headers:
                    if isinstance(header, tuple) and len(header) == 2:
                        name, value = header
                        if isinstance(name, str):
                            name = name.encode()
                        if isinstance(value, str):
                            value = value.encode()
                        headers.append((name, value))
            
            await send({
                "type": "http.response.start",
                "status": response.status,
                "headers": headers,
            })
            
            # Send body
            body = b""
            if response.content:
                if hasattr(response.content, "body"):
                    body = response.content.body
                    if isinstance(body, str):
                        body = body.encode()
                elif hasattr(response.content, "__aiter__"):
                    # Handle streaming
                    chunks = []
                    async for chunk in response.content:
                        if isinstance(chunk, str):
                            chunk = chunk.encode()
                        chunks.append(chunk)
                    body = b"".join(chunks)
            
            await send({
                "type": "http.response.body",
                "body": body,
            })
        
        # Instantiate and call the ASGI middleware
        middleware = asgi_middleware_class(fake_asgi_app, **middleware_kwargs)
        await middleware(asgi_context.scope, asgi_context.receive, send_wrapper)
        
        # Convert captured ASGI response back to BlackSheep Response
        if response_data:
            response = Response(
                status=response_data.get("status", 200),
                headers=response_data.get("headers", []),
            )
            body = response_data.get("body", b"")
            if body:
                from blacksheep.contents import Content
                response.content = Content(b"application/octet-stream", body)
            return response
        
        # Fallback: call handler normally if no response was captured
        return await handler(request)
    
    return blacksheep_middleware
