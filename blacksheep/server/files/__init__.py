import os
from datetime import datetime
from blacksheep import HttpResponse, HttpHeader, HttpHeaderCollection, HttpContent
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


def get_file_chunks(file_path):
    with open(file_path, mode='rb') as file:
        while True:
            chunk = file.read(1024 * 64)

            if not chunk:
                break

            yield chunk


def get_file_data(file_path, file_size, size_limit=1024*64):
    if file_size > size_limit:
        async def file_chunker():
            for chunk in get_file_chunks(file_path):
                yield chunk

        return file_chunker

    with open(file_path, 'rb') as file:
        return file.read()


def get_response_for_file(request, resource_path, cache_time):
    # TODO: support for accept-range and bytes ranges
    file_size = os.path.getsize(resource_path)
    modified_time = os.path.getmtime(resource_path)
    current_etag = str(modified_time).encode()
    previous_etag = request.if_none_match

    headers = [
        HttpHeader(b'Last-Modified', unix_timestamp_to_datetime(modified_time)),
        HttpHeader(b'ETag', current_etag)
    ]

    if cache_time > 0:
        headers.append(HttpHeader(b'Cache-Control', b'max-age=' + str(cache_time).encode()))

    if previous_etag and current_etag == previous_etag:
        return HttpResponse(304, headers, None)

    if request.method == b'HEAD':
        headers.append(HttpHeader(b'Content-Type', get_mime_type(resource_path)))
        headers.append(HttpHeader(b'Content-Length', str(file_size).encode()))
        return HttpResponse(200, headers, None)

    return HttpResponse(200, 
                        HttpHeaderCollection.from_param(headers), 
                        HttpContent(get_mime_type(resource_path),
                                                  get_file_data(resource_path, file_size)))
