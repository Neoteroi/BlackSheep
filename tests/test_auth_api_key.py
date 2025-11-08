import pytest
from essentials.secrets import Secret
from guardpost import Identity

from blacksheep.server.authentication.apikey import (
    APIKey,
    APIKeyAuthentication,
    APIKeyLocation,
    APIKeysProvider,
)
from blacksheep.testing.helpers import get_example_scope
from blacksheep.testing.messages import MockReceive, MockSend
from tests.utils.application import FakeApplication


# Test fixtures
@pytest.fixture
def api_key():
    return APIKey(
        secret=Secret("test-api-key-123", direct_value=True),
        claims={"name": "Test User", "email": "test@example.com"},
        roles=["user", "reader"],
    )


@pytest.fixture
def admin_api_key():
    return APIKey(
        secret=Secret("admin-key-456", direct_value=True),
        claims={"name": "Admin User", "email": "admin@example.com"},
        roles=["admin", "user"],
    )


class MockAPIKeysProvider(APIKeysProvider):
    def __init__(self, keys: list[APIKey]):
        self._keys = keys

    async def get_keys(self) -> list[APIKey]:
        return self._keys


class FailingAPIKeysProvider(APIKeysProvider):
    async def get_keys(self) -> list[APIKey]:
        raise Exception("Database connection failed")


# APIKey tests
def test_api_key_creation():
    api_key = APIKey(
        secret=Secret("test-key", direct_value=True),
        claims={"custom": "claim"},
        roles=["user"],
    )

    assert api_key.claims == {"custom": "claim"}
    assert api_key.roles == ["user"]


def test_api_key_defaults():
    api_key = APIKey(secret=Secret("test-key", direct_value=True))

    assert api_key.claims == {}
    assert api_key.roles == []


def test_api_key_match_success():
    api_key = APIKey(secret=Secret("test-key", direct_value=True))

    assert api_key.match("test-key") is True
    assert api_key.match(Secret("test-key", direct_value=True)) is True


def test_api_key_match_failure():
    api_key = APIKey(secret=Secret("test-key", direct_value=True))

    assert api_key.match("wrong-key") is False
    assert api_key.match(Secret("wrong-key", direct_value=True)) is False


# APIKeyAuthentication creation tests
def test_api_key_authentication_creation_with_keys():
    api_key = APIKey(secret=Secret("test-key", direct_value=True))

    auth = APIKeyAuthentication(api_key, param_name="X-API-Key")
    assert auth.scheme == "APIKey"
    assert auth.param_name == "X-API-Key"
    assert auth.location == APIKeyLocation.HEADER


def test_api_key_authentication_creation_with_provider():
    provider = MockAPIKeysProvider([])
    auth = APIKeyAuthentication(param_name="X-API-Key", keys_provider=provider)
    assert auth._keys_provider is provider


def test_api_key_authentication_creation_with_custom_scheme():
    api_key = APIKey(secret=Secret("test-key", direct_value=True))

    auth = APIKeyAuthentication(api_key, param_name="X-API-Key", scheme="CustomAPI")
    assert auth.scheme == "CustomAPI"


def test_api_key_authentication_creation_with_query_location():
    api_key = APIKey(secret=Secret("test-key", direct_value=True))

    auth = APIKeyAuthentication(api_key, param_name="api_key", location="query")
    assert auth.location == APIKeyLocation.QUERY


def test_api_key_authentication_creation_with_cookie_location():
    api_key = APIKey(secret=Secret("test-key", direct_value=True))

    auth = APIKeyAuthentication(api_key, param_name="api_key", location="cookie")
    assert auth.location == APIKeyLocation.COOKIE


def test_api_key_authentication_creation_requires_keys_or_provider():
    with pytest.raises(
        ValueError, match="Either keys or keys_provider must be provided"
    ):
        APIKeyAuthentication(param_name="X-API-Key")


def test_api_key_authentication_creation_mutual_exclusivity():
    api_key = APIKey(secret=Secret("test-key", direct_value=True))
    provider = MockAPIKeysProvider([])

    with pytest.raises(
        ValueError, match="Cannot specify both static keys and a keys_provider"
    ):
        APIKeyAuthentication(api_key, param_name="X-API-Key", keys_provider=provider)


# Header authentication tests
async def test_api_key_authentication_header_success(app: FakeApplication, api_key):
    app.use_authentication().add(APIKeyAuthentication(api_key, param_name="X-API-Key"))

    identity: Identity | None = None

    @app.router.get("/")
    async def home(request):
        nonlocal identity
        identity = request.user
        return None

    await app.start()

    await app(
        get_example_scope(
            "GET",
            "/",
            extra_headers=[(b"X-API-Key", b"test-api-key-123")],
        ),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 204
    assert identity is not None
    assert identity.is_authenticated() is True
    assert identity["name"] == "Test User"
    assert identity["email"] == "test@example.com"
    assert identity["roles"] == ["user", "reader"]


async def test_api_key_authentication_header_no_header(app: FakeApplication, api_key):
    app.use_authentication().add(APIKeyAuthentication(api_key, param_name="X-API-Key"))

    identity: Identity | None = None

    @app.router.get("/")
    async def home(request):
        nonlocal identity
        identity = request.user
        return None

    await app.start()

    await app(get_example_scope("GET", "/"), MockReceive(), MockSend())

    assert app.response.status == 204
    assert identity is not None
    assert identity.is_authenticated() is False


async def test_api_key_authentication_header_wrong_key(app: FakeApplication, api_key):
    app.use_authentication().add(APIKeyAuthentication(api_key, param_name="X-API-Key"))

    identity: Identity | None = None

    @app.router.get("/")
    async def home(request):
        nonlocal identity
        identity = request.user
        return None

    await app.start()

    await app(
        get_example_scope(
            "GET",
            "/",
            extra_headers=[(b"X-API-Key", b"wrong-key")],
        ),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 204
    assert identity is not None
    assert identity.is_authenticated() is False


# Query parameter authentication tests
async def test_api_key_authentication_query_success(app: FakeApplication, api_key):
    app.use_authentication().add(
        APIKeyAuthentication(api_key, param_name="api_key", location="query")
    )

    identity: Identity | None = None

    @app.router.get("/")
    async def home(request):
        nonlocal identity
        identity = request.user
        return None

    await app.start()

    await app(
        get_example_scope("GET", "/", query="api_key=test-api-key-123"),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 204
    assert identity is not None
    assert identity.is_authenticated() is True
    assert identity["name"] == "Test User"


async def test_api_key_authentication_query_no_param(app: FakeApplication, api_key):
    app.use_authentication().add(
        APIKeyAuthentication(api_key, param_name="api_key", location="query")
    )

    identity: Identity | None = None

    @app.router.get("/")
    async def home(request):
        nonlocal identity
        identity = request.user
        return None

    await app.start()

    await app(get_example_scope("GET", "/"), MockReceive(), MockSend())

    assert app.response.status == 204
    assert identity is not None
    assert identity.is_authenticated() is False


async def test_api_key_authentication_query_wrong_key(app: FakeApplication, api_key):
    app.use_authentication().add(
        APIKeyAuthentication(api_key, param_name="api_key", location="query")
    )

    identity: Identity | None = None

    @app.router.get("/")
    async def home(request):
        nonlocal identity
        identity = request.user
        return None

    await app.start()

    await app(
        get_example_scope("GET", "/?api_key=wrong-key"),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 204
    assert identity is not None
    assert identity.is_authenticated() is False


# Cookie authentication tests
async def test_api_key_authentication_cookie_success(app: FakeApplication, api_key):
    app.use_authentication().add(
        APIKeyAuthentication(api_key, param_name="api_key", location="cookie")
    )

    identity: Identity | None = None

    @app.router.get("/")
    async def home(request):
        nonlocal identity
        identity = request.user
        return None

    await app.start()

    await app(
        get_example_scope(
            "GET",
            "/",
            extra_headers=[(b"Cookie", b"api_key=test-api-key-123")],
        ),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 204
    assert identity is not None
    assert identity.is_authenticated() is True
    assert identity["name"] == "Test User"


async def test_api_key_authentication_cookie_no_cookie(app: FakeApplication, api_key):
    app.use_authentication().add(
        APIKeyAuthentication(api_key, param_name="api_key", location="cookie")
    )

    identity: Identity | None = None

    @app.router.get("/")
    async def home(request):
        nonlocal identity
        identity = request.user
        return None

    await app.start()

    await app(get_example_scope("GET", "/"), MockReceive(), MockSend())

    assert app.response.status == 204
    assert identity is not None
    assert identity.is_authenticated() is False


async def test_api_key_authentication_cookie_wrong_key(app: FakeApplication, api_key):
    app.use_authentication().add(
        APIKeyAuthentication(api_key, param_name="api_key", location="cookie")
    )

    identity: Identity | None = None

    @app.router.get("/")
    async def home(request):
        nonlocal identity
        identity = request.user
        return None

    await app.start()

    await app(
        get_example_scope(
            "GET",
            "/",
            extra_headers=[(b"Cookie", b"api_key=wrong-key")],
        ),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 204
    assert identity is not None
    assert identity.is_authenticated() is False


# Multiple keys tests
async def test_api_key_authentication_multiple_keys(
    app: FakeApplication, api_key, admin_api_key
):
    app.use_authentication().add(
        APIKeyAuthentication(api_key, admin_api_key, param_name="X-API-Key")
    )

    identity: Identity | None = None

    @app.router.get("/")
    async def home(request):
        nonlocal identity
        identity = request.user
        return None

    await app.start()

    # Test with first key
    await app(
        get_example_scope(
            "GET",
            "/",
            extra_headers=[(b"X-API-Key", b"test-api-key-123")],
        ),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 204
    assert identity is not None
    assert identity["name"] == "Test User"
    assert "admin" not in identity["roles"]

    # Test with second key
    await app(
        get_example_scope(
            "GET",
            "/",
            extra_headers=[(b"X-API-Key", b"admin-key-456")],
        ),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 204
    assert identity is not None
    assert identity["name"] == "Admin User"
    assert "admin" in identity["roles"]


# Provider tests
async def test_api_key_authentication_with_provider(app: FakeApplication, api_key):
    provider = MockAPIKeysProvider([api_key])
    app.use_authentication().add(
        APIKeyAuthentication(param_name="X-API-Key", keys_provider=provider)
    )

    identity: Identity | None = None

    @app.router.get("/")
    async def home(request):
        nonlocal identity
        identity = request.user
        return None

    await app.start()

    await app(
        get_example_scope(
            "GET",
            "/",
            extra_headers=[(b"X-API-Key", b"test-api-key-123")],
        ),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 204
    assert identity is not None
    assert identity.is_authenticated() is True
    assert identity["name"] == "Test User"


async def test_api_key_authentication_with_empty_provider(app: FakeApplication):
    provider = MockAPIKeysProvider([])
    app.use_authentication().add(
        APIKeyAuthentication(param_name="X-API-Key", keys_provider=provider)
    )

    identity: Identity | None = None

    @app.router.get("/")
    async def home(request):
        nonlocal identity
        identity = request.user
        return None

    await app.start()

    await app(
        get_example_scope(
            "GET",
            "/",
            extra_headers=[(b"X-API-Key", b"any-key")],
        ),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 204
    assert identity is not None
    assert identity.is_authenticated() is False


async def test_api_key_authentication_with_failing_provider(app: FakeApplication):
    provider = FailingAPIKeysProvider()
    app.use_authentication().add(
        APIKeyAuthentication(param_name="X-API-Key", keys_provider=provider)
    )

    identity: Identity | None = None

    @app.router.get("/")
    async def home(request):
        nonlocal identity
        identity = request.user
        return None

    await app.start()

    # Must not eat exceptions!
    await app(
        get_example_scope(
            "GET",
            "/",
            extra_headers=[(b"X-API-Key", b"any-key")],
        ),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 500


# Edge cases and special scenarios
async def test_api_key_authentication_case_sensitive_header(
    app: FakeApplication, api_key
):
    app.use_authentication().add(
        APIKeyAuthentication(api_key, param_name="X-Api-Key")  # Different case
    )

    identity: Identity | None = None

    @app.router.get("/")
    async def home(request):
        nonlocal identity
        identity = request.user
        return None

    await app.start()

    # Test with exact case
    await app(
        get_example_scope(
            "GET",
            "/",
            extra_headers=[(b"X-Api-Key", b"test-api-key-123")],
        ),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 204
    assert identity is not None
    assert identity.is_authenticated() is True


async def test_api_key_authentication_unicode_key(app: FakeApplication):
    unicode_key = APIKey(
        secret=Secret("ключ-тест-123", direct_value=True),  # Cyrillic characters
        claims={"name": "Unicode User"},
    )

    app.use_authentication().add(
        APIKeyAuthentication(unicode_key, param_name="X-API-Key")
    )

    identity: Identity | None = None

    @app.router.get("/")
    async def home(request):
        nonlocal identity
        identity = request.user
        return None

    await app.start()

    await app(
        get_example_scope(
            "GET",
            "/",
            extra_headers=[(b"X-API-Key", "ключ-тест-123".encode("utf-8"))],
        ),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 204
    assert identity is not None
    assert identity.is_authenticated() is True
    assert identity["name"] == "Unicode User"


async def test_api_key_authentication_empty_key_value(app: FakeApplication, api_key):
    app.use_authentication().add(APIKeyAuthentication(api_key, param_name="X-API-Key"))

    identity: Identity | None = None

    @app.router.get("/")
    async def home(request):
        nonlocal identity
        identity = request.user
        return None

    await app.start()

    await app(
        get_example_scope(
            "GET",
            "/",
            extra_headers=[(b"X-API-Key", b"")],
        ),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 204
    assert identity is not None
    assert identity.is_authenticated() is False


def test_api_key_authentication_custom_description():
    api_key = APIKey(secret=Secret("test-key", direct_value=True))

    auth = APIKeyAuthentication(
        api_key, param_name="X-API-Key", description="Custom API Key Auth"
    )
    assert auth.description == "Custom API Key Auth"


# Test with APIKeyLocation enum directly
def test_api_key_authentication_with_enum_location():
    api_key = APIKey(secret=Secret("test-key", direct_value=True))

    auth = APIKeyAuthentication(
        api_key, param_name="api_key", location=APIKeyLocation.QUERY
    )
    assert auth.location == APIKeyLocation.QUERY
