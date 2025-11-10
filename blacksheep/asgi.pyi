from typing import TypedDict

class ASGIScopeInterface(TypedDict):
    type: str
    http_version: str
    server: tuple[str, int]
    client: tuple[str, int]
    scheme: str
    method: str
    path: str
    root_path: str
    raw_path: bytes
    query_string: str
    headers: list[tuple[bytes, bytes]]
