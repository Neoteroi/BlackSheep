from datetime import datetime
from typing import Optional, Union


def datetime_to_cookie_format(value: datetime) -> bytes:
    ...


def datetime_from_cookie_format(value: bytes) -> datetime:
    ...


class Cookie:
    def __init__(
        self,
        name: bytes,
        value: bytes,
        expires: Optional[bytes] = None,
        domain: Optional[bytes] = None,
        path: Optional[bytes] = None,
        http_only: bool = False,
        secure: bool = False,
        max_age: Optional[bytes] = None,
        same_site: Optional[bytes] = None,
    ):
        self.name = name
        self.value = value
        self.expires = expires
        self._expiration = None
        self.domain = domain
        self.path = path
        self.http_only = http_only
        self.secure = secure
        self.max_age = max_age
        self.same_site = same_site

    def clone(self) -> "Cookie":
        ...

    @property
    def expiration(self) -> datetime:
        ...

    @expiration.setter
    def expiration(self, value: datetime):
        ...

    def set_max_age(self, max_age: int):
        ...

    def __eq__(self, other: Union[str, bytes, "Cookie"]) -> bool:
        ...

    def __repr__(self):
        return f"<Cookie {self.name.decode()}: {self.value.decode()}>"


def parse_cookie(value: bytes) -> Cookie:
    ...
