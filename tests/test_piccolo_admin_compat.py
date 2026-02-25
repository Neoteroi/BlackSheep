"""
Tests to verify that BlackSheep correctly mounts ASGI applications that follow
the ASGI spec for root_path / path handling — most notably Starlette-based apps
like Piccolo Admin.

Reference: https://github.com/piccolo-orm/piccolo_admin/issues/472
           https://github.com/Neoteroi/BlackSheep/issues/668

The ASGI spec says:
  - root_path: The root path this application is mounted at (same as SCRIPT_NAME
    in CGI). The parent (or reverse-proxy) sets this before calling the child.
  - path: The HTTP request target, excluding query string. It MUST NOT be
    modified by the parent when forwarding to a mounted child.
  - raw_path: The original byte-string of the path. Same rule — left intact.

The child app is responsible for deriving its own application-relative path by
stripping root_path from path.
"""
import re
import pytest

from blacksheep.testing.helpers import get_example_scope
from blacksheep.testing.messages import MockReceive, MockSend
from tests.utils.application import FakeApplication

from starlette.applications import Starlette
from starlette.responses import HTMLResponse, PlainTextResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

# ---------------------------------------------------------------------------
# Tests: real Starlette (required dependency)
#
# Piccolo Admin is a Starlette/FastAPI app that internally mounts sub-apps:
#   /           → serves index.html (login page)
#   /assets/*   → StaticFiles serving index-XXX.js, index-XXX.css, etc.
#   /api/*      → REST endpoints (auth-protected)
#   /public/*   → public endpoints (login, translations, meta)
#
# The bug in issue #472 was: the login page HTML loaded fine, but the
# <script> and <link> tags referencing /admin/assets/... returned 404
# because BlackSheep was mangling scope["path"] and scope["raw_path"]
# before forwarding to the child Starlette app.  The child app (and its
# nested StaticFiles mount) needs the original full path so it can strip
# root_path itself and route internally.
# ---------------------------------------------------------------------------


@pytest.fixture
def starlette_admin_like_app(tmp_path):
    """
    Build a Starlette app that mimics Piccolo Admin's structure:
    root serves HTML referencing ./assets/*, with a StaticFiles sub-mount.
    """
    # Create fake static assets on disk
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir()
    (assets_dir / "index-abc123.js").write_text("console.log('admin');")
    (assets_dir / "index-abc123.css").write_text("body{margin:0}")

    async def admin_root(request):
        return HTMLResponse(
            '<html><head>'
            '<link rel="stylesheet" href="./assets/index-abc123.css">'
            '</head><body>'
            '<script src="./assets/index-abc123.js"></script>'
            '</body></html>'
        )

    async def login_endpoint(request):
        return PlainTextResponse("login page")

    async def public_meta(request):
        return PlainTextResponse("meta ok")

    app = Starlette(
        routes=[
            Route("/", admin_root),
            Route("/login/", login_endpoint),
            Mount("/assets", app=StaticFiles(directory=str(assets_dir))),
            Mount(
                "/public",
                routes=[Route("/meta/", public_meta)],
            ),
        ],
    )
    return app


@pytest.mark.asyncio
async def test_real_starlette_app_mounted_root(starlette_admin_like_app):
    """GET /admin/ → Starlette root route returns 200."""
    parent = FakeApplication()
    parent.mount("/admin", starlette_admin_like_app)
    await parent.start()

    scope = get_example_scope("GET", "/admin/")
    mock_send = MockSend()
    await parent(scope, MockReceive(), mock_send)

    assert mock_send.messages[0]["status"] == 200
    body = mock_send.messages[1]["body"]
    assert b"index-abc123.js" in body


@pytest.mark.asyncio
async def test_real_starlette_app_mounted_static_js(starlette_admin_like_app):
    """
    GET /admin/assets/index-abc123.js → must return 200.
    This is the exact failure mode from piccolo_admin#472: the login page
    HTML loads, but browser requests for JS/CSS assets get 404.
    """
    parent = FakeApplication()
    parent.mount("/admin", starlette_admin_like_app)
    await parent.start()

    scope = get_example_scope("GET", "/admin/assets/index-abc123.js")
    mock_send = MockSend()
    await parent(scope, MockReceive(), mock_send)

    start = mock_send.messages[0]
    assert start["status"] == 200, (
        f"Expected 200 for /admin/assets/index-abc123.js, got {start['status']}. "
        "This indicates a regression in ASGI scope handling for nested mounts "
        "(ref: piccolo-orm/piccolo_admin#472)."
    )


@pytest.mark.asyncio
async def test_real_starlette_app_mounted_static_css(starlette_admin_like_app):
    """GET /admin/assets/index-abc123.css → must return 200."""
    parent = FakeApplication()
    parent.mount("/admin", starlette_admin_like_app)
    await parent.start()

    scope = get_example_scope("GET", "/admin/assets/index-abc123.css")
    mock_send = MockSend()
    await parent(scope, MockReceive(), mock_send)

    assert mock_send.messages[0]["status"] == 200


@pytest.mark.asyncio
async def test_real_starlette_app_mounted_sub_route(starlette_admin_like_app):
    """GET /admin/login/ → Starlette sub-route returns 200."""
    parent = FakeApplication()
    parent.mount("/admin", starlette_admin_like_app)
    await parent.start()

    scope = get_example_scope("GET", "/admin/login/")
    mock_send = MockSend()
    await parent(scope, MockReceive(), mock_send)

    assert mock_send.messages[0]["status"] == 200
    assert mock_send.messages[1]["body"] == b"login page"


@pytest.mark.asyncio
async def test_real_starlette_app_mounted_nested_mount(starlette_admin_like_app):
    """GET /admin/public/meta/ → nested Starlette Mount returns 200."""
    parent = FakeApplication()
    parent.mount("/admin", starlette_admin_like_app)
    await parent.start()

    scope = get_example_scope("GET", "/admin/public/meta/")
    mock_send = MockSend()
    await parent(scope, MockReceive(), mock_send)

    assert mock_send.messages[0]["status"] == 200
    assert mock_send.messages[1]["body"] == b"meta ok"


@pytest.mark.asyncio
async def test_real_starlette_app_mounted_nonexistent_asset(
    starlette_admin_like_app,
):
    """GET /admin/assets/does-not-exist.js → 404 from StaticFiles (not crash)."""
    parent = FakeApplication()
    parent.mount("/admin", starlette_admin_like_app)
    await parent.start()

    scope = get_example_scope("GET", "/admin/assets/does-not-exist.js")
    mock_send = MockSend()
    await parent(scope, MockReceive(), mock_send)

    assert mock_send.messages[0]["status"] in (404, 405)


# ---------------------------------------------------------------------------
# Tests: optional Piccolo Admin (if installed)
# ---------------------------------------------------------------------------

try:
    from piccolo_admin.endpoints import create_admin

    _has_piccolo_admin = True
except ImportError:
    _has_piccolo_admin = False


@pytest.mark.asyncio
@pytest.mark.skipif(not _has_piccolo_admin, reason="piccolo_admin not installed")
async def test_piccolo_admin_mounted_serves_login_page():
    """
    Mount the real Piccolo Admin ASGI app and verify that the login page
    is served (returns 200) rather than a 404 or crash.

    This is the exact scenario reported in:
    https://github.com/piccolo-orm/piccolo_admin/issues/472
    """
    admin_app = create_admin(tables=[])

    parent = FakeApplication()
    parent.mount("/admin", admin_app)
    await parent.start()

    scope = get_example_scope("GET", "/admin/")
    mock_send = MockSend()
    await parent(scope, MockReceive(), mock_send)

    start = mock_send.messages[0]
    assert start["status"] == 200, (
        f"Expected 200 from Piccolo Admin at /admin/, got {start['status']}. "
        "This may indicate a regression in ASGI scope handling for mounted apps."
    )

    body = b""
    for msg in mock_send.messages:
        if msg.get("type") == "http.response.body":
            body += msg.get("body", b"")
    html_text = body.decode("utf-8", errors="replace")

    asset_paths = re.findall(r'(?:src|href)="\.(/assets/[^"]+)"', html_text)
    assert asset_paths, (
        "Could not find any asset references in Piccolo Admin HTML. "
        "The HTML template may have changed."
    )
    for asset_path in asset_paths:
        full_path = f"/admin{asset_path}"
        asset_scope = get_example_scope("GET", full_path)
        asset_send = MockSend()
        await parent(asset_scope, MockReceive(), asset_send)
        asset_start = asset_send.messages[0]
        assert asset_start["status"] == 200, (
            f"Expected 200 for {full_path}, got {asset_start['status']}. "
            "Static assets under mounted Piccolo Admin are broken."
        )
