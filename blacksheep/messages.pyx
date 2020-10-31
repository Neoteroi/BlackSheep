from .url cimport URL
from .headers cimport Headers
from .exceptions cimport BadRequestFormat, InvalidOperation, MessageAborted
from .cookies cimport Cookie, parse_cookie, datetime_to_cookie_format, write_cookie_for_response
from .contents cimport Content, MultiPartFormData, parse_www_form_urlencoded, multiparts_to_dictionary


import re
import http
import cchardet as chardet
from asyncio import Event
from urllib.parse import parse_qs, unquote
from json import loads as json_loads
from json.decoder import JSONDecodeError
from datetime import datetime, timedelta
from typing import Union, Dict, List, Optional
from blacksheep.multipart import parse_multipart


_charset_rx = re.compile(b'charset=([^;]+)\\s', re.I)


cpdef str parse_charset(bytes value):
    m = _charset_rx.match(value)
    if m:
        return m.group(1).decode('utf8')
    return None


cdef class Message:

    def __init__(self, list headers):
        self.__headers = headers or []

    @property
    def headers(self):
        cdef str key = '_headers'
        if key in self.__dict__:
            return self.__dict__[key]
        self.__dict__[key] = Headers(self.__headers)
        return self.__dict__[key]

    cpdef Message with_content(self, Content content):
        self.content = content
        return self

    cpdef bytes get_first_header(self, bytes key):
        cdef tuple header
        key = key.lower()
        for header in self.__headers:
            if header[0].lower() == key:
                return header[1]

    cpdef list get_headers(self, bytes key):
        cdef list results = []
        cdef tuple header
        key = key.lower()
        for header in self.__headers:
            if header[0].lower() == key:
                results.append(header[1])
        return results

    cdef list get_headers_tuples(self, bytes key):
        cdef list results = []
        cdef tuple header
        key = key.lower()
        for header in self.__headers:
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
        for header in self.__headers:
            if header[0].lower() == key:
                to_remove.append(header)

        for header in to_remove:
            self.__headers.remove(header)

    cdef void remove_headers(self, list headers):
        cdef tuple header
        for header in headers:
            self.__headers.remove(header)

    cdef bint _has_header(self, bytes key):
        cdef bytes existing_key, existing_value
        key = key.lower()
        for existing_key, existing_value in self.__headers:
            if existing_key.lower() == key:
                return True
        return False

    cpdef bint has_header(self, bytes key):
        return self._has_header(key)

    cdef void _add_header(self, bytes key, bytes value):
        self.__headers.append((key, value))

    cdef void _add_header_if_missing(self, bytes key, bytes value):
        if not self._has_header(key):
            self.__headers.append((key, value))

    cpdef void add_header(self, bytes key, bytes value):
        self.__headers.append((key, value))

    cpdef void set_header(self, bytes key, bytes value):
        self.remove_header(key)
        self.__headers.append((key, value))

    cpdef bytes content_type(self):
        if self.content and self.content.type:
            return self.content.type
        return self.get_first_header(b'content-type')

    async def read(self):
        if self.content:
            # TODO: return content.body if not instance of StreamedContent?
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
        cdef str text
        cdef bytes body
        cdef bytes content_type_value = self.content_type()

        if not content_type_value:
            return None

        if b'application/x-www-form-urlencoded' in content_type_value:
            text = await self.text()
            return parse_www_form_urlencoded(text)

        if b'multipart/form-data;' in content_type_value:
            body = await self.read()
            return multiparts_to_dictionary(list(parse_multipart(body)))
        return None

    async def multipart(self):
        cdef str text
        cdef bytes body
        cdef bytes content_type_value = self.content_type()

        if not content_type_value:
            return None

        if b'multipart/form-data;' in content_type_value:
            body = await self.read()
            return list(parse_multipart(body))
        return None

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
            name = name.encode('ascii')

        content_type = self.content_type()

        if not content_type or b'multipart/form-data;' not in content_type:
            return []
        data = await self.multipart()
        if name:
            return [part for part in data if part.file_name and part.name == name]
        return [part for part in data if part.file_name]

    async def json(self, loads=json_loads):
        text = await self.text()
        try:
            return loads(text)
        except JSONDecodeError as decode_error:
            content_type = self.content_type()
            if content_type and b'json' in content_type:
                # NB: content type could also be "application/problem+json"; so we don't check for
                # application/json in this case
                raise BadRequestFormat(f'Declared Content-Type is {content_type.decode()} but the content '
                                       f'cannot be parsed as JSON.',
                                       decode_error)
            raise InvalidOperation(f'Cannot parse content as JSON; declared Content-Type is '
                                   f'{content_type.decode()}.',
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
        content_type = self.content_type()
        if content_type:
            return parse_charset(content_type) or 'utf8'
        return 'utf8'


cpdef bint method_without_body(str method):
    return method == 'GET' or method == 'HEAD' or method == 'TRACE'


cdef class Request(Message):

    def __init__(self,
                 str method,
                 bytes url,
                 list headers):
        cdef URL _url = URL(url) if url else None
        self.__headers = headers or []
        self.method = method
        self._url = _url
        if _url:
            self._path = _url.path
            self._raw_query = _url.query

    @classmethod
    def incoming(cls, str method, bytes path, bytes query, list headers):
        request = cls(method, None, headers)
        request._path = path
        request._raw_query = query
        return request

    @property
    def query(self):
        if self._raw_query:
            return parse_qs(self._raw_query.decode('utf8'))
        return {}

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
            if isinstance(value, str):
                _url = URL(value.encode('utf8'))
            if isinstance(value, URL):
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
                        name, value = fragment.split(b'=')
                    except ValueError as unpack_error:
                        # discard cookie: in this case it's better to eat the exception
                        # than blocking a request just because a cookie is malformed
                        pass
                    else:
                        cookies[unquote(name.decode())] = unquote(value.rstrip(b'; ').decode())
        return cookies

    def set_cookie(self, Cookie cookie):
        self.__headers.append((b'cookie', cookie.name + b'=' + cookie.value))

    def set_cookies(self, list cookies):
        cdef Cookie cookie
        for cookie in cookies:
            self.set_cookie(cookie)

    @property
    def etag(self):
        return self.get_first_header(b'etag')

    @property
    def if_none_match(self):
        return self.get_first_header(b'if-none-match')

    cpdef bint expect_100_continue(self):
        cdef bytes value
        value = self.get_first_header(b'expect')
        if value and value.lower() == b'100-continue':
            return True
        return False


cdef class Response(Message):

    def __init__(self,
                 int status,
                 list headers = None,
                 Content content = None):
        self.__headers = headers or []
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

    def get_cookie(self, bytes name):
        cdef bytes value
        cdef list set_cookies_headers = self.get_headers(b'set-cookie')

        if set_cookies_headers:
            for value in set_cookies_headers:
                cookie = parse_cookie(value)
                if cookie.name == name:
                    return cookie

        return None

    def set_cookie(self, Cookie cookie):
        self.__headers.append((b'set-cookie', write_cookie_for_response(cookie)))

    def set_cookies(self, list cookies):
        cdef Cookie cookie
        for cookie in cookies:
            self.set_cookie(cookie)

    def unset_cookie(self, bytes name):
        self.set_cookie(Cookie(name, b'', datetime_to_cookie_format(datetime.utcnow() - timedelta(days=365))))

    def remove_cookie(self, bytes name):
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
