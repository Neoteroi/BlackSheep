import pytest
from blacksheep import Request, Headers, Header
from blacksheep import scribe
from blacksheep.exceptions import BadRequestFormat, InvalidOperation


def test_request_supports_dynamic_attributes():
    request = Request(b'GET', b'/', Headers(), None)
    foo = object()

    assert hasattr(request, 'foo') is False, 'This test makes sense if such attribute is not defined'
    request.foo = foo
    assert request.foo is foo


@pytest.mark.asyncio
@pytest.mark.parametrize('url,method,headers,content,expected_result', [
    (b'https://robertoprevato.github.io', b'GET', [], None,
     b'GET / HTTP/1.1\r\nHost: robertoprevato.github.io\r\n\r\n'),
    (b'https://robertoprevato.github.io', b'HEAD', [], None,
     b'HEAD / HTTP/1.1\r\nHost: robertoprevato.github.io\r\n\r\n'),
    (b'https://robertoprevato.github.io', b'POST', [], None,
     b'POST / HTTP/1.1\r\nHost: robertoprevato.github.io\r\n\r\n'),
    (b'https://robertoprevato.github.io/How-I-created-my-own-media-storage-in-Azure/', b'GET', [], None,
     b'GET /How-I-created-my-own-media-storage-in-Azure/ HTTP/1.1\r\nHost: robertoprevato.github.io\r\n\r\n'),
    (b'https://foo.org/a/b/c/?foo=1&ufo=0', b'GET', [], None,
     b'GET /a/b/c/?foo=1&ufo=0 HTTP/1.1\r\nHost: foo.org\r\n\r\n'),
])
async def test_request_writing(url, method, headers, content, expected_result):
    request = Request(method, url, Headers(headers), content)
    data = b''
    async for chunk in scribe.write_request(request):
        data += chunk
    assert data == expected_result


@pytest.mark.parametrize('url,query,parsed_query', [
    (b'https://foo.org/a/b/c?hello=world', b'hello=world', {
        'hello': ['world']
    }),
    (b'https://foo.org/a/b/c?hello=world&foo=power', b'hello=world&foo=power', {
        'hello': ['world'],
        'foo': ['power']
    }),
    (b'https://foo.org/a/b/c?hello=world&foo=power&foo=200', b'hello=world&foo=power&foo=200', {
        'hello': ['world'],
        'foo': ['power', '200']
    }),
])
def test_parse_query(url, query, parsed_query):
    request = Request(b'GET', url, None, None)
    assert request.url.value == url
    assert request.url.query == query
    assert request.query == parsed_query


@pytest.mark.asyncio
async def test_can_read_json_data_even_without_content_type_header():
    request = Request(b'POST', b'/', Headers(), None)

    request.extend_body(b'{"hello":"world","foo":false}')
    request.complete.set()

    json = await request.json()
    assert json == {"hello": "world", "foo": False}


@pytest.mark.asyncio
async def test_if_read_json_fails_content_type_header_is_checked_json_gives_bad_request_format():
    request = Request(b'POST', b'/', Headers([
        Header(b'Content-Type', b'application/json')
    ]), None)

    request.extend_body(b'{"hello":')  # broken json
    request.complete.set()

    with pytest.raises(BadRequestFormat):
        await request.json()


@pytest.mark.asyncio
async def test_if_read_json_fails_content_type_header_is_checked_non_json_gives_invalid_operation():
    request = Request(b'POST', b'/', Headers([
        Header(b'Content-Type', b'text/html')
    ]), None)

    request.extend_body(b'{"hello":')  # broken json
    request.complete.set()

    with pytest.raises(InvalidOperation):
        await request.json()


def test_cookie_parsing():
    request = Request(b'POST', b'/', Headers([
        Header(b'Cookie', b'ai=something; hello=world; foo=Hello%20World%3B;')
    ]), None)

    assert request.cookies == {
        b'ai': b'something',
        b'hello': b'world',
        b'foo': b'Hello World;'
    }


def test_cookie_parsing_multiple_cookie_headers():
    request = Request(b'POST', b'/', Headers([
        Header(b'Cookie', b'ai=something; hello=world; foo=Hello%20World%3B;'),
        Header(b'Cookie', b'jib=jab; ai=else;'),
    ]), None)

    assert request.cookies == {
        b'ai': b'else',
        b'hello': b'world',
        b'foo': b'Hello World;',
        b'jib': b'jab'
    }


def test_cookie_parsing_duplicated_cookie_header_value():
    request = Request(b'POST', b'/', Headers([
        Header(b'Cookie', b'ai=something; hello=world; foo=Hello%20World%3B; hello=kitty;')
    ]), None)

    assert request.cookies == {
        b'ai': b'something',
        b'hello': b'kitty',
        b'foo': b'Hello World;'
    }


@pytest.mark.parametrize('header,expected_result', [
    [Header(b'Expect', b'100-Continue'), True],
    [Header(b'expect', b'100-continue'), True],
    [Header(b'X-Foo', b'foo'), False]
])
def test_request_expect_100_continue(header, expected_result):
    request = Request(b'POST', b'/', Headers([header]), None)
    assert expected_result == request.expect_100_continue()


@pytest.mark.parametrize('headers,expected_result', [
    [[Header(b'Content-Type', b'application/json')], True],
    [[Header(b'Content-Type', b'application/problem+json')], True],
    [[Header(b'Content-Type', b'application/json; charset=utf-8')], True],
    [[], False],
    [[Header(b'Content-Type', b'application/xml')], False]
])
def test_request_declares_json(headers, expected_result):
    request = Request(b'GET', b'/', Headers(headers), None)
    assert request.declares_json() is expected_result
