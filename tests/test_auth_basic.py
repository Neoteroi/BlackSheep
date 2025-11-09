import base64

import pytest
from essentials.secrets import Secret
from guardpost import Identity

from blacksheep.server.authentication.basic import (
    BasicAuthentication,
    BasicCredentials,
    BasicCredentialsProvider,
)
from blacksheep.testing.helpers import get_example_scope
from blacksheep.testing.messages import MockReceive, MockSend
from tests.utils.application import FakeApplication


# Test fixtures
@pytest.fixture
def basic_credentials():
    return BasicCredentials(
        username="testuser",
        password=Secret("password123", direct_value=True),
        claims={"name": "Test User", "email": "test@example.com"},
        roles=["user", "reader"],
    )


@pytest.fixture
def admin_credentials():
    return BasicCredentials(
        username="admin",
        password=Secret("admin123", direct_value=True),
        claims={"name": "Admin User", "email": "admin@example.com"},
        roles=["admin", "user"],
    )


class MockCredentialsProvider(BasicCredentialsProvider):
    def __init__(self, credentials: list[BasicCredentials]):
        self._credentials = credentials

    async def get_credentials(self) -> list[BasicCredentials]:
        return self._credentials


class FailingCredentialsProvider(BasicCredentialsProvider):
    async def get_credentials(self) -> list[BasicCredentials]:
        raise Exception("Database connection failed")


# BasicCredentials tests
def test_basic_credentials_creation():
    credentials = BasicCredentials(
        username="testuser",
        password=Secret("password123", direct_value=True),
        claims={"custom": "claim"},
        roles=["user"],
    )

    assert credentials.username == "testuser"
    assert credentials.claims == {"custom": "claim"}
    assert credentials.roles == ["user"]


def test_basic_credentials_defaults():
    credentials = BasicCredentials(
        username="testuser",
        password=Secret("password123", direct_value=True),
    )

    assert credentials.username == "testuser"
    assert credentials.claims == {}
    assert credentials.roles == []


def test_basic_credentials_to_header_value():
    credentials = BasicCredentials(
        username="testuser",
        password=Secret("password123", direct_value=True),
    )

    header_value = credentials.to_header_value()
    expected = "Basic " + base64.b64encode(b"testuser:password123").decode("utf-8")

    assert header_value == expected


def test_basic_credentials_match_success():
    credentials = BasicCredentials(
        username="testuser",
        password=Secret("password123", direct_value=True),
    )

    assert credentials.match("testuser", "password123") is True


def test_basic_credentials_match_wrong_username():
    credentials = BasicCredentials(
        username="testuser",
        password=Secret("password123", direct_value=True),
    )

    assert credentials.match("wronguser", "password123") is False


def test_basic_credentials_match_wrong_password():
    credentials = BasicCredentials(
        username="testuser",
        password=Secret("password123", direct_value=True),
    )

    assert credentials.match("testuser", "wrongpassword") is False


# BasicAuthentication tests
def test_basic_authentication_creation_with_credentials():
    credentials = BasicCredentials(
        username="test",
        password=Secret("pass", direct_value=True),
    )

    auth = BasicAuthentication(credentials)
    assert auth.scheme == "Basic"
    assert len(auth._credentials) == 1


def test_basic_authentication_creation_with_provider():
    provider = MockCredentialsProvider([])
    auth = BasicAuthentication(credentials_provider=provider)
    assert auth._credentials_provider is provider


def test_basic_authentication_creation_with_custom_scheme():
    credentials = BasicCredentials(
        username="test",
        password=Secret("pass", direct_value=True),
    )

    auth = BasicAuthentication(credentials, scheme="CustomBasic")
    assert auth.scheme == "CustomBasic"


def test_basic_authentication_creation_requires_credentials_or_provider():
    with pytest.raises(
        ValueError, match="Either credentials or credentials_provider must be provided"
    ):
        BasicAuthentication()


async def test_basic_authentication_success(app: FakeApplication, basic_credentials):
    app.use_authentication().add(BasicAuthentication(basic_credentials))

    identity: Identity | None = None

    @app.router.get("/")
    async def home(request):
        nonlocal identity
        identity = request.user
        return None

    await app.start()

    # Create valid authorization header
    auth_header = basic_credentials.to_header_value().encode()

    await app(
        get_example_scope(
            "GET",
            "/",
            extra_headers=[(b"Authorization", auth_header)],
        ),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 204
    assert identity is not None
    assert identity.is_authenticated() is True
    assert identity["sub"] == "testuser"
    assert identity["name"] == "Test User"
    assert identity["email"] == "test@example.com"
    assert identity["roles"] == ["user", "reader"]


async def test_basic_authentication_no_header(app: FakeApplication, basic_credentials):
    app.use_authentication().add(BasicAuthentication(basic_credentials))

    identity: Identity | None = None

    @app.router.get("/")
    async def home(request):
        nonlocal identity
        identity = request.user
        return None

    await app.start()

    await app(
        get_example_scope("GET", "/"),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 204
    assert identity is not None
    assert identity.is_authenticated() is False


async def test_basic_authentication_wrong_scheme(
    app: FakeApplication, basic_credentials
):
    app.use_authentication().add(BasicAuthentication(basic_credentials))

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
            extra_headers=[(b"Authorization", b"Bearer token123")],
        ),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 204
    assert identity is not None
    assert identity.is_authenticated() is False


async def test_basic_authentication_invalid_base64(
    app: FakeApplication, basic_credentials
):
    app.use_authentication().add(BasicAuthentication(basic_credentials))

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
            extra_headers=[(b"Authorization", b"Basic invalid-base64!")],
        ),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 204
    assert identity is not None
    assert identity.is_authenticated() is False


async def test_basic_authentication_malformed_credentials(
    app: FakeApplication, basic_credentials
):
    app.use_authentication().add(BasicAuthentication(basic_credentials))

    identity: Identity | None = None

    @app.router.get("/")
    async def home(request):
        nonlocal identity
        identity = request.user
        return None

    await app.start()

    # Valid base64 but missing colon separator
    malformed_creds = base64.b64encode(b"usernamewithoutcolon").decode()

    await app(
        get_example_scope(
            "GET",
            "/",
            extra_headers=[(b"Authorization", f"Basic {malformed_creds}".encode())],
        ),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 204
    assert identity is not None
    assert identity.is_authenticated() is False


async def test_basic_authentication_wrong_credentials(
    app: FakeApplication, basic_credentials
):
    app.use_authentication().add(BasicAuthentication(basic_credentials))

    identity: Identity | None = None

    @app.router.get("/")
    async def home(request):
        nonlocal identity
        identity = request.user
        return None

    await app.start()

    # Valid format but wrong credentials
    wrong_creds = base64.b64encode(b"wronguser:wrongpass").decode()

    await app(
        get_example_scope(
            "GET",
            "/",
            extra_headers=[(b"Authorization", f"Basic {wrong_creds}".encode())],
        ),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 204
    assert identity is not None
    assert identity.is_authenticated() is False


async def test_basic_authentication_multiple_credentials(
    app: FakeApplication, basic_credentials, admin_credentials
):
    app.use_authentication().add(
        BasicAuthentication(basic_credentials, admin_credentials)
    )

    identity: Identity | None = None

    @app.router.get("/")
    async def home(request):
        nonlocal identity
        identity = request.user
        return None

    await app.start()

    # Test with first credentials
    auth_header = basic_credentials.to_header_value().encode()
    await app(
        get_example_scope(
            "GET",
            "/",
            extra_headers=[(b"Authorization", auth_header)],
        ),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 204
    assert identity is not None
    assert identity["sub"] == "testuser"

    # Test with second credentials
    auth_header = admin_credentials.to_header_value().encode()
    await app(
        get_example_scope(
            "GET",
            "/",
            extra_headers=[(b"Authorization", auth_header)],
        ),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 204
    assert identity is not None
    assert identity["sub"] == "admin"
    assert "admin" in identity["roles"]


async def test_basic_authentication_with_provider(
    app: FakeApplication, basic_credentials
):
    provider = MockCredentialsProvider([basic_credentials])
    app.use_authentication().add(BasicAuthentication(credentials_provider=provider))

    identity: Identity | None = None

    @app.router.get("/")
    async def home(request):
        nonlocal identity
        identity = request.user
        return None

    await app.start()

    auth_header = basic_credentials.to_header_value().encode()

    await app(
        get_example_scope(
            "GET",
            "/",
            extra_headers=[(b"Authorization", auth_header)],
        ),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 204
    assert identity is not None
    assert identity.is_authenticated() is True
    assert identity["sub"] == "testuser"


async def test_basic_authentication_with_failing_provider(app: FakeApplication):
    provider = FailingCredentialsProvider()
    app.use_authentication().add(BasicAuthentication(credentials_provider=provider))

    identity: Identity | None = None

    @app.router.get("/")
    async def home(request):
        nonlocal identity
        identity = request.user
        return None

    await app.start()

    auth_header = base64.b64encode(b"user:pass").decode()

    # Must not eat the exception
    await app(
        get_example_scope(
            "GET",
            "/",
            extra_headers=[(b"Authorization", f"Basic {auth_header}".encode())],
        ),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 500


async def test_basic_authentication_empty_provider(app: FakeApplication):
    provider = MockCredentialsProvider([])
    app.use_authentication().add(BasicAuthentication(credentials_provider=provider))

    identity: Identity | None = None

    @app.router.get("/")
    async def home(request):
        nonlocal identity
        identity = request.user
        return None

    await app.start()

    auth_header = base64.b64encode(b"user:pass").decode()

    await app(
        get_example_scope(
            "GET",
            "/",
            extra_headers=[(b"Authorization", f"Basic {auth_header}".encode())],
        ),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 204
    assert identity is not None
    assert identity.is_authenticated() is False


def test_basic_authentication_custom_description():
    credentials = BasicCredentials(
        username="test",
        password=Secret("pass", direct_value=True),
    )

    auth = BasicAuthentication(credentials, description="Custom Basic Auth")
    assert auth.description == "Custom Basic Auth"


async def test_basic_authentication_unicode_credentials(app: FakeApplication):
    # Test with unicode characters in username/password
    unicode_credentials = BasicCredentials(
        username="тест",
        password=Secret("пароль123", direct_value=True),
        claims={"name": "Unicode User"},
    )

    app.use_authentication().add(BasicAuthentication(unicode_credentials))

    identity: Identity | None = None

    @app.router.get("/")
    async def home(request):
        nonlocal identity
        identity = request.user
        return None

    await app.start()

    auth_header = unicode_credentials.to_header_value().encode()

    await app(
        get_example_scope(
            "GET",
            "/",
            extra_headers=[(b"Authorization", auth_header)],
        ),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 204
    assert identity is not None
    assert identity.is_authenticated() is True
    assert identity["sub"] == "тест"
    assert identity["name"] == "Unicode User"


async def test_basic_authentication_password_with_colon(app: FakeApplication):
    # Test password containing colon character
    credentials = BasicCredentials(
        username="testuser",
        password=Secret("pass:word:123", direct_value=True),
    )

    app.use_authentication().add(BasicAuthentication(credentials))

    identity: Identity | None = None

    @app.router.get("/")
    async def home(request):
        nonlocal identity
        identity = request.user
        return None

    await app.start()

    auth_header = credentials.to_header_value().encode()

    await app(
        get_example_scope(
            "GET",
            "/",
            extra_headers=[(b"Authorization", auth_header)],
        ),
        MockReceive(),
        MockSend(),
    )

    assert app.response.status == 204
    assert identity is not None
    assert identity.is_authenticated() is True
    assert identity["sub"] == "testuser"
