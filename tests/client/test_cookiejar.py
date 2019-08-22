import pytest
from datetime import datetime, timedelta
from blacksheep import (Request,
                        Response,
                        Headers,
                        Header,
                        Cookie,
                        URL,
                        TextContent,
                        datetime_to_cookie_format)
from blacksheep.client import ClientSession, CircularRedirectError, MaximumRedirectsExceededError
from blacksheep.client.cookies import CookieJar, InvalidCookie, InvalidCookieDomain, StoredCookie
from blacksheep.scribe import write_response_cookie
from . import FakePools


@pytest.mark.parametrize('request_url,cookie_domain,expected_domain', [
    [URL(b'https://bezkitu.org'), None, b'bezkitu.org'],
    [URL(b'https://foo.bezkitu.org'), b'foo.bezkitu.org', b'foo.bezkitu.org'],
    [URL(b'https://foo.bezkitu.org'), b'bezkitu.org', b'bezkitu.org'],
    [URL(b'https://foo.bezkitu.org'), b'bezkitu.org.', b'foo.bezkitu.org'],
])
def test_cookiejar_get_domain(request_url, cookie_domain, expected_domain):
    jar = CookieJar()
    cookie = Cookie(b'Name', b'Value', domain=cookie_domain)
    domain = jar.get_domain(request_url, cookie)
    assert domain == expected_domain


@pytest.mark.parametrize('request_url,cookie_domain', [
    [URL(b'https://bezkitu.org'), b'example.com'],
    [URL(b'https://foo.bezkitu.org'), b'baz.foo.bezkitu.org'],
    [URL(b'https://foo.bezkitu.org'), b'foo.org']
])
def test_cookiejar_invalid_domain(request_url, cookie_domain):
    jar = CookieJar()
    cookie = Cookie(b'Name', b'Value', domain=cookie_domain)

    with pytest.raises(InvalidCookieDomain):
        jar.add(request_url, cookie)


@pytest.mark.parametrize('cookie,expected_value', [
    [Cookie(b'name',
                b'value'),
     False],
    [Cookie(b'name',
                b'value',
                expires=datetime_to_cookie_format(datetime.utcnow() + timedelta(days=-20))),
     True]
])
def test_stored_cookie_is_expired(cookie, expected_value):
    stored = StoredCookie(cookie)
    expired = stored.is_expired()
    assert expected_value == expired


@pytest.mark.asyncio
async def test_cookies_jar_single_cookie():
    fake_pools = FakePools([Response(200,
                                     [(b'Set-Cookie', write_response_cookie(Cookie(b'X-Foo', b'Foo')))])
                           .with_content(TextContent('Hello, World!')),
                            Response(200, None, TextContent('Hello!'))])
    check_cookie = False

    async def middleware_for_assertions(request, next_handler):
        if check_cookie:
            cookie = request.cookies.get('X-Foo')
            assert cookie is not None, 'X-Foo cookie must be configured for following requests'

        return await next_handler(request)

    async with ClientSession(base_url=b'https://bezkitu.org',
                             pools=fake_pools,
                             middlewares=[middleware_for_assertions]) as client:
        await client.get(b'/')  # the first request doesn't have any cookie because the response will set;
        check_cookie = True
        await client.get(b'/')


@pytest.mark.asyncio
@pytest.mark.parametrize('first_request_url,second_request_url,set_cookies,expected_cookies', [
    [
        b'https://foo.bezkitu.org',
        b'https://bezkitu.org',
        [(b'Set-Cookie', write_response_cookie(Cookie(b'X-Foo', b'Foo', domain=b'bezkitu.org')))],
        ['X-Foo']
    ],
    [
        b'https://foo.bezkitu.org',
        b'https://foo.bezkitu.org',
        [(b'Set-Cookie', write_response_cookie(Cookie(b'X-Foo', b'Foo', domain=b'foo.bezkitu.org')))],
        ['X-Foo']
    ],
    [
        b'https://foo.bezkitu.org',
        b'https://bezkitu.org',
        [(b'Set-Cookie', write_response_cookie(Cookie(b'X-Foo', b'Foo', domain=b'foo.bezkitu.org')))],
        []
    ],
    [
        b'https://bezkitu.org',
        b'https://foo.org',
        [(b'Set-Cookie', write_response_cookie(Cookie(b'X-Foo', b'Foo', domain=b'bezkitu.org')))],
        []
    ]
])
async def test_cookies_jar(first_request_url, second_request_url, set_cookies, expected_cookies):
    fake_pools = FakePools([Response(200, set_cookies, TextContent('Hello, World!')),
                            Response(200, None, TextContent('Hello!'))])
    check_cookie = False

    async def middleware_for_assertions(request, next_handler):
        if check_cookie:
            if not expected_cookies:
                assert not request.cookies

            for expected_cookie in expected_cookies:
                cookie = request.cookies.get(expected_cookie)
                assert cookie is not None, f'{cookie.name.decode()} cookie must be configured for following requests'

        return await next_handler(request)

    async with ClientSession(pools=fake_pools,
                             middlewares=[middleware_for_assertions],
                             ) as client:
        await client.get(first_request_url)
        check_cookie = True
        await client.get(second_request_url)


@pytest.mark.asyncio
async def test_remove_cookie_with_expiration():
    expire_cookie = Cookie(b'X-Foo', b'Foo')
    expire_cookie.expiration = datetime.utcnow() + timedelta(days=-2)
    fake_pools = FakePools([Response(200, [(b'Set-Cookie', write_response_cookie(Cookie(b'X-Foo', b'Foo')))])
                           .with_content(TextContent('Hello, World!')),
                            Response(200, None, TextContent('Hello!')),
                            Response(200, [(b'Set-Cookie', write_response_cookie(expire_cookie))])
                           .with_content(TextContent('Hello, World!')),
                            Response(200, None, TextContent('Hello!'))])
    expect_cookie = False

    async def middleware_for_assertions(request, next_handler):
        cookie = request.cookies.get('X-Foo')
        if expect_cookie:
            assert cookie is not None, 'X-Foo cookie must be configured'
        else:
            assert cookie is None

        return await next_handler(request)

    async with ClientSession(base_url=b'https://bezkitu.org',
                             pools=fake_pools,
                             middlewares=[middleware_for_assertions]) as client:
        await client.get(b'/')  # <-- cookie set here
        expect_cookie = True
        await client.get(b'/')  # <-- expect cookie in request
        expect_cookie = True
        await client.get(b'/')  # <-- expect cookie in request; it gets removed here
        expect_cookie = False
        await client.get(b'/')  # <-- expect missing cookie; was deleted by previous response


@pytest.mark.asyncio
async def test_remove_cookie_with_max_age():
    expire_cookie = Cookie(b'X-Foo', b'Foo')
    expire_cookie.set_max_age(0)
    fake_pools = FakePools([Response(200,
                                     [(b'Set-Cookie', write_response_cookie(Cookie(b'X-Foo', b'Foo')))],
                                     TextContent('Hello, World!')),
                            Response(200,
                                     None,
                                     TextContent('Hello!')),
                            Response(200,
                                     [(b'Set-Cookie', write_response_cookie(expire_cookie))],
                                     TextContent('Hello, World!')),
                            Response(200,
                                     None,
                                     TextContent('Hello!'))])
    expect_cookie = False

    async def middleware_for_assertions(request, next_handler):
        cookie = request.cookies.get('X-Foo')
        if expect_cookie:
            assert cookie is not None, 'X-Foo cookie must be configured'
        else:
            assert cookie is None
        return await next_handler(request)

    async with ClientSession(base_url=b'https://bezkitu.org',
                             pools=fake_pools,
                             middlewares=[middleware_for_assertions]) as client:
        await client.get(b'/')  # <-- cookie set here
        expect_cookie = True
        await client.get(b'/')  # <-- expect cookie in request
        expect_cookie = True
        await client.get(b'/')  # <-- expect cookie in request; it gets removed here
        expect_cookie = False
        await client.get(b'/')  # <-- expect missing cookie; was deleted by previous response


def test_stored_cookie_max_age_precedence():
    cookie = Cookie(b'X-Foo', b'Foo')
    cookie.set_max_age(0)
    cookie.expiration = datetime.utcnow() + timedelta(days=2)

    stored_cookie = StoredCookie(cookie)
    assert stored_cookie.is_expired()


def test_get_cookies_for_url():
    jar = CookieJar()

    jar.add(URL(b'https://foo.org'), Cookie(b'hello', b'world'))

    cookies = list(jar.get_cookies_for_url(URL(b'https://foo.org/hello-world')))

    assert len(cookies) == 1
    assert cookies[0].name == b'hello'
    assert cookies[0].value == b'world'
