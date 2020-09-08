from typing import Union, Optional


class InvalidURL(Exception):
    def __init__(self, message: str):
        ...


class URL:
    def __init__(self, value: bytes):
        self.value: bytes
        self.schema: Optional[bytes]
        self.host: Optional[bytes]
        self.port: int
        self.path: bytes
        self.query: bytes
        self.fragment: Optional[bytes]
        self.is_absolute: bool

    def __repr__(self):
        return f"<URL {self.value}>"

    def join(self, other: "URL") -> "URL":
        ...

    def base_url(self) -> "URL":
        ...

    def __add__(self, other: Union[bytes, "URL"]):
        ...

    def __eq__(self, other: object) -> bool:
        ...
