from ipaddress import ip_address, ip_network

import pytest

from blacksheep.server.remotes.forwarding import (
    ForwardedHeaderEntry,
    ForwardedHeadersMiddleware,
    XForwardedHeadersMiddleware,
    parse_forwarded_header,
)
from blacksheep.server.remotes.hosts import TrustedHostsMiddleware
from blacksheep.testing.helpers import get_example_scope
from blacksheep.testing.messages import MockReceive, MockSend
from tests.utils.application import FakeApplication


@pytest.mark.parametrize(
    "forwarded_host,forwarded_ip,forwarded_proto",
    [
        (b"neoteroi.dev", b"203.0.113.195", b"https"),
        (b"id42.example-cdn.com", b"2001:db8:85a3:8d3:1319:8a2e:370:7348", b"http"),
    ],
)
async def test_x_forwarded_headers_middleware(
    app: FakeApplication,
    forwarded_host,
    forwarded_ip,
    forwarded_proto,
):
    app.middlewares.append(XForwardedHeadersMiddleware())

    @app.router.get("/")
    async def home(request):
        return

    scope = get_example_scope(
        "GET",
        "/",
        extra_headers=[
            (b"X-Forwarded-Host", forwarded_host),
            (b"X-Forwarded-For", forwarded_ip),
            (b"X-Forwarded-Proto", forwarded_proto),
        ],
    )

    assert scope["scheme"] == "http"
    assert dict(scope["headers"])[b"host"] != forwarded_host

    await app(scope, MockReceive(), MockSend())

    last_request = app.request
    assert last_request is not None
    assert app.response is not None
    assert app.response.status == 204

    # the request is updated to reflect X-Forwarded information
    assert last_request.host == forwarded_host.decode()
    assert last_request.scheme == forwarded_proto.decode()
    assert last_request.original_client_ip == forwarded_ip.decode()


async def test_x_forwarded_headers_middleware_multiple_proxies(app: FakeApplication):
    app.middlewares.append(
        XForwardedHeadersMiddleware(
            forward_limit=3,
            known_proxies=[
                ip_address("127.0.0.1"),
                ip_address("203.0.113.196"),
                ip_address("203.0.113.197"),
            ],
        )
    )

    @app.router.get("/")
    async def home(request):
        return

    scope = get_example_scope(
        "GET",
        "/",
        extra_headers=[
            (b"X-Forwarded-Host", b"neoteroi.dev"),
            (b"X-Forwarded-For", b"203.0.113.195"),
            (b"X-Forwarded-Proto", b"https"),
        ],
    )

    await app(scope, MockReceive(), MockSend())

    last_request = app.request
    assert last_request is not None
    assert app.response is not None
    assert app.response.status == 204

    # the request is updated to reflect X-Forwarded information
    assert last_request.host == "neoteroi.dev"
    assert last_request.scheme == "https"
    assert last_request.original_client_ip == "203.0.113.195"

    scope = get_example_scope(
        "GET",
        "/",
        extra_headers=[
            (b"X-Forwarded-Host", b"neoteroi.dev"),
            (b"X-Forwarded-For", b"203.0.113.195,203.0.113.196,203.0.113.197"),
            (b"X-Forwarded-Proto", b"https,http,http"),
        ],
    )

    assert scope["scheme"] == "http"
    assert dict(scope["headers"])[b"host"] != b"neoteroi.dev"

    await app(scope, MockReceive(), MockSend())

    last_request = app.request
    assert last_request is not None
    assert app.response is not None
    assert app.response.status == 204

    # the request is updated to reflect X-Forwarded information
    assert last_request.host == "neoteroi.dev"
    assert last_request.scheme == "https"
    assert last_request.original_client_ip == "203.0.113.195"


async def test_x_forwarded_headers_middleware_blocks_invalid_host(app: FakeApplication):
    app.middlewares.append(XForwardedHeadersMiddleware(allowed_hosts=["neoteroi.dev"]))

    called = False

    @app.router.get("/")
    async def home(request):
        nonlocal called
        called = True
        return

    scope = get_example_scope(
        "GET",
        "/",
        extra_headers=[
            (b"X-Forwarded-Host", b"ugly-domain.dev"),
            (b"X-Forwarded-For", b"203.0.113.195"),
            (b"X-Forwarded-Proto", b"https"),
        ],
    )

    assert scope["scheme"] == "http"
    assert dict(scope["headers"])[b"host"] != b"neoteroi.dev"

    await app(scope, MockReceive(), MockSend())

    assert app.response is not None
    assert app.response.status == 400

    assert not called

    scope = get_example_scope(
        "GET",
        "/",
        extra_headers=[
            (b"X-Forwarded-Host", b"neoteroi.dev"),
            (b"X-Forwarded-For", b"203.0.113.195"),
            (b"X-Forwarded-Proto", b"https"),
        ],
    )

    assert scope["scheme"] == "http"
    assert dict(scope["headers"])[b"host"] != b"neoteroi.dev"

    await app(scope, MockReceive(), MockSend())

    assert app.response is not None
    assert app.response.status == 204

    assert called


async def test_x_forwarded_headers_middleware_without_forwarded_for(
    app: FakeApplication,
):
    app.middlewares.append(XForwardedHeadersMiddleware(allowed_hosts=["neoteroi.dev"]))

    called = False

    @app.router.get("/")
    async def home(request):
        nonlocal called
        called = True
        return

    scope = get_example_scope(
        "GET",
        "/",
        extra_headers=[
            (b"X-Forwarded-Host", b"neoteroi.dev"),
        ],
    )

    await app(scope, MockReceive(), MockSend())

    assert app.response is not None
    assert app.response.status == 204


async def test_x_forwarded_headers_middleware_without_forwarded_proto(
    app: FakeApplication,
):
    app.middlewares.append(XForwardedHeadersMiddleware(allowed_hosts=["neoteroi.dev"]))

    called = False

    @app.router.get("/")
    async def home(request):
        nonlocal called
        called = True
        return

    scope = get_example_scope(
        "GET",
        "/",
        extra_headers=[
            (b"X-Forwarded-Host", b"neoteroi.dev"),
            (b"X-Forwarded-For", b"203.0.113.195"),
        ],
    )

    await app(scope, MockReceive(), MockSend())

    assert app.response is not None
    assert app.response.status == 204


async def test_x_forwarded_headers_middleware_blocks_too_many_forwards(
    app: FakeApplication,
):
    app.middlewares.append(XForwardedHeadersMiddleware(allowed_hosts=["neoteroi.dev"]))

    called = False

    @app.router.get("/")
    async def home(request):
        nonlocal called
        called = True
        return

    scope = get_example_scope(
        "GET",
        "/",
        extra_headers=[
            (b"X-Forwarded-Host", b"neoteroi.dev"),
            (b"X-Forwarded-For", b"203.0.113.195,203.0.113.196"),
        ],
    )

    await app(scope, MockReceive(), MockSend())

    assert app.response is not None
    assert app.response.status == 400


async def test_x_forwarded_headers_middleware_blocks_multiple_forwarded_host_headers(
    app: FakeApplication,
):
    app.middlewares.append(XForwardedHeadersMiddleware(allowed_hosts=["neoteroi.dev"]))

    called = False

    @app.router.get("/")
    async def home(request):
        nonlocal called
        called = True
        return

    scope = get_example_scope(
        "GET",
        "/",
        extra_headers=[
            (b"X-Forwarded-Host", b"neoteroi.dev"),
            (b"X-Forwarded-Host", b"neoteroi.dev"),
            (b"X-Forwarded-For", b"203.0.113.195"),
            (b"X-Forwarded-Proto", b"https"),
        ],
    )

    assert scope["scheme"] == "http"
    assert dict(scope["headers"])[b"host"] != b"neoteroi.dev"

    await app(scope, MockReceive(), MockSend())

    assert app.response is not None
    assert app.response.status == 400


async def test_x_forwarded_headers_middleware_blocks_multiple_forwarded_proto_headers(
    app: FakeApplication,
):
    app.middlewares.append(XForwardedHeadersMiddleware(allowed_hosts=["neoteroi.dev"]))

    called = False

    @app.router.get("/")
    async def home(request):
        nonlocal called
        called = True
        return

    scope = get_example_scope(
        "GET",
        "/",
        extra_headers=[
            (b"X-Forwarded-Host", b"neoteroi.dev"),
            (b"X-Forwarded-For", b"203.0.113.195"),
            (b"X-Forwarded-Proto", b"https"),
            (b"X-Forwarded-Proto", b"http"),
        ],
    )

    await app(scope, MockReceive(), MockSend())

    assert app.response is not None
    assert app.response.status == 400


async def test_x_forwarded_headers_middleware_blocks_multiple_forwarded_proto_values(
    app: FakeApplication,
):
    app.middlewares.append(XForwardedHeadersMiddleware(allowed_hosts=["neoteroi.dev"]))

    called = False

    @app.router.get("/")
    async def home(request):
        nonlocal called
        called = True
        return

    scope = get_example_scope(
        "GET",
        "/",
        extra_headers=[
            (b"X-Forwarded-Host", b"neoteroi.dev"),
            (b"X-Forwarded-For", b"203.0.113.195"),
            (b"X-Forwarded-Proto", b"https,http"),
        ],
    )

    await app(scope, MockReceive(), MockSend())

    assert app.response is not None
    assert app.response.status == 400


async def test_x_forwarded_headers_middleware_blocks_multiple_forwarded_for_headers(
    app: FakeApplication,
):
    app.middlewares.append(XForwardedHeadersMiddleware(allowed_hosts=["neoteroi.dev"]))

    called = False

    @app.router.get("/")
    async def home(request):
        nonlocal called
        called = True
        return

    scope = get_example_scope(
        "GET",
        "/",
        extra_headers=[
            (b"X-Forwarded-For", b"203.0.113.195,203.0.113.196"),
            (b"X-Forwarded-For", b"203.0.113.195"),
        ],
    )

    assert scope["scheme"] == "http"
    assert dict(scope["headers"])[b"host"] != b"neoteroi.dev"

    await app(scope, MockReceive(), MockSend())

    assert app.response is not None
    assert app.response.status == 400


async def test_x_forwarded_headers_middleware_blocks_too_many_forward_values(
    app: FakeApplication,
):
    app.middlewares.append(XForwardedHeadersMiddleware(allowed_hosts=["neoteroi.dev"]))

    called = False

    @app.router.get("/")
    async def home(request):
        nonlocal called
        called = True
        return

    scope = get_example_scope(
        "GET",
        "/",
        extra_headers=[
            (b"X-Forwarded-For", b"203.0.113.195,203.0.113.196"),
            (b"X-Forwarded-Proto", b"https"),
        ],
    )

    assert scope["scheme"] == "http"
    assert dict(scope["headers"])[b"host"] != b"neoteroi.dev"

    await app(scope, MockReceive(), MockSend())

    assert app.response is not None
    assert app.response.status == 400


async def test_x_forwarded_headers_middleware_blocks_invalid_host_not_forwarded(
    app: FakeApplication,
):
    app.middlewares.append(XForwardedHeadersMiddleware(allowed_hosts=["neoteroi.dev"]))

    called = False

    @app.router.get("/")
    async def home(request):
        nonlocal called
        called = True
        return

    scope = get_example_scope(
        "GET",
        "/",
        extra_headers=[
            (b"X-Forwarded-For", b"203.0.113.195"),
            (b"X-Forwarded-Proto", b"https"),
        ],
    )

    assert scope["scheme"] == "http"
    assert dict(scope["headers"])[b"host"] != b"neoteroi.dev"

    await app(scope, MockReceive(), MockSend())

    assert app.response is not None
    assert app.response.status == 400


async def test_x_forwarded_headers_middleware_blocks_invalid_proxy_id(
    app: FakeApplication,
):
    app.middlewares.append(
        XForwardedHeadersMiddleware(known_proxies=[ip_address("185.152.122.103")])
    )

    called = False

    @app.router.get("/")
    async def home(request):
        nonlocal called
        called = True
        return

    scope = get_example_scope(
        "GET",
        "/",
        extra_headers=[
            (b"X-Forwarded-Host", b"neoteroi.dev"),
            (b"X-Forwarded-For", b"203.0.113.195"),
            (b"X-Forwarded-Proto", b"https"),
        ],
    )

    assert scope["scheme"] == "http"
    assert dict(scope["headers"])[b"host"] != b"neoteroi.dev"

    await app(scope, MockReceive(), MockSend())

    assert app.response is not None
    assert app.response.status == 400

    assert not called

    scope = get_example_scope(
        "GET",
        "/",
        extra_headers=[
            (b"X-Forwarded-Host", b"neoteroi.dev"),
            (b"X-Forwarded-For", b"203.0.113.195"),
            (b"X-Forwarded-Proto", b"https"),
        ],
        client=("185.152.122.103", 443),
    )

    assert scope["scheme"] == "http"
    assert dict(scope["headers"])[b"host"] != b"neoteroi.dev"

    await app(scope, MockReceive(), MockSend())

    assert app.response is not None
    assert app.response.status == 204

    assert called


async def test_x_forwarded_headers_middleware_blocks_invalid_proxy_id_by_network(
    app: FakeApplication,
):
    app.middlewares.append(
        XForwardedHeadersMiddleware(known_networks=[ip_network("192.168.0.0/24")])
    )

    called = False

    @app.router.get("/")
    async def home(request):
        nonlocal called
        called = True
        return

    scope = get_example_scope(
        "GET",
        "/",
        extra_headers=[
            (b"X-Forwarded-Host", b"neoteroi.dev"),
            (b"X-Forwarded-For", b"203.0.113.195"),
            (b"X-Forwarded-Proto", b"https"),
        ],
        client=("203.0.113.196", 443),
    )

    assert scope["scheme"] == "http"
    assert dict(scope["headers"])[b"host"] != b"neoteroi.dev"

    await app(scope, MockReceive(), MockSend())

    assert app.response is not None
    assert app.response.status == 400

    assert not called

    scope = get_example_scope(
        "GET",
        "/",
        extra_headers=[
            (b"X-Forwarded-Host", b"neoteroi.dev"),
            (b"X-Forwarded-For", b"203.0.113.195"),
            (b"X-Forwarded-Proto", b"https"),
        ],
        client=("192.168.0.1", 443),
    )

    assert scope["scheme"] == "http"
    assert dict(scope["headers"])[b"host"] != b"neoteroi.dev"

    await app(scope, MockReceive(), MockSend())

    assert app.request is not None
    assert app.response is not None
    assert app.response.status == 204
    assert app.request.original_client_ip == "203.0.113.195"

    assert called


async def test_forwarded_header_middleware(app: FakeApplication):
    app.middlewares.append(ForwardedHeadersMiddleware(allowed_hosts=["neoteroi.dev"]))

    called = False

    @app.router.get("/")
    async def home(request):
        nonlocal called
        called = True
        return

    scope = get_example_scope(
        "GET",
        "/",
        extra_headers=[
            (
                b"Forwarded",
                b"for=_hidden;host=neoteroi.dev;proto=https",
            ),
        ],
    )

    await app(scope, MockReceive(), MockSend())

    assert app.response is not None
    assert app.response.status == 204

    assert app.request is not None
    assert app.request.host == "neoteroi.dev"
    assert app.request.original_client_ip == "_hidden"
    assert app.request.scheme == "https"


async def test_forwarded_header_middleware_by_invalid(app: FakeApplication):
    app.middlewares.append(ForwardedHeadersMiddleware(allowed_hosts=["neoteroi.dev"]))

    called = False

    @app.router.get("/")
    async def home(request):
        nonlocal called
        called = True
        return

    scope = get_example_scope(
        "GET",
        "/",
        extra_headers=[
            (
                b"Forwarded",
                b"for=_hidden;host=neoteroi.dev;proto=https;by=203.0.113.195",
            ),
        ],
    )

    await app(scope, MockReceive(), MockSend())

    assert app.response is not None
    assert app.response.status == 400


async def test_forwarded_header_middleware_by_hidden(app: FakeApplication):
    app.middlewares.append(ForwardedHeadersMiddleware(allowed_hosts=["neoteroi.dev"]))

    called = False

    @app.router.get("/")
    async def home(request):
        nonlocal called
        called = True
        return

    scope = get_example_scope(
        "GET",
        "/",
        extra_headers=[
            (
                b"Forwarded",
                b"for=_hidden;host=neoteroi.dev;proto=https;by=_hidden",
            ),
        ],
    )

    await app(scope, MockReceive(), MockSend())

    assert app.response is not None
    assert app.response.status == 204

    assert app.request is not None
    assert app.request.host == "neoteroi.dev"
    assert app.request.original_client_ip == "_hidden"
    assert app.request.scheme == "https"


async def test_forwarded_header_middleware_blocks_requests_with_too_many_forwards(
    app: FakeApplication,
):
    app.middlewares.append(ForwardedHeadersMiddleware(allowed_hosts=["neoteroi.dev"]))

    called = False

    @app.router.get("/")
    async def home(request):
        nonlocal called
        called = True
        return

    scope = get_example_scope(
        "GET",
        "/",
        extra_headers=[
            (
                b"Forwarded",
                b"for=_hidden,for=_hidden",
            ),
        ],
    )

    await app(scope, MockReceive(), MockSend())

    assert app.response is not None
    assert app.response.status == 400


def test_forwarded_entry_equality():
    a = ForwardedHeaderEntry(
        forwarded_for="203.0.113.195",
        forwarded_by="_proxy",
        forwarded_proto="https",
        forwarded_host="neoteroi.dev",
    )

    assert a == {
        "forwarded_for": "203.0.113.195",
        "forwarded_by": "_proxy",
        "forwarded_proto": "https",
        "forwarded_host": "neoteroi.dev",
    }

    assert a == ForwardedHeaderEntry(
        forwarded_for="203.0.113.195",
        forwarded_by="_proxy",
        forwarded_proto="https",
        forwarded_host="neoteroi.dev",
    )

    assert a != ForwardedHeaderEntry(
        forwarded_for="_hidden",
        forwarded_by="_proxy",
        forwarded_proto="https",
        forwarded_host="neoteroi.dev",
    )

    assert a != 2


@pytest.mark.parametrize(
    "value,expected_result",
    [
        (
            "host=neoteroi.dev;for=203.0.113.195;proto=https;by=_secret",
            ForwardedHeaderEntry(
                forwarded_for="203.0.113.195",
                forwarded_by="_secret",
                forwarded_proto="https",
                forwarded_host="neoteroi.dev",
            ),
        ),
        (
            "host=neoteroi.dev",
            ForwardedHeaderEntry(
                forwarded_for="",
                forwarded_by="",
                forwarded_proto="",
                forwarded_host="neoteroi.dev",
            ),
        ),
        (
            "host=neoteroi.dev;proto=https",
            ForwardedHeaderEntry(
                forwarded_for="",
                forwarded_by="",
                forwarded_proto="https",
                forwarded_host="neoteroi.dev",
            ),
        ),
    ],
)
def test_parse_forwarded_entry(value, expected_result):
    parsed = next(iter(parse_forwarded_header(value)), None)
    assert parsed == expected_result


async def test_trusted_hosts_middleware_blocks_invalid_host(app: FakeApplication):
    app.middlewares.append(TrustedHostsMiddleware(["neoteroi.dev"]))

    called = False

    @app.router.get("/")
    async def home(request):
        nonlocal called
        called = True
        return

    scope = get_example_scope("GET", "/", server=("ugly-domain.dev", 80))

    await app(scope, MockReceive(), MockSend())

    assert app.response is not None
    assert app.response.status == 400

    assert not called

    scope = get_example_scope("GET", "/", server=("neoteroi.dev", 80))

    await app(scope, MockReceive(), MockSend())

    assert app.response is not None
    assert app.response.status == 204

    assert called
