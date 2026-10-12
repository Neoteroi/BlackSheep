import pytest
from h2.config import H2Configuration
from h2.connection import H2Connection
from h2.events import RequestReceived

from blacksheep import Headers, Request, Response, TextContent
from blacksheep.client import ClientSession
from blacksheep.client.connection import HTTP2Connection

from . import FakePools


async def test_default_headers():
    fake_pools = FakePools([Response(200, [], TextContent("Hello, World!"))])

    async def middleware_for_assertions(request, next_handler):
        assert b"hello" in request.headers
        assert request.headers.get_single(b"hello") == b"World"

        assert b"Foo" in request.headers
        assert request.headers.get_single(b"Foo") == b"Power"

        return await next_handler(request)

    async with ClientSession(
        base_url=b"http://localhost:8080",
        pools=fake_pools,
        middlewares=[middleware_for_assertions],
        default_headers=[(b"Hello", b"World"), (b"Foo", b"Power")],
    ) as client:
        await client.get(b"/")


async def test_request_headers():
    fake_pools = FakePools([Response(200, [], TextContent("Hello, World!"))])

    async def middleware_for_assertions(request, next_handler):
        assert b"Hello" in request.headers
        assert request.headers.get_single(b"Hello") == b"World"

        return await next_handler(request)

    async with ClientSession(
        base_url=b"http://localhost:8080",
        pools=fake_pools,
        middlewares=[middleware_for_assertions],
    ) as client:
        await client.get(b"/", headers=[(b"Hello", b"World")])
        await client.post(b"/", headers=[(b"Hello", b"World")])
        await client.put(b"/", headers=[(b"Hello", b"World")])
        await client.delete(b"/", headers=[(b"Hello", b"World")])


async def test_request_headers_override_default_header():
    fake_pools = FakePools([Response(200, [], TextContent("Hello, World!"))])

    async def middleware_for_assertions(request, next_handler):
        assert b"hello" in request.headers
        assert request.headers.get_single(b"hello") == b"Kitty"

        assert b"Foo" in request.headers
        assert request.headers.get_single(b"Foo") == b"Power"

        return await next_handler(request)

    async with ClientSession(
        base_url=b"http://localhost:8080",
        pools=fake_pools,
        middlewares=[middleware_for_assertions],
        default_headers=[(b"Hello", b"World"), (b"Foo", b"Power")],
    ) as client:
        await client.get(b"/", headers=[(b"Hello", b"Kitty")])


@pytest.mark.parametrize(
    "method", ["get", "post", "put", "delete", "trace", "head", "patch", "options"]
)
async def test_client_text_headers_share_encoding_and_preserve_duplicates(method):
    fake_pools = FakePools([Response(200)])

    async def middleware_for_assertions(request, next_handler):
        assert request.headers["x-example"] == (b"caf\xe9", b"\xff")
        assert request.headers["x-default"] == (b"default=\xe9",)
        assert request.headers.get_text_values("x-example") == ("caf\xe9", "\xff")
        request.headers.add_text("X-Example", "another")
        assert len(request.headers["x-example"]) == 3
        return await next_handler(request)

    async with ClientSession(
        base_url="http://localhost:8080",
        pools=fake_pools,
        middlewares=[middleware_for_assertions],
        default_headers={"X-Example": "overridden", "X-Default": "default=\xe9"},
    ) as client:
        await getattr(client, method)(
            "/", headers=[("x-example", "caf\xe9"), (b"X-Example", b"\xff")]
        )


def test_http2_header_serialization_preserves_raw_values_and_duplicates():
    pools = FakePools([])
    connection = HTTP2Connection(pools, "localhost", 443)
    request = Request(
        "POST",
        b"https://localhost/example?q=test",
        Headers.from_values(
            [
                ("X-Example", "caf\xe9"),
                (b"X-Example", b"\xff"),
                ("Expect", "100-continue"),
                ("Host", "ignored"),
                ("Connection", "keep-alive"),
                ("Transfer-Encoding", "chunked"),
            ]
        ).values,
    )
    request.with_content(TextContent("hello"))
    headers = connection._convert_request_to_h2_headers(request)
    assert (b":path", b"/example?q=test") in headers
    assert (b"expect", b"100-continue") in headers
    assert (b"content-type", b"text/plain; charset=utf-8") in headers
    assert not any(
        name in (b"host", b"connection", b"transfer-encoding") for name, _ in headers
    )

    peer = H2Connection(config=H2Configuration(client_side=False))
    peer.initiate_connection()
    connection.h2_conn.initiate_connection()
    connection.h2_conn.send_headers(1, headers, end_stream=False)
    events = peer.receive_data(connection.h2_conn.data_to_send())
    received = next(event for event in events if isinstance(event, RequestReceived))
    assert [
        (name, value) for name, value in received.headers if name == b"x-example"
    ] == [
        (b"x-example", b"caf\xe9"),
        (b"x-example", b"\xff"),
    ]
