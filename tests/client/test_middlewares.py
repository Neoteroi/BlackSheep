import pytest
from blacksheep import HttpRequest, HttpResponse, HttpHeaders, HttpHeader, TextContent, HtmlContent
from blacksheep.client import ClientSession, CircularRedirectError, MaximumRedirectsExceededError
from . import FakePools


@pytest.mark.asyncio
async def test_single_middleware():
    fake_pools = FakePools([HttpResponse(200, HttpHeaders(), TextContent('Hello, World!'))])

    steps = []

    async def middleware_one(request, context, next_handler):
        steps.append(1)
        response = await next_handler(request, context)
        steps.append(2)
        return response

    async with ClientSession(url=b'http://localhost:8080',
                             pools=fake_pools,
                             middlewares=[middleware_one]
                             ) as client:
        response = await client.get(b'/')

        assert steps == [1, 2]
        assert response.status == 200
        text = await response.text()
        assert text == 'Hello, World!'


@pytest.mark.asyncio
async def test_multiple_middleware():
    fake_pools = FakePools([HttpResponse(200, HttpHeaders(), TextContent('Hello, World!'))])

    steps = []

    async def middleware_one(request, context, next_handler):
        steps.append(1)
        response = await next_handler(request, context)
        steps.append(2)
        return response

    async def middleware_two(request, context, next_handler):
        steps.append(3)
        response = await next_handler(request, context)
        steps.append(4)
        return response

    async def middleware_three(request, context, next_handler):
        steps.append(5)
        response = await next_handler(request, context)
        steps.append(6)
        return response

    async with ClientSession(url=b'http://localhost:8080',
                             pools=fake_pools,
                             middlewares=[middleware_one, middleware_two, middleware_three]
                             ) as client:
        response = await client.get(b'/')

        assert steps == [1, 3, 5, 6, 4, 2]
        assert response.status == 200
        text = await response.text()
        assert text == 'Hello, World!'
