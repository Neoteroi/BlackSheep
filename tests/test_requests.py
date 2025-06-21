import pytest

from blacksheep import Content, Request, scribe
from blacksheep.contents import FormPart, MultiPartFormData, StreamedContent
from blacksheep.exceptions import BadRequestFormat
from blacksheep.messages import get_absolute_url_to_path, get_request_absolute_url
from blacksheep.scribe import write_request, write_small_request
from blacksheep.server.asgi import (
    get_request_url,
    get_request_url_from_scope,
    incoming_request,
)
from blacksheep.testing.helpers import get_example_scope
from blacksheep.url import URL


def test_request_supports_dynamic_attributes():
    request = Request("GET", b"/", None)
    foo = object()

    assert (
        hasattr(request, "foo") is False
    ), "This test makes sense if such attribute is not defined"
    request.foo = foo  # type: ignore
    assert request.foo is foo  # type: ignore


@pytest.mark.parametrize(
    "url,method,headers,content,expected_result",
    [
        (
            b"https://robertoprevato.github.io",
            "GET",
            [],
            None,
            b"GET / HTTP/1.1\r\nhost: robertoprevato.github.io\r\ncontent-length: 0\r\n\r\n",
        ),
        (
            b"https://robertoprevato.github.io",
            "HEAD",
            [],
            None,
            b"HEAD / HTTP/1.1\r\nhost: robertoprevato.github.io\r\ncontent-length: 0\r\n\r\n",
        ),
        (
            b"https://robertoprevato.github.io",
            "POST",
            [],
            None,
            b"POST / HTTP/1.1\r\nhost: robertoprevato.github.io\r\ncontent-length: 0\r\n\r\n",
        ),
        (
            b"https://robertoprevato.github.io/How-I-created-my-own-media-storage-in-Azure/",
            "GET",
            [],
            None,
            b"GET /How-I-created-my-own-media-storage-in-Azure/ HTTP/1.1\r\nhost: robertoprevato.github.io"
            b"\r\ncontent-length: 0\r\n\r\n",
        ),
        (
            b"https://foo.org/a/b/c/?foo=1&ufo=0",
            "GET",
            [],
            None,
            b"GET /a/b/c/?foo=1&ufo=0 HTTP/1.1\r\nhost: foo.org\r\ncontent-length: 0\r\n\r\n",
        ),
        (
            b"https://foo.org/a/b/c/",
            "PROPFIND",  # Issue #517
            [],
            None,
            b"PROPFIND /a/b/c/ HTTP/1.1\r\nhost: foo.org\r\ncontent-length: 0\r\n\r\n",
        ),
        (
            b"https://foo.org/a/b/c/",
            "UNLOCK",  # Issue #517
            [],
            None,
            b"UNLOCK /a/b/c/ HTTP/1.1\r\nhost: foo.org\r\ncontent-length: 0\r\n\r\n",
        ),
    ],
)
async def test_request_writing(url, method, headers, content, expected_result):
    request = Request(method, url, headers).with_content(content)
    data = b""
    async for chunk in scribe.write_request(request):
        data += chunk
    assert data == expected_result


@pytest.mark.parametrize(
    "url,query,parsed_query",
    [
        (b"https://foo.org/a/b/c?hello=world", b"hello=world", {"hello": ["world"]}),
        (
            b"https://foo.org/a/b/c?hello=world&foo=power",
            b"hello=world&foo=power",
            {"hello": ["world"], "foo": ["power"]},
        ),
        (
            b"https://foo.org/a/b/c?hello=world&foo=power&foo=200",
            b"hello=world&foo=power&foo=200",
            {"hello": ["world"], "foo": ["power", "200"]},
        ),
    ],
)
def test_parse_query(url, query, parsed_query):
    request = Request("GET", url, None)
    assert request.url.value == url
    assert request.url.query == query
    assert request.query == parsed_query


async def test_can_read_json_data_even_without_content_type_header():
    request = Request("POST", b"/", None)

    request.with_content(Content(b"application/json", b'{"hello":"world","foo":false}'))

    json = await request.json()
    assert json == {"hello": "world", "foo": False}


async def test_if_read_json_fails_content_type_header_is_checked_json_gives_bad_request_format():
    request = Request("POST", b"/", [(b"Content-Type", b"application/json")])

    request.with_content(Content(b"application/json", b'{"hello":'))  # broken json

    with pytest.raises(BadRequestFormat):
        await request.json()


async def test_if_read_json_fails_content_type_header_is_checked_non_json_gives_invalid_operation():
    request = Request("POST", b"/", [])

    request.with_content(
        Content(b"application/json", b'{"hello":')
    )  # broken json; broken content-type

    with pytest.raises(BadRequestFormat):
        await request.json()


def test_cookie_parsing():
    request = Request(
        "POST", b"/", [(b"Cookie", b"ai=something; hello=world; foo=Hello%20World%3B;")]
    )

    assert request.cookies == {
        "ai": "something",
        "hello": "world",
        "foo": "Hello World;",
    }


def test_cookie_parsing_multiple_cookie_headers():
    request = Request(
        "POST",
        b"/",
        [
            (b"Cookie", b"ai=something; hello=world; foo=Hello%20World%3B;"),
            (b"Cookie", b"jib=jab; ai=else;"),
        ],
    )

    assert request.cookies == {
        "ai": "else",
        "hello": "world",
        "foo": "Hello World;",
        "jib": "jab",
    }


def test_cookie_parsing_duplicated_cookie_header_value():
    request = Request(
        "POST",
        b"/",
        [(b"Cookie", b"ai=something; hello=world; foo=Hello%20World%3B; hello=kitty;")],
    )

    assert request.cookies == {
        "ai": "something",
        "hello": "kitty",
        "foo": "Hello World;",
    }


@pytest.mark.parametrize(
    "header,expected_result",
    [
        [(b"Expect", b"100-Continue"), True],
        [(b"expect", b"100-continue"), True],
        [(b"X-Foo", b"foo"), False],
    ],
)
def test_request_expect_100_continue(header, expected_result):
    request = Request("POST", b"/", [header])
    assert expected_result == request.expect_100_continue()


@pytest.mark.parametrize(
    "headers,expected_result",
    [
        [[(b"Content-Type", b"application/json")], True],
        [[(b"Content-Type", b"application/problem+json")], True],
        [[(b"Content-Type", b"application/json; charset=utf-8")], True],
        [[], False],
        [[(b"Content-Type", b"application/xml")], False],
    ],
)
def test_request_declares_json(headers, expected_result):
    request = Request("GET", b"/", headers)
    assert request.declares_json() is expected_result


def test_small_request_headers_add_through_higher_api():
    request = Request("GET", b"https://hello-world", None)

    request.headers.add(b"Hello", b"World")

    raw_bytes = write_small_request(request)

    assert b"Hello: World\r\n" in raw_bytes


def test_small_request_headers_add_through_higher_api_many():
    request = Request("GET", b"https://hello-world", None)

    request.headers.add_many({b"Hello": b"World", b"X-Foo": b"Foo"})

    raw_bytes = write_small_request(request)

    assert b"Hello: World\r\n" in raw_bytes
    assert b"X-Foo: Foo\r\n" in raw_bytes


def test_small_request_headers_add_through_lower_api():
    request = Request("GET", b"https://hello-world", None)

    request.add_header(b"Hello", b"World")

    raw_bytes = write_small_request(request)

    assert b"Hello: World\r\n" in raw_bytes


@pytest.mark.parametrize(
    "initial_url,new_url",
    [
        (b"https://hello-world/", b"https://ciao-mondo/"),
        (b"https://hello-world/one/two/three", b"https://hello-world/one/two/three/"),
        (b"https://hello-world/one/two/three/", b"https://hello-world/one/two/three"),
    ],
)
def test_request_can_update_url(initial_url, new_url):
    request = Request("GET", initial_url, None)

    assert request.url.value == initial_url

    request.url = URL(new_url)

    assert request.url.value == new_url


def test_request_content_type_is_read_from_content():
    request = Request("POST", b"/", []).with_content(
        MultiPartFormData([FormPart(b"a", b"world"), FormPart(b"b", b"9000")])
    )

    assert request.content is not None
    assert request.content_type() == request.content.type


@pytest.mark.parametrize(
    "scope,expected_value",
    [
        (
            get_example_scope("GET", "/foo", scheme="http", server=["127.0.0.1", 8000]),
            "http://127.0.0.1:8000/foo",
        ),
        (
            get_example_scope("GET", "/foo", scheme="http", server=["127.0.0.1", 80]),
            "http://127.0.0.1/foo",
        ),
        (
            get_example_scope(
                "GET", "/foo", scheme="https", server=["127.0.0.1", 44777]
            ),
            "https://127.0.0.1:44777/foo",
        ),
        (
            get_example_scope("GET", "/foo", scheme="https", server=["127.0.0.1", 443]),
            "https://127.0.0.1/foo",
        ),
    ],
)
def test_get_asgi_request_full_url(scope, expected_value):
    request = incoming_request(scope, None)

    full_url = get_request_url(request)
    assert full_url == expected_value


def test_request_pyi():
    request = Request("GET", b"/", [(b"cookie", b"foo=aaa")])

    request.cookies["foo"] == "aaa"
    request.get_cookie("foo") == "aaa"
    request.get_first_header(b"cookie") == b"foo=aaa"

    request.set_cookie("lorem", "ipsum")
    request.get_cookie("lorem") == "ipsum"


@pytest.mark.parametrize(
    "scope,trailing_slash,expected_value",
    [
        [
            {
                "scheme": "https",
                "path": "/",
                "server": ("www.neoteroi.dev", 443),
                "headers": [],
            },
            False,
            "https://www.neoteroi.dev/",
        ],
        [
            {
                "scheme": "https",
                "path": "/admin",
                "server": ("www.neoteroi.dev", 443),
                "headers": [],
            },
            False,
            "https://www.neoteroi.dev/admin",
        ],
        [
            {
                "scheme": "https",
                "path": "/admin",
                "server": ("www.neoteroi.dev", 443),
                "headers": [],
            },
            True,
            "https://www.neoteroi.dev/admin/",
        ],
        [
            {
                "scheme": "https",
                "path": "/admin",
                "server": ("www.neoteroi.dev", 44777),
                "headers": [],
            },
            True,
            "https://www.neoteroi.dev:44777/admin/",
        ],
        [
            {
                "scheme": "http",
                "path": "/admin",
                "server": ("www.neoteroi.dev", 44777),
                "headers": [],
            },
            True,
            "http://www.neoteroi.dev:44777/admin/",
        ],
        [
            {
                "scheme": "http",
                "path": "/admin",
                "server": ("www.neoteroi.dev", 80),
                "headers": [],
            },
            True,
            "http://www.neoteroi.dev/admin/",
        ],
        [
            {
                "scheme": "http",
                "path": "/admin",
                "server": ("www.neoteroi.dev", 80),
                "query_string": b"foo=Hello%20World%20%C3%B8",
                "headers": [],
            },
            False,
            "http://www.neoteroi.dev/admin?foo=Hello%20World%20%C3%B8",
        ],
    ],
)
def test_get_request_url_from_scope(scope, trailing_slash, expected_value):
    result = get_request_url_from_scope(scope, trailing_slash=trailing_slash)
    assert result == expected_value


def test_get_request_url_from_scope_raises_for_invalid_scope():
    with pytest.raises(ValueError):
        get_request_url_from_scope({})


@pytest.mark.parametrize(
    "scope,expected_value",
    [
        (
            get_example_scope("GET", "/foo", scheme="http", server=["127.0.0.1", 8000]),
            "http://127.0.0.1:8000/foo",
        ),
        (
            get_example_scope("GET", "/foo", scheme="http", server=["127.0.0.1", 80]),
            "http://127.0.0.1/foo",
        ),
        (
            get_example_scope(
                "GET", "/foo", scheme="https", server=["127.0.0.1", 44777]
            ),
            "https://127.0.0.1:44777/foo",
        ),
        (
            get_example_scope("GET", "/foo", scheme="https", server=["127.0.0.1", 443]),
            "https://127.0.0.1/foo",
        ),
    ],
)
def test_get_request_absolute_url(scope, expected_value):
    request = incoming_request(scope)

    assert request.scheme == scope["scheme"]
    assert request.host == dict(scope["headers"])[b"host"].decode()
    assert request.base_path == ""

    absolute_url = get_request_absolute_url(request)
    assert str(absolute_url) == f"{request.scheme}://{request.host}{request.path}"
    assert str(absolute_url) == expected_value


@pytest.mark.parametrize(
    "scope,base_path,expected_value",
    [
        (
            get_example_scope("GET", "/foo", scheme="http", server=["127.0.0.1", 8000]),
            "/api",
            "http://127.0.0.1:8000/api/foo",
        ),
        (
            get_example_scope("GET", "/foo", scheme="http", server=["127.0.0.1", 80]),
            "/api/",
            "http://127.0.0.1/api/foo",
        ),
        (
            get_example_scope(
                "GET", "/foo", scheme="https", server=["127.0.0.1", 44777]
            ),
            "/api/oof",
            "https://127.0.0.1:44777/api/oof/foo",
        ),
        (
            get_example_scope("GET", "/foo", scheme="https", server=["127.0.0.1", 443]),
            "/api/oof/",
            "https://127.0.0.1/api/oof/foo",
        ),
    ],
)
def test_get_request_absolute_url_with_base_path(scope, base_path, expected_value):
    request = incoming_request(scope)

    assert request.scheme == scope["scheme"]
    assert request.host == dict(scope["headers"])[b"host"].decode()
    request.base_path = base_path

    absolute_url = get_request_absolute_url(request)
    assert str(absolute_url) == expected_value


@pytest.mark.parametrize(
    "scope,path,expected_result",
    [
        (
            get_example_scope("GET", "/foo", scheme="http", server=["127.0.0.1", 8000]),
            "/sign-in",
            "http://127.0.0.1:8000/sign-in",
        ),
        (
            get_example_scope("GET", "/", scheme="http", server=["127.0.0.1", 8000]),
            "/authorization/callback",
            "http://127.0.0.1:8000/authorization/callback",
        ),
        (
            get_example_scope(
                "GET", "/a/b/c/", scheme="http", server=["127.0.0.1", 8000]
            ),
            "/authorization/callback",
            "http://127.0.0.1:8000/authorization/callback",
        ),
    ],
)
def test_get_request_absolute_url_to_path(scope, path, expected_result):
    request = incoming_request(scope)
    url_to = get_absolute_url_to_path(request, path)

    assert str(url_to) == expected_result


def test_can_set_request_host_and_scheme():
    scope = get_example_scope(
        "GET", "/blacksheep/", scheme="http", server=["127.0.0.1", 80]
    )
    request = incoming_request(scope)

    request.scheme = "https"
    request.host = "neoteroi.dev"

    absolute_url = get_request_absolute_url(request)
    assert str(absolute_url) == "https://neoteroi.dev/blacksheep/"


def test_can_set_request_client_ip():
    scope = get_example_scope(
        "GET", "/blacksheep/", scheme="http", server=["127.0.0.1", 80]
    )
    request = incoming_request(scope)

    request.client_ip == scope["client"][0]

    assert request.original_client_ip == "127.0.0.1"

    # can set (e.g. when handling forwarded headers)
    request.original_client_ip = "185.152.122.103"

    assert request.original_client_ip == "185.152.122.103"
    assert scope["client"] == ("127.0.0.1", 51492)


def test_updating_request_url_read_host():
    request = Request("GET", b"https://www.neoteroi.dev/blacksheep", [])

    assert request.path == "/blacksheep"
    assert request.host == "www.neoteroi.dev"

    request.url = "https://github.com/RobertoPrevato"

    assert request.path == "/RobertoPrevato"
    assert request.host == "github.com"


async def test_updating_request_host_in_headers():
    request = Request("GET", b"https://www.neoteroi.dev/blacksheep", [])

    assert request.path == "/blacksheep"
    assert request.host == "www.neoteroi.dev"
    assert request.headers[b"host"] == tuple()

    async for _ in write_request(request):
        pass

    assert request.headers[b"host"] == (b"www.neoteroi.dev",)
    request.url = "https://github.com/RobertoPrevato"

    assert request.headers[b"host"] == tuple()

    async for _ in write_request(request):
        pass

    assert request.headers[b"host"] == (b"github.com",)


async def test_write_request_cookies():
    request = Request("GET", b"https://www.neoteroi.dev/blacksheep", [])

    request.set_cookie("example_1", "one")
    request.set_cookie("example_2", "two")

    expected_bytes = b"""GET /blacksheep HTTP/1.1
cookie: example_1=one;example_2=two
host: www.neoteroi.dev
content-length: 0

""".replace(
        b"\n", b"\r\n"
    )

    value = bytearray()

    async for chunk in write_request(request):
        value.extend(chunk)

    assert bytes(value) == expected_bytes


def test_scope_root_path():
    request = Request("GET", b"/", [])
    assert request.base_path == ""

    request.base_path = "/app"
    assert request.base_path == "/app"

    request = Request("GET", b"/", [])
    request.scope = {"root_path": "/app"}  # type: ignore

    assert request.base_path == "/app"

    request.base_path = "/app2"
    assert request.base_path == "/app2"


async def test_write_small_request_streamed():
    async def content_gen():
        yield b"Hello"
        yield b"World"

    request = Request("POST", b"/", []).with_content(
        StreamedContent(b"text/plain", content_gen)
    )

    data = bytearray()
    async for chunk in write_request(request):
        data.extend(chunk)
    assert (
        bytes(data)
        == b"""POST / HTTP/1.1\r\ncontent-type: text/plain\r\ntransfer-encoding: chunked\r\n\r\n5\r\nHello\r\n5\r\nWorld\r\n0\r\n\r\n"""
    )


async def test_write_small_request_streamed_fixed_length():
    async def content_gen():
        yield b"Hello"
        yield b"World"

    request = Request("POST", b"/", []).with_content(
        StreamedContent(b"text/plain", content_gen, len("HelloWorld"))
    )

    data = bytearray()
    async for chunk in write_request(request):
        data.extend(chunk)
    assert (
        bytes(data)
        == b"POST / HTTP/1.1\r\ncontent-type: text/plain\r\ncontent-length: 10\r\n\r\nHelloWorld"
    )


@pytest.mark.parametrize(
    "content_type_header,expected_charset",
    [
        ("text/plain; charset=UTF-8", "UTF-8"),
        ("application/json", "utf8"),  # default
        ("application/json; charset=utf-8", "utf-8"),
        ("application/json; charset=ISO-8859-1", "ISO-8859-1"),
        ("text/html; charset=ISO-8859-1", "ISO-8859-1"),
        ("application/xml; charset=utf-8", "utf-8"),
    ],
)
def test_request_charset(content_type_header, expected_charset):
    request = Request("POST", b"/", [(b"Content-Type", content_type_header.encode())])
    assert request.charset == expected_charset
