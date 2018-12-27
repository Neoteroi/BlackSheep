import pytest
from blacksheep import HttpRequest, HttpHeaders, HttpHeader
from blacksheep import scribe
from blacksheep.exceptions import BadRequestFormat, InvalidOperation


def test_request_supports_for_dynamic_attributes():
    request = HttpRequest(b'GET', b'/', HttpHeaders(), None)
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
    request = HttpRequest(method, url, HttpHeaders(headers), content)
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
    request = HttpRequest(b'GET', url, None, None)
    assert request.url.value == url
    assert request.url.query == query
    assert request.query == parsed_query


@pytest.mark.asyncio
async def test_can_read_json_data_even_without_content_type_header():
    request = HttpRequest(b'POST', b'/', HttpHeaders(), None)

    request.extend_body(b'{"hello":"world","foo":false}')
    request.complete.set()

    json = await request.json()
    assert json == {"hello": "world", "foo": False}


@pytest.mark.asyncio
async def test_if_read_json_fails_content_type_header_is_checked_json_gives_bad_request_format():
    request = HttpRequest(b'POST', b'/', HttpHeaders([
        HttpHeader(b'Content-Type', b'application/json')
    ]), None)

    request.extend_body(b'{"hello":')  # broken json
    request.complete.set()

    with pytest.raises(BadRequestFormat):
        await request.json()


@pytest.mark.asyncio
async def test_if_read_json_fails_content_type_header_is_checked_non_json_gives_invalid_operation():
    request = HttpRequest(b'POST', b'/', HttpHeaders([
        HttpHeader(b'Content-Type', b'text/html')
    ]), None)

    request.extend_body(b'{"hello":')  # broken json
    request.complete.set()

    with pytest.raises(InvalidOperation) as io:
        await request.json()
