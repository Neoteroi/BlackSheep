import json
from typing import Dict, Generator, List, Union, Optional, Any, Callable
from .url import URL
from .contents import Content, FormPart
from .headers import HeaderType, Headers
from .cookies import Cookie
from guardpost.authentication import Identity, User


class Message:

    @property
    def headers(self) -> Headers: ...

    def content_type(self) -> bytes: ...

    def with_content(self, content: Content) -> Message: ...

    def get_first_header(self, key: bytes) -> bytes: ...

    def get_headers(self, key: bytes) -> List[bytes]: ...

    def get_single_header(self, key: bytes) -> bytes: ...

    def remove_header(self, key: bytes): ...

    def has_header(self, key: bytes) -> bool: ...

    def add_header(self, name: bytes, value: bytes): ...

    def set_header(self, key: bytes, value: bytes): ...

    def content_type(self) -> bytes: ...

    async def read(self) -> Optional[bytes]: ...

    async def stream(self) -> Generator[bytes, None, None]: ...

    async def text(self) -> str: ...

    async def form(self) -> Union[Dict[str, str], Dict[str, List[str]], None]:
        """Returns values read either from multipart or www-form-urlencoded payload.

        This function adopts some compromises to provide a consistent api, returning a dictionary of key: values.
        If a key is unique, the value is a single string; if a key is duplicated (licit in both form types),
        the value is a list of strings.

        Multipart form parts values that can be decoded as UTF8 are decoded, otherwise kept as raw bytes.
        In case of ambiguity, use the dedicated `multiparts()` method.
        """

    async def multipart(self) -> List[FormPart]:
        """Returns parts read from multipart/form-data, if present, otherwise None"""

    def declares_content_type(self, type: bytes) -> bool: ...

    def declares_json(self) -> bool: ...

    def declares_xml(self) -> bool: ...

    async def files(self, name: Optional[str] = None) -> List[FormPart]: ...

    async def json(self, loads: Callable[[str], Any]=json.loads) -> Any: ...

    def has_body(self) -> bool: ...

    @property
    def charset(self) -> str: ...


Cookies = Dict[str, Cookie]


def method_without_body(method: str) -> bool: ...


class Request(Message):

    def __init__(self,
                 method: str,
                 url: bytes,
                 headers: Optional[List[HeaderType]]):
        self.method = ... # type: str
        self.url = ... # type: URL
        self.headers = headers
        self.route_values: Optional[Dict[str, str]] = ...
        self.content: Optional[Content] = ...
        self.identity: Union[None, Identity, User] = ...

    @classmethod
    def incoming(cls, method: str, path: bytes, query: bytes, headers: List[HeaderType]) -> Request: ...

    @property
    def query(self) -> Dict[str, List[str]]: ...

    @property
    def url(self) -> URL: ...

    @url.setter
    def url(self, value: Union[URL, bytes, str]): ...

    def __repr__(self):
        return f'<Request {self.method} {self.url.value.decode()}>'

    @property
    def cookies(self) -> Cookies: ...

    def get_cookies(self) -> Cookies: ...

    def get_cookie(self, name: bytes) -> Optional[Cookie]: ...

    def set_cookie(self, cookie: Cookie): ...

    def set_cookies(self, cookies: List[Cookie]): ...

    @property
    def etag(self) -> Optional[bytes]: ...

    @property
    def if_none_match(self) -> Optional[bytes]: ...

    def expect_100_continue(self) -> bool: ...


class Response(Message):

    def __init__(self,
                 status: int,
                 headers: Optional[List[HeaderType]] = None,
                 content: Optional[Content] = None):
        self.__headers = headers or []
        self.status = status
        self.content = content

    def __repr__(self):
        return f'<Response {self.status}>'

    @property
    def cookies(self) -> Cookies: ...

    @property
    def reason(self) -> str: ...

    def get_cookies(self) -> Cookies: ...

    def get_cookie(self, name: bytes) -> Optional[Cookie]: ...

    def set_cookie(self, cookie: Cookie): ...

    def set_cookies(self, cookies: List[Cookie]): ...

    def unset_cookie(self, name: bytes): ...

    def remove_cookie(self, name: bytes): ...

    def is_redirect(self) -> bool: ...
