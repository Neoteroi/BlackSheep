import ntpath
from enum import Enum
from typing import Any, Optional, Callable, Union
from blacksheep import Response, Headers, Header, TextContent, HtmlContent, JsonContent, Content


class ContentDispositionType(Enum):
    INLINE = 'inline'
    ATTACHMENT = 'attachment'


def _ensure_bytes(value: Union[str, bytes]):
    if isinstance(value, str):
        return value.encode()
    if isinstance(value, bytes):
        return value
    raise ValueError('Input value must be bytes or str')


def status_code(status: int = 200, message: Union[None, str, dict] = None):
    """Returns a plain response with given status, with optional message; sent as plain text or JSON."""
    if not message:
        return Response(status)
    if isinstance(message, str):
        content = TextContent(message)
    else:
        content = JsonContent(message)
    return Response(status, content=content)


def ok(message: Union[None, str, dict] = None):
    """Returns an HTTP 200 OK response, with optional message; sent as plain text or JSON."""
    return status_code(200, message)


def created(location: Union[bytes, str], value: Any = None):
    """Returns an HTTP 201 Created response, to the given location and with optional JSON content."""
    return Response(201,
                    Headers([Header(b'Location', _ensure_bytes(location))]),
                    JsonContent(value) if value else None)


def accepted():
    """Returns an HTTP 202 Accepted response."""
    return Response(202)


def no_content():
    """Returns an HTTP 204 No Content response."""
    return Response(204)


def not_modified():
    """Returns an HTTP 304 Not Modified response."""
    return Response(304)


def unauthorized(message: Union[None, str, dict] = None):
    """Returns an HTTP 401 Unauthorized response, with optional message; sent as plain text or JSON."""
    return status_code(401, message)


def forbidden(message: Union[None, str, dict] = None):
    """Returns an HTTP 403 Forbidden response, with optional message; sent as plain text or JSON."""
    return status_code(403, message)


def bad_request(message: Union[None, str, dict] = None):
    """Returns an HTTP 400 Bad Request response, with optional message; sent as plain text or JSON."""
    return status_code(400, message)


def not_found():
    """Returns an HTTP 404 Not Found response"""
    return Response(404)


def moved_permanently(location: Union[bytes, str]):
    """Returns an HTTP 301 Moved Permanently response, to the given location"""
    return Response(301, Headers([Header(b'Location', _ensure_bytes(location))]))


def redirect(location: Union[bytes, str]):
    """Returns an HTTP 302 Found response (commonly called redirect), to the given location"""
    return Response(302, Headers([Header(b'Location', _ensure_bytes(location))]))


def see_other(location: Union[bytes, str]):
    """Returns an HTTP 303 See Other response, to the given location."""
    return Response(303, Headers([Header(b'Location', _ensure_bytes(location))]))


def temporary_redirect(location: Union[bytes, str]):
    """Returns an HTTP 307 Temporary Redirect response, to the given location."""
    return Response(307, Headers([Header(b'Location', _ensure_bytes(location))]))


def permanent_redirect(location: Union[bytes, str]):
    """Returns an HTTP 308 Permanent Redirect response, to the given location."""
    return Response(308, Headers([Header(b'Location', _ensure_bytes(location))]))


def text(value: str, status: int = 200):
    """Returns a response with text/plain content, and given status (default HTTP 200 OK)."""
    return Response(status, content=TextContent(value))


def html(value: str, status: int = 200):
    """Returns a response with text/html content, and given status (default HTTP 200 OK)."""
    return Response(status, content=HtmlContent(value))


def json(value: Any, status: int = 200):
    """Returns a response with application/json content, and given status (default HTTP 200 OK)."""
    return Response(status, content=JsonContent(value))


def _file(value: Union[Callable, bytes],
          content_type: Union[str, bytes],
          content_disposition_type: ContentDispositionType,
          file_name: str = None):
    if file_name:
        exact_file_name = ntpath.basename(file_name)
        if not exact_file_name:
            raise ValueError('Invalid file name: it should be an exact file name without path, for example: "foo.txt"')

        content_disposition_value = f'{content_disposition_type.value}; filename="{exact_file_name}"'
    else:
        content_disposition_value = content_disposition_type.value
    response = Response(200, content=Content(_ensure_bytes(content_type), value))
    response.headers.add(Header(b'Content-Disposition', content_disposition_value.encode()))
    return response


def inline_file(value: Union[Callable, bytes],
                content_type: Union[str, bytes],
                file_name: str = None):
    """Returns a binary file response with given content type and optional file name, for inline use
    (default HTTP 200 OK). This method supports both call with bytes, or a generator yielding chunks.

    Remarks: this method does not handle cache, ETag and HTTP 304 Not Modified responses;
    when handling files it is recommended to handle cache, ETag and Not Modified, according to use case."""
    return _file(value, content_type, ContentDispositionType.INLINE, file_name)


def file(value: Union[Callable, bytes],
         content_type: Union[str, bytes],
         file_name: str = None):
    """Returns a binary file response with given content type and optional file name, for download (attachment)
    (default HTTP 200 OK). This method supports both call with bytes, or a generator yielding chunks.

    Remarks: this method does not handle cache, ETag and HTTP 304 Not Modified responses;
    when handling files it is recommended to handle cache, ETag and Not Modified, according to use case."""
    return _file(value, content_type, ContentDispositionType.ATTACHMENT, file_name)

