"""
Integration tests for FileBuffer OpenAPI documentation generation.
"""

import pytest
from openapidocs.v3 import Info, ValueFormat, ValueType

from blacksheep import Application, FileBuffer
from blacksheep.server.openapi.common import DefaultSerializer
from blacksheep.server.openapi.v3 import OpenAPIHandler


def get_test_app():
    """Create a test application."""
    return Application()


@pytest.mark.asyncio
async def test_filedata_single_file_openapi_spec():
    """Test that single FileBuffer generates correct OpenAPI spec."""
    app = get_test_app()

    @app.router.post("/upload")
    async def upload_file(file: FileBuffer):
        """Upload a single file."""
        return {"status": "ok"}

    docs = OpenAPIHandler(info=Info(title="Test API", version="1.0.0"))
    docs.bind_app(app)
    await app.start()

    spec = docs.generate_documentation(app)

    # Check that the path exists
    assert "/upload" in spec.paths

    # Check that POST operation exists
    path_item = spec.paths["/upload"]
    assert path_item.post is not None

    # Check request body
    assert path_item.post.request_body is not None
    request_body = path_item.post.request_body

    # Check that multipart/form-data is used
    assert "multipart/form-data" in request_body.content

    # Check schema
    media_type = request_body.content["multipart/form-data"]
    assert media_type.schema.type == ValueType.STRING
    assert media_type.schema.format == ValueFormat.BINARY


@pytest.mark.asyncio
async def test_filedata_multiple_files_openapi_spec():
    """Test that list[FileBuffer] generates correct OpenAPI spec."""
    app = get_test_app()

    @app.router.post("/upload-multiple")
    async def upload_files(files: list[FileBuffer]):
        """Upload multiple files."""
        return {"status": "ok", "count": len(files)}

    docs = OpenAPIHandler(info=Info(title="Test API", version="1.0.0"))
    docs.bind_app(app)
    await app.start()

    spec = docs.generate_documentation(app)

    # Check that the path exists
    assert "/upload-multiple" in spec.paths

    # Check that POST operation exists
    path_item = spec.paths["/upload-multiple"]
    assert path_item.post is not None

    # Check request body
    assert path_item.post.request_body is not None
    request_body = path_item.post.request_body

    # Check that multipart/form-data is used
    assert "multipart/form-data" in request_body.content

    # Check schema - should be array of binary
    media_type = request_body.content["multipart/form-data"]
    assert media_type.schema.type == ValueType.ARRAY
    assert media_type.schema.items is not None
    assert media_type.schema.items.type == ValueType.STRING
    assert media_type.schema.items.format == ValueFormat.BINARY


@pytest.mark.asyncio
async def test_filedata_yaml_output():
    """Test that FileBuffer generates correct YAML output."""
    app = get_test_app()

    @app.router.post("/upload")
    async def upload_file(file: FileBuffer):
        """Upload a file."""
        return {"status": "ok"}

    docs = OpenAPIHandler(info=Info(title="Test API", version="1.0.0"))
    docs.bind_app(app)
    await app.start()

    serializer = DefaultSerializer()
    yaml_text = serializer.to_yaml(docs.generate_documentation(app))

    # Verify key elements in YAML
    assert "/upload:" in yaml_text
    assert "post:" in yaml_text
    assert "multipart/form-data:" in yaml_text
    assert "type: string" in yaml_text
    assert "format: binary" in yaml_text


@pytest.mark.asyncio
async def test_filedata_json_output():
    """Test that FileBuffer generates correct JSON output."""
    app = get_test_app()

    @app.router.post("/upload")
    async def upload_file(file: FileBuffer):
        """Upload a file."""
        return {"status": "ok"}

    docs = OpenAPIHandler(info=Info(title="Test API", version="1.0.0"))
    docs.bind_app(app)
    await app.start()

    serializer = DefaultSerializer()
    json_text = serializer.to_json(docs.generate_documentation(app))

    # Verify key elements in JSON
    assert '"/upload"' in json_text
    assert '"post"' in json_text
    assert '"multipart/form-data"' in json_text
    assert '"type": "string"' in json_text or '"type":"string"' in json_text
    assert '"format": "binary"' in json_text or '"format":"binary"' in json_text
