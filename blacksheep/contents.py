import uuid
from collections.abc import MutableSequence
from inspect import isasyncgenfunction
from tempfile import SpooledTemporaryFile
from typing import AsyncIterable
from urllib.parse import parse_qsl, quote_plus

from blacksheep.settings.json import json_settings

from .exceptions import MessageAborted


class Content:
    def __init__(self, content_type: bytes, data: bytes):
        self.type = content_type
        self.body = data
        self.length = len(data)

    async def read(self) -> bytes:
        return self.body


class StreamedContent(Content):
    def __init__(self, content_type: bytes, data_provider, data_length: int = -1):
        self.type = content_type
        self.body = None
        self.length = data_length
        self.generator = data_provider
        if not isasyncgenfunction(data_provider):
            raise ValueError("Data provider must be an async generator")

    async def read(self):
        value = bytearray()
        async for chunk in self.generator():
            value.extend(chunk)
        self.body = bytes(value)
        self.length = len(self.body)
        return self.body

    async def stream(self):
        async for chunk in self.generator():
            yield chunk

    async def get_parts(self):
        async for chunk in self.generator():
            yield chunk


class ASGIContent(Content):
    def __init__(self, receive):
        self.type = None
        self.body = None
        self.length = -1
        self.receive = receive

    def dispose(self):
        self.receive = None
        self.body = None

    async def stream(self):
        while True:
            message = await self.receive()
            if message.get("type") == "http.disconnect":
                raise MessageAborted()
            yield message.get("body", b"")
            if not message.get("more_body"):
                break
        yield b""

    async def read(self):
        if self.body is not None:
            return self.body
        value = bytearray()
        while True:
            message = await self.receive()
            if message.get("type") == "http.disconnect":
                raise MessageAborted()
            value.extend(message.get("body", b""))
            if not message.get("more_body"):
                break
        self.body = bytes(value)
        self.length = len(self.body)
        return self.body


class TextContent(Content):
    def __init__(self, text: str):
        super().__init__(b"text/plain; charset=utf-8", text.encode("utf8"))


class HTMLContent(Content):
    def __init__(self, html: str):
        super().__init__(b"text/html; charset=utf-8", html.encode("utf8"))


class JSONContent(Content):
    def __init__(self, data, dumps=json_settings.dumps):
        super().__init__(b"application/json", dumps(data).encode("utf8"))


def parse_www_form_urlencoded(content: str) -> dict:
    data = {}
    for key, value in parse_qsl(content):
        if key in data:
            if isinstance(data[key], str):
                data[key] = [data[key], value]
            else:
                data[key].append(value)
        else:
            data[key] = value
    return data


def parse_www_form(content: str) -> dict:
    return parse_www_form_urlencoded(content)


def try_decode(value: bytes, encoding: str):
    try:
        return value.decode(encoding or "utf8")
    except Exception:
        return value


def multiparts_to_dictionary(parts: list) -> dict:
    data = {}
    for part in parts:
        key = part.name.decode("utf8")
        charset = part.charset.encode() if part.charset else None
        if part.file_name:
            if key in data:
                data[key].append(part)
            else:
                data[key] = [part]
        else:
            if key in data:
                if isinstance(data[key], list):
                    data[key].append(try_decode(part.data, charset))
                else:
                    data[key] = [data[key], try_decode(part.data, charset)]
            else:
                data[key] = try_decode(part.data, charset)
    return data


def write_multipart_part(part, destination: bytearray):
    destination.extend(b'Content-Disposition: form-data; name="')
    destination.extend(part.name)
    destination.extend(b'"')
    if part.file_name:
        destination.extend(b'; filename="')
        destination.extend(part.file_name)
        destination.extend(b'"\r\n')
    if part.content_type:
        destination.extend(b"Content-Type: ")
        destination.extend(part.content_type)
    destination.extend(b"\r\n\r\n")
    destination.extend(part.data)
    destination.extend(b"\r\n")


def write_www_form_urlencoded(data: dict | list) -> bytes:
    if isinstance(data, list):
        values = data
    else:
        values = data.items()
    contents = []
    for key, value in values:
        if isinstance(value, MutableSequence):
            for item in value:
                contents.append(quote_plus(key) + "=" + quote_plus(str(item)))
        else:
            contents.append(quote_plus(key) + "=" + quote_plus(str(value)))
    return ("&".join(contents)).encode("utf8")


class FormContent(Content):
    def __init__(self, data: dict[str, str] | list[tuple[str, str]]):
        super().__init__(
            b"application/x-www-form-urlencoded", write_www_form_urlencoded(data)
        )


class FormPart:
    """
    Represents a single part of a multipart/form-data request.

    Attributes:
        name: The name of the form field (bytes).
        data: The binary content of the form part.
        file_name: The filename if this part represents a file upload (optional).
        content_type: The MIME type of the content (optional).
        charset: The character encoding of the content (optional).
    """
    __slots__ = (
        "name",
        "_data",
        "_file"
        "file_name",
        "content_type",
        "charset",
        "size"
    )

    def __init__(
        self,
        name: bytes,
        data: bytes | SpooledTemporaryFile,
        content_type: bytes | None = None,
        file_name: bytes | None = None,
        charset: bytes | None = None,
        size: int = 0
    ):
        self.name = name
        self._data = data if isinstance(data, bytes) else None
        self._file = data if isinstance(data, SpooledTemporaryFile) else None
        self.file_name = file_name
        self.content_type = content_type
        self.charset = charset
        self.size = size

    @property
    def data(self) -> bytes:
        if isinstance(self._data, bytes):
            return self._data
        if self._file:
            return self._file.read()
        return b""

    def __eq__(self, other):
        if isinstance(other, FormPart):
            return (
                other.name == self.name
                and other.file_name == self.file_name
                and other.content_type == self.content_type
                and other.charset == self.charset
                and other.data == self.data
            )
        if other is None:
            return False
        return NotImplemented

    def __repr__(self):
        return f"<FormPart {self.name} - at {id(self)}>"



class UploadFile:
    """
    Represents an uploaded file with lazy data access.

    This class wraps a SpooledTemporaryFile to provide memory-efficient file uploads.
    Small files (<1MB) are kept in memory, larger files are automatically spooled to disk.

    Attributes:
        name: The form field name (str).
        filename: The uploaded file's name (str).
        content_type: The MIME type (str or None).
        file: The underlying file-like object (SpooledTemporaryFile).
        size: The size in bytes (if known), or 0.

    Usage:
        # Access as file-like object
        content = upload_file.file.read()

        # Or read all data
        data = await upload_file.read()
    """
    __slots__ = ("name", "filename", "content_type", "file", "size", "_charset")

    def __init__(
        self,
        name: str,
        filename: str | None,
        file,  # file-like object (SpooledTemporaryFile)
        content_type: str | None = None,
        size: int = 0,
        charset: str | None = None,
    ):
        self.name = name
        self.filename = filename
        self.content_type = content_type
        self.file = file
        self.size = size
        self._charset = charset

    def read(self, size: int = -1) -> bytes:
        """Read data from the file."""
        return self.file.read(size)

    def seek(self, offset: int, whence: int = 0) -> int:
        """Seek to a position in the file."""
        return self.file.seek(offset, whence)

    def close(self):
        """Close the underlying file."""
        if hasattr(self.file, "close"):
            self.file.close()

    def __repr__(self):
        return f"<UploadFile {self.filename} ({self.content_type})>"

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class StreamingFormPart:
    """
    Represents a streaming part of a multipart/form-data request.

    Unlike FormPart, which loads all data into memory, StreamingFormPart provides
    lazy access to file content through async iteration, making it suitable for
    large file uploads without memory pressure.

    Attributes:
        name: The name of the form field (bytes).
        content_type: The MIME type of the content (optional).
        file_name: The filename if this part represents a file upload (optional).
        charset: The character encoding of the content (optional).
    """
    __slots__ = (
        "name",
        "file_name",
        "content_type",
        "charset",
        "_data_stream",
    )

    def __init__(
        self,
        name: str,
        data_stream: AsyncIterable[bytes],
        content_type: str | None = None,
        file_name: str | None = None,
        charset: str | None = None,
    ):
        self.name = name
        self.file_name = file_name
        self.content_type = content_type
        self.charset = charset
        self._data_stream = data_stream

    async def stream(self) -> AsyncIterable[bytes]:
        """
        Stream the part data in chunks.

        Yields:
            Byte chunks of the part data.
        """
        # Stream from source
        async for chunk in self._data_stream:
            yield chunk

    async def save_to(self, path: str) -> int:
        """
        Stream part data directly to a file.

        Args:
            path: File path where data should be saved.

        Returns:
            Total number of bytes written.
        """
        total_bytes = 0
        with open(path, 'wb') as f:
            async for chunk in self.stream():
                f.write(chunk)
                total_bytes += len(chunk)
        return total_bytes

    def __repr__(self):
        return f"<StreamingFormPart {self.name} - at {id(self)}>"




class FileData(StreamingFormPart):
    """
    Represents file data extracted from a multipart/form-data request.

    FileData inherits from StreamingFormPart and provides lazy access to uploaded
    file content through async iteration, making it suitable for large file uploads
    without loading entire files into memory.

    Attributes:
        name: The name of the form parameter containing the file.
        file_name: The name of the uploaded file.
        content_type: The MIME type of the file.
        charset: The character encoding of the content (optional).

    Usage:
        # Stream data in chunks
        async for chunk in file_data.stream():
            process(chunk)

        # Save directly to disk
        bytes_written = await file_data.save_to('/path/to/file')
    """
    def __repr__(self):
        return f"<FileData {self.file_name} ({self.content_type})>"


class MultiPartFormData(Content):
    def __init__(self, parts: list):
        self.parts = parts
        self.boundary = b"------" + str(uuid.uuid4()).replace("-", "").encode()
        super().__init__(
            b"multipart/form-data; boundary=" + self.boundary,
            write_multipart_form_data(self),
        )


def write_multipart_form_data(data: "MultiPartFormData") -> bytes:
    contents = bytearray()
    for part in data.parts:
        contents.extend(b"--")
        contents.extend(data.boundary)
        contents.extend(b"\r\n")
        write_multipart_part(part, contents)
    contents.extend(b"--")
    contents.extend(data.boundary)
    contents.extend(b"--\r\n")
    return bytes(contents)


class ServerSentEvent:
    """
    Represents a single event of a Server-sent event communication, to be used
    in a asynchronous generator.
    """

    def __init__(
        self,
        data,
        event: str | None = None,
        id: str | None = None,
        retry: int | None = -1,
        comment: str | None = None,
    ):
        self.data = data
        self.event = event
        self.id = id
        self.retry = retry
        self.comment = comment

    def write_data(self) -> str:
        return json_settings.dumps(self.data)

    def __repr__(self):
        return f"ServerSentEvent({self.data})"


class TextServerSentEvent(ServerSentEvent):
    def __init__(
        self,
        data: str,
        event: str | None = None,
        id: str | None = None,
        retry: int | None = -1,
        comment: str | None = None,
    ):
        super().__init__(data, event, id, retry, comment)

    def write_data(self) -> str:
        return self.data.replace("\r", "\\r").replace("\n", "\\n")
