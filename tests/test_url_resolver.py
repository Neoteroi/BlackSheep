"""
Tests for URLResolver: the scoped dependency that generates named-route URLs
taking the request's external mount prefix (ASGI root_path) into account.

Scenarios covered
-----------------
1. Basic usage – no router prefix, no mount: url_for returns the plain route path.
2. Router with a prefix – the prefix appears once in the result (it comes from
   Router.url_for; the external root_path is empty).
3. Child app mounted at a sub-path – the mount prefix is prepended by reading
   scope["root_path"] that the parent's MountMixin sets.
4. Child app with its own router prefix, mounted at a sub-path – mount prefix
   and router prefix both appear, but the router prefix is not doubled.
5. absolute_url_for – validates that the scheme and host are prepended correctly.
6. absolute_url_for behind a reverse proxy – root_path from an upstream proxy
   is reflected in the absolute URL.
7. Injection verification – asserts that declaring ``url_resolver: URLResolver``
   in a handler signature is sufficient (no extra DI setup required).
"""

import pytest

from blacksheep import Response
from blacksheep.server.application import Application
from blacksheep.server.responses import redirect
from blacksheep.server.routing import Router, URLResolver
from blacksheep.testing.helpers import get_example_scope
from blacksheep.testing.messages import MockReceive, MockSend
from tests.utils.application import FakeApplication

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _scope(method: str, path: str, *, root_path: str = "", host: str = "localhost"):
    """Build a minimal ASGI scope with an explicit root_path."""
    scope = get_example_scope(method, path, {"host": host})
    scope["root_path"] = root_path
    return scope


async def _call(app: FakeApplication, scope: dict) -> Response:
    await app(scope, MockReceive(), MockSend())
    assert app.response is not None
    return app.response


def _location(response: Response) -> str:
    header = response.get_first_header(b"location")
    assert header is not None, "Response has no Location header"
    return header.decode()


# ---------------------------------------------------------------------------
# 1. Basic – no prefix, no mount
# ---------------------------------------------------------------------------


async def test_url_resolver_basic_resolves_named_route():
    """url_for returns the plain route path when there is no prefix or mount."""
    app = FakeApplication(router=Router())

    @app.router.get("/cats/{cat_id}", name="cat-detail")
    async def cat_detail(cat_id: int) -> Response:
        return Response(200)

    @app.router.get("/redirect")
    async def redirect_handler(url_resolver: URLResolver) -> Response:
        return redirect(url_resolver.url_for("cat-detail", cat_id="42"))

    await app.start()

    response = await _call(app, _scope("GET", "/redirect"))

    assert response.status == 302
    assert _location(response) == "/cats/42"


# ---------------------------------------------------------------------------
# 2. Router with prefix="/api/v1" – prefix appears exactly once in the URL
# ---------------------------------------------------------------------------


async def test_url_resolver_with_router_prefix_no_double_prefix():
    """
    When the router has a prefix, Router.url_for already includes it.
    URLResolver must NOT prepend it a second time via base_path.
    """
    app = FakeApplication(router=Router(prefix="/api/v1"))

    @app.router.get("/cats/{cat_id}", name="cat-detail")
    async def cat_detail(cat_id: int) -> Response:
        return Response(200)

    @app.router.get("/redirect")
    async def redirect_handler(url_resolver: URLResolver) -> Response:
        return redirect(url_resolver.url_for("cat-detail", cat_id="42"))

    await app.start()

    response = await _call(app, _scope("GET", "/api/v1/redirect"))

    assert response.status == 302
    location = _location(response)
    assert location == "/api/v1/cats/42", (
        f"Expected /api/v1/cats/42 but got {location!r}. "
        "The router prefix must appear exactly once."
    )


# ---------------------------------------------------------------------------
# 3. Mounted child app – no child prefix
# ---------------------------------------------------------------------------


async def test_url_resolver_in_mounted_child_app_prepends_mount_prefix():
    """
    The parent mounts the child at '/sub'.
    MountMixin sets scope["root_path"] = "/sub" before delegating to the child.
    URLResolver.url_for must prepend "/sub" so the generated URL is absolute
    with respect to the host root.
    """
    parent_app = FakeApplication(router=Router())
    child_app = FakeApplication(router=Router())

    @child_app.router.get("/cats/{cat_id}", name="cat-detail")
    async def cat_detail(cat_id: int) -> Response:
        return Response(200)

    @child_app.router.get("/redirect")
    async def redirect_handler(url_resolver: URLResolver) -> Response:
        return redirect(url_resolver.url_for("cat-detail", cat_id="7"))

    parent_app.mount("/sub", child_app)
    await parent_app.start()
    await child_app.start()

    await parent_app(_scope("GET", "/sub/redirect"), MockReceive(), MockSend())
    response = child_app.response
    assert response is not None

    assert response.status == 302
    location = _location(response)
    assert location == "/sub/cats/7", (
        f"Expected /sub/cats/7 but got {location!r}. "
        "The mount prefix must be prepended to the generated URL."
    )


# ---------------------------------------------------------------------------
# 4. Mounted child app WITH a router prefix
# ---------------------------------------------------------------------------


async def test_url_resolver_in_mounted_child_app_with_child_prefix_no_double_prefix():
    """
    Parent mounts child at '/sub'; child router has prefix='/api'.
    The generated URL must be '/sub/api/cats/99' – mount prefix once,
    router prefix once, not doubled.
    """
    parent_app = FakeApplication()
    child_app = FakeApplication(router=Router(prefix="/api"))

    @child_app.router.get("/cats/{cat_id}", name="cat-detail")
    async def cat_detail(cat_id: int) -> Response:
        return Response(200)

    @child_app.router.get("/redirect")
    async def redirect_handler(url_resolver: URLResolver) -> Response:
        return redirect(url_resolver.url_for("cat-detail", cat_id="99"))

    parent_app.mount("/sub", child_app)
    await parent_app.start()
    await child_app.start()

    await parent_app(_scope("GET", "/sub/api/redirect"), MockReceive(), MockSend())
    response = child_app.response

    assert response is not None
    assert response.status == 302
    location = _location(response)
    assert location == "/sub/api/cats/99", (
        f"Expected /sub/api/cats/99 but got {location!r}. "
        "Mount prefix and router prefix must each appear exactly once."
    )


# ---------------------------------------------------------------------------
# 5. absolute_url_for – basic
# ---------------------------------------------------------------------------


async def test_url_resolver_absolute_url_for():
    """absolute_url_for returns scheme + host + path for a named route."""
    app = FakeApplication(router=Router())
    captured: list[str] = []

    @app.router.get("/cats/{cat_id}", name="cat-detail")
    async def cat_detail(cat_id: int) -> Response:
        return Response(200)

    @app.router.get("/redirect")
    async def redirect_handler(url_resolver: URLResolver) -> Response:
        captured.append(url_resolver.absolute_url_for("cat-detail", cat_id="5"))
        return Response(200)

    await app.start()
    await _call(app, _scope("GET", "/redirect", host="example.com"))

    assert len(captured) == 1
    assert captured[0] == "http://example.com/cats/5"


# ---------------------------------------------------------------------------
# 6. absolute_url_for behind a reverse proxy (scope root_path set)
# ---------------------------------------------------------------------------


async def test_url_resolver_absolute_url_for_behind_reverse_proxy():
    """
    When a reverse proxy sets scope["root_path"] (e.g. the app is served under
    /myapp), absolute_url_for must include that prefix.
    """
    app = FakeApplication(router=Router())
    captured: list[str] = []

    @app.router.get("/cats/{cat_id}", name="cat-detail")
    async def cat_detail(cat_id: int) -> Response:
        return Response(200)

    @app.router.get("/redirect")
    async def redirect_handler(url_resolver: URLResolver) -> Response:
        captured.append(url_resolver.absolute_url_for("cat-detail", cat_id="3"))
        return Response(200)

    await app.start()
    await _call(
        app,
        _scope("GET", "/redirect", root_path="/myapp", host="example.com"),
    )

    assert len(captured) == 1
    assert captured[0] == "http://example.com/myapp/cats/3"


# ---------------------------------------------------------------------------
# 7. Injection verification – no extra DI setup required
# ---------------------------------------------------------------------------


async def test_url_resolver_injected_without_di_scope_middleware():
    """
    Declaring ``url_resolver: URLResolver`` in a handler signature must work
    out of the box, without calling register_http_context or adding
    di_scope_middleware.  The URLResolverBinder handles this transparently.
    """
    app = FakeApplication(router=Router())
    injected_instance: list[URLResolver] = []

    @app.router.get("/items/{item_id}", name="item-detail")
    async def item_detail(item_id: str) -> Response:
        return Response(200)

    @app.router.get("/check")
    async def check_handler(url_resolver: URLResolver) -> Response:
        injected_instance.append(url_resolver)
        return Response(200, content=None)

    await app.start()
    await _call(app, _scope("GET", "/check"))

    assert len(injected_instance) == 1
    assert isinstance(injected_instance[0], URLResolver)


# ---------------------------------------------------------------------------
# 8. Unit-level: URLResolver.url_for with explicit scope root_path
# ---------------------------------------------------------------------------


async def test_url_resolver_unit_with_explicit_root_path():
    """
    Unit test: construct a URLResolver directly, set scope["root_path"] on the
    request, and verify url_for prepends the external base.
    """
    from blacksheep.messages import Request

    router = Router()

    @router.get("/widgets/{widget_id}", name="widget-detail")
    def widget_detail(widget_id: str) -> Response:
        return Response(200)

    router.apply_routes()

    request = Request("GET", b"/widgets/redirect", None)
    request.scope = {"root_path": "/tenant"}  # type: ignore[assignment]

    resolver = URLResolver(router, request)
    assert resolver.url_for("widget-detail", widget_id="9") == "/tenant/widgets/9"


async def test_url_resolver_unit_no_root_path():
    """
    Unit test: when scope["root_path"] is absent or empty, url_for returns the
    plain path from Router.url_for (which already includes any router prefix).
    """
    from blacksheep.messages import Request

    router = Router(prefix="/v2")

    @router.get("/things/{thing_id}", name="thing-detail")
    def thing_detail(thing_id: str) -> Response:
        return Response(200)

    router.apply_routes()

    request = Request("GET", b"/v2/things/redirect", None)
    request.scope = {"root_path": ""}  # type: ignore[assignment]

    resolver = URLResolver(router, request)
    # Router.url_for already includes /v2 prefix; no external base → no doubling
    assert resolver.url_for("thing-detail", thing_id="1") == "/v2/things/1"
