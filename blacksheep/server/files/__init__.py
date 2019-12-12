import os
import aiofiles
from typing import Optional
from datetime import datetime
from blacksheep import Response, StreamedContent
from blacksheep.server.pathsutils import get_mime_type
from blacksheep.exceptions import BadRequest, RangeNotSatisfiable
from blacksheep.ranges import Range, RangePart, InvalidRangeValue


def get_default_extensions():
    """It returns a set of extensions that are served by default."""
    return {
        '.txt',
        '.css',
        '.js',
        '.jpeg',
        '.jpg',
        '.html',
        '.ico',
        '.png',
        '.woff',
        '.woff2',
        '.ttf',
        '.eot',
        '.svg',
        '.mp4',
        '.mp3'
    }


def unix_timestamp_to_datetime(ts):
    return datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S').encode()


async def get_file_chunks(file_path: str, size_limit: int = 1024*64):
    async with aiofiles.open(file_path, mode='rb') as f:
        while True:
            chunk = await f.read(size_limit)

            if not chunk:
                break

            yield chunk


def get_file_data(file_path, file_size, size_limit=1024*64):
    # NB: if the file size is small, we read its bytes and return them;
    # otherwise, a lazy reader is returned; that returns the file in chunks
    if file_size > size_limit:
        async def file_chunker():
            async for chunk in get_file_chunks(file_path, size_limit):
                yield chunk
            yield b''

        return file_chunker

    async def file_getter():
        async with aiofiles.open(file_path, mode='rb') as file:
            data = await file.read()
            yield data
            yield b''
    return file_getter


def _get_requested_range(request) -> Optional[Range]:
    # NB: only the first Range request header is taken into consideration;
    # if the HTTP contains several Range headers, only the first is used
    range_header = request.get_first_header(b'range')

    if not range_header:
        return None

    try:
        return Range.parse(range_header)
    except InvalidRangeValue:
        raise BadRequest('Invalid Range header')


def get_response_for_file(request, resource_path: str, cache_time: int):
    stat = os.stat(resource_path)
    file_size = stat.st_size
    modified_time = stat.st_mtime
    current_etag = str(modified_time).encode()
    previous_etag = request.if_none_match

    # is the client requesting a Range of bytes?
    requested_range = _get_requested_range(request)

    if requested_range:
        # only bytes ranges are supported
        if requested_range.unit != 'bytes':
            raise RangeNotSatisfiable()

        if not requested_range.can_satisfy(file_size):
            raise RangeNotSatisfiable()

        # TODO: handle If-Range
        # https://developer.mozilla.org/en-US/docs/Web/HTTP/Range_requests

    headers = [
        (b'Last-Modified', unix_timestamp_to_datetime(modified_time)),
        (b'ETag', current_etag),
        (b'Accept-Ranges', b'bytes')
    ]

    if cache_time > 0:
        headers.append((b'Cache-Control', b'max-age=' + str(cache_time).encode()))

    if previous_etag and current_etag == previous_etag:
        return Response(304, headers, None)

    if request.method == 'HEAD':
        headers.append((b'Content-Type', get_mime_type(resource_path)))
        headers.append((b'Content-Length', str(file_size).encode()))
        return Response(200, headers, None)

    return Response(200, 
                    headers,
                    StreamedContent(get_mime_type(resource_path),
                                    get_file_data(resource_path, file_size)))
