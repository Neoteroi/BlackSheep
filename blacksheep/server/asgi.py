from blacksheep.contents import ASGIContent
from blacksheep.messages import Request


def get_request_url_from_scope(
    scope,
    base_path: str = "",
    include_query: bool = True,
    trailing_slash: bool = False,
) -> str:
    """
    Function used for diagnostic reasons, for example to generate URLs in pages with
    detailed information about internal server errors.

    Do not use this method for logic that must generate full request URL, since it
    doesn't handle Forward and X-Forwarded* headers - use instead:

    > from blacksheep.messages import get_absolute_url_to_path, get_request_absolute_url
    """
    try:
        path = scope["path"]
        protocol = scope["scheme"]
        for key, val in scope["headers"]:
            if key.lower() in (b"host", b"x-forwarded-host", b"x-original-host"):
                host = val.decode("latin-1")
                port = 0
                break
        else:
            host, port = scope["server"]
    except KeyError as key_error:
        raise ValueError(f"Invalid scope: {key_error}")

    if not port:
        port_part = ""
    elif protocol == "http" and port == 80:
        port_part = ""
    elif protocol == "https" and port == 443:
        port_part = ""
    else:
        port_part = f":{port}"

    if trailing_slash:
        path = path + "/"

    query_part = (
        ""
        if not include_query or not scope.get("query_string")
        else ("?" + scope.get("query_string").decode("utf8"))
    )
    return f"{protocol}://{host}{port_part}{base_path}{path}{query_part}"


def get_request_url(request: Request) -> str:
    """
    Function used for diagnostic reasons, for example to generate URLs in pages with
    detailed information about internal server errors.

    Do not use this method for logic that must generate full request URL, since it
    doesn't handle Forward and X-Forwarded* headers - use instead:

    > from blacksheep.messages import get_absolute_url_to_path, get_request_absolute_url
    """
    return get_request_url_from_scope(request.scope)


def incoming_request(scope, receive=None) -> Request:
    """
    Function used to simulate incoming requests from an ASGI scope.
    This function is intentionally not used in
    `blacksheep.server.application.Application`.
    """
    request = Request.incoming(
        scope["method"],
        scope["raw_path"],
        scope["query_string"],
        list(scope["headers"]),
    )
    request.scope = scope
    if receive:
        request.content = ASGIContent(receive)
    return request


def get_full_path(scope) -> bytes:
    """
    Returns the full path of the HTTP message from an ASGI scope.
    """
    path = scope["path"].encode()
    query = scope["query_string"]

    if query:
        return path + b"?" + query

    return path
