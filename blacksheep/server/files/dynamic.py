import html
import os
from pathlib import Path
from urllib.parse import unquote

from blacksheep import HtmlContent, Request, Response
from blacksheep.common.files.asyncfs import FilesHandler
from blacksheep.common.files.pathsutils import get_file_extension_from_name
from blacksheep.exceptions import InvalidArgument, NotFound
from blacksheep.server.resources import get_resource_file_content
from blacksheep.server.routing import Route, Router

from . import ServeFilesOptions, get_response_for_file


def get_files_to_serve(source_folder, extensions=None, recurse=False, root_folder=None):
    if not root_folder:
        root_folder = source_folder

    p = Path(source_folder)

    if not p.exists():
        raise InvalidArgument("given root path does not exist")

    if not p.is_dir():
        raise InvalidArgument("given root path is not a directory")

    names = os.listdir(p)
    names.sort()
    dirs, nondirs = [], []

    for name in names:
        full_path = Path(os.path.join(source_folder, name))
        if os.path.isdir(full_path):
            dirs.append(full_path)
        else:
            nondirs.append(full_path)

    items = dirs + nondirs

    for item in items:
        item_path = str(item)

        if os.path.islink(item_path):
            continue

        if item.is_dir():
            if not recurse:
                yield {
                    "rel_path": item_path[len(root_folder) + 1 :],
                    "full_path": item_path,
                    "is_dir": True,
                }
            else:
                for v in get_files_to_serve(
                    Path(item_path), extensions, recurse, root_folder
                ):
                    yield v
        else:
            extension = get_file_extension_from_name(item_path)

            if extension in extensions:
                yield {
                    "rel_path": item_path[len(root_folder) + 1 :],
                    "full_path": item_path,
                    "is_dir": False,
                }


def get_files_list_html_response(template, parent_folder_path, contents):
    info_lines = []
    for item in contents:
        full_rel_path = html.escape(
            os.path.join(parent_folder_path, item.get("rel_path"))
        )
        info_lines.append(f'<li><a href="/{full_rel_path}">{full_rel_path}</a></li>')
    info = "".join(info_lines)
    p = []
    whole_p = []
    for fragment in parent_folder_path.split("/"):
        if fragment:
            whole_p.append(html.escape(fragment))
            fragment_path = "/".join(whole_p)
            p.append(f'<a href="/{fragment_path}">{html.escape(fragment)}</a>')

    # TODO: use chunked encoding here with HTML response
    return Response(
        200,
        content=HtmlContent(template.format_map({"path": "/".join(p), "info": info})),
    )


def get_files_route_handler(
    files_handler: FilesHandler,
    source_folder_name,
    source_folder_full_path,
    discovery,
    cache_time,
    extensions,
):
    async def file_getter(request: Request):
        tail = unquote(request.route_values.get("tail")).lstrip("/")

        resource_path = os.path.join(source_folder_name, tail)

        if "../" in tail:
            # verify that a relative path doesn't go outside of the
            # static root folder
            abs_path = os.path.abspath(resource_path)
            if not str(abs_path).lower().startswith(source_folder_full_path.lower()):
                # outside of the static folder!
                raise NotFound()

        if not os.path.exists(resource_path) or os.path.islink(resource_path):
            raise NotFound()

        if os.path.isdir(resource_path):
            if discovery:
                return get_files_list_html_response(
                    get_resource_file_content("fileslist.html"),
                    tail.rstrip("/"),
                    list(get_files_to_serve(resource_path.rstrip("/"))),
                )
            else:
                raise NotFound()

        file_extension = get_file_extension_from_name(resource_path)

        if file_extension not in extensions:
            raise NotFound()

        try:
            return get_response_for_file(
                files_handler, request, resource_path, cache_time
            )
        except FileNotFoundError:
            raise NotFound()

    return file_getter


def serve_files_dynamic(
    router: Router, files_handler: FilesHandler, options: ServeFilesOptions
):
    options.validate()

    route = Route(
        b"*",
        get_files_route_handler(
            files_handler,
            options.source_folder,
            os.path.abspath(options.source_folder),
            options.discovery,
            options.cache_time,
            options.extensions,
        ),
    )
    router.add_route("GET", route)
    router.add_route("HEAD", route)
