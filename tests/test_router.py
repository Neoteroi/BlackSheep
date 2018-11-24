import pytest
from blacksheep import HttpMethod
from blacksheep.server.routing import Router, Route, RouteDuplicate


FAKE = b'FAKE'

MATCHING_ROUTES = [
    (b'head', b'', b'/'),
    (b'get', b'', b'/'),
    (b'head', b'/', b'/'),
    (b'get', b'/', b'/'),
    (b'get', b'/:a', b'/foo'),
    (b'get', b'/foo', b'/foo'),
    (b'get', b'/foo', b'/Foo'),
    (b'get', b'/:a/:b', b'/foo/oof'),
    (b'post', b'/', b'/'),
    (b'post', b'/:id', b'/123'),
    (b'put', b'/', b'/'),
    (b'delete', b'/', b'/'),
]

NON_MATCHING_ROUTE = [
    (b'head', b'/', b'/foo'),
    (b'get', b'/', b'/foo'),
    (b'post', b'/', b'/foo'),
    (b'post', b'/foo', b'/123'),
    (b'put', b'/a/b/c/d', b'/a/b/c/'),
    (b'put', b'/a/b/c/d', b'/a/b/c/d/e'),
    (b'delete', b'/', b'/a'),
]


def mock_handler():
    return None


class MockHandler:

    def __init__(self, request_handler, auth_handler):
        self.request_handler = request_handler
        self.auth_handler = auth_handler


class TestRoute:

    @pytest.mark.parametrize('pattern,url,expected_values', [
        (b'/foo/:id', b'/foo/123', {'id': b'123'}),
        (b'/foo/:id/ufo/:b', b'/foo/223/ufo/a13', {'id': b'223', 'b': b'a13'}),
        (b'/foo/:id/ufo/:b', b'/Foo/223/Ufo/a13', {'id': b'223', 'b': b'a13'}),
        (b'/:a', b'/Something', {'a': b'Something'}),
        (b'/alive', b'/alive', None)
    ])
    def test_route_good_matches(self, pattern, url, expected_values):
        route = Route(pattern, mock_handler)
        match = route.match(url)

        assert match is not None
        assert match.values == expected_values

    @pytest.mark.parametrize('pattern,url', [
        (b'/foo/:id', b'/fo/123'),
        (b'/foo/:id/ufo/:b', b'/foo/223/uof/a13'),
        (b'/:a', b'/'),
    ])
    def test_route_bad_matches(self, pattern, url):
        route = Route(pattern, mock_handler)
        match = route.match(url)

        assert match is None

    @pytest.mark.parametrize('pattern', [
        b'/:a/:a',
        b'/foo/:a/ufo/:a',
        b'/:foo/a/:foo'
    ])
    def test_invalid_route_repeated_group_name(self, pattern):
        with pytest.raises(ValueError):
            Route(pattern, mock_handler)

    def test_route_handler_can_be_anything(self):

        def request_handler():
            pass

        def auth_handler():
            pass

        handler = MockHandler(request_handler, auth_handler)

        route = Route(b'/', handler)
        match = route.match(b'/')

        assert match is not None
        assert match.handler.request_handler is request_handler
        assert match.handler.auth_handler is auth_handler


class TestRouter:

    @pytest.mark.parametrize('method,pattern,url', MATCHING_ROUTES)
    def test_router_add_method(self, method, pattern, url):
        router = Router()
        router.add(method, pattern, mock_handler)

        route = router.get_match(method, url)

        assert route is not None
        assert route.handler is mock_handler

        route = router.get_match(FAKE, url)
        assert route is None

    @pytest.mark.parametrize('method,pattern,url', NON_MATCHING_ROUTE)
    def test_router_not_matching_routes(self, method, pattern, url):
        router = Router()
        router.add(method, pattern, mock_handler)
        route = router.get_match(method, url)
        assert route is None

    @pytest.mark.parametrize('method,pattern,url', MATCHING_ROUTES)
    def test_router_add_shortcuts(self, method, pattern, url):
        router = Router()

        fn = getattr(router, f'add_{method.decode("latin-1")}')

        def home():
            return 'Hello, World'

        fn(pattern, home)

        route = router.get_match(method.upper(), url)

        assert route is not None
        assert route.handler is home

        value = route.handler()
        assert value == 'Hello, World'

        route = router.get_match(FAKE, url)
        assert route is None

    @pytest.mark.parametrize('decorator,pattern,url', MATCHING_ROUTES)
    def test_router_decorator(self, decorator, pattern, url):
        router = Router()

        method = getattr(router, decorator.decode("latin-1"))

        @method(pattern)
        def home():
            return 'Hello, World'

        route = router.get_match(decorator.upper(), url)

        assert route is not None
        assert route.handler is home

        value = route.handler()
        assert value == 'Hello, World'

        route = router.get_match(FAKE, url)
        assert route is None

    def test_router_match_any_by_extension(self):
        router = Router()

        def a():
            pass

        def b():
            pass

        router.add_get(b'/a/*.js', a)
        router.add_get(b'/b/*.css', b)

        m = router.get_match(HttpMethod.GET, b'/a/anything/really')
        assert m is None

        m = router.get_match(HttpMethod.GET, b'/a/anything/really.js')
        assert m is not None
        assert m.handler is a
        assert m.values.get('tail') == b'anything/really'

        m = router.get_match(HttpMethod.GET, b'/b/anything/really.css')
        assert m is not None
        assert m.handler is b
        assert m.values.get('tail') == b'anything/really'

    def test_router_match_any_below(self):
        router = Router()

        def a():
            pass

        def b():
            pass

        def c():
            pass

        def d():
            pass

        router.add_get(b'/a/*', a)
        router.add_get(b'/b/*', b)
        router.add_get(b'/c/*', c)
        router.add_get(b'/d/*', d)

        m = router.get_match(HttpMethod.GET, b'/a')
        assert m is None

        m = router.get_match(HttpMethod.GET, b'/a/anything/really')
        assert m is not None
        assert m.handler is a
        assert m.values.get('tail') == b'anything/really'

        m = router.get_match(HttpMethod.GET, b'/b/anything/really')
        assert m is not None
        assert m.handler is b
        assert m.values.get('tail') == b'anything/really'

        m = router.get_match(HttpMethod.GET, b'/c/anything/really')
        assert m is not None
        assert m.handler is c
        assert m.values.get('tail') == b'anything/really'

        m = router.get_match(HttpMethod.GET, b'/d/anything/really')
        assert m is not None
        assert m.handler is d
        assert m.values.get('tail') == b'anything/really'

        m = router.get_match(HttpMethod.POST, b'/a/anything/really')
        assert m is None

        m = router.get_match(HttpMethod.POST, b'/b/anything/really')
        assert m is None

        m = router.get_match(HttpMethod.POST, b'/c/anything/really')
        assert m is None

        m = router.get_match(HttpMethod.POST, b'/d/anything/really')
        assert m is None

    def test_router_match_among_many(self):
        router = Router()

        def home():
            pass

        def get_foo():
            pass

        def create_foo():
            pass

        def delete_foo():
            pass
        
        router.add_get(b'/', home)
        router.add_get(b'/foo', get_foo)
        router.add_post(b'/foo', create_foo)
        router.add_delete(b'/foo', delete_foo)

        m = router.get_match(HttpMethod.GET, b'/')

        assert m is not None
        assert m.handler is home

        m = router.get_match(HttpMethod.POST, b'/')

        assert m is None

        m = router.get_match(HttpMethod.GET, b'/foo')

        assert m is not None
        assert m.handler is get_foo

        m = router.get_match(HttpMethod.POST, b'/foo')

        assert m is not None
        assert m.handler is create_foo

        m = router.get_match(HttpMethod.DELETE, b'/foo')

        assert m is not None
        assert m.handler is delete_foo

    def test_fallback_route(self):
        router = Router()

        def not_found_handler():
            pass

        router.fallback = not_found_handler

        m = router.get_match(HttpMethod.POST, b'/')

        assert m is not None
        assert m.handler is not_found_handler

    def test_duplicate_pattern_raises(self):
        router = Router()

        def home():
            pass

        def another():
            pass

        router.add_get(b'/', home)

        with pytest.raises(RouteDuplicate):
            router.add_get(b'/', another)

    def test_duplicate_pattern_star_raises(self):
        router = Router()

        def home():
            pass

        def another():
            pass

        router.add_get(b'*', home)

        with pytest.raises(RouteDuplicate):
            router.add_get(b'*', another)
