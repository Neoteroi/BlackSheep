"""
Tests for ASGI middleware wrapper functionality.
"""

import pytest

from blacksheep import Application, Response, get, text
from blacksheep.middlewares import ASGIMiddlewareWrapper, use_asgi_middleware
from blacksheep.testing import TestClient


class MockASGIMiddleware:
    """A mock ASGI middleware for testing."""

    def __init__(self, app, **kwargs):
        self.app = app
        self.kwargs = kwargs
        self.call_count = 0

    async def __call__(self, scope, receive, send):
        self.call_count += 1
        # Add a custom header to track middleware execution
        if scope["type"] == "http":
            # Store original send
            original_send = send

            async def custom_send(message):
                if message["type"] == "http.response.start":
                    # Add custom header
                    headers = list(message.get("headers", []))
                    headers.append((b"x-mock-middleware", b"executed"))
                    message = {**message, "headers": headers}
                await original_send(message)

            await self.app(scope, receive, custom_send)
        else:
            await self.app(scope, receive, send)


class OrderTrackingMiddleware:
    """Middleware to track execution order."""

    def __init__(self, app, name: str, tracker: list):
        self.app = app
        self.name = name
        self.tracker = tracker

    async def __call__(self, scope, receive, send):
        self.tracker.append(f"{self.name}_before")
        await self.app(scope, receive, send)
        self.tracker.append(f"{self.name}_after")


class ExceptionRaisingMiddleware:
    """Middleware that raises an exception."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("path") == "/error":
            raise ValueError("Test exception from middleware")
        await self.app(scope, receive, send)


class TestASGIMiddlewareWrapper:
    """Tests for ASGIMiddlewareWrapper class."""

    def test_wrapper_initialization(self):
        """Test that ASGIMiddlewareWrapper initializes correctly."""
        app = Application()
        wrapper = ASGIMiddlewareWrapper(app, MockASGIMiddleware, test_arg="value")

        assert wrapper.app is app
        assert isinstance(wrapper.middleware, MockASGIMiddleware)
        assert wrapper.middleware.app is app
        assert wrapper.middleware.kwargs == {"test_arg": "value"}

    async def test_wrapper_basic_functionality(self):
        """Test basic request/response flow through wrapped middleware."""
        app = Application()

        @get("/")
        async def home():
            return text("Hello, World!")

        await app.start()
        wrapped_app = ASGIMiddlewareWrapper(app, MockASGIMiddleware)

        client = TestClient(wrapped_app)
        response = await client.get("/")

        assert response.status == 200
        assert await response.text() == "Hello, World!"
        assert response.headers.get(b"x-mock-middleware") == b"executed"

    async def test_wrapper_preserves_response_data(self):
        """Test that response data flows correctly through the wrapper."""
        app = Application()

        @get("/json")
        async def json_endpoint():
            return Response(200).with_json({"message": "test", "value": 42})

        await app.start()
        wrapped_app = ASGIMiddlewareWrapper(app, MockASGIMiddleware)

        client = TestClient(wrapped_app)
        response = await client.get("/json")

        assert response.status == 200
        data = await response.json()
        assert data == {"message": "test", "value": 42}
        assert response.headers.get(b"x-mock-middleware") == b"executed"

    async def test_multiple_wrapped_middlewares(self):
        """Test chaining multiple ASGI middlewares."""
        execution_order = []

        app = Application()

        @get("/")
        async def home():
            return text("Hello")

        await app.start()
        # Wrap with multiple middlewares
        wrapped_app = ASGIMiddlewareWrapper(
            app, OrderTrackingMiddleware, name="middleware1", tracker=execution_order
        )
        wrapped_app = ASGIMiddlewareWrapper(
            wrapped_app,
            OrderTrackingMiddleware,
            name="middleware2",
            tracker=execution_order,
        )

        client = TestClient(wrapped_app)
        response = await client.get("/")

        assert response.status == 200
        # Middleware2 wraps middleware1, so it executes first
        assert execution_order == [
            "middleware2_before",
            "middleware1_before",
            "middleware1_after",
            "middleware2_after",
        ]

    async def test_use_asgi_middleware_helper(self):
        """Test the use_asgi_middleware helper function."""
        app = Application()

        @get("/")
        async def home():
            return text("Hello")

        await app.start()
        wrapped_app = use_asgi_middleware(app, MockASGIMiddleware)

        assert isinstance(wrapped_app, ASGIMiddlewareWrapper)

        client = TestClient(wrapped_app)
        response = await client.get("/")

        assert response.status == 200
        assert response.headers.get(b"x-mock-middleware") == b"executed"

    async def test_middleware_with_kwargs(self):
        """Test passing kwargs to middleware constructor."""
        app = Application()

        @get("/")
        async def home():
            return text("Hello")

        wrapped_app = use_asgi_middleware(
            app, MockASGIMiddleware, custom_arg="test_value", another=123
        )

        assert wrapped_app.middleware.kwargs == {"custom_arg": "test_value", "another": 123}

    async def test_404_with_wrapped_middleware(self):
        """Test that 404 responses work correctly with wrapped middleware."""
        app = Application()

        @get("/existing")
        async def existing():
            return text("exists")

        await app.start()
        wrapped_app = ASGIMiddlewareWrapper(app, MockASGIMiddleware)

        client = TestClient(wrapped_app)
        response = await client.get("/nonexistent")

        assert response.status == 404
        assert response.headers.get(b"x-mock-middleware") == b"executed"

    async def test_mixed_blacksheep_and_asgi_middlewares(self):
        """Test mixing BlackSheep middlewares with ASGI middlewares."""
        blacksheep_calls = []

        app = Application()

        # Add a BlackSheep middleware
        async def blacksheep_middleware(request, handler):
            blacksheep_calls.append("before")
            response = await handler(request)
            blacksheep_calls.append("after")
            response.set_header(b"x-blacksheep-middleware", b"executed")
            return response

        app.middlewares.append(blacksheep_middleware)

        @get("/")
        async def home():
            return text("Hello")

        await app.start()
        # Wrap with ASGI middleware (runs before BlackSheep middlewares)
        wrapped_app = ASGIMiddlewareWrapper(app, MockASGIMiddleware)

        client = TestClient(wrapped_app)
        response = await client.get("/")

        assert response.status == 200
        # Both middlewares should have executed
        assert response.headers.get(b"x-mock-middleware") == b"executed"
        assert response.headers.get(b"x-blacksheep-middleware") == b"executed"
        assert blacksheep_calls == ["before", "after"]

    async def test_exception_in_asgi_middleware(self):
        """Test that exceptions in ASGI middleware are propagated correctly."""
        app = Application()

        @get("/")
        async def home():
            return text("Hello")

        @get("/error")
        async def error_route():
            return text("Should not reach here")

        await app.start()
        wrapped_app = ASGIMiddlewareWrapper(app, ExceptionRaisingMiddleware)

        client = TestClient(wrapped_app)
        
        # Normal route should work
        response = await client.get("/")
        assert response.status == 200

        # Error route should raise exception
        with pytest.raises(ValueError, match="Test exception from middleware"):
            await client.get("/error")

    async def test_post_request_with_body(self):
        """Test POST requests with body data through wrapped middleware."""
        app = Application()

        @app.router.post("/echo")
        async def echo(request):
            data = await request.json()
            return Response(200).with_json(data)

        await app.start()
        wrapped_app = ASGIMiddlewareWrapper(app, MockASGIMiddleware)

        client = TestClient(wrapped_app)
        test_data = {"name": "test", "value": 123}
        response = await client.post("/echo", json=test_data)

        assert response.status == 200
        result = await response.json()
        assert result == test_data
        assert response.headers.get(b"x-mock-middleware") == b"executed"

    async def test_wrapper_with_query_parameters(self):
        """Test that query parameters are preserved through the wrapper."""
        app = Application()

        @get("/search")
        async def search(request):
            query = request.query.get("q")
            return text(f"Query: {query}")

        await app.start()
        wrapped_app = ASGIMiddlewareWrapper(app, MockASGIMiddleware)

        client = TestClient(wrapped_app)
        response = await client.get("/search?q=test")

        assert response.status == 200
        assert await response.text() == "Query: test"

    async def test_wrapper_with_custom_headers(self):
        """Test that custom request headers are preserved."""
        app = Application()

        @get("/headers")
        async def headers(request):
            custom = request.headers.get(b"x-custom-header")
            return text(f"Custom: {custom.decode() if custom else 'none'}")

        await app.start()
        wrapped_app = ASGIMiddlewareWrapper(app, MockASGIMiddleware)

        client = TestClient(wrapped_app)
        response = await client.get(
            "/headers", headers=[(b"x-custom-header", b"test-value")]
        )

        assert response.status == 200
        assert await response.text() == "Custom: test-value"

    async def test_chaining_use_asgi_middleware(self):
        """Test chaining multiple calls to use_asgi_middleware."""
        execution_order = []

        app = Application()

        @get("/")
        async def home():
            return text("Hello")

        await app.start()
        # Chain multiple middlewares using the helper
        app = use_asgi_middleware(
            app, OrderTrackingMiddleware, name="first", tracker=execution_order
        )
        app = use_asgi_middleware(
            app, OrderTrackingMiddleware, name="second", tracker=execution_order
        )
        app = use_asgi_middleware(
            app, OrderTrackingMiddleware, name="third", tracker=execution_order
        )

        client = TestClient(app)
        response = await client.get("/")

        assert response.status == 200
        # Last wrapped executes first
        assert execution_order == [
            "third_before",
            "second_before",
            "first_before",
            "first_after",
            "second_after",
            "third_after",
        ]
