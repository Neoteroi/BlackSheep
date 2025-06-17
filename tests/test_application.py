import asyncio
import json
import os
import re
import sys
from base64 import urlsafe_b64decode, urlsafe_b64encode
from collections.abc import AsyncIterable
from dataclasses import dataclass
from datetime import date, datetime
from functools import wraps
from typing import Annotated, Any, Dict, Generic, List, Optional, TypeVar
from uuid import UUID, uuid4

import pytest
from guardpost import AuthenticationHandler, Identity, User
from openapidocs.v3 import Info
from pydantic import VERSION as PYDANTIC_LIB_VERSION
from pydantic import BaseModel, Field, ValidationError
from rodi import Container, inject

from blacksheep import (
    HTTPException,
    JSONContent,
    Request,
    Response,
    TextContent,
)
from blacksheep.contents import FormPart
from blacksheep.exceptions import Conflict, InternalServerError, NotFound
from blacksheep.server.application import Application, ApplicationSyncEvent
from blacksheep.server.bindings import (
    ClientInfo,
    FromBytes,
    FromCookie,
    FromFiles,
    FromForm,
    FromHeader,
    FromJSON,
    FromQuery,
    FromRoute,
    FromServices,
    FromText,
    RequestUser,
    ServerInfo,
)
from blacksheep.server.di import di_scope_middleware
from blacksheep.server.normalization import ensure_response
from blacksheep.server.openapi.v3 import OpenAPIHandler
from blacksheep.server.resources import get_resource_file_path
from blacksheep.server.responses import status_code, text
from blacksheep.server.routing import Router, SharedRouterError
from blacksheep.server.security.hsts import HSTSMiddleware
from blacksheep.server.sse import ServerSentEvent, TextServerSentEvent
from blacksheep.testing.helpers import get_example_scope
from blacksheep.testing.messages import MockReceive, MockSend
from tests.utils.application import FakeApplication
from tests.utils.folder import ensure_folder

try:
    # v2
    from pydantic import validate_call
except ImportError:
    # v1
    # v1 validate_arguments is not supported
    # https://github.com/Neoteroi/BlackSheep/issues/559
    validate_call = None


class Item:
    def __init__(self, a, b, c):
        self.a = a
        self.b = b
        self.c = c


@dataclass
class Item2:
    a: str
    b: str
    c: str


class Foo:
    def __init__(self, item) -> None:
        self.item = Item(**item)


def read_multipart_mix_dat():
    with open(
        get_resource_file_path("tests", os.path.join("res", "multipart-mix.dat")),
        mode="rb",
    ) as dat_file:
        return dat_file.read()


async def test_application_supports_dynamic_attributes(app):
    foo = object()

    assert (
        hasattr(app, "foo") is False
    ), "This test makes sense if such attribute is not defined"
    app.foo = foo  # type: ignore
    assert app.foo is foo  # type: ignore


async def test_application_get_handler(app):
    @app.router.get("/")
    async def home(request):
        pass

    @app.router.get("/foo")
    async def foo(request):
        pass

    await app(get_example_scope("GET", "/"), MockReceive(), MockSend())

    assert app.request is not None
    request: Request = app.request

    assert request is not None

    connection = request.headers[b"connection"]
    assert connection == (b"keep-alive",)


async def test_application_post_multipart_formdata(app):
    @app.router.post("/files/upload")
    async def upload_files(request):
        data = await request.multipart()
        assert data is not None

        assert data[0].name == b"text1"
        assert data[0].file_name is None
        assert data[0].content_type is None
        assert data[0].data == b"text default"

        assert data[1].name == b"text2"
        assert data[1].file_name is None
        assert data[1].content_type is None
        assert data[1].data == "aωb".encode("utf8")

        assert data[2].name == b"file1"
        assert data[2].file_name == b"a.txt"
        assert data[2].content_type == b"text/plain"
        assert data[2].data == b"Content of a.txt.\r\n"

        assert data[3].name == b"file2"
        assert data[3].file_name == b"a.html"
        assert data[3].content_type == b"text/html"
        assert data[3].data == b"<!DOCTYPE html><title>Content of a.html.</title>\r\n"

        assert data[4].name == b"file3"
        assert data[4].file_name == b"binary"
        assert data[4].content_type == b"application/octet-stream"
        assert data[4].data == "aωb".encode("utf8")

        files = await request.files()

        assert files[0].name == b"file1"
        assert files[0].file_name == b"a.txt"
        assert files[0].content_type == b"text/plain"
        assert files[0].data == b"Content of a.txt.\r\n"

        assert files[1].name == b"file2"
        assert files[1].file_name == b"a.html"
        assert files[1].content_type == b"text/html"
        assert files[1].data == b"<!DOCTYPE html><title>Content of a.html.</title>\r\n"

        assert files[2].name == b"file3"
        assert files[2].file_name == b"binary"
        assert files[2].content_type == b"application/octet-stream"
        assert files[2].data == "aωb".encode("utf8")

        file_one = await request.files("file1")
        assert file_one[0].name == b"file1"

        return Response(200)

    boundary = b"---------------------0000000000000000000000001"

    content = b"\r\n".join(
        [
            boundary,
            b'Content-Disposition: form-data; name="text1"',
            b"",
            b"text default",
            boundary,
            b'Content-Disposition: form-data; name="text2"',
            b"",
            "aωb".encode("utf8"),
            boundary,
            b'Content-Disposition: form-data; name="file1"; filename="a.txt"',
            b"Content-Type: text/plain",
            b"",
            b"Content of a.txt.",
            b"",
            boundary,
            b'Content-Disposition: form-data; name="file2"; filename="a.html"',
            b"Content-Type: text/html",
            b"",
            b"<!DOCTYPE html><title>Content of a.html.</title>",
            b"",
            boundary,
            b'Content-Disposition: form-data; name="file3"; filename="binary"',
            b"Content-Type: application/octet-stream",
            b"",
            "aωb".encode("utf8"),
            boundary + b"--",
        ]
    )
    await app(
        get_example_scope(
            "POST",
            "/files/upload",
            [
                (b"content-length", str(len(content)).encode()),
                (b"content-type", b"multipart/form-data; boundary=" + boundary),
            ],
        ),
        MockReceive([content]),
        MockSend(),
    )

    assert app.response is not None
    response: Response = app.response

    data = await response.text()

    assert response is not None
    assert response.status == 200, data


async def test_application_post_handler(app):
    called_times = 0

    @app.router.post("/api/cat")
    async def create_cat(request):
        nonlocal called_times
        called_times += 1
        assert request is not None

        content = await request.read()
        assert b'{"name":"Celine","kind":"Persian"}' == content

        data = await request.json()
        assert {"name": "Celine", "kind": "Persian"} == data

        return Response(201, [(b"Server", b"Python/3.7")], JSONContent({"id": "123"}))

    content = b'{"name":"Celine","kind":"Persian"}'

    await app(
        get_example_scope(
            "POST",
            "/api/cat",
            [
                (b"content-length", str(len(content)).encode()),
                (b"content-type", b"application/json"),
            ],
        ),
        MockReceive([content]),
        MockSend(),
    )

    response = app.response
    assert called_times == 1
    response_data = await response.json()
    assert {"id": "123"} == response_data


async def test_application_post_handler_invalid_content_type(app):
    called_times = 0

    @app.router.post("/api/cat")
    async def create_cat(request):
        nonlocal called_times
        called_times += 1
        assert request is not None

        content = await request.read()
        assert b'{"name":"Celine","kind":"Persian"}' == content

        data = await request.json()
        assert data is None

        return Response(400)

    content = b'{"name":"Celine","kind":"Persian"}'

    await app(
        get_example_scope(
            "POST",
            "/api/cat",
            [
                (b"content-length", str(len(content)).encode()),
                (b"content-type", b"text/plain"),
            ],
        ),
        MockReceive([content]),
        MockSend(),
    )

    response: Response = app.response
    assert called_times == 1
    assert response.status == 400


async def test_application_post_json_handles_missing_body(app):
    @app.router.post("/api/cat")
    async def create_cat(request):
        assert request is not None

        content = await request.read()
        assert b"" == content

        text = await request.text()
        assert "" == text

        data = await request.json()
        assert data is None

        return Response(201)

    await app(
        get_example_scope("POST", "/api/cat", []),
        MockReceive([]),
        MockSend(),
    )

    response = app.response
    assert response.status == 201


async def test_application_returns_400_for_invalid_json(app):
    @app.router.post("/api/cat")
    async def create_cat(request):
        await request.json()
        ...

    # invalid JSON:
    content = b'"name":"Celine";"kind":"Persian"'

    await app(
        get_example_scope(
            "POST",
            "/api/cat",
            [
                (b"content-length", str(len(content)).encode()),
                (b"content-type", b"application/json"),
            ],
        ),
        MockReceive([content]),
        MockSend(),
    )

    response = app.response
    assert response.status == 400
    assert response.content.body == (
        b"Bad Request: Declared Content-Type is application/json but "
        b"the content cannot be parsed as JSON."
    )


async def test_application_middlewares_one(app):
    calls = []

    async def middleware_one(request, handler):
        nonlocal calls
        calls.append(1)
        response = await handler(request)
        calls.append(2)
        return response

    async def middleware_two(request, handler):
        nonlocal calls
        calls.append(3)
        response = await handler(request)
        calls.append(4)
        return response

    @app.router.get("/")
    async def example(request):
        nonlocal calls
        calls.append(5)
        return Response(200, [(b"Server", b"Python/3.7")], JSONContent({"id": "123"}))

    app.middlewares.append(middleware_one)
    app.middlewares.append(middleware_two)

    await app(get_example_scope("GET", "/"), MockReceive(), MockSend())

    assert app.response is not None
    response: Response = app.response

    assert response is not None
    assert response.status == 200
    assert calls == [1, 3, 5, 4, 2]


async def test_application_middlewares_as_classes(app):
    calls = []

    class MiddlewareExample:
        def __init__(self, calls: List[int], seed: int) -> None:
            self.seed = seed
            self.calls = calls

        def get_seed(self) -> int:
            self.seed += 1
            return self.seed

        async def __call__(self, request, handler):
            self.calls.append(self.get_seed())
            response = await handler(request)
            self.calls.append(self.get_seed())
            return response

    @app.router.route("/")
    async def example(request):
        nonlocal calls
        calls.append(5)
        return Response(200, [(b"Server", b"Python/3.7")], JSONContent({"id": "123"}))

    app.middlewares.append(MiddlewareExample(calls, 0))
    app.middlewares.append(MiddlewareExample(calls, 2))

    await app(get_example_scope("GET", "/"), MockReceive([]), MockSend())

    assert app.response is not None
    response: Response = app.response

    assert response is not None
    assert response.status == 200
    assert calls == [1, 3, 5, 4, 2]


async def test_application_middlewares_are_applied_only_once(app):
    """
    This test checks that the same request handled bound to several routes
    is normalized only once with middlewares, and that more calls to
    configure_middlewares don't apply several times the chain of middlewares.
    """
    calls = []

    async def example(request: Request):
        nonlocal calls
        calls.append(2)
        return None

    app.router.add_get("/", example)
    app.router.add_head("/", example)

    async def middleware(request, handler):
        nonlocal calls
        calls.append(1)
        response = await handler(request)
        return response

    app.middlewares.append(middleware)

    for method, _ in {("GET", 1), ("GET", 2), ("HEAD", 1), ("HEAD", 2)}:
        await app(get_example_scope(method, "/"), MockReceive([]), MockSend())

        assert app.response is not None
        response: Response = app.response

        assert response is not None
        assert response.status == 204
        assert calls == [1, 2]

        calls.clear()


async def test_application_middlewares_two(app):
    calls = []

    async def middleware_one(request, handler):
        nonlocal calls
        calls.append(1)
        response = await handler(request)
        calls.append(2)
        return response

    async def middleware_two(request, handler):
        nonlocal calls
        calls.append(3)
        response = await handler(request)
        calls.append(4)
        return response

    async def middleware_three(request, handler):
        nonlocal calls
        calls.append(6)
        response = await handler(request)
        calls.append(7)
        return response

    @app.router.get("/")
    async def example(request):
        nonlocal calls
        calls.append(5)
        return Response(200, [(b"Server", b"Python/3.7")], JSONContent({"id": "123"}))

    app.middlewares.append(middleware_one)
    app.middlewares.append(middleware_two)
    app.middlewares.append(middleware_three)

    await app(get_example_scope("GET", "/"), MockReceive([]), MockSend())

    assert app.response is not None
    response: Response = app.response

    assert response is not None
    assert response.status == 200
    assert calls == [1, 3, 6, 5, 7, 4, 2]


async def test_application_middlewares_skip_handler(app):
    calls = []

    async def middleware_one(request, handler):
        nonlocal calls
        calls.append(1)
        response = await handler(request)
        calls.append(2)
        return response

    async def middleware_two(request, handler):
        nonlocal calls
        calls.append(3)
        response = await handler(request)
        calls.append(4)
        return response

    async def middleware_three(request, handler):
        nonlocal calls
        calls.append(6)
        return Response(403)

    @app.router.get("/")
    async def example(request):
        nonlocal calls
        calls.append(5)
        return Response(200, [(b"Server", b"Python/3.7")], JSONContent({"id": "123"}))

    app.middlewares.append(middleware_one)
    app.middlewares.append(middleware_two)
    app.middlewares.append(middleware_three)

    await app(get_example_scope("GET", "/"), MockReceive([]), MockSend())

    assert app.response is not None
    response: Response = app.response

    assert response is not None
    assert response.status == 403
    assert calls == [1, 3, 6, 4, 2]


async def test_application_post_multipart_formdata_files_handler(app):
    ensure_folder("out")
    ensure_folder("tests/out")

    @app.router.post("/files/upload")
    async def upload_files(request):
        files = await request.files("files[]")

        # NB: in this example; we save files to output folder and verify
        # that their binaries are identical
        for part in files:
            full_path = get_resource_file_path(
                "tests", f"out/{part.file_name.decode()}"
            )
            with open(full_path, mode="wb") as saved_file:
                saved_file.write(part.data)

        return Response(200)

    boundary = b"---------------------0000000000000000000000001"
    lines = []

    file_names = {
        "pexels-photo-126407.jpeg",
        "pexels-photo-302280.jpeg",
        "pexels-photo-730896.jpeg",
    }

    rel_path = "files/"

    for file_name in file_names:
        full_path = get_resource_file_path("tests", f"{rel_path}{file_name}")
        with open(full_path, mode="rb") as source_file:
            binary = source_file.read()
            lines += [
                boundary,
                b'Content-Disposition: form-data; name="files[]"; filename="'
                + file_name.encode()
                + b'"',
                b"",
                binary,
            ]

    lines += [boundary + b"--"]
    content = b"\r\n".join(lines)

    await app(
        get_example_scope(
            "POST",
            "/files/upload",
            [
                [b"content-length", str(len(content)).encode()],
                [b"content-type", b"multipart/form-data; boundary=" + boundary],
            ],
        ),
        MockReceive([content]),
        MockSend(),
    )

    assert app.response is not None
    response: Response = app.response

    body = await response.text()
    assert response.status == 200, body

    # now files are in both folders: compare to ensure they are identical
    for file_name in file_names:
        full_path = get_resource_file_path("tests", f"{rel_path}{file_name}")
        copy_full_path = get_resource_file_path("tests", f"out/{file_name}")

        with open(full_path, mode="rb") as source_file:
            binary = source_file.read()
            with open(copy_full_path, mode="rb") as file_clone:
                clone_binary = file_clone.read()

                assert binary == clone_binary


async def test_application_http_exception_handlers(app):
    called = False

    async def exception_handler(self, request, http_exception):
        nonlocal called
        assert request is not None
        called = True
        return Response(200, content=TextContent("Called"))

    app.exceptions_handlers[519] = exception_handler

    @app.router.get("/")
    async def home(request):
        raise HTTPException(519)

    await app(get_example_scope("GET", "/"), MockReceive, MockSend())

    assert app.response is not None
    response: Response = app.response

    assert response is not None
    assert called is True, "Http exception handler was called"

    text = await response.text()
    assert text == "Called", (
        "The response is the one returned by " "defined http exception handler"
    )


async def test_application_http_exception_handlers_called_in_application_context(app):
    async def exception_handler(self, request, http_exception):
        nonlocal app
        assert self is app
        return Response(200, content=TextContent("Called"))

    app.exceptions_handlers[519] = exception_handler

    @app.router.get("/")
    async def home(request):
        raise HTTPException(519)

    await app(get_example_scope("GET", "/"), MockReceive(), MockSend())
    assert app.response is not None
    response: Response = app.response

    assert response is not None
    text = await response.text()
    assert text == "Called", (
        "The response is the one returned by " "defined http exception handler"
    )


async def test_application_user_defined_exception_handlers(app):
    called = False

    class CustomException(Exception):
        pass

    async def exception_handler(self, request, exception: CustomException):
        nonlocal called
        assert request is not None
        called = True
        return Response(200, content=TextContent("Called"))

    app.exceptions_handlers[CustomException] = exception_handler

    @app.router.get("/")
    async def home(request):
        raise CustomException()

    await app(get_example_scope("GET", "/"), MockReceive(), MockSend())

    assert app.response is not None
    response: Response = app.response

    assert response is not None
    assert called is True, "Http exception handler was called"

    text = await response.text()
    assert text == "Called", (
        "The response is the one returned by " "defined http exception handler"
    )


async def test_user_defined_exception_handlers_called_in_application_context(app):
    class CustomException(Exception):
        pass

    async def exception_handler(
        self: FakeApplication, request: Request, exc: CustomException
    ) -> Response:
        nonlocal app
        assert self is app
        assert isinstance(exc, CustomException)
        return Response(200, content=TextContent("Called"))

    app.exceptions_handlers[CustomException] = exception_handler

    @app.router.get("/")
    async def home(request):
        raise CustomException()

    await app(get_example_scope("GET", "/"), MockReceive(), MockSend())

    assert app.response is not None
    response: Response = app.response

    assert response is not None
    text = await response.text()
    assert text == "Called", (
        "The response is the one returned by " "defined http exception handler"
    )


async def test_application_exception_handler_decorator_by_custom_exception(app):
    expected_handler_response_text = "Called"

    class CustomException(Exception):
        pass

    @app.exception_handler(CustomException)
    async def exception_handler(
        self: FakeApplication, request: Request, exc: CustomException
    ) -> Response:
        nonlocal app
        assert self is app
        assert isinstance(exc, CustomException)
        return Response(200, content=TextContent("Called"))

    @app.router.get("/")
    async def home(request):
        raise CustomException()

    await app(get_example_scope("GET", "/"), MockReceive(), MockSend())

    assert app.response is not None
    response: Response = app.response

    assert response
    actual_response_text = await response.text()
    assert actual_response_text == expected_handler_response_text


async def test_application_exception_handler_decorator_by_http_status_code(app):
    expected_exception_status_code = 519
    expected_handler_response_text = "Called"

    @app.exception_handler(519)
    async def exception_handler(self, request: Request, exc: HTTPException) -> Response:
        assert isinstance(exc, HTTPException)
        assert exc.status == expected_exception_status_code
        return Response(200, content=TextContent("Called"))

    @app.router.get("/")
    async def home(request):
        raise HTTPException(519)

    await app(get_example_scope("GET", "/"), MockReceive(), MockSend())

    assert app.response
    response: Response = app.response

    assert response

    actual_response_text = await response.text()

    assert actual_response_text == expected_handler_response_text


@pytest.mark.parametrize(
    "parameter,expected_value",
    [("a", "a"), ("foo", "foo"), ("Hello%20World!!%3B%3B", "Hello World!!;;")],
)
async def test_handler_route_value_binding_single(parameter, expected_value, app):
    called = False

    @app.router.get("/:value")
    async def home(request, value):
        nonlocal called
        called = True
        assert value == expected_value

    await app(get_example_scope("GET", "/" + parameter), MockReceive(), MockSend())

    assert app.response.status == 204


@pytest.mark.parametrize(
    "parameter,expected_a,expected_b",
    [
        ("a/b", "a", "b"),
        ("foo/something", "foo", "something"),
        ("Hello%20World!!%3B%3B/another", "Hello World!!;;", "another"),
    ],
)
async def test_handler_route_value_binding_two(parameter, expected_a, expected_b, app):
    @app.router.get("/:a/:b")
    async def home(request, a, b):
        assert a == expected_a
        assert b == expected_b

    await app(get_example_scope("GET", "/" + parameter), MockReceive(), MockSend())
    assert app.response.status == 204


@pytest.mark.parametrize(
    "parameter,expected_value", [("12", 12), ("0", 0), ("16549", 16549)]
)
async def test_handler_route_value_binding_single_int(parameter, expected_value, app):
    called = False

    @app.router.get("/:value")
    async def home(request, value: int):
        nonlocal called
        called = True
        assert value == expected_value

    await app(get_example_scope("GET", "/" + parameter), MockReceive(), MockSend())

    assert app.response.status == 204


@pytest.mark.parametrize("parameter", ["xx", "x"])
async def test_handler_route_value_binding_single_int_invalid(parameter, app):
    called = False

    @app.router.get("/:value")
    async def home(request, value: int):
        nonlocal called
        called = True

    await app(get_example_scope("GET", "/" + parameter), MockReceive(), MockSend())

    assert called is False
    assert app.response.status == 400


@pytest.mark.parametrize("parameter", ["xx", "x"])
async def test_handler_route_value_binding_single_float_invalid(parameter, app):
    called = False

    @app.router.get("/:value")
    async def home(request, value: float):
        nonlocal called
        called = True

    await app(get_example_scope("GET", "/" + parameter), MockReceive(), MockSend())

    assert called is False
    assert app.response.status == 400


@pytest.mark.parametrize(
    "parameter,expected_value", [("12", 12.0), ("0", 0.0), ("16549.55", 16549.55)]
)
async def test_handler_route_value_binding_single_float(parameter, expected_value, app):
    called = False

    @app.router.get("/:value")
    async def home(request, value: float):
        nonlocal called
        called = True
        assert value == expected_value

    await app(get_example_scope("GET", "/" + parameter), MockReceive(), MockSend())

    assert app.response.status == 204


@pytest.mark.parametrize(
    "parameter,expected_a,expected_b,expected_c",
    [
        ("a/1/12.50", "a", 1, 12.50),
        ("foo/446/500", "foo", 446, 500.0),
        ("Hello%20World!!%3B%3B/60/88.05", "Hello World!!;;", 60, 88.05),
    ],
)
async def test_handler_route_value_binding_mixed_types(
    parameter, expected_a, expected_b, expected_c, app
):
    @app.router.get("/:a/:b/:c")
    async def home(request, a: str, b: int, c: float):
        assert a == expected_a
        assert b == expected_b
        assert c == expected_c

    await app(get_example_scope("GET", "/" + parameter), MockReceive(), MockSend())
    assert app.response.status == 204


@pytest.mark.parametrize(
    "query,expected_value",
    [
        (b"a=a", ["a"]),
        (b"a=foo", ["foo"]),
        (b"a=Hello%20World!!%3B%3B", ["Hello World!!;;"]),
    ],
)
async def test_handler_query_value_binding_single(query, expected_value, app):
    @app.router.get("/")
    async def home(request, a):
        assert a == expected_value

    await app(get_example_scope("GET", "/", query=query), MockReceive(), MockSend())

    assert app.response.status == 204


@pytest.mark.parametrize(
    "query,expected_value", [(b"a=10", 10), (b"b=20", None), (b"", None)]
)
async def test_handler_query_value_binding_optional_int(query, expected_value, app):
    @app.router.get("/")
    async def home(request, a: Optional[int]):
        assert a == expected_value

    await app(get_example_scope("GET", "/", query=query), MockReceive(), MockSend())
    assert app.response.status == 204


@pytest.mark.parametrize(
    "query,expected_value",
    [
        (b"a=10", 10.0),
        (b"a=12.6", 12.6),
        (b"a=12.6&c=4", 12.6),
        (b"b=20", None),
        (b"", None),
    ],
)
async def test_handler_query_value_binding_optional_float(query, expected_value, app):
    @app.router.get("/")
    async def home(request, a: Optional[float]):
        assert a == expected_value

    await app(get_example_scope("GET", "/", query=query), MockReceive(), MockSend())
    assert app.response.status == 204


@pytest.mark.parametrize(
    "query,expected_value",
    [
        (b"a=10", [10.0]),
        (b"a=12.6", [12.6]),
        (b"a=12.6&c=4", [12.6]),
        (b"a=12.6&a=4&a=6.6", [12.6, 4.0, 6.6]),
        (b"b=20", None),
        (b"", None),
    ],
)
async def test_handler_query_value_binding_optional_list(query, expected_value, app):
    @app.router.get("/")
    async def home(request, a: Optional[List[float]]):
        assert a == expected_value

    await app(get_example_scope("GET", "/", query=query), MockReceive(), MockSend())
    assert app.response.status == 204


@pytest.mark.parametrize(
    "query,expected_a,expected_b,expected_c",
    [
        (b"a=a&b=1&c=12.50", "a", 1, 12.50),
        (b"a=foo&b=446&c=500", "foo", 446, 500.0),
        (b"a=Hello%20World!!%3B%3B&b=60&c=88.05", "Hello World!!;;", 60, 88.05),
    ],
)
async def test_handler_query_value_binding_mixed_types(
    query, expected_a, expected_b, expected_c, app
):
    @app.router.get("/")
    async def home(request, a: str, b: int, c: float):
        assert a == expected_a
        assert b == expected_b
        assert c == expected_c

    await app(get_example_scope("GET", "/", query=query), MockReceive(), MockSend())
    assert app.response.status == 204


@pytest.mark.parametrize(
    "query,expected_value",
    [
        (
            b"a=Hello%20World!!%3B%3B&a=Hello&a=World",
            ["Hello World!!;;", "Hello", "World"],
        ),
    ],
)
async def test_handler_query_value_binding_list(query, expected_value, app):
    @app.router.get("/")
    async def home(request, a):
        assert a == expected_value

    await app(get_example_scope("GET", "/", query=query), MockReceive(), MockSend())
    assert app.response.status == 204


@pytest.mark.parametrize(
    "query,expected_value",
    [(b"a=2", [2]), (b"a=2&a=44", [2, 44]), (b"a=1&a=5&a=18", [1, 5, 18])],
)
async def test_handler_query_value_binding_list_of_ints(query, expected_value, app):
    @app.router.get("/")
    async def home(request, a: List[int]):
        assert a == expected_value

    await app(get_example_scope("GET", "/", query=query), MockReceive(), MockSend())
    assert app.response.status == 204


@pytest.mark.parametrize(
    "query,expected_value",
    [
        (b"a=2", [2.0]),
        (b"a=2.5&a=44.12", [2.5, 44.12]),
        (b"a=1&a=5.55556&a=18.656", [1, 5.55556, 18.656]),
    ],
)
async def test_handler_query_value_binding_list_of_floats(query, expected_value, app):
    @app.router.get("/")
    async def home(a: List[float]):
        assert a == expected_value

    await app(get_example_scope("GET", "/", query=query), MockReceive(), MockSend())
    assert app.response.status == 204


async def test_handler_normalize_sync_method(app):
    @app.router.get("/")
    def home(request):
        pass

    await app(get_example_scope("GET", "/"), MockReceive(), MockSend())
    assert app.response.status == 204


async def test_handler_normalize_sync_method_from_header(app):
    @app.router.get("/")
    def home(request, xx: FromHeader[str]):
        assert xx.value == "Hello World"

    await app(
        get_example_scope("GET", "/", [(b"XX", b"Hello World")]),
        MockReceive(),
        MockSend(),
    )
    assert app.response.status == 204


async def test_handler_normalize_sync_method_from_header_name_compatible(app):
    class AcceptLanguageHeader(FromHeader[str]):
        name = "accept-language"

    @inject()
    @app.router.get("/")
    def home(accept_language: AcceptLanguageHeader):
        assert accept_language.value == "en-US,en;q=0.9,it-IT;q=0.8,it;q=0.7"

    await app(
        get_example_scope("GET", "/", []),
        MockReceive(),
        MockSend(),
    )
    assert app.response.status == 204


async def test_handler_normalize_sync_method_from_query(app):
    @app.router.get("/")
    def home(xx: FromQuery[int]):
        assert xx.value == 20

    await app(get_example_scope("GET", "/", query=b"xx=20"), MockReceive(), MockSend())
    assert app.response.status == 204


async def test_handler_normalize_sync_method_from_query_implicit_default(app):
    @app.router.get("/")
    def get_products(
        page: int = 1,
        size: int = 30,
        search: str = "",
    ):
        return text(f"Page: {page}; size: {size}; search: {search}")

    await app(get_example_scope("GET", "/"), MockReceive(), MockSend())

    response = app.response
    content = await response.text()

    assert response.status == 200
    assert content == "Page: 1; size: 30; search: "

    await app(get_example_scope("GET", "/", query=b"page=2"), MockReceive(), MockSend())

    response = app.response
    content = await response.text()

    assert response.status == 200
    assert content == "Page: 2; size: 30; search: "

    await app(
        get_example_scope("GET", "/", query=b"page=2&size=50"),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    content = await response.text()

    assert response.status == 200
    assert content == "Page: 2; size: 50; search: "

    await app(
        get_example_scope("GET", "/", query=b"page=2&size=50&search=foo"),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    content = await response.text()

    assert response.status == 200
    assert content == "Page: 2; size: 50; search: foo"


async def test_handler_normalize_sync_method_from_query_default(app):
    @app.router.get("/")
    def get_products(
        page: FromQuery[int] = FromQuery(1),
        size: FromQuery[int] = FromQuery(30),
        search: FromQuery[str] = FromQuery(""),
    ):
        return text(f"Page: {page.value}; size: {size.value}; search: {search.value}")

    await app(get_example_scope("GET", "/"), MockReceive(), MockSend())

    response = app.response
    content = await response.text()

    assert response.status == 200
    assert content == "Page: 1; size: 30; search: "

    await app(get_example_scope("GET", "/", query=b"page=2"), MockReceive(), MockSend())

    response = app.response
    content = await response.text()

    assert response.status == 200
    assert content == "Page: 2; size: 30; search: "

    await app(
        get_example_scope("GET", "/", query=b"page=2&size=50"),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    content = await response.text()

    assert response.status == 200
    assert content == "Page: 2; size: 50; search: "

    await app(
        get_example_scope("GET", "/", query=b"page=2&size=50&search=foo"),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    content = await response.text()

    assert response.status == 200
    assert content == "Page: 2; size: 50; search: foo"


async def test_handler_normalize_list_sync_method_from_query_default(app):
    @app.router.get("/")
    def example(
        a: FromQuery[List[int]] = FromQuery([1, 2, 3]),
        b: FromQuery[List[int]] = FromQuery([4, 5, 6]),
        c: FromQuery[List[str]] = FromQuery(["x"]),
    ):
        return text(f"A: {a.value}; B: {b.value}; C: {c.value}")

    await app(get_example_scope("GET", "/"), MockReceive(), MockSend())

    response = app.response
    content = await response.text()

    assert response.status == 200
    assert content == f"A: {[1, 2, 3]}; B: {[4, 5, 6]}; C: {['x']}"

    await app(get_example_scope("GET", "/", query=b"a=1349"), MockReceive(), MockSend())

    response = app.response
    content = await response.text()

    assert response.status == 200
    assert content == f"A: {[1349]}; B: {[4, 5, 6]}; C: {['x']}"

    await app(
        get_example_scope("GET", "/", query=b"a=1349&c=Hello&a=55"),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    content = await response.text()

    assert response.status == 200
    assert content == f"A: {[1349, 55]}; B: {[4, 5, 6]}; C: {['Hello']}"

    await app(
        get_example_scope("GET", "/", query=b"a=1349&c=Hello&a=55&b=10"),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    content = await response.text()

    assert response.status == 200
    assert content == f"A: {[1349, 55]}; B: {[10]}; C: {['Hello']}"


async def test_handler_normalize_sync_method_without_arguments(app):
    @app.router.get("/")
    def home():
        return

    await app(get_example_scope("GET", "/"), MockReceive(), MockSend())
    assert app.response.status == 204


async def test_handler_normalize_sync_method_from_query_optional(app):
    @app.router.get("/")
    def home(xx: FromQuery[Optional[int]], yy: FromQuery[Optional[int]]):
        assert xx.value is None
        assert yy.value == 20

    await app(get_example_scope("GET", "/", query=b"yy=20"), MockReceive(), MockSend())
    assert app.response.status == 204


async def test_handler_normalize_optional_binder(app):
    @app.router.get("/1")
    def home1(xx: Optional[FromQuery[int]], yy: Optional[FromQuery[int]]):
        assert xx is None
        assert yy.value == 20

    @app.router.get("/2")
    def home2(xx: Optional[FromQuery[int]]):
        assert xx is not None
        assert xx.value == 10

    @app.router.get("/3")
    def home3(xx: Optional[FromQuery[Optional[int]]]):
        assert xx is not None
        assert xx.value == 10

    await app(get_example_scope("GET", "/1", query=b"yy=20"), MockReceive(), MockSend())
    assert app.response.status == 204

    await app(get_example_scope("GET", "/2", query=b"xx=10"), MockReceive(), MockSend())
    assert app.response.status == 204

    await app(get_example_scope("GET", "/3", query=b"xx=10"), MockReceive(), MockSend())
    assert app.response.status == 204


async def test_handler_normalize_sync_method_from_query_optional_list(app):
    @app.router.get("/")
    def home(xx: FromQuery[Optional[List[int]]], yy: FromQuery[Optional[List[int]]]):
        assert xx.value is None
        assert yy.value == [20, 55, 64]

    await app(
        get_example_scope("GET", "/", query=b"yy=20&yy=55&yy=64"),
        MockReceive(),
        MockSend(),
    )
    assert app.response.status == 204


@pytest.mark.parametrize(
    "query,expected_values",
    [
        [b"xx=hello&xx=world&xx=lorem&xx=ipsum", ["hello", "world", "lorem", "ipsum"]],
        [b"xx=1&xx=2", ["1", "2"]],
        [b"xx=1&yy=2", ["1"]],
    ],
)
async def test_handler_normalize_sync_method_from_query_default_type(
    query, expected_values, app
):
    @app.router.get("/")
    def home(request, xx: FromQuery):
        assert xx.value == expected_values

    await app(get_example_scope("GET", "/", query=query), MockReceive(), MockSend())
    assert app.response.status == 204


async def test_handler_normalize_method_without_input(app):
    @app.router.get("/")
    async def home():
        pass

    await app(get_example_scope("GET", "/"), MockReceive(), MockSend())
    assert app.response.status == 204


@pytest.mark.parametrize(
    "value,expected_value",
    [["dashboard", "dashboard"], ["hello_world", "hello_world"]],
)
async def test_handler_from_route(value, expected_value, app):
    @app.router.get("/:area")
    async def home(request, area: FromRoute[str]):
        assert area.value == expected_value

    await app(get_example_scope("GET", "/" + value), MockReceive(), MockSend())
    assert app.response.status == 204


@pytest.mark.parametrize(
    "value_one,value_two,expected_value_one,expected_value_two",
    [
        ["en", "dashboard", "en", "dashboard"],
        ["it", "hello_world", "it", "hello_world"],
    ],
)
async def test_handler_two_routes_parameters(
    value_one: str,
    value_two: str,
    expected_value_one: str,
    expected_value_two: str,
    app,
):
    @app.router.get("/:culture_code/:area")
    async def home(culture_code: FromRoute[str], area: FromRoute[str]):
        assert culture_code.value == expected_value_one
        assert area.value == expected_value_two

    await app(
        get_example_scope("GET", "/" + value_one + "/" + value_two),
        MockReceive(),
        MockSend(),
    )
    assert app.response.status == 204


@pytest.mark.parametrize(
    "value_one,value_two,expected_value_one,expected_value_two",
    [
        ["en", "dashboard", "en", "dashboard"],
        ["it", "hello_world", "it", "hello_world"],
    ],
)
async def test_handler_two_routes_parameters_implicit(
    value_one: str,
    value_two: str,
    expected_value_one: str,
    expected_value_two: str,
    app,
):
    @app.router.get("/:culture_code/:area")
    async def home(culture_code, area):
        assert culture_code == expected_value_one
        assert area == expected_value_two

    await app(
        get_example_scope("GET", "/" + value_one + "/" + value_two),
        MockReceive(),
        MockSend(),
    )
    assert app.response.status == 204


async def test_handler_from_json_parameter(app):
    @app.router.post("/")
    async def home(item: FromJSON[Item]):
        assert item is not None
        value = item.value
        assert value.a == "Hello"
        assert value.b == "World"
        assert value.c == 10

    await app(
        get_example_scope(
            "POST",
            "/",
            [(b"content-type", b"application/json"), (b"content-length", b"32")],
        ),
        MockReceive([b'{"a":"Hello","b":"World","c":10}']),
        MockSend(),
    )
    assert app.response.status == 204


async def test_handler_from_json_annotated_parameter(app):
    @app.router.post("/")
    async def home(item: Annotated[Item, FromJSON]):
        assert item is not None
        value = item
        assert value.a == "Hello"
        assert value.b == "World"
        assert value.c == 10

    await app(
        get_example_scope(
            "POST",
            "/",
            [(b"content-type", b"application/json"), (b"content-length", b"32")],
        ),
        MockReceive([b'{"a":"Hello","b":"World","c":10}']),
        MockSend(),
    )
    assert app.response.status == 204


async def test_handler_from_json_without_annotation(app):
    @app.router.post("/")
    async def home(item: FromJSON):
        assert item is not None
        assert isinstance(item.value, dict)
        value = item.value
        assert value == {"a": "Hello", "b": "World", "c": 10}

    await app(
        get_example_scope(
            "POST",
            "/",
            [(b"content-type", b"application/json"), (b"content-length", b"32")],
        ),
        MockReceive([b'{"a":"Hello","b":"World","c":10}']),
        MockSend(),
    )
    assert app.response.status == 204


async def test_handler_from_json_parameter_dict(app):
    @app.router.post("/")
    async def home(item: FromJSON[dict]):
        assert item is not None
        assert isinstance(item.value, dict)
        value = item.value
        assert value == {"a": "Hello", "b": "World", "c": 10}

    await app(
        get_example_scope(
            "POST",
            "/",
            [(b"content-type", b"application/json"), (b"content-length", b"32")],
        ),
        MockReceive([b'{"a":"Hello","b":"World","c":10}']),
        MockSend(),
    )
    assert app.response.status == 204


async def test_handler_from_json_parameter_dict_unannotated(app):
    @app.router.post("/")
    async def home(item: FromJSON[Dict]):
        assert item is not None
        assert isinstance(item.value, dict)
        value = item.value
        assert value == {"a": "Hello", "b": "World", "c": 10}

    await app(
        get_example_scope(
            "POST",
            "/",
            [(b"content-type", b"application/json"), (b"content-length", b"32")],
        ),
        MockReceive([b'{"a":"Hello","b":"World","c":10}']),
        MockSend(),
    )
    assert app.response.status == 204


async def test_handler_from_json_parameter_dict_annotated(app):
    @app.router.post("/")
    async def home(item: FromJSON[Dict[str, Any]]):
        assert item is not None
        assert isinstance(item.value, dict)
        value = item.value
        assert value == {"a": "Hello", "b": "World", "c": 10}

    await app(
        get_example_scope(
            "POST",
            "/",
            [(b"content-type", b"application/json"), (b"content-length", b"32")],
        ),
        MockReceive([b'{"a":"Hello","b":"World","c":10}']),
        MockSend(),
    )
    assert app.response.status == 204


@pytest.mark.parametrize(
    "value",
    [
        "Lorem ipsum dolor sit amet",
        "Hello, World",
        "Lorem ipsum dolor sit amet\n" * 200,
    ],
)
async def test_handler_from_text_parameter(value: str, app):
    @app.router.post("/")
    async def home(text: FromText):
        assert text.value == value

    await app(
        get_example_scope(
            "POST",
            "/",
            [
                (b"content-type", b"text/plain; charset=utf-8"),
                (b"content-length", str(len(value)).encode()),
            ],
        ),
        MockReceive([value.encode("utf8")]),
        MockSend(),
    )
    assert app.response.status == 204


@pytest.mark.parametrize(
    "value",
    [
        b"Lorem ipsum dolor sit amet",
        b"Hello, World",
        b"Lorem ipsum dolor sit amet\n" * 200,
    ],
)
async def test_handler_from_bytes_parameter(value: bytes, app):
    @app.router.post("/")
    async def home(text: FromBytes):
        assert text.value == value

    await app(
        get_example_scope(
            "POST",
            "/",
            [
                (b"content-type", b"text/plain; charset=utf-8"),
                (b"content-length", str(len(value)).encode()),
            ],
        ),
        MockReceive([value]),
        MockSend(),
    )
    assert app.response.status == 204


async def test_handler_from_files(app):
    @app.router.post("/")
    async def home(files: FromFiles):
        assert files is not None
        assert files.value is not None
        assert len(files.value) == 4
        file1 = files.value[0]
        file2 = files.value[1]
        file3 = files.value[2]
        file4 = files.value[3]

        assert file1.name == b"file1"
        assert file1.file_name == b"a.txt"
        assert file1.data == b"Content of a.txt.\r\n"

        assert file2.name == b"file2"
        assert file2.file_name == b"a.html"
        assert file2.data == b"<!DOCTYPE html><title>Content of a.html.</title>\r\n"

        assert file3.name == b"file2"
        assert file3.file_name == b"a.html"
        assert file3.data == b"<!DOCTYPE html><title>Content of a.html.</title>\r\n"

        assert file4.name == b"file3"
        assert file4.file_name == b"binary"
        assert file4.data == b"a\xcf\x89b"

    boundary = b"---------------------0000000000000000000000001"

    content = b"\r\n".join(
        [
            boundary,
            b'Content-Disposition: form-data; name="text1"',
            b"",
            b"text default",
            boundary,
            b'Content-Disposition: form-data; name="text2"',
            b"",
            "aωb".encode("utf8"),
            boundary,
            b'Content-Disposition: form-data; name="file1"; filename="a.txt"',
            b"Content-Type: text/plain",
            b"",
            b"Content of a.txt.",
            b"",
            boundary,
            b'Content-Disposition: form-data; name="file2"; filename="a.html"',
            b"Content-Type: text/html",
            b"",
            b"<!DOCTYPE html><title>Content of a.html.</title>",
            b"",
            boundary,
            b'Content-Disposition: form-data; name="file2"; filename="a.html"',
            b"Content-Type: text/html",
            b"",
            b"<!DOCTYPE html><title>Content of a.html.</title>",
            b"",
            boundary,
            b'Content-Disposition: form-data; name="file3"; filename="binary"',
            b"Content-Type: application/octet-stream",
            b"",
            "aωb".encode("utf8"),
            boundary + b"--",
        ]
    )

    await app(
        get_example_scope(
            "POST",
            "/",
            [
                (b"content-length", str(len(content)).encode()),
                (b"content-type", b"multipart/form-data; boundary=" + boundary),
            ],
        ),
        MockReceive([content]),
        MockSend(),
    )
    assert app.response.status == 204


async def _multipart_mix_scenario(app):

    content = read_multipart_mix_dat()

    await app(
        get_example_scope(
            "POST",
            "/",
            [
                (b"content-length", str(len(content)).encode()),
                (
                    b"content-type",
                    b"multipart/form-data; boundary=----WebKitFormBoundarygKWtIe0dRcq6RJaJ",
                ),
            ],
        ),
        MockReceive([content]),
        MockSend(),
    )
    assert app.response.status == 204


async def test_handler_from_files_and_form(app):
    """
    Tests proper handling of a separate FromFiles and FromForm binders, with class
    definition for the FromForm - not including the files.
    """

    @dataclass(init=False)
    class OtherInput:
        textfield: str
        checkbox1: bool
        checkbox2: bool

        def __init__(
            self,
            textfield: str,
            checkbox1: Optional[str],
            checkbox2: Optional[str] = None,
            **kwargs,
        ):
            self.textfield = textfield
            self.checkbox1 = checkbox1 == "on"
            self.checkbox2 = checkbox2 == "on"

    @app.router.post("/")
    async def home(files: FromFiles, other: FromForm[OtherInput]):
        assert files is not None
        assert files.value is not None
        assert len(files.value) == 1
        file1 = files.value[0]

        assert file1.name == b"files"
        assert file1.file_name == b"red-dot.png"

        assert other.value.checkbox1 is True
        assert other.value.checkbox2 is False
        assert other.value.textfield == "Hello World!"

    await _multipart_mix_scenario(app)


async def test_handler_from_form_handling_whole_multipart_with_class(app):
    """
    Tests proper handling of a single FromForm binder, handling multipart with files
    and other input.
    """

    @dataclass(init=False)
    class WholeInput:
        textfield: str
        checkbox1: bool
        checkbox2: bool
        files: list

        def __init__(
            self,
            textfield: str,
            checkbox1: Optional[str] = None,
            checkbox2: Optional[str] = None,
            files: Optional[List[FormPart]] = None,
            **kwargs,
        ):
            self.textfield = textfield
            self.checkbox1 = checkbox1 == "on"
            self.checkbox2 = checkbox2 == "on"
            self.files = files or []

    @app.router.post("/")
    async def home(data: FromForm[WholeInput]):
        files = data.value.files
        assert files is not None
        assert len(files) == 1
        file1 = files[0]

        assert file1.name == b"files"
        assert file1.file_name == b"red-dot.png"

        assert data.value.checkbox1 is True
        assert data.value.checkbox2 is False
        assert data.value.textfield == "Hello World!"

    await _multipart_mix_scenario(app)


async def test_handler_from_form_handling_whole_multipart_without_class(app):
    """
    Tests proper handling of a single FromForm binder, handling multipart with files
    and other input with dictionary.
    """

    @app.router.post("/")
    async def home(data: FromForm):
        files = data.value.get("files")
        assert files is not None
        assert len(files) == 1
        file1 = files[0]

        assert file1.name == b"files"
        assert file1.file_name == b"red-dot.png"

        assert data.value.get("checkbox1") == "on"
        assert data.value.get("checkbox2") is None
        assert data.value.get("textfield") == "Hello World!"

    await _multipart_mix_scenario(app)


async def test_handler_from_files_and_form_dict(app):
    """
    Tests proper handling of a separate FromFiles and FromForm binders, without class
    definition for the FromForm - not including the files.
    """

    @app.router.post("/")
    async def home(files: FromFiles, other: FromForm):
        assert files is not None
        assert files.value is not None
        assert len(files.value) == 1
        file1 = files.value[0]

        assert file1.name == b"files"
        assert file1.file_name == b"red-dot.png"

        assert other.value.get("checkbox1") == "on"
        assert other.value.get("checkbox2") is None
        assert other.value.get("textfield") == "Hello World!"

    await _multipart_mix_scenario(app)


async def test_handler_from_files_handles_empty_body(app):
    @app.router.post("/")
    async def home(files: FromFiles):
        assert files.value == []

    await app(
        get_example_scope(
            "POST",
            "/",
            [],
        ),
        MockReceive([]),
        MockSend(),
    )
    assert app.response.status == 204


async def test_handler_from_json_parameter_missing_property(app):
    @app.router.post("/")
    async def home(item: FromJSON[Item]): ...

    # Note: the following example missing one of the properties
    # required by the constructor
    await app(
        get_example_scope(
            "POST",
            "/",
            [(b"content-type", b"application/json"), (b"content-length", b"25")],
        ),
        MockReceive([b'{"a":"Hello","b":"World"}']),
        MockSend(),
    )
    assert app.response.status == 400
    assert (
        b"Bad Request: invalid parameter in request payload, caused by type Item "
        + b"or one of its subproperties."
        in app.response.content.body
    )


async def test_handler_json_response_implicit(app):
    @app.router.get("/")
    async def get_item() -> Item2:
        return Item2("Hello", "World", "!")

    # Note: the following example missing one of the properties
    # required by the constructor
    await app(
        get_example_scope(
            "GET",
            "/",
            [],
        ),
        MockReceive(),
        MockSend(),
    )
    assert app.response.status == 200
    data = await app.response.json()
    assert data == Item2("Hello", "World", "!").__dict__


async def test_handler_json_response_implicit_no_annotation(app):
    @app.router.get("/")
    async def get_item():
        return Item2("Hello", "World", "!")

    # Note: the following example missing one of the properties
    # required by the constructor
    await app(
        get_example_scope(
            "GET",
            "/",
            [],
        ),
        MockReceive(),
        MockSend(),
    )
    assert app.response.status == 200
    data = await app.response.json()
    assert data == Item2("Hello", "World", "!").__dict__


async def test_handler_text_response_implicit(app):
    @app.router.get("/")
    async def get_lorem():
        return "Lorem ipsum"

    # Note: the following example missing one of the properties
    # required by the constructor
    await app(
        get_example_scope(
            "GET",
            "/",
            [],
        ),
        MockReceive(),
        MockSend(),
    )
    assert app.response.status == 200
    data = await app.response.text()
    assert data == "Lorem ipsum"


async def test_handler_from_json_parameter_missing_property_complex_type(app):
    @inject()
    @app.router.post("/")
    async def home(item: FromJSON[Foo]): ...

    # Note: the following example missing one of the properties
    # required by the constructor
    await app(
        get_example_scope(
            "POST",
            "/",
            [(b"content-type", b"application/json"), (b"content-length", b"34")],
        ),
        MockReceive([b'{"item":{"a":"Hello","b":"World"}}']),
        MockSend(),
    )
    assert app.response.status == 400
    assert (
        b"Bad Request: invalid parameter in request payload, caused by type Foo "
        + b"or one of its subproperties."
        in app.response.content.body
    )


async def test_handler_from_json_parameter_missing_property_array(app):
    @app.router.post("/")
    async def home(item: FromJSON[List[Item]]): ...

    # Note: the following example missing one of the properties
    # required by the constructor
    await app(
        get_example_scope(
            "POST",
            "/",
            [(b"content-type", b"application/json"), (b"content-length", b"25")],
        ),
        MockReceive([b'[{"a":"Hello","b":"World"}]']),
        MockSend(),
    )
    assert app.response.status == 400
    assert (
        b"Bad Request: invalid parameter in request payload, caused by type Item"
        in app.response.content.body
    )


async def test_handler_from_json_parameter_handles_request_without_body(app):
    @app.router.post("/")
    async def home(item: FromJSON[Item]):
        return Response(200)

    await app(
        get_example_scope(
            "POST",
            "/",
            [],
        ),
        MockReceive([]),
        MockSend(),
    )
    assert app.response.status == 400
    assert app.response.content.body == b"Bad Request: Expected request content"


async def test_handler_from_json_list_of_objects(app):
    @app.router.post("/")
    async def home(item: FromJSON[List[Item]]):
        assert item is not None
        value = item.value

        item_one = value[0]
        item_two = value[1]
        assert item_one.a == "Hello"
        assert item_one.b == "World"
        assert item_one.c == 10

        assert item_two.a == "Lorem"
        assert item_two.b == "ipsum"
        assert item_two.c == 55

    await app(
        get_example_scope(
            "POST",
            "/",
            [[b"content-type", b"application/json"], [b"content-length", b"32"]],
        ),
        MockReceive(
            [
                b'[{"a":"Hello","b":"World","c":10},'
                + b'{"a":"Lorem","b":"ipsum","c":55}]'
            ]
        ),
        MockSend(),
    )
    assert app.response.status == 204


@pytest.mark.parametrize(
    "expected_type,request_body,expected_result",
    [
        [
            List,
            b'["one","two","three"]',
            ["one", "two", "three"],
        ],
        [
            List[bytes],
            b'["bG9yZW0gaXBzdW0=","aGVsbG8gd29ybGQ=","VGhyZWU="]',
            ["lorem ipsum", "hello world", "Three"],
        ],
        [
            List[str],
            b'["one","two","three"]',
            ["one", "two", "three"],
        ],
        [
            List[int],
            b"[20, 10, 0, 200, 12, 64]",
            [20, 10, 0, 200, 12, 64],
        ],
        [
            List[float],
            b"[20.4, 10.23, 0.12, 200.00, 12.12, 64.01]",
            [20.4, 10.23, 0.12, 200.00, 12.12, 64.01],
        ],
        [
            List[bool],
            b"[true, false, true, true, 1, 0]",
            [True, False, True, True, True, False],
        ],
        [
            List[datetime],
            b'["2020-10-24", "2020-10-24T18:46:19.313346", "2019-05-30"]',
            [
                datetime(2020, 10, 24),
                datetime(2020, 10, 24, 18, 46, 19, 313346),
                datetime(2019, 5, 30),
            ],
        ],
        [
            List[date],
            b'["2020-10-24", "2020-10-24", "2019-05-30"]',
            [date(2020, 10, 24), date(2020, 10, 24), date(2019, 5, 30)],
        ],
        [
            List[UUID],
            b'["d1e7745f-2a20-4181-8249-b7fef73592dd",'
            + b'"0bf95cca-3299-4cc0-93d1-ec8e041f5d3e",'
            + b'"d2d52dde-b174-47e0-8a8e-a07d6a559a3a"]',
            [
                UUID("d1e7745f-2a20-4181-8249-b7fef73592dd"),
                UUID("0bf95cca-3299-4cc0-93d1-ec8e041f5d3e"),
                UUID("d2d52dde-b174-47e0-8a8e-a07d6a559a3a"),
            ],
        ],
    ],
)
async def test_handler_from_json_list_of_primitives(
    expected_type, request_body, expected_result, app
):
    @inject()
    @app.router.post("/")
    async def home(item: FromJSON[expected_type]):
        assert item is not None
        value = item.value
        assert value == expected_result

    await app(
        get_example_scope(
            "POST",
            "/",
            [
                [b"content-type", b"application/json"],
                [b"content-length", str(len(request_body)).encode()],
            ],
        ),
        MockReceive([request_body]),
        MockSend(),
    )
    assert app.response.status == 204


async def test_handler_from_json_dataclass(app):
    @dataclass
    class Foo:
        foo: str
        ufo: bool

    @inject()
    @app.router.post("/")
    async def home(item: FromJSON[Foo]):
        assert item is not None
        value = item.value
        assert value.foo == "Hello"
        assert value.ufo is True

    await app(
        get_example_scope(
            "POST",
            "/",
            [[b"content-type", b"application/json"], [b"content-length", b"32"]],
        ),
        MockReceive([b'{"foo":"Hello","ufo":true}']),
        MockSend(),
    )
    assert app.response.status == 204


async def test_handler_from_json_parameter_default(app):
    @app.router.post("/")
    async def home(item: FromJSON[Item] = FromJSON(Item("One", "Two", 3))):
        assert item is not None
        value = item.value
        assert value.a == "One"
        assert value.b == "Two"
        assert value.c == 3

    await app(
        get_example_scope(
            "POST",
            "/",
            [],
        ),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 204


async def test_handler_from_json_parameter_default_override(app):
    @app.router.post("/")
    async def home(item: FromJSON[Item] = FromJSON(Item("One", "Two", 3))):
        assert item is not None
        value = item.value
        assert value.a == "Hello"
        assert value.b == "World"
        assert value.c == 10

    await app(
        get_example_scope(
            "POST",
            "/",
            [[b"content-type", b"application/json"], [b"content-length", b"32"]],
        ),
        MockReceive([b'{"a":"Hello","b":"World","c":10}']),
        MockSend(),
    )
    assert app.response.status == 204


async def test_handler_from_json_parameter_implicit(app):
    @app.router.post("/")
    async def home(item: Item):
        assert item is not None
        assert item.a == "Hello"
        assert item.b == "World"
        assert item.c == 10

    await app(
        get_example_scope(
            "POST",
            "/",
            [[b"content-type", b"application/json"], [b"content-length", b"32"]],
        ),
        MockReceive([b'{"a":"Hello","b":"World","c":10}']),
        MockSend(),
    )
    assert app.response.status == 204


async def test_handler_from_json_parameter_implicit_default(app):
    @app.router.post("/")
    async def home(item: Item = Item(1, 2, 3)):
        assert item is not None
        assert item.a == 1
        assert item.b == 2
        assert item.c == 3

    await app(
        get_example_scope(
            "POST",
            "/",
            [],
        ),
        MockReceive(),
        MockSend(),
    )
    assert app.response.status == 204


async def test_handler_from_wrong_method_json_parameter_gets_null_if_optional(app):
    @app.router.get("/")  # <--- NB: wrong http method for posting payloads
    async def home(item: FromJSON[Optional[Item]]):
        assert item.value is None

    await app(
        get_example_scope(
            "GET",
            "/",
            [[b"content-type", b"application/json"], [b"content-length", b"32"]],
        ),
        MockReceive([b'{"a":"Hello","b":"World","c":10}']),
        MockSend(),
    )

    assert app.response.status == 204


async def test_handler_from_wrong_method_json_parameter_gets_bad_request(app):
    @app.router.get("/")  # <--- NB: wrong http method for posting payloads
    async def home(request, item: FromJSON[Item]):
        assert item.value is None

    await app(
        get_example_scope(
            "GET",
            "/",
            [[b"content-type", b"application/json"], [b"content-length", b"32"]],
        ),
        MockReceive([b'{"a":"Hello","b":"World","c":10}']),
        MockSend(),
    )

    # 400 because the annotation FromJSON[Item] makes the item REQUIRED;
    assert app.response.status == 400
    content = await app.response.text()
    assert content == "Bad Request: Expected request content"


@pytest.mark.parametrize(
    "parameter_type,parameter,expected_value",
    [
        [str, "Hello", "Hello"],
        [int, "1349", 1349],
        [float, "13.2", 13.2],
        [bool, "True", True],
        [bool, "1", True],
        [Optional[bool], "1", True],
        [Optional[bool], "", None],
        [bool, "False", False],
        [Optional[bool], "False", False],
        [date, "2020-5-30", date(2020, 5, 30)],
        [date, "2020-1-1", date(2020, 1, 1)],
        [Optional[date], "", None],
        [
            datetime,
            "2020-10-24T18:46:19.313346",
            datetime(2020, 10, 24, 18, 46, 19, 313346),
        ],
        [bool, "0", False],
        [
            UUID,
            "54b2587a-0afc-40ec-a03d-13223d4bb04d",
            UUID("54b2587a-0afc-40ec-a03d-13223d4bb04d"),
        ],
    ],
)
async def test_valid_query_parameter_parse(
    parameter_type, parameter, expected_value, app
):
    @inject()
    @app.router.get("/")
    async def home(foo: FromQuery[parameter_type]):
        assert foo.value == expected_value
        return status_code(200)

    await app(
        get_example_scope("GET", "/", [], query=f"foo={parameter}".encode()),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 200


@pytest.mark.parametrize(
    "parameter_type,parameter,expected_value",
    [
        [str, "Hello", "Hello"],
        [int, "1349", 1349],
        [float, "13.2", 13.2],
        [bool, "True", True],
        [bool, "1", True],
        [Optional[bool], "1", True],
        [Optional[bool], "", None],
        [bool, "False", False],
        [Optional[bool], "False", False],
        [date, "2020-5-30", date(2020, 5, 30)],
        [date, "2020-1-1", date(2020, 1, 1)],
        [Optional[date], "", None],
        [
            datetime,
            "2020-10-24T18:46:19.313346",
            datetime(2020, 10, 24, 18, 46, 19, 313346),
        ],
        [bool, "0", False],
        [
            UUID,
            "54b2587a-0afc-40ec-a03d-13223d4bb04d",
            UUID("54b2587a-0afc-40ec-a03d-13223d4bb04d"),
        ],
    ],
)
async def test_valid_cookie_parameter_parse(
    parameter_type, parameter, expected_value, app
):
    @inject()
    @app.router.get("/")
    async def home(foo: FromCookie[parameter_type]):
        assert foo.value == expected_value
        return status_code(200)

    await app(
        get_example_scope("GET", "/", [(b"cookie", f"foo={parameter}".encode())]),
        MockReceive(),
        MockSend(),
    )
    assert app.response.status == 200


@pytest.mark.parametrize(
    "parameter_type,parameters,expected_value",
    [
        [List, ["Hello", "World"], ["Hello", "World"]],
        [List[str], ["Hello", "World"], ["Hello", "World"]],
        [List[int], ["1349"], [1349]],
        [List[int], ["1", "2", "3"], [1, 2, 3]],
        [List[float], ["1.12", "2.30", "3.55"], [1.12, 2.30, 3.55]],
        [List[bool], ["1", "0", "0", "1"], [True, False, False, True]],
        [
            List[date],
            ["2020-5-30", "2019-5-30", "2018-1-1"],
            [date(2020, 5, 30), date(2019, 5, 30), date(2018, 1, 1)],
        ],
        [
            List[datetime],
            ["2020-10-24T18:46:19.313346", "2019-10-24T18:46:19.313346"],
            [
                datetime(2020, 10, 24, 18, 46, 19, 313346),
                datetime(2019, 10, 24, 18, 46, 19, 313346),
            ],
        ],
    ],
)
async def test_valid_query_parameter_list_parse(
    parameter_type, parameters, expected_value, app
):
    @inject()
    @app.router.get("/")
    async def home(foo: FromQuery[parameter_type]):
        assert foo.value == expected_value
        return status_code(200)

    query = "&".join(f"foo={parameter}" for parameter in parameters)

    await app(
        get_example_scope("GET", "/", [], query=query.encode()),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 200


@pytest.mark.parametrize(
    "parameter_type,parameter",
    [
        [int, "nope"],
        [float, "nope"],
        [date, "nope"],
        [Optional[date], "nope"],
        [datetime, "nope"],
        [UUID, "nope"],
    ],
)
async def test_invalid_query_parameter_400(parameter_type, parameter, app):
    @inject()
    @app.router.get("/")
    async def home(foo: FromQuery[parameter_type]):
        return status_code(200)

    await app(
        get_example_scope("GET", "/", [], query=f"foo={parameter}".encode()),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 400
    content = await app.response.text()
    assert "Bad Request: Invalid value ['nope'] for parameter `foo`;" in content


@pytest.mark.parametrize(
    "parameter_type,parameter,expected_value",
    [
        [str, "Hello", "Hello"],
        [int, "1349", 1349],
        [float, "13.2", 13.2],
        [bool, "True", True],
        [bool, "1", True],
        [bool, "False", False],
        [date, "2020-5-30", date(2020, 5, 30)],
        [
            datetime,
            "2020-10-24T18:46:19.313346",
            datetime(2020, 10, 24, 18, 46, 19, 313346),
        ],
        [bool, "0", False],
        [
            UUID,
            "54b2587a-0afc-40ec-a03d-13223d4bb04d",
            UUID("54b2587a-0afc-40ec-a03d-13223d4bb04d"),
        ],
    ],
)
async def test_valid_route_parameter_parse(
    parameter_type, parameter, expected_value, app
):
    @inject()
    @app.router.get("/:foo")
    async def home(foo: FromRoute[parameter_type]):
        assert foo.value == expected_value
        return status_code(200)

    await app(
        get_example_scope("GET", "/" + parameter, []),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 200


@pytest.mark.parametrize(
    "parameter_type,parameter,expected_value",
    [
        [str, "Hello", "Hello"],
        [int, "1349", 1349],
        [float, "13.2", 13.2],
        [bool, "True", True],
        [bool, "1", True],
        [bool, "False", False],
        [date, "2020-5-30", date(2020, 5, 30)],
        [
            datetime,
            "2020-10-24T18:46:19.313346",
            datetime(2020, 10, 24, 18, 46, 19, 313346),
        ],
        [bool, "0", False],
        [
            UUID,
            "54b2587a-0afc-40ec-a03d-13223d4bb04d",
            UUID("54b2587a-0afc-40ec-a03d-13223d4bb04d"),
        ],
    ],
)
async def test_valid_header_parameter_parse(
    parameter_type, parameter, expected_value, app
):
    T = TypeVar("T")

    class XFooHeader(FromHeader[T]):
        name = "X-Foo"

    @inject()
    @app.router.get("/")
    async def home(x_foo: XFooHeader[parameter_type]):
        assert x_foo.value == expected_value
        return status_code(200)

    await app(
        get_example_scope("GET", "/", [(b"X-Foo", parameter.encode())]),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 200


@pytest.mark.parametrize(
    "parameter_type,parameter_one,parameter_two",
    [
        [str, "Hello", "World"],
        [int, "1349", "164"],
        [float, "1.2", "13.3"],
        [bytes, b"example", b"example"],
        [bool, True, False],
        [
            UUID,
            "54b2587a-0afc-40ec-a03d-13223d4bb04d",
            "8ffd8e17-1a38-462f-ba71-3d92e52edf1f",
        ],
    ],
)
async def test_valid_query_parameter(parameter_type, parameter_one, parameter_two, app):
    @inject()
    @app.router.get("/")
    async def home(foo: FromQuery[parameter_type]):
        assert isinstance(foo.value, parameter_type)
        if isinstance(foo.value, bytes):
            return text(f"Got: {foo.value.decode('utf8')}")
        return text(f"Got: {foo.value}")

    # f strings handle bytes creating string representations:
    if isinstance(parameter_one, bytes):
        parameter_one = parameter_one.decode("utf8")
    if isinstance(parameter_two, bytes):
        parameter_two = parameter_two.decode("utf8")

    await app(
        get_example_scope("GET", "/", [], query=f"foo={parameter_one}".encode()),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 200
    content = await app.response.text()
    assert content == f"Got: {parameter_one}"

    await app(
        get_example_scope(
            "GET", "/", [], query=f"foo={parameter_one}&foo={parameter_two}".encode()
        ),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 200
    content = await app.response.text()
    assert content == f"Got: {parameter_one}"


@pytest.mark.parametrize(
    "parameter_type,parameter_one,parameter_two",
    [
        [str, "Hello", "World"],
        [int, "1349", "164"],
        [float, "1.2", "13.3"],
        [bool, True, False],
        [
            UUID,
            "54b2587a-0afc-40ec-a03d-13223d4bb04d",
            "8ffd8e17-1a38-462f-ba71-3d92e52edf1f",
        ],
    ],
)
async def test_valid_query_parameter_implicit(
    parameter_type, parameter_one, parameter_two, app
):
    @inject()
    @app.router.get("/")
    async def home(request, foo: parameter_type):
        assert isinstance(foo, parameter_type)
        return text(f"Got: {foo}")

    await app(
        get_example_scope("GET", "/", [], query=f"foo={parameter_one}".encode()),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 200
    content = await app.response.text()
    assert content == f"Got: {parameter_one}"

    await app(
        get_example_scope(
            "GET", "/", [], query=f"foo={parameter_one}&foo={parameter_two}".encode()
        ),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 200
    content = await app.response.text()
    assert content == f"Got: {parameter_one}"


async def test_valid_query_parameter_list_of_int(app):
    expected_values_1 = [1349]
    expected_values_2 = [1349, 164]

    @app.router.get("/")
    async def home(foo: FromQuery[List[int]]):
        return text(f"Got: {foo.value}")

    await app(
        get_example_scope("GET", "/", [], query=b"foo=1349"),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 200
    content = await app.response.text()
    assert content == f"Got: {expected_values_1}"

    await app(
        get_example_scope("GET", "/", [], query=b"foo=1349&foo=164"),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 200
    content = await app.response.text()
    assert content == f"Got: {expected_values_2}"


async def test_invalid_query_parameter_int(app):
    @app.router.get("/")
    async def home(request, foo: FromQuery[int]): ...

    await app(
        get_example_scope(
            "GET",
            "/",
            [],
        ),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 400
    content = await app.response.text()
    assert content == "Bad Request: Missing query parameter `foo`"

    await app(
        get_example_scope("GET", "/", [], query=b"foo=xxx"),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 400
    content = await app.response.text()
    assert (
        content == "Bad Request: Invalid value ['xxx'] for parameter `foo`; "
        "expected a valid int."
    )

    await app(
        get_example_scope("GET", "/", [], query=b"foo=xxx&foo=yyy"),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 400
    content = await app.response.text()
    assert (
        content == "Bad Request: Invalid value ['xxx', 'yyy'] for parameter `foo`; "
        "expected a valid int."
    )


async def test_invalid_query_parameter_float(app):
    @app.router.get("/")
    async def home(request, foo: FromQuery[float]): ...

    await app(
        get_example_scope(
            "GET",
            "/",
            [],
        ),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 400
    content = await app.response.text()
    assert content == "Bad Request: Missing query parameter `foo`"

    await app(
        get_example_scope("GET", "/", [], query=b"foo=xxx"),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 400
    content = await app.response.text()
    assert (
        content == "Bad Request: Invalid value ['xxx'] for parameter `foo`; "
        "expected a valid float."
    )

    await app(
        get_example_scope("GET", "/", [], query=b"foo=xxx&foo=yyy"),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 400
    content = await app.response.text()
    assert (
        content == "Bad Request: Invalid value ['xxx', 'yyy'] for parameter `foo`; "
        "expected a valid float."
    )


async def test_invalid_query_parameter_bool(app):
    @app.router.get("/")
    async def home(request, foo: FromQuery[bool]): ...

    await app(
        get_example_scope(
            "GET",
            "/",
            [],
        ),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 400
    content = await app.response.text()
    assert content == "Bad Request: Missing query parameter `foo`"

    await app(
        get_example_scope("GET", "/", [], query=b"foo=xxx"),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 400
    content = await app.response.text()
    assert (
        content == "Bad Request: Invalid value ['xxx'] for parameter `foo`; "
        "expected a valid bool."
    )

    await app(
        get_example_scope("GET", "/", [], query=b"foo=xxx&foo=yyy"),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 400
    content = await app.response.text()
    assert (
        content == "Bad Request: Invalid value ['xxx', 'yyy'] for parameter `foo`; "
        "expected a valid bool."
    )


async def test_invalid_query_parameter_uuid(app):
    @app.router.get("/")
    async def home(request, foo: FromQuery[UUID]):
        return text(f"Got: {foo.value}")

    value_1 = "99cb720c-26f2-43dd-89ea-"

    await app(
        get_example_scope("GET", "/", [], query=b"foo=" + str(value_1).encode()),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 400
    content = await app.response.text()
    assert content == (
        f"Bad Request: Invalid value ['{value_1}'] for "
        "parameter `foo`; expected a valid UUID."
    )


async def test_valid_route_parameter_uuid(app):
    @app.router.get("/:foo")
    async def home(request, foo: FromRoute[UUID]):
        return text(f"Got: {foo.value}")

    value_1 = uuid4()

    await app(
        get_example_scope("GET", "/" + str(value_1), []),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 200
    content = await app.response.text()
    assert content == f"Got: {value_1}"


async def test_valid_route_parameter_uuid_2(app):
    @app.router.get("/:a_id/:b_id")
    async def home(request, a_id: FromRoute[UUID], b_id: FromRoute[UUID]):
        return text(f"Got: {a_id.value} and {b_id.value}")

    value_1 = uuid4()
    value_2 = uuid4()

    await app(
        get_example_scope("GET", f"/{value_1}/{value_2}", []),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 200
    content = await app.response.text()
    assert content == f"Got: {value_1} and {value_2}"


async def test_valid_header_parameter_uuid_list(app):
    @app.router.get("/")
    async def home(request, x_foo: FromHeader[List[UUID]]):
        return text(f"Got: {x_foo.value}")

    value_1 = uuid4()
    value_2 = uuid4()

    await app(
        get_example_scope(
            "GET",
            "/",
            [(b"x_foo", str(value_1).encode()), (b"x_foo", str(value_2).encode())],
        ),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 200
    content = await app.response.text()
    assert content == f"Got: {[value_1, value_2]}"


async def test_invalid_route_parameter_uuid(app):
    @app.router.get("/:document_id")
    async def home(request, document_id: FromRoute[UUID]):
        return text(f"Got: {document_id.value}")

    value_1 = "abc"

    await app(
        get_example_scope("GET", "/" + str(value_1), []),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 400
    content = await app.response.text()
    assert content == (
        f"Bad Request: Invalid value ['{value_1}'] for "
        "parameter `document_id`; expected a valid UUID."
    )


async def test_valid_route_parameter_uuid_implicit(app):
    @app.router.get("/:foo")
    async def home(request, foo: UUID):
        return text(f"Got: {foo}")

    value_1 = uuid4()

    await app(
        get_example_scope("GET", "/" + str(value_1), []),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 200
    content = await app.response.text()
    assert content == f"Got: {value_1}"


async def test_route_resolution_order(app):
    @app.router.get("/:id")
    async def example_a():
        return text("A")

    @app.router.get("/exact")
    async def example_b():
        return text("B")

    @app.router.get("/:foo/:ufo")
    async def example_c():
        return text("C")

    @app.router.get("/:foo/exact")
    async def example_d():
        return text("D")

    await app(
        get_example_scope("GET", "/exact", []),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 200
    content = await app.response.text()
    assert content == "B"

    await app(
        get_example_scope("GET", "/aaa/exact", []),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 200
    content = await app.response.text()
    assert content == "D"

    await app(
        get_example_scope("GET", "/aaa/exact/", []),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 200
    content = await app.response.text()
    assert content == "D"

    await app(
        get_example_scope("GET", "/aaa/bbb", []),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 200
    content = await app.response.text()
    assert content == "C"


async def test_client_server_info_bindings(app):
    @app.router.get("/")
    async def home(client: ClientInfo, server: ServerInfo):
        return text(f"Client: {client.value}; Server: {server.value}")

    scope = get_example_scope("GET", "/", [])
    await app(
        scope,
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 200
    content = await app.response.text()
    assert content == (
        f"Client: {tuple(scope.get('client', ''))}; "
        f"Server: {tuple(scope.get('server', ''))}"
    )


async def test_service_bindings():
    container = Container()

    @inject()
    class B:
        def __init__(self) -> None:
            self.foo = "foo"

    @inject()
    class A:
        def __init__(self, b: B) -> None:
            self.dep = b

    container.add_scoped(A)
    container.add_scoped(B)

    app = FakeApplication(services=container)

    @inject()
    @app.router.get("/explicit")
    async def explicit(a: FromServices[A]):
        assert isinstance(a.value, A)
        assert isinstance(a.value.dep, B)
        assert a.value.dep.foo == "foo"
        return text("OK")

    @inject()
    @app.router.get("/implicit")
    async def implicit(a: A):
        assert isinstance(a, A)
        assert isinstance(a.dep, B)
        assert a.dep.foo == "foo"
        return text("OK")

    for path in {"/explicit", "/implicit"}:
        scope = get_example_scope("GET", path, [])
        await app(
            scope,
            MockReceive(),
            MockSend(),
        )

        assert app.response is not None
        content = await app.response.text()
        assert content == "OK"
        assert app.response.status == 200


async def test_di_middleware_enables_scoped_services_in_handle_signature():
    container = Container()

    class OperationContext:
        def __init__(self) -> None:
            self.trace_id = uuid4()

    container.add_scoped(OperationContext)

    first_operation: Optional[OperationContext] = None

    app = FakeApplication(services=container)
    app.middlewares.append(di_scope_middleware)

    @inject()
    @app.router.get("/")
    async def home(a: OperationContext, b: OperationContext):
        assert a is b
        nonlocal first_operation
        if first_operation is None:
            first_operation = a
        else:
            assert first_operation is not a

        return text("OK")

    for _ in range(2):
        scope = get_example_scope("GET", "/", [])
        await app(
            scope,
            MockReceive(),
            MockSend(),
        )
        assert app.response is not None
        content = await app.response.text()
        assert content == "OK"
        assert app.response.status == 200


async def test_without_di_middleware_no_support_for_scoped_svcs_in_handler_signature():
    container = Container()

    class OperationContext:
        def __init__(self) -> None:
            self.trace_id = uuid4()

    container.add_scoped(OperationContext)
    app = FakeApplication(services=container)

    @inject()
    @app.router.get("/")
    async def home(a: OperationContext, b: OperationContext):
        assert a is not b
        return text("OK")

    for _ in range(2):
        scope = get_example_scope("GET", "/", [])
        await app(
            scope,
            MockReceive(),
            MockSend(),
        )

        content = await app.response.text()
        assert content == "OK"
        assert app.response.status == 200


async def test_service_bindings_default():
    # Extremely unlikely, but still supported if the user defines a default service
    container = Container()

    class B:
        def __init__(self) -> None:
            self.foo = "foo"

    @inject()
    class A:
        def __init__(self, b: B) -> None:
            self.dep = b

    app = FakeApplication(services=container)

    @inject()
    @app.router.get("/explicit")
    async def explicit(a: FromServices[A] = FromServices(A(B()))):
        assert isinstance(a.value, A)
        assert isinstance(a.value.dep, B)
        assert a.value.dep.foo == "foo"
        return text("OK")

    @inject()
    @app.router.get("/implicit")
    async def implicit(a: A = A(B())):
        assert isinstance(a, A)
        assert isinstance(a.dep, B)
        assert a.dep.foo == "foo"
        return text("OK")

    for path in {"/explicit", "/implicit"}:
        scope = get_example_scope("GET", path, [])
        await app(
            scope,
            MockReceive(),
            MockSend(),
        )

        content = await app.response.text()
        assert content == "OK"
        assert app.response.status == 200


async def test_service_bindings_default_override():
    # Extremely unlikely, but still supported if the user defines a default service
    container = Container()

    @inject()
    class B:
        def __init__(self, value: str) -> None:
            self.foo = value

    @inject()
    class A:
        def __init__(self, b: B) -> None:
            self.dep = b

    # Note: the registered service is used instead of the default function argument
    container.add_instance(A(B("ufo")))
    container.add_instance(B("oof"))

    app = FakeApplication(services=container)

    @inject()
    @app.router.get("/explicit")
    async def explicit(a: FromServices[A] = FromServices(A(B("foo")))):
        assert isinstance(a.value, A)
        assert isinstance(a.value.dep, B)
        assert a.value.dep.foo == "ufo"
        return text("OK")

    @inject()
    @app.router.get("/implicit")
    async def implicit(a: A = A(B("foo"))):
        assert isinstance(a, A)
        assert isinstance(a.dep, B)
        assert a.dep.foo == "ufo"
        return text("OK")

    for path in {"/explicit", "/implicit"}:
        scope = get_example_scope("GET", path, [])
        await app(
            scope,
            MockReceive(),
            MockSend(),
        )

        content = await app.response.text()
        assert content == "OK"
        assert app.response.status == 200


async def test_user_binding(app):
    class MockAuthHandler(AuthenticationHandler):
        async def authenticate(self, context):
            header_value = context.get_first_header(b"Authorization")
            if header_value:
                data = json.loads(urlsafe_b64decode(header_value).decode("utf8"))
                context.user = Identity(data, "TEST")
            else:
                context.user = None
            return context.user

    app.use_authentication().add(MockAuthHandler())

    @app.router.get("/example-1")
    async def example(user: RequestUser):
        assert user.value is not None
        assert user.value.authentication_mode == "TEST"
        return text(f"User name: {user.value.claims['name']}")

    @app.router.get("/example-2")
    async def example_2(user: User):
        assert user is not None
        assert user.authentication_mode == "TEST"
        return text(f"User name: {user.claims['name']}")

    @app.router.get("/example-3")
    async def example_3(user: Identity):
        assert user is not None
        assert user.authentication_mode == "TEST"
        return text(f"User name: {user.claims['name']}")

    claims = {"id": "001", "name": "Charlie Brown", "role": "user"}

    for path in ["/example-1", "/example-2", "/example-3"]:
        scope = get_example_scope(
            "GET",
            path,
            [(b"Authorization", urlsafe_b64encode(json.dumps(claims).encode("utf8")))],
        )
        await app(
            scope,
            MockReceive(),
            MockSend(),
        )

        content = await app.response.text()
        assert app.response.status == 200
        assert content == "User name: Charlie Brown"


async def test_request_binding(app):
    @app.router.get("/")
    async def example(req: Request):
        assert isinstance(req, Request)
        return "Foo"

    await app(
        get_example_scope("GET", "/", []),
        MockReceive(),
        MockSend(),
    )

    content = await app.response.text()
    assert app.response.status == 200
    assert content == "Foo"


async def test_use_auth_raises_if_app_is_already_started(app):
    class MockAuthHandler(AuthenticationHandler):
        async def authenticate(self, context):
            header_value = context.get_first_header(b"Authorization")
            if header_value:
                data = json.loads(urlsafe_b64decode(header_value).decode("utf8"))
                context.user = Identity(data, "TEST")
            else:
                context.user = None
            return context.user

    await app.start()
    with pytest.raises(RuntimeError):
        app.use_authentication()

    with pytest.raises(RuntimeError):
        app.use_authorization()


async def test_default_headers(app):
    app.default_headers = (("Example", "Foo"),)

    assert app.default_headers == (("Example", "Foo"),)

    @app.router.route("/")
    async def home():
        return text("Hello World")

    await app(
        get_example_scope("GET", "/", []),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 200
    assert response.headers.get_first(b"Example") == b"Foo"


async def test_start_stop_events(app):
    on_start_called = False
    on_after_start_called = False
    on_stop_called = False

    async def before_start(application: FakeApplication) -> None:
        assert isinstance(application, FakeApplication)
        assert application is app
        nonlocal on_start_called
        on_start_called = True

    async def after_start(application: FakeApplication) -> None:
        assert isinstance(application, FakeApplication)
        assert application is app
        nonlocal on_after_start_called
        on_after_start_called = True

    async def on_stop(application: FakeApplication) -> None:
        assert isinstance(application, FakeApplication)
        assert application is app
        nonlocal on_stop_called
        on_stop_called = True

    app.on_start += before_start
    app.after_start += after_start
    app.on_stop += on_stop

    await app.start()

    assert on_start_called is True
    assert on_after_start_called is True
    assert on_stop_called is False

    await app.stop()

    assert on_start_called is True
    assert on_after_start_called is True
    assert on_stop_called is True


@pytest.mark.parametrize("method", ["environ", "explicit"])
async def test_mounted_app_auto_events(method: str):
    if method == "environ":
        os.environ["APP_MOUNT_AUTO_EVENTS"] = "1"

    parent_app = FakeApplication()

    if method == "explicit":
        parent_app.mount_auto_events = True

    app = FakeApplication()

    parent_app.mount("/", app)

    on_start_called = False
    on_after_start_called = False
    on_stop_called = False

    async def before_start(application: FakeApplication) -> None:
        assert isinstance(application, FakeApplication)
        assert application is app
        nonlocal on_start_called
        on_start_called = True

    async def after_start(application: FakeApplication) -> None:
        assert isinstance(application, FakeApplication)
        assert application is app
        nonlocal on_after_start_called
        on_after_start_called = True

    async def on_stop(application: FakeApplication) -> None:
        assert isinstance(application, FakeApplication)
        assert application is app
        nonlocal on_stop_called
        on_stop_called = True

    app.on_start += before_start
    app.after_start += after_start
    app.on_stop += on_stop

    await parent_app.start()

    assert on_start_called is True
    assert on_after_start_called is True
    assert on_stop_called is False

    await parent_app.stop()

    assert on_start_called is True
    assert on_after_start_called is True
    assert on_stop_called is True


async def test_start_stop_multiple_events(app):
    on_start_count = 0
    on_stop_count = 0

    async def before_start_1(application: FakeApplication) -> None:
        assert isinstance(application, FakeApplication)
        assert application is app
        nonlocal on_start_count
        on_start_count += 1

    async def before_start_2(application: FakeApplication) -> None:
        assert isinstance(application, FakeApplication)
        assert application is app
        nonlocal on_start_count
        on_start_count += 1

    async def before_start_3(application: FakeApplication) -> None:
        assert isinstance(application, FakeApplication)
        assert application is app
        nonlocal on_start_count
        on_start_count += 1

    async def on_stop_1(application: FakeApplication) -> None:
        assert isinstance(application, FakeApplication)
        assert application is app
        nonlocal on_stop_count
        on_stop_count += 1

    async def on_stop_2(application: FakeApplication) -> None:
        assert isinstance(application, FakeApplication)
        assert application is app
        nonlocal on_stop_count
        on_stop_count += 1

    app.on_start += before_start_1
    app.on_start += before_start_2
    app.on_start += before_start_3
    app.on_stop += on_stop_1
    app.on_stop += on_stop_2

    await app.start()

    assert on_start_count == 3
    assert on_stop_count == 0

    await app.stop()

    assert on_start_count == 3
    assert on_stop_count == 2


async def test_start_stop_multiple_events_using_decorators(app: Application):
    on_start_count = 0
    on_stop_count = 0

    @app.on_start
    async def before_start_1(application: FakeApplication) -> None:
        assert isinstance(application, FakeApplication)
        assert application is app
        nonlocal on_start_count
        on_start_count += 1

    @app.on_start
    async def before_start_2(application: FakeApplication) -> None:
        assert isinstance(application, FakeApplication)
        assert application is app
        nonlocal on_start_count
        on_start_count += 1

    @app.on_start
    async def before_start_3(application: FakeApplication) -> None:
        assert isinstance(application, FakeApplication)
        assert application is app
        nonlocal on_start_count
        on_start_count += 1

    @app.on_stop
    async def on_stop_1(application: FakeApplication) -> None:
        assert isinstance(application, FakeApplication)
        assert application is app
        nonlocal on_stop_count
        on_stop_count += 1

    @app.on_stop
    async def on_stop_2(application: FakeApplication) -> None:
        assert isinstance(application, FakeApplication)
        assert application is app
        nonlocal on_stop_count
        on_stop_count += 1

    await app.start()

    assert on_start_count == 3
    assert on_stop_count == 0

    await app.stop()

    assert on_start_count == 3
    assert on_stop_count == 2


async def test_on_middlewares_configured_event(app: Application):
    on_middlewares_configuration_count = 0

    @app.on_middlewares_configuration
    def on_middlewares_configuration_1(application: FakeApplication) -> None:
        assert isinstance(application, FakeApplication)
        assert application is app
        nonlocal on_middlewares_configuration_count
        on_middlewares_configuration_count += 1

    @app.on_middlewares_configuration
    def on_middlewares_configuration_2(application: FakeApplication) -> None:
        assert isinstance(application, FakeApplication)
        assert application is app
        nonlocal on_middlewares_configuration_count
        on_middlewares_configuration_count += 1

    await app.start()

    assert on_middlewares_configuration_count == 2


async def test_app_events_decorator_args_support(app: Application):
    @app.on_start
    async def before_start_1(application: FakeApplication) -> None: ...

    @app.on_start()
    async def before_start_2(application: FakeApplication) -> None: ...


async def test_start_stop_remove_event_handlers(app):
    on_start_count = 0
    on_stop_count = 0

    async def before_start_1(application: FakeApplication) -> None:
        assert isinstance(application, FakeApplication)
        assert application is app
        nonlocal on_start_count
        on_start_count += 1

    async def before_start_2(application: FakeApplication) -> None:
        assert isinstance(application, FakeApplication)
        assert application is app
        nonlocal on_start_count
        on_start_count += 1

    async def on_stop_1(application: FakeApplication) -> None:
        assert isinstance(application, FakeApplication)
        assert application is app
        nonlocal on_stop_count
        on_stop_count += 1

    async def on_stop_2(application: FakeApplication) -> None:
        assert isinstance(application, FakeApplication)
        assert application is app
        nonlocal on_stop_count
        on_stop_count += 1

    app.on_start += before_start_1
    app.on_start += before_start_2
    app.on_stop += on_stop_1
    app.on_stop += on_stop_2

    app.on_start -= before_start_2
    app.on_stop -= on_stop_2

    await app.start()

    assert on_start_count == 1
    assert on_stop_count == 0

    await app.stop()

    assert on_start_count == 1
    assert on_stop_count == 1


async def test_start_runs_once(app):
    on_start_count = 0

    async def before_start(application: FakeApplication) -> None:
        assert isinstance(application, FakeApplication)
        assert application is app
        nonlocal on_start_count
        on_start_count += 1

    app.on_start += before_start

    await app.start()

    assert on_start_count == 1

    await app.start()

    assert on_start_count == 1


async def test_handles_on_start_error_asgi_lifespan(app):
    async def before_start(application: FakeApplication) -> None:
        raise RuntimeError("Crash!")

    app.on_start += before_start
    mock_send = MockSend()
    app.auto_start = False

    await app(
        {"type": "lifespan", "message": "lifespan.startup"},
        MockReceive(
            [
                {"type": "lifespan.startup"},
                {"type": "lifespan.shutdown"},
            ]
        ),
        mock_send,
    )

    assert mock_send.messages[0] == {"type": "lifespan.startup.failed"}


async def test_app_with_mounts_handles_on_start_error_asgi_lifespan(app: Application):
    async def before_start(application: FakeApplication) -> None:
        raise RuntimeError("Crash!")

    def foo():
        return "foo"

    other_app = Application()
    other_app.router.add_get("/foo", foo)

    app.mount("/foo", other_app)
    app.on_start += before_start

    mock_receive = MockReceive(
        [{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}]
    )
    mock_send = MockSend()

    await app(
        {"type": "lifespan", "message": "lifespan.startup"}, mock_receive, mock_send
    )

    assert mock_send.messages[0] == {"type": "lifespan.startup.failed"}


def test_register_controller_types_handle_empty_list(app):
    assert app.register_controllers([]) is None


async def test_response_normalization_wrapped(app):
    app.use_cors(
        allow_methods="GET POST DELETE", allow_origins="https://www.neoteroi.dev"
    )

    def headers(additional_headers):
        def decorator(next_handler):
            @wraps(next_handler)
            async def wrapped(*args, **kwargs) -> Response:
                response = ensure_response(await next_handler(*args, **kwargs))

                for name, value in additional_headers:
                    response.add_header(name.encode(), value.encode())

                return response

            return wrapped

        return decorator

    @app.router.get("/")
    @headers((("X-Foo", "Foo"),))
    async def home():
        return "Hello, World"

    await app(
        get_example_scope("GET", "/", []),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 200
    assert response.headers.get_single(b"X-Foo") == b"Foo"
    assert response.content.body == b"Hello, World"


async def test_response_normalization_with_cors(app):
    app.use_cors(
        allow_methods="GET POST DELETE", allow_origins="https://www.neoteroi.dev"
    )

    @app.router.get("/")
    async def home():
        return "Hello, World"

    await app(
        get_example_scope("GET", "/", []),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 200
    assert response.content.body == b"Hello, World"

    await app(
        get_example_scope("GET", "/", [(b"Origin", b"https://www.neoteroi.dev")]),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 200
    assert response.content.body == b"Hello, World"


async def test_async_event_raises_for_fire_method():
    event = ApplicationSyncEvent(None)

    with pytest.raises(TypeError):
        await event.fire()


async def test_application_raises_for_unhandled_scope_type(app):
    with pytest.raises(TypeError) as app_type_error:
        await app(
            {"type": "foo"},
            MockReceive(),
            MockSend(),
        )

    assert str(app_type_error.value) == "Unsupported scope type: foo"


def test_mounting_self_raises(app):
    with pytest.raises(TypeError):
        app.mount("/nope", app)


@pytest.mark.parametrize("param", [404, NotFound])
async def test_custom_handler_for_404_not_found(app, param):
    # Issue #538
    @app.exception_handler(param)
    async def not_found_handler(
        self: FakeApplication, request: Request, exc: NotFound
    ) -> Response:
        nonlocal app
        assert self is app
        assert isinstance(exc, NotFound)
        return Response(200, content=TextContent("Called"))

    @app.router.get("/")
    async def home():
        raise NotFound()

    await app(get_example_scope("GET", "/"), MockReceive(), MockSend())

    assert app.response is not None
    response: Response = app.response

    assert response
    actual_response_text = await response.text()
    assert actual_response_text == "Called"


@pytest.mark.parametrize("param", [404, NotFound])
async def test_http_exception_handler_type_resolution(app, param):
    # https://github.com/Neoteroi/BlackSheep/issues/538#issuecomment-2867564293

    # THIS IS NOT RECOMMENDED! IT IS NOT RECOMMENDED TO USE A CATCH-ALL EXCEPTION
    # HANDLER LIKE THE ONE BELOW. BLACKSHEEP AUTOMATICALLY HANDLES NON-HANDLED
    # EXCEPTIONS USING THE DIAGNOSTIC PAGES IF SHOW_ERROR_DETAILS IS ENABLED, AND USING
    # THE INTERNAL SERVER ERROR HANDLER OTHERWISE!
    # USE INSTEAD:
    # @app.exception_handler(500) or @app.exception_handler(InternalServerError)
    @app.exception_handler(Exception)
    async def catch_all(self: FakeApplication, request: Request, exc: NotFound):
        return Response(500, content=TextContent("Oh, No!"))

    @app.exception_handler(param)
    async def not_found_handler(
        self: FakeApplication, request: Request, exc: NotFound
    ) -> Response:
        return Response(200, content=TextContent("Called"))

    @app.router.get("/")
    async def home():
        raise NotFound()

    await app(get_example_scope("GET", "/"), MockReceive(), MockSend())

    assert app.response is not None
    response: Response = app.response

    assert response
    actual_response_text = await response.text()
    assert actual_response_text == "Called"


@pytest.mark.parametrize("param", [Conflict, 409])
async def test_http_exception_handler_type_resolution_inheritance(app, param):
    # https://github.com/Neoteroi/BlackSheep/issues/538#issuecomment-2867564293

    @app.exception_handler(param)
    async def catch_conflicts(self: FakeApplication, request: Request, exc: Conflict):
        return Response(
            409, content=TextContent(f"Custom {type(exc).__name__} Handler!")
        )

    class FooConflict(Conflict):
        pass

    class UfoConflict(Conflict):
        pass

    @app.router.get("/foo")
    async def foo():
        raise FooConflict()

    @app.router.get("/ufo")
    async def ufo():
        raise UfoConflict()

    expectations = {
        "/foo": "Custom FooConflict Handler!",
        "/ufo": "Custom UfoConflict Handler!",
    }

    for key, value in expectations.items():
        await app(get_example_scope("GET", key), MockReceive(), MockSend())

        assert app.response is not None
        response: Response = app.response

        assert response
        actual_response_text = await response.text()
        assert actual_response_text == value


@pytest.mark.parametrize("param", [500, InternalServerError])
async def test_custom_handler_for_500_internal_server_error(app, param):
    # Issue #538
    @app.exception_handler(param)
    async def unhandled_exception_handler(
        self: FakeApplication, request: Request, exc: InternalServerError
    ) -> Response:
        nonlocal app
        assert self is app
        assert isinstance(exc, InternalServerError)
        assert isinstance(exc.source_error, TypeError)
        return Response(200, content=TextContent("Called"))

    @app.router.get("/")
    async def home():
        raise TypeError()

    await app(get_example_scope("GET", "/"), MockReceive(), MockSend())

    assert app.response is not None
    response: Response = app.response

    assert response
    actual_response_text = await response.text()
    assert actual_response_text == "Called"


def get_pydantic_error(cls, data) -> str:
    expected_error = None

    try:
        cls(**data)
    except ValidationError as validation_error:
        expected_error = validation_error.json()

    assert isinstance(expected_error, str)
    return expected_error


async def test_application_pydantic_json_error(app):
    class CreateCatInput(BaseModel):
        name: str
        type: str

    @app.router.post("/api/cat")
    async def create_cat(data: CreateCatInput): ...

    # invalid JSON:
    content = b'{"foo":"not valid"}'

    expected_error = get_pydantic_error(CreateCatInput, {"foo": "not valid"})

    await app(
        get_example_scope(
            "POST",
            "/api/cat",
            [
                (b"content-length", str(len(content)).encode()),
                (b"content-type", b"application/json"),
            ],
        ),
        MockReceive([content]),
        MockSend(),
    )

    response = app.response
    assert response.status == 400
    assert response.content.body.decode() == expected_error


async def test_app_fallback_route(app):
    def not_found_handler():
        return text("Example", 404)

    app.router.fallback = not_found_handler

    await app(
        get_example_scope("GET", "/not-registered", []), MockReceive(), MockSend()
    )

    response = app.response
    assert response.status == 404
    assert (await response.text()) == "Example"


async def test_hsts_middleware(app):
    @app.router.get("/")
    async def home():
        return "OK"

    app.middlewares.append(HSTSMiddleware())

    await app(get_example_scope("GET", "/", []), MockReceive(), MockSend())

    response = app.response
    assert response.status == 200
    assert (await response.text()) == "OK"
    strict_transport = response.headers.get_first(b"Strict-Transport-Security")

    assert strict_transport == b"max-age=31536000; includeSubDomains;"


@pytest.mark.skipif(sys.version_info < (3, 10), reason="requires python3.10 or higher")
async def test_pep_593(app):
    """
    Tests a scenario that was reported as bug here:
    https://github.com/Neoteroi/BlackSheep/issues/257

    Application start-up failed
    """
    from dataclasses import dataclass

    @dataclass
    class Pet:
        name: str
        age: int | None

    @app.router.get("/pets")
    def pets() -> List[Pet]:
        return [
            Pet(name="Ren", age=None),
            Pet(name="Stimpy", age=3),
        ]

    docs = OpenAPIHandler(info=Info(title="Example API", version="0.0.1"))
    docs.bind_app(app)

    await app(get_example_scope("GET", "/pets", []), MockReceive(), MockSend())

    response = app.response
    assert response.status == 200
    assert (await response.json()) == [
        {"name": "Ren", "age": None},
        {"name": "Stimpy", "age": 3},
    ]


async def test_lifespan_event(app: Application):
    initialized = False
    disposed = False

    @app.lifespan
    async def some_async_gen():
        nonlocal initialized
        nonlocal disposed

        initialized = True
        yield
        disposed = True

    await app.start()

    assert initialized is True
    assert disposed is False

    await app.stop()

    assert initialized is True
    assert disposed is True


def test_mounting_apps_using_the_same_router_raises_error():
    # Recreates the scenario happening when the default singleton router is used for
    # both parent app and child app
    # https://github.com/Neoteroi/BlackSheep/issues/443
    single_router = Router()
    Application(router=single_router)

    with pytest.raises(SharedRouterError):
        Application(router=single_router)


async def test_application_sub_router_normalization():
    router = Router()
    app = FakeApplication(router=Router(sub_routers=[router]))

    # https://github.com/Neoteroi/BlackSheep/issues/466
    @dataclass
    class Person:
        id: Optional[int] = None
        name: str = ""

    @router.post("/")
    async def hello(request: Request, p: Person):
        return f"{request.client_ip}:Hello, {p.name}!"

    content = b'{"id": 1, "name": "Charlie Brown"}'

    await app(
        get_example_scope(
            "POST",
            "/",
            [
                (b"content-length", str(len(content)).encode()),
                (b"content-type", b"application/json"),
            ],
        ),
        MockReceive([content]),
        MockSend(),
    )

    response = app.response
    assert response is not None
    assert response.status == 200


@pytest.mark.skipif(
    validate_call is None, reason="Pydantic v1 validate_arguments is not supported"
)
async def test_pydantic_validate_call_scenario():
    app = FakeApplication(show_error_details=True, router=Router())
    get = app.router.get

    @get("/test1")
    @validate_call
    async def something(i: Annotated[int, Field(ge=1, le=10)] = 1):
        return f"i={i}"

    @get("/test2")
    @validate_call
    async def something_with_response_annotation(
        i: Annotated[int, Field(ge=1, le=10)] = 1,
    ) -> Response:
        return text(f"i={i}")

    expectations = [
        ("", 200, "i=1"),
        ("i=5", 200, "i=5"),
        ("i=-3", 400, "Input should be greater than or equal to 1"),
        ("i=20", 400, "Input should be less than or equal to 10"),
    ]

    for endpoint in ["/test1", "/test2"]:
        for query, status, response_text in expectations:
            await app(
                get_example_scope("GET", endpoint, query=query),
                MockReceive(),
                MockSend(),
            )
            response = app.response
            assert response is not None
            assert response.status == status

            if int(PYDANTIC_LIB_VERSION[0]) > 1:
                assert response_text in (await response.text())


@pytest.mark.skipif(
    int(PYDANTIC_LIB_VERSION[0]) < 2, reason="Run this test only with Pydantic v2"
)
async def test_refs_characters_handling():
    app = FakeApplication(show_error_details=True, router=Router())
    get = app.router.get

    # TODO: when support for Python < 3.12 is dropped,
    # the following can be rewritten without TypeVar, like:
    #
    # class Response[DataT](BaseModel):
    #

    DataT = TypeVar("DataT")

    class Response(BaseModel, Generic[DataT]):
        data: DataT

    class Cat(BaseModel):
        id: int
        name: str
        creation_time: datetime

    docs = OpenAPIHandler(info=Info(title="Example API", version="0.0.1"))
    docs.bind_app(app)

    @get("/cat")
    def generic_example() -> Response[Cat]: ...

    @get("/cats")
    def generic_list_example() -> list[Response[Cat]]: ...

    await app.start()

    json_docs = docs._json_docs.decode("utf8")
    yaml_docs = docs._yaml_docs.decode("utf8")
    spec = json.loads(json_docs)

    # "$ref": "#/components/schemas/Cat"
    for key in spec["components"]["schemas"].keys():
        assert re.match(
            "^[a-zA-Z0-9-_.]+$", key
        ), "$ref values must match /^[a-zA-Z0-9-_.]+$/"
        assert f'"$ref": "#/components/schemas/{key}"' in json_docs
        assert f"$ref: '#/components/schemas/{key}'" in yaml_docs


async def test_application_sse():
    app = FakeApplication(show_error_details=True, router=Router())
    get = app.router.get

    @get("/events")
    async def events_handler() -> AsyncIterable[ServerSentEvent]:
        for i in range(3):
            yield ServerSentEvent({"message": f"Hello World {i}"})
            await asyncio.sleep(0.05)

    scope = get_example_scope("GET", "/events", [])
    mock_send = MockSend()

    await app(scope, MockReceive(), mock_send)

    # Assert response status
    response = app.response
    assert response is not None
    assert response.status == 200

    # Assert Content-Type header
    assert response.headers.get_first(b"content-type") == b"text/event-stream"

    # Assert streamed events
    streamed_data = b"".join(
        [msg["body"] for msg in mock_send.messages if "body" in msg]
    )
    expected_events = (
        'data: {"message":"Hello World 0"}\n\n'
        'data: {"message":"Hello World 1"}\n\n'
        'data: {"message":"Hello World 2"}\n\n'
    )
    assert streamed_data.decode("utf-8") == expected_events


async def test_application_sse_plain_text():
    app = FakeApplication(show_error_details=True, router=Router())
    get = app.router.get

    @get("/events")
    async def events_handler() -> AsyncIterable[ServerSentEvent]:
        for i in range(3):
            yield TextServerSentEvent(f"Hello World {i}")
            await asyncio.sleep(0.05)

    scope = get_example_scope("GET", "/events", [])
    mock_send = MockSend()

    await app(scope, MockReceive(), mock_send)

    # Assert response status
    response = app.response
    assert response is not None
    assert response.status == 200

    # Assert Content-Type header
    assert response.headers.get_first(b"content-type") == b"text/event-stream"

    # Assert streamed events
    streamed_data = b"".join(
        [msg["body"] for msg in mock_send.messages if "body" in msg]
    )
    expected_events = (
        "data: Hello World 0\n\n" "data: Hello World 1\n\n" "data: Hello World 2\n\n"
    )
    assert streamed_data.decode("utf-8") == expected_events
