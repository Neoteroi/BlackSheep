from datetime import datetime
from email.utils import parsedate_to_datetime
from enum import Enum
from typing import Optional
from urllib.parse import quote, unquote


class CookieSameSiteMode(Enum):
    UNDEFINED = 0
    STRICT = 1
    LAX = 2
    NONE = 3


def datetime_to_cookie_format(value: datetime) -> bytes:
    return value.strftime("%a, %d %b %Y %H:%M:%S GMT").encode()


def datetime_from_cookie_format(value: bytes) -> datetime:
    return parsedate_to_datetime(value.decode()).replace(tzinfo=None)


class CookieError(Exception):
    def __init__(self, message: str):
        super().__init__(message)


class CookieValueExceedsMaximumLength(CookieError):
    def __init__(self):
        super().__init__(
            "The length of the cookie value exceeds the maximum "
            "length of 4096 bytes, and it would be ignored or truncated "
            "by clients. See: https://tools.ietf.org/html/rfc6265#section-6.1"
        )


class Cookie:
    def __init__(
        self,
        name: str,
        value: str,
        expires: Optional[datetime] = None,
        domain: Optional[str] = None,
        path: Optional[str] = None,
        http_only: bool = False,
        secure: bool = False,
        max_age: int = -1,
        same_site: CookieSameSiteMode = CookieSameSiteMode.UNDEFINED,
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

    def clone(self):
        return Cookie(
            self.name,
            self.value,
            self.expires,
            self.domain,
            self.path,
            self.http_only,
            self.secure,
            self.max_age,
            self.same_site,
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
        return f"<Cookie {self.name}: {self.value}>"


def split_value(raw_value: bytes, separator: bytes):
    try:
        index = raw_value.index(separator)
    except ValueError:
        # this is the situation of flags, e.g. httponly and secure
        return b"", raw_value
    return raw_value[:index], raw_value[index + 1 :]


def same_site_mode_from_bytes(raw_value: bytes) -> CookieSameSiteMode:
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


def parse_cookie(raw_value: bytes) -> Cookie:
    eq = b"="
    parts = raw_value.split(b"; ")
    if len(parts) == 0:
        # only name=value pair
        try:
            name, value = split_value(raw_value, eq)
        except ValueError:
            raise ValueError(f"Invalid name=value fragment: {parts[0]}")
        else:
            return Cookie(name.decode(), value.decode())
    if len(parts) == 1:
        # some set a cookie with a separator without space
        parts = raw_value.split(b";")
    try:
        name, value = split_value(parts[0], eq)
    except ValueError:
        raise ValueError(f"Invalid name=value fragment: {parts[0]}")
    if b" " in value and value.startswith(b'"'):
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
            if lower_k == b"expires":
                expires = v
            elif lower_k == b"domain":
                domain = v
            elif lower_k == b"path":
                path = v
            elif lower_k == b"max-age":
                max_age = int(v)
            elif lower_k == b"samesite":
                same_site = v
        else:
            lower_part = part.lower()
            if lower_part == b"httponly":
                http_only = True
            if lower_part == b"secure":
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
        same_site_mode_from_bytes(same_site),
    )


def write_cookie_for_response(cookie: Cookie) -> bytes:
    parts = []
    parts.append(quote(cookie.name).encode() + b"=" + quote(cookie.value).encode())
    if cookie.expires:
        parts.append(b"Expires=" + datetime_to_cookie_format(cookie.expires))
    if cookie.max_age > -1:
        parts.append(b"Max-Age=" + str(cookie.max_age).encode())
    if cookie.domain:
        parts.append(b"Domain=" + cookie.domain.encode())
    if cookie.path:
        parts.append(b"Path=" + cookie.path.encode())
    if cookie.http_only:
        parts.append(b"HttpOnly")
    if (
        cookie.secure
        or cookie.same_site == CookieSameSiteMode.STRICT
        or cookie.same_site == CookieSameSiteMode.NONE
    ):
        parts.append(b"Secure")
    if cookie.same_site == CookieSameSiteMode.STRICT:
        parts.append(b"SameSite=Strict")
    if cookie.same_site == CookieSameSiteMode.LAX:
        parts.append(b"SameSite=Lax")
    if cookie.same_site == CookieSameSiteMode.NONE:
        parts.append(b"SameSite=None")
    return b"; ".join(parts)
