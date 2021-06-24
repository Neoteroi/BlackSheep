from blacksheep.messages import Request


def get_request_url_from_scope(scope) -> str:
    try:
        path = scope["path"]
        protocol = scope["scheme"]
        host, port = scope["server"]
    except KeyError as key_error:
        raise ValueError(f"Invalid scope: {key_error}")

    if protocol == "http" and port == 80:
        port_part = ""
    elif protocol == "https" and port == 443:
        port_part = ""
    else:
        port_part = f":{port}"

    return f"{protocol}://{host}{port_part}{path}"


def get_request_url(request: Request) -> str:
    return get_request_url_from_scope(request.scope)
