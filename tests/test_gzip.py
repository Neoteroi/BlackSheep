import gzip

import pytest

from blacksheep.server.compression import GzipMiddleware
from blacksheep.testing.helpers import get_example_scope
from blacksheep.testing.messages import MockReceive, MockSend


@pytest.mark.parametrize(
    "comp_level, comp_size",
    (zip(range(0, 10), (468, 283, 283, 283, 282, 282, 282, 282, 282, 282))),
)
async def test_gzip_output(app, comp_level, comp_size):
    return_value = (
        "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do "
        "eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim "
        "veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo "
        "consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse cillum "
        "dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, "
        "sunt in culpa qui officia deserunt mollit anim id est laborum."
    )

    @app.router.get("/")
    async def home():
        return return_value

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
    assert response.content.length == comp_size
    assert gzip.decompress(response.content.body) == return_value.encode("ascii")
    assert response.headers.get_single(b"content-encoding") == b"gzip"


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
    assert response.content.length == 12
    with pytest.raises(ValueError):
        assert response.headers.get_single(b"content-encoding")


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
    assert response.content.length == 12
    with pytest.raises(ValueError):
        assert response.headers.get_single(b"content-encoding")


async def test_skip_gzip_output_for_unhandled_type(app):
    @app.router.get("/")
    async def home():
        return "Hello, World"

    app.middlewares.append(GzipMiddleware(min_size=0, handled_types=[b"text/html"]))

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
    assert response.content.length == 12
    assert response.content.body == b"Hello, World"
    with pytest.raises(ValueError):
        assert response.headers.get_single(b"content-encoding")
