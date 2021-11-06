from typing import Optional, Tuple, Sequence, Union, List


_DEFAULT_AGENT = (
    b"Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:63.0) Gecko/20100101 Firefox/63.0"
)

_DEFAULT_ACCEPT = b"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"

_DEFAULT_ACCEPT_LANGUAGE = b"en-US,en;q=0.9,it-IT;q=0.8,it;q=0.7"

_DEFAULT_ACCEPT_ENCODING = b"gzip, deflate"


def _get_tuple(value: Union[List, Tuple[str, int]]) -> Tuple[str, int]:
    if isinstance(value, tuple):
        return value
    assert len(value) == 2
    return tuple(value)  # type: ignore


def get_example_scope(
    method: str,
    path: str,
    extra_headers: Optional[Sequence[Tuple[bytes, bytes]]] = None,
    *,
    query: Optional[bytes] = b"",
    scheme: str = "http",
    server: Union[List, Tuple[str, int]] = None,
    client: Union[List, Tuple[str, int]] = None,
    user_agent: bytes = _DEFAULT_AGENT,
    accept: bytes = _DEFAULT_ACCEPT,
    accept_language: bytes = _DEFAULT_ACCEPT_LANGUAGE,
    accept_encoding: bytes = _DEFAULT_ACCEPT_ENCODING,
):
    """Returns mocked ASGI scope"""

    if "?" in path:
        raise ValueError("The path in ASGI messages does not contain query string")

    if server is None:
        server = ("127.0.0.1", 8000)
    else:
        server = _get_tuple(server)

    if client is None:
        client = ("127.0.0.1", 51492)
    else:
        client = _get_tuple(client)

    server_port = server[1]
    if scheme == "http" and server_port == 80:
        port_part = ""
    elif scheme == "https" and server_port == 443:
        port_part = ""
    else:
        port_part = f":{server_port}"

    host = f"{server[0]}{port_part}"

    return {
        "type": scheme,
        "http_version": "1.1",
        "server": tuple(server),
        "client": client,
        "scheme": scheme,
        "method": method,
        "root_path": "",
        "path": path,
        "raw_path": path.encode(),
        "query_string": query,
        "headers": [
            (b"host", host.encode()),
            (b"user-agent", user_agent),
            (b"accept", accept),
            (b"accept-language", accept_language),
            (b"accept-encoding", accept_encoding),
            (b"connection", b"keep-alive"),
            (b"upgrade-insecure-requests", b"1"),
        ]
        + ([tuple(header) for header in extra_headers] if extra_headers else []),
    }
