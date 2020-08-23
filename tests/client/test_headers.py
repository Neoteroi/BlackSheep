import pytest
from blacksheep import Response, TextContent
from blacksheep.client import ClientSession
from . import FakePools


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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
