import pytest
from blacksheep import HttpRequest, HttpResponse, HttpHeaders, HttpHeader, TextContent, HtmlContent
from blacksheep.client import ClientSession, CircularRedirectError, MaximumRedirectsExceededError
from . import FakePools


@pytest.mark.asyncio
async def test_default_headers():
    fake_pools = FakePools([HttpResponse(200, HttpHeaders(), TextContent('Hello, World!'))])

    async def middleware_for_assertions(request, next_handler):
        assert b'hello' in request.headers
        assert request.headers.get_single(b'hello').value == b'World'

        assert b'Foo' in request.headers
        assert request.headers.get_single(b'Foo').value == b'Power'

        return await next_handler(request)

    async with ClientSession(url=b'http://localhost:8080',
                             pools=fake_pools,
                             middlewares=[middleware_for_assertions],
                             default_headers=[HttpHeader(b'Hello', b'World'),
                                              HttpHeader(b'Foo', b'Power')]
                             ) as client:
        await client.get(b'/')


@pytest.mark.asyncio
async def test_request_headers():
    fake_pools = FakePools([HttpResponse(200, HttpHeaders(), TextContent('Hello, World!'))])

    async def middleware_for_assertions(request, next_handler):
        assert b'Hello' in request.headers
        assert request.headers.get_single(b'Hello').value == b'World'

        return await next_handler(request)

    async with ClientSession(url=b'http://localhost:8080',
                             pools=fake_pools,
                             middlewares=[middleware_for_assertions]
                             ) as client:
        await client.get(b'/', headers=[HttpHeader(b'Hello', b'World')])
        await client.post(b'/', headers=[HttpHeader(b'Hello', b'World')])
        await client.put(b'/', headers=[HttpHeader(b'Hello', b'World')])
        await client.delete(b'/', headers=[HttpHeader(b'Hello', b'World')])


@pytest.mark.asyncio
async def test_request_headers_override_default_header():
    fake_pools = FakePools([HttpResponse(200, HttpHeaders(), TextContent('Hello, World!'))])

    async def middleware_for_assertions(request, next_handler):
        assert b'hello' in request.headers
        assert request.headers.get_single(b'hello').value == b'Kitty'

        assert b'Foo' in request.headers
        assert request.headers.get_single(b'Foo').value == b'Power'

        return await next_handler(request)

    async with ClientSession(url=b'http://localhost:8080',
                             pools=fake_pools,
                             middlewares=[middleware_for_assertions],
                             default_headers=[HttpHeader(b'Hello', b'World'),
                                              HttpHeader(b'Foo', b'Power')]
                             ) as client:
        await client.get(b'/', headers=[HttpHeader(b'Hello', b'Kitty')])
