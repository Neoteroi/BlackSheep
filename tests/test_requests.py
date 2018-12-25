import pytest
from blacksheep import HttpRequest, HttpHeaders
from blacksheep import scribe


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
