from datetime import datetime
from urllib.parse import quote, unquote
from cpython.datetime cimport datetime

from email.utils import parsedate_to_datetime


cpdef bytes datetime_to_cookie_format(datetime value):
    return value.strftime('%a, %d %b %Y %H:%M:%S GMT').encode()


cpdef datetime datetime_from_cookie_format(bytes value):
    return parsedate_to_datetime(value.decode()).replace(tzinfo=None)


cdef class CookieError(Exception):

    def __init__(self, str message):
        super().__init__(message)


cdef class CookieValueExceedsMaximumLength(CookieError):

    def __init__(self):
        super().__init__(
            "The length of the cookie value exceeds the maximum "
            "length of 4096 bytes, and it would be ignored or truncated "
            "by clients. See: https://tools.ietf.org/html/rfc6265#section-6.1"
        )


cdef class Cookie:

    def __init__(
        self,
        str name,
        str value,
        datetime expires=None,
        str domain=None,
        str path=None,
        bint http_only=0,
        bint secure=0,
        int max_age=-1,
        CookieSameSiteMode same_site=CookieSameSiteMode.UNDEFINED
    ):
        self.name = name
        self.value = value
        self.expires = expires
        self.domain = domain
        self.path = path
        self.http_only = http_only
        self.secure = secure
        self.max_age = max_age
        self.same_site = same_site

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        if not value:
            raise ValueError("A cookie name is required")
        self._name = value

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value):
        if value and len(value.encode()) > 4096:
            raise CookieValueExceedsMaximumLength()
        self._value = value

    cpdef Cookie clone(self):
        return Cookie(
            self.name,
            self.value,
            self.expires,
            self.domain,
            self.path,
            self.http_only,
            self.secure,
            self.max_age,
            self.same_site
        )

    def __eq__(self, other):
        if isinstance(other, str):
            return other == self.value
        if isinstance(other, bytes):
            return other.decode() == self.value
        if isinstance(other, Cookie):
            return other.name == self.name and other.value == self.value
        return NotImplemented

    def __repr__(self):
        return f'<Cookie {self.name)}: {self.value}>'


cdef tuple split_value(bytes raw_value, bytes separator):
    cdef int index = raw_value.index(separator)
    if index == -1:
        # this is the situation of flags, e.g. httponly and secure
        return b"", raw_value
    return raw_value[:index], raw_value[index+1:]


cdef CookieSameSiteMode same_site_mode_from_bytes(bytes raw_value):
    cdef bytes raw_value_lower
    if not raw_value:
        return CookieSameSiteMode.UNDEFINED

    raw_value_lower = raw_value.lower()

    if raw_value_lower == b"strict":
        return CookieSameSiteMode.STRICT
    if raw_value_lower == b"lax":
        return CookieSameSiteMode.LAX
    if raw_value_lower == b"none":
        return CookieSameSiteMode.NONE

    return CookieSameSiteMode.UNDEFINED


cpdef Cookie parse_cookie(bytes raw_value):
    # https://tools.ietf.org/html/rfc6265
    cdef int max_age
    cdef bytes value = b''
    cdef bytes eq, expires, domain, path, part, k, v, lower_k, lower_part
    cdef bint http_only, secure
    cdef bytes same_site
    cdef list parts
    eq = b'='
    parts = raw_value.split(b'; ')
    if len(parts) == 0:
        # only name=value pair
        try:
            name, value = split_value(raw_value, eq)
        except ValueError as unpack_error:
            raise ValueError(f'Invalid name=value fragment: {parts[0]}')
        else:
            return Cookie(name, value)
    if len(parts) == 1:
        # some set a cookie with a separator without space
        parts = raw_value.split(b';')
    try:
        name, value = split_value(parts[0], eq)
    except ValueError as unpack_error:
        raise ValueError(f'Invalid name=value fragment: {parts[0]}')

    if b' ' in value and value.startswith(b'"'):
        value = value.strip(b'"')

    expires = None
    domain = None
    path = None
    http_only = False
    secure = False
    max_age = -1
    same_site = None

    for part in parts:
        if eq in part:
            k, v = split_value(part, eq)
            lower_k = k.lower()
            if lower_k == b'expires':
                expires = v
            elif lower_k == b'domain':
                domain = v
            elif lower_k == b'path':
                path = v
            elif lower_k == b'max-age':
                max_age = int(v)
            elif lower_k == b'samesite':
                same_site = v
        else:
            lower_part = part.lower()
            if lower_part == b'httponly':
                http_only = True
            if lower_part == b'secure':
                secure = True

    return Cookie(
        unquote(name.decode()),
        unquote(value.decode()),
        datetime_from_cookie_format(expires) if expires else None,
        domain.decode() if domain else None,
        path.decode() if path else None,
        http_only,
        secure,
        max_age,
        same_site_mode_from_bytes(same_site)
    )


cdef bytes write_cookie_for_response(Cookie cookie):
    cdef list parts = []
    parts.append(quote(cookie.name).encode() + b'=' + quote(cookie.value).encode())

    if cookie.expires:
        parts.append(b'Expires=' + datetime_to_cookie_format(cookie.expires))

    if cookie.max_age > -1:
        parts.append(b'Max-Age=' + str(cookie.max_age).encode())

    if cookie.domain:
        parts.append(b'Domain=' + cookie.domain.encode())

    if cookie.path:
        parts.append(b'Path=' + cookie.path.encode())

    if cookie.http_only:
        parts.append(b'HttpOnly')

    if cookie.secure or cookie.same_site == CookieSameSiteMode.STRICT or cookie.same_site == CookieSameSiteMode.NONE:
        parts.append(b'Secure')

    if cookie.same_site == CookieSameSiteMode.STRICT:
        parts.append(b'SameSite=Strict')

    if cookie.same_site == CookieSameSiteMode.LAX:
        parts.append(b'SameSite=Lax')

    if cookie.same_site == CookieSameSiteMode.NONE:
        parts.append(b'SameSite=None')

    return b'; '.join(parts)
