from email.utils import formatdate

from blacksheep.contents import Content
from blacksheep.messages import Request, Response


def get_response_for_static_content(
    request: Request,
    content_type: bytes,
    contents: bytes,
    last_modified_time: float,
    cache_time: int = 10800,
) -> Response:
    """
    Returns a response object to serve static content.
    """
    current_etag = str(last_modified_time).encode()
    previous_etag = request.if_none_match

    headers = [
        (b"Last-Modified", formatdate(last_modified_time, usegmt=True).encode()),
        (b"ETag", current_etag),
    ]

    if cache_time > -1:
        headers.append((b"Cache-Control", b"max-age=" + str(cache_time).encode()))

    if previous_etag and current_etag == previous_etag:
        # handle HTTP 304 Not Modified
        return Response(304, headers, None)

    if request.method == "HEAD":
        headers.append((b"Content-Type", content_type))
        headers.append((b"Content-Length", str(len(contents)).encode()))
        return Response(200, headers, None)

    return Response(200, headers, Content(content_type, contents))
