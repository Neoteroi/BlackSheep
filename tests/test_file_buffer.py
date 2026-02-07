"""
Tests for FileBuffer integration with multipart form data handling.
"""

from dataclasses import dataclass, field

import pytest

from blacksheep.contents import FileBuffer
from blacksheep.server.bindings import FromForm
from blacksheep.testing.helpers import get_example_scope
from blacksheep.testing.messages import MockReceive, MockSend
from tests.utils.application import FakeApplication


@pytest.fixture
def app():
    app = FakeApplication(show_error_details=True)
    yield app


async def test_from_form_with_file_buffer_dataclass(app):
    """Test FromForm binding with FileBuffer in dataclass"""

    @dataclass
    class UploadForm:
        username: str
        avatar: FileBuffer
        documents: list[FileBuffer] = field(default_factory=list)
        subscribe: bool = False

    @app.router.post("/upload")
    async def upload_handler(data: FromForm[UploadForm]):
        form = data.value
        assert isinstance(form, UploadForm)
        assert isinstance(form.username, str)
        assert isinstance(form.avatar, FileBuffer)
        assert isinstance(form.documents, list)
        assert isinstance(form.subscribe, bool)

        # Verify avatar FileBuffer properties
        assert form.avatar.name == "avatar"
        assert form.avatar.file_name == "test.txt"
        assert form.avatar.content_type == "text/plain"
        assert form.avatar.size > 0

        # Read avatar content
        avatar_content = form.avatar.read()
        assert avatar_content == b"Avatar file content"
        form.avatar.seek(0)  # Reset for potential re-reading

        # Verify documents
        assert len(form.documents) == 2
        for doc in form.documents:
            assert isinstance(doc, FileBuffer)
            assert doc.name == "documents"
            assert doc.file_name in ["doc1.txt", "doc2.txt"]

        return {
            "username": form.username,
            "avatar_filename": form.avatar.file_name,
            "documents_count": len(form.documents),
            "subscribe": form.subscribe,
        }

    await app.start()

    boundary = b"----WebKitFormBoundary7MA4YWxkTrZu0gW"
    content = b"\r\n".join(
        [
            boundary,
            b'Content-Disposition: form-data; name="username"',
            b"",
            b"john_doe",
            boundary,
            b'Content-Disposition: form-data; name="avatar"; filename="test.txt"',
            b"Content-Type: text/plain",
            b"",
            b"Avatar file content",
            boundary,
            b'Content-Disposition: form-data; name="documents"; filename="doc1.txt"',
            b"Content-Type: text/plain",
            b"",
            b"Document 1 content",
            boundary,
            b'Content-Disposition: form-data; name="documents"; filename="doc2.txt"',
            b"Content-Type: text/plain",
            b"",
            b"Document 2 content",
            boundary,
            b'Content-Disposition: form-data; name="subscribe"',
            b"",
            b"true",
            boundary + b"--",
        ]
    )

    await app(
        get_example_scope(
            "POST",
            "/upload",
            [
                (b"content-length", str(len(content)).encode()),
                (b"content-type", b"multipart/form-data; boundary=" + boundary[2:]),
            ],
        ),
        MockReceive([content]),
        MockSend(),
    )

    response = app.response
    assert response is not None
    assert response.status == 200

    data = await response.json()
    assert data["username"] == "john_doe"
    assert data["avatar_filename"] == "test.txt"
    assert data["documents_count"] == 2
    assert data["subscribe"] is True


async def test_from_form_with_file_buffer_optional_fields(app):
    """Test FromForm binding with FileBuffer when optional fields are missing"""

    @dataclass
    class UploadForm:
        username: str
        avatar: FileBuffer
        documents: list[FileBuffer] = field(default_factory=list)
        subscribe: bool = False

    @app.router.post("/upload-minimal")
    async def upload_minimal_handler(data: FromForm[UploadForm]):
        form = data.value
        assert isinstance(form, UploadForm)
        assert form.username == "jane_doe"
        assert isinstance(form.avatar, FileBuffer)
        assert form.avatar.file_name == "avatar.jpg"

        # Verify optional fields have defaults
        assert form.documents == []
        assert form.subscribe is False

        return {
            "username": form.username,
            "avatar_filename": form.avatar.file_name,
            "has_documents": len(form.documents) > 0,
            "subscribe": form.subscribe,
        }

    await app.start()

    boundary = b"----WebKitFormBoundary7MA4YWxkTrZu0gW"
    content = b"\r\n".join(
        [
            boundary,
            b'Content-Disposition: form-data; name="username"',
            b"",
            b"jane_doe",
            boundary,
            b'Content-Disposition: form-data; name="avatar"; filename="avatar.jpg"',
            b"Content-Type: image/jpeg",
            b"",
            b"\xff\xd8\xff\xe0",  # JPEG header bytes
            boundary + b"--",
        ]
    )

    await app(
        get_example_scope(
            "POST",
            "/upload-minimal",
            [
                (b"content-length", str(len(content)).encode()),
                (b"content-type", b"multipart/form-data; boundary=" + boundary[2:]),
            ],
        ),
        MockReceive([content]),
        MockSend(),
    )

    response = app.response
    assert response is not None
    assert response.status == 200

    data = await response.json()
    assert data["username"] == "jane_doe"
    assert data["avatar_filename"] == "avatar.jpg"
    assert data["has_documents"] is False
    assert data["subscribe"] is False


async def test_file_buffer_properties(app):
    """Test FileBuffer properties and methods"""

    @dataclass
    class FileUploadForm:
        file: FileBuffer

    @app.router.post("/test-props")
    async def test_props_handler(data: FromForm[FileUploadForm]):
        file_buffer = data.value.file
        assert isinstance(file_buffer, FileBuffer)

        # Test properties
        assert file_buffer.name == "file"
        assert file_buffer.file_name == "test.bin"
        assert file_buffer.content_type == "application/octet-stream"
        assert file_buffer.size > 0

        # Test read and seek
        content = file_buffer.read()
        assert content == b"Test file content for properties"

        # Test seek
        file_buffer.seek(0)
        content_again = file_buffer.read(10)
        assert content_again == b"Test file "

        # Reset position
        file_buffer.seek(0)

        return {
            "filename": file_buffer.file_name,
            "size": file_buffer.size,
            "content_type": file_buffer.content_type,
            "content_preview": content[:20].decode("utf-8", errors="ignore"),
        }

    await app.start()

    boundary = b"----WebKitFormBoundary7MA4YWxkTrZu0gW"
    content = b"\r\n".join(
        [
            boundary,
            b'Content-Disposition: form-data; name="file"; filename="test.bin"',
            b"Content-Type: application/octet-stream",
            b"",
            b"Test file content for properties",
            boundary + b"--",
        ]
    )

    await app(
        get_example_scope(
            "POST",
            "/test-props",
            [
                (b"content-length", str(len(content)).encode()),
                (b"content-type", b"multipart/form-data; boundary=" + boundary[2:]),
            ],
        ),
        MockReceive([content]),
        MockSend(),
    )

    response = app.response
    assert response is not None
    assert response.status == 200

    data = await response.json()
    assert data["filename"] == "test.bin"
    assert data["content_type"] == "application/octet-stream"
    assert data["size"] == 32
    assert "Test file content" in data["content_preview"]


async def test_file_buffer_with_large_file(app):
    """Test FileBuffer with larger content that would use SpooledTemporaryFile disk"""

    @dataclass
    class LargeFileForm:
        large_file: FileBuffer

    @app.router.post("/upload-large")
    async def upload_large_handler(data: FromForm[LargeFileForm]):
        file_buffer = data.value.large_file
        assert isinstance(file_buffer, FileBuffer)

        # Read the content
        content = file_buffer.read()
        file_buffer.seek(0)

        # Verify it's the expected size
        assert len(content) == file_buffer.size

        return {
            "filename": file_buffer.file_name,
            "size": file_buffer.size,
            "first_10_bytes": content[:10].hex(),
            "last_10_bytes": content[-10:].hex(),
        }

    await app.start()

    # Create a large content (>1MB to trigger disk spooling in SpooledTemporaryFile)
    large_data = b"X" * (2 * 1024 * 1024)  # 2MB of data

    boundary = b"----WebKitFormBoundary7MA4YWxkTrZu0gW"
    content = b"\r\n".join(
        [
            boundary,
            b'Content-Disposition: form-data; name="large_file"; filename="large.dat"',
            b"Content-Type: application/octet-stream",
            b"",
            large_data,
            boundary + b"--",
        ]
    )

    await app(
        get_example_scope(
            "POST",
            "/upload-large",
            [
                (b"content-length", str(len(content)).encode()),
                (b"content-type", b"multipart/form-data; boundary=" + boundary[2:]),
            ],
        ),
        MockReceive([content]),
        MockSend(),
    )

    response = app.response
    assert response is not None
    assert response.status == 200

    data = await response.json()
    assert data["filename"] == "large.dat"
    assert data["size"] == 2 * 1024 * 1024
    assert data["first_10_bytes"] == (b"X" * 10).hex()
    assert data["last_10_bytes"] == (b"X" * 10).hex()


async def test_file_buffer_context_manager(app):
    """Test FileBuffer as context manager"""

    @dataclass
    class FileForm:
        document: FileBuffer

    @app.router.post("/with-context")
    async def with_context_handler(data: FromForm[FileForm]):
        file_buffer = data.value.document

        # Use as context manager
        with file_buffer as f:
            content = f.read()
            assert content == b"Context manager test content"

        # File should still be accessible after context exit
        # (close() is called but SpooledTemporaryFile should handle it)
        return {
            "filename": file_buffer.file_name,
            "content_length": len(content),
        }

    await app.start()

    boundary = b"----WebKitFormBoundary7MA4YWxkTrZu0gW"
    content = b"\r\n".join(
        [
            boundary,
            b'Content-Disposition: form-data; name="document"; filename="test.txt"',
            b"Content-Type: text/plain",
            b"",
            b"Context manager test content",
            boundary + b"--",
        ]
    )

    await app(
        get_example_scope(
            "POST",
            "/with-context",
            [
                (b"content-length", str(len(content)).encode()),
                (b"content-type", b"multipart/form-data; boundary=" + boundary[2:]),
            ],
        ),
        MockReceive([content]),
        MockSend(),
    )

    response = app.response
    assert response is not None
    assert response.status == 200

    data = await response.json()
    assert data["filename"] == "test.txt"
    assert data["content_length"] == 28
