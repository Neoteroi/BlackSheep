import pytest
from blacksheep import Response, Content, Cookie
from blacksheep import scribe


def test_response_supports_dynamic_attributes():
    response = Response(200)
    foo = object()

    assert (
        hasattr(response, "response") is False
    ), "This test makes sense if such attribute is not defined"
    response.foo = foo
    assert response.foo is foo


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response,cookies,expected_result",
    [
        (
            Response(400, [(b"Server", b"BlackSheep")]).with_content(
                Content(b"text/plain", b"Hello, World")
            ),
            [],
            b"HTTP/1.1 400 Bad Request\r\n"
            b"Server: BlackSheep\r\n"
            b"content-type: text/plain\r\n"
            b"content-length: 12\r\n\r\nHello, World",
        ),
        (
            Response(400, [(b"Server", b"BlackSheep")]).with_content(
                Content(b"text/plain", b"Hello, World")
            ),
            [Cookie(b"session", b"123")],
            b"HTTP/1.1 400 Bad Request\r\n"
            b"Server: BlackSheep\r\n"
            b"set-cookie: session=123\r\n"
            b"content-type: text/plain\r\n"
            b"content-length: 12\r\n\r\nHello, World",
        ),
        (
            Response(400, [(b"Server", b"BlackSheep")]).with_content(
                Content(b"text/plain", b"Hello, World")
            ),
            [Cookie(b"session", b"123"), Cookie(b"aaa", b"bbb", domain=b"bezkitu.org")],
            b"HTTP/1.1 400 Bad Request\r\n"
            b"Server: BlackSheep\r\n"
            b"set-cookie: session=123\r\n"
            b"set-cookie: aaa=bbb; Domain=bezkitu.org\r\n"
            b"content-type: text/plain\r\n"
            b"content-length: 12\r\n\r\nHello, World",
        ),
    ],
)
async def test_write_http_response(response, cookies, expected_result):
    response.set_cookies(cookies)
    data = b""
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
        response = Response(status)
        is_redirect = status in {301, 302, 303, 307, 308}
        assert response.is_redirect() == is_redirect
