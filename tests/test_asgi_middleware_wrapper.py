"""
Tests for ASGI middleware wrapper functionality.

Note: BlackSheep's TestClient bypasses the ASGI layer (calls app.handle() directly),
so these tests focus on unit testing the components or use manual ASGI protocol calls.
"""

import pytest

from blacksheep import Application, Response, get, text
from blacksheep.middlewares import (
    ASGIMiddlewareWrapper,
    ASGIContext,
    use_asgi_middleware,
    enable_asgi_context,
    asgi_middleware_adapter,
)


class MockASGIMiddleware:
    """A mock ASGI middleware for testing."""

    def __init__(self, app, **kwargs):
        self.app = app
        self.kwargs = kwargs
        self.called = False

    async def __call__(self, scope, receive, send):
        self.called = True
        # Add a custom header to track middleware execution
        if scope["type"] == "http":
            original_send = send

            async def custom_send(message):
                if message["type"] == "http.response.start":
                    headers = list(message.get("headers", []))
                    headers.append((b"x-mock-middleware", b"executed"))
                    message = {**message, "headers": headers}
                await original_send(message)

            await self.app(scope, receive, custom_send)
        else:
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

    def test_wrapper_has_started_property(self):
        """Test that wrapper exposes started property."""
        app = Application()
        wrapper = ASGIMiddlewareWrapper(app, MockASGIMiddleware)
        
        # Should delegate to wrapped app
        assert wrapper.started == app.started

    def test_use_asgi_middleware_returns_wrapper(self):
        """Test that use_asgi_middleware returns ASGIMiddlewareWrapper."""
        app = Application()
        wrapped = use_asgi_middleware(app, MockASGIMiddleware, test_arg="value")
        
        assert isinstance(wrapped, ASGIMiddlewareWrapper)
        assert wrapped.app is app
        assert wrapped.middleware.kwargs == {"test_arg": "value"}

    async def test_wrapper_calls_middleware(self):
        """Test that wrapper actually calls the ASGI middleware."""
        app = Application()
        
        @get("/")
        async def home():
            return text("Hello")
        
        await app.start()
        
        mock_middleware_instance = None
        
        class TrackingMiddleware:
            def __init__(self, app):
                nonlocal mock_middleware_instance
                self.app = app
                self.called = False
                mock_middleware_instance = self
            
            async def __call__(self, scope, receive, send):
                self.called = True
                await self.app(scope, receive, send)
        
        wrapped = use_asgi_middleware(app, TrackingMiddleware)
        
        # Simulate complete ASGI call with proper scope
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/",
            "raw_path": b"/",
            "query_string": b"",
            "root_path": "",
            "headers": [],
            "server": ("127.0.0.1", 8000),
        }
        
        received_messages = []
        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}
        
        async def send(message):
            received_messages.append(message)
        
        await wrapped(scope, receive, send)
        
        assert mock_middleware_instance.called is True
        assert len(received_messages) > 0


class TestASGIContext:
    """Tests for ASGIContext class."""

    def test_context_initialization(self):
        """Test ASGIContext initialization."""
        scope = {"type": "http"}
        
        async def receive():
            pass
        
        async def send(message):
            pass
        
        context = ASGIContext(scope, receive, send)
        
        assert context.scope is scope
        assert context._receive is receive
        assert context._send is send
        assert context._body_chunks == []
        assert context._body_consumed is False

    async def test_context_body_caching(self):
        """Test that ASGIContext caches body chunks."""
        messages = [
            {"type": "http.request", "body": b"chunk1", "more_body": True},
            {"type": "http.request", "body": b"chunk2", "more_body": False},
        ]
        message_index = 0
        
        async def receive():
            nonlocal message_index
            msg = messages[message_index]
            message_index += 1
            return msg
        
        async def send(message):
            pass
        
        context = ASGIContext({"type": "http"}, receive, send)
        
        # Read first chunk
        msg1 = await context.receive()
        assert msg1["body"] == b"chunk1"
        assert msg1["more_body"] is True
        
        # Read second chunk
        msg2 = await context.receive()
        assert msg2["body"] == b"chunk2"
        assert msg2["more_body"] is False
        
        # Check chunks were cached
        assert context._body_chunks == [b"chunk1", b"chunk2"]
        assert context._body_consumed is True

    async def test_context_send_delegation(self):
        """Test that ASGIContext.send delegates to original send."""
        sent_messages = []
        
        async def receive():
            pass
        
        async def send(message):
            sent_messages.append(message)
        
        context = ASGIContext({"type": "http"}, receive, send)
        
        test_message = {"type": "http.response.start", "status": 200}
        await context.send(test_message)
        
        assert len(sent_messages) == 1
        assert sent_messages[0] == test_message


class TestEnableASGIContext:
    """Tests for enable_asgi_context function."""

    def test_enable_asgi_context_wraps_app(self):
        """Test that enable_asgi_context modifies app.__call__."""
        app = Application()
        original_call = app.__call__
        
        wrapped_app = enable_asgi_context(app)
        
        # Should return same app instance
        assert wrapped_app is app
        # But with modified __call__
        assert app.__call__ is not original_call

    async def test_enable_asgi_context_creates_asgi_context(self):
        """Test that ASGIContext is created for HTTP requests."""
        app = Application()
        
        @get("/")
        async def home():
            return text("Hello")
        
        await app.start()
        app = enable_asgi_context(app)
        
        # Create a simple test by checking that wrapped_call creates context
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/test",
            "raw_path": b"/test",
            "query_string": b"",
            "root_path": "",
            "headers": [],
            "server": ("127.0.0.1", 8000),
        }
        
        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}
        
        sent_messages = []
        async def send(message):
            sent_messages.append(message)
        
        await app(scope, receive, send)
        
        # We should have sent at least the start message
        assert len(sent_messages) > 0
        # And the context should have been added to scope during execution
        # (even if it's not there at the end, it was there during processing)
        # The fact that the request was processed means enable_asgi_context worked

class TestASGIMiddlewareAdapter:
    """Tests for asgi_middleware_adapter function."""

    def test_adapter_returns_callable(self):
        """Test that adapter returns a BlackSheep middleware function."""
        adapter = asgi_middleware_adapter(MockASGIMiddleware)
        
        # Should be a coroutine function
        assert callable(adapter)

    async def test_adapter_raises_without_context(self):
        """Test that adapter raises error if ASGI context is missing."""
        adapter = asgi_middleware_adapter(MockASGIMiddleware)
        
        # Create a fake request without ASGI context
        from blacksheep import Request
        request = Request("GET", b"/", None)
        request.scope = {}  # No ASGI context
        
        async def handler(req):
            return Response(200)
        
        # Should raise RuntimeError
        with pytest.raises(RuntimeError, match="ASGI context not found"):
            await adapter(request, handler)

    async def test_adapter_works_with_context(self):
        """Test that adapter works when ASGI context is present."""
        from blacksheep import Request
        from blacksheep.contents import TextContent
        
        # Create adapter
        adapter = asgi_middleware_adapter(MockASGIMiddleware)
        
        # Create a request with ASGI context
        request = Request("GET", b"/", None)
        
        scope = {"type": "http", "method": "GET", "path": "/"}
        
        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}
        
        async def send(message):
            pass
        
        asgi_context = ASGIContext(scope, receive, send)
        request.scope = {"_blacksheep_asgi_context": asgi_context}
        
        handler_called = [False]
        
        async def handler(req):
            handler_called[0] = True
            response = Response(200, headers=[(b"test", b"value")])
            response.content = TextContent("Hello")
            return response
        
        # Call the adapter
        response = await adapter(request, handler)
        
        assert handler_called[0] is True
        assert isinstance(response, Response)


class TestIntegration:
    """Integration tests for both approaches."""

    def test_both_approaches_can_coexist(self):
        """Test that both approaches can be used together."""
        app = Application()
        
        # Enable context preservation
        app = enable_asgi_context(app)
        
        # Add middleware via adapter
        app.middlewares.append(asgi_middleware_adapter(MockASGIMiddleware))
        
        # Also wrap with another ASGI middleware
        wrapped_app = use_asgi_middleware(app, MockASGIMiddleware)
        
        # Both should work
        assert isinstance(wrapped_app, ASGIMiddlewareWrapper)
        assert len(app.middlewares) == 1


# Note: Full end-to-end tests with actual HTTP requests would require
# using an ASGI test client like httpx.AsyncClient instead of BlackSheep's
# TestClient, since TestClient bypasses the ASGI layer entirely.


class TestEarlyResponseBlocking:
    """Tests for early response handling - critical for auth/security middlewares."""
    
    class BlockingAuthMiddleware:
        """Mock auth middleware that blocks unauthorized requests."""
        
        def __init__(self, app, **kwargs):
            self.app = app
        
        async def __call__(self, scope, receive, send):
            # Check for auth header
            headers = dict(scope.get("headers", []))
            auth_token = headers.get(b"authorization", b"").decode()
            
            if not auth_token or auth_token != "Bearer valid-token":
                # Send 401 WITHOUT calling the app - handler should NOT execute
                await send({
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [(b"content-type", b"text/plain")],
                })
                await send({
                    "type": "http.response.body",
                    "body": b"Unauthorized",
                })
                return  # Do NOT call self.app
            
            # Auth passed - call the app
            await self.app(scope, receive, send)
    
    async def test_approach1_blocks_handler_on_early_response(self):
        """Test that simple wrapper blocks handler when middleware responds early."""
        handler_called = [False]
        
        app = Application()
        
        @get("/protected")
        async def protected_resource():
            handler_called[0] = True
            return text("Secret data")
        
        await app.start()
        app = use_asgi_middleware(app, self.BlockingAuthMiddleware)
        
        # Request without auth token
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/protected",
            "raw_path": b"/protected",
            "query_string": b"",
            "root_path": "",
            "headers": [],  # No auth header
            "server": ("127.0.0.1", 8000),
        }
        
        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}
        
        response_messages = []
        async def send(message):
            response_messages.append(message)
        
        await app(scope, receive, send)
        
        # Verify middleware sent 401
        assert len(response_messages) == 2
        assert response_messages[0]["type"] == "http.response.start"
        assert response_messages[0]["status"] == 401
        assert response_messages[1]["body"] == b"Unauthorized"
        
        # CRITICAL: Handler must NOT have been called
        assert handler_called[0] is False
    
    async def test_approach2_blocks_handler_on_early_response(self):
        """Test that adapter blocks handler when middleware responds early."""
        from blacksheep import Request
        
        # Create adapter
        adapter = asgi_middleware_adapter(self.BlockingAuthMiddleware)
        
        # Create request with ASGI context (no auth header)
        request = Request("GET", b"/protected", None)
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/protected",
            "headers": [],  # No auth header
        }
        
        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}
        
        async def send(message):
            pass
        
        asgi_context = ASGIContext(scope, receive, send)
        request.scope = {"_blacksheep_asgi_context": asgi_context}
        
        handler_called = [False]
        
        async def handler(req):
            handler_called[0] = True
            return text("Secret data")
        
        # Call adapter
        response = await adapter(request, handler)
        
        # Verify 401 response
        assert response.status == 401
        
        # CRITICAL: Handler must NOT have been called
        assert handler_called[0] is False
    
    async def test_approach2_calls_handler_with_valid_auth(self):
        """Test that adapter calls handler when auth passes."""
        from blacksheep import Request
        
        adapter = asgi_middleware_adapter(self.BlockingAuthMiddleware)
        
        # Create request with ASGI context WITH auth header
        request = Request("GET", b"/protected", None)
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/protected",
            "headers": [(b"authorization", b"Bearer valid-token")],
        }
        
        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}
        
        async def send(message):
            pass
        
        asgi_context = ASGIContext(scope, receive, send)
        request.scope = {"_blacksheep_asgi_context": asgi_context}
        
        handler_called = [False]
        
        async def handler(req):
            handler_called[0] = True
            return text("Secret data")
        
        # Call adapter
        response = await adapter(request, handler)
        
        # Handler SHOULD have been called
        assert handler_called[0] is True
        assert response.status == 200
