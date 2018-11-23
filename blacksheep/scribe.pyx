from .headers cimport HttpHeaderCollection, HttpHeader
from .contents cimport HttpContent
from .cookies cimport HttpCookie
from .messages cimport HttpRequest, HttpResponse


include "includes/consts.pxi"


import http


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


cdef bytes write_header(HttpHeader header):
    return header.name + b': ' + header.value + b'\r\n'


cdef bytes write_headers(list headers):
    cdef HttpHeader header
    cdef bytearray value
    
    value = bytearray()
    for header in headers:
        value.extend(write_header(header))
    return bytes(value)


cdef void extend_data_with_headers(list headers, bytearray data):
    cdef HttpHeader header

    for header in headers:
        data.extend(write_header(header))


cdef bytes write_request_uri(HttpRequest request):
    cdef p
    cdef object url = request.url  # TODO: how to use type from httptools?
    p = url.path or b'/'
    if url.query:
        return p + b'?' + url.query
    return p


cdef bint should_use_chunked_encoding(HttpContent content):
    return content.length < 0


cdef list get_headers_for_content(HttpContent content):
    cdef list headers = []
    
    if not content:
        headers.append(HttpHeader(b'Content-Length', b'0'))
        return headers
    headers.append(HttpHeader(b'Content-Type', content.type or b'application/octet-stream'))

    if should_use_chunked_encoding(content):
        headers.append(HttpHeader(b'Transfer-Encoding', b'chunked'))
    else:
        headers.append(HttpHeader(b'Content-Length', str(content.length).encode()))
    return headers


cdef bytes write_cookie_for_response(HttpCookie cookie):
    cdef list parts = []
    parts.append(cookie.name + b'=' + cookie.value)

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


cpdef bytes write_response_cookie(HttpCookie cookie):
    return write_cookie_for_response(cookie)


cdef bytes write_cookies_for_request(list cookies):
    cdef list parts = []
    cdef HttpCookie cookie

    for cookie in cookies:
        parts.append(cookie.name + b'=' + cookie.value for cookie in cookies)
    
    return b'; '.join(parts)


cdef list get_all_response_headers(HttpResponse response):
    cdef list result = []
    cdef HttpContent content
    cdef HttpHeader header
    cdef HttpCookie cookie
    cdef dict cookies

    for header in response.headers:
        result.append(header)

    headers = response.headers
    content = response.content

    if content:
        for header in get_headers_for_content(content):
            result.append(header)
    else:
        result.append(HttpHeader(b'Content-Length', b'0'))

    cookies = response.cookies

    if cookies:
        for cookie in cookies.values():
            result.append(HttpHeader(b'Set-Cookie', write_cookie_for_response(cookie)))
    return result


async def write_chunks(HttpContent http_content):
    async for chunk in http_content.get_parts():
        yield (hex(len(chunk))).encode()[2:] + b'\r\n' + chunk + b'\r\n'
    yield b'0\r\n\r\n'


cdef bint is_small_response(HttpResponse response):
    if response.content is None:
        return True
    if response.content.length > 0 and response.content.length < MAX_RESPONSE_CHUNK_SIZE:
        return True
    return False


cdef bytes write_small_response(HttpResponse response):
    cdef bytearray data = bytearray()
    data.extend(STATUS_LINES[response.status])
    extend_data_with_headers(get_all_response_headers(response), data)
    data.extend(b'\r\n')
    data.extend(response.content.body)
    return bytes(data)


cpdef bytes py_write_small_response(HttpResponse response):
    return write_small_response(response)


cdef list get_all_request_headers(HttpRequest request):
    cdef list result = []
    cdef HttpContent content
    cdef HttpHeader header
    cdef HttpCookie cookie
    cdef dict cookies

    for header in request.headers:
        result.append(header)
    
    content = request.content

    result.append(HttpHeader(b'Host', request.url.host))

    if content:
        for header in get_headers_for_content(content):
            result.append(header)

    cookies = request.cookies

    if cookies:
        result.append(HttpHeader(b'Cookie', write_cookies_for_request(cookies.values())))
    return result


async def write_request(HttpRequest request):
    yield request.method + b' ' + write_request_uri(request) + b' HTTP/1.1\r\n' + \
        write_headers(get_all_request_headers(request)) + b'\r\n'
    
    # TODO: complete


async def write_response(HttpResponse response):
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
                for chunk in (data[i:i + MAX_RESPONSE_CHUNK_SIZE] for i in range(0, len(data), MAX_RESPONSE_CHUNK_SIZE)):
                    yield chunk
            else:
                yield content.body
