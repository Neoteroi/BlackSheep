import pytest

from blacksheep.messages import Request
from blacksheep.server.redirects import (
    default_trailing_slash_exclude,
    get_trailing_slash_middleware,
)
from blacksheep.server.responses import text


class TestDefaultTrailingSlashExclude:
    def test_excludes_api_paths(self):
        assert default_trailing_slash_exclude("/api/users") is True
        assert default_trailing_slash_exclude("/api/") is True
        assert default_trailing_slash_exclude("/v1/api/endpoint") is True

    def test_does_not_exclude_non_api_paths(self):
        assert default_trailing_slash_exclude("/home") is False
        assert default_trailing_slash_exclude("/about") is False
        assert default_trailing_slash_exclude("/") is False


class TestTrailingSlashMiddleware:
    @pytest.mark.asyncio
    async def test_redirects_path_without_trailing_slash(self):
        middleware = get_trailing_slash_middleware()
        request = Request("GET", b"/home", [])

        async def handler(req):
            return text("OK")

        response = await middleware(request, handler)

        assert response.status == 301
        assert response.headers.get_single(b"Location") == b"/home/"

    @pytest.mark.asyncio
    async def test_does_not_redirect_path_with_trailing_slash(self):
        middleware = get_trailing_slash_middleware()
        request = Request("GET", b"/home/", [])

        async def handler(req):
            return text("OK")

        response = await middleware(request, handler)

        assert response.status == 200

    @pytest.mark.asyncio
    async def test_does_not_redirect_paths_with_file_extensions(self):
        middleware = get_trailing_slash_middleware()
        request = Request("GET", b"/style.css", [])

        async def handler(req):
            return text("OK")

        response = await middleware(request, handler)

        assert response.status == 200

    @pytest.mark.asyncio
    async def test_does_not_redirect_paths_with_file_extensions_in_subdirs(self):
        middleware = get_trailing_slash_middleware()
        request = Request("GET", b"/assets/script.js", [])

        async def handler(req):
            return text("OK")

        response = await middleware(request, handler)

        assert response.status == 200

    @pytest.mark.asyncio
    async def test_excludes_api_paths_by_default(self):
        middleware = get_trailing_slash_middleware()
        request = Request("GET", b"/api/users", [])

        async def handler(req):
            return text("OK")

        response = await middleware(request, handler)

        assert response.status == 200

    @pytest.mark.asyncio
    async def test_custom_exclude_function(self):
        def custom_exclude(path: str) -> bool:
            return path.startswith("/admin")

        middleware = get_trailing_slash_middleware(exclude=custom_exclude)
        request = Request("GET", b"/admin/dashboard", [])

        async def handler(req):
            return text("OK")

        response = await middleware(request, handler)

        assert response.status == 200

    @pytest.mark.asyncio
    async def test_custom_exclude_does_not_affect_other_paths(self):
        def custom_exclude(path: str) -> bool:
            return path.startswith("/admin")

        middleware = get_trailing_slash_middleware(exclude=custom_exclude)
        request = Request("GET", b"/home", [])

        async def handler(req):
            return text("OK")

        response = await middleware(request, handler)

        assert response.status == 301
        assert response.headers.get_single(b"Location") == b"/home/"

    @pytest.mark.asyncio
    async def test_none_exclude_disables_exclusion(self):
        middleware = get_trailing_slash_middleware(exclude=lambda x: False)
        request = Request("GET", b"/api/users", [])

        async def handler(req):
            return text("OK")

        response = await middleware(request, handler)

        assert response.status == 301
        assert response.headers.get_single(b"Location") == b"/api/users/"

    @pytest.mark.asyncio
    async def test_handles_root_path(self):
        middleware = get_trailing_slash_middleware()
        request = Request("GET", b"/", [])

        async def handler(req):
            return text("OK")

        response = await middleware(request, handler)

        assert response.status == 200

    @pytest.mark.asyncio
    async def test_normalizes_path_with_leading_slashes(self):
        middleware = get_trailing_slash_middleware()
        request = Request("GET", b"/home", [])

        async def handler(req):
            return text("OK")

        response = await middleware(request, handler)

        assert response.status == 301
        assert response.headers.get_single(b"Location") == b"/home/"

    @pytest.mark.asyncio
    async def test_nested_paths_without_trailing_slash(self):
        middleware = get_trailing_slash_middleware()
        request = Request("GET", b"/about/team", [])

        async def handler(req):
            return text("OK")

        response = await middleware(request, handler)

        assert response.status == 301
        assert response.headers.get_single(b"Location") == b"/about/team/"
