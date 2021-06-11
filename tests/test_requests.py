import pytest
from blacksheep import Content, Request, scribe
from blacksheep.contents import FormPart, MultiPartFormData
from blacksheep.exceptions import BadRequestFormat
from blacksheep.scribe import write_small_request
from blacksheep.server.asgi import get_request_url
from blacksheep.url import URL


from blacksheep.testing.helpers import get_example_scope


def test_request_supports_dynamic_attributes():
    request = Request("GET", b"/", None)
    foo = object()

    assert (
        hasattr(request, "foo") is False
    ), "This test makes sense if such attribute is not defined"
    request.foo = foo  # type: ignore
    assert request.foo is foo  # type: ignore


@pytest.mark.asyncio
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


@pytest.mark.asyncio
async def test_can_read_json_data_even_without_content_type_header():
    request = Request("POST", b"/", None)

    request.with_content(Content(b"application/json", b'{"hello":"world","foo":false}'))

    json = await request.json()
    assert json == {"hello": "world", "foo": False}


@pytest.mark.asyncio
async def test_if_read_json_fails_content_type_header_is_checked_json_gives_bad_request_format():
    request = Request("POST", b"/", [(b"Content-Type", b"application/json")])

    request.with_content(Content(b"application/json", b'{"hello":'))  # broken json

    with pytest.raises(BadRequestFormat):
        await request.json()


@pytest.mark.asyncio
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
    request = Request.incoming(
        scope["method"], scope["raw_path"], scope["query_string"], scope["headers"]
    )
    request.scope = scope

    full_url = get_request_url(request)
    assert full_url == expected_value


def test_request_pyi():
    request = Request("GET", b"/", [(b"cookie", b"foo=aaa")])

    request.cookies["foo"] == "aaa"
    request.get_cookie("foo") == "aaa"
    request.get_first_header(b"cookie") == b"foo=aaa"

    request.set_cookie("lorem", "ipsum")
    request.get_cookie("lorem") == "ipsum"
