import pytest

from blacksheep import URL, Request, Response
from blacksheep.client import ClientSession
from blacksheep.client.connection import ClientConnection, ConnectionClosedError
from blacksheep.client.exceptions import UnsupportedRedirect
from blacksheep.client.session import normalize_headers
from blacksheep.contents import TextContent


@pytest.mark.parametrize(
    "value,result",
    [
        ["", b"/"],
        ["/?hello=world", b"/?hello=world"],
        ["https://foo.org", b"https://foo.org"],
        ["https://foo.org/?hello=world", b"https://foo.org/?hello=world"],
        ["https://foo.org?hello=world", b"https://foo.org?hello=world"],
    ],
)
def test_get_url_value(value, result):
    client = ClientSession()
    assert client.get_url_value(value) == result


@pytest.mark.parametrize(
    "base_url,value,result",
    [
        ["https://example.org", "/?hello=world", b"https://example.org/?hello=world"],
        ["https://example.org", "https://foo.org", b"https://foo.org"],
        [
            "https://example.org",
            "https://foo.org/?hello=world",
            b"https://foo.org/?hello=world",
        ],
        [
            "https://example.org",
            "https://foo.org?hello=world",
            b"https://foo.org?hello=world",
        ],
    ],
)
def test_get_url_value_with_base_url(base_url, value, result):
    client = ClientSession(base_url=base_url)
    assert client.get_url_value(value) == result


def test_check_permanent_redirects():
    client = ClientSession()
    client._permanent_redirects_urls._cache[b"/foo"] = URL(b"https://somewhere.org")

    request = Request("GET", b"/foo", None)
    assert request.url == URL(b"/foo")

    client.check_permanent_redirects(request)
    assert request.url == URL(b"https://somewhere.org")


def test_update_request_for_redirect_raises_for_urn_redirects():
    client = ClientSession()

    with pytest.raises(UnsupportedRedirect) as redirect_exception:
        client.update_request_for_redirect(
            Request("GET", b"/foo", None),
            Response(
                302, [(b"Location", b"urn:uuid:6e8bc430-9c3a-11d9-9669-0800200c9a66")]
            ),
        )

    assert (
        redirect_exception.value.redirect_url
        == b"urn:uuid:6e8bc430-9c3a-11d9-9669-0800200c9a66"
    )


async def test_client_send_handles_connection_closed_error():
    attempt = 0

    class DemoConnection(ClientConnection):
        async def send(self, request):
            nonlocal attempt
            attempt += 1
            raise ConnectionClosedError(attempt < 2)

    class DemoClient(ClientSession):
        async def get_connection(self, url: URL) -> ClientConnection:
            pool = self.pools.get_pool(url.schema, url.host, url.port, self.ssl)
            return DemoConnection(pool)

    with pytest.raises(ConnectionClosedError):
        async with DemoClient() as client:
            await client._send_using_connection(
                Request("GET", b"https://somewhere.org", None)
            )


async def test_client_session_without_middlewares_and_cookiejar():
    called = False

    async def monkey_send_core(request):
        nonlocal called
        called = True
        return Response(200)

    async with ClientSession(cookie_jar=False) as client:
        assert client._handler is None
        assert not client.middlewares

        client._send_core = monkey_send_core  # type: ignore

        await client.send(Request("GET", b"https://somewhere.org", None))

        assert called is True


async def test_client_session_validate_url_for_relative_urls_no_base_url():
    async with ClientSession() as client:
        with pytest.raises(ValueError):
            client._validate_request_url(Request("GET", b"/", None))


async def test_client_session_validate_url_for_relative_urls_with_base_url():
    async with ClientSession(base_url=b"https://foo.org") as client:
        request = Request("GET", b"/home", None)

        client._validate_request_url(request)

        assert request.url == URL(b"https://foo.org/home")


@pytest.mark.parametrize(
    "value,expected_result",
    [
        [
            [("accept", "gzip br")],
            [(b"accept", b"gzip br")],
        ],
        [
            [("accept", b"gzip br"), ("referrer", "http://neoteroi.dev")],
            [(b"accept", b"gzip br"), (b"referrer", b"http://neoteroi.dev")],
        ],
        [
            [(b"accept", b"gzip br")],
            [(b"accept", b"gzip br")],
        ],
        [
            {"X-Refresh-Token": "Example"},
            [(b"X-Refresh-Token", b"Example")],
        ],
        [
            {"x-one": "one", "x-two": "two", "x-three": "three"},
            [(b"x-one", b"one"), (b"x-two", b"two"), (b"x-three", b"three")],
        ],
    ],
)
def test_normalize_headers(value, expected_result):
    result = normalize_headers(value)
    assert result == expected_result


async def test_client_session_middleware_execution_order():
    """Test that middlewares are executed in the correct order"""
    execution_order = []

    async def middleware_1(request, next_handler):
        execution_order.append("middleware_1_before")
        response = await next_handler(request)
        execution_order.append("middleware_1_after")
        return response

    async def middleware_2(request, next_handler):
        execution_order.append("middleware_2_before")
        response = await next_handler(request)
        execution_order.append("middleware_2_after")
        return response

    async def mock_send_core(request):
        execution_order.append("core_handler")
        return Response(200)

    async with ClientSession(middlewares=[middleware_1, middleware_2]) as client:
        client._send_core = mock_send_core  # type: ignore

        await client.send(Request("GET", b"https://example.com", None))

        assert execution_order == [
            "middleware_1_before",
            "middleware_2_before",
            "core_handler",
            "middleware_2_after",
            "middleware_1_after",
        ]


async def test_client_session_middleware_modifies_request():
    """Test that middlewares can modify the request"""

    async def auth_middleware(request, next_handler):
        request.add_header(b"Authorization", b"Bearer token123")
        return await next_handler(request)

    captured_request = None

    async def mock_send_core(request):
        nonlocal captured_request
        captured_request = request
        return Response(200)

    async with ClientSession(middlewares=[auth_middleware]) as client:
        client._send_core = mock_send_core  # type: ignore

        request = Request("GET", b"https://example.com", None)
        await client.send(request)

        assert captured_request.get_first_header(b"Authorization") == b"Bearer token123"


async def test_client_session_middleware_modifies_response():
    """Test that middlewares can modify the response"""

    async def response_modifier_middleware(request, next_handler):
        response = await next_handler(request)
        response.add_header(b"X-Modified", b"true")
        return response

    async def mock_send_core(request):
        return Response(200)

    async with ClientSession(middlewares=[response_modifier_middleware]) as client:
        client._send_core = mock_send_core  # type: ignore

        response = await client.send(Request("GET", b"https://example.com", None))

        assert response.get_first_header(b"X-Modified") == b"true"


async def test_client_session_middleware_exception_handling():
    """Test that exceptions in middlewares are properly handled"""

    class CustomError(Exception):
        pass

    async def failing_middleware(request, next_handler):
        raise CustomError("Middleware failed")

    async with ClientSession(middlewares=[failing_middleware]) as client:
        with pytest.raises(CustomError, match="Middleware failed"):
            await client.send(Request("GET", b"https://example.com", None))


async def test_client_session_middleware_can_skip_core_handler():
    """Test that middleware can return a response without calling the next handler"""

    async def short_circuit_middleware(request, next_handler):
        if request.get_first_header(b"X-Skip-Core"):
            return Response(304, content=TextContent("Not Modified"))
        return await next_handler(request)

    core_called = False

    async def mock_send_core(request):
        nonlocal core_called
        core_called = True
        return Response(200)

    async with ClientSession(middlewares=[short_circuit_middleware]) as client:
        client._send_core = mock_send_core  # type: ignore

        request = Request("GET", b"https://example.com", [(b"X-Skip-Core", b"true")])
        response = await client.send(request)

        assert response.status == 304
        assert not core_called


async def test_client_session_middleware_with_cookie_jar():
    """Test that middlewares work correctly with cookie jar enabled"""

    async def custom_middleware(request, next_handler):
        request.add_header(b"X-Custom", b"middleware")
        return await next_handler(request)

    captured_request = None

    async def mock_send_core(request):
        nonlocal captured_request
        captured_request = request
        return Response(200)

    async with ClientSession(
        middlewares=[custom_middleware], cookie_jar=True
    ) as client:
        client._send_core = mock_send_core  # type: ignore

        await client.send(Request("GET", b"https://example.com", None))

        # Should have both cookie middleware and custom middleware effects
        assert captured_request.get_first_header(b"X-Custom") == b"middleware"
        # Cookie middleware should be present in the chain
        assert len(client.middlewares) == 2  # cookie middleware + custom middleware


async def test_client_session_add_middlewares():
    """Test adding middlewares after client creation"""
    execution_order = []

    async def middleware_1(request, next_handler):
        execution_order.append("middleware_1")
        return await next_handler(request)

    async def middleware_2(request, next_handler):
        execution_order.append("middleware_2")
        return await next_handler(request)

    async def mock_send_core(request):
        execution_order.append("core")
        return Response(200)

    async with ClientSession() as client:
        client.add_middlewares([middleware_1, middleware_2])
        client._send_core = mock_send_core  # type: ignore

        await client.send(Request("GET", b"https://example.com", None))

        assert "middleware_1" in execution_order
        assert "middleware_2" in execution_order
        assert "core" in execution_order


async def test_client_session_middleware_with_redirects():
    """Test that middlewares work correctly with redirect handling"""
    redirect_count = 0

    async def redirect_counter_middleware(request, next_handler):
        nonlocal redirect_count
        redirect_count += 1
        return await next_handler(request)

    call_count = 0

    async def mock_send_core(request):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return Response(302, [(b"Location", b"https://example.com/redirected")])
        return Response(200, content=TextContent("Final response"))

    async with ClientSession(
        middlewares=[redirect_counter_middleware], follow_redirects=True
    ) as client:
        client._send_core = mock_send_core  # type: ignore

        response = await client.send(Request("GET", b"https://example.com", None))

        assert response.status == 200
        assert redirect_count == 2  # Called for initial request and redirect
        assert call_count == 2


async def test_client_session_multiple_middlewares_modify_same_header():
    """Test multiple middlewares modifying the same header"""

    async def middleware_1(request, next_handler):
        request.add_header(b"X-Test", b"value1")
        return await next_handler(request)

    async def middleware_2(request, next_handler):
        request.add_header(b"X-Test", b"value2")
        return await next_handler(request)

    captured_request: Request | None = None

    async def mock_send_core(request):
        nonlocal captured_request
        captured_request = request
        return Response(200)

    async with ClientSession(middlewares=[middleware_1, middleware_2]) as client:
        client._send_core = mock_send_core  # type: ignore

        await client.send(Request("GET", b"https://example.com", None))

        # Should have both header values
        assert isinstance(captured_request, Request)
        test_headers = captured_request.headers[b"X-Test"]
        assert b"value1" in test_headers
        assert b"value2" in test_headers


async def test_client_session_middleware_async_context_manager():
    """Test middleware behavior with client used as async context manager"""
    middleware_called = False

    async def test_middleware(request, next_handler):
        nonlocal middleware_called
        middleware_called = True
        return await next_handler(request)

    async def mock_send_core(request):
        return Response(200)

    client = ClientSession(middlewares=[test_middleware])
    client._send_core = mock_send_core  # type: ignore

    async with client:
        await client.send(Request("GET", b"https://example.com", None))

    assert middleware_called


async def test_client_session_middleware_preserves_request_context():
    """Test that middlewares preserve request context"""

    async def context_middleware(request, next_handler):
        # Middleware should not interfere with request context
        return await next_handler(request)

    context_set = False

    async def mock_send_core(request):
        nonlocal context_set
        context_set = hasattr(request, "context")
        return Response(200)

    async with ClientSession(middlewares=[context_middleware]) as client:
        client._send_core = mock_send_core  # type: ignore

        await client.send(Request("GET", b"https://example.com", None))

        assert context_set
