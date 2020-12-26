import pytest
from blacksheep.server.cors import CORSPolicy, cors
from blacksheep.server.responses import text

from .test_application import FakeApplication, MockReceive, MockSend, get_example_scope


def test_cors_policy():
    policy = CORSPolicy(
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization"],
        allow_origins=["http://localhost:44555"],
    )
    assert policy.allow_methods == {"GET", "POST", "DELETE"}
    assert policy.allow_headers == {"authorization"}
    assert policy.allow_origins == {"http://localhost:44555"}


def test_cors_policy_setters_strings():
    policy = CORSPolicy()

    policy.allow_methods = "get delete"
    assert policy.allow_methods == {"GET", "DELETE"}

    policy.allow_methods = "GET POST PATCH"
    assert policy.allow_methods == {"GET", "POST", "PATCH"}

    policy.allow_methods = "GET, POST, PATCH"
    assert policy.allow_methods == {"GET", "POST", "PATCH"}

    policy.allow_methods = "GET,POST,PATCH"
    assert policy.allow_methods == {"GET", "POST", "PATCH"}

    policy.allow_methods = "GET;POST;PATCH"
    assert policy.allow_methods == {"GET", "POST", "PATCH"}

    for value in {"X-Foo Authorization", "X-Foo, Authorization", "X-Foo,Authorization"}:
        policy.allow_headers = value
        assert policy.allow_headers == {"x-foo", "authorization"}

    policy.allow_origins = "http://Example.com https://Bezkitu.ORG"
    assert policy.allow_origins == {"http://example.com", "https://bezkitu.org"}

    policy.allow_headers = None
    assert policy.allow_headers == frozenset()

    policy.allow_methods = None
    assert policy.allow_methods == frozenset()

    policy.allow_origins = None
    assert policy.allow_origins == frozenset()


def test_cors_policy_setters_force_case():
    policy = CORSPolicy()

    policy.allow_methods = ["get", "delete"]
    assert policy.allow_methods == {"GET", "DELETE"}

    policy.allow_headers = ["X-Foo", "Authorization"]
    assert policy.allow_headers == {"x-foo", "authorization"}

    policy.allow_origins = ["http://Example.com", "https://Bezkitu.ORG"]
    assert policy.allow_origins == {"http://example.com", "https://bezkitu.org"}


def test_cors_policy_allow_all_methods():
    policy = CORSPolicy()

    assert policy.allow_headers == set()
    policy.allow_any_header()
    assert policy.allow_headers == {"*"}

    assert policy.allow_methods == set()
    policy.allow_any_method()
    assert policy.allow_methods == {"*"}

    assert policy.allow_origins == set()
    policy.allow_any_origin()
    assert policy.allow_origins == {"*"}


def test_cors_policy_raises_for_negative_max_age():
    with pytest.raises(ValueError):
        CORSPolicy(max_age=-1)

    policy = CORSPolicy()
    with pytest.raises(ValueError):
        policy.max_age = -5


@pytest.mark.asyncio
async def test_cors_request():
    app = FakeApplication()

    app.use_cors(
        allow_methods="GET POST DELETE", allow_origins="https://www.neoteroi.dev"
    )

    @app.router.get("/")
    async def home():
        return text("Hello, World")

    @app.router.put("/")
    async def put_something():
        ...

    await app.start()

    await app(
        get_example_scope("GET", "/", [(b"Origin", b"https://www.something-else.dev")]),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 400
    assert (
        response.headers.get_single(b"CORS-Error")
        == b"The origin of the request is not enabled by CORS rules."
    )

    await app(
        get_example_scope("PUT", "/", [(b"Origin", b"https://www.neoteroi.dev")]),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 400
    assert (
        response.headers.get_single(b"CORS-Error")
        == b"The method of the request is not enabled by CORS rules."
    )

    for headers in ([], [(b"Origin", b"https://www.neoteroi.dev")]):
        await app(
            get_example_scope("GET", "/", headers),
            MockReceive(),
            MockSend(),
        )

        response = app.response
        assert response.status == 200
        assert response.content.body == b"Hello, World"


@pytest.mark.asyncio
async def test_cors_preflight_request():
    app = FakeApplication()

    app.use_cors(allow_methods="GET POST", allow_origins="https://www.neoteroi.dev")

    @app.router.get("/")
    async def home():
        return text("Hello, World")

    await app.start()

    await app(
        get_example_scope(
            "OPTIONS",
            "/",
            [
                (b"Origin", b"https://www.neoteroi.dev"),
                (b"Access-Control-Request-Method", b"POST"),
            ],
        ),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 200
    assert set(
        response.headers.get_single(b"Access-Control-Allow-Methods").split(b", ")
    ) == {b"GET", b"POST"}
    assert (
        response.headers.get_single(b"Access-Control-Allow-Origin")
        == b"https://www.neoteroi.dev"
    )

    await app(
        get_example_scope(
            "OPTIONS",
            "/",
            [
                (b"Origin", b"https://www.neoteroi.dev"),
                (b"Access-Control-Request-Method", b"DELETE"),
            ],
        ),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 400
    assert (
        response.headers.get_single(b"CORS-Error")
        == b"The method of the request is not enabled by CORS rules."
    )


@pytest.mark.asyncio
async def test_cors_preflight_request_allow_headers():
    app = FakeApplication()

    app.use_cors(
        allow_methods="GET POST",
        allow_origins="https://www.neoteroi.dev",
        allow_headers="Authorization credentials",
    )

    @app.router.get("/")
    async def home():
        return text("Hello, World")

    await app.start()

    await app(
        get_example_scope(
            "OPTIONS",
            "/",
            [
                (b"Origin", b"https://www.neoteroi.dev"),
                (b"Access-Control-Request-Method", b"POST"),
                (b"Access-Control-Request-Headers", b"Authorization"),
            ],
        ),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 200
    assert (
        response.headers.get_single(b"Access-Control-Allow-Headers") == b"Authorization"
    )

    await app(
        get_example_scope(
            "OPTIONS",
            "/",
            [
                (b"Origin", b"https://www.neoteroi.dev"),
                (b"Access-Control-Request-Method", b"POST"),
                (b"Access-Control-Request-Headers", b"Authorization, Credentials"),
            ],
        ),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 200
    assert set(
        response.headers.get_single(b"Access-Control-Allow-Headers").split(b", ")
    ) == {b"Authorization", b"Credentials"}

    await app(
        get_example_scope(
            "OPTIONS",
            "/",
            [
                (b"Origin", b"https://www.neoteroi.dev"),
                (b"Access-Control-Request-Method", b"POST"),
                (b"Access-Control-Request-Headers", b"X-Foo"),
            ],
        ),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 400
    assert (
        response.headers.get_single(b"CORS-Error")
        == b'The "X-Foo" request header is not enabled by CORS rules.'
    )


@pytest.mark.asyncio
async def test_cors_preflight_request_allow_credentials():
    app = FakeApplication()

    app.use_cors(
        allow_methods="GET POST",
        allow_origins="https://www.neoteroi.dev",
        allow_credentials=True,
    )

    @app.router.get("/")
    async def home():
        return text("Hello, World")

    await app.start()

    await app(
        get_example_scope(
            "OPTIONS",
            "/",
            [
                (b"Origin", b"https://www.neoteroi.dev"),
                (b"Access-Control-Request-Method", b"POST"),
            ],
        ),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 200
    assert response.headers.get_single(b"Access-Control-Allow-Credentials") == b"true"


@pytest.mark.asyncio
async def test_cors_preflight_request_allow_any():
    app = FakeApplication()

    app.use_cors(allow_methods="*", allow_origins="*", allow_headers="*")

    @app.router.get("/")
    async def home():
        return text("Hello, World")

    await app.start()

    await app(
        get_example_scope(
            "OPTIONS",
            "/",
            [
                (b"Origin", b"https://www.neoteroi.dev"),
                (b"Access-Control-Request-Method", b"POST"),
            ],
        ),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 200
    assert response.headers.get_single(b"Access-Control-Allow-Methods") == b"*"
    assert response.headers.get_single(b"Access-Control-Allow-Origin") == b"*"

    await app(
        get_example_scope(
            "OPTIONS",
            "/",
            [
                (b"Origin", b"https://www.neoteroi.dev"),
                (b"Access-Control-Request-Method", b"POST"),
                (b"Access-Control-Request-Headers", b"X-Foo"),
            ],
        ),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 200
    assert response.headers.get_single(b"Access-Control-Allow-Headers") == b"X-Foo"

    await app(
        get_example_scope(
            "OPTIONS",
            "/",
            [
                (b"Origin", b"https://www.neoteroi.dev"),
                (b"Access-Control-Request-Method", b"POST"),
                (b"Access-Control-Request-Headers", b"X-Ufo X-Foo"),
            ],
        ),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 200
    assert (
        response.headers.get_single(b"Access-Control-Allow-Headers") == b"X-Ufo X-Foo"
    )


@pytest.mark.asyncio
async def test_non_cors_options_request():
    app = FakeApplication()

    app.use_cors(
        allow_methods="GET POST",
        allow_origins="https://www.neoteroi.dev",
        allow_credentials=True,
    )

    await app.start()

    await app(
        get_example_scope(
            "OPTIONS",
            "/",
            [],
        ),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 404


@pytest.mark.asyncio
async def test_use_cors_raises_for_started_app():
    app = FakeApplication()

    await app.start()

    with pytest.raises(RuntimeError):
        app.use_cors()

    await app.start()


@pytest.mark.asyncio
async def OFF_test_cors_by_handler():
    app = FakeApplication()

    app.use_cors(
        allow_methods="GET POST DELETE", allow_origins="https://www.neoteroi.dev"
    ).add(
        "specific",
        CORSPolicy(allow_methods="GET POST", allow_origins="https://www.neoteroi.xyz"),
    )

    @app.router.get("/")
    async def home():
        return text("Hello, World")

    @cors("specific")
    @app.router.get("/specific-rules")
    async def different_rules():
        return text("Specific")

    await app.start()

    await app(
        get_example_scope(
            "OPTIONS",
            "/",
            [
                (b"Origin", b"https://www.neoteroi.dev"),
                (b"Access-Control-Request-Method", b"POST"),
            ],
        ),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 200
    assert (
        response.headers.get_single(b"Access-Control-Allow-Origin")
        == b"https://www.neoteroi.dev"
    )
    assert set(
        response.headers.get_single(b"Access-Control-Allow-Methods").split(b", ")
    ) == {b"GET", b"POST", b"DELETE"}

    await app(
        get_example_scope(
            "OPTIONS",
            "/",
            [
                (b"Origin", b"https://www.neoteroi.xyz"),
                (b"Access-Control-Request-Method", b"POST"),
            ],
        ),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response.status == 200
    assert (
        response.headers.get_single(b"Access-Control-Allow-Origin")
        == b"https://www.neoteroi.xyz"
    )
    assert set(
        response.headers.get_single(b"Access-Control-Allow-Methods").split(b", ")
    ) == {b"GET", b"POST"}


# TODO: support more policies
# TODO: cleaner handling of polluting properties
