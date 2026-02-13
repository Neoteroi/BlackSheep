import uuid
from tempfile import SpooledTemporaryFile
from typing import (
    Any,
    AsyncIterable,
    AsyncIterator,
    Awaitable,
    BinaryIO,
    Callable,
    Union,
)

class Content:
    def __init__(self, content_type: bytes, data: bytes):
        self.type = content_type
        self.body = data
        self.length = len(data)

    async def read(self) -> bytes:
        return self.body

    def dispose(self) -> None: ...

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

    def __init__(
        self,
        content_type: bytes,
        data_provider: Callable[[], AsyncIterable[bytes]],
        data_length: int = -1,
    ) -> None:
        self.type = content_type
        self.body = None
        self.length = data_length
        self.generator = data_provider

    async def read(self) -> bytes:
        """
        Read and return all content as bytes.

        **WARNING**: This method loads the entire content into memory at once. For large
        content, this can cause excessive memory usage and may lead to out-of-memory
        errors. Use the `stream()` method instead for memory-efficient processing
        of large content.

        Returns:
            The complete content as bytes.
        """
        ...

    async def stream(self) -> AsyncIterable[bytes]:
        """
        Stream the content in chunks.

        This method is the recommended way to process large content as it yields
        chunks of data without loading everything into memory at once.

        Yields:
            Chunks of bytes from the content stream.
        """
        ...

    async def get_parts(self) -> AsyncIterable[bytes]:
        """
        Stream the content in chunks.

        This is an alias for `stream()` and provides the same functionality.

        Yields:
            Chunks of bytes from the content stream.
        """
        ...

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

    def __init__(self, receive: Callable[[], Awaitable[dict]]):
        """
        Initialize ASGIContent with an ASGI receive callable.

        Args:
            receive: An ASGI receive callable that returns awaitable messages.
        """
        self.type = None
        self.body = None
        self.length = -1
        self.receive = receive

    def dispose(self) -> None:
        """
        Dispose of the ASGI content by clearing references.

        This method should be called when the content is no longer needed
        to allow garbage collection and prevent memory leaks.
        """
        ...

    def stream(self) -> AsyncIterable[bytes]:
        """
        Stream the content from ASGI messages in chunks.

        This method is the recommended way to process large content as it yields
        chunks of data without loading everything into memory at once.

        Yields:
            Byte chunks from ASGI message bodies.

        Raises:
            MessageAborted: If the HTTP connection is disconnected.
        """
        ...

    async def read(self) -> bytes:
        """
        Read and return all content as bytes.

        **WARNING**: This method loads the entire content into memory at once. For large
        content, this can cause excessive memory usage and may lead to out-of-memory
        errors. Use the `stream()` method instead for memory-efficient processing
        of large content.

        Returns:
            The complete content as bytes.

        Raises:
            MessageAborted: If the HTTP connection is disconnected.
        """
        ...

class TextContent(Content):
    def __init__(self, text: str):
        super().__init__(b"text/plain; charset=utf-8", text.encode("utf8"))

class HTMLContent(Content):
    def __init__(self, html: str):
        super().__init__(b"text/html; charset=utf-8", html.encode("utf8"))

def default_json_dumps(value: Any) -> str: ...

class JSONContent(Content):
    def __init__(self, data: object, dumps: Callable[[Any], str] = default_json_dumps):
        """
        Creates an instance of JSONContent class, automatically serializing the given
        input in JSON format, encoded using UTF-8.
        """
        super().__init__(b"application/json", dumps(data).encode("utf8"))

class FormContent(Content):
    def __init__(self, data: Union[dict[str, str], list[tuple[str, str]]]):
        """
        Creates an instance of FormContent class, with application/x-www-form-urlencoded
        type, and bytes data serialized from the given dictionary.

        :param data: data to be serialized.
        """
        super().__init__(b"application/x-www-form-urlencoded", b"")

class FormPart:
    """
    Represents a single part of a multipart/form-data request.

    Attributes:
        name: The name of the form field (bytes).
        data: The binary content of the form part.
        file_name: The file_name if this part represents a file upload (optional).
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
        """
        Initialize a FormPart instance.

        Args:
            name: The name of the form field.
            data: The binary content or a file-like object (BinaryIO).
            content_type: The MIME type of the content (optional).
            file_name: The file name if this part represents a file upload (optional).
            charset: The character encoding of the content (optional).
            size: The size of the content in bytes (default: 0).
        """
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
    ) -> FormPart:
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
        ...

    @classmethod
    def from_file(
        cls,
        part_name: str,
        file_path: str,
        content_type: str | None = None,
    ) -> FormPart:
        """
        Create a FormPart for a file upload.

        This is a convenience method that accepts string parameters and opens
        the file at the specified path, making it easier to create file upload parts.

        Args:
            part_name: The name of the form field.
            file_path: The path to the file to upload.
            content_type: Optional MIME type (e.g., "image/jpeg"). If not provided,
                         the MIME type will be inferred from the file extension.

        Returns:
            A new FormPart instance.

        Example:
            part = FormPart.from_file("photo", "photo.jpg", "image/jpeg")
        """
        ...
            charset: Optional character encoding.

        Returns:
            A new FormPart instance.

        Example:
            with open("photo.jpg", "rb") as f:
                part = FormPart.from_file("photo", "photo.jpg", f, "image/jpeg")
        """
        ...

    @property
    def data(self) -> bytes:
        """
        Returns the binary content of the form part.

        WARNING: This property loads all data into memory at once. For large files
        or fields, this can cause excessive memory usage. Use the `stream()` method
        instead for memory-efficient processing of large content.
        """
        ...
    @property
    def file(self) -> BinaryIO:
        """
        Returns the file-like object if the data is stored as a file.

        Use this property when the form part was initialized with a file-like object
        (BinaryIO), such as BytesIO, SpooledTemporaryFile, or file handles from open().

        Returns:
            The file-like object containing the file data.
        """
        ...
    def stream(self, chunk_size: int = 8192) -> AsyncIterator[bytes]:
        """
        Stream the form part content in chunks.

        This method is recommended for processing large files or fields as it reads
        data in chunks instead of loading everything into memory at once.

        Args:
            chunk_size: The size of each chunk in bytes (default: 8192).

        Yields:
            Chunks of binary data.
        """
        ...
    async def save_to(self, path: str) -> int:
        """
        Save the form part content to a file.

        Args:
            path: The file path where the content should be saved.

        Returns:
            The number of bytes written to the file.

        Raises:
            InvalidOperation: If the path is outside the current working directory.
        """
        ...
    def __eq__(self, other) -> bool:
        """
        Compare this FormPart with another object for equality.

        Args:
            other: The object to compare with.

        Returns:
            True if the objects are equal, False otherwise.
        """
        ...

class FileBuffer:
    """
    Represents an uploaded file with buffered data access.

    This class wraps a SpooledTemporaryFile to provide memory-efficient file uploads.
    Small files (<1MB) are kept in memory, larger files are automatically spooled to disk.

    Attributes:
        name: The form field name (str).
        file_name: The uploaded file's name (str).
        content_type: The MIME type (str or None).
        file: The underlying file-like object (SpooledTemporaryFile).
        size: The size in bytes (if known), or 0.

    Usage:
        # Access as file-like object
        content = file_buffer.file.read()

        # Or read all data
        data = await file_buffer.read()
    """

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

    def read(self, size: int = -1) -> bytes: ...
    def seek(self, offset: int, whence: int = 0) -> int: ...
    def close(self) -> None: ...
    def __repr__(self) -> str: ...
    def __enter__(self) -> "FileBuffer": ...
    def __exit__(self, exc_type, exc_val, exc_tb) -> None: ...
    async def save_to(self, path: str) -> int: ...
    @classmethod
    def from_form_part(cls, form_part: FormPart): ...

class StreamingFormPart:
    """
    Represents a streaming part of a multipart/form-data request.

    Unlike FormPart, which uses a SpooledTemporaryFile, StreamingFormPart provides
    access to streams of bytes as they are parsed in a multipart/form-data request.

    Attributes:
        name: The name of the form field (str).
        content_type: The MIME type of the content (optional).
        file_name: The file_name if this part represents a file upload (optional).
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

    def stream(self) -> AsyncIterable[bytes]:
        """
        Stream the form part content as bytes.

        This method provides access to the underlying async data stream,
        allowing memory-efficient processing of large file uploads without
        loading the entire content into memory.

        Yields:
            Chunks of binary data as they are received.
        """
        ...
    async def save_to(self, path: str) -> int:
        """
        Save the streamed form part content to a file.

        This method streams the data directly to disk, making it suitable
        for large file uploads without consuming excessive memory.

        Args:
            path: The file path where the content should be saved.

        Returns:
            The number of bytes written to the file.
        """
        ...
    def __repr__(self) -> str: ...


class MultiPartFormData(Content):
    """
    Represents multipart/form-data content for responses.

    Attributes:
        parts: List of FormPart objects to encode as multipart/form-data.
        boundary: Randomly generated boundary string for separating parts.
    """

    def __init__(self, parts: list[FormPart]):
        self.parts = parts
        self.boundary = b"------" + str(uuid.uuid4()).replace("-", "").encode()
        super().__init__(b"multipart/form-data; boundary=" + self.boundary, b"")

    def stream(self) -> AsyncIterable[bytes]: ...

def parse_www_form(content: str) -> dict[str, str | list[str]]: ...
def write_www_form_urlencoded(
    data: dict[str, str] | list[tuple[str, str]],
) -> bytes: ...
def simplify_multipart_data(data: dict | None) -> dict | None: ...

class ServerSentEvent:
    """
    Represents a single event of a Server-sent event communication, to be used
    in a asynchronous generator.

    Attributes:
        data: An object that will be transmitted to the client, in JSON.
        event: Optional event name.
        id: Optional event ID to set the EventSource's last event ID value.
        retry: Optional reconnection time, in milliseconds.
               If the connection to the server is lost, the browser will wait
               for the specified time before attempting to reconnect.
        comment: Optional comment.
    """

    def __init__(
        self,
        data: Any,
        event: str | None = None,
        id: str | None = None,
        retry: int = -1,
        comment: str | None = None,
    ):
        self.data = data
        self.event = event
        self.id = id
        self.retry = retry
        self.comment = comment

    def write_data(self) -> str: ...

class TextServerSentEvent(ServerSentEvent):
    def __init__(
        self,
        data: str,
        event: str | None = None,
        id: str | None = None,
        retry: int = -1,
        comment: str | None = None,
    ):
        super().__init__(data, event, id, retry, comment)

    def write_data(self) -> str: ...
