import http
import re

from .contents import Content, StreamedContent
from .cookies import Cookie, write_cookie_for_response
from .messages import Request, Response

MAX_RESPONSE_CHUNK_SIZE = 61440  # 64kb


def should_use_chunked_encoding(content: Content) -> bool:
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


def write_response_cookie(cookie: Cookie):
    return write_cookie_for_response(cookie)


async def write_chunks(http_content: Content):
    async for chunk in http_content.get_parts():
        yield (hex(len(chunk)))[2:].encode() + b"\r\n" + chunk + b"\r\n"
    yield b"0\r\n\r\n"


def get_chunks(data: bytes):
    for i in range(0, len(data), MAX_RESPONSE_CHUNK_SIZE):
        yield data[i : i + MAX_RESPONSE_CHUNK_SIZE]
    yield b""


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
