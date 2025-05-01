import uuid
from typing import (
    Any,
    AsyncIterable,
    Awaitable,
    Callable,
    Dict,
    List,
    Optional,
    Tuple,
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
    def __init__(self, data: Union[Dict[str, str], List[Tuple[str, str]]]):
        """
        Creates an instance of FormContent class, with application/x-www-form-urlencoded
        type, and bytes data serialized from the given dictionary.

        :param data: data to be serialized.
        """
        super().__init__(b"application/x-www-form-urlencoded", b"")

class FormPart:
    def __init__(
        self,
        name: bytes,
        data: bytes,
        content_type: Optional[bytes] = None,
        file_name: Optional[bytes] = None,
        charset: Optional[bytes] = None,
    ):
        self.name = name
        self.data = data
        self.file_name = file_name
        self.content_type = content_type
        self.charset = charset

    def __repr__(self):
        return f"<FormPart {self.name} - at {id(self)}>"

class MultiPartFormData(Content):
    def __init__(self, parts: List[FormPart]):
        self.parts = parts
        self.boundary = b"------" + str(uuid.uuid4()).replace("-", "").encode()
        super().__init__(b"multipart/form-data; boundary=" + self.boundary, b"")

def parse_www_form(content: str) -> Dict[str, Union[str, List[str]]]:
    """Parses application/x-www-form-urlencoded content"""

def write_www_form_urlencoded(
    data: Union[Dict[str, str], List[Tuple[str, str]]],
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
        event: Optional[str] = None,
        id: Optional[str] = None,
        retry: int = -1,
        comment: Optional[str] = None,
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
        event: Optional[str] = None,
        id: Optional[str] = None,
        retry: int = -1,
        comment: Optional[str] = None,
    ):
        super().__init__(data, event, id, retry, comment)

    def write_data(self) -> str: ...
