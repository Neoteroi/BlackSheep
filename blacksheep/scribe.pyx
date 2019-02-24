from .headers cimport Headers, Header
from .contents cimport Content
from .cookies cimport Cookie
from .messages cimport Request, Response


include "includes/consts.pxi"


import http
from urllib.parse import quote


cdef bytes _get_status_line(int status_code):
    try:
        return b'HTTP/1.1 ' + str(status_code).encode() + b' ' + http.HTTPStatus(status_code).phrase.encode() + b'\r\n'
    except ValueError:
        return b'HTTP/1.1 ' + str(status_code).encode() + b'\r\n'


STATUS_LINES = {
    status_code: _get_status_line(status_code) for status_code in range(100, 600)
}


cpdef bytes get_status_line(int status):
    return STATUS_LINES[status]


cdef bytes write_header(Header header):
    return header.name + b': ' + header.value + b'\r\n'


cdef bytes write_headers(list headers):
    cdef Header header
    cdef bytearray value
    
    value = bytearray()
    for header in headers:
        value.extend(write_header(header))
    return bytes(value)


cdef void extend_data_with_headers(list headers, bytearray data):
    cdef Header header

    for header in headers:
        data.extend(write_header(header))


cdef bytes write_request_uri(Request request):
    cdef p
    cdef object url = request.url  # TODO: how to use type from httptools?
    p = url.path or b'/'
    if url.query:
        return p + b'?' + url.query
    return p


cdef bint should_use_chunked_encoding(Content content):
    return content.length < 0


cdef list get_headers_for_content(Content content):
    cdef list headers = []
    
    if not content:
        headers.append(Header(b'Content-Length', b'0'))
        return headers
    headers.append(Header(b'Content-Type', content.type or b'application/octet-stream'))

    if should_use_chunked_encoding(content):
        headers.append(Header(b'Transfer-Encoding', b'chunked'))
    else:
        headers.append(Header(b'Content-Length', str(content.length).encode()))
    return headers


cdef bytes write_cookie_for_response(Cookie cookie):
    cdef list parts = []
    parts.append(quote(cookie.name).encode() + b'=' + quote(cookie.value).encode())

    if cookie.expires:
        parts.append(b'Expires=' + cookie.expires)

    if cookie.max_age:
        parts.append(b'Max-Age=' + cookie.max_age)

    if cookie.domain:
        parts.append(b'Domain=' + cookie.domain)

    if cookie.path:
        parts.append(b'Path=' + cookie.path)

    if cookie.http_only:
        parts.append(b'HttpOnly')

    if cookie.secure:
        parts.append(b'Secure')

    if cookie.same_site:
        parts.append(b'SameSite=' + cookie.same_site)

    return b'; '.join(parts)


cpdef bytes write_response_cookie(Cookie cookie):
    return write_cookie_for_response(cookie)


cdef bytes write_cookies_for_request(dict cookies):
    cdef list parts = []
    cdef bytes name, value

    for name, value in cookies.items():
        parts.append(name + b'=' + value)
    
    return b'; '.join(parts)


cdef list get_all_response_headers(Response response):
    cdef list result = []
    cdef Content content
    cdef Header header
    cdef Cookie cookie
    cdef dict cookies

    for header in response.headers:
        result.append(header)

    headers = response.headers
    content = response.content

    if content:
        for header in get_headers_for_content(content):
            result.append(header)
    else:
        result.append(Header(b'Content-Length', b'0'))

    cookies = response.cookies

    if cookies:
        for cookie in cookies.values():
            result.append(Header(b'Set-Cookie', write_cookie_for_response(cookie)))
    return result


async def write_chunks(Content http_content):
    async for chunk in http_content.get_parts():
        yield (hex(len(chunk))).encode()[2:] + b'\r\n' + chunk + b'\r\n'
    yield b'0\r\n\r\n'


cdef bint is_small_response(Response response):
    cdef Content content = response.content
    if not content:
        return True
    if content.length > 0 and content.length < MAX_RESPONSE_CHUNK_SIZE:
        return True
    return False


cpdef bint is_small_request(Request request):
    cdef Content content = request.content
    if not content:
        return True
    if content.length > 0 and content.length < MAX_RESPONSE_CHUNK_SIZE:
        return True
    return False


cpdef bint request_has_body(Request request):
    cdef Content content = request.content
    if not content or content.length == 0:
        return False
    # NB: if we use chunked encoding, we don't know the content.length;
    # and it is set to -1 (in contents.pyx), therefore it is handled properly
    return True


cpdef bytes write_request_without_body(Request request):
    cdef bytearray data = bytearray()
    data.extend(request.method + b' ' + write_request_uri(request) + b' HTTP/1.1\r\n')
    extend_data_with_headers(get_all_request_headers(request), data)
    data.extend(b'\r\n')
    return bytes(data)


cpdef bytes write_small_request(Request request):
    cdef bytearray data = bytearray()
    data.extend(request.method + b' ' + write_request_uri(request) + b' HTTP/1.1\r\n')
    extend_data_with_headers(get_all_request_headers(request), data)
    data.extend(b'\r\n')
    if request.content:
        data.extend(request.content.body)
    return bytes(data)


cdef bytes write_small_response(Response response):
    cdef bytearray data = bytearray()
    data.extend(STATUS_LINES[response.status])
    extend_data_with_headers(get_all_response_headers(response), data)
    data.extend(b'\r\n')
    if response.content:
        data.extend(response.content.body)
    return bytes(data)


cpdef bytes py_write_small_response(Response response):
    return write_small_response(response)


cpdef bytes py_write_small_request(Request request):
    return write_small_request(request)


cdef list get_all_request_headers(Request request):
    cdef list result = []
    cdef Content content
    cdef Header header
    cdef Cookie cookie
    cdef dict cookies

    for header in request.headers:
        result.append(header)
    
    content = request.content

    # TODO: if the request port is not default; add b':' + port
    result.append(Header(b'Host', request.url.host))

    if content:
        for header in get_headers_for_content(content):
            result.append(header)

    cookies = request.cookies

    if cookies:
        result.append(Header(b'Cookie', write_cookies_for_request(cookies)))
    return result


async def write_request_body_only(Request request):
    # This method is used only for Expect: 100-continue scenario;
    # in such case the request headers are sent before and then the body
    cdef bytes data
    cdef bytes chunk
    cdef Content content

    content = request.content

    if content:
        if should_use_chunked_encoding(content):
            async for chunk in write_chunks(content):
                yield chunk
        else:
            data = content.body

            if content.length > MAX_RESPONSE_CHUNK_SIZE:
                for chunk in get_chunks(data):
                    yield chunk
            else:
                yield data
    else:
        raise ValueError('Missing request content')


async def write_request(Request request):
    cdef bytes data
    cdef bytes chunk
    cdef Content content

    yield request.method + b' ' + write_request_uri(request) + b' HTTP/1.1\r\n' + \
        write_headers(get_all_request_headers(request)) + b'\r\n'

    content = request.content

    if content:
        if should_use_chunked_encoding(content):
            async for chunk in write_chunks(content):
                yield chunk
        else:
            data = content.body

            if content.length > MAX_RESPONSE_CHUNK_SIZE:
                for chunk in get_chunks(data):
                    yield chunk
            else:
                yield data


def get_chunks(bytes data):
    cdef int i
    for i in range(0, len(data), MAX_RESPONSE_CHUNK_SIZE):
        yield data[i:i + MAX_RESPONSE_CHUNK_SIZE]


async def write_response(Response response):
    cdef bytes data
    cdef bytes chunk
    cdef Content content

    yield STATUS_LINES[response.status] + \
        write_headers(get_all_response_headers(response)) + b'\r\n'

    content = response.content

    if content:
        if should_use_chunked_encoding(content):
            async for chunk in write_chunks(content):
                yield chunk
        else:
            data = content.body

            if content.length > MAX_RESPONSE_CHUNK_SIZE:
                for chunk in get_chunks(data):
                    yield chunk
            else:
                yield data
