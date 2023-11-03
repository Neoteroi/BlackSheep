from datetime import timedelta

import pytest

from blacksheep import URL, Cookie, Response, TextContent
from blacksheep.client import ClientSession
from blacksheep.client.cookies import (
    CookieJar,
    InvalidCookieDomain,
    MissingSchemeInURL,
    StoredCookie,
)
from blacksheep.cookies import datetime_from_cookie_format
from blacksheep.scribe import write_response_cookie
from blacksheep.utils.time import utcnow

from . import FakePools


@pytest.mark.parametrize(
    "request_url,cookie_domain,expected_domain",
    [
        [URL(b"https://bezkitu.org"), None, "bezkitu.org"],
        [URL(b"https://foo.bezkitu.org"), "foo.bezkitu.org", "foo.bezkitu.org"],
        [URL(b"https://foo.bezkitu.org"), "bezkitu.org", "bezkitu.org"],
        [URL(b"https://foo.bezkitu.org"), "bezkitu.org.", "foo.bezkitu.org"],
    ],
)
def test_cookiejar_get_domain(request_url, cookie_domain, expected_domain):
    jar = CookieJar()
    cookie = Cookie("Name", "Value", domain=cookie_domain)
    domain = jar.get_domain(request_url, cookie)
    assert domain == expected_domain


@pytest.mark.parametrize(
    "request_url,cookie_domain",
    [
        [URL(b"https://bezkitu.org"), "example.com"],
        [URL(b"https://foo.bezkitu.org"), "baz.foo.bezkitu.org"],
        [URL(b"https://foo.bezkitu.org"), "foo.org"],
    ],
)
def test_cookiejar_invalid_domain(request_url, cookie_domain):
    jar = CookieJar()
    cookie = Cookie("Name", "Value", domain=cookie_domain)

    with pytest.raises(InvalidCookieDomain):
        jar.add(request_url, cookie)


@pytest.mark.parametrize(
    "cookie,expected_value",
    [
        [Cookie("name", "value"), False],
        [
            Cookie("name", "value", expires=utcnow() + timedelta(days=-20)),
            True,
        ],
    ],
)
def test_stored_cookie_is_expired(cookie, expected_value):
    stored = StoredCookie(cookie)
    expired = stored.is_expired()
    assert expected_value == expired


def test_stored_cookie_handles_max_age_value_error():
    stored = StoredCookie(
        Cookie(
            "name",
            "value",
            max_age=-20,
        )
    )
    assert stored.expiry_time is None


def test_stored_cookie_handles_max_age():
    stored = StoredCookie(
        Cookie(
            "name",
            "value",
            max_age=20,
        )
    )
    assert stored.expiry_time is not None


def test_cookie_jar_throws_for_url_without_host():
    jar = CookieJar()

    with pytest.raises(MissingSchemeInURL):
        jar.get_cookies_for_url(URL(b"/"))


@pytest.mark.asyncio
async def test_cookies_jar_single_cookie():
    fake_pools = FakePools(
        [
            Response(
                200, [(b"Set-Cookie", write_response_cookie(Cookie("X-Foo", "Foo")))]
            ).with_content(TextContent("Hello, World!")),
            Response(200, None, TextContent("Hello!")),
        ]
    )
    check_cookie = False

    async def middleware_for_assertions(request, next_handler):
        if check_cookie:
            cookie = request.cookies.get("X-Foo")
            assert (
                cookie is not None
            ), "X-Foo cookie must be configured for following requests"

        return await next_handler(request)

    async with ClientSession(
        base_url=b"https://bezkitu.org",
        pools=fake_pools,
        middlewares=[middleware_for_assertions],
    ) as client:
        await client.get(
            b"/"
        )  # the first request doesn't have any cookie because the response will set;
        check_cookie = True
        await client.get(b"/")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "first_request_url,second_request_url,set_cookies,expected_cookies",
    [
        [
            b"https://ufo.foo.bezkitu.org",
            b"https://bezkitu.org",
            [
                (
                    b"Set-Cookie",
                    write_response_cookie(Cookie("X-Foo", "Foo", domain="bezkitu.org")),
                )
            ],
            ["X-Foo"],
        ],
        [
            b"https://ufo.foo.bezkitu.org",
            b"https://foo.bezkitu.org",
            [
                (
                    b"Set-Cookie",
                    write_response_cookie(Cookie("X-Foo", "Foo", domain="bezkitu.org")),
                )
            ],
            ["X-Foo"],
        ],
        [
            b"https://ufo.foo.bezkitu.org",
            b"https://foo.bezkitu.org",
            [
                (
                    b"Set-Cookie",
                    write_response_cookie(
                        Cookie("X-Foo", "Foo", domain="foo.bezkitu.org")
                    ),
                )
            ],
            ["X-Foo"],
        ],
        [
            b"https://foo.bezkitu.org",
            b"https://bezkitu.org",
            [
                (
                    b"Set-Cookie",
                    write_response_cookie(Cookie("X-Foo", "Foo", domain="bezkitu.org")),
                )
            ],
            ["X-Foo"],
        ],
        [
            b"https://foo.bezkitu.org",
            b"https://foo.bezkitu.org",
            [
                (
                    b"Set-Cookie",
                    write_response_cookie(
                        Cookie("X-Foo", "Foo", domain="foo.bezkitu.org")
                    ),
                )
            ],
            ["X-Foo"],
        ],
        [
            b"https://foo.bezkitu.org",
            b"https://foo.bezkitu.org",
            [
                (
                    b"Set-Cookie",
                    write_response_cookie(
                        Cookie("X-Foo", "Foo", domain="foo.bezkitu.org")
                    ),
                ),
                (
                    b"Set-Cookie",
                    write_response_cookie(
                        Cookie("X-Not-Valid", "Foo", domain="notvalid.org")
                    ),  # tests not valid cookie (invalid domain)
                ),
            ],
            ["X-Foo"],
        ],
        [
            b"https://foo.bezkitu.org",
            b"https://bezkitu.org",
            [
                (
                    b"Set-Cookie",
                    write_response_cookie(
                        Cookie("X-Foo", "Foo", domain="foo.bezkitu.org")
                    ),
                )
            ],
            [],
        ],
        [
            b"https://bezkitu.org",
            b"https://foo.org",
            [
                (
                    b"Set-Cookie",
                    write_response_cookie(Cookie("X-Foo", "Foo", domain="bezkitu.org")),
                )
            ],
            [],
        ],
        [
            b"https://some-example.org",
            b"https://example.org",
            [
                (
                    b"Set-Cookie",
                    write_response_cookie(
                        Cookie("X-Foo", "Foo", domain="some-example.org")
                    ),
                )
            ],
            [],
        ],
        [
            b"https://example.org",
            b"https://some-example.org",
            [
                (
                    b"Set-Cookie",
                    write_response_cookie(Cookie("X-Foo", "Foo", domain="example.org")),
                )
            ],
            [],
        ],
    ],
)
async def test_cookies_jar(
    first_request_url, second_request_url, set_cookies, expected_cookies
):
    fake_pools = FakePools(
        [
            Response(200, set_cookies, TextContent("Hello, World!")),
            Response(200, None, TextContent("Hello!")),
        ]
    )
    check_cookie = False

    async def middleware_for_assertions(request, next_handler):
        if check_cookie:
            if not expected_cookies:
                assert not request.cookies

            for expected_cookie in expected_cookies:
                cookie = request.cookies.get(expected_cookie)
                assert (
                    cookie is not None
                ), f"{expected_cookie} cookie must be configured for following requests"

        return await next_handler(request)

    async with ClientSession(
        pools=fake_pools,
        middlewares=[middleware_for_assertions],
    ) as client:
        await client.get(first_request_url)
        check_cookie = True
        await client.get(second_request_url)


@pytest.mark.asyncio
async def test_remove_cookie_with_expiration():
    expire_cookie = Cookie("X-Foo", "Foo")
    expire_cookie.expires = utcnow() + timedelta(days=-2)
    fake_pools = FakePools(
        [
            Response(
                200, [(b"Set-Cookie", write_response_cookie(Cookie("X-Foo", "Foo")))]
            ).with_content(TextContent("Hello, World!")),
            Response(200, None, TextContent("Hello!")),
            Response(
                200, [(b"Set-Cookie", write_response_cookie(expire_cookie))]
            ).with_content(TextContent("Hello, World!")),
            Response(200, None, TextContent("Hello!")),
        ]
    )
    expect_cookie = False

    async def middleware_for_assertions(request, next_handler):
        cookie = request.cookies.get("X-Foo")
        if expect_cookie:
            assert cookie is not None, "X-Foo cookie must be configured"
        else:
            assert cookie is None

        return await next_handler(request)

    async with ClientSession(
        base_url=b"https://bezkitu.org",
        pools=fake_pools,
        middlewares=[middleware_for_assertions],
    ) as client:
        await client.get(b"/")  # <-- cookie set here
        expect_cookie = True
        await client.get(b"/")  # <-- expect cookie in request
        expect_cookie = True
        await client.get(b"/")  # <-- expect cookie in request; it gets removed here
        expect_cookie = False
        await client.get(
            b"/"
        )  # <-- expect missing cookie; was deleted by previous response


@pytest.mark.asyncio
async def test_remove_cookie_with_max_age():
    expire_cookie = Cookie("X-Foo", "Foo")
    expire_cookie.max_age = 0
    fake_pools = FakePools(
        [
            Response(
                200,
                [(b"Set-Cookie", write_response_cookie(Cookie("X-Foo", "Foo")))],
                TextContent("Hello, World!"),
            ),
            Response(200, None, TextContent("Hello!")),
            Response(
                200,
                [(b"Set-Cookie", write_response_cookie(expire_cookie))],
                TextContent("Hello, World!"),
            ),
            Response(200, None, TextContent("Hello!")),
        ]
    )
    expect_cookie = False

    async def middleware_for_assertions(request, next_handler):
        cookie = request.cookies.get("X-Foo")
        if expect_cookie:
            assert cookie is not None, "X-Foo cookie must be configured"
        else:
            assert cookie is None
        return await next_handler(request)

    async with ClientSession(
        base_url=b"https://bezkitu.org",
        pools=fake_pools,
        middlewares=[middleware_for_assertions],
    ) as client:
        await client.get(b"/")  # <-- cookie set here
        expect_cookie = True
        await client.get(b"/")  # <-- expect cookie in request
        expect_cookie = True
        await client.get(b"/")  # <-- expect cookie in request; it gets removed here
        expect_cookie = False
        await client.get(
            b"/"
        )  # <-- expect missing cookie; was deleted by previous response


def test_stored_cookie_max_age_precedence():
    cookie = Cookie("X-Foo", "Foo")
    cookie.max_age = 0
    cookie.expires = utcnow() + timedelta(days=2)

    stored_cookie = StoredCookie(cookie)
    assert stored_cookie.is_expired()


def test_get_cookies_for_url():
    jar = CookieJar()

    jar.add(URL(b"https://foo.org"), Cookie("hello", "world"))

    cookies = list(jar.get_cookies_for_url(URL(b"https://foo.org/hello-world")))

    assert len(cookies) == 1
    assert cookies[0].name == "hello"
    assert cookies[0].value == "world"


def test_get_cookies_for_url_ignores_secure_cookies_for_http():
    jar = CookieJar()

    jar.add(URL(b"https://foo.org"), Cookie("hello", "world", secure=True))

    cookies = list(jar.get_cookies_for_url(URL(b"http://foo.org/hello-world")))
    assert len(cookies) == 0


@pytest.mark.parametrize(
    "domain,value,is_match",
    [
        ("x.y.z.com", "x.y.z.com", True),
        ("y.z.com", "x.y.z.com", True),
        ("z.com", "x.y.z.com", True),
        ("x.y.z.com", "y.z.com", False),
        ("x.y.z.com", "z.com", False),
        ("x.y.z.com", ".com", False),
        ("x.y.z.com", "com", False),
    ],
)
def test_cookie_domain_match(domain: str, value: str, is_match: bool):
    assert (
        CookieJar.domain_match(domain, value) is is_match
    ), f"{domain} {value} != {is_match}"


@pytest.mark.parametrize(
    "request_path,cookie_path,is_match",
    [
        ("/", "/", True),
        ("/foo", "/foo", True),
        ("/foo/foo", "/foo/foo", True),
        ("/foo/foo", "/foo", True),
        ("/foo", "/foo/foo", False),
        ("/ufo", "/foo", False),
        ("/foo", "/foo/foo", False),
    ],
)
def test_cookie_path_match(request_path: str, cookie_path: str, is_match: bool):
    assert (
        CookieJar.path_match(request_path, cookie_path) is is_match
    ), f"{request_path.decode()} {cookie_path.decode()} != {is_match}"


def test_cookiejar_ignores_cookie_domain_set_as_ipaddress():
    jar = CookieJar()

    assert (
        jar.get_domain(
            URL(b"https://foo.org/hello-world"),
            Cookie("foo", "foo", domain="192.168.1.5"),
        )
        == "foo.org"
    )


@pytest.mark.parametrize(
    "value,expected_result",
    [
        (b"/", "/"),
        (b"/foo", "/"),
        (b"/hello/world", "/hello"),
        (b"/hello/world/super", "/hello/world"),
    ],
)
def test_cookie_jar_get_cookie_default_path(value, expected_result):
    assert CookieJar.get_cookie_default_path(URL(value)) == expected_result


def test_cookie_jar_check_cookies_removes_expired():
    jar = CookieJar()

    # simulate an expired cookie that gets removed
    jar._domain_cookies

    jar._host_only_cookies = {
        "foo.org": {
            "/": {
                "hello": StoredCookie(
                    Cookie(
                        "hello",
                        "world",
                        expires=datetime_from_cookie_format(
                            b"Fri, 17 Aug 2018 20:55:04 GMT"
                        ),
                    )
                )
            }
        }
    }

    list(jar._get_cookies_checking_exp("https", jar._host_only_cookies["foo.org"]["/"]))
    assert jar.get("foo.org", "/", "hello") is None


def test_cookie_jar_does_not_override_http_only_cookie_with_non_http_only_cookie():
    jar = CookieJar()

    jar.add(
        URL(b"https://foo.org"),
        Cookie(
            "hello",
            "world",
            expires=utcnow() + timedelta(days=2),
            http_only=True,
        ),
    )

    jar.add(
        URL(b"https://foo.org"),
        Cookie(
            "hello",
            "world2",
            expires=utcnow() + timedelta(days=2),
            http_only=True,
        ),
    )

    cookie = jar.get("foo.org", "/", "hello")
    assert cookie is not None
    assert cookie.cookie.value == "world2"

    jar.add(
        URL(b"https://foo.org"),
        Cookie(
            "hello",
            "world modified",
            expires=utcnow() + timedelta(days=2),
            http_only=False,
        ),
    )

    cookie = jar.get("foo.org", "/", "hello")
    assert cookie is not None
    assert cookie.cookie.value == "world2"


def test_cookie_jar_remove_does_not_throw_key_error():
    jar = CookieJar()

    assert jar.remove("foo", "foo", "foo") is False
