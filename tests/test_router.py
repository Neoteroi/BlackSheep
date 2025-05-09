from typing import List

import pytest

from blacksheep.messages import Request
from blacksheep.server.application import Application
from blacksheep.server.routing import (
    HostFilter,
    InvalidValuePatternName,
    MountRegistry,
    Route,
    RouteDuplicate,
    RouteException,
    RouteFilter,
    RouteMethod,
    Router,
    normalize_filters,
)
from tests.utils import modified_env

FAKE = b"FAKE"

MATCHING_ROUTES = [
    ("head", b"", b"/"),
    ("get", b"", b"/"),
    ("head", b"/", b"/"),
    ("get", b"/", b"/"),
    ("get", b"/:a", b"/foo"),
    ("get", b"/foo", b"/foo"),
    ("get", b"/foo", b"/Foo"),
    ("get", b"/:a/:b", b"/foo/oof"),
    ("post", b"/", b"/"),
    ("post", b"/:id", b"/123"),
    ("put", b"/", b"/"),
    ("delete", b"/", b"/"),
]

NON_MATCHING_ROUTE = [
    ("head", b"/", b"/foo"),
    ("get", b"/", b"/foo"),
    ("post", b"/", b"/foo"),
    ("post", b"/foo", b"/123"),
    ("put", b"/a/b/c/d", b"/a/b/c/"),
    ("put", b"/a/b/c/d", b"/a/b/c/d/e"),
    ("delete", b"/", b"/a"),
]


def mock_handler():
    return None


class MockHandler:
    def __init__(self, request_handler, auth_handler):
        self.request_handler = request_handler
        self.auth_handler = auth_handler


@pytest.mark.parametrize(
    "pattern,url,expected_values",
    [
        (b"/foo/:id", b"/foo/123", {"id": "123"}),
        (b"/foo/{id}", b"/foo/123", {"id": "123"}),
        (b"/foo/<id>", b"/foo/123", {"id": "123"}),
        ("/foo/:id", b"/foo/123", {"id": "123"}),
        ("/foo/{id}", b"/foo/123", {"id": "123"}),
        ("/foo/<id>", b"/foo/123", {"id": "123"}),
        (b"/foo/:id/ufo/:b", b"/foo/223/ufo/a13", {"id": "223", "b": "a13"}),
        (b"/foo/{id}/ufo/{b}", b"/foo/223/ufo/a13", {"id": "223", "b": "a13"}),
        (b"/foo/<id>/ufo/<b>", b"/foo/223/ufo/a13", {"id": "223", "b": "a13"}),
        ("/foo/:id/ufo/:b", b"/foo/223/ufo/a13", {"id": "223", "b": "a13"}),
        ("/foo/{id}/ufo/{b}", b"/foo/223/ufo/a13", {"id": "223", "b": "a13"}),
        (b"/foo/:id/ufo/:b", b"/Foo/223/Ufo/a13", {"id": "223", "b": "a13"}),
        (b"/:a", b"/Something", {"a": "Something"}),
        (b"/{a}", b"/Something", {"a": "Something"}),
        (b"/<a>", b"/Something", {"a": "Something"}),
        (b"/alive", b"/alive", None),
    ],
)
def test_route_good_matches(pattern, url, expected_values):
    route = Route(pattern, mock_handler)

    match = route.match_by_path(url)

    assert match is not None
    assert match.values == expected_values


@pytest.mark.parametrize(
    "pattern,url,expected_values",
    [
        ("/foo/{string:foo}", b"/foo/Hello", {"foo": "Hello"}),
        ("/foo/{string:foo}/ufo", b"/foo/Hello/ufo", {"foo": "Hello"}),
        ("/foo/{str:foo}", b"/foo/Hello", {"foo": "Hello"}),
        ("/foo/{str:foo}/ufo", b"/foo/Hello/ufo", {"foo": "Hello"}),
        ("/foo/{int:id}", b"/foo/123", {"id": "123"}),
        ("/foo/<int:id>", b"/foo/123", {"id": "123"}),
        ("/foo/{float:a}", b"/foo/123", {"a": "123"}),
        ("/foo/{float:a}", b"/foo/123.15", {"a": "123.15"}),
        ("/foo/<int:a>/<float:b>", b"/foo/123/777.77", {"a": "123", "b": "777.77"}),
        (
            "/foo/{uuid:id}",
            b"/foo/52464abf-f583-4b32-80f8-704bcb9e36a2",
            {"id": "52464abf-f583-4b32-80f8-704bcb9e36a2"},
        ),
        (
            "/public/{path:file}",
            b"/public/",
            {"file": ""},
        ),
        (
            "/public/{path:file}",
            b"/public/js/home/home.js",
            {"file": "js/home/home.js"},
        ),
        (
            "/public/{path:file}",
            b"/public/home.js",
            {"file": "home.js"},
        ),
        (
            "/public/<path:file>",
            b"/public/js/home/home.js",
            {"file": "js/home/home.js"},
        ),
        (
            "/<path:filepath>",
            b"/public/js/home/home.js",
            {"filepath": "public/js/home/home.js"},
        ),
    ],
)
def test_route_good_matches_with_parameter_patterns(pattern, url, expected_values):
    route = Route(pattern, mock_handler)
    match = route.match_by_path(url)

    assert match is not None
    assert match.values == expected_values


@pytest.mark.parametrize(
    "pattern,url",
    [
        (b"/foo/{int:id}", b"/foo/abc"),
        (b"/foo/<int:id>", b"/foo/X"),
        (b"/foo/{float:a}", b"/foo/false"),
        (b"/foo/{float:a}", b"/foo/123.15.31"),
        (b"/foo/{float:a}", b"/foo/123,50"),
        (b"/foo/{uuid:a}", b"/foo/not-a-guid"),
    ],
)
def test_route_bad_matches_with_parameter_patterns(pattern, url):
    route = Route(pattern, mock_handler)
    match = route.match_by_path(url)
    assert match is None


@pytest.mark.parametrize(
    "pattern",
    (
        "/public/<path:file>",
        "/<path:file>",
        "/public/*",
        "/*",
        "*",
    ),
)
def test_sort_routes_path_pattern(pattern):
    router = Router()
    catch_all_route = Route(pattern, mock_handler)

    router.add_route("GET", catch_all_route)
    router.add_route("GET", Route("/cat/:cat_id", mock_handler))
    router.add_route("GET", Route("/index", mock_handler))
    router.add_route("GET", Route("/about", mock_handler))

    assert router.routes[b"GET"][0] is catch_all_route

    router.sort_routes()

    assert router.routes[b"GET"][-1] is catch_all_route


@pytest.mark.parametrize(
    "pattern,invalid_pattern_name",
    [
        (b"/foo/{xxx:id}", "xxx"),
        (b"/foo/{ind:id}", "ind"),
    ],
)
def test_route_raises_for_invalid_parameter_name(pattern, invalid_pattern_name):
    with pytest.raises(InvalidValuePatternName):
        Route(pattern, mock_handler)


@pytest.mark.parametrize(
    "pattern",
    ["/a", "/a/b", "/a/b/c", "/cats/:cat_id", "/cats/:cat_id/friends"],
)
def test_route_repr(pattern: str):
    route = Route(pattern, mock_handler)
    assert repr(route) == f'<Route "{pattern}">'


@pytest.mark.parametrize(
    "pattern,url",
    [
        (b"/foo/:id", b"/fo/123"),
        (b"/foo/:id/ufo/:b", b"/foo/223/uof/a13"),
        (b"/:a", b"/"),
    ],
)
def test_route_bad_matches(pattern, url):
    route = Route(pattern, mock_handler)
    match = route.match_by_path(url)

    assert match is None


@pytest.mark.parametrize("pattern", [b"/:a/:a", b"/foo/:a/ufo/:a", b"/:foo/a/:foo"])
def test_invalid_route_repeated_group_name(pattern):
    with pytest.raises(ValueError):
        Route(pattern, mock_handler)


def test_route_handler_can_be_anything():
    def request_handler():
        pass

    def auth_handler():
        pass

    handler = MockHandler(request_handler, auth_handler)

    route = Route(b"/", handler)
    match = route.match_by_path(b"/")

    assert match is not None
    assert match.handler.request_handler is request_handler
    assert match.handler.auth_handler is auth_handler


@pytest.mark.parametrize("method,pattern,url", MATCHING_ROUTES)
def test_router_add_method(method, pattern, url):
    router = Router()
    router.add(method, pattern, mock_handler)
    router.apply_routes()
    match = router.get_match_by_method_and_path(method, url)

    assert match is not None
    assert match.handler is mock_handler

    route = router.get_matching_route(method, url)
    assert route is not None

    match = router.get_match_by_method_and_path(FAKE, url)
    assert match is None

    route = router.get_matching_route(FAKE, url)
    assert route is None


@pytest.mark.parametrize("method,pattern,url", NON_MATCHING_ROUTE)
def test_router_not_matching_routes(method, pattern, url):
    router = Router()
    router.add(method, pattern, mock_handler)
    route = router.get_match_by_method_and_path(method, url)
    assert route is None


@pytest.mark.parametrize("method,pattern,url", MATCHING_ROUTES)
def test_router_add_shortcuts(method, pattern, url):
    router = Router()

    fn = getattr(router, f"add_{method}")

    def home():
        return "Hello, World"

    fn(pattern, home)

    router.apply_routes()
    route = router.get_match_by_method_and_path(method.upper(), url)

    assert route is not None
    assert route.handler is home

    value = route.handler()
    assert value == "Hello, World"

    route = router.get_match_by_method_and_path(FAKE, url)
    assert route is None


@pytest.mark.parametrize("decorator,pattern,url", MATCHING_ROUTES)
def test_router_decorator(decorator, pattern, url):
    router = Router()

    method = getattr(router, decorator)

    @method(pattern)
    def home():
        return "Hello, World"

    router.apply_routes()
    route = router.get_match_by_method_and_path(decorator.upper(), url)

    assert route is not None
    assert route.handler is home

    value = route.handler()
    assert value == "Hello, World"

    route = router.get_match_by_method_and_path(FAKE, url)
    assert route is None


def test_router_match_any_by_extension():
    router = Router()

    def a(): ...

    def b(): ...

    router.add_get("/a/*.js", a)
    router.add_get("/b/*.css", b)

    router.apply_routes()
    m = router.get_match_by_method_and_path(RouteMethod.GET, b"/a/anything/really")
    assert m is None

    m = router.get_match_by_method_and_path(RouteMethod.GET, b"/a/anything/really.js")
    assert m is not None
    assert m.handler is a
    assert m.values.get("tail") == "anything/really"

    m = router.get_match_by_method_and_path(RouteMethod.GET, b"/b/anything/really.css")
    assert m is not None
    assert m.handler is b
    assert m.values.get("tail") == "anything/really"


def test_router_match_any_below():
    router = Router()

    def a(): ...

    def b(): ...

    def c(): ...

    def d(): ...

    router.add_get("/a/*", a)
    router.add_get("/b/*", b)
    router.add_get("/c/*", c)
    router.add_get("/d/*", d)

    router.apply_routes()

    m = router.get_match_by_method_and_path(RouteMethod.GET, b"/a")
    assert m is not None
    assert m.handler is a
    assert m.values.get("tail") == ""

    m = router.get_match_by_method_and_path(RouteMethod.GET, b"/a/")
    assert m is not None
    assert m.handler is a
    assert m.values.get("tail") == ""

    m = router.get_match_by_method_and_path(RouteMethod.GET, b"/a/anything/really")
    assert m is not None
    assert m.handler is a
    assert m.values.get("tail") == "anything/really"

    m = router.get_match_by_method_and_path(RouteMethod.GET, b"/b/anything/really")
    assert m is not None
    assert m.handler is b
    assert m.values.get("tail") == "anything/really"

    m = router.get_match_by_method_and_path(RouteMethod.GET, b"/c/anything/really")
    assert m is not None
    assert m.handler is c
    assert m.values.get("tail") == "anything/really"

    m = router.get_match_by_method_and_path(RouteMethod.GET, b"/d/anything/really")
    assert m is not None
    assert m.handler is d
    assert m.values.get("tail") == "anything/really"

    m = router.get_match_by_method_and_path(RouteMethod.POST, b"/a/anything/really")
    assert m is None

    m = router.get_match_by_method_and_path(RouteMethod.POST, b"/b/anything/really")
    assert m is None

    m = router.get_match_by_method_and_path(RouteMethod.POST, b"/c/anything/really")
    assert m is None

    m = router.get_match_by_method_and_path(RouteMethod.POST, b"/d/anything/really")
    assert m is None


def test_router_match_among_many():
    router = Router()

    def home(): ...

    def home_verbose(): ...

    def home_options(): ...

    def home_connect(): ...

    def get_foo(): ...

    def create_foo(): ...

    def patch_foo(): ...

    def delete_foo(): ...

    def ws(): ...

    router.add_trace("/", home_verbose)
    router.add_options("/", home_options)
    router.add_connect("/", home_connect)
    router.add_get("/", home)
    router.add_get("/foo", get_foo)
    router.add_patch("/foo", patch_foo)
    router.add_post("/foo", create_foo)
    router.add_delete("/foo", delete_foo)
    router.add_ws("/ws", ws)

    router.apply_routes()
    m = router.get_match_by_method_and_path(RouteMethod.GET, b"/")
    assert m is not None
    assert m.handler is home

    m = router.get_match_by_method_and_path(RouteMethod.TRACE, b"/")
    assert m is not None
    assert m.handler is home_verbose

    m = router.get_match_by_method_and_path(RouteMethod.CONNECT, b"/")
    assert m is not None
    assert m.handler is home_connect

    m = router.get_match_by_method_and_path(RouteMethod.OPTIONS, b"/")
    assert m is not None
    assert m.handler is home_options

    m = router.get_match_by_method_and_path(RouteMethod.POST, b"/")
    assert m is None

    m = router.get_match_by_method_and_path(RouteMethod.GET, b"/foo")
    assert m is not None
    assert m.handler is get_foo

    m = router.get_match_by_method_and_path(RouteMethod.POST, b"/foo")
    assert m is not None
    assert m.handler is create_foo

    m = router.get_match_by_method_and_path(RouteMethod.PATCH, b"/foo")
    assert m is not None
    assert m.handler is patch_foo

    m = router.get_match_by_method_and_path(RouteMethod.DELETE, b"/foo")
    assert m is not None
    assert m.handler is delete_foo

    m = router.get_match_by_method_and_path(RouteMethod.GET_WS, b"/ws")
    assert m is not None
    assert m.handler is ws


def test_router_match_ws_get_sharing_path():
    router = Router()

    def home(): ...

    def ws(): ...

    router.add_get("/", home)
    router.add_ws("/", ws)

    router.apply_routes()
    m = router.get_match_by_method_and_path(RouteMethod.GET, b"/")
    assert m is not None
    assert m.handler is home

    m = router.get_match_by_method_and_path(RouteMethod.GET_WS, b"/")
    assert m is not None
    assert m.handler is ws


def test_router_match_among_many_decorators():
    router = Router()

    @router.get("/")
    def home(): ...

    @router.trace("/")
    def home_verbose(): ...

    @router.options("/")
    def home_options(): ...

    @router.connect("/")
    def home_connect(): ...

    @router.get("/foo")
    def get_foo(): ...

    @router.post("/foo")
    def create_foo(): ...

    @router.patch("/foo")
    def patch_foo(): ...

    @router.delete("/foo")
    def delete_foo(): ...

    router.apply_routes()
    m = router.get_match_by_method_and_path(RouteMethod.GET, b"/")
    assert m is not None
    assert m.handler is home

    m = router.get_match_by_method_and_path(RouteMethod.TRACE, b"/")
    assert m is not None
    assert m.handler is home_verbose

    m = router.get_match_by_method_and_path(RouteMethod.CONNECT, b"/")
    assert m is not None
    assert m.handler is home_connect

    m = router.get_match_by_method_and_path(RouteMethod.OPTIONS, b"/")
    assert m is not None
    assert m.handler is home_options

    m = router.get_match_by_method_and_path(RouteMethod.POST, b"/")
    assert m is None

    m = router.get_match_by_method_and_path(RouteMethod.GET, b"/foo")
    assert m is not None
    assert m.handler is get_foo

    m = router.get_match_by_method_and_path(RouteMethod.POST, b"/foo")
    assert m is not None
    assert m.handler is create_foo

    m = router.get_match_by_method_and_path(RouteMethod.PATCH, b"/foo")
    assert m is not None
    assert m.handler is patch_foo

    m = router.get_match_by_method_and_path(RouteMethod.DELETE, b"/foo")
    assert m is not None
    assert m.handler is delete_foo


def test_router_match_with_trailing_slash():
    router = Router()

    def get_foo(): ...

    def create_foo(): ...

    router.add_get("/foo", get_foo)
    router.add_post("/foo", create_foo)

    router.apply_routes()
    m = router.get_match_by_method_and_path(RouteMethod.GET, b"/foo/")

    assert m is not None
    assert m.handler is get_foo

    m = router.get_match_by_method_and_path(RouteMethod.POST, b"/foo/")

    assert m is not None
    assert m.handler is create_foo

    m = router.get_match_by_method_and_path(RouteMethod.POST, b"/foo//")

    assert m is None


def test_fallback_route():
    router = Router()

    def not_found_handler():
        pass

    router.fallback = not_found_handler
    assert isinstance(router.fallback, Route)
    assert router.fallback.handler is not_found_handler

    m = router.get_match_by_method_and_path(RouteMethod.POST, b"/")

    assert m is not None
    assert m.handler is not_found_handler


def test_fallback_route_must_be_callable_or_route():
    router = Router()

    def not_found_handler():
        pass

    router.fallback = Route("*", not_found_handler)
    router.fallback = not_found_handler

    class Example:
        def __call__(self):
            pass

    router.fallback = Example()

    with pytest.raises(ValueError):
        router.fallback = False

    with pytest.raises(ValueError):
        router.fallback = "Something"


@pytest.mark.parametrize(
    "first_route,second_route",
    [
        ("/", "/"),
        (b"/", b"/"),
        (b"/", "/"),
        ("/", b"/"),
        ("/home/", "/home"),
        (b"/home/", b"/home"),
        ("/home", "/home/"),
        (b"/home", b"/home/"),
        ("/home", "/home//"),
        (b"/home", b"/home//"),
        ("/hello/world", "/hello/world/"),
        (b"/hello/world", b"/hello/world//"),
        ("/a/b", "/a/b"),
    ],
)
def test_duplicate_pattern_raises(first_route, second_route):
    router = Router()

    def home(): ...

    def another(): ...

    router.add_get(first_route, home)
    router.add_get(second_route, another)

    with pytest.raises(RouteDuplicate):
        router.apply_routes()


def test_duplicate_pattern_star_raises():
    router = Router()

    def home(): ...

    def another(): ...

    router.add_get("*", home)
    router.add_get("*", another)

    with pytest.raises(RouteDuplicate):
        router.apply_routes()


def test_more_than_one_star_raises():
    router = Router()

    def home(): ...

    with pytest.raises(RouteException):
        router.add_get("*/*", home)


def test_automatic_pattern_with_ellipsis():
    router = Router()

    @router.get(...)
    def home(): ...

    @router.get(...)
    def another(): ...

    router.apply_routes()
    match = router.get_match_by_method_and_path("GET", "/")
    assert match is None

    match = router.get_match_by_method_and_path("GET", "/home")

    assert match is not None
    assert match.handler is home

    match = router.get_match_by_method_and_path("GET", "/another")

    assert match is not None
    assert match.handler is another


def test_automatic_pattern_with_ellipsis_name_normalization():
    router = Router()

    @router.get(...)
    def hello_world(): ...

    router.apply_routes()
    match = router.get_match_by_method_and_path("GET", "/hello_world")

    assert match is None

    match = router.get_match_by_method_and_path("GET", "/hello-world")

    assert match is not None
    assert match.handler is hello_world


def test_automatic_pattern_with_ellipsis_index_name():
    router = Router()

    @router.get(...)
    def index(): ...

    router.apply_routes()
    match = router.get_match_by_method_and_path("GET", "/")

    assert match is not None
    assert match.handler is index


def test_router_iterable():
    router = Router()

    @router.get("/")
    def home(): ...

    @router.trace("/")
    def home_verbose(): ...

    @router.options("/")
    def home_options(): ...

    router.apply_routes()
    routes = list(router)
    assert len(routes) == 3

    handlers = {home, home_verbose, home_options}

    for route in routes:
        assert route.handler in handlers

    def fallback(): ...

    router.fallback = fallback

    routes = list(router)
    assert len(routes) == 4

    handlers = {home, home_verbose, home_options, fallback}

    for route in routes:
        assert route.handler in handlers


@pytest.mark.parametrize(
    "route_pattern,expected_pattern",
    [
        ["/", "/"],
        ["/api/v1/help", "/api/v1/help"],
        ["/api/cats/:cat_id", "/api/cats/{cat_id}"],
        ["/api/cats/:cat_id/friends", "/api/cats/{cat_id}/friends"],
        [
            "/api/cats/:cat_id/friends/:friend_id",
            "/api/cats/{cat_id}/friends/{friend_id}",
        ],
        [
            "/api/cats/{int:cat_id}/friends/{uuid:friend_id}",
            "/api/cats/{cat_id}/friends/{friend_id}",
        ],
        [
            "/api/cats/<int:cat_id>/friends/<uuid:friend_id>",
            "/api/cats/{cat_id}/friends/{friend_id}",
        ],
    ],
)
def test_route_to_openapi_pattern(route_pattern, expected_pattern):
    route = Route(route_pattern, object())

    assert route.mustache_pattern == expected_pattern


@pytest.mark.parametrize(
    "mount_path,expected_scope_path",
    [
        ("", "/*"),
        ("/", "/*"),
        ("/*", "/*"),
        ("/foo", "/foo/*"),
        ("/foo*", "/foo/*"),
        ("/foo/", "/foo/*"),
        ("/foo/*", "/foo/*"),
        ("/admin", "/admin/*"),
        ("/admin*", "/admin/*"),
        ("/a/b/c", "/a/b/c/*"),
        ("/a/b/c/", "/a/b/c/*"),
        ("/a/b/c*", "/a/b/c/*"),
        ("/a/b/c/*", "/a/b/c/*"),
    ],
)
def test_mount_add_method(mount_path, expected_scope_path):
    class ASGIHandler:
        def __call__(self, *args, **kwargs):
            pass

    app = ASGIHandler()
    mount = MountRegistry()
    mount.mount(mount_path, app)

    assert any(
        mount_route.pattern.decode() == expected_scope_path
        for mount_route in mount.mounted_apps
    )
    assert any(mount_route.handler is app for mount_route in mount.mounted_apps)


def test_mount_mounted_paths():
    mount = MountRegistry()
    assert mount.mounted_paths == set()

    mount.mount("/foo", Application())
    assert mount.mounted_paths == {"/foo"}

    mount.mount("/oFo", Application())
    assert mount.mounted_paths == {"/foo", "/ofo"}

    mount.mount("/ooF", Application())
    assert mount.mounted_paths == {"/foo", "/ofo", "/oof"}


def test_mount_add_raise_error_if_path_exist():
    with pytest.raises(AssertionError):
        mount = MountRegistry()
        mount.mount("/foo", None)  # type: ignore
        mount.mount("/foo", None)  # type: ignore


def test_route_filter_headers_1():
    router = Router(headers={"X-Test": "Test"})

    @router.get("/")
    def home(): ...

    router.apply_routes()
    match = router.get_match(Request("GET", b"/", []))

    assert match is None

    match = router.get_match(Request("GET", b"/foo", []))

    assert match is None

    match = router.get_match(Request("GET", b"/", [(b"X-Test", b"Test")]))

    assert match is not None


def test_route_filter_fallback():
    router = Router(headers={"X-Test": "Test"})

    @router.get("/")
    def home(): ...

    def fallback(): ...

    router.fallback = fallback
    match = router.get_match(Request("GET", b"/", []))

    assert match is not None
    assert match.handler is fallback


def test_route_filter_headers_2():
    test_router = Router(headers={"X-Test": "Test"})
    router = Router(sub_routers=[test_router])

    @router.get("/")
    def home(): ...

    @test_router.get("/")
    def test_home(): ...

    router.apply_routes()

    match = router.get_match(Request("GET", b"/", []))

    assert match is not None
    assert match.handler is home

    match = router.get_match(Request("GET", b"/", [(b"X-Test", b"Test")]))

    assert match is not None
    assert match.handler is test_home


def test_route_filter_params_1():
    router = Router(params={"foo": "1"})

    @router.get("/")
    def home(): ...

    router.apply_routes()
    match = router.get_match(Request("GET", b"/", []))

    assert match is None

    match = router.get_match(Request("GET", b"/?foo=1", []))

    assert match is not None

    match = router.get_match(Request("GET", b"/?foo=2", []))

    assert match is None


def test_route_filter_host():
    router = Router(host="neoteroi.dev")

    @router.get("/")
    def test_home(): ...

    router.apply_routes()
    match = router.get_match(Request("GET", b"/", [(b"host", b"localhost")]))

    assert match is None

    for host_value in {b"neoteroi.dev", b"NEOTEROI.DEV", b"neoteroi.dev:3000"}:
        match = router.get_match(Request("GET", b"/", [(b"host", host_value)]))

        assert match is not None
        assert match.handler is test_home


def test_route_custom_filter():
    class TimeFilter(RouteFilter):
        def __init__(self) -> None:
            self._counter = -1

        def handle(self, request: Request) -> bool:
            self._counter += 1

            return self._counter % 2 == 0

    router = Router(filters=[TimeFilter()])

    @router.get("/")
    def test_home(): ...

    router.apply_routes()

    for i in range(5):
        match = router.get_match(Request("GET", b"/", []))

        if i % 2 == 0:
            assert match is not None
        else:
            assert match is None


def test_host_filter_props():
    host_filter = HostFilter("www.neoteroi.dev")
    assert host_filter.host == "www.neoteroi.dev"


def test_normalize_filters():
    class CustomFilter(RouteFilter):
        def handle(self, request: Request) -> bool:
            return True

    input_filters: List[RouteFilter] = [CustomFilter()]
    all_filters = normalize_filters(
        host="www.neoteroi.dev", headers={"X-Foo": "foo"}, filters=input_filters
    )

    assert len(input_filters) == 1
    assert len(all_filters) == 3


def test_sub_routers_iter():
    test_router = Router(headers={"X-Test": "Test"})
    router = Router(sub_routers=[test_router])

    @router.get("/")
    def home(): ...

    @router.post("/foo")
    def post_foo(): ...

    @test_router.get("/")
    def test_home(): ...

    @test_router.post("/cats")
    def post_cat(): ...

    router.apply_routes()
    routes = list(router)
    assert len(routes) == 4
    handlers = [route.handler for route in routes]
    assert set(handlers) == {home, post_foo, test_home, post_cat}


def test_sub_routers_sort():
    test_router = Router(headers={"X-Test": "Test"})
    router = Router(sub_routers=[test_router])

    @router.get("/")
    def home(): ...

    @router.post("/foo")
    def post_foo(): ...

    @test_router.get("/")
    def test_home(): ...

    @test_router.post("/cats")
    def post_cat(): ...

    router.apply_routes()
    router.sort_routes()

    routes = list(router)
    assert len(routes) == 4
    handlers = [route.handler for route in routes]
    assert handlers == [home, post_foo, test_home, post_cat]


def test_routes_with_filters_can_have_duplicates():
    """
    Verifies that the router does not prevent registering multiple routes for the same
    method and path, when they have filters.
    """
    test_router = Router(headers={"X-Test": "Test"})
    router = Router(sub_routers=[test_router])

    @router.get("/")
    def home(): ...

    @router.post("/foo")
    def post_foo(): ...

    @test_router.get("/")
    def test_home(): ...

    @test_router.post("/cats")
    def post_cat(): ...

    router.apply_routes()
    routes = list(router)
    assert len(routes) == 4
    handlers = [route.handler for route in routes]
    assert set(handlers) == {home, post_foo, test_home, post_cat}


def _router_prefix_scenario_1(router: Router, prefix):
    @router.get("/")
    def home():
        return "Hello, World"

    router.apply_routes()
    match = router.get_match(Request("GET", prefix.encode(), []))
    assert match is not None
    assert match.handler() == "Hello, World"

    if prefix.endswith("/"):
        other_path = prefix[:-1]
    else:
        other_path = prefix + "/"

    match = router.get_match(Request("GET", other_path.encode(), []))
    assert match is not None
    assert match.handler() == "Hello, World"

    match = router.get_match(Request("GET", b"/", []))
    assert match is None


@pytest.mark.parametrize("prefix", ("/foo", "/x/", "/foo/bar/"))
def test_router_with_prefix(prefix):
    _router_prefix_scenario_1(Router(prefix=prefix), prefix)


@pytest.mark.parametrize("prefix", ("/foo", "/x/", "/foo/bar/"))
def test_router_with_env_prefix(prefix):
    with modified_env(APP_ROUTE_PREFIX=prefix):
        _router_prefix_scenario_1(Router(), prefix)


@pytest.mark.parametrize(
    "env_prefix,prefix", (("/foo", "/bar"), ("/x/", "v1"), ("/a", "/v1"))
)
def test_router_with_combined_prefix(env_prefix, prefix):
    with modified_env(APP_ROUTE_PREFIX=env_prefix):
        _router_prefix_scenario_1(Router(prefix=prefix), env_prefix + prefix)
