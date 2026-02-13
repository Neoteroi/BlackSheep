import asyncio
import os
import uuid
from collections.abc import MutableSequence
from inspect import isasyncgenfunction
from typing import Any, AsyncIterable, AsyncIterator, BinaryIO
from urllib.parse import parse_qsl, quote_plus

from blacksheep.common.files.pathsutils import get_mime_type_from_name
from blacksheep.settings.json import json_settings

from .exceptions import MessageAborted


def ensure_in_cwd(path: str) -> None:
    """
    Security check to ensure the given path is within the current working directory.

    This function prevents directory traversal attacks by verifying that the
    absolute path of the provided path starts with the current working directory.

    Args:
        path (str): The file path to validate.

    Raises:
        ValueError: If the path is outside the current working directory.
    """
    abs_path = os.path.abspath(path)
    cwd = os.getcwd()
    if not abs_path.startswith(cwd):
        raise ValueError("Cannot save file outside current working directory.")



class Content:
    def __init__(self, content_type: bytes, data: bytes):
        self.type = content_type
        self.body = data
        self.length = len(data)

    async def read(self) -> bytes:
        return self.body


class StreamedContent(Content):
    """
    Represents content that is streamed in chunks rather than loaded entirely into memory.

    This class is designed for efficient handling of large content by providing
    streaming capabilities. It wraps an async generator that produces chunks of bytes.

    Attributes:
        type: The content type (MIME type) as bytes.
        body: The full body content (bytes or None if not yet read).
        length: The content length in bytes, or -1 if unknown.
        generator: The async generator function that produces content chunks.
    """
    def __init__(self, content_type: bytes, data_provider, data_length: int = -1):
        self.type = content_type
        self.body = None
        self.length = data_length
        self.generator = data_provider
        if not isasyncgenfunction(data_provider):
            raise ValueError("Data provider must be an async generator")

    async def read(self):
        """
        Read and return all content as bytes.

        **WARNING**: This method loads the entire content into memory at once. For large
        content, this can cause excessive memory usage and may lead to out-of-memory
        errors. Use the `stream()` method instead for memory-efficient processing
        of large content.

        Returns:
            The complete content as bytes.
        """
        value = bytearray()
        async for chunk in self.generator():
            value.extend(chunk)
        self.body = bytes(value)
        self.length = len(self.body)
        return self.body

    async def stream(self):
        """
        Stream the content in chunks.

        This method is the recommended way to process large content as it yields
        chunks of data without loading everything into memory at once.

        Yields:
            Chunks of bytes from the content stream.
        """
        async for chunk in self.generator():
            yield chunk

    async def get_parts(self):
        """
        Stream the content in chunks.

        This is an alias for `stream()` and provides the same functionality.

        Yields:
            Chunks of bytes from the content stream.
        """
        async for chunk in self.generator():
            yield chunk


class ASGIContent(Content):
    """
    Represents content received from an ASGI application.

    This class handles streaming content from ASGI messages, typically used
    for request bodies in ASGI applications. It provides both streaming and
    buffered reading capabilities.

    Attributes:
        type: The content type (MIME type), initially None.
        body: The full body content (bytes or None if not yet read).
        length: The content length in bytes, initially -1 (unknown).
        receive: The ASGI receive callable for getting messages.
    """

    def __init__(self, receive):
        """
        Initialize ASGIContent with an ASGI receive callable.

        Args:
            receive: An ASGI receive callable that returns awaitable messages.
        """
        self.type = None
        self.body = None
        self.length = -1
        self.receive = receive

    async def stream(self):
        """
        Stream the content from ASGI messages in chunks.

        This method is the recommended way to process large content as it yields
        chunks of data without loading everything into memory at once.

        Yields:
            Byte chunks from ASGI message bodies.

        Raises:
            MessageAborted: If the HTTP connection is disconnected.
        """
        while True:
            message = await self.receive()
            if message.get("type") == "http.disconnect":
                raise MessageAborted()
            yield message.get("body", b"")
            if not message.get("more_body"):
                break
        yield b""

    async def read(self):
        """
        Read and return all content as bytes.

        Returns:
            The complete content as bytes.

        Raises:
            MessageAborted: If the HTTP connection is disconnected.
        """
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

    def dispose(self):
        """
        Dispose of the ASGI content by clearing references.

        This method should be called when the content is no longer needed
        to allow garbage collection and prevent memory leaks.
        """
        self.receive = None
        self.body = None


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
    def __init__(self, data: dict[str, Any] | list[tuple[str, Any]]):
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
        "_file",
        "file_name",
        "content_type",
        "charset",
        "size",
    )

    def __init__(
        self,
        name: bytes,
        data: bytes | BinaryIO,
        content_type: bytes | None = None,
        file_name: bytes | None = None,
        charset: bytes | None = None,
        size: int = 0,
    ):
        self.name = name
        self._data = data if isinstance(data, bytes) else None
        self._file = data if not isinstance(data, bytes) else None
        self.file_name = file_name
        self.content_type = content_type
        self.charset = charset
        self.size = size

    @classmethod
    def from_field(
        cls,
        name: str,
        value: str | bytes,
        content_type: str | None = None,
        charset: str = "utf-8",
    ) -> "FormPart":
        """
        Create a FormPart for a simple form field.

        This is a convenience method that accepts string parameters and converts
        them to bytes internally, making it easier to create form parts without
        manually encoding strings.

        Args:
            name: The name of the form field.
            value: The field value (string or bytes).
            content_type: Optional MIME type (defaults to text/plain for strings).
            charset: Character encoding (default: utf-8).

        Returns:
            A new FormPart instance.

        Example:
            part = FormPart.from_field("username", "john_doe")
        """
        data = value.encode(charset) if isinstance(value, str) else value

        if content_type is None and isinstance(value, str):
            content_type_bytes = f"text/plain; charset={charset}".encode("utf-8")
        elif content_type:
            content_type_bytes = content_type.encode("utf-8")
        else:
            content_type_bytes = None

        return cls(
            name=name.encode("utf-8"),
            data=data,
            content_type=content_type_bytes,
            charset=charset.encode("utf-8"),
            size=len(data),
        )

    @classmethod
    def from_file(
        cls,
        part_name: str,
        file_path: str,
        file: BinaryIO | None = None,
        content_type: str | None = None,
    ) -> "FormPart":
        """
        Create a FormPart for a file upload.

        This is a convenience method that accepts string parameters and converts
        them to bytes internally. It can automatically open the file or use an
        already-opened file handle.

        Args:
            part_name: The name of the form field.
            file_path: The path to the file to upload. Used for determining the
                      filename and MIME type. If 'file' is not provided, the file
                      at this path will be opened.
            file: Optional file-like object. If provided, this will be used instead
                 of opening the file at file_path. The file_path will still be used
                 as the filename in the multipart data.
            content_type: Optional MIME type (e.g., "image/jpeg"). If not provided,
                         the MIME type will be inferred from the file extension.

        Returns:
            A new FormPart instance.

        Examples:
            # Automatic file opening
            part = FormPart.from_file("photo", "photo.jpg")

            # With explicit content type
            part = FormPart.from_file("photo", "photo.jpg", content_type="image/jpeg")

            # With already-opened file
            with open("photo.jpg", "rb") as f:
                part = FormPart.from_file("photo", "photo.jpg", file=f)
        """
        # We cannot close the file while used by FormPart
        specified_file = file is not None
        file = open(file_path, mode="rb") if file is None else file
        file_name = file_path if specified_file else file.name

        # Get file size if possible
        size = 0
        try:
            current_pos = file.tell()
            file.seek(0, 2)  # Seek to end
            size = file.tell()
            file.seek(current_pos)  # Restore position
        except (OSError, AttributeError):
            # File doesn't support seeking
            pass

        if content_type is None:
            # Try obtaining mime type from the file name
            content_type = get_mime_type_from_name(file_path)

        return cls(
            name=part_name.encode("utf-8"),
            data=file,
            file_name=file_name.encode("utf-8"),
            content_type=content_type.encode("utf-8") if content_type else None,
            charset=None,
            size=size,
        )

    @property
    def data(self) -> bytes:
        if isinstance(self._data, bytes):
            return self._data
        if self._file:
            self._file.seek(0)
            return self._file.read()
        return b""

    @property
    def file(self) -> BinaryIO:
        if self._file is None:
            raise TypeError("Missing file data")
        return self._file

    async def stream(self, chunk_size: int = 8192) -> AsyncIterator[bytes]:
        """
        Async generator that yields the data in chunks.

        Args:
            chunk_size: Size of each chunk in bytes (default: 8192).

        Yields:
            Byte chunks of the form part data.
        """
        if isinstance(self._data, bytes):
            # For small in-memory data, yield it all at once
            yield self._data
        elif self._file:
            self._file.seek(0)
            while True:
                chunk = await asyncio.to_thread(self._file.read, chunk_size)
                if not chunk:
                    break
                yield chunk

    async def save_to(self, path: str) -> int:
        """Save file data to a specified path.

        Args:
            path: File path where data should be saved.

        Returns:
            Total number of bytes written.

        Raises:
            ValueError: If the path is outside the current working directory.
        """
        ensure_in_cwd(path)
        total_bytes = 0
        with open(path, "wb") as f:
            async for chunk in self.stream():
                f.write(chunk)
                total_bytes += len(chunk)
        return total_bytes

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


class FileBuffer:
    """
    Represents a file uploaded using multi-part/form-data.
    This class provides buffered data access.

    Attributes:
        name: The form field name (str).
        filename: The uploaded file's name (str).
        content_type: The MIME type (str or None).
        file: The underlying file-like object (BinaryIO).
        size: The size in bytes (if known), or 0.
    """

    __slots__ = ("name", "file_name", "content_type", "file", "size", "_charset")

    def __init__(
        self,
        name: str,
        file_name: str | None,
        file: BinaryIO,
        content_type: str | None = None,
        size: int = 0,
        charset: str | None = None,
    ):
        self.name = name
        self.file_name = file_name
        self.content_type = content_type
        self.file = file
        self.size = size
        self._charset = charset

    async def stream(self, chunk_size: int = 8192) -> AsyncIterator[bytes]:
        """
        Async generator that yields the data in chunks.

        Args:
            chunk_size: Size of each chunk in bytes (default: 8192).

        Yields:
            Byte chunks of the form part data.
        """
        self.file.seek(0)
        while True:
            chunk = await asyncio.to_thread(self.file.read, chunk_size)
            if not chunk:
                break
            yield chunk

    @classmethod
    def from_form_part(cls, form_part: FormPart):
        return cls(
            name=form_part.name.decode(),
            file_name=form_part.file_name.decode() if form_part.file_name else None,
            file=form_part.file,
            content_type=(
                form_part.content_type.decode() if form_part.content_type else None
            ),
            size=form_part.size,
            charset=form_part.charset.decode() if form_part.charset else None,
        )

    def read(self, size: int = -1) -> bytes:
        """Read data from the file."""
        return self.file.read(size)

    def seek(self, offset: int, whence: int = 0) -> int:
        """Seek to a position in the file."""
        return self.file.seek(offset, whence)

    async def save_to(self, path: str) -> int:
        """Save file data to a specified path.

        Args:
            path: File path where data should be saved.

        Returns:
            Total number of bytes written.

        Raises:
            ValueError: If the path is outside the current working directory.
        """
        ensure_in_cwd(path)
        total_bytes = 0
        with open(path, "wb") as f:
            async for chunk in self.stream():
                f.write(chunk)
                total_bytes += len(chunk)
        return total_bytes

    def close(self):
        """Close the underlying file."""
        self.file.close()

    def __repr__(self):
        return f"<FileBuffer {self.file_name} ({self.content_type})>"

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
        async for chunk in self._data_stream:
            yield chunk

    async def save_to(self, path: str) -> int:
        """
        Stream part data directly to a file.

        Args:
            path: File path where data should be saved.

        Returns:
            Total number of bytes written.

        Raises:
            ValueError: If the path is outside the current working directory.
        """
        ensure_in_cwd(path)
        total_bytes = 0
        with open(path, "wb") as f:
            async for chunk in self.stream():
                f.write(chunk)
                total_bytes += len(chunk)
        return total_bytes

    def __repr__(self):
        return f"<StreamingFormPart {self.name} - at {id(self)}>"


class MultiPartFormData(StreamedContent):
    """
    Represents multipart/form-data content for responses.

    This class streams multipart/form-data in chunks, avoiding loading
    all form parts into memory at once. It uses the StreamedContent API
    for memory-efficient streaming.

    Attributes:
        parts: List of FormPart objects to encode as multipart/form-data.
        boundary: Randomly generated boundary string for separating parts.
    """

    def __init__(self, parts: list[FormPart]):
        self.parts = parts
        self.boundary = b"----" + str(uuid.uuid4()).replace("-", "").encode()
        super().__init__(
            b"multipart/form-data; boundary=" + self.boundary,
            self._generate_multipart_chunks,
            data_length=-1,
        )

    async def _generate_multipart_chunks(self) -> AsyncIterator[bytes]:
        """Generate multipart/form-data content in chunks."""
        for part in self.parts:
            # Build headers as a single chunk
            header = bytearray()
            header.extend(b"--")
            header.extend(self.boundary)
            header.extend(b"\r\n")
            header.extend(b'Content-Disposition: form-data; name="')
            header.extend(part.name)
            header.extend(b'"')

            if part.file_name:
                header.extend(b'; filename="')
                header.extend(part.file_name)
                header.extend(b'"\r\n')

            if part.content_type:
                header.extend(b"Content-Type: ")
                header.extend(part.content_type)

            header.extend(b"\r\n\r\n")
            yield bytes(header)

            # Stream the part data
            async for chunk in part.stream():
                yield chunk

            yield b"\r\n"

        # Write final boundary
        yield b"--" + self.boundary + b"--\r\n"


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
