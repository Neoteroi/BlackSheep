import os
from pathlib import Path
from urllib.parse import quote
from blacksheep import Response, Content, Header, Headers
from blacksheep.server.routing import Route
from blacksheep.exceptions import InvalidArgument
from blacksheep.server.pathsutils import get_file_extension_from_name
from . import get_default_extensions, get_response_for_file, get_mime_type, unix_timestamp_to_datetime, get_file_data


def get_files_to_serve(source_folder, extensions=None, discovery=False, root_folder=None):
    if extensions is None:
        extensions = get_default_extensions()

    if not root_folder:
        root_folder = source_folder

    p = Path(source_folder)

    if not p.exists():
        raise InvalidArgument('given root path does not exist')

    if not p.is_dir():
        raise InvalidArgument('given root path is not a directory')

    items = [x for x in p.iterdir()]
    items.sort(reverse=True)

    for item in items:
        item_path = str(item)

        if os.path.islink(item_path):
            continue

        if item.is_dir():
            if discovery:
                yield {
                    'rel_path': item_path[len(root_folder):],
                    'full_path': item_path,
                    'is_dir': True
                }
            for v in get_files_to_serve(Path(item_path),
                                        extensions,
                                        discovery,
                                        root_folder):
                yield v
        else:
            extension = get_file_extension_from_name(item_path)

            if extension in extensions:
                yield {
                    'rel_path': item_path[len(root_folder):],
                    'full_path': item_path
                }


def get_folder_getter(folder_path, cache_max_age):
    # TODO: implement navigation also for this function
    raise Exception('Folder navigation is not implemented for this function.')


def get_frozen_file_getter(file_path, cache_max_age=12000):
    mime = get_mime_type(file_path)
    size = os.path.getsize(file_path)
    current_etag = str(os.path.getmtime(file_path)).encode()
    headers = [
        Header(b'Last-Modified', unix_timestamp_to_datetime(os.path.getmtime(file_path))),
        Header(b'ETag', current_etag),
        Header(b'Cache-Control', b'max-age=' + str(cache_max_age).encode())
    ]

    head_headers = headers + [
        Header(b'Content-Type', mime),
        Header(b'Content-Length', str(size).encode())
    ]

    data = get_file_data(file_path, size, size_limit=1.049e+7)

    async def frozen_file_getter(request):
        previous_etag = request.if_none_match

        if previous_etag and previous_etag == current_etag:
            return Response(304, headers, None)

        if request.method == 'HEAD':
            return Response(200, head_headers, None)

        return Response(200, Headers(headers), Content(mime, data))
    return frozen_file_getter


def get_file_getter(file_path, cache_max_age):
    async def file_getter(request):
        return get_response_for_file(request, file_path, cache_max_age)
    return file_getter


def get_routes_for_static_files(source_folder, extensions, discovery, cache_max_age, frozen):
    for file_paths in get_files_to_serve(source_folder, extensions, discovery):
        full_path = file_paths.get('full_path')

        if file_paths.get('is_dir'):
            handler = get_folder_getter(full_path, cache_max_age)
        else:
            handler = get_frozen_file_getter(full_path, cache_max_age) \
                if frozen else get_file_getter(full_path, cache_max_age)
        yield Route(quote(file_paths.get('rel_path')).encode(), handler)


def serve_static_files(router, folder_name='static', extensions=None, discovery=False, cache_max_age=10800, frozen=True):
    for route in get_routes_for_static_files(folder_name, extensions, discovery, cache_max_age, frozen):
        router.add_route('GET', route)
        router.add_route('HEAD', route)
