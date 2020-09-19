from typing import Any, Optional, Union


class InvalidURL(Exception):
    def __init__(self, message: str) -> None:
        ...


class URL:
    value: bytes
    schema: Optional[bytes]
    host: Optional[bytes]
    port: int
    path: bytes
    query: bytes
    fragment: Optional[bytes]
    is_absolute: Any

    def __init__(self, value: bytes) -> None:
        ...

    def join(self, other: "URL") -> "URL":
        ...

    def base_url(self) -> "URL":
        ...

    def __add__(self, other: Union[bytes, "URL"]) -> "URL":
        ...

    def __eq__(self, other: object) -> bool:
        ...
