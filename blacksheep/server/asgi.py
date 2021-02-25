from blacksheep.messages import Request


def get_request_url(request: Request) -> str:
    protocol = request.scope.get("type")
    host, port = request.scope.get("server")

    if protocol == "http" and port == 80:
        port_part = ""
    elif protocol == "https" and port == 443:
        port_part = ""
    else:
        port_part = f":{port}"

    return f"{protocol}://{host}{port_part}{request.url.value.decode()}"
