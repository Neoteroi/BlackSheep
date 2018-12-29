import pytest
from blacksheep import Request, Response, Headers, Header, TextContent, HtmlContent
from blacksheep.client import ClientSession, CircularRedirectError, MaximumRedirectsExceededError
from . import FakePools


@pytest.mark.asyncio
async def test_single_middleware():
    fake_pools = FakePools([Response(200, Headers(), TextContent('Hello, World!'))])

    steps = []

    async def middleware_one(request, next_handler):
        steps.append(1)
        response = await next_handler(request)
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
    fake_pools = FakePools([Response(200, Headers(), TextContent('Hello, World!'))])

    steps = []

    async def middleware_one(request, next_handler):
        steps.append(1)
        response = await next_handler(request)
        steps.append(2)
        return response

    async def middleware_two(request, next_handler):
        steps.append(3)
        response = await next_handler(request)
        steps.append(4)
        return response

    async def middleware_three(request, next_handler):
        steps.append(5)
        response = await next_handler(request)
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


@pytest.mark.asyncio
async def test_middlewares_can_be_applied_multiple_times_without_changing():
    fake_pools = FakePools([Response(200, Headers(), TextContent('Hello, World!'))])

    steps = []

    async def middleware_one(request, next_handler):
        steps.append(1)
        response = await next_handler(request)
        steps.append(2)
        return response

    async def middleware_two(request, next_handler):
        steps.append(3)
        response = await next_handler(request)
        steps.append(4)
        return response

    async def middleware_three(request, next_handler):
        steps.append(5)
        response = await next_handler(request)
        steps.append(6)
        return response

    async with ClientSession(url=b'http://localhost:8080',
                             pools=fake_pools) as client:
        client.add_middlewares([middleware_one])
        client.add_middlewares([middleware_two])
        client.add_middlewares([middleware_three])

        assert middleware_one in client._middlewares
        assert middleware_two in client._middlewares
        assert middleware_three in client._middlewares

        client._build_middlewares_chain()

        response = await client.get(b'/')

        assert steps == [1, 3, 5, 6, 4, 2]
        assert response.status == 200
        text = await response.text()
        assert text == 'Hello, World!'
