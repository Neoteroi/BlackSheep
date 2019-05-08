from .url cimport URL
from .exceptions cimport BadRequestFormat, InvalidOperation, MessageAborted
from .headers cimport Headers, Header
from .cookies cimport Cookie, parse_cookie, datetime_to_cookie_format
from .contents cimport Content, extract_multipart_form_data_boundary, parse_www_form_urlencoded, parse_multipart_form_data


import re
import cchardet as chardet
from asyncio import Event
from urllib.parse import parse_qs, unquote
from json import loads as json_loads
from json.decoder import JSONDecodeError
from datetime import datetime, timedelta
from typing import Union, Dict, List, Optional


cdef int get_content_length(Headers headers):
    header = headers.get_single(b'content-length')
    if header:
        return int(header.value)
    return -1


cdef bint get_is_chunked_encoding(Headers headers):
    cdef Header header
    header = headers.get_single(b'transfer-encoding')
    if header and b'chunked' in header.value.lower():
        return True
    return False


_charset_rx = re.compile(b'charset=([^;]+)\\s', re.I)


cpdef str parse_charset(bytes value):
    m = _charset_rx.match(value)
    if m:
        return m.group(1).decode('utf8')
    return None


cdef class Message:

    def __init__(self, 
                 Headers headers, 
                 Content content):
        self.headers = headers or Headers()
        self.content = content
        self._cookies = None
        self._raw_body = bytearray()
        self.complete = Event()
        self._form_data = None
        self.aborted = False
        if content:
            self.complete.set()

    @property
    def raw_body(self):
        return self._raw_body

    cpdef void set_content(self, Content content):
        if content:
            self._raw_body.clear()
            if isinstance(content.body, (bytes, bytearray)):
                self._raw_body.extend(content.body)
            self.complete.set()
        else:
            self.complete.clear()
            self._raw_body.clear()

    cdef void on_body(self, bytes chunk):
        self._raw_body.extend(chunk)

    cpdef void extend_body(self, bytes chunk):
        self._raw_body.extend(chunk)

    async def read(self) -> bytes:
        await self.complete.wait()

        if self.aborted:
            # this happens when a connection is lost, or closed by the client while
            # request content is being sent, and the request headers were received and parsed
            # in other words, the request content is not complete; we can only throw here
            raise MessageAborted()

        if not self._raw_body and self.content:
            # NB: this will happen realistically only in tests, not in real use cases
            # we don't want to always extend raw_body with content bytes, it's not necessary for outgoing
            # requests and responses: this is useful for incoming messages!
            if isinstance(self.content.body, (bytes, bytearray)):
                self._raw_body.extend(self.content.body)
        return bytes(self._raw_body)

    async def text(self) -> str:
        body = await self.read()
        try:
            return body.decode(self.charset)
        except UnicodeDecodeError:
            # this can happen when the server returned a declared charset,
            # but its content is not actually using the declared encoding
            # a common encoding is 'ISO-8859-1', so before using chardet, we try with this
            if self.charset != 'ISO-8859-1':
                try:
                    return body.decode('ISO-8859-1')
                except UnicodeDecodeError:
                    # fallback to chardet;
                    result = chardet.detect(body)
                    encoding = result['encoding']
                    return body.decode(encoding)

    async def form(self):
        if self._form_data is not None:
            return self._form_data
        content_type = self.headers.get_single(b'content-type')

        if not content_type:
            return {}

        content_type_value = content_type.value

        if b'application/x-www-form-urlencoded' in content_type_value:
            text = await self.text()
            self._form_data = parse_www_form_urlencoded(text)
            return self._form_data

        if b'multipart/form-data;' in content_type_value:
            body = await self.read()
            boundary = extract_multipart_form_data_boundary(content_type_value)
            self._form_data = list(parse_multipart_form_data(body, boundary))
            return self._form_data
        self._form_data = {}

    cpdef bint declares_content_type(self, bytes type):
        cdef Header header
        header = self.headers.get_first(b'content-type')
        if not header:
            return False

        if type.lower() in header.value.lower():
            return True
        return False

    cpdef bint declares_json(self):
        return self.declares_content_type(b'json')

    cpdef bint declares_xml(self):
        return self.declares_content_type(b'xml')

    async def files(self, name=None):
        if isinstance(name, str):
            name = name.encode('ascii')

        content_type = self.headers.get_single(b'content-type')

        if not content_type or b'multipart/form-data;' not in content_type.value:
            return []
        data = await self.form()
        if name:
            return [part for part in data if part.file_name and part.name == name]
        return [part for part in data if part.file_name]

    async def json(self, loads=json_loads):
        text = await self.text()
        try:
            return loads(text)
        except JSONDecodeError as decode_error:
            content_type = self.headers.get_single(b'content-type')
            if content_type and b'json' in content_type.value:
                # NB: content type could also be "application/problem+json"; so we don't check for
                # application/json in this case
                raise BadRequestFormat(f'Declared Content-Type is {content_type.value.decode()} but the content '
                                       f'cannot be parsed as JSON.',
                                       decode_error)
            raise InvalidOperation(f'Cannot parse content as JSON; declared Content-Type is '
                                   f'{content_type.value.decode()}.',
                                   decode_error)

    cpdef bint has_body(self):
        cdef Content content = self.content
        if not content or content.length == 0:
            return False
        # NB: if we use chunked encoding, we don't know the content.length;
        # and it is set to -1 (in contents.pyx), therefore it is handled properly
        return True

    @property
    def charset(self):
        content_type = self.headers.get_single(b'content-type')
        if content_type:
            return parse_charset(content_type.value) or 'utf8'
        return 'utf8'


cdef class Request(Message):

    def __init__(self,
                 bytes method,
                 bytes url,
                 Headers headers,
                 Content content):
        super().__init__(headers, content)
        self.url = URL(url)
        self.method = method
        self._query = None
        self.route_values = None
        self.active = True
        self.services = None
        if method in {b'GET', b'HEAD', b'TRACE'}:
            self.complete.set()  # methods without body
        
    def __repr__(self):
        return f'<Request {self.method.decode()} {self.url.value.decode()}>'

    @property
    def query(self):
        if self._query is None:
            if self.url.query is None:
                self._query = {}
            else:
                self._query = parse_qs(self.url.query.decode('utf8'))
        return self._query

    @property
    def cookies(self):
        cdef list pairs
        cdef bytes name
        cdef bytes value
        cdef bytes fragment
        if self._cookies is not None:
            return self._cookies

        cookies = {}
        if b'cookie' in self.headers:
            # a single cookie header is expected from the client, but anyway here the case of
            # multiple headers is handled:
            for header in self.headers.get(b'cookie'):
                pairs = header.value.split(b'; ')

                for fragment in pairs:
                    try:
                        name, value = fragment.split(b'=')
                    except ValueError as unpack_error:
                        # discard cookie: in this case it's better to eat the exception
                        # than blocking a request just because a cookie is malformed
                        pass
                    else:
                        cookies[unquote(name.decode()).encode()] = unquote(value.rstrip(b'; ').decode()).encode()

        self._cookies = cookies
        return cookies

    def get_cookie(self, bytes name):
        return self.cookies.get(name)

    def set_cookie(self, bytes name, bytes value):
        self.cookies[name] = value

    def set_cookies(self, list cookies):
        cdef bytes name, value
        for name, value in cookies:
            self.set_cookie(name, value)

    def unset_cookie(self, bytes name):
        try:
            del self.cookies[name]
        except KeyError:
            pass

    @property
    def etag(self):
        return self.headers.get(b'etag')

    @property
    def if_none_match(self):
        return self.headers.get_first(b'if-none-match')

    cpdef bint expect_100_continue(self):
        cdef Header header
        header = self.headers.get_first(b'expect')
        if header and header.value.lower() == b'100-continue':
            return True
        return False


cdef class Response(Message):

    def __init__(self,
                 int status,
                 Headers headers=None,
                 Content content=None):
        super().__init__(headers or Headers(), content)
        self.status = status
        self.active = True

    def __repr__(self):
        return f'<Response {self.status}>'

    @property
    def cookies(self):
        if self._cookies is not None:
            return self._cookies

        cookies = {}
        if b'set-cookie' in self.headers:
            for header in self.headers.get(b'set-cookie'):
                cookie = parse_cookie(header.value)
                cookies[cookie.name] = cookie
        self._cookies = cookies
        return cookies

    def get_cookie(self, bytes name):
        return self.cookies.get(name)

    def set_cookie(self, Cookie cookie):
        self.cookies[cookie.name] = cookie

    def set_cookies(self, list cookies):
        cdef Cookie cookie
        for cookie in cookies:
            self.set_cookie(cookie)

    def unset_cookie(self, bytes name):
        self.set_cookie(Cookie(name, b'', datetime_to_cookie_format(datetime.utcnow() - timedelta(days=365))))

    def remove_cookie(self, bytes name):
        try:
            del self.cookies[name]
        except KeyError:
            pass

    cpdef bint is_redirect(self):
        return self.status in {301, 302, 303, 307, 308}
