import sys
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from typing import Any, AsyncIterable, Callable, Dict, Optional
from uuid import UUID, uuid4

import pytest

from blacksheep import Content, Cookie, Response, scribe
from blacksheep.exceptions import FailedRequestError
from blacksheep.server.controllers import (
    CannotDetermineDefaultViewNameError,
    Controller,
)
from blacksheep.server.responses import (
    ContentDispositionType,
    accepted,
    bad_request,
    created,
    file,
    forbidden,
    html,
    json,
    moved_permanently,
    no_content,
    not_found,
    not_modified,
    ok,
    permanent_redirect,
    pretty_json,
    redirect,
    see_other,
    status_code,
    temporary_redirect,
    text,
    unauthorized,
)
from blacksheep.server.routing import RoutesRegistry
from blacksheep.testing.helpers import get_example_scope
from blacksheep.testing.messages import MockReceive, MockSend
from tests.test_files_serving import get_file_path

STATUS_METHODS_OPTIONAL_BODY = [
    (ok, 200),
    (created, 201),
    (accepted, 202),
    (unauthorized, 401),
    (bad_request, 400),
    (forbidden, 403),
    (not_found, 404),
]

REDIRECT_METHODS = [
    (moved_permanently, 301),
    (redirect, 302),
    (see_other, 303),
    (temporary_redirect, 307),
    (permanent_redirect, 308),
]

STATUS_METHODS_NO_BODY = [(no_content, 204), (not_modified, 304)]

EXAMPLE_HTML = """
<!DOCTYPE html>
<html>
  <head>
    <title>Example</title>
    <style>
      h1 {
          color: pink;
      }
    </style>
    <link rel="stylesheet" type="text/css" href="/home.css" />
  </head>
  <body>
    <h1>Lorem ipsum 🍎</h1>
    <p>Dolor sit amet</p>
  </body>
</html>"""


@dataclass
class Demo:
    id: UUID
    name: str
    created_at: datetime


@dataclass
class Foo:
    id: UUID
    name: str
    ufo: bool


JSON_OBJECTS = [
    (
        Demo(
            UUID("00000000-0000-0000-0000-000000000000"),
            "Foo",
            datetime(2018, 8, 17, 20, 55, 4),
        ),
        {
            "id": "00000000-0000-0000-0000-000000000000",
            "name": "Foo",
            "created_at": "2018-08-17T20:55:04",
        },
    ),
    (
        Demo(
            UUID("00000000-0000-0000-0000-000000000001"),
            "Lorem ipsum",
            datetime(2015, 10, 21, 7, 28, 00),
        ),
        {
            "id": "00000000-0000-0000-0000-000000000001",
            "name": "Lorem ipsum",
            "created_at": "2015-10-21T07:28:00",
        },
    ),
]


async def read_from_asynciterable(method: Callable[[], AsyncIterable[bytes]]) -> str:
    parts = []
    async for chunk in method():
        parts.append(chunk.decode("utf8"))
    return "".join(parts)


def test_response_supports_dynamic_attributes():
    response = Response(200)
    foo = object()

    assert (
        hasattr(response, "response") is False
    ), "This test makes sense if such attribute is not defined"
    response.foo = foo  # type: ignore
    assert response.foo is foo  # type: ignore


@pytest.mark.parametrize(
    "response,cookies,expected_result",
    [
        (
            Response(400, [(b"Server", b"BlackSheep")]).with_content(
                Content(b"text/plain", b"Hello, World")
            ),
            [],
            b"HTTP/1.1 400 Bad Request\r\n"
            b"Server: BlackSheep\r\n"
            b"content-type: text/plain\r\n"
            b"content-length: 12\r\n\r\nHello, World",
        ),
        (
            Response(400, [(b"Server", b"BlackSheep")]).with_content(
                Content(b"text/plain", b"Hello, World")
            ),
            [Cookie("session", "123")],
            b"HTTP/1.1 400 Bad Request\r\n"
            b"Server: BlackSheep\r\n"
            b"set-cookie: session=123\r\n"
            b"content-type: text/plain\r\n"
            b"content-length: 12\r\n\r\nHello, World",
        ),
        (
            Response(400, [(b"Server", b"BlackSheep")]).with_content(
                Content(b"text/plain", b"Hello, World")
            ),
            [Cookie("session", "123"), Cookie("aaa", "bbb", domain="bezkitu.org")],
            b"HTTP/1.1 400 Bad Request\r\n"
            b"Server: BlackSheep\r\n"
            b"set-cookie: session=123\r\n"
            b"set-cookie: aaa=bbb; Domain=bezkitu.org\r\n"
            b"content-type: text/plain\r\n"
            b"content-length: 12\r\n\r\nHello, World",
        ),
    ],
)
async def test_write_http_response(response, cookies, expected_result):
    response.set_cookies(cookies)
    data = b""
    async for chunk in scribe.write_response(response):
        data += chunk
    assert data == expected_result


def test_is_redirect():
    # 301 Moved Permanently
    # 302 Found
    # 303 See Other
    # 307 Temporary Redirect
    # 308 Permanent Redirect
    for status in range(200, 500):
        response = Response(status)
        is_redirect = status in {301, 302, 303, 307, 308}
        assert response.is_redirect() == is_redirect


@pytest.mark.parametrize("method,expected_status", REDIRECT_METHODS)
async def test_redirect_method(method, expected_status, app):
    @app.router.get("/")
    async def home():
        return method("https://foo.org/somewhere")

    await app(
        get_example_scope("GET", "/", []),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == expected_status
    location = response.headers.get_single(b"location")
    assert location == b"https://foo.org/somewhere"


@pytest.mark.parametrize("method", (method for method, _ in REDIRECT_METHODS))
def test_redirect_method_raises_for_invalid_location(method):
    with pytest.raises(ValueError):
        method(location=True)

    with pytest.raises(ValueError):
        method(location=100)


@pytest.mark.parametrize("method,expected_status", REDIRECT_METHODS)
async def test_redirect_method_bytes_location(method, expected_status, app):
    @app.router.get("/")
    async def home():
        return method(b"https://foo.org/somewhere")

    await app(
        get_example_scope("GET", "/", []),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == expected_status
    location = response.headers.get_single(b"location")
    assert location == b"https://foo.org/somewhere"


@pytest.mark.parametrize("method,expected_status", STATUS_METHODS_NO_BODY)
async def test_no_body_method(method, expected_status, app):
    @app.router.get("/")
    async def home():
        return method()

    await app(
        get_example_scope("GET", "/", []),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == expected_status
    assert response.has_body() is False


@pytest.mark.parametrize("method,expected_status", STATUS_METHODS_OPTIONAL_BODY)
async def test_status_method_response(method, expected_status, app):
    @app.router.get("/")
    async def home():
        return method("Everything's good")

    await app(
        get_example_scope("GET", "/", []),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == expected_status
    content = await app.response.text()
    assert content == "Everything's good"


@pytest.mark.parametrize("method,expected_status", STATUS_METHODS_OPTIONAL_BODY)
async def test_status_method_response_empty_body(method, expected_status, app):
    @app.router.get("/")
    async def home():
        return method()

    await app(
        get_example_scope("GET", "/", []),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == expected_status
    content = await app.response.text()
    assert content == ""


@pytest.mark.parametrize("method,expected_status", STATUS_METHODS_OPTIONAL_BODY)
async def test_status_method_response_with_object(method, expected_status, app):
    @app.router.get("/")
    async def home():
        return method(Foo(uuid4(), "foo", True))

    await app(
        get_example_scope("GET", "/", []),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == expected_status
    content = await app.response.json()
    assert content.get("name") == "foo"
    assert content.get("ufo") is True


@pytest.mark.parametrize("status", [200, 201, 202, 400, 404, 500])
async def test_status_code_response_with_text(status: int, app):
    @app.router.get("/")
    async def home():
        return status_code(status, "Everything's good")

    await app(
        get_example_scope("GET", "/", []),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == status
    content = await app.response.text()
    assert content == "Everything's good"


@pytest.mark.parametrize("status", [200, 201, 202, 400, 404, 500])
async def test_status_code_response_with_empty_body(status: int, app):
    @app.router.get("/")
    async def home():
        return status_code(status)

    await app(
        get_example_scope("GET", "/", []),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == status
    content = await app.response.text()
    assert content == ""


@pytest.mark.parametrize("status", [200, 201, 202, 400, 404, 500])
async def test_status_code_response_with_object(status: int, app):
    @app.router.get("/")
    async def home():
        return status_code(status, Foo(uuid4(), "foo", True))

    await app(
        get_example_scope("GET", "/", []),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == status
    content = await app.response.json()
    assert content.get("name") == "foo"
    assert content.get("ufo") is True


async def test_created_response_with_empty_body(app):
    @app.router.get("/")
    async def home():
        return created(location="https://foo.org/foo/001")

    await app(
        get_example_scope("GET", "/", []),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 201
    location = response.headers.get_single(b"location")
    assert location == b"https://foo.org/foo/001"


async def test_created_response_with_value(app):
    @app.router.get("/")
    async def home():
        return created(
            Foo(UUID("726807b3-5a82-4a59-8bed-65639d3529ba"), "example", False),
            location="https://foo.org/foo/726807b3-5a82-4a59-8bed-65639d3529ba",
        )

    await app(
        get_example_scope("GET", "/", []),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 201
    location = response.headers.get_single(b"location")
    assert location == b"https://foo.org/foo/726807b3-5a82-4a59-8bed-65639d3529ba"
    content = await app.response.json()
    assert content.get("id") == "726807b3-5a82-4a59-8bed-65639d3529ba"
    assert content.get("name") == "example"
    assert content.get("ufo") is False


async def test_text_response_default_status(app):
    @app.router.get("/")
    async def home():
        return text("Hello World")

    await app(
        get_example_scope("GET", "/", []),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 200

    content_type = response.headers.get_single(b"content-type")
    assert content_type == b"text/plain; charset=utf-8"

    body = await response.text()
    assert body == "Hello World"


@pytest.mark.parametrize(
    "content,status",
    [
        ("Hello World", 200),
        ("Hello World", 400),
        ("🍎 🐍", 200),
        ("""Lorem ipsum dolor sit amet""", 200),
    ],
)
async def test_text_response_with_status(content, status, app):
    @app.router.get("/")
    async def home():
        return text(content, status)

    await app(
        get_example_scope("GET", "/", []),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == status

    content_type = response.headers.get_single(b"content-type")
    assert content_type == b"text/plain; charset=utf-8"

    body = await response.text()
    assert body == content


async def test_html_response_default_status(app):
    @app.router.get("/")
    async def home():
        return html(EXAMPLE_HTML)

    await app(
        get_example_scope("GET", "/", []),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 200

    content_type = response.headers.get_single(b"content-type")
    assert content_type == b"text/html; charset=utf-8"

    body = await response.text()
    assert body == EXAMPLE_HTML


@pytest.mark.parametrize(
    "content,status",
    [
        (EXAMPLE_HTML, 200),
        (EXAMPLE_HTML, 400),
        ("<div><h2>Partial View</h2><p>Lorem ipsum dolor sit amet</p></div>", 200),
        ("<div><h2>Partial View</h2><p>Lorem ipsum dolor sit amet</p></div>", 400),
    ],
)
async def test_html_response_with_status(content, status, app):
    @app.router.get("/")
    async def home():
        return html(content, status)

    await app(
        get_example_scope("GET", "/", []),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == status

    content_type = response.headers.get_single(b"content-type")
    assert content_type == b"text/html; charset=utf-8"

    body = await response.text()
    assert body == content


@pytest.mark.parametrize("obj,values", JSON_OBJECTS)
async def test_json_response(obj: Any, values: Dict[str, Any], app):
    @app.router.get("/")
    async def home():
        return json(obj)

    await app(
        get_example_scope("GET", "/", []),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 200

    content_type = response.headers.get_single(b"content-type")
    assert content_type == b"application/json"

    raw = await response.text()
    data = await response.json()
    for name, value in values.items():
        assert data.get(name) == value

        if isinstance(value, str):
            assert f'"{name}":"{value}"' in raw
        else:
            assert f'"{name}":' in raw


@pytest.mark.parametrize("obj,values", JSON_OBJECTS)
async def test_pretty_json_response(obj: Any, values: Dict[str, Any], app):
    @app.router.get("/")
    async def home():
        return pretty_json(obj)

    await app(
        get_example_scope("GET", "/", []),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 200

    content_type = response.headers.get_single(b"content-type")
    assert content_type == b"application/json"

    raw = await response.text()
    data = await response.json()
    for name, value in values.items():
        assert data.get(name) == value
        if isinstance(value, str):
            assert f'    "{name}": "{value}"' in raw
        else:
            assert f'    "{name}": ' in raw


async def test_file_response_from_fs(app):
    file_path = get_file_path("example.config", "files2")

    @app.router.get("/")
    async def home():
        return file(file_path, "text/plain; charset=utf-8")

    await app(
        get_example_scope("GET", "/", []),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 200
    assert response.headers.get_single(b"content-type") == b"text/plain; charset=utf-8"
    assert response.headers.get_single(b"content-disposition") == b"attachment"

    text = await response.text()
    with open(file_path, mode="rt", encoding="utf8") as f:
        contents = f.read()
        assert contents == text


async def test_file_response_from_fs_with_filename(app):
    file_path = get_file_path("example.config", "files2")

    @app.router.get("/")
    async def home():
        return file(file_path, "text/plain; charset=utf-8", file_name="foo.xml")

    await app(
        get_example_scope("GET", "/", []),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 200
    assert response.headers.get_single(b"content-type") == b"text/plain; charset=utf-8"
    assert (
        response.headers.get_single(b"content-disposition")
        == b'attachment; filename="foo.xml"'
    )

    text = await response.text()
    with open(file_path, mode="rt", encoding="utf8") as f:
        contents = f.read()
        assert contents == text


async def get_example_css():
    yield b"body {\n"
    yield b"    background-color: red;\n"
    yield b"}\n"
    yield b"\n"
    yield b"h1 {\n"
    yield b"    font-size: 2rem;\n"
    yield b"}\n"


async def test_file_response_from_generator(app):
    @app.router.get("/")
    async def home():
        return file(get_example_css, "text/css")

    await app(
        get_example_scope("GET", "/", []),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 200
    assert response.headers.get_single(b"content-type") == b"text/css"
    assert response.headers.get_single(b"content-disposition") == b"attachment"

    text = await response.text()
    assert text == await read_from_asynciterable(get_example_css)


async def test_file_response_from_bytes_io(app):
    bytes_io: Optional[BytesIO] = None

    @app.router.get("/")
    async def home():
        nonlocal bytes_io
        bytes_io = BytesIO()
        bytes_io.write("Żywią i bronią".encode("utf-8"))
        return file(bytes_io, "text/plain; charset=utf-8", file_name="foo.txt")

    await app(
        get_example_scope("GET", "/", []),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 200
    assert response.headers.get_single(b"content-type") == b"text/plain; charset=utf-8"
    assert (
        response.headers.get_single(b"content-disposition")
        == b'attachment; filename="foo.txt"'
    )

    assert bytes_io is not None
    assert bytes_io.closed  # type: ignore


async def test_file_response_from_generator_inline(app):
    @app.router.get("/")
    async def home():
        return file(
            get_example_css,
            "text/css",
            content_disposition=ContentDispositionType.INLINE,
        )

    await app(
        get_example_scope("GET", "/", []),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 200
    assert response.headers.get_single(b"content-type") == b"text/css"
    assert response.headers.get_single(b"content-disposition") == b"inline"

    text = await response.text()
    assert text == await read_from_asynciterable(get_example_css)


async def test_file_response_from_bytes(app):
    @app.router.get("/")
    async def home():
        return file(
            EXAMPLE_HTML.encode("utf8"),
            "text/css",
            file_name="home.css",
            content_disposition=ContentDispositionType.INLINE,
        )

    await app(
        get_example_scope("GET", "/", []),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 200
    assert response.headers.get_single(b"content-type") == b"text/css"
    assert (
        response.headers.get_single(b"content-disposition")
        == b'inline; filename="home.css"'
    )

    text = await response.text()
    assert text == EXAMPLE_HTML


async def test_file_response_from_byte_array(app):
    value = bytearray()
    value.extend(b"Hello!\n")
    value.extend(b"World!\n\n")
    value.extend(b"...")
    expected_result = bytes(value).decode("utf8")

    @app.router.get("/")
    async def home():
        return file(
            value,
            "text/plain",
            file_name="example.txt",
            content_disposition=ContentDispositionType.INLINE,
        )

    await app(
        get_example_scope("GET", "/", []),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 200
    assert response.headers.get_single(b"content-type") == b"text/plain"
    assert (
        response.headers.get_single(b"content-disposition")
        == b'inline; filename="example.txt"'
    )

    text = await response.text()
    assert text == expected_result


async def test_file_response_from_generator_inline_with_name(app):
    @app.router.get("/")
    async def home():
        return file(
            get_example_css,
            "text/css",
            file_name="home.css",
            content_disposition=ContentDispositionType.INLINE,
        )

    await app(
        get_example_scope("GET", "/", []),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 200
    assert response.headers.get_single(b"content-type") == b"text/css"
    assert (
        response.headers.get_single(b"content-disposition")
        == b'inline; filename="home.css"'
    )

    text = await response.text()
    assert text == await read_from_asynciterable(get_example_css)


def test_files_raises_for_invalid_input():
    with pytest.raises(ValueError):
        file(True, "text/plain")  # type: ignore

    with pytest.raises(ValueError):
        file(100, "text/plain")  # type: ignore

    with pytest.raises(ValueError):
        file([10, 120, 400], "text/plain")  # type: ignore


def test_files_raises_for_invalid_name_with_folder_path():
    with pytest.raises(ValueError):
        file(b"Hello, There!", "text/plain", file_name="not_good/")


def test_json_response_raises_for_not_json_serializable():
    class NotSerializable:
        def __init__(self) -> None:
            self.foo = True
            self.might_be_secret = "iunisud109283012"

    with pytest.raises(TypeError):
        json(NotSerializable())


@pytest.mark.parametrize("status", [200, 201, 202, 400, 404, 500])
async def test_status_code_response_with_text_in_controller(status: int, app):
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    class Home(Controller):
        @get("/")
        def greet(self):
            return self.status_code(status, "Everything's good")

    await app.start()

    await app(
        get_example_scope("GET", "/", []),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == status
    content = await app.response.text()
    assert content == "Everything's good"


@pytest.mark.parametrize("method,expected_status", STATUS_METHODS_OPTIONAL_BODY)
async def test_status_method_response_in_controller(method, expected_status, app):
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    method_name = method.__name__

    class Home(Controller):
        @get("/")
        def greet(self):
            controller_method = getattr(Home, method_name, None)
            return controller_method(self, "Everything's good")

    controller_method = getattr(Home, method_name, None)
    assert callable(controller_method)

    await app.start()

    await app(
        get_example_scope("GET", "/", []),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == expected_status
    content = await app.response.text()
    assert content == "Everything's good"


@pytest.mark.parametrize("method,expected_status", STATUS_METHODS_NO_BODY)
async def test_status_method_without_body_response_in_controller(
    method, expected_status, app
):
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    method_name = method.__name__

    class Home(Controller):
        @get("/")
        def greet(self):
            controller_method = getattr(Home, method_name, None)
            return controller_method(self)

    controller_method = getattr(Home, method_name, None)
    assert callable(controller_method)

    await app.start()

    await app(
        get_example_scope("GET", "/", []),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == expected_status
    assert response.has_body() is False


@pytest.mark.parametrize("method,expected_status", REDIRECT_METHODS)
async def test_redirect_method_in_controller(method, expected_status, app):
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    method_name = method.__name__

    class Home(Controller):
        @get("/")
        def greet(self):
            controller_method = getattr(Home, method_name, None)
            return controller_method(self, "https://foo.org/somewhere")

    controller_method = getattr(Home, method_name, None)
    assert callable(controller_method)

    await app.start()

    await app(
        get_example_scope("GET", "/", []),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == expected_status
    location = response.headers.get_single(b"location")
    assert location == b"https://foo.org/somewhere"


async def test_view_methods_in_controller_throw_if_view_name_cannot_be_determined():
    class Home(Controller):
        pass

    home = Home()
    with pytest.raises(CannotDetermineDefaultViewNameError):
        home.view()

    with pytest.raises(CannotDetermineDefaultViewNameError):
        await home.view_async()


async def test_view_methods_in_controller_throw_if_sys_get_frame_is_not_defined():
    class Home(Controller):
        pass

    def monkey_getframe(num: int):
        raise AttributeError("Test")

    base_getframe = sys._getframe
    sys._getframe = monkey_getframe

    home = Home()
    with pytest.raises(CannotDetermineDefaultViewNameError):
        home.view()

    sys._getframe = base_getframe


@pytest.mark.parametrize("obj,values", JSON_OBJECTS)
async def test_json_response_in_controller(obj: Any, values: Dict[str, Any], app):
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    class Home(Controller):
        @get("/")
        def greet(self):
            return self.json(obj)

    await app.start()

    await app(
        get_example_scope("GET", "/", []),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 200

    content_type = response.headers.get_single(b"content-type")
    assert content_type == b"application/json"

    raw = await response.text()
    data = await response.json()
    for name, value in values.items():
        assert data.get(name) == value

        if isinstance(value, str):
            assert f'"{name}":"{value}"' in raw
        else:
            assert f'"{name}":' in raw


@pytest.mark.parametrize("obj,values", JSON_OBJECTS)
async def test_pretty_json_response_in_controller(
    obj: Any, values: Dict[str, Any], app
):
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    class Home(Controller):
        @get("/")
        def greet(self):
            return self.pretty_json(obj)

    await app.start()

    await app(
        get_example_scope("GET", "/", []),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    raw = await response.text()
    assert response.status == 200

    content_type = response.headers.get_single(b"content-type")
    assert content_type == b"application/json"

    raw = await response.text()
    data = await response.json()
    for name, value in values.items():
        assert data.get(name) == value
        if isinstance(value, str):
            assert f'    "{name}": "{value}"' in raw
        else:
            assert f'    "{name}": ' in raw


async def test_response_raise_for_status():
    response = Response(200)
    await response.raise_for_status()

    response = Response(404).with_content(Content(b"text/plain", b"Hello, World"))

    with pytest.raises(FailedRequestError) as exc_info:
        await response.raise_for_status()

    assert exc_info.value.status == 404
    assert exc_info.value.data == "Hello, World"

    response = Response(500).with_content(
        Content(b"text/plain", b"Internal server error")
    )

    with pytest.raises(FailedRequestError) as exc_info:
        await response.raise_for_status()

    assert exc_info.value.status == 500
    assert exc_info.value.data == "Internal server error"
