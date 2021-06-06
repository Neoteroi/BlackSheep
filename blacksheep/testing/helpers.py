from typing import List, Optional


def get_example_scope(
    method: str,
    path: str,
    extra_headers=None,
    query: Optional[bytes] = b"",
    scheme: str = "http",
    server: Optional[List] = None,
):
    """Returns mocked ASGI scope"""

    if "?" in path:
        raise ValueError("The path in ASGI messages does not contain query string")
    if query.startswith(b""):
        query = query.lstrip(b"")
    if server is None:
        server = ["127.0.0.1", 8000]
    return {
        "type": scheme,
        "http_version": "1.1",
        "server": server,
        "client": ["127.0.0.1", 51492],
        "scheme": scheme,
        "method": method,
        "root_path": "",
        "path": path,
        "raw_path": path.encode(),
        "query_string": query,
        "headers": [
            (b"host", b"127.0.0.1:8000"),
            (
                b"user-agent",
                (
                    b"Mozilla/5.0 (X11; Ubuntu; Linux x86_64; "
                    b"rv:63.0) Gecko/20100101 Firefox/63.0"
                ),
            ),
            (
                b"accept",
                (
                    b"text/html,application/xhtml+xml,"
                    b"application/xml;q=0.9,*/*;q=0.8"
                ),
            ),
            (b"accept-language", b"en-US,en;q=0.9,it-IT;q=0.8,it;q=0.7"),
            (b"accept-encoding", b"gzip, deflate"),
            (b"connection", b"keep-alive"),
            (b"upgrade-insecure-requests", b"1"),
        ]
        + ([tuple(header) for header in extra_headers] if extra_headers else []),
    }
