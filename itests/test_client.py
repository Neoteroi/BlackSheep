import os
import shutil
from uuid import uuid4

import pytest

from blacksheep import FormContent, FormPart, JSONContent, MultiPartFormData, Response

from .client_fixtures import get_static_path
from .client_fixtures import *  # NoQA
from .utils import assert_file_content_equals, assert_files_equals, get_file_bytes


def ensure_success(response: Response):
    assert response is not None
    assert isinstance(response, Response)
    assert response.status == 200


@pytest.mark.asyncio
async def test_get_plain_text(session):
    for _ in range(5):
        response = await session.get("/hello-world")
        ensure_success(response)
        text = await response.text()
        assert text == "Hello, World!"


@pytest.mark.asyncio
async def test_get_wikipedia_home(session):
    for _ in range(2):
        response = await session.get("https://www.wikipedia.org")
        ensure_success(response)
        text = await response.text()
        assert "Wikipedia" in text


@pytest.mark.asyncio
async def test_get_plain_text_stream(session):
    response = await session.get("/hello-world")
    ensure_success(response)

    data = bytearray()
    async for chunk in response.stream():
        data.extend(chunk)

    assert bytes(data) == b"Hello, World!"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "headers",
    [
        [(b"x-foo", str(uuid4()).encode())],
        [(b"x-a", b"Hello"), (b"x-b", b"World"), (b"x-c", b"!!")],
    ],
)
async def test_headers(session, headers):
    response = await session.head("/echo-headers", headers=headers)
    ensure_success(response)

    for key, value in headers:
        header = response.headers[key]
        assert (value,) == header


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "headers",
    [
        [(b"x-foo", str(uuid4()).encode())],
        [(b"x-a", b"Hello"), (b"x-b", b"World"), (b"x-c", b"!!")],
    ],
)
async def test_default_headers(session_alt, headers, server_host, server_port):
    response = await session_alt.head(
        f"http://{server_host}:{server_port}/echo-headers", headers=headers
    )
    ensure_success(response)

    for key, value in session_alt.default_headers:
        header = response.headers[key]
        assert (value,) == header

    for key, value in headers:
        header = response.headers[key]
        assert (value,) == header


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cookies", [{"x-foo": str(uuid4())}, {"x-a": "Hello", "x-b": "World", "x-c": "!!"}]
)
async def test_cookies(session, cookies):
    response = await session.get(
        "/echo-cookies",
        headers=[
            (
                b"cookie",
                "; ".join(
                    [f"{name}={value}" for name, value in cookies.items()]
                ).encode(),
            )
        ],
    )
    ensure_success(response)

    data = await response.json()

    for key, value in cookies.items():
        header = data[key]
        assert value == header


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name,value", [("Foo", "Foo"), ("Character-Name", "Charlie Brown")]
)
async def test_set_cookie(session, name, value):
    response = await session.get("/set-cookie", params=dict(name=name, value=value))
    ensure_success(response)

    assert value == response.cookies[name]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "data",
    [
        {"name": "Gorun Nova", "type": "Sword"},
        {"id": str(uuid4()), "price": 15.15, "name": "Ravenclaw T-Shirt"},
    ],
)
async def test_post_json(session, data):
    response = await session.post("/echo-posted-json", JSONContent(data))
    ensure_success(response)

    assert await response.json() == data


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "data",
    [
        {"name": "Gorun Nova", "type": "Sword"},
        {"id": str(uuid4()), "price": "15.15", "name": "Ravenclaw T-Shirt"},
    ],
)
async def test_post_form(session, data):
    response = await session.post("/echo-posted-form", FormContent(data))
    ensure_success(response)

    assert await response.json() == data


@pytest.mark.asyncio
async def test_post_multipart_form_with_files(session):

    if os.path.exists("out"):
        shutil.rmtree("out")

    response = await session.post(
        "/upload-files",
        MultiPartFormData(
            [
                FormPart(b"text1", b"text default"),
                FormPart(b"text2", "aωb".encode("utf8")),
                FormPart(b"file1", b"Content of a.txt.\r\n", b"text/plain", b"a.txt"),
                FormPart(
                    b"file2",
                    b"<!DOCTYPE html><title>Content of a.html.</title>\r\n",
                    b"text/html",
                    b"a.html",
                ),
                FormPart(
                    b"file3",
                    "aωb".encode("utf8"),
                    b"application/octet-stream",
                    b"binary",
                ),
            ]
        ),
    )
    ensure_success(response)

    assert_file_content_equals("./out/a.txt", "Content of a.txt.\n")
    assert_file_content_equals(
        "./out/a.html", "<!DOCTYPE html><title>Content of a.html.</title>\n"
    )
    assert_file_content_equals("./out/binary", "aωb")


@pytest.mark.asyncio
async def test_post_multipart_form_with_images(session):

    if os.path.exists("out"):
        shutil.rmtree("out")

    file_one_path = get_static_path("pexels-photo-126407.jpeg")
    file_two_path = get_static_path("pexels-photo-923360.jpeg")

    # NB: Flask api to handle parts with equal name is quite uncomfortable,
    # here for simplicity we set two parts with different names
    response = await session.post(
        "/upload-files",
        MultiPartFormData(
            [
                FormPart(
                    b"images1",
                    get_file_bytes(file_one_path),
                    b"image/jpeg",
                    b"three.jpg",
                ),
                FormPart(
                    b"images2",
                    get_file_bytes(file_two_path),
                    b"image/jpeg",
                    b"four.jpg",
                ),
            ]
        ),
    )
    ensure_success(response)

    assert_files_equals(f"./out/three.jpg", file_one_path)
    assert_files_equals(f"./out/four.jpg", file_two_path)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url_path,file_path",
    [
        ("/picture.jpg", get_static_path("pexels-photo-126407.jpeg")),
        ("/example.html", get_static_path("example.html")),
    ],
)
async def test_download_file(session, url_path, file_path):
    response = await session.get(url_path)
    ensure_success(response)

    value = bytearray()
    async for chunk in response.stream():
        value.extend(chunk)

    assert get_file_bytes(file_path) == bytes(value)
