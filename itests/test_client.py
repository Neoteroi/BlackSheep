from uuid import uuid4
from blacksheep import Response
from .client_fixtures import *


def ensure_success(response: Response):
    assert response is not None
    assert isinstance(response, Response)
    assert response.status == 200


@pytest.mark.asyncio
async def test_get_plain_text(session, event_loop):
    response = await session.get('/hello-world')
    ensure_success(response)

    text = await response.text()
    assert text == 'Hello, World!'


@pytest.mark.asyncio
async def test_get_plain_text_stream(session, event_loop):
    response = await session.get('/hello-world')
    ensure_success(response)

    data = bytearray()
    async for chunk in response.stream():
        data.extend(chunk)

    assert bytes(data) == b'Hello, World!'


@pytest.mark.asyncio
@pytest.mark.parametrize('headers', [
    [(b'x-foo', str(uuid4()).encode())],
    [(b'x-a', b'Hello'), (b'x-b', b'World'), (b'x-c', b'!!')]
])
async def test_headers(session, headers):
    response = await session.head('/echo-headers', headers=headers)
    ensure_success(response)

    for key, value in headers:
        header = response.headers[key]
        assert (value,) == header


@pytest.mark.asyncio
@pytest.mark.parametrize('cookies', [
    {'x-foo': str(uuid4())},
    {'x-a': 'Hello', 'x-b': 'World', 'x-c': '!!'}
])
async def test_cookies(session, cookies):
    response = await session.get('/echo-cookies', headers=[
        (b'cookie', '; '.join([f'{name}={value}' for name, value in cookies.items()]).encode())
    ])
    ensure_success(response)

    data = await response.json()

    for key, value in cookies.items():
        header = data[key]
        assert value == header


@pytest.mark.asyncio
@pytest.mark.parametrize('name,value', [
    (b'Foo', b'Foo'),
    (b'Character-Name', b'Charlie Brown')
])
async def test_set_cookie(session, name, value):
    response = await session.get('/set-cookie', params=dict(name=name, value=value))
    ensure_success(response)

    assert value == response.cookies[name]
