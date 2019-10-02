from typing import Union, Optional


class InvalidURL(Exception):

    def __init__(self, message: str): ...


class URL:

    def __init__(self, value: bytes):
        self.value = ... # type: bytes
        self.schema = ... # type: Optional[bytes]
        self.host = ... # type: Optional[bytes]
        self.port = ... # type: int
        self.path = ... # type: bytes
        self.query = ... # type: bytes
        self.fragment = ... # type: Optional[bytes]
        self.is_absolute = ... # type: bool

    def __repr__(self):
        return f'<URL {self.value}>'

    def join(self, other: URL) -> URL: ...

    def base_url(self) -> URL: ...

    def __add__(self, other: Union[bytes, URL]): ...

    def __eq__(self, other: URL) -> bool: ...
