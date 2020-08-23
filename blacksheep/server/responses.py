import ntpath
from enum import Enum
from functools import lru_cache
from io import BytesIO
from typing import Any, Callable, Union

from essentials import json as JSON

from blacksheep import Content, JsonContent, Response, StreamedContent, TextContent
from blacksheep.common.files.asyncfs import FilesHandler
from blacksheep.utils import BytesOrStr

MessageType = Union[None, str, Any]


class ContentDispositionType(Enum):
    INLINE = "inline"
    ATTACHMENT = "attachment"


def _ensure_bytes(value: BytesOrStr):
    if isinstance(value, str):
        return value.encode()
    if isinstance(value, bytes):
        return value
    raise ValueError("Input value must be bytes or str")


def status_code(status: int = 200, message: MessageType = None):
    """
    Returns a plain response with given status, with optional message;
    sent as plain text or JSON.
    """
    if not message:
        return Response(status)
    if isinstance(message, str):
        content = TextContent(message)
    else:
        content = JsonContent(message)
    return Response(status, content=content)


def ok(message: MessageType = None):
    """
    Returns an HTTP 200 OK response, with optional message;
    sent as plain text or JSON."""
    return status_code(200, message)


def created(location: BytesOrStr, value: Any = None):
    """
    Returns an HTTP 201 Created response, to the given location
    and with optional JSON content.
    """
    return Response(
        201,
        [(b"Location", _ensure_bytes(location))],
        JsonContent(value) if value else None,
    )


def accepted(message: MessageType = None):
    """
    Returns an HTTP 202 Accepted response, with optional message;
    sent as plain text or JSON.
    """
    return status_code(202, message)


def no_content():
    """
    Returns an HTTP 204 No Content response.
    """
    return Response(204)


def not_modified():
    """
    Returns an HTTP 304 Not Modified response.
    """
    return Response(304)


def unauthorized(message: MessageType = None):
    """
    Returns an HTTP 401 Unauthorized response, with optional message;
    sent as plain text or JSON.
    """
    return status_code(401, message)


def forbidden(message: MessageType = None):
    """
    Returns an HTTP 403 Forbidden response, with optional message;
    sent as plain text or JSON.
    """
    return status_code(403, message)


def bad_request(message: MessageType = None):
    """
    Returns an HTTP 400 Bad Request response, with optional message;
    sent as plain text or JSON.
    """
    return status_code(400, message)


def not_found(message: MessageType = None):
    """
    Returns an HTTP 404 Not Found response, with optional message;
    sent as plain text or JSON.
    """
    return status_code(404, message)


def moved_permanently(location: BytesOrStr):
    """
    Returns an HTTP 301 Moved Permanently response, to the given location.
    """
    return Response(301, [(b"Location", _ensure_bytes(location))])


def redirect(location: BytesOrStr):
    """
    Returns an HTTP 302 Found response (commonly called redirect),
    to the given location.
    """
    return Response(302, [(b"Location", _ensure_bytes(location))])


def see_other(location: BytesOrStr):
    """
    Returns an HTTP 303 See Other response, to the given location.
    """
    return Response(303, [(b"Location", _ensure_bytes(location))])


def temporary_redirect(location: BytesOrStr):
    """
    Returns an HTTP 307 Temporary Redirect response, to the given location.
    """
    return Response(307, [(b"Location", _ensure_bytes(location))])


def permanent_redirect(location: BytesOrStr):
    """
    Returns an HTTP 308 Permanent Redirect response, to the given location.
    """
    return Response(308, [(b"Location", _ensure_bytes(location))])


def text(value: str, status: int = 200):
    """
    Returns a response with text/plain content,
    and given status (default HTTP 200 OK).
    """
    return Response(
        status, None, Content(b"text/plain; charset=utf-8", value.encode("utf8"))
    )


def html(value: str, status: int = 200):
    """
    Returns a response with text/html content,
    and given status (default HTTP 200 OK).
    """
    return Response(
        status, None, Content(b"text/html; charset=utf-8", value.encode("utf8"))
    )


def json(data: Any, status: int = 200, dumps=JSON.dumps):
    """
    Returns a response with application/json content,
    and given status (default HTTP 200 OK).
    """
    return Response(
        status,
        None,
        Content(b"application/json", dumps(data, separators=(",", ":")).encode("utf8")),
    )


def pretty_json(data: Any, status: int = 200, dumps=JSON.dumps, indent: int = 4):
    """
    Returns a response with indented application/json content,
    and given status (default HTTP 200 OK).
    """
    return Response(
        status,
        None,
        Content(b"application/json", dumps(data, indent=indent).encode("utf8")),
    )


FileInput = Union[Callable, str, bytes, bytearray, BytesIO]


@lru_cache(2000)
def _get_file_provider(file_path: str):
    async def data_provider():
        async for chunk in FilesHandler().chunks(file_path):
            yield chunk

    return data_provider


def _file(
    value: FileInput,
    content_type: BytesOrStr,
    content_disposition_type: ContentDispositionType,
    file_name: str = None,
):
    if file_name:
        exact_file_name = ntpath.basename(file_name)
        if not exact_file_name:
            raise ValueError(
                "Invalid file name: it should be an exact "
                'file name without path, for example: "foo.txt"'
            )

        content_disposition_value = (
            f'{content_disposition_type.value}; filename="{exact_file_name}"'
        )
    else:
        content_disposition_value = content_disposition_type.value

    content_type = _ensure_bytes(content_type)

    if isinstance(value, str):
        # value is treated as a path
        content = StreamedContent(content_type, _get_file_provider(value))
    elif isinstance(value, BytesIO):

        async def data_provider():
            while True:
                chunk = value.read(1024 * 64)

                if not chunk:
                    break

                yield chunk
            yield b""

        content = StreamedContent(content_type, data_provider)
    elif callable(value):
        # value is treated as an async generator
        async def data_provider():
            async for chunk in value():
                yield chunk
            yield b""

        content = StreamedContent(content_type, data_provider)
    elif isinstance(value, bytes):
        content = Content(content_type, value)
    elif isinstance(value, bytearray):
        content = Content(content_type, bytes(value))
    else:
        raise ValueError(
            "Invalid value, expected one of: Callable, str, "
            "bytes, bytearray, io.BytesIO"
        )

    return Response(
        200, [(b"Content-Disposition", content_disposition_value.encode())], content
    )


def inline_file(value: FileInput, content_type: BytesOrStr, file_name: str = None):
    """
    Returns a binary file response with given content type and optional file
    name, for inline use (default HTTP 200 OK). This method supports both call
    with bytes, or a generator yielding chunks.

    Remarks: this method does not handle cache, ETag and HTTP 304 Not Modified
    responses; when handling files it is recommended to handle cache, ETag and
    Not Modified, according to use case.
    """
    return _file(value, content_type, ContentDispositionType.INLINE, file_name)


def file(
    value: FileInput,
    content_type: BytesOrStr,
    file_name: str = None,
    content_disposition: ContentDispositionType = ContentDispositionType.ATTACHMENT,  # NOQA
):
    """
    Returns a binary file response with given content type and optional
    file name, for download (attachment)
    (default HTTP 200 OK). This method supports both call with bytes,
    or a generator yielding chunks.

    Remarks: this method does not handle cache, ETag and HTTP 304 Not Modified
    responses; when handling files it is recommended to handle cache, ETag and
    Not Modified, according to use case.
    """
    return _file(value, content_type, content_disposition, file_name)
