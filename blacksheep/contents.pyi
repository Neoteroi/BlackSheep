from tempfile import SpooledTemporaryFile
import uuid
from typing import (
    Any,
    AsyncIterable,
    Awaitable,
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

    async def get_parts(self) -> AsyncIterable[bytes]: ...

class ASGIContent(Content):
    def __init__(self, receive: Callable[[], Awaitable[dict]]):
        self.type = None
        self.body = None
        self.length = -1
        self.receive = receive

    def dispose(self): ...
    async def stream(self) -> AsyncIterable[bytes]: ...
    async def read(self) -> bytes: ...

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
        ...

    def __eq__(self, other) -> bool:
        ...


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



class FileData:
    """
    Represents file data extracted from a multipart/form-data request.

    Attributes:
        param_name: The name of the form parameter containing the file.
        data: The binary content of the file.
        content_type: The MIME type of the file.
        file_name: The name of the uploaded file.
    """

    def __init__(
        self,
        param_name: str,
        data: bytes,
        content_type: str,
        file_name: str,
    ):
        self.param_name = param_name
        self.data = data
        self.file_name = file_name
        self.content_type = content_type

    @classmethod
    def from_form_part(cls, form_data: FormPart) -> "FileData":
        ...


class MultiPartFormData(Content):
    def __init__(self, parts: list[FormPart]):
        self.parts = parts
        self.boundary = b"------" + str(uuid.uuid4()).replace("-", "").encode()
        super().__init__(b"multipart/form-data; boundary=" + self.boundary, b"")

def parse_www_form(content: str) -> dict[str, Union[str, list[str]]]:
    """Parses application/x-www-form-urlencoded content"""

def write_www_form_urlencoded(
    data: Union[dict[str, str], list[tuple[str, str]]],
) -> bytes: ...

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
