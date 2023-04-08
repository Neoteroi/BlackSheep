import pytest
import gzip

from blacksheep.server.gzip import GzipMiddleware
from blacksheep.testing.helpers import get_example_scope
from blacksheep.testing.messages import MockReceive, MockSend


@pytest.mark.parametrize("comp_level", range(0, 10))
@pytest.mark.asyncio
async def test_gzip_output(app, comp_level):
    @app.router.get("/")
    async def home():
        return "Hello, World"

    app.middlewares.append(GzipMiddleware(min_size=0, comp_level=comp_level))

    await app.start()

    await app(
        get_example_scope(
            "GET",
            "/",
        ),
        MockReceive([]),
        MockSend(),
    )

    response = app.response
    assert response.status == 200
    assert gzip.decompress(response.content.body) == b"Hello, World"
    assert response.headers.get_single(b"content-encoding") == b"gzip"


@pytest.mark.asyncio
async def test_skip_gzip_small_output(app):
    @app.router.get("/")
    async def home():
        return "Hello, World"

    app.middlewares.append(GzipMiddleware(min_size=16))

    await app.start()

    await app(
        get_example_scope(
            "GET",
            "/",
        ),
        MockReceive([]),
        MockSend(),
    )

    response = app.response
    assert response.status == 200
    assert response.content.body == b"Hello, World"
    with pytest.raises(ValueError):
        assert response.headers.get_single(b"content-encoding")


@pytest.mark.asyncio
async def test_skip_gzip_output_without_header(app):
    @app.router.get("/")
    async def home():
        return "Hello, World"

    app.middlewares.append(GzipMiddleware(min_size=0))

    await app.start()

    await app(
        get_example_scope(
            "GET",
            "/",
            accept_encoding=b"deflate",
        ),
        MockReceive([]),
        MockSend(),
    )

    response = app.response
    assert response.status == 200
    assert response.content.body == b"Hello, World"
    with pytest.raises(ValueError):
        assert response.headers.get_single(b"content-encoding")
