import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterable, Callable, Optional, Set, TypedDict, Union

from blacksheep import Request, Response, StreamedContent
from blacksheep.common.files.asyncfs import FilesHandler
from blacksheep.common.files.info import FileInfo
from blacksheep.common.files.pathsutils import get_mime_type_from_name
from blacksheep.exceptions import BadRequest, InvalidArgument, RangeNotSatisfiable
from blacksheep.ranges import InvalidRangeValue, Range, RangePart
from blacksheep.server.headers.cache import CacheControlHeaderValue


class FilePathInfo(TypedDict):
    rel_path: str
    full_path: str
    is_dir: bool


@dataclass
class DefaultFileOptions:
    """
    Options to configure how the default file (by default index.html) is served to
    clients.
    """

    on_response: Optional[Callable[[Request, Response], None]] = None
    cache_control: Optional[CacheControlHeaderValue] = None

    def handle(self, request: Request, response: Response):
        if self.cache_control:
            response.set_header(b"cache-control", self.cache_control.value)
        if self.on_response:
            self.on_response(request, response)


def _get_content_range_value(part: RangePart, file_size: int) -> bytes:
    start = part.start
    end = part.end

    if part.start is None:
        end = file_size - 1
        start = file_size - part.end

    if part.end is None:
        end = file_size - 1

    return b"bytes " + f"{start}-{end}/{file_size}".encode()


def get_range_file_getter(
    files_handler: FilesHandler,
    file_path: str,
    file_size: int,
    range_option: Range,
    size_limit=1024 * 64,
    boundary: Optional[bytes] = None,
    file_type: Optional[bytes] = None,
) -> Callable[[], AsyncIterable[bytes]]:
    # https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Range
    async def file_chunker() -> AsyncIterable[bytes]:
        async with files_handler.open(file_path) as file:
            for part in range_option:
                if part.start is None and part.end is None:
                    raise BadRequest("Invalid range part: both boundaries are None")
                if part.start is not None and part.end is not None:
                    # return a portion between start and end indexes
                    await file.seek(part.start, 0)
                    part_size = part.end - part.start

                elif part.end is None:
                    assert part.start is not None
                    # return all bytes to the end, starting from start index
                    await file.seek(part.start)
                    part_size = file_size - part.start

                elif part.start is None:
                    # return a number of units at the end of the file
                    await file.seek(file_size - part.end)
                    part_size = part.end

                bytes_to_return = part_size

                while True:
                    chunk_limit = (
                        size_limit if bytes_to_return > size_limit else bytes_to_return
                    )
                    chunk = await file.read(chunk_limit)

                    if not chunk:
                        break

                    bytes_to_return -= len(chunk)

                    if boundary:
                        yield b"--" + boundary + b"\r\n"
                        yield b"Content-Type: " + file_type + b"\r\n"
                        yield b"Content-Range: " + _get_content_range_value(
                            part, file_size
                        ) + b"\r\n\r\n"

                    yield chunk

                    if boundary:
                        yield b"\r\n"

        if boundary:
            yield b"--" + boundary + b"--\r\n"

        yield b""

    return file_chunker


def get_file_getter(
    files_handler: FilesHandler,
    file_path: str,
    file_size: int,
    size_limit: int = 1024 * 64,
) -> Callable[[], AsyncIterable[bytes]]:
    # NB: if the file size is small, we read its bytes and return them;
    # otherwise, a lazy reader is returned; that returns the file in chunks

    if file_size > size_limit:

        async def file_chunker():
            async for chunk in files_handler.chunks(file_path, size_limit):
                yield chunk

        return file_chunker

    async def file_getter():
        yield await files_handler.read(file_path)
        yield b""

    return file_getter


def _get_requested_range(request: Request) -> Optional[Range]:
    # http://svn.tools.ietf.org/svn/wg/httpbis/specs/rfc7233.html#rfc.section.3.1
    # A server must ignore a Range header field received with a request method
    # other than GET
    if request.method != "GET":
        return None

    # NB: only the first Range request header is taken into consideration;
    # if the HTTP contains several Range headers, only the first is used
    range_header = request.get_first_header(b"range")

    if not range_header:
        return None

    try:
        value = Range.parse(range_header)
    except InvalidRangeValue:
        raise BadRequest("Invalid Range header")
    else:
        # An origin server must ignore a Range header field that contains
        # a range unit it does not understand.
        if value.unit != "bytes":
            return None

        return value


def _validate_range(requested_range: Range, file_size: int) -> None:
    if not requested_range.can_satisfy(file_size):
        raise RangeNotSatisfiable()


def is_requested_range_actual(request: Request, info: FileInfo) -> bool:
    if_range = request.get_first_header(b"if-range")

    if not if_range:
        return True

    return if_range == info.etag.encode() or if_range == info.modified_time.encode()


def get_default_extensions() -> Set[str]:
    """Returns a set of extensions that are served by default."""
    return {
        ".txt",
        ".css",
        ".js",
        ".jpeg",
        ".jpg",
        ".html",
        ".ico",
        ".png",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
        ".svg",
        ".mp4",
        ".mp3",
        ".webp",
        ".webm",
    }


def validate_source_path(source_folder: Union[str, Path]) -> None:
    source_folder_path = Path(source_folder)

    if not source_folder_path.exists():
        raise InvalidArgument("The given root path does not exist.")

    if not source_folder_path.is_dir():
        raise InvalidArgument("The given root path is not a directory.")


def get_response_for_file(
    files_handler: FilesHandler,
    request: Request,
    resource_path: str,
    cache_time: int,
    info: Optional[FileInfo] = None,
) -> Response:
    if info is None:
        info = FileInfo.from_path(resource_path)

    current_etag = info.etag.encode()
    previous_etag = request.if_none_match

    # is the client requesting a Range of bytes?
    # NB: ignored if not GET or unit cannot be handled
    requested_range = _get_requested_range(request)

    if requested_range:
        _validate_range(requested_range, info.size)

    headers = [
        (b"Last-Modified", info.modified_time.encode()),
        (b"ETag", current_etag),
        (b"Accept-Ranges", b"bytes"),
    ]

    if cache_time > 0:
        headers.append((b"Cache-Control", b"max-age=" + str(cache_time).encode()))

    if previous_etag and current_etag == previous_etag:
        # handle HTTP 304 Not Modified
        return Response(304, headers, None)

    if request.method == "HEAD":
        # NB: responses to HEAD requests don't have a body,
        # and responses with a body in BlackSheep have content-type
        # and content-length headers set automatically,
        # depending on their content; therefore here it's necessary to set
        # content-type and content-length for HEAD

        # TODO: instead of calling info.mime.encode every time, optimize using a
        # Dict[str, bytes] - optimize number to encoded string, too, using LRU
        headers.append((b"Content-Type", info.mime.encode()))
        headers.append((b"Content-Length", str(info.size).encode()))
        return Response(200, headers, None)

    status = 200
    mime = get_mime_type_from_name(resource_path).encode()

    if requested_range and is_requested_range_actual(request, info):
        # NB: the method can only be GET for range requests, so it cannot
        # happen to have response 206 partial content with HEAD
        status = 206
        boundary: Optional[bytes]

        if requested_range.is_multipart:
            # NB: multipart byteranges return the mime inside the portions
            boundary = str(uuid.uuid4()).replace("-", "").encode()
            file_type = mime
            mime = b"multipart/byteranges; boundary=" + boundary
        else:
            boundary = file_type = None
            single_part = requested_range.parts[0]
            headers.append(
                (b"Content-Range", _get_content_range_value(single_part, info.size))
            )

        content = StreamedContent(
            mime,
            get_range_file_getter(
                files_handler,
                resource_path,
                info.size,
                requested_range,
                boundary=boundary,
                file_type=file_type,
            ),
        )
    else:
        content = StreamedContent(
            mime, get_file_getter(files_handler, resource_path, info.size)
        )

    return Response(status, headers, content)
