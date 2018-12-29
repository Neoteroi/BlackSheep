import pytest
from blacksheep import Request, Response, Headers, Header, TextContent, HtmlContent
from blacksheep.client import ClientSession, CircularRedirectError, MaximumRedirectsExceededError
from . import FakePools


@pytest.mark.asyncio
@pytest.mark.parametrize('params,expected_query', [
    [{}, None],
    [{'hello': 'world'}, b'hello=world'],
    [{'foo': True}, b'foo=True'],
    [{'foo': True, 'ufo': 'ufo'}, b'foo=True&ufo=ufo'],
    [[('x', 'a'), ('x', 'b'), ('x', 'c')], b'x=a&x=b&x=c'],
    [{'v': 'Hello World!'}, b'v=Hello+World%21'],
    [{'name': 'Łukasz'}, b'name=%C5%81ukasz']
])
async def test_query_params(params, expected_query):
    fake_pools = FakePools([Response(200, Headers(), TextContent('Hello, World!'))])

    async def middleware_for_assertions(request, next_handler):
        assert expected_query == request.url.query
        return await next_handler(request)

    async with ClientSession(url=b'http://localhost:8080',
                             pools=fake_pools,
                             middlewares=[middleware_for_assertions]) as client:
        await client.get(b'/', params=params)
        await client.head(b'/', params=params)
        await client.post(b'/', params=params)
        await client.put(b'/', params=params)
        await client.patch(b'/', params=params)
        await client.delete(b'/', params=params)
        await client.options(b'/', params=params)
        await client.trace(b'/', params=params)


@pytest.mark.asyncio
@pytest.mark.parametrize('request_url,params,expected_query', [
    ['/?foo=power', {}, b'foo=power'],
    ['/?foo=power', {'hello': 'world'}, b'foo=power&hello=world'],
    ['/?foo=power', {'foo': True}, b'foo=power&foo=True'],
    ['/?foo=power&search=something', {'ufo': 'ufo'}, b'foo=power&search=something&ufo=ufo']
])
async def test_query_params_concatenation(request_url, params, expected_query):
    fake_pools = FakePools([Response(200, Headers(), TextContent('Hello, World!'))])

    async def middleware_for_assertions(request, next_handler):
        assert expected_query == request.url.query
        return await next_handler(request)

    async with ClientSession(url=b'http://localhost:8080',
                             pools=fake_pools,
                             middlewares=[middleware_for_assertions]) as client:
        await client.get(request_url, params=params)
