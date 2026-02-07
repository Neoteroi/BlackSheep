import asyncio
import http
import re
from datetime import datetime, timedelta
from json.decoder import JSONDecodeError
from urllib.parse import parse_qs, quote, unquote, urlencode

from guardpost import Identity

from blacksheep.sessions import Session
from blacksheep.settings.encodings import encodings_settings
from blacksheep.settings.json import json_settings
from blacksheep.utils.time import utcnow

from .contents cimport (
    ASGIContent,
    Content,
    parse_www_form_urlencoded,
)
from .cookies cimport Cookie, parse_cookie, split_value, write_cookie_for_response
from .exceptions cimport (
    BadRequest,
    BadRequestFormat,
    FailedRequestError,
    MessageAborted,
)
from .headers cimport Headers
from .url cimport URL, build_absolute_url

_charset_rx = re.compile(rb"charset=([\w\-]+)", re.I)


cpdef str parse_charset(bytes value):
    m = _charset_rx.search(value)
    if m:
        return m.group(1).decode("ascii")
    return None


async def _read_stream(request):
    async for _ in request.content.stream():  # type: ignore
        pass


async def _call_soon(coro):
    """
    Returns the output of a coroutine if its result is immediately available,
    otherwise None.
    """
    task = asyncio.create_task(coro)
    asyncio.get_event_loop().call_soon(task.cancel)
    try:
        return await task
    except asyncio.CancelledError:
        return None


def _encode(value):
    return value.encode("utf8") if value else None


async def _multipart_to_dict_streaming(
    stream_iter,
    spool_max_size=1024 * 1024,
):
    """
    Convert streaming multipart parts to dictionary with memory-efficient file handling.

    Files are wrapped in UploadFile with SpooledTemporaryFile:
    - Small files (<1MB): Kept in memory for performance
    - Large files (>1MB): Automatically spooled to temporary disk files
    - Form fields: Buffered in memory with size limits

    Args:
        stream_iter: Async iterator of StreamingFormPart objects
        spool_max_size: Threshold for spooling files to disk (default: 1MB)

    Returns:
        Dictionary with form data and UploadFile instances for files
    """
    from collections import defaultdict
    from tempfile import SpooledTemporaryFile
    from .contents import FormPart

    data = defaultdict(list)

    async for part in stream_iter:
        key = part.name

        spooled_file = SpooledTemporaryFile(max_size=spool_max_size, mode="w+b")
        total_size = 0

        async for chunk in part.stream():
            spooled_file.write(chunk)
            total_size += len(chunk)
        spooled_file.seek(0)

        # TODO: encoding below is for backward compatibility
        # TODO: remove in v3
        item = FormPart(
            name=_encode(part.name),
            data=spooled_file,
            file_name=_encode(part.file_name),
            content_type=_encode(part.content_type),
            size=total_size,
            charset=_encode(part.charset),
        )
        data[key].append(item)

    return dict(data)


cdef class Message:

    def __init__(self, list headers):
        self._raw_headers = headers or []

    @property
    def headers(self):
        cdef str key = '_headers'
        if key in self.__dict__:
            return self.__dict__[key]
        self.__dict__[key] = Headers(self._raw_headers)
        return self.__dict__[key]

    cpdef Message with_content(self, Content content):
        self.content = content
        return self

    cpdef bytes get_first_header(self, bytes key):
        cdef tuple header
        key = key.lower()
        for header in self._raw_headers:
            if header[0].lower() == key:
                return header[1]

    cpdef list get_headers(self, bytes key):
        cdef list results = []
        cdef tuple header
        key = key.lower()
        for header in self._raw_headers:
            if header[0].lower() == key:
                results.append(header[1])
        return results

    cdef void init_prop(self, str name, object value):
        """
        This method is for internal use and only accessible in Cython.
        It initializes a new property on the request object, for rare scenarios
        where an additional property can be useful. It would also be possible
        to use a weakref.WeakKeyDictionary to store additional information
        about request objects when useful, but for simplicity this method uses
        the object __dict__.
        """
        try:
            getattr(self, name)
        except AttributeError:
            setattr(self, name, value)

    cdef list get_headers_tuples(self, bytes key):
        cdef list results = []
        cdef tuple header
        key = key.lower()
        for header in self._raw_headers:
            if header[0].lower() == key:
                results.append(header)
        return results

    cpdef bytes get_single_header(self, bytes key):
        cdef list results = self.get_headers(key)
        if len(results) > 1:
            raise ValueError('Headers contains more than one header with the given key')
        if len(results) < 1:
            raise ValueError('Headers does not contain one header with the given key')
        return results[0]

    cpdef void remove_header(self, bytes key):
        cdef tuple header
        cdef list to_remove = []
        key = key.lower()
        for header in self._raw_headers:
            if header[0].lower() == key:
                to_remove.append(header)

        for header in to_remove:
            self._raw_headers.remove(header)

    cdef void remove_headers(self, list headers):
        cdef tuple header
        for header in headers:
            self._raw_headers.remove(header)

    cdef bint _has_header(self, bytes key):
        cdef bytes existing_key, existing_value
        key = key.lower()
        for existing_key, existing_value in self._raw_headers:
            if existing_key.lower() == key:
                return True
        return False

    cpdef bint has_header(self, bytes key):
        return self._has_header(key)

    cdef void _add_header(self, bytes key, bytes value):
        self._raw_headers.append((key, value))

    cdef void _add_header_if_missing(self, bytes key, bytes value):
        if not self._has_header(key):
            self._raw_headers.append((key, value))

    cpdef void add_header(self, bytes key, bytes value):
        self._raw_headers.append((key, value))

    cpdef void set_header(self, bytes key, bytes value):
        self.remove_header(key)
        self._raw_headers.append((key, value))

    cpdef bytes content_type(self):
        if self.content and self.content.type:
            return self.content.type
        return self.get_first_header(b'content-type')

    async def read(self):
        if self.content:
            return await self.content.read()
        return None

    async def stream(self):
        if self.content:
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

    async def form(self, simplify_fields=True):
        """
        Parse form data from the request with memory-efficient file handling, but
        reading text inputs whole in memory. To handle big text input fields, use
        `multipart()` which doesn't read automatically text fields in memory or
        `multipart_stream()` for streaming without any buffering.

        This method now uses SpooledTemporaryFile for multipart uploads:
        - Small files (<1MB): Kept in memory for performance
        - Large files (>1MB): Automatically spooled to temporary disk files
        - No memory exhaustion on large uploads!

        File uploads are returned as `UploadFile` instances (not bytes!).
        Form fields are returned as strings.

        Returns:
            Dictionary with form data. File uploads are UploadFile instances.

        Example:
            ```python
            form_data = await request.form()

            # Form fields are strings
            name = form_data.get("name")  # str

            # Files are UploadFile instances
            avatar = form_data.get("avatar")  # UploadFile
            if isinstance(avatar, UploadFile):
                # Save without loading into memory
                with open(f"uploads/{avatar.filename}", "wb") as f:
                    avatar.seek(0)
                    f.write(avatar.read())
                avatar.close()
            ```
        """
        cdef str text
        cdef bytes content_type_value = self.content_type()

        if not content_type_value:
            return None

        if hasattr(self, '_form_data'):
            if b'multipart/form-data;' in content_type_value and simplify_fields:
                # This is just to not break backward compatibility.
                # TODO: consider removing this in v3
                from .contents import simplify_multipart_data
                return simplify_multipart_data(self._form_data)
            return self._form_data

        if b'application/x-www-form-urlencoded' in content_type_value:
            text = await self.text()
            return parse_www_form_urlencoded(text)
        if b'multipart/form-data;' in content_type_value:
            # In this case, multipart/form-data is handled in a memory efficient way,
            # which does not support reading the request stream more than once and
            # requires disposal at the end of the request-response cycle.
            # Request form is intentionally not kept in memory if multipart_stream
            # is read directly by the user.
            from .contents import simplify_multipart_data
            self._form_data = await _multipart_to_dict_streaming(
                self.multipart_stream()
            )
            return (
                simplify_multipart_data(self._form_data)
                if simplify_fields
                else self._form_data
            )
        return None

    async def multipart(self):
        """
        Parse multipart/form-data with memory-efficient part handling, relying on
        SpooledTemporaryFile. **Note:** for true streaming without any buffering,
        use `multipart_stream()`.

        This method uses SpooledTemporaryFile for field and file uploads:
        - Small data (<1MB): Kept in memory
        - Large data (>1MB): Automatically spooled to temporary disk files

        Returns:
            List of FormPart, or None
        """
        items = []
        data = await self.form(simplify_fields=False)
        if not data:
            return items
        for _, values in data.items():
            for value in values:
                items.append(value)
        return items

    async def multipart_stream(self):
        """
        Parse multipart/form-data lazily from the request stream.

        This method streams and parses multipart data without loading the entire
        request body into memory, making it suitable for large file uploads and large
        text uploads.

        Yields:
            FormPart objects as they are parsed from the stream.

        Example:
            ```python
            async def upload_handler(request):
                async for part in request.multipart_stream():
                    if part.file_name:
                        # Process file part
                        await save_file(part.file_name, part.data)
                    else:
                        # Process form field
                        value = part.data.decode('utf-8')
            ```
        """
        cdef bytes content_type_value = self.content_type()
        if not content_type_value:
            return

        if b'multipart/form-data;' not in content_type_value:
            return

        # Extract boundary from Content-Type header
        # e.g., "multipart/form-data; boundary=----WebKitFormBoundary..."
        from blacksheep.multipart import get_boundary_from_header, parse_multipart_async
        try:
            boundary = get_boundary_from_header(content_type_value)
        except (ValueError, IndexError):
            return

        async for part in parse_multipart_async(self.stream(), boundary):
            yield part

    cpdef bint declares_content_type(self, bytes type):
        cdef bytes content_type = self.content_type()
        if not content_type:
            return False

        # NB: we look for substring intentionally here
        if type.lower() in content_type.lower():
            return True
        return False

    cpdef bint declares_json(self):
        return self.declares_content_type(b'json')

    cpdef bint declares_xml(self):
        return self.declares_content_type(b'xml')

    async def files(self, name=None):
        if isinstance(name, str):
            # Note: FormPart fields are not decoded (TODO: decode them in v3).
            name = name.encode('utf8')
        data = await self.multipart()
        if data is None:
            return []
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
            if content_type and b'json' in content_type:
                # NB: content type could also be "application/problem+json";
                # so we don't check for application/json in this case
                raise BadRequestFormat(
                    f'Declared Content-Type is {content_type.decode()} but '
                    f'the content cannot be parsed as JSON.', decode_error
                )
            raise BadRequestFormat(
                f'Cannot parse content as JSON',
                decode_error
            )

    cpdef bint has_body(self):
        cdef Content content = self.content
        if not content or content.length == 0:
            return False
        # NB: if we use chunked encoding, we don't know the content.length;
        # and it is set to -1 (in contents.pyx), therefore it is handled
        # properly
        return True

    @property
    def charset(self):
        content_type = self.content_type()
        if content_type:
            return parse_charset(content_type) or 'utf8'
        return 'utf8'


cpdef bint method_without_body(str method):
    return method == 'GET' or method == 'HEAD' or method == 'TRACE'


cdef class Request(Message):

    def __init__(
        self,
        str method,
        bytes url,
        list headers
    ):
        cdef URL _url = URL(url) if url else None
        self._raw_headers = headers or []
        self.method = method
        self._url = _url
        self._session = None
        if _url:
            self._path = _url.path
            self._raw_query = _url.query

    # TODO: deprecate the 'identity' property in the future. This requires a
    # breaking change in guardpost, too.
    @property
    def identity(self):
        return self.user

    @identity.setter
    def identity(self, value):
        self.__dict__["_user"] = value

    @property
    def user(self):
        try:
            return self.__dict__["_user"]
        except KeyError:
            self.__dict__["_user"] = Identity()  # no claims, unauthenticated
            return self.__dict__["_user"]

    @user.setter
    def user(self, value):
        self.__dict__["_user"] = value

    @property
    def scheme(self) -> str:
        return self.__dict__.get("scheme") or (self.scope.get("scheme", "") if self.scope else "")

    @scheme.setter
    def scheme(self, value: str):
        # this can be set, for example when handling forward headers
        self.__dict__["scheme"] = value

    @property
    def host(self) -> str:
        if not self.__dict__.get("host"):
            if self._url is not None and self._url.is_absolute:
                self.__dict__["host"] = self._url.host.decode()
            else:
                # default to host header
                host_header = self.get_first_header(b'host')
                if host_header is None:
                    raise BadRequest("Missing Host header")
                self.__dict__["host"] = host_header.decode()
        return self.__dict__["host"]

    @host.setter
    def host(self, value: str) -> None:
        # this can be set, for example when handling forward headers
        self.__dict__["host"] = value

    @property
    def path(self) -> str:
        return self._path.decode("utf8")

    @property
    def base_path(self) -> str:
        # 1. if a base path was explicitly set, use it
        # 2. if a root_path is set in the ASGI scope, use it
        # 3. default to empty string otherwise
        try:
            return self.__dict__["base_path"]
        except KeyError:
            try:
                return self.scope.get("root_path", "")
            except AttributeError:
                return ""

    @base_path.setter
    def base_path(self, value: str):
        # this can be set, for example when handling forward headers
        self.__dict__["base_path"] = value

    @property
    def client_ip(self) -> str:
        if self.scope is None:
            return ""
        client_ip, client_port = self.scope.get("client", ("", 0))
        return client_ip

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
    def session(self, value: Session):
        self._session = value

    @classmethod
    def incoming(cls, str method, bytes path, bytes query, list headers):
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
        cdef bytes raw_query
        raw_query = urlencode(value, True).encode("utf8")
        self._raw_query = raw_query
        self.url = self.url.with_query(raw_query)

    @property
    def url(self):
        if self._url:
            return self._url

        if self._raw_query:
            self._url = URL(self._path + b'?' + self._raw_query)
        else:
            self._url = URL(self._path)
        return self._url

    @url.setter
    def url(self, object value):
        cdef URL _url

        if value:
            if isinstance(value, bytes):
                _url = URL(value)
            elif isinstance(value, str):
                _url = URL(value.encode('utf8'))
            elif isinstance(value, URL):
                _url = value
            else:
                raise TypeError('Invalid value type, expected bytes, str, or URL')
        else:
            _url = None

        if _url:
            self._path = _url.path
            self._raw_query = _url.query
        else:
            self._path = None
            self._raw_query = None
        self._url = _url
        # unset the cached host
        self.__dict__["host"] = None
        self.remove_header(b"host")

    def __repr__(self):
        return f'<Request {self.method} {self.url.value.decode()}>'

    @property
    def cookies(self):
        cdef bytes header
        cdef list cookies_headers
        cdef dict cookies = {}

        cookies_headers = self.get_headers(b'cookie')
        if cookies_headers:
            for header in cookies_headers:
                # a single cookie header is expected from the client, but anyway here
                # multiple headers are handled:
                pairs = header.split(b'; ')

                for fragment in pairs:
                    try:
                        name, value = split_value(fragment, b"=")
                    except ValueError as unpack_error:
                        # discard cookie: in this case it's better to eat the exception
                        # than blocking a request just because a cookie is malformed
                        pass
                    else:
                        cookies[unquote(name.decode())] = unquote(value.rstrip(b'; ').decode())
        return cookies

    def get_cookie(self, str name):
        return self.cookies.get(name)

    def set_cookie(self, str name, str value):
        """
        Sets a cookie in the request. This method also ensures that a single
        `cookie` header is set on the request.
        """
        cdef bytes new_value
        cdef bytes existing_cookie

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

    cpdef bint expect_100_continue(self):
        cdef bytes value
        value = self.get_first_header(b'expect')
        if value and value.lower() == b'100-continue':
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

    def dispose(self):
        if hasattr(self, '_form_data') and self._form_data:
            for parts in self._form_data.values():
                for part in parts:
                    if part.file:
                        part.file.close()
        if self.content:
            self.content.dispose()  # type: ignore


cdef class Response(Message):

    def __init__(
        self,
        int status,
        list headers = None,
        Content content = None
    ):
        self._raw_headers = headers or []
        self.status = status
        self.content = content

    def __repr__(self):
        return f'<Response {self.status}>'

    @property
    def cookies(self):
        return self.get_cookies()

    @property
    def reason(self) -> str:
        return http.HTTPStatus(self.status).phrase

    def get_cookies(self):
        cdef bytes value
        cdef Cookie cookie
        cdef dict cookies
        cdef list set_cookies_headers

        cookies = {}
        set_cookies_headers = self.get_headers(b'set-cookie')
        if set_cookies_headers:
            for value in set_cookies_headers:
                cookie = parse_cookie(value)
                cookies[cookie.name] = cookie
        return cookies

    def get_cookie(self, str name):
        cdef bytes value
        cdef list set_cookies_headers = self.get_headers(b'set-cookie')

        if set_cookies_headers:
            for value in set_cookies_headers:
                cookie = parse_cookie(value)
                if cookie.name == name:
                    return cookie

        return None

    def set_cookie(self, Cookie cookie):
        self._raw_headers.append((b'set-cookie', write_cookie_for_response(cookie)))

    def set_cookies(self, list cookies):
        cdef Cookie cookie
        for cookie in cookies:
            self.set_cookie(cookie)

    def unset_cookie(self, str name):
        self.set_cookie(
            Cookie(
                name,
                '',
                utcnow() - timedelta(days=365)
            )
        )

    def remove_cookie(self, str name):
        cdef list to_remove = []
        cdef tuple value
        cdef list set_cookies_headers = self.get_headers_tuples(b'set-cookie')

        if set_cookies_headers:
            for value in set_cookies_headers:
                cookie = parse_cookie(value[1])
                if cookie.name == name:
                    to_remove.append(value)

        self.remove_headers(to_remove)

    cpdef bint is_redirect(self):
        return self.status in {301, 302, 303, 307, 308}

    async def raise_for_status(self):
        if not (200 <= self.status < 300):
            raise FailedRequestError(self.status, await self.text())


cpdef bint is_cors_request(Request request):
    return bool(request.get_first_header(b"Origin"))


cpdef bint is_cors_preflight_request(Request request):
    if request.method != "OPTIONS" or not is_cors_request(request):
        return False

    next_request_method = request.get_first_header(
        b"Access-Control-Request-Method"
    )

    return bool(next_request_method)


cdef bytes ensure_bytes(value):
    if isinstance(value, str):
        return value.encode()
    if isinstance(value, bytes):
        return value
    raise ValueError("Input value must be bytes or str")


cpdef URL get_request_absolute_url(Request request):
    if request.url.is_absolute:
        # outgoing request
        return request.url

    # incoming request
    return build_absolute_url(
        ensure_bytes(request.scheme),
        ensure_bytes(request.host),
        ensure_bytes(request.base_path),
        request._path
    )


cpdef URL get_absolute_url_to_path(Request request, str path):
    return build_absolute_url(
        ensure_bytes(request.scheme),
        ensure_bytes(request.host),
        ensure_bytes(request.base_path),
        ensure_bytes(path)
    )
