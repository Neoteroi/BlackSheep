import asyncio
import json
import shutil
import uuid
from collections.abc import MutableSequence
from inspect import isasyncgenfunction
from urllib.parse import parse_qsl, quote_plus
from tempfile import SpooledTemporaryFile

from blacksheep.settings.json import json_settings

from .exceptions cimport MessageAborted


cdef class Content:

    def __init__(
        self,
        bytes content_type,
        bytes data
    ):
        self.type = content_type
        self.body = data
        self.length = len(data)

    async def read(self):
        return self.body


cdef class StreamedContent(Content):

    def __init__(
        self,
        bytes content_type,
        object data_provider,
        long long data_length = -1
    ):
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


cdef class ASGIContent(Content):

    def __init__(self, object receive):
        self.type = None
        self.body = None
        self.length = -1
        self.receive = receive

    cpdef void dispose(self):
        self.receive = None
        self.body = None

    async def stream(self):
        while True:
            message = await self.receive()

            if message.get('type') == 'http.disconnect':
                raise MessageAborted()

            yield message.get('body', b'')

            if not message.get('more_body'):
                break

        yield b''

    async def read(self):
        if self.body is not None:
            return self.body
        value = bytearray()

        while True:
            message = await self.receive()

            if message.get('type') == 'http.disconnect':
                raise MessageAborted()

            value.extend(message.get('body', b''))

            if not message.get('more_body'):
                break

        self.body = bytes(value)
        self.length = len(self.body)
        return self.body


cdef class TextContent(Content):

    def __init__(self, str text):
        super().__init__(b'text/plain; charset=utf-8', text.encode('utf8'))


cdef class HTMLContent(Content):

    def __init__(self, str html):
        super().__init__(b'text/html; charset=utf-8', html.encode('utf8'))


cdef class JSONContent(Content):

    def __init__(self, object data, dumps=json_settings.dumps):
        super().__init__(b'application/json', dumps(data).encode('utf8'))


cdef dict parse_www_form_urlencoded(str content):
    # application/x-www-form-urlencoded
    cdef str key, value
    cdef dict data = {}
    for key, value in parse_qsl(content):
        if key in data:
            if isinstance(data[key], str):
                data[key] = [data[key], value]
            else:
                data[key].append(value)
        else:
            data[key] = value
    return data


cpdef dict parse_www_form(str content):
    return parse_www_form_urlencoded(content)


cdef object try_decode(bytes value, str encoding):
    try:
        return value.decode(encoding or 'utf8')
    except:
        return value


cdef dict multiparts_to_dictionary(list parts):
    cdef str key
    cdef str charset
    cdef data = {}
    cdef FormPart part

    for part in parts:
        key = part.name.decode('utf8')
        if part.charset:
            charset = part.charset.encode()
        else:
            charset = None

        # NB: we cannot assume that the value of a multipart form part can be decoded as UTF8;
        # here we try to decode it, just to be more consistent with values read from www-urlencoded form data
        if part.file_name:
            # Files need special handling, must be kept as-is
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


cdef object _simplify_part(FormPart part):
    import warnings
    if part.file_name:
        # keep as is
        return part
    if part.size > 1024 * 1024:
        warnings.warn(
            f"Form field '{part.name.decode('utf8', errors='replace')}' "
            f"is {part.size / (1024 * 1024):.2f}MB and will be loaded into "
            f"memory. Consider handling large form fields directly with "
            f"request.multipart_stream instead.",
            UserWarning,
            stacklevel=3,
        )
    return part.data.decode(part.charset.decode() if part.charset else "utf8")


cpdef dict simplify_multipart_data(dict data):
    # This code is for backward compatibility,
    # probably this behavior will be changed in v3
    if data is None:
        return None
    cdef dict simplified_data = {}
    cdef list value
    for key, value in data.items():
        if len(value) > 1:
            simplified_data[key] = [_simplify_part(item) for item in value]
        else:
            if value[0].file_name:
                simplified_data[key] = value
            else:
                simplified_data[key] = _simplify_part(value[0])
    return simplified_data


cpdef void write_multipart_part(FormPart part, bytearray destination):
    # https://tools.ietf.org/html/rfc7578#page-4
    destination.extend(b'Content-Disposition: form-data; name="')
    destination.extend(part.name)
    destination.extend(b'"')
    if part.file_name:
        destination.extend(b'; filename="')
        destination.extend(part.file_name)
        destination.extend(b'"\r\n')
    if part.content_type:
        destination.extend(b'Content-Type: ')
        destination.extend(part.content_type)
    destination.extend(b'\r\n\r\n')
    destination.extend(part.data)
    destination.extend(b'\r\n')


cpdef bytes write_www_form_urlencoded(data: dict | list):
    # application/x-www-form-urlencoded
    if isinstance(data, list):
        values = data
    else:
        values = data.items()

    cdef list contents = []

    for key, value in values:
        if isinstance(value, MutableSequence):
            for item in value:
                contents.append(quote_plus(key) + '=' + quote_plus(str(item)))
        else:
            contents.append(quote_plus(key) + '=' + quote_plus(str(value)))
    return ('&'.join(contents)).encode('utf8')


cdef class FormContent(Content):

    def __init__(self, data: Union[dict[str, str], list[tuple[str, str]]]):
        super().__init__(b'application/x-www-form-urlencoded', write_www_form_urlencoded(data))


cdef class FormPart:
    """
    Represents a single part of a multipart/form-data request.

    Attributes:
        name: The name of the form field (bytes).
        data: The binary content of the form part.
        file_name: The filename if this part represents a file upload (optional).
        content_type: The MIME type of the content (optional).
        charset: The character encoding of the content (optional).
    """

    def __init__(
        self,
        bytes name,
        object data,
        bytes content_type: bytes | None=None,
        bytes file_name: bytes | None=None,
        bytes charset: bytes | None = None,
        int size = 0
    ):
        self.name = name
        self._data = data if isinstance(data, bytes) else None
        self._file = data if not isinstance(data, bytes) else None
        self.file_name = file_name
        self.content_type = content_type
        self.charset = charset
        self.size = size

    @property
    def data(self):
        if isinstance(self._data, bytes):
            return self._data
        if self._file:
            self._file.seek(0)
            return self._file.read()
        return b""

    @property
    def file(self):
        if self._file is None:
            raise TypeError("Missing file data")
        return self._file

    async def stream(self, chunk_size: int = 8192):
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
        """

        def _copy():
            self.file.seek(0)
            with open(path, "wb") as dest:
                bytes_written = shutil.copyfileobj(self.file, dest)
            self.file.seek(0)
            return bytes_written if bytes_written is not None else self.size

        return await asyncio.to_thread(_copy)

    def __eq__(self, other):
        if isinstance(other, FormPart):
            return (other.name == self.name and
                    other.file_name == self.file_name and
                    other.content_type == self.content_type and
                    other.charset == self.charset and
                    other.data == self.data)
        if other is None:
            return False
        return NotImplemented

    def __repr__(self):
        return f'<FormPart {self.name} - at {id(self)}>'


cdef class FileBuffer:
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

    def __init__(self,
                 str name,
                 str file_name,
                 object file,
                 str content_type = None,
                 int size = 0,
                 str charset = None):
        self.name = name
        self.file_name = file_name
        self.content_type = content_type
        self.file = file
        self.size = size
        self._charset = charset

    @classmethod
    def from_form_part(cls, FormPart form_part):
        return cls(
            name=form_part.name.decode(),
            file_name=form_part.file_name.decode() if form_part.file_name else None,
            file=form_part.file,
            content_type=form_part.content_type.decode() if form_part.content_type else None,
            size=form_part.size,
            charset=form_part.charset.decode() if form_part.charset else None,
        )

    def read(self, int size=-1):
        """Read data from the file."""
        return self.file.read(size)

    def seek(self, int offset, int whence=0):
        """Seek to a position in the file."""
        return self.file.seek(offset, whence)

    async def save_to(self, str path):
        """Save file data to a specified path.

        Args:
            path: File path where data should be saved.

        Returns:
            Total number of bytes written.
        """
        def _copy():
            self.file.seek(0)
            with open(path, "wb") as dest:
                bytes_written = shutil.copyfileobj(self.file, dest)
            self.file.seek(0)
            return bytes_written if bytes_written is not None else self.size

        return await asyncio.to_thread(_copy)

    def close(self):
        """Close the underlying file."""
        if hasattr(self.file, 'close'):
            self.file.close()

    def __repr__(self):
        return f"<FileBuffer {self.file_name} ({self.content_type})>"

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


cdef class StreamingFormPart:
    """
    Represents a streaming part of a multipart/form-data request.

    Unlike FormPart, which loads all data into memory, StreamingFormPart provides
    lazy access to file content through async iteration, making it suitable for
    large file uploads without memory pressure.

    Attributes:
        name: The name of the form field (str).
        content_type: The MIME type of the content (optional).
        file_name: The filename if this part represents a file upload (optional).
        charset: The character encoding of the content (optional).
    """

    def __init__(self,
                 str name,
                 object data_stream,
                 str content_type = None,
                 str file_name = None,
                 str charset = None):
        self.name = name
        self.file_name = file_name
        self.content_type = content_type
        self.charset = charset
        self._data_stream = data_stream

    async def stream(self):
        """
        Stream the part data in chunks.

        Yields:
            Byte chunks of the part data.
        """
        async for chunk in self._data_stream:
            yield chunk

    async def save_to(self, str path):
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


cdef class MultiPartFormData(StreamedContent):
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


cdef class ServerSentEvent:
    """
    Represents a single event of a Server-sent event communication, to be used
    in a asynchronous generator.

    Attributes:
        data: An object that will be transmitted to the client, in JSON format.
        event: Optional event name.
        id: Optional event ID to set the EventSource's last event ID value.
        retry: The reconnection time. If the connection to the server is lost,
               the browser will wait for the specified time before attempting
               to reconnect.
        comment: Optional comment.
    """

    def __init__(
        self,
        object data,
        str event = None,
        str id = None,
        int retry = -1,
        str comment = None,
    ):
        """
        Creates an instance of ServerSentEvent
        """
        self.data = data
        self.event = event
        self.id = id
        self.retry = retry
        self.comment = comment

    cpdef str write_data(self):
        return json_settings.dumps(self.data)

    def __repr__(self):
        return f"ServerSentEvent({self.data})"


cdef class TextServerSentEvent(ServerSentEvent):
    """
    Represents a single event of a Server-sent event communication, to be used
    in a asynchronous generator.

    Attributes:
        data: A string that will be transmitted to the client as is.
        event: Optional event name.
        id: Optional event ID to set the EventSource's last event ID value.
        retry: The reconnection time. If the connection to the server is lost,
               the browser will wait for the specified time before attempting
               to reconnect.
        comment: Optional comment.
    """

    def __init__(
        self,
        str data,
        str event = None,
        str id = None,
        int retry = -1,
        str comment = None,
    ):
        super().__init__(data, event, id, retry, comment)

    cpdef str write_data(self):
        # Escape \r\n to avoid issues with data containing EOL
        return self.data.replace("\r", "\\r").replace("\n", "\\n")
