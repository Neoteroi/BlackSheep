import pytest

from blacksheep import URL, Request, Response
from blacksheep.client import ClientSession
from blacksheep.client.connection import ClientConnection, ConnectionClosedError
from blacksheep.client.exceptions import UnsupportedRedirect
from blacksheep.client.session import normalize_headers


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


@pytest.mark.asyncio
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
            return DemoConnection(None, pool)

    with pytest.raises(ConnectionClosedError):
        async with DemoClient() as client:
            await client._send_using_connection(
                Request("GET", b"https://somewhere.org", None)
            )


@pytest.mark.asyncio
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


@pytest.mark.asyncio
async def test_client_session_validate_url_for_relative_urls_no_base_url():
    async with ClientSession() as client:
        with pytest.raises(ValueError):
            client._validate_request_url(Request("GET", b"/", None))


@pytest.mark.asyncio
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
