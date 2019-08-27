import os
import aiofiles
from datetime import datetime
from blacksheep import Response, StreamedContent
from blacksheep.server.pathsutils import get_mime_type


def get_default_extensions():
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


def get_response_for_file(request, resource_path: str, cache_time: int):
    stat = os.stat(resource_path)
    file_size = stat.st_size
    modified_time = stat.st_mtime
    current_etag = str(modified_time).encode()
    previous_etag = request.if_none_match

    headers = [
        (b'Last-Modified', unix_timestamp_to_datetime(modified_time)),
        (b'ETag', current_etag)
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
