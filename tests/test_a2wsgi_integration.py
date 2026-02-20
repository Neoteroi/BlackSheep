"""
Integration tests for a2wsgi support in BlackSheep.

This module tests that BlackSheep applications work correctly with a2wsgi,
which bridges ASGI applications to WSGI servers. a2wsgi requires proper
Content-Length headers instead of chunked transfer encoding for static files.
"""
import asyncio
import os
import tempfile
from pathlib import Path

import pytest

from blacksheep import Application, Response, json, text
from blacksheep.server.files import get_response_for_file
from blacksheep.common.files.asyncfs import FilesHandler
from blacksheep.server.resources import get_resource_file_path


def get_file_path(file_name, folder_name: str = "files") -> str:
    return get_resource_file_path("tests", f"{folder_name}/{file_name}")


class TestA2WSGICompatibility:
    """Tests for a2wsgi compatibility."""

    async def test_static_files_have_content_length(self):
        """Verify static files are served with Content-Length header."""
        from blacksheep.scribe import set_headers_for_response_content
        from blacksheep import Request

        test_file = get_file_path("example.txt")

        response = get_response_for_file(
            FilesHandler(),
            Request("GET", b"/static/example.txt", None),
            test_file,
            3600
        )

        # Simulate what the framework does
        set_headers_for_response_content(response)

        # Verify Content-Length is set
        content_length = response.get_first_header(b"content-length")
        assert content_length is not None, "a2wsgi requires Content-Length header"
        assert int(content_length) == 447

        # Verify no chunked encoding
        transfer_encoding = response.get_first_header(b"transfer-encoding")
        assert transfer_encoding is None, "a2wsgi cannot handle chunked encoding"

    async def test_application_with_static_files(self):
        """Test full application with static file serving."""
        app = Application()

        # Add static file serving
        test_folder = Path(get_resource_file_path("tests", "files"))
        app.serve_files(test_folder, root_path="/static")

        # Add a simple route
        @app.router.get("/")
        async def home():
            return text("Hello from BlackSheep")

        @app.router.get("/api/data")
        async def api_data():
            return json({"message": "API response", "status": "ok"})

        await app.start()

        # Test the routes work
        from blacksheep.testing import TestClient

        client = TestClient(app)

        # Test regular route
        response = await client.get("/")
        assert response.status == 200
        body = await response.text()
        assert body == "Hello from BlackSheep"

        # Test JSON API
        response = await client.get("/api/data")
        assert response.status == 200
        data = await response.json()
        assert data["message"] == "API response"

        # Test static file - this is critical for a2wsgi
        response = await client.get("/static/example.txt")
        assert response.status == 200

        # Verify Content-Length header is present
        content_length_headers = response.headers.get(b"content-length")
        assert content_length_headers, "Static files must have Content-Length for a2wsgi"
        assert len(content_length_headers) > 0
        content_length = int(content_length_headers[0])
        assert content_length == 447

        # Verify no chunked encoding
        transfer_encoding = response.headers.get(b"transfer-encoding")
        assert not transfer_encoding or b"chunked" not in transfer_encoding

    @pytest.mark.skipif(
        os.getenv("TEST_A2WSGI_REAL") != "1",
        reason="Requires a2wsgi package - set TEST_A2WSGI_REAL=1 to run"
    )
    async def test_with_actual_a2wsgi(self):
        """Test with actual a2wsgi package if available."""
        try:
            from a2wsgi import ASGIMiddleware
        except ImportError:
            pytest.skip("a2wsgi not installed")

        # Create a BlackSheep app
        app = Application()

        test_folder = Path(get_resource_file_path("tests", "files"))
        app.serve_files(test_folder, root_path="/static")

        @app.router.get("/")
        async def home():
            return text("Hello World")

        await app.start()

        # Wrap with a2wsgi
        wsgi_app = ASGIMiddleware(app)

        # Simulate a WSGI environ for static file request
        environ = {
            "REQUEST_METHOD": "GET",
            "PATH_INFO": "/static/example.txt",
            "QUERY_STRING": "",
            "SERVER_NAME": "localhost",
            "SERVER_PORT": "8000",
            "wsgi.url_scheme": "http",
            "wsgi.input": None,
            "wsgi.errors": None,
        }

        # Call the WSGI app
        status = None
        headers = None

        def start_response(status_line, response_headers):
            nonlocal status, headers
            status = status_line
            headers = dict(response_headers)

        # This should not raise an exception if a2wsgi compatibility works
        try:
            body_iter = wsgi_app(environ, start_response)
            body_parts = list(body_iter)

            # Verify we got a response
            assert status is not None
            assert status.startswith("200"), f"Expected 200 status, got {status}"

            # Verify Content-Length header exists
            assert "Content-Length" in headers or "content-length" in headers, \
                "a2wsgi requires Content-Length header"

            # Verify body was returned
            assert len(body_parts) > 0, "Should have response body"

            print("✓ a2wsgi compatibility verified with actual package")

        except Exception as e:
            pytest.fail(f"a2wsgi compatibility failed: {e}")


class TestContentLengthBehavior:
    """Test Content-Length header behavior for various response types."""

    async def test_small_file_content_length(self):
        """Small files should have Content-Length."""
        from blacksheep import Request
        from blacksheep.scribe import set_headers_for_response_content

        test_file = get_file_path("example.txt")
        response = get_response_for_file(
            FilesHandler(),
            Request("GET", b"/file.txt", None),
            test_file,
            3600
        )

        set_headers_for_response_content(response)

        content_length = response.get_first_header(b"content-length")
        assert content_length is not None
        assert int(content_length) == 447

    async def test_large_file_content_length(self):
        """Large files should also have Content-Length."""
        from blacksheep import Request
        from blacksheep.scribe import set_headers_for_response_content

        test_file = get_file_path("pexels-photo-126407.jpeg")
        response = get_response_for_file(
            FilesHandler(),
            Request("GET", b"/photo.jpeg", None),
            test_file,
            3600
        )

        set_headers_for_response_content(response)

        content_length = response.get_first_header(b"content-length")
        assert content_length is not None
        assert int(content_length) == 212034

    async def test_head_request_has_content_length(self):
        """HEAD requests should also have Content-Length."""
        from blacksheep import Request
        from blacksheep.scribe import set_headers_for_response_content

        test_file = get_file_path("example.txt")
        response = get_response_for_file(
            FilesHandler(),
            Request("HEAD", b"/file.txt", None),
            test_file,
            3600
        )

        # HEAD requests set headers directly, no need for set_headers_for_response_content
        content_length = response.get_first_header(b"content-length")
        assert content_length is not None
        assert int(content_length) == 447

        # Verify no body for HEAD
        assert response.content is None


class TestTemporaryFileServing:
    """Test serving dynamically created files."""

    async def test_serve_temporary_file(self):
        """Test that temporary files can be served with Content-Length."""
        from blacksheep import Request
        from blacksheep.scribe import set_headers_for_response_content

        # Create a temporary file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            test_content = "This is a test file for a2wsgi compatibility.\n" * 100
            f.write(test_content)
            temp_path = f.name

        try:
            expected_size = len(test_content.encode("utf-8"))

            response = get_response_for_file(
                FilesHandler(),
                Request("GET", b"/temp.txt", None),
                temp_path,
                0  # No cache
            )

            set_headers_for_response_content(response)

            # Verify Content-Length matches file size
            content_length = response.get_first_header(b"content-length")
            assert content_length is not None
            assert int(content_length) == expected_size

            # Verify content can be read
            body = await response.read()
            assert len(body) == expected_size

        finally:
            # Clean up
            os.unlink(temp_path)


if __name__ == "__main__":
    # Allow running this file directly for quick testing
    print("Running a2wsgi compatibility tests...")
    print("=" * 60)

    async def run_tests():
        test_suite = TestA2WSGICompatibility()

        print("\n1. Testing static files have Content-Length...")
        await test_suite.test_static_files_have_content_length()
        print("   ✓ Passed")

        print("\n2. Testing application with static files...")
        await test_suite.test_application_with_static_files()
        print("   ✓ Passed")

        print("\n3. Testing Content-Length behavior...")
        content_tests = TestContentLengthBehavior()
        await content_tests.test_small_file_content_length()
        print("   ✓ Small file: Passed")
        await content_tests.test_large_file_content_length()
        print("   ✓ Large file: Passed")
        await content_tests.test_head_request_has_content_length()
        print("   ✓ HEAD request: Passed")

        print("\n4. Testing temporary file serving...")
        temp_tests = TestTemporaryFileServing()
        await temp_tests.test_serve_temporary_file()
        print("   ✓ Passed")

        print("\n" + "=" * 60)
        print("✓ All a2wsgi compatibility tests passed!")
        print("\nTo test with actual a2wsgi package, run:")
        print("  pip install a2wsgi")
        print("  TEST_A2WSGI_REAL=1 pytest tests/test_a2wsgi_integration.py -v")

    asyncio.run(run_tests())
