import http
import re

from .contents import Content, StreamedContent
from .cookies import Cookie, write_cookie_for_response
from .messages import Request, Response

MAX_RESPONSE_CHUNK_SIZE = 61440  # 64kb


# Header writing utilities
def write_header(header):
    return header[0] + b": " + header[1] + b"\r\n"


def write_headers(headers):
    value = bytearray()
    for header in headers:
        value.extend(write_header(header))
    return bytes(value)


def extend_data_with_headers(headers, data: bytearray):
    for header in headers:
        data.extend(write_header(header))


def _get_status_line(status_code: int):
    try:
        return (
            b"HTTP/1.1 "
            + str(status_code).encode()
            + b" "
            + http.HTTPStatus(status_code).phrase.encode()
            + b"\r\n"
        )
    except ValueError:
        return b"HTTP/1.1 " + str(status_code).encode() + b"\r\n"


STATUS_LINES = {
    status_code: _get_status_line(status_code) for status_code in range(100, 600)
}


def get_status_line(status: int):
    return STATUS_LINES[status]


def write_request_method(request: Request):
    return request.method.encode()


def write_request_uri(request: Request):
    url = request.url
    p = url.path or b"/"
    if url.query:
        return p + b"?" + url.query
    return p


def ensure_host_header(request: Request):
    if request.url.host:
        request._add_header_if_missing(b"host", request.url.host)


def should_use_chunked_encoding(content: Content):
    return content.length < 0


def set_headers_for_response_content(message: Response):
    content = message.content
    if not content:
        message._add_header(b"content-length", b"0")
        return
    message._add_header(b"content-type", content.type or b"application/octet-stream")
    if should_use_chunked_encoding(content):
        message._add_header(b"transfer-encoding", b"chunked")
    else:
        message._add_header(b"content-length", str(content.length).encode())


def set_headers_for_content(message):
    content = message.content
    if not content:
        message._add_header_if_missing(b"content-length", b"0")
        return
    message._add_header_if_missing(
        b"content-type", content.type or b"application/octet-stream"
    )
    if should_use_chunked_encoding(content):
        message._add_header_if_missing(b"transfer-encoding", b"chunked")
    else:
        message._add_header_if_missing(b"content-length", str(content.length).encode())


def write_response_cookie(cookie: Cookie):
    return write_cookie_for_response(cookie)


async def write_chunks(http_content: Content):
    async for chunk in http_content.get_parts():
        yield (hex(len(chunk)))[2:].encode() + b"\r\n" + chunk + b"\r\n"
    yield b"0\r\n\r\n"


def is_small_response(response: Response):
    content = response.content
    if not content:
        return True
    if (
        content.length > 0
        and content.length < MAX_RESPONSE_CHUNK_SIZE
        and content.body is not None
    ):
        return True
    return False


def is_small_request(request: Request):
    content = request.content
    if not content:
        return True
    if (
        content.length > 0
        and content.length < MAX_RESPONSE_CHUNK_SIZE
        and content.body is not None
    ):
        return True
    return False


def request_has_body(request: Request):
    content = request.content
    if not content or content.length == 0:
        return False
    return True


def write_request_without_body(request: Request):
    data = bytearray()
    data.extend(
        write_request_method(request)
        + b" "
        + write_request_uri(request)
        + b" HTTP/1.1\r\n"
    )
    ensure_host_header(request)
    extend_data_with_headers(request._raw_headers, data)
    data.extend(b"\r\n")
    return bytes(data)


def write_small_request(request: Request):
    data = bytearray()
    data.extend(
        write_request_method(request)
        + b" "
        + write_request_uri(request)
        + b" HTTP/1.1\r\n"
    )
    ensure_host_header(request)
    set_headers_for_content(request)
    extend_data_with_headers(request._raw_headers, data)
    data.extend(b"\r\n")
    if request.content:
        data.extend(request.content.body)
    return bytes(data)


def write_small_response(response: Response):
    data = bytearray()
    data.extend(STATUS_LINES[response.status])
    set_headers_for_content(response)
    extend_data_with_headers(response._raw_headers, data)
    data.extend(b"\r\n")
    if response.content:
        data.extend(response.content.body)
    return bytes(data)


def py_write_small_response(response: Response):
    return write_small_response(response)


def py_write_small_request(request: Request):
    return write_small_request(request)


async def write_request_body_only(request: Request):
    content = request.content
    if content:
        if should_use_chunked_encoding(content):
            async for chunk in write_chunks(content):
                yield chunk
        elif isinstance(content, StreamedContent):
            async for chunk in content.get_parts():
                yield chunk
        else:
            data = content.body
            if content.length > MAX_RESPONSE_CHUNK_SIZE:
                for chunk in get_chunks(data):
                    yield chunk
            else:
                yield data
    else:
        raise ValueError("Missing request content")


async def write_request(request: Request):
    ensure_host_header(request)
    set_headers_for_content(request)
    yield write_request_method(request) + b" " + write_request_uri(
        request
    ) + b" HTTP/1.1\r\n" + write_headers(request._raw_headers) + b"\r\n"
    content = request.content
    if content:
        if should_use_chunked_encoding(content):
            async for chunk in write_chunks(content):
                yield chunk
        elif isinstance(content, StreamedContent):
            async for chunk in content.get_parts():
                yield chunk
        else:
            data = content.body
            if content.length > MAX_RESPONSE_CHUNK_SIZE:
                for chunk in get_chunks(data):
                    yield chunk
            else:
                yield data


def get_chunks(data: bytes):
    for i in range(0, len(data), MAX_RESPONSE_CHUNK_SIZE):
        yield data[i : i + MAX_RESPONSE_CHUNK_SIZE]
    yield b""


async def write_response_content(response: Response):
    content = response.content
    if content:
        if should_use_chunked_encoding(content):
            async for chunk in write_chunks(content):
                yield chunk
        elif isinstance(content, StreamedContent):
            async for chunk in content.get_parts():
                yield chunk
        else:
            data = content.body
            if content.length > MAX_RESPONSE_CHUNK_SIZE:
                for chunk in get_chunks(data):
                    yield chunk
            else:
                yield data


async def write_response(response: Response):
    set_headers_for_content(response)
    yield STATUS_LINES[response.status] + write_headers(response._raw_headers) + b"\r\n"
    async for chunk in write_response_content(response):
        yield chunk


async def send_asgi_response(response: Response, send):
    content = response.content
    set_headers_for_response_content(response)
    await send(
        {
            "type": "http.response.start",
            "status": response.status,
            "headers": response._raw_headers,
        }
    )
    if content:
        if content.length < 0 or isinstance(content, StreamedContent):
            closing_chunk = False
            async for chunk in content.get_parts():
                if not chunk:
                    closing_chunk = True
                await send(
                    {
                        "type": "http.response.body",
                        "body": chunk,
                        "more_body": bool(chunk),
                    }
                )
            if not closing_chunk:
                await send(
                    {"type": "http.response.body", "body": b"", "more_body": False}
                )
        else:
            if content.length > MAX_RESPONSE_CHUNK_SIZE:
                for chunk in get_chunks(content.body):
                    await send(
                        {
                            "type": "http.response.body",
                            "body": chunk,
                            "more_body": bool(chunk),
                        }
                    )
            else:
                await send(
                    {
                        "type": "http.response.body",
                        "body": content.body,
                        "more_body": False,
                    }
                )
    else:
        await send({"type": "http.response.body", "body": b""})


_NEW_LINES_RX = re.compile("\r\n|\n")


def write_sse(event):
    value = bytearray()
    if event.id:
        value.extend(b"id: " + _NEW_LINES_RX.sub("", event.id).encode("utf8") + b"\n")
    if event.comment:
        for part in _NEW_LINES_RX.split(event.comment):
            value.extend(b": " + part.encode("utf8") + b"\n")
    if event.event:
        value.extend(
            b"event: " + _NEW_LINES_RX.sub("", event.event).encode("utf8") + b"\n"
        )
    if event.data:
        value.extend(b"data: " + event.write_data().encode("utf8") + b"\n")
    if event.retry > -1:
        value.extend(b"retry: " + str(event.retry).encode() + b"\n")
    value.extend(b"\n")
    return bytes(value)
