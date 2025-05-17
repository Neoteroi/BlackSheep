import uuid
from collections.abc import MutableSequence
from inspect import isasyncgenfunction
from typing import Dict, List, Optional, Tuple, Union
from urllib.parse import parse_qsl, quote_plus

from blacksheep.settings.json import json_settings

from .exceptions import MessageAborted


class Content:
    def __init__(self, content_type: bytes, data: bytes):
        self.type = content_type
        self.body = data
        self.length = len(data)

    async def read(self):
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


def write_www_form_urlencoded(data: Union[dict, list]) -> bytes:
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
    def __init__(self, data: Union[Dict[str, str], List[Tuple[str, str]]]):
        super().__init__(
            b"application/x-www-form-urlencoded", write_www_form_urlencoded(data)
        )


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
        event: Optional[str] = None,
        id: Optional[str] = None,
        retry: Optional[int] = -1,
        comment: Optional[str] = None,
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
        event: Optional[str] = None,
        id: Optional[str] = None,
        retry: Optional[int] = -1,
        comment: Optional[str] = None,
    ):
        super().__init__(data, event, id, retry, comment)

    def write_data(self) -> str:
        return self.data.replace("\r", "\\r").replace("\n", "\\n")
