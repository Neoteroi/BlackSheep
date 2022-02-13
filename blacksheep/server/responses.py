import ntpath
from enum import Enum
from functools import lru_cache
from io import BytesIO
from typing import Any, AnyStr, AsyncIterable, Callable, Union

from blacksheep import Content, JSONContent, Response, StreamedContent, TextContent
from blacksheep.common.files.asyncfs import FilesHandler
from blacksheep.plugins import json as json_plugin

MessageType = Any


class ContentDispositionType(Enum):
    """
    Represents the type for a Content-Disposition header (inline or attachment).
    The Content-Disposition response header is a header indicating if the content
    is expected to be displayed inline in the browser as part of a Web page
    or as an attachment, that is downloaded and saved locally.
    """

    INLINE = "inline"
    ATTACHMENT = "attachment"


def _ensure_bytes(value: AnyStr) -> bytes:
    if isinstance(value, str):
        return value.encode()
    if isinstance(value, bytes):
        return value
    raise ValueError("Input value must be bytes or str")


def _json_serialize(obj) -> str:
    return json_plugin.dumps(obj)


def _json_content(obj) -> JSONContent:
    return JSONContent(obj, _json_serialize)


def _optional_content(message: Any = None) -> Content:
    if isinstance(message, str):
        return TextContent(message)
    else:
        return _json_content(message)


def status_code(status: int = 200, message: Any = None) -> Response:
    """
    Returns a plain response with given status, with optional message;
    sent as plain text or JSON.
    """
    if not message:
        return Response(status)
    return Response(status, content=_optional_content(message))


def ok(message: Any = None) -> Response:
    """
    Returns an HTTP 200 OK response, with optional message;
    sent as plain text or JSON."""
    return status_code(200, message)


def created(message: Any = None, location: AnyStr = "") -> Response:
    """
    Returns an HTTP 201 Created response, to the given location
    and with optional JSON content.
    """
    return Response(
        201,
        [(b"Location", _ensure_bytes(location))] if location else [],
        content=_optional_content(message) if message else None,
    )


def accepted(message: Any = None) -> Response:
    """
    Returns an HTTP 202 Accepted response, with optional message;
    sent as plain text or JSON.
    """
    return status_code(202, message)


def no_content() -> Response:
    """
    Returns an HTTP 204 No Content response.
    """
    return Response(204)


def not_modified() -> Response:
    """
    Returns an HTTP 304 Not Modified response.
    """
    return Response(304)


def unauthorized(message: Any = None) -> Response:
    """
    Returns an HTTP 401 Unauthorized response, with optional message;
    sent as plain text or JSON.
    """
    return status_code(401, message)


def forbidden(message: Any = None) -> Response:
    """
    Returns an HTTP 403 Forbidden response, with optional message;
    sent as plain text or JSON.
    """
    return status_code(403, message)


def bad_request(message: Any = None) -> Response:
    """
    Returns an HTTP 400 Bad Request response, with optional message;
    sent as plain text or JSON.
    """
    return status_code(400, message)


def not_found(message: Any = None) -> Response:
    """
    Returns an HTTP 404 Not Found response, with optional message;
    sent as plain text or JSON.
    """
    return status_code(404, message)


def moved_permanently(location: AnyStr) -> Response:
    """
    Returns an HTTP 301 Moved Permanently response, to the given location.
    """
    return Response(301, [(b"Location", _ensure_bytes(location))])


def redirect(location: AnyStr) -> Response:
    """
    Returns an HTTP 302 Found response (commonly called redirect),
    to the given location.
    """
    return Response(302, [(b"Location", _ensure_bytes(location))])


def see_other(location: AnyStr) -> Response:
    """
    Returns an HTTP 303 See Other response, to the given location.
    """
    return Response(303, [(b"Location", _ensure_bytes(location))])


def temporary_redirect(location: AnyStr) -> Response:
    """
    Returns an HTTP 307 Temporary Redirect response, to the given location.
    """
    return Response(307, [(b"Location", _ensure_bytes(location))])


def permanent_redirect(location: AnyStr) -> Response:
    """
    Returns an HTTP 308 Permanent Redirect response, to the given location.
    """
    return Response(308, [(b"Location", _ensure_bytes(location))])


def text(value: str, status: int = 200) -> Response:
    """
    Returns a response with text/plain content,
    and given status (default HTTP 200 OK).
    """
    return Response(
        status, None, Content(b"text/plain; charset=utf-8", value.encode("utf8"))
    )


def html(value: str, status: int = 200) -> Response:
    """
    Returns a response with text/html content,
    and given status (default HTTP 200 OK).
    """
    return Response(
        status, None, Content(b"text/html; charset=utf-8", value.encode("utf8"))
    )


def json(data: Any, status: int = 200) -> Response:
    """
    Returns a response with application/json content,
    and given status (default HTTP 200 OK).
    """
    return Response(
        status,
        None,
        Content(
            b"application/json",
            json_plugin.dumps(data).encode("utf8"),
        ),
    )


def pretty_json(
    data: Any,
    status: int = 200,
    indent: int = 4,
) -> Response:
    """
    Returns a response with indented application/json content,
    and given status (default HTTP 200 OK).
    """
    return Response(
        status,
        None,
        Content(
            b"application/json",
            json_plugin.pretty_dumps(data).encode("utf8"),
        ),
    )


FileInput = Union[Callable[[], AsyncIterable[bytes]], str, bytes, bytearray, BytesIO]


@lru_cache(2000)
def _get_file_provider(file_path: str) -> Callable[[], AsyncIterable[bytes]]:
    async def data_provider():
        async for chunk in FilesHandler().chunks(file_path):
            yield chunk

    return data_provider


def _file(
    value: FileInput,
    content_type: str,
    content_disposition_type: ContentDispositionType,
    file_name: str = None,
) -> Response:
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

    content: Content
    content_type_value = _ensure_bytes(content_type)

    if isinstance(value, str):
        # value is treated as a path
        content = StreamedContent(content_type_value, _get_file_provider(value))
    elif isinstance(value, BytesIO):

        async def data_provider():
            try:
                value.seek(0)

                while True:
                    chunk = value.read(1024 * 64)

                    if not chunk:
                        break

                    yield chunk
                yield b""
            finally:
                if not value.closed:
                    value.close()

        content = StreamedContent(content_type_value, data_provider)
    elif callable(value):
        # value is treated as an async generator
        async def data_provider():
            async for chunk in value():
                yield chunk
            yield b""

        content = StreamedContent(content_type_value, data_provider)
    elif isinstance(value, bytes):
        content = Content(content_type_value, value)
    elif isinstance(value, bytearray):
        content = Content(content_type_value, bytes(value))
    else:
        raise ValueError(
            "Invalid value, expected one of: Callable, str, "
            "bytes, bytearray, io.BytesIO"
        )

    return Response(
        200, [(b"Content-Disposition", content_disposition_value.encode())], content
    )


def file(
    value: FileInput,
    content_type: str,
    *,
    file_name: str = None,
    content_disposition: ContentDispositionType = ContentDispositionType.ATTACHMENT,
) -> Response:
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
