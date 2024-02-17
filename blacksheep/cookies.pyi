from datetime import datetime
from enum import IntEnum
from typing import Optional, Union

class CookieSameSiteMode(IntEnum):
    UNDEFINED = 0
    LAX = 1
    STRICT = 2
    NONE = 3

class CookieError(Exception): ...
class CookieValueExceedsMaximumLength(CookieError): ...

def datetime_to_cookie_format(value: datetime) -> bytes: ...
def datetime_from_cookie_format(value: bytes) -> datetime: ...

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

    def clone(self) -> "Cookie": ...
    def __eq__(self, other: Union[str, bytes, "Cookie"]) -> bool: ...
    def __repr__(self) -> str:
        return f"<Cookie {self.name}: {self.value}>"

def parse_cookie(value: bytes) -> Cookie: ...
def write_response_cookie(cookie: Cookie) -> bytes: ...
