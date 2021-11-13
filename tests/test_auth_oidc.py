from datetime import datetime
from typing import Optional

import pytest
from guardpost.authorization import Policy
from guardpost.common import AuthenticatedRequirement

from blacksheep.cookies import parse_cookie
from blacksheep.exceptions import Unauthorized
from blacksheep.messages import Request, Response
from blacksheep.server.application import Application
from blacksheep.server.authentication.oidc import (
    OpenIDConfiguration,
    OpenIDConnectHandler,
    OpenIDSettings,
    TokenResponse,
    use_openid_connect,
)
from blacksheep.testing.helpers import get_example_scope
from blacksheep.testing.messages import MockReceive, MockSend

from .test_auth_cookie import get_auth_cookie
from .utils.application import FakeApplication

MOCKED_AUTHORITY = (
    "https://raw.githubusercontent.com/Neoteroi/BlackSheep-Examples/jwks/.res/"
)


def configure_test_oidc(app: Application):
    return use_openid_connect(
        app,
        OpenIDSettings(
            client_id="067cee45-faf3-4c75-9fef-09f050bcc3ae",
            authority=MOCKED_AUTHORITY,
        ),
    )


def get_request(method: str = "GET", path: str = "/account") -> Request:
    request = Request(method, path.encode(), [(b"host", b"localhost:5000")])
    request.scope = get_example_scope(method, path)  # type: ignore
    return request


def assert_redirect_to_sign_in(response: Optional[Response]):
    assert response is not None
    assert response.status == 302
    location = response.headers.get_first(b"location")

    assert location is not None
    assert location.startswith(b"https://neoteroi.dev/authorization")
    assert b"response_type=id_token" in location


@pytest.mark.asyncio
async def test_openid_connect_handler_redirect(app: FakeApplication):
    oidc = configure_test_oidc(app)
    assert isinstance(oidc, OpenIDConnectHandler)

    await app(
        get_example_scope("GET", oidc.settings.entry_path), MockReceive(), MockSend()
    )

    assert_redirect_to_sign_in(app.response)


@pytest.mark.asyncio
async def test_openid_connect_handler_auth_post(app: FakeApplication):
    oidc = configure_test_oidc(app)
    assert isinstance(oidc, OpenIDConnectHandler)

    await app(
        get_example_scope("POST", oidc.settings.callback_path),
        MockReceive([b'{"error":"access_denied"}']),
        MockSend(),
    )

    response = app.response
    assert response is not None


@pytest.mark.asyncio
async def test_openid_connect_handler_handling_request_without_host_header(
    app: FakeApplication,
):
    oidc = configure_test_oidc(app)

    scope = get_example_scope("GET", oidc.settings.entry_path)
    scope["headers"] = []

    await app(
        scope,
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response is not None
    assert response.status == 400


@pytest.mark.asyncio
async def test_default_openid_connect_handler_redirects_unauthenticated_users(
    app: FakeApplication,
):
    oidc = configure_test_oidc(app)

    app.use_authorization().with_default_policy(
        Policy("authenticated", AuthenticatedRequirement())
    )

    @app.router.get("/account")
    def get_account_details():
        ...

    @app.router.get("/requirement")
    def example():
        raise Unauthorized()

    await app.start()
    await app(get_example_scope("GET", "/account"), MockReceive(), MockSend())

    assert_redirect_to_sign_in(app.response)

    # if the user is authenticated, but not authorized to do something,
    # then the server should not redirect to the sign-in page
    await app(
        get_example_scope(
            "GET",
            "/requirement",
            [
                (
                    b"cookie",
                    get_auth_cookie(
                        oidc._auth_handler, {"id": 1, "email": "example@neoteroi.dev"}
                    ).encode(),
                )
            ],
        ),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response is not None
    assert response.status == 401  # unauthorized


@pytest.mark.asyncio
async def test_openid_connect_handler_logout_endpoint(
    app: FakeApplication,
):
    oidc = configure_test_oidc(app)

    await app.start()
    await app(
        get_example_scope("GET", oidc.settings.logout_path), MockReceive(), MockSend()
    )

    response = app.response
    assert response is not None
    assert response.status == 302
    location = response.headers.get_first(b"location")

    assert location is not None
    assert location == oidc.settings.post_logout_redirect_path.encode()
    cookie_value = response.headers.get_single(b"set-cookie")

    assert cookie_value is not None
    cookie = parse_cookie(cookie_value)
    assert cookie.expires is not None
    assert cookie.expires < datetime.utcnow()


def test_openid_configuration_class():
    # https://neoteroi.eu.auth0.com/.well-known/openid-configuration
    instance = OpenIDConfiguration(
        {
            "issuer": "https://neoteroi.eu.auth0.com/",
            "authorization_endpoint": "https://neoteroi.eu.auth0.com/authorize",
            "token_endpoint": "https://neoteroi.eu.auth0.com/oauth/token",
            "device_authorization_endpoint": "https://neoteroi.eu.auth0.com/oauth/device/code",
            "userinfo_endpoint": "https://neoteroi.eu.auth0.com/userinfo",
            "mfa_challenge_endpoint": "https://neoteroi.eu.auth0.com/mfa/challenge",
            "jwks_uri": "https://neoteroi.eu.auth0.com/.well-known/jwks.json",
            "registration_endpoint": "https://neoteroi.eu.auth0.com/oidc/register",
            "revocation_endpoint": "https://neoteroi.eu.auth0.com/oauth/revoke",
            "scopes_supported": [
                "openid",
                "profile",
                "offline_access",
                "name",
                "given_name",
                "family_name",
                "nickname",
                "email",
                "email_verified",
                "picture",
                "created_at",
                "identities",
                "phone",
                "address",
            ],
            "response_types_supported": [
                "code",
                "token",
                "id_token",
                "code token",
                "code id_token",
                "token id_token",
                "code token id_token",
            ],
            "code_challenge_methods_supported": ["S256", "plain"],
            "response_modes_supported": ["query", "fragment", "form_post"],
            "subject_types_supported": ["public"],
            "id_token_signing_alg_values_supported": ["HS256", "RS256"],
            "token_endpoint_auth_methods_supported": [
                "client_secret_basic",
                "client_secret_post",
            ],
            "claims_supported": [
                "aud",
                "auth_time",
                "created_at",
                "email",
                "email_verified",
                "exp",
                "family_name",
                "given_name",
                "iat",
                "identities",
                "iss",
                "name",
                "nickname",
                "phone_number",
                "picture",
                "sub",
            ],
            "request_uri_parameter_supported": False,
        }
    )

    for name in {
        "authorization_endpoint",
        "jwks_uri",
        "token_endpoint",
        "end_session_endpoint",
        "issuer",
    }:
        assert getattr(instance, name) == instance._data.get(name)


def test_token_response_class():
    token_response = TokenResponse(
        {
            "token_type": "Bearer",
            "access_token": "LOREM IPSUM",
            "refresh_token": "DOLOR SIT AMET",
        }
    )

    assert str(token_response) == str(token_response.data)
    assert repr(token_response) == repr(token_response.data)

    assert token_response.token_type == "Bearer"
    assert token_response.access_token == "LOREM IPSUM"
    assert token_response.refresh_token == "DOLOR SIT AMET"
    assert token_response.id_token is None
    assert token_response.expires_on is None
    assert token_response.expires_in is None

    token_response = TokenResponse(
        {
            "token_type": "Bearer",
            "access_token": "LOREM IPSUM",
            "refresh_token": "DOLOR SIT AMET",
            "id_token": "CONSECTETUR",
            "expires_in": "360",
            "expires_on": "900",
        }
    )

    assert str(token_response) == str(token_response.data)
    assert repr(token_response) == repr(token_response.data)

    assert token_response.token_type == "Bearer"
    assert token_response.access_token == "LOREM IPSUM"
    assert token_response.refresh_token == "DOLOR SIT AMET"
    assert token_response.id_token == "CONSECTETUR"
    assert token_response.expires_on == 900
    assert token_response.expires_in == 360
