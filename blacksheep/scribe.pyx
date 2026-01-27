import http
import re

from .contents cimport Content, StreamedContent
from .cookies cimport Cookie, write_cookie_for_response
from .messages cimport Request, Response
from .url cimport URL


cdef int MAX_RESPONSE_CHUNK_SIZE = 61440  # 64kb


cdef bint should_use_chunked_encoding(Content content):
    return content.length < 0


cdef void set_headers_for_response_content(Response message):
    cdef Content content = message.content

    if not content:
        message._add_header(b'content-length', b'0')
        return

    message._add_header(b'content-type', content.type or b'application/octet-stream')

    if should_use_chunked_encoding(content):
        message._add_header(b'transfer-encoding', b'chunked')
    else:
        message._add_header(b'content-length', str(content.length).encode())


cpdef bytes write_response_cookie(Cookie cookie):
    return write_cookie_for_response(cookie)


async def write_chunks(Content http_content):
    """
    Writes chunks for transfer encoding. This method only works when using
    `transfer-encoding: chunked`!
    """
    async for chunk in http_content.get_parts():
        yield (hex(len(chunk))).encode()[2:] + b'\r\n' + chunk + b'\r\n'
    yield b'0\r\n\r\n'


def get_chunks(bytes data):
    cdef int i
    for i in range(0, len(data), MAX_RESPONSE_CHUNK_SIZE):
        yield data[i:i + MAX_RESPONSE_CHUNK_SIZE]
    yield b''


async def send_asgi_response(Response response, object send):
    cdef bytes chunk
    cdef Content content = response.content

    set_headers_for_response_content(response)

    await send({
        'type': 'http.response.start',
        'status': response.status,
        'headers': response._raw_headers
    })

    if content:
        if content.length < 0 or isinstance(content, StreamedContent):
            # NB: ASGI HTTP Servers automatically handle chunked encoding,
            # there is no need to write the length of each chunk
            # (see write_chunks function)
            closing_chunk = False
            async for chunk in content.get_parts():
                if not chunk:
                    closing_chunk = True
                await send({
                    'type': 'http.response.body',
                    'body': chunk,
                    'more_body': bool(chunk)
                })

            if not closing_chunk:
                # This is needed, otherwise uvicorn complains with:
                # ERROR:    ASGI callable returned without completing response.
                await send({
                    'type': 'http.response.body',
                    'body': b"",
                    'more_body': False
                })
        else:
            if content.length > MAX_RESPONSE_CHUNK_SIZE:
                # Note: get_chunks yields the closing bytes fragment therefore
                # we do not need to check for the closing message!
                for chunk in get_chunks(content.body):
                    await send({
                        'type': 'http.response.body',
                        'body': chunk,
                        'more_body': bool(chunk)
                    })
            else:
                await send({
                    'type': 'http.response.body',
                    'body': content.body,
                    'more_body': False
                })
    else:
        await send({
            'type': 'http.response.body',
            'body': b''
        })


_NEW_LINES_RX = re.compile("\r\n|\n")


cpdef bytes write_sse(ServerSentEvent event):
    """
    Writes a ServerSentEvent object to bytes.
    """
    cdef bytearray value = bytearray()

    if event.id:
        value.extend(b"id: " + _NEW_LINES_RX.sub("", event.id).encode("utf8") + b"\n")

    if event.comment:
        for part in _NEW_LINES_RX.split(event.comment):
            value.extend(b": " + part.encode("utf8") + b"\n")

    if event.event:
        value.extend(b"event: " + _NEW_LINES_RX.sub("", event.event).encode("utf8") + b"\n")

    if event.data:
        value.extend(b"data: " + event.write_data().encode("utf8") + b"\n")

    if event.retry > -1:
        value.extend(b"retry: " + str(event.retry).encode() + b"\n")

    value.extend(b"\n")
    return bytes(value)
