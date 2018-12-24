import pytest
from blacksheep import HttpResponse, HttpHeader, HttpHeaders, HttpContent, HttpCookie
from blacksheep import scribe


@pytest.mark.asyncio
@pytest.mark.parametrize('response,cookies,expected_result', [
    (
        HttpResponse(400, HttpHeaders([
            HttpHeader(b'Server', b'BlackSheep'),
        ]), HttpContent(b'text/plain', b'Hello, World')),
        [],
        b'HTTP/1.1 400 Bad Request\r\nServer: BlackSheep\r\nContent-Type: text/plain\r\nContent-Length: 12\r\n\r\nHello, World'
    ),
    (
        HttpResponse(400, HttpHeaders([
            HttpHeader(b'Server', b'BlackSheep'),
        ]), HttpContent(b'text/plain', b'Hello, World')),
        [HttpCookie(b'session', b'123')],
        b'HTTP/1.1 400 Bad Request\r\nServer: BlackSheep\r\nContent-Type: text/plain\r\nContent-Length: 12\r\nSet-Cookie: session=123\r\n\r\nHello, World'
    ),
    (
        HttpResponse(400, HttpHeaders([
            HttpHeader(b'Server', b'BlackSheep')
        ]), HttpContent(b'text/plain', b'Hello, World')),
        [HttpCookie(b'session', b'123'), HttpCookie(b'aaa', b'bbb', domain=b'bezkitu.org')],
        b'HTTP/1.1 400 Bad Request\r\nServer: BlackSheep\r\nContent-Type: text/plain\r\nContent-Length: 12\r\nSet-Cookie: session=123\r\nSet-Cookie: aaa=bbb; Domain=bezkitu.org\r\n\r\nHello, World'
    )
])
async def test_write_http_response(response, cookies, expected_result):
    response.set_cookies(cookies)
    data = b''
    async for chunk in scribe.write_response(response):
        data += chunk
    assert data == expected_result


def test_is_redirect():
    # 301 Moved Permanently
    # 302 Found
    # 303 See Other
    # 307 Temporary Redirect
    # 308 Permanent Redirect
    for status in range(200, 500):
        response = HttpResponse(status, HttpHeaders())
        is_redirect = status in {301, 302, 303, 307, 308}
        assert response.is_redirect() == is_redirect
