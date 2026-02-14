import os
import shutil
from typing import AsyncIterable, Callable
from uuid import uuid4

import pytest

from blacksheep import (
    FormContent,
    FormPart,
    JSONContent,
    MultiPartFormData,
    Response,
    StreamedContent,
)
from blacksheep.common.files.asyncfs import FilesHandler

from .client_fixtures import *  # NoQA
from .client_fixtures import get_static_path
from .utils import assert_file_content_equals, assert_files_equals, get_file_bytes


def ensure_success(response: Response):
    assert response is not None
    assert isinstance(response, Response)
    assert response.status == 200


async def test_get_plain_text(session):
    for _ in range(5):
        response = await session.get("/hello-world")
        ensure_success(response)
        text = await response.text()
        assert text == "Hello, World!"


async def test_get_neoteroi_home(session):
    for _ in range(2):
        response = await session.get("https://www.neoteroi.dev")
        ensure_success(response)
        text = await response.text()
        assert "Neoteroi" in text


async def test_get_plain_text_stream(session):
    response = await session.get("/hello-world")
    ensure_success(response)

    data = bytearray()
    async for chunk in response.stream():
        data.extend(chunk)

    assert bytes(data) == b"Hello, World!"


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


@pytest.mark.parametrize(
    "name,value", [("Foo", "Foo"), ("Character-Name", "Charlie Brown")]
)
async def test_set_cookie(session, name, value):
    response = await session.get("/set-cookie", params=dict(name=name, value=value))
    ensure_success(response)

    assert value == response.cookies[name]


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

    assert_files_equals("./out/three.jpg", file_one_path)
    assert_files_equals("./out/four.jpg", file_two_path)


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


async def test_close_connection(session):
    for _ in range(3):
        response = await session.get("/close-connection")
        ensure_success(response)


async def test_cookies_with_redirect(session):
    """
    Tests proper handling of set-cookie header and client middlewares in general, when
    handling redirects.
    """
    response = await session.get("/redirect-setting-cookie")
    ensure_success(response)


async def test_request_body_streaming(session):
    """
    Test request body streaming by uploading a file using StreamedContent.
    This verifies that the client can stream request bodies efficiently.
    """
    if os.path.exists("out"):
        shutil.rmtree("out")

    file_path = get_static_path("pexels-photo-126407.jpeg")
    file_content = get_file_bytes(file_path)

    # Create a streaming content provider
    async def file_provider():
        # Simulate streaming by yielding chunks
        chunk_size = 8192
        for i in range(0, len(file_content), chunk_size):
            yield file_content[i : i + chunk_size]

    # Upload using StreamedContent
    content = StreamedContent(b"image/jpeg", file_provider)
    response = await session.post("/upload-raw/streamed-image.jpg", content=content)
    ensure_success(response)

    # Verify the uploaded file matches the original
    assert_files_equals("./out/streamed-image.jpg", file_path)


async def test_request_body_streaming_with_expect_continue(session):
    """
    Test request body streaming with Expect: 100-continue header.
    This ensures the server accepts the request before sending the body.
    """
    if os.path.exists("out"):
        shutil.rmtree("out")

    file_path = get_static_path("pexels-photo-923360.jpeg")
    file_content = get_file_bytes(file_path)

    async def file_provider():
        # Stream the file in chunks
        chunk_size = 16384
        for i in range(0, len(file_content), chunk_size):
            yield file_content[i : i + chunk_size]

    # Upload with Expect: 100-continue header
    content = StreamedContent(b"image/jpeg", file_provider)
    response = await session.post(
        "/upload-raw/expect-continue.jpg",
        content=content,
        headers=[(b"expect", b"100-continue")],
    )
    ensure_success(response)

    # Verify the uploaded file matches the original
    assert_files_equals("./out/expect-continue.jpg", file_path)


async def test_response_body_streaming_large_file(session):
    """
    Test response body streaming with a larger file to ensure
    proper chunk handling and memory efficiency.
    """
    response = await session.get("/picture.jpg")
    ensure_success(response)

    # Stream response and verify chunks
    received_chunks = []
    chunk_count = 0
    total_bytes = 0

    async for chunk in response.stream():
        chunk_count += 1
        total_bytes += len(chunk)
        received_chunks.append(chunk)

    # Verify we received the complete content
    received_content = b"".join(received_chunks)

    # The endpoint serves pexels-photo-126407.jpeg
    actual_file = get_static_path("pexels-photo-126407.jpeg")
    expected_content = get_file_bytes(actual_file)

    assert received_content == expected_content
    assert total_bytes == len(expected_content)
    assert chunk_count > 0  # At least one chunk


async def test_response_streaming_with_json(session):
    """
    Test response streaming with JSON content to ensure
    streaming works for different content types.
    """
    response = await session.get("/plain-json")
    ensure_success(response)

    # Stream the JSON response
    chunks = []
    async for chunk in response.stream():
        chunks.append(chunk)

    full_content = b"".join(chunks)

    # Parse JSON from streamed content
    import json

    data = json.loads(full_content.decode("utf-8"))

    assert data["message"] == "Hello, World!"


async def test_concurrent_streaming_requests(session):
    """
    Test multiple concurrent streaming requests to ensure
    proper connection pooling and stream isolation.
    """
    import asyncio

    async def fetch_and_stream(url_path):
        response = await session.get(url_path)
        ensure_success(response)

        chunks = []
        async for chunk in response.stream():
            chunks.append(chunk)

        return b"".join(chunks)

    # Fetch multiple resources concurrently
    results = await asyncio.gather(
        fetch_and_stream("/hello-world"),
        fetch_and_stream("/plain-json"),
        fetch_and_stream("/hello-world?name=Test"),
    )

    # Verify each response
    assert results[0] == b"Hello, World!"
    assert b"Hello, World!" in results[1]  # JSON response
    assert results[2] == b"Hello, Test!"


async def test_request_streaming_with_files_handler(session):
    """
    Test request body streaming using FilesHandler for chunked file reading.
    This simulates real-world file upload scenarios.
    """
    if os.path.exists("out"):
        shutil.rmtree("out")

    file_path = get_static_path("pexels-photo-126407.jpeg")

    def get_file_provider(file_path: str) -> Callable[[], AsyncIterable[bytes]]:
        async def data_provider():
            async for chunk in FilesHandler().chunks(file_path):
                yield chunk

        return data_provider

    # Upload using FilesHandler streaming
    content = StreamedContent(b"image/jpeg", get_file_provider(file_path))
    response = await session.post(
        "/upload-raw/files-handler-upload.jpg", content=content
    )
    ensure_success(response)

    # Verify the uploaded file
    assert_files_equals("./out/files-handler-upload.jpg", file_path)


async def test_streaming_error_handling(session):
    """
    Test error handling during response streaming to ensure
    exceptions are properly propagated.
    """
    # Request an endpoint that returns an error
    response = await session.get("/plain-json-error-simulation")

    # Should receive a 500 error
    assert response.status == 500

    # Stream should still work even for error responses
    chunks = []
    async for chunk in response.stream():
        chunks.append(chunk)

    content = b"".join(chunks)
    assert len(content) > 0  # Should have error response body


async def test_bidirectional_streaming(session):
    """
    Test bidirectional streaming: stream request body while receiving response.
    This verifies proper handling of concurrent read/write operations.
    """
    if os.path.exists("out"):
        shutil.rmtree("out")

    file_path = get_static_path("pexels-photo-923360.jpeg")
    file_content = get_file_bytes(file_path)

    async def file_provider():
        # Stream in smaller chunks to test concurrent behavior
        chunk_size = 4096
        for i in range(0, len(file_content), chunk_size):
            yield file_content[i : i + chunk_size]

    content = StreamedContent(b"image/jpeg", file_provider)
    response = await session.post("/upload-raw/bidirectional-test.jpg", content=content)

    # Stream the response (JSON confirmation)
    chunks = []
    async for chunk in response.stream():
        chunks.append(chunk)

    response_data = b"".join(chunks)
    assert response.status == 200
    assert len(response_data) > 0

    # Verify uploaded file
    assert_files_equals("./out/bidirectional-test.jpg", file_path)


async def test_multipart_stream_with_field_and_file(session):
    """
    Test multipart_stream handling with FormPart.field() and FormPart.from_file().
    This verifies proper handling of mixed form fields and file uploads.
    """
    if os.path.exists("out"):
        shutil.rmtree("out")

    # Prepare file path
    file_path = get_static_path("pexels-photo-923360.jpeg")

    # Create multipart data using the convenience methods
    parts = [
        # Text field - use field() method
        FormPart.field(
            "description",
            "Important documents for review",
        ),
        # File upload - use from_file() method
        FormPart.from_file(
            "attachment",
            file_path,
        ),
    ]

    # Create multipart content
    content = MultiPartFormData(parts)

    response = await session.post(
        "/upload-multipart-stream",
        content=content,
    )
    ensure_success(response)

    # Verify response
    data = await response.json()

    assert data["folder"] == "out"
    assert data["fields"]["description"] == "Important documents for review"
    assert len(data["files"]) == 1
    assert data["files"][0]["name"] == "pexels-photo-923360.jpeg"
    assert data["files"][0]["size"] > 0

    # Verify the uploaded file
    assert_files_equals("./out/pexels-photo-923360.jpeg", file_path)
