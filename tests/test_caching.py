import pytest

from blacksheep.server.controllers import Controller
from blacksheep.server.headers.cache import (
    CacheControlMiddleware,
    cache_control,
    write_cache_control_response_header,
)
from blacksheep.server.routing import RoutesRegistry
from blacksheep.testing.helpers import get_example_scope
from blacksheep.testing.messages import MockReceive, MockSend

CACHE_CONTROL_PARAMS_EXPECTED = [
    ({"max_age": 0}, b"max-age=0"),
    ({"max_age": 120}, b"max-age=120"),
    ({"shared_max_age": 604800}, b"s-maxage=604800"),
    ({"no_cache": True}, b"no-cache"),
    ({"no_store": True}, b"no-store"),
    ({"must_understand": True, "no_store": True}, b"no-store, must-understand"),
    ({"private": True}, b"private"),
    ({"public": True}, b"public"),
    ({"no_cache": True, "no_store": True}, b"no-cache, no-store"),
    ({"max_age": 0, "must_revalidate": True}, b"max-age=0, must-revalidate"),
    ({"max_age": 0, "proxy_revalidate": True}, b"max-age=0, proxy-revalidate"),
    ({"no_transform": True}, b"no-transform"),
    (
        {"public": True, "max_age": 604800, "immutable": True},
        b"public, max-age=604800, immutable",
    ),
    (
        {"max_age": 604800, "stale_while_revalidate": 86400},
        b"max-age=604800, stale-while-revalidate=86400",
    ),
    (
        {"max_age": 604800, "stale_if_error": 86400},
        b"max-age=604800, stale-if-error=86400",
    ),
]


async def _assert_scenario(app, expected_header: bytes):
    @app.router.get("/no-cache")
    @cache_control(no_cache=True, no_store=True)
    def example_no():
        return "Example"

    await app.start()
    await app(get_example_scope("GET", "/", []), MockReceive(), MockSend())

    response = app.response
    assert response.status == 200
    cache_control_value = response.headers[b"cache-control"]
    assert len(cache_control_value) == 1
    assert cache_control_value[0] == expected_header

    await app(get_example_scope("GET", "/no-cache", []), MockReceive(), MockSend())

    response = app.response
    assert response.status == 200
    cache_control_value = response.headers[b"cache-control"]
    assert len(cache_control_value) == 1
    assert cache_control_value[0] == b"no-cache, no-store"


def test_write_cache_control_response_header_raises_for_priv_pub():
    with pytest.raises(ValueError):
        write_cache_control_response_header(private=True, public=True)


@pytest.mark.parametrize("params,expected_header", CACHE_CONTROL_PARAMS_EXPECTED)
async def test_cache_control_decorator(app, params, expected_header):
    @app.router.get("/")
    @cache_control(**params)
    def example():
        return "Example"

    await _assert_scenario(app, expected_header)


@pytest.mark.parametrize("params,expected_header", CACHE_CONTROL_PARAMS_EXPECTED)
async def test_cache_control_in_controller(app, params, expected_header):
    app.controllers_router = RoutesRegistry()
    get = app.controllers_router.get

    class Home(Controller):
        @get("/")
        @cache_control(**params)
        async def index(self):
            return "Example"

    await _assert_scenario(app, expected_header)


@pytest.mark.parametrize("params,expected_header", CACHE_CONTROL_PARAMS_EXPECTED)
async def test_cache_control_middleware(app, params, expected_header):
    app.middlewares.append(CacheControlMiddleware(**params))

    @app.router.get("/")
    def example():
        return "Example"

    await _assert_scenario(app, expected_header)
