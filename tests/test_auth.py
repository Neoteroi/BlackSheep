import json
from typing import Any, Dict, Optional

import jwt
import pkg_resources
import pytest
from guardpost.authentication import Identity
from guardpost.authorization import AuthorizationContext, UnauthorizedError
from guardpost.common import AuthenticatedRequirement
from guardpost.jwks import JWKS, InMemoryKeysProvider, KeysProvider
from pytest import raises
from blacksheep.server.application import Application

from blacksheep.server.authentication import (
    AuthenticateChallenge,
    AuthenticationHandler,
)
from blacksheep.server.authentication.jwt import JWTBearerAuthentication
from blacksheep.server.authorization import (
    AuthorizationWithoutAuthenticationError,
    Policy,
    Requirement,
    allow_anonymous,
    auth,
    get_www_authenticated_header_from_generic_unauthorized_error,
)
from blacksheep.testing.helpers import get_example_scope
from tests.test_files_serving import get_folder_path


def get_file_path(file_name, folder_name: str = "res") -> str:
    return pkg_resources.resource_filename(__name__, f"./{folder_name}/{file_name}")


# region JWTBearer


def get_test_jwks() -> JWKS:
    with open(get_file_path("jwks.json"), mode="rt", encoding="utf8") as jwks_file:
        jwks_dict = json.loads(jwks_file.read())
    return JWKS.from_dict(jwks_dict)


@pytest.fixture(scope="session")
def default_keys_provider() -> KeysProvider:
    return InMemoryKeysProvider(get_test_jwks())


def get_access_token(kid: str, payload: Dict[str, Any]):
    with open(get_file_path(f"{kid}.pem"), "r") as key_file:
        private_key = key_file.read()

    return jwt.encode(
        payload,
        private_key,
        algorithm="RS256",
        headers={"kid": kid},
    )


# endregion


class MockAuthHandler(AuthenticationHandler):
    def __init__(self, identity=None):
        if identity is None:
            identity = Identity({"id": "001", "name": "Charlie Brown"}, "JWT")
        self.identity = identity

    async def authenticate(self, context: Any) -> Optional[Identity]:
        context.identity = self.identity
        return context.identity


class MockNotAuthHandler(AuthenticationHandler):
    async def authenticate(self, context: Any) -> Optional[Identity]:
        context.identity = Identity({"id": "007"})
        # NB: an identity without authentication scheme is treated
        # as anonymous identity
        return context.identity


class AccessTokenCrashingHandler(AuthenticationHandler):
    async def authenticate(self, context: Any) -> Optional[Identity]:
        raise AuthenticateChallenge(
            "Bearer",
            None,
            {
                "error": "Invalid access token",
                "error_description": "Access token expired",
            },
        )


class AdminRequirement(Requirement):
    def handle(self, context: AuthorizationContext):
        identity = context.identity

        if identity is not None and identity["role"] == "admin":
            context.succeed(self)


class AdminsPolicy(Policy):
    def __init__(self):
        super().__init__("admin", AdminRequirement())


@pytest.mark.asyncio
async def test_authentication_sets_identity_in_request(app, mock_receive, mock_send):
    app.use_authentication().add(MockAuthHandler())

    identity = None

    @app.router.get("/")
    async def home(request):
        nonlocal identity
        identity = request.identity
        return None

    app.prepare()
    await app(get_example_scope("GET", "/"), mock_receive(), mock_send)

    assert app.response.status == 204

    assert identity is not None
    assert identity["id"] == "001"
    assert identity["name"] == "Charlie Brown"


@pytest.mark.asyncio
async def test_authorization_unauthorized_error(app, mock_receive, mock_send):
    app.use_authentication().add(MockAuthHandler())

    app.use_authorization().add(AdminsPolicy())

    @auth("admin")
    @app.router.get("/")
    async def home():
        return None

    app.prepare()
    await app(get_example_scope("GET", "/"), mock_receive(), mock_send)

    assert app.response.status == 401


@pytest.mark.asyncio
async def test_authorization_policy_success(app, mock_receive, mock_send):
    admin = Identity({"id": "001", "name": "Charlie Brown", "role": "admin"}, "JWT")

    app.use_authentication().add(MockAuthHandler(admin))

    app.use_authorization().add(AdminsPolicy())

    @auth("admin")
    @app.router.get("/")
    async def home():
        return None

    app.prepare()
    await app(get_example_scope("GET", "/"), mock_receive(), mock_send)

    assert app.response.status == 204


@pytest.mark.asyncio
async def test_authorization_default_allows_anonymous(app, mock_receive, mock_send):
    app.use_authentication().add(MockAuthHandler())

    app.use_authorization().add(AdminsPolicy())

    @app.router.get("/")
    async def home():
        return None

    app.prepare()
    await app(get_example_scope("GET", "/"), mock_receive(), mock_send)

    assert app.response.status == 204


@pytest.mark.asyncio
async def test_authorization_supports_default_require_authenticated(
    app, mock_receive, mock_send
):
    app.use_authentication().add(MockNotAuthHandler())

    app.use_authorization().add(
        AdminsPolicy()
    ).default_policy += AuthenticatedRequirement()

    @app.router.get("/")
    async def home():
        return None

    app.prepare()
    await app(get_example_scope("GET", "/"), mock_receive(), mock_send)

    assert app.response.status == 401


@pytest.mark.asyncio
async def test_static_files_allow_anonymous_by_default(app, mock_receive, mock_send):
    app.use_authentication().add(MockNotAuthHandler())

    app.use_authorization().add(
        AdminsPolicy()
    ).default_policy += AuthenticatedRequirement()

    @app.router.get("/")
    async def home():
        return None

    app.serve_files(get_folder_path("files"))

    await app.start()

    await app(get_example_scope("GET", "/"), mock_receive(), mock_send)

    assert app.response.status == 401

    await app(get_example_scope("GET", "/lorem-ipsum.txt"), mock_receive(), mock_send)

    assert app.response.status == 200
    content = await app.response.text()
    assert content == "Lorem ipsum dolor sit amet\n"


@pytest.mark.asyncio
async def test_static_files_support_authentication(app, mock_receive, mock_send):
    app.use_authentication().add(MockNotAuthHandler())

    app.use_authorization().add(
        AdminsPolicy()
    ).default_policy += AuthenticatedRequirement()

    @app.router.get("/")
    async def home():
        return None

    app.serve_files(get_folder_path("files"), allow_anonymous=False)

    await app.start()

    await app(get_example_scope("GET", "/"), mock_receive(), mock_send)

    assert app.response.status == 401

    await app(get_example_scope("GET", "/lorem-ipsum.txt"), mock_receive(), mock_send)

    assert app.response.status == 401


@pytest.mark.asyncio
async def test_static_files_support_authentication_by_route(
    app, mock_receive, mock_send
):
    app.use_authentication().add(MockNotAuthHandler())

    app.use_authorization().add(
        AdminsPolicy()
    ).default_policy += AuthenticatedRequirement()

    @app.router.get("/")
    async def home():
        return None

    app.serve_files(get_folder_path("files"), allow_anonymous=False)
    app.serve_files(get_folder_path("files2"), allow_anonymous=True, root_path="/login")

    await app.start()

    await app(get_example_scope("GET", "/"), mock_receive(), mock_send)

    assert app.response.status == 401

    await app(get_example_scope("GET", "/lorem-ipsum.txt"), mock_receive(), mock_send)

    assert app.response.status == 401

    await app(get_example_scope("GET", "/login/index.html"), mock_receive(), mock_send)

    assert app.response.status == 200
    content = await app.response.text()
    assert (
        content
        == """<!DOCTYPE html>
<html>
  <head>
    <title>Example.</title>
    <link rel="stylesheet" type="text/css" href="/styles/main.css" />
  </head>
  <body>
    <h1>Lorem ipsum</h1>
    <p>Dolor sit amet.</p>
    <script src="/scripts/main.js"></script>
  </body>
</html>
"""
    )


@pytest.mark.asyncio
async def test_authorization_supports_allow_anonymous(app, mock_receive, mock_send):
    from blacksheep.server.responses import text

    app.use_authentication().add(MockNotAuthHandler())

    app.use_authorization().add(
        AdminsPolicy()
    ).default_policy += AuthenticatedRequirement()

    @allow_anonymous()
    @app.router.get("/")
    async def home():
        return text("Hi There!")

    app.prepare()
    await app(get_example_scope("GET", "/"), mock_receive(), mock_send)

    assert app.response.status == 200


@pytest.mark.asyncio
async def test_authentication_challenge_response(app, mock_receive, mock_send):
    app.use_authentication().add(AccessTokenCrashingHandler())

    app.use_authorization().add(
        AdminsPolicy()
    ).default_policy += AuthenticatedRequirement()

    @app.router.get("/")
    async def home():
        return None

    app.prepare()
    await app(get_example_scope("GET", "/"), mock_receive(), mock_send)

    assert app.response.status == 401
    header = app.response.get_single_header(b"WWW-Authenticate")

    assert header is not None
    assert header == (
        b'Bearer, error="Invalid access token", '
        b'error_description="Access token expired"'
    )


@pytest.mark.asyncio
async def test_authorization_strategy_without_authentication_raises(app):
    app.use_authorization()

    with raises(AuthorizationWithoutAuthenticationError):
        app.prepare()


@pytest.mark.parametrize(
    "scheme,realm,parameters,expected_value",
    [
        ["Basic", None, None, b"Basic"],
        ["Bearer", "Mushrooms Kingdom", None, b'Bearer realm="Mushrooms Kingdom"'],
        [
            "Bearer",
            "Mushrooms Kingdom",
            {
                "title": "Something",
                "error": "Invalid access token",
                "error_description": "access token expired",
            },
            b'Bearer realm="Mushrooms Kingdom", '
            b'title="Something", '
            b'error="Invalid access token", '
            b'error_description="access token expired"',
        ],
    ],
)
def test_authentication_challenge_error(scheme, realm, parameters, expected_value):
    error = AuthenticateChallenge(scheme, realm, parameters)

    header = error.get_header()
    assert header[0] == b"WWW-Authenticate"
    assert header[1] == expected_value


@pytest.mark.parametrize(
    "exc,expected_value",
    [
        (UnauthorizedError(None, [], scheme="AAD"), b"AAD"),
        (UnauthorizedError(None, [], scheme="example"), b"example"),
        (
            UnauthorizedError(None, [], scheme="Something-Something"),
            b"Something-Something",
        ),
    ],
)
def test_get_www_authenticated_header_from_generic_unauthorized_error(
    exc, expected_value
):
    header = get_www_authenticated_header_from_generic_unauthorized_error(exc)

    assert header is not None
    name, value = header
    assert name == b"WWW-Authenticate"
    assert value == expected_value


@pytest.mark.asyncio
async def test_authorization_default_requires_authenticated_user(
    app, mock_receive, mock_send
):
    app.use_authentication().add(MockNotAuthHandler())

    app.use_authorization()

    @app.router.get("/")
    async def home():
        return None

    @auth()
    @app.router.get("/admin")
    async def admin():
        return None

    app.prepare()
    await app(get_example_scope("GET", "/"), mock_receive(), mock_send)
    assert app.response.status == 204

    await app(get_example_scope("GET", "/admin"), mock_receive(), mock_send)
    assert app.response.status == 401


@pytest.mark.asyncio
async def test_jwt_bearer_authentication(
    app, mock_receive, mock_send, default_keys_provider
):
    app.use_authentication().add(
        JWTBearerAuthentication(
            valid_audiences=["a"],
            valid_issuers=["b"],
            keys_provider=default_keys_provider,
        )
    )

    identity: Optional[Identity] = None

    @app.router.get("/")
    async def home(request):
        nonlocal identity
        identity = request.identity
        return None

    await app.start()
    await app(get_example_scope("GET", "/"), mock_receive(), mock_send)

    assert app.response is not None
    assert app.response.status == 204

    assert identity is not None
    assert identity.is_authenticated() is False

    # request with valid Bearer Token
    access_token = get_access_token(
        "0",
        {
            "aud": "a",
            "iss": "b",
            "id": "001",
            "name": "Charlie Brown",
        },
    )
    await app(
        get_example_scope(
            "GET",
            "/",
            extra_headers=[(b"Authorization", b"Bearer " + access_token.encode())],
        ),
        mock_receive(),
        mock_send,
    )

    assert app.response is not None
    assert app.response.status == 204

    assert identity is not None
    assert identity["id"] == "001"
    assert identity["name"] == "Charlie Brown"

    # request with invalid Bearer Token (invalid audience)
    access_token = get_access_token(
        "0",
        {
            "aud": "NO",
            "iss": "b",
            "id": "001",
            "name": "Charlie Brown",
        },
    )
    await app(
        get_example_scope(
            "GET",
            "/",
            extra_headers=[(b"Authorization", b"Bearer " + access_token.encode())],
        ),
        mock_receive(),
        mock_send,
    )

    assert app.response is not None
    assert app.response.status == 204

    assert identity is not None
    assert identity.is_authenticated() is False

    # request with invalid Bearer Token (invalid header)
    access_token = get_access_token(
        "0",
        {
            "aud": "a",
            "iss": "b",
            "id": "001",
            "name": "Charlie Brown",
        },
    )
    await app(
        get_example_scope(
            "GET",
            "/",
            extra_headers=[(b"Authorization", access_token.encode())],
        ),
        mock_receive(),
        mock_send,
    )

    assert app.response is not None
    assert app.response.status == 204

    assert identity is not None
    assert identity.is_authenticated() is False


def test_set_authentication_strategy_more_than_once(app: Application):
    auth_strategy = app.use_authentication()
    assert app.use_authentication() is auth_strategy


def test_set_authorization_strategy_more_than_once(app: Application):
    auth_strategy = app.use_authorization()
    assert app.use_authorization() is auth_strategy
