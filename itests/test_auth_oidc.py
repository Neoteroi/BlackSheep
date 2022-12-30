"""
This module is under integration tests folder because it uses a partially faked
authorization server in a running Flask server.
"""
from datetime import datetime
from typing import Any, List, Optional, Tuple
from urllib.parse import parse_qs, urlencode

import pytest

from neoteroi.auth import Identity, Policy
from neoteroi.auth.common import AuthenticatedRequirement
from neoteroi.web.cookies import parse_cookie
from neoteroi.web.exceptions import BadRequest, Unauthorized
from neoteroi.web.messages import Request, Response
from neoteroi.web.server.application import Application
from neoteroi.web.server.asgi import incoming_request
from neoteroi.web.server.authentication.cookie import CookieAuthentication
from neoteroi.web.server.authentication.oidc import (
    CookiesTokensStore,
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
    use_openid_connect,
)
from neoteroi.web.testing.helpers import get_example_scope
from neoteroi.web.testing.messages import MockReceive, MockSend
from neoteroi.web.url import URL
from neoteroi.web.utils.aio import FailedRequestError
from tests.test_auth import get_access_token
from tests.test_auth_cookie import get_auth_cookie
from tests.utils.application import FakeApplication

from .client_fixtures import *  # NoQA

MOCKED_AUTHORITY = "http://127.0.0.1:44777/oidc"


@pytest.fixture
def app():
    return FakeApplication()


def configure_test_oidc_implicit_id_token(app: Application):
    return use_openid_connect(
        app,
        OpenIDSettings(
            client_id="067cee45-faf3-4c75-9fef-09f050bcc3ae",
            authority=MOCKED_AUTHORITY,
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


@pytest.mark.asyncio
async def test_oidc_handler_redirect(app: FakeApplication):
    oidc = configure_test_oidc_implicit_id_token(app)
    assert isinstance(oidc, OpenIDConnectHandler)

    await app(
        get_example_scope("GET", oidc.settings.entry_path), MockReceive(), MockSend()
    )

    assert_redirect_to_sign_in(app.response)


@pytest.mark.asyncio
async def test_oidc_handler_redirect_with_secret(app: FakeApplication):
    oidc = configure_test_oidc_with_secret(app)
    assert isinstance(oidc, OpenIDConnectHandler)

    await app(
        get_example_scope("GET", oidc.settings.entry_path), MockReceive(), MockSend()
    )

    assert_redirect_to_sign_in(app.response, has_secret=True)


@pytest.mark.asyncio
async def test_oidc_handler_auth_post_id_token(app: FakeApplication):
    oidc = configure_test_oidc_implicit_id_token(app)
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
    id_token = get_access_token("0", claims)
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
    parsed_cookie_value = oidc._auth_handler.serializer.loads(cookie.value)
    assert parsed_cookie_value == claims


@pytest.mark.asyncio
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
            "access_token": get_access_token("0", access_token_claims),
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
    id_token = get_access_token("0", id_token_claims)
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
    parsed_cookie_value = oidc._auth_handler.serializer.loads(cookie.value)
    assert parsed_cookie_value == id_token_claims


@pytest.mark.asyncio
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
            "id_token": get_access_token("0", id_token_claims),
            "access_token": get_access_token("0", access_token_claims),
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
    parsed_cookie_value = oidc._auth_handler.serializer.loads(cookie.value)
    assert parsed_cookie_value == id_token_claims


@pytest.mark.parametrize(
    "original_path,query",
    [
        ("/", {}),
        ("/account", {}),
        ("/product/garden/bench", {"page": 2, "search": "red bench"}),
    ],
)
@pytest.mark.asyncio
async def test_redirect_state_includes_original_path(
    app: FakeApplication, original_path, query
):
    """
    Tests the ability to redirect the user to the original path that was requested
    before a redirect to the OIDC sign-in page, using the state parameter.
    """
    oidc = configure_test_oidc_implicit_id_token(app)

    oidc_configuration = await oidc.get_openid_configuration()

    app.use_authorization().with_default_policy(
        Policy("authenticated", AuthenticatedRequirement())
    )

    @app.router.get("/")
    async def home():
        ...

    @app.router.get("/account")
    async def account_page():
        ...

    @app.router.get("/product/{category}/{name}")
    async def product_details():
        ...

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
    id_token = get_access_token("0", id_token_claims)
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


@pytest.mark.asyncio
async def test_raises_for_nonce_mismatch(app: FakeApplication):
    """
    Tests the ability to redirect the user to the original path that was requested
    before a redirect to the OIDC sign-in page, using the state parameter.
    """
    oidc = configure_test_oidc_implicit_id_token(app)

    oidc_configuration = await oidc.get_openid_configuration()

    app.use_authorization().with_default_policy(
        Policy("authenticated", AuthenticatedRequirement())
    )

    @app.router.get("/")
    async def home():
        ...

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
    id_token = get_access_token("0", id_token_claims)
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


@pytest.mark.asyncio
async def test_raises_for_missing_data(app: FakeApplication):
    oidc = configure_test_oidc_implicit_id_token(app)

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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
async def test_refresh_token(app: FakeApplication):
    oidc = configure_test_oidc_with_secret(app)

    async def mocked_post_form(*args):
        return {"access_token": "example AT", "refresh_token": "example RT"}

    oidc._http_handler.post_form = mocked_post_form

    token_response = await oidc.refresh_token("example")
    assert token_response.access_token == "example AT"
    assert token_response.refresh_token == "example RT"


@pytest.mark.asyncio
async def test_raises_for_failure_in_refresh_token(app: FakeApplication):
    oidc = configure_test_oidc_with_secret(app)

    async def mocked_post_form(*args):
        raise FailedRequestError(-1, "Connection refused")

    oidc._http_handler.post_form = mocked_post_form

    with pytest.raises(OpenIDConnectFailedExchangeError):
        await oidc.refresh_token("example")


@pytest.mark.asyncio
async def test_uses_settings_redirect_error_if_set(app: FakeApplication):
    oidc = configure_test_oidc_with_secret(app)
    oidc.settings.error_redirect_path = "/error-foo"

    response = await oidc.handle_error(
        Request("GET", b"/", None), {"error": "access_denied"}
    )
    assert response.status == 302
    assert response.headers.get_single(b"location").startswith(b"/error-foo")


@pytest.mark.asyncio
async def test_raises_for_invalid_id_token(app: FakeApplication):
    """
    Tests handling of forged id_token.
    """
    oidc = configure_test_oidc_implicit_id_token(app)

    oidc_configuration = await oidc.get_openid_configuration()

    # arrange a forged id_token
    id_token_claims = {
        "aud": oidc.settings.client_id,
        "iss": oidc_configuration.issuer,
        "sub": "4534224f-546f-401f-9cab-067b0b2b9abb",
        "nonce": "this will not match",
    }

    for forged_id_token in [
        get_access_token("foreign", id_token_claims),
        get_access_token("foreign", id_token_claims, fake_kid="0"),
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


@pytest.mark.asyncio
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
            "access_token": get_access_token("0", access_token_claims),
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

    parsed_cookie_value = oidc._auth_handler.serializer.loads(cookie.value)
    assert parsed_cookie_value == {}


@pytest.mark.asyncio
async def test_oidc_handler_auth_post_id_token_code_3(app: FakeApplication):
    """With token store"""
    oidc = configure_test_oidc_with_secret(app)
    oidc.tokens_store = CookiesTokensStore(oidc.settings.scheme_name)

    assert oidc.tokens_store.scheme_name == oidc.settings.scheme_name

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
            "id_token": get_access_token("0", id_token_claims),
            "access_token": get_access_token("0", access_token_claims),
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


@pytest.mark.asyncio
async def test_cookies_tokens_store_restoring_context(
    app: FakeApplication,
):
    oidc = use_openid_connect(
        app,
        OpenIDSettings(
            client_id="067cee45-faf3-4c75-9fef-09f050bcc3ae",
            client_secret="JUST_AN_EXAMPLE",
            authority=MOCKED_AUTHORITY,
        ),
        tokens_store=CookiesTokensStore(),
    )
    assert oidc.tokens_store in app.middlewares

    assert isinstance(oidc.tokens_store, CookiesTokensStore)
    access_token = oidc.tokens_store.serializer.dumps("secret")
    refresh_token = oidc.tokens_store.serializer.dumps("secret-refresh")

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

    request.identity = Identity({})
    await oidc.tokens_store.restore_tokens(request)

    assert request.identity.access_token == "secret"
    assert request.identity.refresh_token == "secret-refresh"

    request = incoming_request(
        get_example_scope(
            "GET",
            "/",
            cookies={scheme + ".at": access_token, scheme + ".rt": refresh_token},
        )
    )

    request.identity = Identity({})

    async def handler(*args):
        pass

    await oidc.tokens_store(request, handler)  # middleware way

    assert request.identity.access_token == "secret"
    assert request.identity.refresh_token == "secret-refresh"


@pytest.mark.asyncio
async def test_cookies_tokens_store_discards_invalid_tokens(
    app: FakeApplication,
):
    oidc = configure_test_oidc_with_secret(app)
    oidc.tokens_store = CookiesTokensStore(oidc.settings.scheme_name)

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

    request.identity = Identity({})
    await oidc.tokens_store.restore_tokens(request)

    assert getattr(request.identity, "access_token", None) is None
    assert getattr(request.identity, "refresh_token", None) is None


@pytest.mark.asyncio
async def test_cookies_tokens_store_handle_missing_cookies(
    app: FakeApplication,
):
    oidc = configure_test_oidc_with_secret(app)
    oidc.tokens_store = CookiesTokensStore(oidc.settings.scheme_name)

    request = incoming_request(
        get_example_scope(
            "GET",
            "/",
        )
    )

    request.identity = Identity({})
    await oidc.tokens_store.restore_tokens(request)

    assert getattr(request.identity, "access_token", None) is None
    assert getattr(request.identity, "refresh_token", None) is None


@pytest.mark.asyncio
async def test_oidc_handler_auth_post_error(app: FakeApplication):
    oidc = configure_test_oidc_implicit_id_token(app)
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


@pytest.mark.asyncio
async def test_oidc_handler_handling_request_without_host_header(
    app: FakeApplication,
):
    oidc = configure_test_oidc_implicit_id_token(app)

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
    oidc = configure_test_oidc_implicit_id_token(app)

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
async def test_oidc_handler_logout_endpoint(
    app: FakeApplication,
):
    oidc = configure_test_oidc_implicit_id_token(app)

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


def test_raises_for_missing_authority_and_discovery_endpoint():
    handler = OpenIDConnectHandler(
        OpenIDSettings(client_id="1"), auth_handler=CookieAuthentication()
    )

    with pytest.raises(OpenIDConnectConfigurationError):
        handler.get_well_known_openid_configuration_url()


@pytest.mark.asyncio
async def test_raises_for_failed_request_to_fetch_openid_configuration():
    handler = OpenIDConnectHandler(
        OpenIDSettings(client_id="1", discovery_endpoint="http://localhost:44123"),
        auth_handler=CookieAuthentication(),
    )

    with pytest.raises(OpenIDConnectRequestError):
        await handler.fetch_openid_configuration()


@pytest.mark.asyncio
async def test_oidc_handler_auth_post_without_input(app: FakeApplication):
    oidc = configure_test_oidc_implicit_id_token(app)
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
