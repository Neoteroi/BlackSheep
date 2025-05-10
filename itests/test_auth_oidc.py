"""
This module is under integration tests folder because it uses a partially faked
authorization server in a running Flask server.
"""

import json
import re
from datetime import datetime
from typing import Any, List, Optional, Tuple
from urllib.parse import parse_qs, urlencode

import pytest
from guardpost import Identity, Policy
from guardpost.common import AuthenticatedRequirement

from blacksheep.contents import Content
from blacksheep.cookies import parse_cookie
from blacksheep.exceptions import BadRequest, Unauthorized
from blacksheep.messages import Request, Response
from blacksheep.server.application import Application
from blacksheep.server.asgi import incoming_request
from blacksheep.server.authentication.cookie import CookieAuthentication
from blacksheep.server.authentication.jwt import JWTBearerAuthentication
from blacksheep.server.authentication.oidc import (
    CookiesOpenIDTokensHandler,
    CookiesTokensStore,
    IDToken,
    JWTOpenIDTokensHandler,
    MissingClientSecretSettingError,
    OpenIDConfiguration,
    OpenIDConnectConfigurationError,
    OpenIDConnectError,
    OpenIDConnectFailedExchangeError,
    OpenIDConnectHandler,
    OpenIDConnectRequestError,
    OpenIDSettings,
    ParametersBuilder,
    TokenResponse,
    TokensStore,
    use_openid_connect,
)
from blacksheep.testing.helpers import get_example_scope
from blacksheep.testing.messages import MockReceive, MockSend
from blacksheep.url import URL
from blacksheep.utils.aio import FailedRequestError
from blacksheep.utils.time import utcnow
from tests.test_auth import get_token
from tests.test_auth_cookie import get_auth_cookie
from tests.utils.application import FakeApplication

from .client_fixtures import *  # NoQA

MOCKED_AUTHORITY = "http://127.0.0.1:44777/oidc"


try:
    from unittest.mock import AsyncMock
except ImportError:
    # Python 3.7
    from mock import AsyncMock


@pytest.fixture
def app():
    return FakeApplication()


def _mock_token_endpoint(oidc, oidc_configuration, id_token_claims):
    # mock handling of the remote OIDC server
    async def mocked_post_form(url: str, data: Any):
        assert url == oidc_configuration.token_endpoint

        access_token_claims = {
            "sub": "4534224f-546f-401f-9cab-067b0b2b9abb",
            "aud": "------------------------------------",
            "scp": "read:todos",
            "iss": oidc_configuration.issuer,
        }

        return {
            "id_token": get_token("0", id_token_claims),
            "access_token": get_token("0", access_token_claims),
            "refresh_token": "00000000-0000-0000-0000-000000000000",
        }

    oidc._http_handler.post_form = mocked_post_form


class FakeTokensStore(TokensStore):
    def __init__(
        self,
        access_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
    ) -> None:
        super().__init__()
        self._access_token = access_token
        self._refresh_token = refresh_token

    async def store_tokens(
        self,
        request: Request,
        response: Response,
        access_token: str,
        refresh_token: Optional[str],
        expires: Optional[datetime] = None,
    ):
        """
        Applies a strategy to store an access token and an optional refresh token for
        the given request and response.
        """
        self._access_token = access_token
        self._refresh_token = refresh_token

    async def unset_tokens(self, request: Request):
        """
        Optional method, to unset access tokens upon sign-out.
        """
        self._access_token = None
        self._refresh_token = None

    async def restore_tokens(self, request: Request) -> None:
        """
        Applies a strategy to restore an access token and an optional refresh token for
        the given request.
        """
        assert request.identity is not None
        request.identity.access_token = self._access_token
        request.identity.refresh_token = self._refresh_token


def configure_test_oidc_cookie_auth_id_token(
    app: Application, secret: Optional[str] = None
):
    return use_openid_connect(
        app,
        OpenIDSettings(
            client_id="067cee45-faf3-4c75-9fef-09f050bcc3ae",
            client_secret=secret,
            authority=MOCKED_AUTHORITY,
        ),
    )


def configure_test_oidc_jwt_auth_id_token(
    app: Application, secret: Optional[str] = None
):
    CLIENT_ID = "067cee45-faf3-4c75-9fef-09f050bcc3ae"
    return use_openid_connect(
        app,
        OpenIDSettings(
            client_id=CLIENT_ID,
            client_secret=secret,
            authority=MOCKED_AUTHORITY,
        ),
        auth_handler=JWTOpenIDTokensHandler(
            JWTBearerAuthentication(
                authority=MOCKED_AUTHORITY,
                valid_audiences=[CLIENT_ID],
            )
        ),
    )


def configure_test_oidc_with_secret(app: Application):
    return use_openid_connect(
        app,
        OpenIDSettings(
            client_id="067cee45-faf3-4c75-9fef-09f050bcc3ae",
            client_secret="JUST_AN_EXAMPLE",
            authority=MOCKED_AUTHORITY,
        ),
    )


def get_request(method: str = "GET", path: str = "/account") -> Request:
    request = Request(method, path.encode(), [(b"host", b"localhost:5000")])
    request.scope = get_example_scope(method, path)  # type: ignore
    return request


def form_extra_headers(content: bytes) -> List[Tuple[bytes, bytes]]:
    return [
        (b"content-length", str(len(content)).encode()),
        (b"content-type", b"application/x-www-form-urlencoded"),
    ]


def assert_redirect_to_sign_in(response: Optional[Response], has_secret: bool = False):
    assert response is not None
    assert response.status == 302
    location = response.headers.get_first(b"location")

    assert location is not None
    assert location.startswith(b"https://neoteroi.dev/authorization")

    if has_secret:
        assert b"response_type=code" in location
    else:
        assert b"response_type=id_token" in location


async def test_oidc_handler_redirect(app: FakeApplication):
    oidc = configure_test_oidc_cookie_auth_id_token(app)
    assert isinstance(oidc, OpenIDConnectHandler)

    await app(
        get_example_scope("GET", oidc.settings.entry_path), MockReceive(), MockSend()
    )

    assert_redirect_to_sign_in(app.response)


async def test_oidc_handler_redirect_with_jwt_handler(app: FakeApplication):
    oidc = configure_test_oidc_jwt_auth_id_token(app)
    assert isinstance(oidc, OpenIDConnectHandler)

    await app(
        get_example_scope("GET", oidc.settings.entry_path), MockReceive(), MockSend()
    )

    assert_redirect_to_sign_in(app.response)


async def test_oidc_handler_redirect_with_secret(app: FakeApplication):
    oidc = configure_test_oidc_with_secret(app)
    assert isinstance(oidc, OpenIDConnectHandler)

    await app(
        get_example_scope("GET", oidc.settings.entry_path), MockReceive(), MockSend()
    )

    assert_redirect_to_sign_in(app.response, has_secret=True)


async def test_oidc_handler_cookie_auth_post_id_token(app: FakeApplication):
    """
    Tests the response from the built-in CookiesOpenIDTokensHandler handler after a
    successful sign-in.
    """
    oidc = configure_test_oidc_cookie_auth_id_token(app)
    assert isinstance(oidc, OpenIDConnectHandler)

    oidc_configuration = await oidc.get_openid_configuration()

    called = False
    claims = {
        "aud": oidc.settings.client_id,
        "iss": oidc_configuration.issuer,
        "sub": "4534224f-546f-401f-9cab-067b0b2b9abb",
    }

    @oidc.events.on_id_token_validated
    async def on_id_token_validated(context, parsed_token):
        nonlocal called
        called = True
        assert parsed_token == claims

    # arrange an id_token set by the remote auth server
    id_token = get_token("0", claims)
    content = urlencode({"id_token": id_token}).encode()

    await app(
        get_example_scope(
            "POST",
            oidc.settings.callback_path,
            form_extra_headers(content),
        ),
        MockReceive([content]),
        MockSend(),
    )

    response = app.response
    assert response is not None

    assert called is True
    assert response.status == 302
    assert response.headers.get_single(b"location") == b"/"
    cookie_value = response.headers.get_single(b"set-cookie")

    assert cookie_value is not None
    cookie = parse_cookie(cookie_value)

    # the auth_handler can parse the cookie value:
    assert isinstance(oidc.auth_handler, CookiesOpenIDTokensHandler)
    parsed_cookie_value = oidc.auth_handler.auth_handler.serializer.loads(cookie.value)
    assert parsed_cookie_value == claims


async def test_oidc_handler_jwt_auth_post_id_token(app: FakeApplication):
    """
    Tests the response from the built-in JWTOpenIDTokensHandler handler after a
    successful sign-in.
    """
    oidc = configure_test_oidc_jwt_auth_id_token(app)
    assert isinstance(oidc, OpenIDConnectHandler)

    oidc_configuration = await oidc.get_openid_configuration()

    called = False
    claims = {
        "aud": oidc.settings.client_id,
        "iss": oidc_configuration.issuer,
        "sub": "4534224f-546f-401f-9cab-067b0b2b9abb",
    }

    @oidc.events.on_id_token_validated
    async def on_id_token_validated(context, parsed_token):
        nonlocal called
        called = True
        assert parsed_token == claims

    # arrange an id_token set by the remote auth server
    id_token = get_token("0", claims)
    content = urlencode({"id_token": id_token}).encode()

    await app(
        get_example_scope(
            "POST",
            oidc.settings.callback_path,
            form_extra_headers(content),
        ),
        MockReceive([content]),
        MockSend(),
    )

    response = app.response
    assert response is not None

    assert called is True
    assert response.status == 200
    html = await response.text()

    assert 'sessionStorage.setItem("ID_TOKEN",' in html
    assert 'sessionStorage.setItem("ACCESS_TOKEN", "");' in html
    assert 'sessionStorage.setItem("REFRESH_TOKEN", "");' in html
    match = re.search(r'"ID_TOKEN",\s"([^\"]+)\"', html)
    assert match

    parsed_id_token = IDToken.from_trusted_token(match.group(1))
    assert parsed_id_token.data == claims


async def test_oidc_handler_jwt_refresh_token(app: FakeApplication):
    """
    Tests handling of refresh tokens using the JWT handler.
    """
    oidc = configure_test_oidc_jwt_auth_id_token(app, "EXAMPLE")

    await app.start()
    oidc_configuration = await oidc.get_openid_configuration()

    claims = {
        "aud": oidc.settings.client_id,
        "iss": oidc_configuration.issuer,
        "sub": "4534224f-546f-401f-9cab-067b0b2b9abb",
    }

    auth_handler = oidc.auth_handler
    assert isinstance(auth_handler, JWTOpenIDTokensHandler)

    _mock_token_endpoint(oidc, oidc_configuration, claims)

    # call to obtain fresh tokens
    await app(
        get_example_scope(
            "POST",
            oidc.settings.refresh_token_path,
            extra_headers={
                "X-Refresh-Token": auth_handler.protect_refresh_token("TEST")
            },
        ),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response is not None

    assert response.status == 200
    data = await response.json()

    assert "id_token" in data
    assert "access_token" in data
    assert "refresh_token" in data


async def test_oidc_handler_jwt_refresh_token_invalid_token(app: FakeApplication):
    """
    Tests that the JWT handler ignores invalid refresh tokens.
    """
    oidc = configure_test_oidc_jwt_auth_id_token(app, "EXAMPLE")

    await app.start()
    oidc_configuration = await oidc.get_openid_configuration()

    claims = {
        "aud": oidc.settings.client_id,
        "iss": oidc_configuration.issuer,
        "sub": "4534224f-546f-401f-9cab-067b0b2b9abb",
    }

    auth_handler = oidc.auth_handler
    assert isinstance(auth_handler, JWTOpenIDTokensHandler)

    _mock_token_endpoint(oidc, oidc_configuration, claims)

    # call to obtain fresh tokens
    await app(
        get_example_scope(
            "POST",
            oidc.settings.refresh_token_path,
            extra_headers={"X-Refresh-Token": "INVALID_TOKEN"},
        ),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response is not None
    assert response.status == 400

    text = await response.text()
    assert "Missing refresh_token" in text


async def test_oidc_handler_cookie_refresh_token(app: FakeApplication):
    """
    Tests handling of refresh tokens using the JWT handler.
    """
    oidc = configure_test_oidc_cookie_auth_id_token(app, secret="TEST_EXAMPLE")
    oidc.auth_handler.tokens_store = FakeTokensStore(refresh_token="TEST")  # type: ignore

    await app.start()
    oidc_configuration = await oidc.get_openid_configuration()

    claims = {
        "aud": oidc.settings.client_id,
        "iss": oidc_configuration.issuer,
        "sub": "4534224f-546f-401f-9cab-067b0b2b9abb",
    }

    _mock_token_endpoint(oidc, oidc_configuration, claims)

    # call to obtain fresh tokens
    await app(
        get_example_scope("POST", oidc.settings.refresh_token_path),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response is not None

    assert response.status == 200

    cookie_value = response.headers.get_single(b"set-cookie")

    assert cookie_value is not None
    cookie = parse_cookie(cookie_value)

    # the auth_handler can parse the cookie value:
    assert isinstance(oidc.auth_handler, CookiesOpenIDTokensHandler)
    parsed_cookie_value = oidc.auth_handler.auth_handler.serializer.loads(cookie.value)
    assert parsed_cookie_value == claims


@pytest.mark.skip("TODO: verify if this scenario is really needed.")
async def test_oidc_handler_refresh_token_missing_user_context(app: FakeApplication):
    oidc = configure_test_oidc_cookie_auth_id_token(app, secret="TEST_EXAMPLE")
    oidc.auth_handler.tokens_store = FakeTokensStore(refresh_token=None)  # type: ignore

    await app(
        get_example_scope("POST", oidc.settings.refresh_token_path),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response is not None

    assert response.status == 400

    text = await response.text()
    assert "Missing user" in text


async def test_oidc_handler_refresh_token_missing_refresh_token_context(
    app: FakeApplication,
):
    oidc = configure_test_oidc_cookie_auth_id_token(app, secret="TEST_EXAMPLE")
    oidc.auth_handler.tokens_store = FakeTokensStore(refresh_token=None)  # type: ignore

    await app.start()
    oidc_configuration = await oidc.get_openid_configuration()

    claims = {
        "aud": oidc.settings.client_id,
        "iss": oidc_configuration.issuer,
        "sub": "4534224f-546f-401f-9cab-067b0b2b9abb",
    }

    _mock_token_endpoint(oidc, oidc_configuration, claims)

    # call to obtain fresh tokens
    await app(
        get_example_scope("POST", oidc.settings.refresh_token_path),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response is not None

    assert response.status == 400

    text = await response.text()
    assert "Missing refresh_token" in text


async def test_oidc_handler_auth_post_id_token_code_1(app: FakeApplication):
    oidc = configure_test_oidc_with_secret(app)
    assert isinstance(oidc, OpenIDConnectHandler)

    # Note: mock the HTTPHandler to simulate a real authorization server that
    # handles a valid request to the token endpoint

    async def mocked_post_form(url: str, data: Any):
        assert url == oidc_configuration.token_endpoint

        assert data == {
            "grant_type": "authorization_code",
            "code": "xxx",
            "scope": "openid profile email",
            "redirect_uri": "http://127.0.0.1:8000/authorization-callback",
            "client_id": "067cee45-faf3-4c75-9fef-09f050bcc3ae",
            "client_secret": "JUST_AN_EXAMPLE",
        }

        access_token_claims = {
            "sub": "4534224f-546f-401f-9cab-067b0b2b9abb",
            "aud": "------------------------------------",
            "iss": oidc_configuration.issuer,
        }

        return {
            "access_token": get_token("0", access_token_claims),
            "refresh_token": "00000000-0000-0000-0000-000000000000",
        }

    oidc._http_handler.post_form = mocked_post_form

    oidc_configuration = await oidc.get_openid_configuration()

    called = False
    id_token_claims = {
        "aud": oidc.settings.client_id,
        "iss": oidc_configuration.issuer,
        "sub": "4534224f-546f-401f-9cab-067b0b2b9abb",
    }

    @oidc.events.on_tokens_received
    async def on_tokens_received(context, token_response: TokenResponse):
        nonlocal called
        called = True

    # arrange an id_token set by the remote auth server
    id_token = get_token("0", id_token_claims)
    content = urlencode({"id_token": id_token, "code": "xxx"}).encode()

    await app(
        get_example_scope(
            "POST",
            oidc.settings.callback_path,
            form_extra_headers(content),
        ),
        MockReceive([content]),
        MockSend(),
    )

    response = app.response
    assert response is not None

    assert called is True
    assert response.status == 302
    assert response.headers.get_single(b"location") == b"/"
    cookie_value = response.headers.get_single(b"set-cookie")

    assert cookie_value is not None
    cookie = parse_cookie(cookie_value)

    # the auth_handler can parse the cookie value:
    assert isinstance(oidc.auth_handler, CookiesOpenIDTokensHandler)
    parsed_cookie_value = oidc.auth_handler.auth_handler.serializer.loads(cookie.value)
    assert parsed_cookie_value == id_token_claims


async def test_oidc_handler_auth_post_id_token_code_2(app: FakeApplication):
    oidc = configure_test_oidc_with_secret(app)
    assert isinstance(oidc, OpenIDConnectHandler)

    # Note: mock the HTTPHandler to simulate a real authorization server that
    # handles a valid request to the token endpoint

    oidc_configuration = await oidc.get_openid_configuration()

    id_token_claims = {
        "aud": oidc.settings.client_id,
        "iss": oidc_configuration.issuer,
        "sub": "4534224f-546f-401f-9cab-067b0b2b9abb",
    }

    async def mocked_post_form(url: str, data: Any):
        assert url == oidc_configuration.token_endpoint

        assert data == {
            "grant_type": "authorization_code",
            "code": "xxx",
            "scope": "openid profile email",
            "redirect_uri": "http://127.0.0.1:8000/authorization-callback",
            "client_id": "067cee45-faf3-4c75-9fef-09f050bcc3ae",
            "client_secret": "JUST_AN_EXAMPLE",
        }

        access_token_claims = {
            "sub": "4534224f-546f-401f-9cab-067b0b2b9abb",
            "aud": "------------------------------------",
            "iss": oidc_configuration.issuer,
        }

        return {
            "id_token": get_token("0", id_token_claims),
            "access_token": get_token("0", access_token_claims),
            "refresh_token": "00000000-0000-0000-0000-000000000000",
        }

    oidc._http_handler.post_form = mocked_post_form

    called = False

    @oidc.events.on_tokens_received
    async def on_tokens_received(context, token_response: TokenResponse):
        nonlocal called
        called = True
        assert token_response.id_token is not None
        assert token_response.access_token is not None
        assert token_response.refresh_token is not None

    content = urlencode({"code": "xxx"}).encode()

    await app(
        get_example_scope(
            "POST",
            oidc.settings.callback_path,
            form_extra_headers(content),
        ),
        MockReceive([content]),
        MockSend(),
    )

    response = app.response
    assert response is not None

    assert called is True
    assert response.status == 302
    assert response.headers.get_single(b"location") == b"/"
    cookie_value = response.headers.get_single(b"set-cookie")

    assert cookie_value is not None
    cookie = parse_cookie(cookie_value)

    # the auth_handler can parse the cookie value:
    assert isinstance(oidc.auth_handler, CookiesOpenIDTokensHandler)
    parsed_cookie_value = oidc.auth_handler.auth_handler.serializer.loads(cookie.value)
    assert parsed_cookie_value == id_token_claims


@pytest.mark.parametrize(
    "original_path,query",
    [
        ("/", {}),
        ("/account", {}),
        ("/product/garden/bench", {"page": 2, "search": "red bench"}),
    ],
)
async def test_redirect_state_includes_original_path(
    app: FakeApplication, original_path, query
):
    """
    Tests the ability to redirect the user to the original path that was requested
    before a redirect to the OIDC sign-in page, using the state parameter.
    """
    oidc = configure_test_oidc_cookie_auth_id_token(app)

    oidc_configuration = await oidc.get_openid_configuration()

    app.use_authorization().with_default_policy(
        Policy("authenticated", AuthenticatedRequirement())
    )

    @app.router.get("/")
    async def home(): ...

    @app.router.get("/account")
    async def account_page(): ...

    @app.router.get("/product/{category}/{name}")
    async def product_details(): ...

    await app.start()
    await app(
        get_example_scope("GET", original_path, [], query=query),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response is not None

    assert response.status == 302
    location = response.headers.get_single(b"location")
    assert b"state=" in location

    url = URL(location)
    query_dict = parse_qs(url.query)
    state_value = query_dict[b"state"][0]
    parsed_state = oidc.parameters_builder.read_state(state_value.decode())
    assert parsed_state.get("orig_path") == original_path + (
        ("?" + urlencode(query)) if query else ""
    )

    # arrange an id_token set by the remote auth server
    id_token_claims = {
        "aud": oidc.settings.client_id,
        "iss": oidc_configuration.issuer,
        "sub": "4534224f-546f-401f-9cab-067b0b2b9abb",
        "nonce": parsed_state.get("nonce"),
    }
    id_token = get_token("0", id_token_claims)
    content = urlencode({"id_token": id_token, "state": state_value}).encode()

    await app(
        get_example_scope(
            "POST",
            oidc.settings.callback_path,
            form_extra_headers(content),
        ),
        MockReceive([content]),
        MockSend(),
    )

    response = app.response
    assert response is not None

    assert response.status == 302
    assert response.headers.get_single(b"location").decode() == original_path + (
        ("?" + urlencode(query)) if query else ""
    )


async def test_raises_for_nonce_mismatch(app: FakeApplication):
    """
    Tests the ability to redirect the user to the original path that was requested
    before a redirect to the OIDC sign-in page, using the state parameter.
    """
    oidc = configure_test_oidc_cookie_auth_id_token(app)

    oidc_configuration = await oidc.get_openid_configuration()

    app.use_authorization().with_default_policy(
        Policy("authenticated", AuthenticatedRequirement())
    )

    @app.router.get("/")
    async def home(): ...

    await app.start()
    await app(
        get_example_scope("GET", "/", []),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response is not None

    assert response.status == 302
    location = response.headers.get_single(b"location")
    assert b"state=" in location

    url = URL(location)
    query_dict = parse_qs(url.query)
    state_value = query_dict[b"state"][0]

    # arrange an id_token set by the remote auth server
    id_token_claims = {
        "aud": oidc.settings.client_id,
        "iss": oidc_configuration.issuer,
        "sub": "4534224f-546f-401f-9cab-067b0b2b9abb",
        "nonce": "this will not match",
    }
    id_token = get_token("0", id_token_claims)
    content = urlencode({"id_token": id_token, "state": state_value}).encode()
    scope = get_example_scope(
        "POST",
        oidc.settings.callback_path,
        form_extra_headers(content),
    )
    request = incoming_request(scope, MockReceive([content]))

    with pytest.raises(OpenIDConnectError) as oidc_error:
        await oidc.handle_auth_redirect(request)

    assert str(oidc_error.value) == "nonce mismatch error"


async def test_raises_for_missing_data(app: FakeApplication):
    oidc = configure_test_oidc_cookie_auth_id_token(app)

    content = urlencode({"invalid": 1}).encode()
    scope = get_example_scope(
        "POST",
        oidc.settings.callback_path,
        form_extra_headers(content),
    )
    request = incoming_request(scope, MockReceive([content]))

    with pytest.raises(BadRequest) as bad_request:
        await oidc.handle_auth_redirect(request)

    assert str(bad_request.value) == "Expected either an error, an id_token, or a code."


async def test_raises_for_failure_in_exchange_token(app: FakeApplication):
    oidc = configure_test_oidc_with_secret(app)

    async def mocked_post_form(*args):
        raise FailedRequestError(-1, "Connection refused")

    oidc._http_handler.post_form = mocked_post_form

    content = urlencode({"code": "xxx"}).encode()
    scope = get_example_scope(
        "POST",
        oidc.settings.callback_path,
        form_extra_headers(content),
    )
    request = incoming_request(scope, MockReceive([content]))

    with pytest.raises(OpenIDConnectFailedExchangeError):
        await oidc.handle_auth_redirect(request)


async def test_refresh_token(app: FakeApplication):
    oidc = configure_test_oidc_with_secret(app)

    async def mocked_post_form(*args):
        return {"access_token": "example AT", "refresh_token": "example RT"}

    oidc._http_handler.post_form = mocked_post_form

    token_response = await oidc.refresh_token("example")
    assert token_response.access_token == "example AT"
    assert token_response.refresh_token == "example RT"


async def test_raises_for_failure_in_refresh_token(app: FakeApplication):
    oidc = configure_test_oidc_with_secret(app)

    async def mocked_post_form(*args):
        raise FailedRequestError(-1, "Connection refused")

    oidc._http_handler.post_form = mocked_post_form

    with pytest.raises(OpenIDConnectFailedExchangeError):
        await oidc.refresh_token("example")


async def test_uses_settings_redirect_error_if_set(app: FakeApplication):
    oidc = configure_test_oidc_with_secret(app)
    oidc.settings.error_redirect_path = "/error-foo"

    response = await oidc.handle_error(
        Request("GET", b"/", None), {"error": "access_denied"}
    )
    assert response.status == 302
    assert response.headers.get_single(b"location").startswith(b"/error-foo")


async def test_raises_for_invalid_id_token(app: FakeApplication):
    """
    Tests handling of forged id_token.
    """
    oidc = configure_test_oidc_cookie_auth_id_token(app)

    oidc_configuration = await oidc.get_openid_configuration()

    # arrange a forged id_token
    id_token_claims = {
        "aud": oidc.settings.client_id,
        "iss": oidc_configuration.issuer,
        "sub": "4534224f-546f-401f-9cab-067b0b2b9abb",
        "nonce": "this will not match",
    }

    for forged_id_token in [
        get_token("foreign", id_token_claims),
        get_token("foreign", id_token_claims, fake_kid="0"),
    ]:
        content = urlencode({"id_token": forged_id_token}).encode()
        scope = get_example_scope(
            "POST",
            oidc.settings.callback_path,
            form_extra_headers(content),
        )
        request = incoming_request(scope, MockReceive([content]))

        with pytest.raises(Unauthorized) as invalid_token:
            await oidc.handle_auth_redirect(request)

        assert str(invalid_token.value).startswith("Invalid id_token:")


def test_parameters_builder_raises_for_missing_secret():
    builder = ParametersBuilder(OpenIDSettings(client_id="1"))

    with pytest.raises(MissingClientSecretSettingError):
        builder.build_refresh_token_parameters("foo")


def test_parameters_builder_raises_for_invalid_state():
    builder = ParametersBuilder(OpenIDSettings(client_id="1"))

    with pytest.raises(BadRequest) as bad_request:
        builder.read_state("invalid")

    assert str(bad_request.value) == "Invalid state"


async def test_oidc_handler_with_secret_and_audience_no_id_token(
    app: FakeApplication,
):
    """
    Tests the ability to handle OIDC integration when no id_token is required, but only
    an access token to access an API. In this case, an audience parameter is configured
    (applies, for example, to Auth0 and Okta).
    """
    oidc = use_openid_connect(
        app,
        OpenIDSettings(
            client_id="067cee45-faf3-4c75-9fef-09f050bcc3ae",
            client_secret="JUST_AN_EXAMPLE",
            audience="api://default",
            authority=MOCKED_AUTHORITY,
            scope="read:todos",
        ),
    )

    # Note: mock the HTTPHandler to simulate a real authorization server that
    # handles a valid request to the token endpoint

    oidc_configuration = await oidc.get_openid_configuration()

    await app(
        get_example_scope(
            "GET",
            oidc.settings.entry_path,
            [],
        ),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response is not None

    assert response.status == 302
    location = response.headers.get_single(b"location")
    assert b"audience=" in location

    async def mocked_post_form(url: str, data: Any):
        assert url == oidc_configuration.token_endpoint

        access_token_claims = {
            "sub": "4534224f-546f-401f-9cab-067b0b2b9abb",
            "aud": "------------------------------------",
            "scp": "read:todos",
            "iss": oidc_configuration.issuer,
        }

        return {
            "access_token": get_token("0", access_token_claims),
            "refresh_token": "00000000-0000-0000-0000-000000000000",
        }

    oidc._http_handler.post_form = mocked_post_form

    content = urlencode({"code": "xxx"}).encode()

    await app(
        get_example_scope(
            "POST",
            oidc.settings.callback_path,
            form_extra_headers(content),
        ),
        MockReceive([content]),
        MockSend(),
    )

    response = app.response
    assert response is not None

    assert response.status == 302
    assert response.headers.get_single(b"location") == b"/"
    cookie_value = response.headers.get_single(b"set-cookie")

    assert cookie_value is not None
    cookie = parse_cookie(cookie_value)

    assert isinstance(oidc.auth_handler, CookiesOpenIDTokensHandler)
    parsed_cookie_value = oidc.auth_handler.auth_handler.serializer.loads(cookie.value)
    assert parsed_cookie_value == {}


async def test_oidc_handler_auth_post_id_token_code_3(app: FakeApplication):
    """With token store"""
    oidc = configure_test_oidc_with_secret(app)
    assert isinstance(oidc.auth_handler, CookiesOpenIDTokensHandler)
    oidc.auth_handler.tokens_store = CookiesTokensStore(oidc.settings.scheme_name)

    assert oidc.auth_handler.tokens_store.scheme_name == oidc.settings.scheme_name

    # Note: mock the HTTPHandler to simulate a real authorization server that
    # handles a valid request to the token endpoint

    oidc_configuration = await oidc.get_openid_configuration()

    id_token_claims = {
        "aud": oidc.settings.client_id,
        "iss": oidc_configuration.issuer,
        "sub": "4534224f-546f-401f-9cab-067b0b2b9abb",
    }

    async def mocked_post_form(*args):
        access_token_claims = {
            "sub": "4534224f-546f-401f-9cab-067b0b2b9abb",
            "aud": "------------------------------------",
            "iss": oidc_configuration.issuer,
        }

        return {
            "id_token": get_token("0", id_token_claims),
            "access_token": get_token("0", access_token_claims),
            "refresh_token": "00000000-0000-0000-0000-000000000000",
        }

    oidc._http_handler.post_form = mocked_post_form

    content = urlencode({"code": "xxx"}).encode()

    await app(
        get_example_scope(
            "POST",
            oidc.settings.callback_path,
            form_extra_headers(content),
        ),
        MockReceive([content]),
        MockSend(),
    )

    response = app.response
    assert response is not None

    assert response.status == 302
    assert response.headers.get_single(b"location") == b"/"
    cookies_values = response.headers[b"set-cookie"]

    assert len(cookies_values) == 3

    names = set()
    for cookie_value in cookies_values:
        cookie = parse_cookie(cookie_value)
        names.add(cookie.name)

    scheme = oidc.settings.scheme_name.lower()
    assert names == {scheme, f"{scheme}.at", f"{scheme}.rt"}


async def test_cookies_tokens_store_restoring_context(
    app: FakeApplication,
):
    tokens_store = CookiesTokensStore()
    oidc = use_openid_connect(
        app,
        OpenIDSettings(
            client_id="067cee45-faf3-4c75-9fef-09f050bcc3ae",
            client_secret="JUST_AN_EXAMPLE",
            authority=MOCKED_AUTHORITY,
        ),
        auth_handler=CookiesOpenIDTokensHandler(
            CookieAuthentication(
                cookie_name="OpenIDConnect".lower(), auth_scheme="OpenIDConnect"
            ),
            tokens_store=tokens_store,
        ),
    )

    access_token = tokens_store.serializer.dumps("secret")
    refresh_token = tokens_store.serializer.dumps("secret-refresh")

    assert isinstance(access_token, str)
    assert isinstance(refresh_token, str)

    scheme = oidc.settings.scheme_name.lower()
    request = incoming_request(
        get_example_scope(
            "GET",
            "/",
            cookies={scheme + ".at": access_token, scheme + ".rt": refresh_token},
        )
    )

    request.user = Identity({})
    await tokens_store.restore_tokens(request)

    assert request.user.access_token == "secret"
    assert request.user.refresh_token == "secret-refresh"


async def test_cookies_tokens_store_discards_invalid_tokens(
    app: FakeApplication,
):
    oidc = configure_test_oidc_with_secret(app)
    assert isinstance(oidc.auth_handler, CookiesOpenIDTokensHandler)
    tokens_store = CookiesTokensStore(oidc.settings.scheme_name)
    oidc.auth_handler.tokens_store = tokens_store

    access_token = "invalid"
    refresh_token = "invalid"

    scheme = oidc.settings.scheme_name.lower()
    request = incoming_request(
        get_example_scope(
            "GET",
            "/",
            cookies={scheme + ".at": access_token, scheme + ".rt": refresh_token},
        )
    )

    request.user = Identity({})
    await tokens_store.restore_tokens(request)

    assert getattr(request.user, "access_token", None) is None
    assert getattr(request.user, "refresh_token", None) is None


async def test_cookies_tokens_store_handle_missing_cookies(
    app: FakeApplication,
):
    oidc = configure_test_oidc_with_secret(app)
    tokens_store = CookiesTokensStore(oidc.settings.scheme_name)
    oidc.auth_handler.tokens_store = tokens_store

    request = incoming_request(
        get_example_scope(
            "GET",
            "/",
        )
    )

    request.user = Identity({})
    await tokens_store.restore_tokens(request)

    assert getattr(request.user, "access_token", None) is None
    assert getattr(request.user, "refresh_token", None) is None


async def test_oidc_handler_auth_post_error(app: FakeApplication):
    oidc = configure_test_oidc_cookie_auth_id_token(app)
    assert isinstance(oidc, OpenIDConnectHandler)

    called = False

    @oidc.events.on_error
    async def on_error(*args):
        nonlocal called
        called = True

    content = urlencode({"error": "access_denied"}).encode()

    await app(
        get_example_scope(
            "POST",
            oidc.settings.callback_path,
            form_extra_headers(content),
        ),
        MockReceive([content]),
        MockSend(),
    )

    response = app.response
    assert response is not None

    assert called is True
    assert response.status == 302
    assert response.headers.get_single(b"location") == b"/?error=access_denied"


async def test_oidc_handler_handling_request_without_host_header(
    app: FakeApplication,
):
    oidc = configure_test_oidc_cookie_auth_id_token(app)

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


async def test_default_openid_connect_handler_redirects_unauthenticated_users(
    app: FakeApplication,
):
    oidc = configure_test_oidc_cookie_auth_id_token(app)

    app.use_authorization().with_default_policy(
        Policy("authenticated", AuthenticatedRequirement())
    )

    @app.router.get("/account")
    def get_account_details(): ...

    @app.router.get("/requirement")
    def example():
        raise Unauthorized()

    await app.start()
    await app(get_example_scope("GET", "/account"), MockReceive(), MockSend())

    assert_redirect_to_sign_in(app.response)

    # if the user is authenticated, but not authorized to do something,
    # then the server should not redirect to the sign-in page
    assert isinstance(oidc.auth_handler, CookiesOpenIDTokensHandler)
    await app(
        get_example_scope(
            "GET",
            "/requirement",
            [
                (
                    b"cookie",
                    get_auth_cookie(
                        oidc.auth_handler.auth_handler,
                        {"id": 1, "email": "example@neoteroi.dev"},
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


async def test_oidc_handler_logout_endpoint(
    app: FakeApplication,
):
    oidc = configure_test_oidc_cookie_auth_id_token(app)

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
    assert cookie.expires < utcnow()


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


def test_raises_for_missing_authority_and_discovery_endpoint():
    handler = OpenIDConnectHandler(
        OpenIDSettings(client_id="1"), auth_handler=CookiesOpenIDTokensHandler()
    )

    with pytest.raises(OpenIDConnectConfigurationError):
        handler.get_well_known_openid_configuration_url()


async def test_raises_for_failed_request_to_fetch_openid_configuration():
    handler = OpenIDConnectHandler(
        OpenIDSettings(client_id="1", discovery_endpoint="http://localhost:44123"),
        auth_handler=CookiesOpenIDTokensHandler(),
    )

    with pytest.raises(OpenIDConnectRequestError):
        await handler.fetch_openid_configuration()


async def test_oidc_handler_auth_post_without_input(app: FakeApplication):
    oidc = configure_test_oidc_cookie_auth_id_token(app)
    assert isinstance(oidc, OpenIDConnectHandler)

    await app(
        get_example_scope(
            "POST",
            oidc.settings.callback_path,
        ),
        MockReceive(),
        MockSend(),
    )

    response = app.response
    assert response is not None

    assert response.status == 202  # accepted


async def test_logout_cookie_handler_unset_tokens():
    tokens_store = FakeTokensStore()
    tokens_store.unset_tokens = AsyncMock()
    handler = CookiesOpenIDTokensHandler(tokens_store=tokens_store)
    logout_request = Request("GET", b"/logout", [])
    await handler.get_logout_response(logout_request, "/")

    assert tokens_store.unset_tokens.call_count == 1
    assert tokens_store.unset_tokens.call_args == ((logout_request,),)


async def test_jwt_handler_get_logout_response():
    handler = JWTOpenIDTokensHandler(
        JWTBearerAuthentication(
            authority=MOCKED_AUTHORITY,
            valid_audiences=["NULL"],
        )
    )
    logout_request = Request("GET", b"/logout", [])
    response = await handler.get_logout_response(logout_request, "/")

    html = response.content.body.decode("utf8")  # type: ignore
    assert 'sessionStorage.setItem("ID_TOKEN", ""' in html
    assert 'sessionStorage.setItem("ACCESS_TOKEN", "");' in html
    assert 'sessionStorage.setItem("REFRESH_TOKEN", "");' in html


async def test_jwt_handler_get_refresh_tokens_response():
    handler = JWTOpenIDTokensHandler(
        JWTBearerAuthentication(
            authority=MOCKED_AUTHORITY,
            valid_audiences=["NULL"],
        )
    )
    response = await handler.get_refresh_tokens_response(
        Request("POST", b"/example", []),
        TokenResponse(
            {"id_token": "example", "access_token": "a", "refresh_token": "b"}
        ),
    )

    assert isinstance(response.content, Content)
    assert response.content.type == b"application/json"
    raw_json = response.content.body  # type: ignore

    assert b'"id_token":"example"' in raw_json
    assert b'"access_token":"a"' in raw_json

    # the refresh token must be protected
    assert b'"refresh_token":"b"' not in raw_json
    assert b'"refresh_token":"' in raw_json

    data = json.loads(raw_json.decode("utf8"))
    assert handler._serializer.loads(data["refresh_token"]) == "b"


async def test_jwt_handler_restore_refresh_token():
    handler = JWTOpenIDTokensHandler(
        JWTBearerAuthentication(
            authority=MOCKED_AUTHORITY,
            valid_audiences=["NULL"],
        )
    )
    context = Request(
        "GET",
        b"/",
        [(b"X-Refresh-Token", handler.protect_refresh_token("Example").encode())],
    )

    handler.restore_refresh_token(context)
    assert context.user is not None
    assert context.user.refresh_token == "Example"


def test_id_token_value():
    id_token = IDToken("x", {})
    assert id_token.value == "x"
    assert str(id_token) == "x"
