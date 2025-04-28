import html
import os
from pathlib import Path
from typing import Awaitable, Callable, Iterable, Optional, Sequence, Set, Union
from urllib.parse import unquote

from blacksheep import HTMLContent, Request, Response
from blacksheep.common.files.asyncfs import FilesHandler
from blacksheep.common.files.pathsutils import get_file_extension_from_name
from blacksheep.exceptions import NotFound
from blacksheep.server.authorization import allow_anonymous
from blacksheep.server.files import (
    DefaultFileOptions,
    FilePathInfo,
    get_default_extensions,
    get_response_for_file,
    validate_source_path,
)
from blacksheep.server.resources import get_resource_file_content
from blacksheep.server.routing import Route, Router
from blacksheep.utils import join_fragments


def get_files_to_serve(
    source_folder: Path, extensions: Set[str], root_folder: Optional[Path] = None
) -> Iterable[FilePathInfo]:
    assert source_folder.exists(), "The source folder path must exist"
    assert source_folder.is_dir(), "The source folder path must be a directory"

    if not root_folder:
        root_folder = source_folder

    names = os.listdir(source_folder)
    names.sort()
    dirs, nondirs = [], []

    for name in names:
        full_path = source_folder / name
        if os.path.isdir(full_path):
            dirs.append(full_path)
        else:
            nondirs.append(full_path)

    items = dirs + nondirs
    items = (item for item in items if not os.path.islink(item))

    yield {
        "rel_path": "../",
        "full_path": str(source_folder),
        "is_dir": True,
    }

    for item in items:
        item_path = str(item)

        if item.is_dir():
            yield {
                "rel_path": item_path[len(str(root_folder)) + 1 :],
                "full_path": item_path,
                "is_dir": True,
            }
        else:
            extension = get_file_extension_from_name(item_path)

            if extension in extensions:
                yield {
                    "rel_path": item_path[len(str(root_folder)) + 1 :],
                    "full_path": item_path,
                    "is_dir": False,
                }


def get_files_list_html_response(
    template: str,
    parent_folder_path: str,
    contents: Sequence[FilePathInfo],
    root_path: str,
) -> Response:
    info_lines = []
    for item in contents:
        rel_path = item.get("rel_path")
        assert rel_path is not None
        full_rel_path = html.escape(
            join_fragments(root_path, parent_folder_path, rel_path)
        )
        info_lines.append(f'<li><a href="{full_rel_path}">{rel_path}</a></li>')
    info = "".join(info_lines)
    p = []
    whole_p = [root_path]
    for fragment in parent_folder_path.split("/"):
        if fragment:
            whole_p.append(html.escape(fragment))
            fragment_path = "/".join(whole_p)
            p.append(f'<a href="{fragment_path}">{html.escape(fragment)}</a>')

    # TODO: use chunked encoding here, yielding HTML fragments
    return Response(
        200,
        content=HTMLContent(template.format_map({"path": "/".join(p), "info": info})),
    )


def get_response_for_resource_path(
    request: Request,
    tail: str,
    files_list_html: str,
    source_folder_name: str,
    files_handler: FilesHandler,
    source_folder_full_path: str,
    discovery: bool,
    cache_time: int,
    extensions: Set[str],
    root_path: str,
    index_document: Optional[str],
    default_file_options: Optional[DefaultFileOptions] = None,
) -> Response:
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
        # Request for a path that matches a folder: e.g. /foo/
        if discovery:
            return get_files_list_html_response(
                files_list_html,
                tail.rstrip("/"),
                list(get_files_to_serve(Path(resource_path.rstrip("/")), extensions)),
                root_path,
            )
        else:
            if index_document is not None:
                # try returning the default index document
                response = get_response_for_resource_path(
                    request,
                    index_document,
                    files_list_html,
                    source_folder_name,
                    files_handler,
                    source_folder_full_path,
                    discovery,
                    cache_time,
                    extensions,
                    root_path,
                    None,
                )

                if default_file_options:
                    default_file_options.handle(request, response)

                return response
            raise NotFound()

    file_extension = get_file_extension_from_name(resource_path)

    if file_extension not in extensions:
        raise NotFound()

    return get_response_for_file(files_handler, request, resource_path, cache_time)


def get_files_route_handler(
    files_handler: FilesHandler,
    source_folder_name: str,
    discovery: bool,
    cache_time: int,
    extensions: Set[str],
    root_path: str,
    index_document: Optional[str],
    fallback_document: Optional[str],
    default_file_options: Optional[DefaultFileOptions] = None,
) -> Callable[[Request], Awaitable[Response]]:
    files_list_html = get_resource_file_content("fileslist.html")
    source_folder_full_path = os.path.abspath(str(source_folder_name))

    async def static_files_handler(request: Request) -> Response:
        assert request.route_values is not None, "Expects a route pattern with star *"
        tail = unquote(request.route_values.get("tail", "")).lstrip("/")

        try:
            return get_response_for_resource_path(
                request,
                tail,
                files_list_html,
                source_folder_name,
                files_handler,
                source_folder_full_path,
                discovery,
                cache_time,
                extensions,
                root_path,
                index_document,
                default_file_options=default_file_options,
            )
        except NotFound:
            if fallback_document is None:
                raise

            response = get_response_for_resource_path(
                request,
                fallback_document,
                files_list_html,
                source_folder_name,
                files_handler,
                source_folder_full_path,
                discovery,
                cache_time,
                extensions,
                root_path,
                None,
                default_file_options=default_file_options,
            )

            if default_file_options and index_document == fallback_document:
                default_file_options.handle(request, response)

            return response

    return static_files_handler


def get_static_files_route(path_prefix: str) -> bytes:
    if not path_prefix:
        return b"*"
    if path_prefix[0] != "/":
        path_prefix = "/" + path_prefix
    if path_prefix[-1] != "/":
        path_prefix = path_prefix + "/"
    return path_prefix.encode() + b"*"


def serve_files_dynamic(
    router: Router,
    files_handler: FilesHandler,
    source_folder: Union[str, Path],
    *,
    discovery: bool,
    cache_time: int,
    extensions: Optional[Set[str]],
    root_path: str,
    index_document: Optional[str],
    fallback_document: Optional[str],
    anonymous_access: bool = True,
    default_file_options: Optional[DefaultFileOptions] = None,
) -> None:
    """
    Configures a route to serve files dynamically, using the given files handler and
    options.
    """
    validate_source_path(source_folder)

    if not extensions:
        extensions = get_default_extensions()

    if router.prefix:
        if not root_path:
            root_path = router.prefix
        else:
            root_path = join_fragments(router.prefix, root_path)

    handler = get_files_route_handler(
        files_handler,
        str(source_folder),
        bool(discovery),
        int(cache_time),
        set(extensions),
        root_path,
        index_document,
        fallback_document,
        default_file_options,
    )

    if anonymous_access:
        handler = allow_anonymous()(handler)

    route = Route(
        get_static_files_route(root_path),
        handler,
    )
    router.add_route("GET", route)
    router.add_route("HEAD", route)
