from asyncio import AbstractEventLoop
from datetime import datetime
from pathlib import Path
from typing import List
from unittest.mock import create_autospec

import pytest
from essentials.folders import get_file_extension

from blacksheep import Application, Request
from blacksheep.common.files.asyncfs import FileContext, FilesHandler
from blacksheep.exceptions import BadRequest, InvalidArgument
from blacksheep.ranges import Range, RangePart
from blacksheep.server.files import (
    DefaultFileOptions,
    FileInfo,
    RangeNotSatisfiable,
    _get_requested_range,
    get_default_extensions,
    get_range_file_getter,
    validate_source_path,
)
from blacksheep.server.files.dynamic import get_response_for_file
from blacksheep.server.files.static import get_response_for_static_content
from blacksheep.server.headers.cache import CacheControlHeaderValue
from blacksheep.server.resources import get_resource_file_path
from blacksheep.server.responses import text
from blacksheep.testing.helpers import get_example_scope
from blacksheep.testing.messages import MockReceive, MockSend
from blacksheep.utils.aio import get_running_loop


def get_folder_path(folder_name: str) -> str:
    return get_resource_file_path("tests", folder_name)


def get_file_path(file_name, folder_name: str = "files") -> str:
    return get_resource_file_path("tests", f"{folder_name}/{file_name}")


files2_index_path = get_file_path("index.html", "files2")


@pytest.fixture(scope="module")
def files2_index_contents():
    with open(files2_index_path, mode="rb") as actual_file:
        return actual_file.read()


async def test_get_response_for_file_raise_for_file_not_found():
    with pytest.raises(FileNotFoundError):
        get_response_for_file(
            FilesHandler(), Request("GET", b"/example.txt", None), "example.txt", 1200
        )


TEST_FILES = [
    get_file_path("lorem-ipsum.txt"),
    get_file_path("example.txt"),
    get_file_path("pexels-photo-126407.jpeg"),
]
TEST_FILES_METHODS = [[i, "GET"] for i in TEST_FILES] + [
    [i, "HEAD"] for i in TEST_FILES
]


@pytest.mark.parametrize("file_path", TEST_FILES)
async def test_get_response_for_file_returns_file_contents(file_path):
    response = get_response_for_file(
        FilesHandler(), Request("GET", b"/example", None), file_path, 1200
    )

    assert response.status == 200
    data = await response.read()

    with open(file_path, mode="rb") as test_file:
        contents = test_file.read()

    assert data == contents


@pytest.mark.parametrize("file_path,method", TEST_FILES_METHODS)
async def test_get_response_for_file_returns_headers(file_path, method):
    response = get_response_for_file(
        FilesHandler(), Request(method, b"/example", None), file_path, 1200
    )

    assert response.status == 200

    info = FileInfo.from_path(file_path)
    expected_headers = {
        b"etag": info.etag.encode(),
        b"last-modified": str(info.modified_time).encode(),
        b"accept-ranges": b"bytes",
        b"cache-control": b"max-age=1200",
    }

    for expected_header_name, expected_header_value in expected_headers.items():
        value = response.get_single_header(expected_header_name)

        assert value is not None
        assert value == expected_header_value


@pytest.mark.parametrize("file_path,method", TEST_FILES_METHODS)
async def test_get_response_for_file_returns_not_modified_handling_if_none_match_header(
    file_path, method
):
    info = FileInfo.from_path(file_path)

    response = get_response_for_file(
        FilesHandler(),
        Request(method, b"/example", [(b"If-None-Match", info.etag.encode())]),
        file_path,
        1200,
    )

    assert response.status == 304
    data = await response.read()
    assert data is None


@pytest.mark.parametrize("file_path", TEST_FILES)
async def test_get_response_for_file_with_head_method_returns_empty_body_with_info(
    file_path,
):
    response = get_response_for_file(
        FilesHandler(), Request("HEAD", b"/example", None), file_path, 1200
    )

    assert response.status == 200
    data = await response.read()
    assert data is None


@pytest.mark.parametrize("cache_time", [100, 500, 1200])
async def test_get_response_for_file_returns_cache_control_header(cache_time):
    response = get_response_for_file(
        FilesHandler(), Request("GET", b"/example", None), TEST_FILES[0], cache_time
    )

    assert response.status == 200
    header = response.get_single_header(b"cache-control")

    assert header == f"max-age={cache_time}".encode()


@pytest.mark.parametrize(
    "range_value,expected_bytes,expected_content_range",
    [
        [b"bytes=0-10", b"Lorem ipsu", b"bytes 0-10/447"],
        [b"bytes=10-20", b"m dolor si", b"bytes 10-20/447"],
        [b"bytes=33-44", b"ctetur adip", b"bytes 33-44/447"],
        [b"bytes=15-50", b"or sit amet, consectetur adipiscing", b"bytes 15-50/447"],
        [
            b"bytes=66-",
            b"usmod tempor incididunt ut labore et dolore magna\naliqua. Ut enim ad minim veniam, quis nostrud "
            b"exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis\n aute irure dolor in "
            b"reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint\n "
            b"occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum.",
            b"bytes 66-446/447",
        ],
        [
            b"bytes=381-",
            b"nt, sunt in culpa qui officia deserunt mollit anim id est laborum.",
            b"bytes 381-446/447",
        ],
        [
            b"bytes=-50",
            b"a qui officia deserunt mollit anim id est laborum.",
            b"bytes 397-446/447",
        ],
        [
            b"bytes=-66",
            b"nt, sunt in culpa qui officia deserunt mollit anim id est laborum.",
            b"bytes 381-446/447",
        ],
    ],
)
async def test_text_file_range_request_single_part(
    range_value, expected_bytes, expected_content_range
):
    file_path = get_file_path("example.txt")
    response = get_response_for_file(
        FilesHandler(),
        Request("GET", b"/example", [(b"Range", range_value)]),
        file_path,
        1200,
    )
    assert response.status == 206
    body = await response.read()
    assert body == expected_bytes

    assert response.get_single_header(b"content-range") == expected_content_range


@pytest.mark.parametrize(
    "range_value",
    [
        b"bytes=0-10000000000",
        b"bytes=100-200000",
        b"bytes=1111111111114-",
        b"bytes=-1111111111114",
    ],
)
async def test_invalid_range_request_range_not_satisfiable(range_value):
    file_path = get_file_path("example.txt")
    with pytest.raises(RangeNotSatisfiable):
        get_response_for_file(
            FilesHandler(),
            Request("GET", b"/example", [(b"Range", range_value)]),
            file_path,
            1200,
        )


@pytest.mark.parametrize(
    "range_value,expected_bytes_lines",
    [
        [
            b"bytes=0-10, 10-20",
            [
                b"--##BOUNDARY##",
                b"Content-Type: text/plain",
                b"Content-Range: bytes 0-10/447",
                b"",
                b"Lorem ipsu",
                b"--##BOUNDARY##",
                b"Content-Type: text/plain",
                b"Content-Range: bytes 10-20/447",
                b"",
                b"m dolor si",
                b"--##BOUNDARY##--",
            ],
        ],
        [
            b"bytes=0-10, -66",
            [
                b"--##BOUNDARY##",
                b"Content-Type: text/plain",
                b"Content-Range: bytes 0-10/447",
                b"",
                b"Lorem ipsu",
                b"--##BOUNDARY##",
                b"Content-Type: text/plain",
                b"Content-Range: bytes 381-446/447",
                b"",
                b"nt, sunt in culpa qui officia deserunt mollit anim id est laborum.",
                b"--##BOUNDARY##--",
            ],
        ],
    ],
)
async def test_text_file_range_request_multi_part(
    range_value: bytes, expected_bytes_lines: List[bytes]
):
    file_path = get_file_path("example.txt")
    response = get_response_for_file(
        FilesHandler(),
        Request("GET", b"/example", [(b"Range", range_value)]),
        file_path,
        1200,
    )
    assert response.status == 206
    content_type = response.content.type
    boundary = content_type.split(b"=")[1]
    body = await response.read()

    expected_bytes_lines = [
        line.replace(b"##BOUNDARY##", boundary) for line in expected_bytes_lines
    ]
    assert body.splitlines() == expected_bytes_lines


@pytest.mark.parametrize(
    "range_value,matches",
    [
        [b"bytes=0-10", True],
        [b"bytes=0-10", False],
        [b"bytes=10-20", True],
        [b"bytes=10-20", False],
    ],
)
async def test_text_file_range_request_single_part_if_range_handling(
    range_value, matches
):
    file_path = get_file_path("example.txt")
    info = FileInfo.from_path(file_path)

    response = get_response_for_file(
        FilesHandler(),
        Request(
            "GET",
            b"/example",
            [
                (b"Range", range_value),
                (b"If-Range", info.etag.encode() + (b"" if matches else b"xx")),
            ],
        ),
        file_path,
        1200,
    )

    expected_status = 206 if matches else 200

    assert response.status == expected_status

    if not matches:
        body = await response.read()

        with open(file_path, mode="rb") as actual_file:
            assert body == actual_file.read()


async def test_serve_files_no_discovery(app):
    # Note the folder files3 does not contain an index.html page
    app.serve_files(get_folder_path("files3"))

    await app.start()

    scope = get_example_scope("GET", "/", [])
    await app(
        scope,
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 404


async def test_serve_files_fallback_document(files2_index_contents: bytes, app):
    """Feature used to serve SPAs that use HTML5 History API"""
    app.serve_files(get_folder_path("files2"), fallback_document="index.html")

    await app.start()

    for path in {"/", "/one", "/one/two", "/one/two/anything.txt"}:
        scope = get_example_scope("GET", path, [])
        await app(
            scope,
            MockReceive(),
            MockSend(),
        )

        response = app.response
        assert response.status == 200
        assert await response.read() == files2_index_contents


async def test_serve_files_serves_index_html_by_default(files2_index_contents, app):
    app.serve_files(get_folder_path("files2"))

    await app.start()

    scope = get_example_scope("GET", "/", [])
    await app(
        scope,
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 200
    assert files2_index_contents == await response.read()


async def test_serve_files_can_disable_index_html_by_default(app):
    app.serve_files(get_folder_path("files2"), index_document=None)

    await app.start()

    scope = get_example_scope("GET", "/", [])
    await app(
        scope,
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 404


async def test_serve_files_custom_index_page(app):
    # Note the folder files3 does not contain an index.html page
    app.serve_files(get_folder_path("files3"), index_document="lorem-ipsum.txt")

    await app.start()

    scope = get_example_scope("GET", "/", [])
    await app(
        scope,
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 200

    with open(get_file_path("lorem-ipsum.txt", "files3"), mode="rt") as actual_file:
        content = actual_file.read()
        assert content == await response.text()


async def test_cannot_serve_files_outside_static_folder(app):
    folder_path = get_folder_path("files")
    app.serve_files(folder_path, discovery=True, extensions={".py"})

    await app.start()

    scope = get_example_scope("GET", "../test_files_serving.py", [])
    await app(
        scope,
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 404


async def test_cannot_serve_files_with_unhandled_extension(app):
    folder_path = get_folder_path("files2")
    app.serve_files(folder_path, discovery=True, extensions={".py"})

    await app.start()

    scope = get_example_scope("GET", "/example.config", [])
    await app(
        scope,
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 404


async def test_can_serve_files_with_relative_paths(files2_index_contents, app):
    folder_path = get_folder_path("files2")
    app.serve_files(folder_path, discovery=True)

    await app.start()

    scope = get_example_scope("GET", "/styles/../index.html", [])
    await app(
        scope,
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 200
    body = await response.read()
    assert body == files2_index_contents

    scope = get_example_scope("GET", "/styles/fonts/../../index.html", [])
    await app(
        scope,
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 200
    body = await response.read()
    assert body == files2_index_contents

    scope = get_example_scope("GET", "/styles/../does-not-exist.html", [])
    await app(
        scope,
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 404


@pytest.mark.parametrize("folder_name", ["files", "files2"])
async def test_serve_files_discovery(folder_name: str, app):
    folder_path = get_folder_path(folder_name)
    app.serve_files(folder_path, discovery=True)
    extensions = get_default_extensions()

    await app.start()

    scope = get_example_scope("GET", "/", [])
    await app(
        scope,
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 200
    body = await response.text()

    folder = Path(folder_path)
    for item in folder.iterdir():
        if item.is_dir():
            assert f"/{item.name}" in body
            continue

        file_extension = get_file_extension(str(item))
        if file_extension in extensions:
            assert f"/{item.name}" in body
        else:
            assert item.name not in body


async def test_serve_files_discovery_subfolder(app):
    folder_path = get_folder_path("files2")
    app.serve_files(folder_path, discovery=True)

    await app.start()

    scope = get_example_scope("GET", "/scripts", [])
    await app(
        scope,
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 200
    body = await response.text()

    folder = Path(folder_path) / "scripts"
    for item in folder.iterdir():
        assert f"/{item.name}" in body


async def test_serve_files_with_custom_files_handler(app):
    file_path = files2_index_path

    with open(file_path, mode="rt") as actual_file:
        expected_body = actual_file.read()

    class CustomFilesHandler(FilesHandler):
        def __init__(self) -> None:
            self.calls = []

        def open(self, file_path: str, mode: str = "rb") -> FileContext:
            self.calls.append(file_path)
            return super().open(file_path, mode)

    app.files_handler = CustomFilesHandler()

    folder_path = get_folder_path("files2")
    app.serve_files(folder_path, discovery=True)

    await app.start()

    scope = get_example_scope("GET", "/index.html", [])
    await app(
        scope,
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 200
    body = await response.text()
    assert body == expected_body

    assert app.files_handler.calls[0] == file_path


def test_file_context_mode_property():
    handler = FilesHandler()
    file_path = files2_index_path
    context = handler.open(file_path, loop=get_running_loop())
    assert context.mode == "rb"
    assert context.loop is not None
    assert isinstance(context.loop, AbstractEventLoop)


async def test_serve_files_multiple_folders(files2_index_contents, app):
    files1 = get_folder_path("files")
    files2 = get_folder_path("files2")
    app.serve_files(files1, discovery=True, root_path="one")
    app.serve_files(files2, discovery=True, root_path="two")

    await app.start()

    scope = get_example_scope("GET", "/", [])
    await app(
        scope,
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 404

    scope = get_example_scope("GET", "/example.txt", [])
    await app(
        scope,
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 404

    scope = get_example_scope("GET", "/one/example.txt", [])
    await app(
        scope,
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 200
    body = await response.read()

    with open(get_file_path("example.txt"), mode="rb") as actual_file:
        assert body == actual_file.read()

    scope = get_example_scope("GET", "/two/styles/main.css", [])
    await app(
        scope,
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 200
    body = await response.read()

    with open(get_file_path("styles/main.css", "files2"), mode="rb") as actual_file:
        assert body == actual_file.read()

    scope = get_example_scope("GET", "/two/index.html", [])
    await app(
        scope,
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 200
    body = await response.read()
    assert body == files2_index_contents


def test_validate_source_path_raises_for_invalid_path():
    with pytest.raises(InvalidArgument):
        validate_source_path("./not-existing")

    with pytest.raises(InvalidArgument):
        validate_source_path(files2_index_path)


def test_get_requested_range_raises_for_invalid_range():
    request = Request("GET", b"/foo", [(b"range", b"XXXXXXXXXXXX")])

    with pytest.raises(BadRequest):
        _get_requested_range(request)


async def test_get_range_file_getter_raises_for_invalid():
    getter = get_range_file_getter(
        FilesHandler(), files2_index_path, 100, Range("bytes", [RangePart(None, None)])
    )

    with pytest.raises(BadRequest):
        async for chunk in getter():
            ...


def test_range_with_unknown_unit_is_ignored():
    request = Request(
        "GET", b"/foo", [(b"Range", b"peanuts=200-1000, 2000-6576, 19000- ")]
    )

    assert _get_requested_range(request) is None


def test_file_info():
    info = FileInfo.from_path(files2_index_path)

    assert info.mime == "text/html"
    data = info.to_dict()

    assert data["size"] == info.size
    assert data["etag"] == info.etag
    assert data["mime"] == info.mime
    assert data["modified_time"] == info.modified_time

    assert info.mime in repr(info)


async def test_get_response_for_static_content_returns_given_bytes():
    response = get_response_for_static_content(
        Request("GET", b"/", None),
        b"text/plain",
        b"Lorem ipsum dolor sit amet\n",
        datetime(2020, 10, 24).timestamp(),
    )

    assert response.status == 200
    data = await response.read()
    assert data == b"Lorem ipsum dolor sit amet\n"


async def test_get_response_for_static_content_handles_head():
    response = get_response_for_static_content(
        Request("GET", b"/", None),
        b"text/plain",
        b"Lorem ipsum dolor sit amet\n",
        datetime(2020, 10, 24).timestamp(),
    )

    assert response.status == 200

    head_response = get_response_for_static_content(
        Request("HEAD", b"/", None),
        b"text/plain",
        b"Lorem ipsum dolor sit amet\n",
        datetime(2020, 10, 24).timestamp(),
    )

    data = await head_response.read()
    assert data is None

    for name in {b"content-length", b"content-type"}:
        # Note: a response with content has these headers handled automatically
        assert head_response.get_single_header(name) is not None


async def test_get_response_for_static_content_can_disable_max_age():
    response = get_response_for_static_content(
        Request("GET", b"/", None),
        b"text/plain",
        b"Lorem ipsum dolor sit amet\n",
        datetime(2020, 10, 24).timestamp(),
        cache_time=-1,
    )

    assert response.status == 200
    assert response.headers.contains(b"Cache-Control") is False

    response = get_response_for_static_content(
        Request("GET", b"/", None),
        b"text/plain",
        b"Lorem ipsum dolor sit amet\n",
        datetime(2020, 10, 24).timestamp(),
        cache_time=20,
    )
    assert response.status == 200
    assert b"20" in response.headers.get_first(b"Cache-Control")


async def test_get_response_for_static_content_handles_304():
    response = get_response_for_static_content(
        Request("GET", b"/", None),
        b"text/plain",
        b"Lorem ipsum dolor sit amet\n",
        datetime(2020, 10, 24).timestamp(),
    )

    assert response.status == 200

    response = get_response_for_static_content(
        Request("GET", b"/", [(b"If-None-Match", response.get_first_header(b"etag"))]),
        b"text/plain",
        b"Lorem ipsum dolor sit amet\n",
        datetime(2020, 10, 24).timestamp(),
    )

    assert response.status == 304


async def test_app_fallback_route_static_files(app):
    called = False

    def not_found_handler():
        nonlocal called
        called = True
        return text("Example", 404)

    app.router.fallback = not_found_handler

    app.serve_files(get_folder_path("files3"))

    await app.start()
    await app(
        get_example_scope("GET", "/not-registered", []), MockReceive(), MockSend()
    )

    response = app.response
    response_text = await response.text()
    assert response.status == 404
    assert called is True
    assert response_text == "Example"


async def test_app_404_handler_static_files_not_found(app):
    called = False

    @app.exception_handler(404)
    async def not_found_handler(*args):
        nonlocal called
        called = True
        return text("Example", 404)

    app.serve_files(get_folder_path("files3"))

    await app.start()
    await app(
        get_example_scope("GET", "/not-registered", []), MockReceive(), MockSend()
    )

    response = app.response
    response_text = await response.text()
    assert response.status == 404
    assert called is True
    assert response_text == "Example"


async def test_serve_files_index_html_options(files2_index_contents, app: Application):
    def on_response(request, response): ...

    mock = create_autospec(on_response, return_value=None)

    index_options = DefaultFileOptions(
        on_response=mock,
        cache_control=CacheControlHeaderValue(no_cache=True, no_store=True),
    )

    app.serve_files(get_folder_path("files2"), default_file_options=index_options)

    await app.start()

    scope = get_example_scope("GET", "/", [])
    await app(
        scope,
        MockReceive(),
        MockSend(),
    )

    assert mock.call_count == 1

    response = app.response
    assert response.status == 200
    assert files2_index_contents == await response.read()
    assert response.headers[b"cache-control"] == (b"no-cache, no-store",)

    scope = get_example_scope("GET", "/scripts/main.js", [])
    await app(
        scope,
        MockReceive(),
        MockSend(),
    )

    assert mock.call_count == 1
    response = app.response
    assert response.status == 200
    assert response.headers[b"cache-control"] != (b"no-cache, no-store",)


async def test_serve_files_index_html_options_fallback(
    files2_index_contents, app: Application
):
    def on_response(request, response): ...

    mock = create_autospec(on_response, return_value=None)

    index_options = DefaultFileOptions(
        on_response=mock,
        cache_control=CacheControlHeaderValue(no_cache=True, no_store=True),
    )

    app.serve_files(
        get_folder_path("files2"),
        fallback_document="index.html",
        default_file_options=index_options,
    )

    await app.start()

    scope = get_example_scope("GET", "/not-existent-file", [])
    await app(
        scope,
        MockReceive(),
        MockSend(),
    )

    assert mock.call_count == 1

    response = app.response
    assert response.status == 200
    assert files2_index_contents == await response.read()
    assert response.headers[b"cache-control"] == (b"no-cache, no-store",)

    scope = get_example_scope("GET", "/scripts/main.js", [])
    await app(
        scope,
        MockReceive(),
        MockSend(),
    )

    assert mock.call_count == 1
    response = app.response
    assert response.status == 200
    assert response.headers[b"cache-control"] != (b"no-cache, no-store",)
