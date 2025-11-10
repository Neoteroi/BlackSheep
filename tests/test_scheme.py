import pytest

from blacksheep import Request, Response
from blacksheep.contents import TextContent
from blacksheep.server.remotes.scheme import (
    HTTPSchemeMiddleware,
    configure_scheme_middleware,
)
from blacksheep.server.security.hsts import HSTSMiddleware
from blacksheep.testing.helpers import get_example_scope
from blacksheep.testing.messages import MockReceive, MockSend
from tests.utils.application import FakeApplication


class TestHTTPSchemeMiddleware:
    """Tests for HTTPSchemeMiddleware"""

    def test_middleware_accepts_http_scheme(self):
        middleware = HTTPSchemeMiddleware("http")
        assert middleware.scheme == "http"

    def test_middleware_accepts_https_scheme(self):
        middleware = HTTPSchemeMiddleware("https")
        assert middleware.scheme == "https"

    def test_middleware_rejects_invalid_scheme(self):
        with pytest.raises(TypeError, match="Invalid scheme, expected http | https"):
            HTTPSchemeMiddleware("ftp")

    async def test_middleware_forces_http_scheme(self):
        middleware = HTTPSchemeMiddleware("http")
        request = Request("GET", b"/", None)
        request.scheme = "https"  # Original scheme

        async def handler(req):
            assert req.scheme == "http"
            return Response(200)

        response = await middleware(request, handler)
        assert response.status == 200

    async def test_middleware_forces_https_scheme(self):
        middleware = HTTPSchemeMiddleware("https")
        request = Request("GET", b"/", None)
        request.scheme = "http"  # Original scheme

        async def handler(req):
            assert req.scheme == "https"
            return Response(200)

        response = await middleware(request, handler)
        assert response.status == 200


class TestConfigureSchemeMiddleware:
    """Tests for configure_scheme_middleware function"""

    @pytest.fixture
    def fake_app(self, monkeypatch):
        """Fixture that creates a FakeApplication with monkeypatch available"""

        def _create_app(**env_vars):
            for key, value in env_vars.items():
                monkeypatch.setenv(key, value)
            return FakeApplication()

        return _create_app

    async def test_force_https_enables_https_and_hsts(self, fake_app):
        app = fake_app(APP_FORCE_HTTPS="true")

        configure_scheme_middleware(app)

        # Check that HTTPSchemeMiddleware with https is added
        force_scheme_middlewares = [
            m for m in app.middlewares if isinstance(m, HTTPSchemeMiddleware)
        ]
        assert len(force_scheme_middlewares) == 1
        assert force_scheme_middlewares[0].scheme == "https"

        # Check that HSTSMiddleware is added
        hsts_middlewares = [m for m in app.middlewares if isinstance(m, HSTSMiddleware)]
        assert len(hsts_middlewares) == 1

    async def test_http_scheme_without_force_https(self, fake_app):
        app = fake_app(APP_HTTP_SCHEME="http")

        configure_scheme_middleware(app)

        # Check that HTTPSchemeMiddleware is added with http
        force_scheme_middlewares = [
            m for m in app.middlewares if isinstance(m, HTTPSchemeMiddleware)
        ]
        assert len(force_scheme_middlewares) == 1
        assert force_scheme_middlewares[0].scheme == "http"

        # Check that HSTSMiddleware is NOT added
        hsts_middlewares = [m for m in app.middlewares if isinstance(m, HSTSMiddleware)]
        assert len(hsts_middlewares) == 0

    async def test_https_scheme_without_force_https(self, fake_app):
        app = fake_app(APP_HTTP_SCHEME="https")

        configure_scheme_middleware(app)

        # Check that HTTPSchemeMiddleware is added with https
        force_scheme_middlewares = [
            m for m in app.middlewares if isinstance(m, HTTPSchemeMiddleware)
        ]
        assert len(force_scheme_middlewares) == 1
        assert force_scheme_middlewares[0].scheme == "https"

        # Check that HSTSMiddleware is NOT added (only when force_https=True)
        hsts_middlewares = [m for m in app.middlewares if isinstance(m, HSTSMiddleware)]
        assert len(hsts_middlewares) == 0

    async def test_no_middleware_when_not_configured(self, fake_app):
        app = fake_app()

        configure_scheme_middleware(app)

        # Check that no middleware is added
        force_scheme_middlewares = [
            m for m in app.middlewares if isinstance(m, HTTPSchemeMiddleware)
        ]
        assert len(force_scheme_middlewares) == 0

        hsts_middlewares = [m for m in app.middlewares if isinstance(m, HSTSMiddleware)]
        assert len(hsts_middlewares) == 0

    async def test_force_https_takes_precedence(self, fake_app):
        app = fake_app(APP_FORCE_HTTPS="true", APP_HTTP_SCHEME="http")

        configure_scheme_middleware(app)

        # Check that https is used despite http_scheme="http"
        force_scheme_middlewares = [
            m for m in app.middlewares if isinstance(m, HTTPSchemeMiddleware)
        ]
        assert len(force_scheme_middlewares) == 1
        assert force_scheme_middlewares[0].scheme == "https"

        # Check that HSTS is still added
        hsts_middlewares = [m for m in app.middlewares if isinstance(m, HSTSMiddleware)]
        assert len(hsts_middlewares) == 1


class TestEndToEndScheme:
    """End-to-end tests with real application requests"""

    async def test_request_with_forced_https_scheme(self, monkeypatch):
        monkeypatch.setenv("APP_FORCE_HTTPS", "true")
        app = FakeApplication()
        configure_scheme_middleware(app)

        @app.router.get("/")
        async def home(request: Request):
            return Response(200, content=TextContent(request.scheme))

        await app.start()

        scope = get_example_scope("GET", "/", [])
        scope["scheme"] = "http"  # Original scheme

        await app(scope, MockReceive(), MockSend())

        assert app.response.status == 200
        # The handler should see https due to middleware
        assert b"https" in app.response.content.body

    async def test_request_with_forced_http_scheme(self, monkeypatch):
        monkeypatch.setenv("APP_HTTP_SCHEME", "http")
        app = FakeApplication()
        configure_scheme_middleware(app)

        @app.router.get("/")
        async def home(request: Request):
            return Response(200, content=TextContent(request.scheme))

        await app.start()

        scope = get_example_scope("GET", "/", [])
        scope["scheme"] = "https"  # Original scheme

        await app(scope, MockReceive(), MockSend())

        assert app.response.status == 200
        # The handler should see http due to middleware
        assert b"http" in app.response.content.body
