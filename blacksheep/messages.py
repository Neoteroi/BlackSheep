import asyncio
import http
import re
from datetime import timedelta
from json.decoder import JSONDecodeError
from typing import TYPE_CHECKING, Optional
from urllib.parse import parse_qs, quote, unquote, urlencode

from blacksheep.multipart import parse_multipart
from blacksheep.settings.encodings import encodings_settings
from blacksheep.settings.json import json_settings
from blacksheep.utils.time import utcnow

from .contents import (
    ASGIContent,
    Content,
    multiparts_to_dictionary,
    parse_www_form_urlencoded,
)
from .cookies import Cookie, parse_cookie, split_value, write_cookie_for_response
from .exceptions import BadRequest, BadRequestFormat, FailedRequestError, MessageAborted
from .headers import Headers
from .url import URL, build_absolute_url

if TYPE_CHECKING:
    from blacksheep.sessions import Session

_charset_rx = re.compile(rb"charset=([\w\-]+)", re.I)


def parse_charset(value: bytes):
    m = _charset_rx.search(value)
    if m:
        return m.group(1).decode("ascii")
    return None


async def _read_stream(request):
    async for _ in request.content.stream():
        pass


async def _call_soon(coro):
    task = asyncio.create_task(coro)
    asyncio.get_event_loop().call_soon(task.cancel)
    try:
        return await task
    except asyncio.CancelledError:
        return None


class Message:
    def __init__(self, headers):
        self._raw_headers = headers or []

    @property
    def headers(self):
        key = "_headers"
        if key in self.__dict__:
            return self.__dict__[key]
        self.__dict__[key] = Headers(self._raw_headers)
        return self.__dict__[key]

    def with_content(self, content: Content):
        self.content = content
        return self

    def get_first_header(self, key: bytes):
        key = key.lower()
        for header in self._raw_headers:
            if header[0].lower() == key:
                return header[1]

    def get_headers(self, key: bytes):
        results = []
        key = key.lower()
        for header in self._raw_headers:
            if header[0].lower() == key:
                results.append(header[1])
        return results

    def init_prop(self, name: str, value):
        try:
            getattr(self, name)
        except AttributeError:
            setattr(self, name, value)

    def get_headers_tuples(self, key: bytes):
        results = []
        key = key.lower()
        for header in self._raw_headers:
            if header[0].lower() == key:
                results.append(header)
        return results

    def get_single_header(self, key: bytes):
        results = self.get_headers(key)
        if len(results) > 1:
            raise ValueError("Headers contains more than one header with the given key")
        if len(results) < 1:
            raise ValueError("Headers does not contain one header with the given key")
        return results[0]

    def remove_header(self, key: bytes):
        to_remove = []
        key = key.lower()
        for header in self._raw_headers:
            if header[0].lower() == key:
                to_remove.append(header)
        for header in to_remove:
            self._raw_headers.remove(header)

    def remove_headers(self, headers):
        for header in headers:
            self._raw_headers.remove(header)

    def _has_header(self, key: bytes):
        key = key.lower()
        for existing_key, existing_value in self._raw_headers:
            if existing_key.lower() == key:
                return True
        return False

    def has_header(self, key: bytes):
        return self._has_header(key)

    def _add_header(self, key: bytes, value: bytes):
        self._raw_headers.append((key, value))

    def _add_header_if_missing(self, key: bytes, value: bytes):
        if not self._has_header(key):
            self._raw_headers.append((key, value))

    def add_header(self, key: bytes, value: bytes):
        self._raw_headers.append((key, value))

    def set_header(self, key: bytes, value: bytes):
        self.remove_header(key)
        self._raw_headers.append((key, value))

    def content_type(self):
        if hasattr(self, "content") and self.content and self.content.type:
            return self.content.type
        return self.get_first_header(b"content-type")

    async def read(self):
        if hasattr(self, "content") and self.content:
            return await self.content.read()
        return None

    async def stream(self):
        if hasattr(self, "content") and self.content:
            async for chunk in self.content.stream():
                yield chunk
        else:
            yield None

    async def text(self):
        body = await self.read()
        if body is None:
            return ""
        try:
            return body.decode(self.charset)
        except UnicodeDecodeError as decode_error:
            return encodings_settings.decode(body, decode_error)

    async def form(self):
        content_type_value = self.content_type()
        if not content_type_value:
            return None
        if b"application/x-www-form-urlencoded" in content_type_value:
            text = await self.text()
            return parse_www_form_urlencoded(text)
        if b"multipart/form-data;" in content_type_value:
            body = await self.read()
            return multiparts_to_dictionary(list(parse_multipart(body)))
        return None

    async def multipart(self):
        content_type_value = self.content_type()
        if not content_type_value:
            return None
        if b"multipart/form-data;" in content_type_value:
            body = await self.read()
            return list(parse_multipart(body))
        return None

    def declares_content_type(self, type: bytes):
        content_type = self.content_type()
        if not content_type:
            return False
        if type.lower() in content_type.lower():
            return True
        return False

    def declares_json(self):
        return self.declares_content_type(b"json")

    def declares_xml(self):
        return self.declares_content_type(b"xml")

    async def files(self, name=None):
        if isinstance(name, str):
            name = name.encode("ascii")
        content_type = self.content_type()
        if not content_type or b"multipart/form-data;" not in content_type:
            return []
        data = await self.multipart()
        if name:
            return [part for part in data if part.file_name and part.name == name]
        return [part for part in data if part.file_name]

    async def json(self, loads=json_settings.loads):
        if not self.declares_json():
            return None
        text = await self.text()
        if text is None or text == "":
            return None
        try:
            return loads(text)
        except JSONDecodeError as decode_error:
            content_type = self.content_type()
            if content_type and b"json" in content_type:
                raise BadRequestFormat(
                    f"Declared Content-Type is {content_type.decode()} but "
                    f"the content cannot be parsed as JSON.",
                    decode_error,
                )
            raise BadRequestFormat("Cannot parse content as JSON", decode_error)

    def has_body(self):
        content = getattr(self, "content", None)
        if not content or content.length == 0:
            return False
        return True

    @property
    def charset(self):
        content_type = self.content_type()
        if content_type:
            return parse_charset(content_type) or "utf8"
        return "utf8"


def method_without_body(method: str):
    return method in ("GET", "HEAD", "TRACE")


class Request(Message):
    def __init__(self, method: str, url: bytes, headers):
        _url = URL(url) if url else None
        self._raw_headers = headers or []
        self.method = method
        self._url = _url
        self._session = None
        if _url:
            self._path = _url.path
            self._raw_query = _url.query
        else:
            self._path = None
            self._raw_query = None
        self.scope = None
        self.content: Optional[Content] = None

    @property
    def identity(self):
        return self.__dict__.get("_user")

    @identity.setter
    def identity(self, value):
        self.__dict__["_user"] = value

    @property
    def user(self):
        return self.__dict__.get("_user")

    @user.setter
    def user(self, value):
        self.__dict__["_user"] = value

    @property
    def scheme(self) -> str:
        return self.__dict__.get("scheme") or (
            self.scope.get("scheme", "") if self.scope else ""
        )

    @scheme.setter
    def scheme(self, value: str):
        self.__dict__["scheme"] = value

    @property
    def host(self) -> str:
        if not self.__dict__.get("host"):
            if self._url is not None and self._url.is_absolute:
                self.__dict__["host"] = (
                    self._url.host.decode()
                    if isinstance(self._url.host, bytes)
                    else self._url.host
                )
            else:
                host_header = self.get_first_header(b"host")
                if host_header is None:
                    raise BadRequest("Missing Host header")
                self.__dict__["host"] = host_header.decode()
        return self.__dict__["host"]

    @host.setter
    def host(self, value: str) -> None:
        self.__dict__["host"] = value

    @property
    def path(self) -> str:
        return self._path.decode("utf8") if self._path else ""

    @property
    def base_path(self) -> str:
        try:
            return self.__dict__["base_path"]
        except KeyError:
            try:
                return self.scope.get("root_path", "")
            except AttributeError:
                return ""

    @base_path.setter
    def base_path(self, value: str):
        self.__dict__["base_path"] = value

    @property
    def client_ip(self) -> str:
        if getattr(self, "scope", None) is None:
            return ""
        client = self.scope.get("client", ("", 0))
        return client[0]

    @property
    def original_client_ip(self) -> str:
        if "original_client_ip" in self.__dict__:
            return self.__dict__["original_client_ip"]
        return self.client_ip

    @original_client_ip.setter
    def original_client_ip(self, value: str):
        self.__dict__["original_client_ip"] = value

    @property
    def session(self):
        if self._session is None:
            raise TypeError(
                "A session is not configured for this request, activate "
                "sessions using `app.use_sessions` method."
            )
        return self._session

    @session.setter
    def session(self, value: "Session"):
        self._session = value

    @classmethod
    def incoming(cls, method: str, path: bytes, query: bytes, headers):
        request = cls(method, None, headers)
        request._path = path
        request._raw_query = query
        return request

    @property
    def query(self):
        if self._raw_query:
            return parse_qs(self._raw_query.decode("utf8"))
        return {}

    @query.setter
    def query(self, value):
        raw_query = urlencode(value, True).encode("utf8")
        self._raw_query = raw_query
        self.url = self.url.with_query(raw_query)

    @property
    def url(self):
        if self._url:
            return self._url
        if self._raw_query:
            self._url = URL(self._path + b"?" + self._raw_query)
        else:
            self._url = URL(self._path)
        return self._url

    @url.setter
    def url(self, value):
        if value:
            if isinstance(value, bytes):
                _url = URL(value)
            elif isinstance(value, str):
                _url = URL(value.encode("utf8"))
            elif isinstance(value, URL):
                _url = value
            else:
                raise TypeError("Invalid value type, expected bytes, str, or URL")
        else:
            _url = None
        if _url:
            self._path = _url.path
            self._raw_query = _url.query
        else:
            self._path = None
            self._raw_query = None
        self._url = _url
        self.__dict__["host"] = None
        self.remove_header(b"host")

    def __repr__(self):
        return f"<Request {self.method} {self.url.value.decode()}>"

    @property
    def cookies(self):
        cookies = {}
        cookies_headers = self.get_headers(b"cookie")
        if cookies_headers:
            for header in cookies_headers:
                pairs = header.split(b"; ")
                for fragment in pairs:
                    try:
                        name, value = split_value(fragment, b"=")
                    except ValueError:
                        pass
                    else:
                        cookies[unquote(name.decode())] = unquote(
                            value.rstrip(b"; ").decode()
                        )
        return cookies

    def get_cookie(self, name: str):
        return self.cookies.get(name)

    def set_cookie(self, name: str, value: str):
        new_value = (quote(name) + "=" + quote(value)).encode()
        existing_cookie = self.get_first_header(b"cookie")
        if existing_cookie:
            self.set_header(b"cookie", existing_cookie + b";" + new_value)
        else:
            self._raw_headers.append((b"cookie", new_value))

    @property
    def etag(self):
        return self.get_first_header(b"etag")

    @property
    def if_none_match(self):
        return self.get_first_header(b"if-none-match")

    def expect_100_continue(self):
        value = self.get_first_header(b"expect")
        if value and value.lower() == b"100-continue":
            return True
        return False

    async def is_disconnected(self):
        if not isinstance(self.content, ASGIContent):
            raise TypeError(
                "This method is only supported when a request is bound to "
                "an instance of ASGIContent and to an ASGI "
                "request/response cycle."
            )
        self.init_prop("_is_disconnected", False)
        if self._is_disconnected is True:
            return True
        try:
            await _call_soon(_read_stream(self))
        except MessageAborted:
            self._is_disconnected = True
        return self._is_disconnected


class Response(Message):
    def __init__(self, status: int, headers=None, content: Content = None):
        self._raw_headers = headers or []
        self.status = status
        self.content = content

    def __repr__(self):
        return f"<Response {self.status}>"

    @property
    def cookies(self):
        return self.get_cookies()

    @property
    def reason(self) -> str:
        return http.HTTPStatus(self.status).phrase

    def get_cookies(self):
        cookies = {}
        set_cookies_headers = self.get_headers(b"set-cookie")
        if set_cookies_headers:
            for value in set_cookies_headers:
                cookie = parse_cookie(value)
                cookies[cookie.name] = cookie
        return cookies

    def get_cookie(self, name: str):
        set_cookies_headers = self.get_headers(b"set-cookie")
        if set_cookies_headers:
            for value in set_cookies_headers:
                cookie = parse_cookie(value)
                if cookie.name == name:
                    return cookie
        return None

    def set_cookie(self, cookie: Cookie):
        self._raw_headers.append((b"set-cookie", write_cookie_for_response(cookie)))

    def set_cookies(self, cookies):
        for cookie in cookies:
            self.set_cookie(cookie)

    def unset_cookie(self, name: str):
        self.set_cookie(Cookie(name, "", utcnow() - timedelta(days=365)))

    def remove_cookie(self, name: str):
        to_remove = []
        set_cookies_headers = self.get_headers_tuples(b"set-cookie")
        if set_cookies_headers:
            for value in set_cookies_headers:
                cookie = parse_cookie(value[1])
                if cookie.name == name:
                    to_remove.append(value)
        self.remove_headers(to_remove)

    def is_redirect(self):
        return self.status in {301, 302, 303, 307, 308}

    async def raise_for_status(self):
        if not (200 <= self.status < 300):
            raise FailedRequestError(self.status, await self.text())


def is_cors_request(request: "Request"):
    return bool(request.get_first_header(b"Origin"))


def is_cors_preflight_request(request: "Request"):
    if request.method != "OPTIONS" or not is_cors_request(request):
        return False
    next_request_method = request.get_first_header(b"Access-Control-Request-Method")
    return bool(next_request_method)


def ensure_bytes(value):
    if isinstance(value, str):
        return value.encode()
    if isinstance(value, bytes):
        return value
    raise ValueError("Input value must be bytes or str")


def get_request_absolute_url(request: "Request"):
    if request.url.is_absolute:
        return request.url
    return build_absolute_url(
        ensure_bytes(request.scheme),
        ensure_bytes(request.host),
        ensure_bytes(request.base_path),
        request._path,
    )


def get_absolute_url_to_path(request: "Request", path: str):
    return build_absolute_url(
        ensure_bytes(request.scheme),
        ensure_bytes(request.host),
        ensure_bytes(request.base_path),
        ensure_bytes(path),
    )
