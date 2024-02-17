"""
This module provides classes to handle OpenID Connect authentication through integration
with OAuth applications, supporting Authorization Code Grant and Hybrid flows.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, AnyStr, Awaitable, Callable, Dict, Optional, Sequence
from urllib.parse import urlencode

import jwt
from guardpost import AuthenticationHandler, Identity, UnauthorizedError
from guardpost.jwts import InvalidAccessToken, JWTValidator
from itsdangerous import Serializer
from itsdangerous.exc import BadSignature
from jwt import InvalidTokenError

from blacksheep.cookies import Cookie
from blacksheep.exceptions import BadRequest, Unauthorized
from blacksheep.messages import Request, Response, get_absolute_url_to_path
from blacksheep.server.application import Application, ApplicationEvent
from blacksheep.server.authentication.cookie import CookieAuthentication
from blacksheep.server.authentication.jwt import JWTBearerAuthentication
from blacksheep.server.authorization import allow_anonymous
from blacksheep.server.dataprotection import generate_secret, get_serializer
from blacksheep.server.headers.cache import cache_control
from blacksheep.server.responses import accepted, bad_request, html, json, ok, redirect
from blacksheep.utils import ensure_str
from blacksheep.utils.aio import FailedRequestError, HTTPHandler


def get_logger() -> logging.Logger:
    logger = logging.getLogger("blacksheep.oidc")
    logger.setLevel(logging.INFO)
    return logger


logger = get_logger()


class OpenIDConfiguration:
    """
    Proxy class for a remote OpenID Connect well-known configuration.
    """

    def __init__(self, data) -> None:
        self._data = data

    @property
    def issuer(self) -> str:
        return self._data["issuer"]

    @property
    def jwks_uri(self) -> str:
        return self._data["jwks_uri"]

    @property
    def authorization_endpoint(self) -> str:
        return self._data["authorization_endpoint"]

    @property
    def token_endpoint(self) -> str:
        return self._data["token_endpoint"]

    @property
    def end_session_endpoint(self) -> Optional[str]:
        return self._data.get("end_session_endpoint")


class OpenIDConnectEvent(ApplicationEvent):
    pass


class OpenIDConnectEvents:
    on_id_token_validated: OpenIDConnectEvent
    on_tokens_received: OpenIDConnectEvent
    on_error: OpenIDConnectEvent

    def __init__(self, context) -> None:
        self.on_tokens_received = OpenIDConnectEvent(context)
        self.on_id_token_validated = OpenIDConnectEvent(context)
        self.on_error = OpenIDConnectEvent(context)


@dataclass
class OpenIDSettings:
    client_id: str
    authority: Optional[str] = None
    audience: Optional[str] = None
    client_secret: Optional[str] = None
    discovery_endpoint: Optional[str] = None
    entry_path: str = "/sign-in"
    logout_path: str = "/sign-out"
    post_logout_redirect_path: str = "/"
    callback_path: str = "/authorization-callback"
    refresh_token_path: str = "/refresh-token"
    response_type: str = "code"
    scope: str = "openid profile email"
    redirect_uri: Optional[str] = None
    scheme_name: str = "OpenIDConnect"
    error_redirect_path: Optional[str] = None
    end_session_endpoint: Optional[str] = None


class OpenIDSettingsError(TypeError):
    def __init__(self, message: str) -> None:
        super().__init__(message)


class MissingClientSecretSettingError(OpenIDSettingsError):
    def __init__(self) -> None:
        super().__init__(
            "Missing application client secret, to use the Authorization Code Grant "
            "flow, it is necessary to configure an application secret."
        )


def _get_desired_path(request: Request) -> str:
    base_path = request.base_path
    path = request.path
    query_part = (
        "" if not request.url.query else ("?" + request.url.query.decode("utf8"))
    )
    return f"{base_path}{path}{query_part}"


class ParametersBuilder:
    def __init__(self, settings: OpenIDSettings) -> None:
        self._settings = settings
        self._serializer = get_serializer(purpose=f"{settings.scheme_name}state")

    @property
    def scope(self) -> str:
        return self._settings.scope

    def get_state(self, request: Request) -> Dict[str, str]:
        desired_path = (
            "/"
            if request.path == self._settings.entry_path
            else _get_desired_path(request)
        )
        return {"orig_path": desired_path, "nonce": generate_secret(8)}

    def read_state(self, state: str) -> Dict[str, str]:
        try:
            return self._serializer.loads(state)
        except BadSignature as signature_error:
            logger.error(
                "Failed to parse the request state (%s), invalid signature.",
                str(signature_error),
            )
            raise BadRequest("Invalid state")

    def get_redirect_url(self, request: Request) -> str:
        return str(get_absolute_url_to_path(request, self._settings.callback_path))

    def build_signin_parameters(self, request: Request):
        if self._settings.client_secret:
            # authorization code grant
            response_type = "code"
        else:
            # hybrid flow, requires implicit flow for id_token to be enabled
            response_type = "id_token"

        state = self.get_state(request)
        parameters = {
            "response_type": response_type,
            "response_mode": "form_post",
            "scope": self.scope,
            "client_id": self._settings.client_id,
            "redirect_uri": self._settings.redirect_uri
            or self.get_redirect_url(request),
            "nonce": state.get("nonce") or generate_secret(8),
        }

        if self._settings.audience:
            # Note: Auth0 and Okta use `audience` parameter when
            # the scope includes custom scopes
            parameters["audience"] = self._settings.audience

        if state:
            parameters["state"] = self._serializer.dumps(state)  # type: ignore

        return parameters

    def _require_secret(self):
        if not self._settings.client_secret:
            raise MissingClientSecretSettingError()

    def build_code_grant_parameters(self, request: Request, code: str):
        self._require_secret()

        return {
            "grant_type": "authorization_code",
            "code": code,
            "scope": self.scope,
            "redirect_uri": self._settings.redirect_uri
            or self.get_redirect_url(request),
            "client_id": self._settings.client_id,
            "client_secret": self._settings.client_secret,
        }

    def build_refresh_token_parameters(self, refresh_token: str):
        self._require_secret()

        return {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self._settings.client_id,
            "client_secret": self._settings.client_secret,
        }


class OpenIDConnectError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)


class OpenIDConnectConfigurationError(OpenIDConnectError):
    """
    Exception thrown when there is an error in the programmer's
    defined configuration.
    """


class OpenIDConnectRequestError(OpenIDConnectError):
    def __init__(
        self,
        request_error: FailedRequestError,
        message: str = "Failed web request to the OpenIDConnect provider.",
    ) -> None:
        super().__init__(message + " " + str(request_error))
        self.request_error = request_error


class OpenIDConnectFailedExchangeError(OpenIDConnectRequestError):
    def __init__(
        self,
        request_error: FailedRequestError,
        message: str = (
            "Failed token exchange web request to the OpenIDConnect provider."
        ),
    ) -> None:
        super().__init__(request_error, message=message)


class TokenResponse:
    __slots__ = ("data",)

    def __init__(self, data) -> None:
        self.data = data

    def __repr__(self) -> str:
        return repr(self.data)

    def __str__(self) -> str:
        return str(self.data)

    @property
    def expires_in(self) -> Optional[int]:
        value = self.data.get("expires_in")
        return int(value) if value else None

    @property
    def expires_on(self) -> Optional[int]:
        value = self.data.get("expires_on")
        return int(value) if value else None

    @property
    def token_type(self) -> Optional[str]:
        return self.data.get("token_type")

    @property
    def id_token(self) -> Optional[str]:
        return self.data.get("id_token")

    @property
    def access_token(self) -> Optional[str]:
        return self.data.get("access_token")

    @property
    def refresh_token(self) -> Optional[str]:
        return self.data.get("refresh_token")


@dataclass
class IDToken:
    """
    Stores information about an id_token that was
    obtained and validated: both the original id_token and
    parsed payload.
    """

    value: str
    data: dict

    def __str__(self) -> str:
        return self.value

    @classmethod
    def from_trusted_token(cls, token):
        return cls(
            value=token, data=jwt.decode(token, options={"verify_signature": False})
        )


class TokensStore(ABC):
    """
    Base abstract class for types that can store and restore access tokens and refresh
    tokens in the context of a web request.
    """

    @abstractmethod
    async def store_tokens(
        self,
        request: Request,
        response: Response,
        access_token: str,
        refresh_token: Optional[str],
    ):
        """
        Applies a strategy to store an access token and an optional refresh token for
        the given request and response.
        """

    @abstractmethod
    async def restore_tokens(self, request: Request):
        """
        Applies a strategy to restore an access token and an optional refresh token for
        the given request.
        """

    async def unset_tokens(self, request: Request):
        """
        Optional method, to unset access tokens upon sign-out.
        """


class OpenIDTokensHandler(AuthenticationHandler):
    """
    Abstract type that can handle tokens for requests and responses for the
    OpenID Connect flow. This class is responsible of communicating tokens
    to clients, and restoring tokens context for following requests.
    Handled tokens can be:
    - id_token(s), access_token(s), refresh_token(s)
    """

    @abstractmethod
    async def get_success_response(
        self,
        request: Request,
        id_token: IDToken,
        token_response: Optional[TokenResponse],
        original_path: str,
    ) -> Response:
        """
        Creates the response after a successful sign-in, used to communicate the
        tokens to the client.
        """

    @abstractmethod
    async def get_refresh_tokens_response(
        self,
        request: Request,
        tokens_response: TokenResponse,
    ) -> Response:
        """
        Creates the response after a successful request to refresh tokens, used to
        communicate new tokens to the client.
        """

    @abstractmethod
    async def get_logout_response(
        self, request: Request, post_logout_redirect_path: str
    ) -> Response:
        """
        Creates the response for a log-out / sign-out event.
        """


class CookiesOpenIDTokensHandler(OpenIDTokensHandler):
    """
    Default authentication handler used in OpenID Connect flows. This class uses a
    cookie to set user context (encrypting data read from validated id_tokens) and
    reads the same cookie to restore user context at each following web request.
    Cookie expiration is configured automatically from id_token `exp` claim.

    IMPORTANT: this class is not able to store all tokens when the flow is configured to
    obtain an id_token, an access_token, and a refresh_token because they would exceed
    the maximum cookie size.
    """

    def __init__(
        self,
        auth_handler: Optional[CookieAuthentication] = None,
        tokens_store: Optional["TokensStore"] = None,
    ) -> None:
        self.auth_handler = (
            auth_handler if auth_handler is not None else CookieAuthentication()
        )
        self.tokens_store = tokens_store
        self._serializer = get_serializer(purpose="oidc-tokens-protection")

    async def get_success_response(
        self,
        request: Request,
        id_token: IDToken,
        token_response: Optional[TokenResponse],
        original_path: str,
    ) -> Response:
        """
        Returns a redirect response that includes Set-Cookie headers
        to configure an encrypted id_token and, optionally, also encrypted
        access_token and refresh_token.
        """
        response = redirect(original_path)
        await self._set_tokens_in_response(request, response, id_token, token_response)
        return response

    async def get_refresh_tokens_response(
        self,
        request: Request,
        tokens_response: TokenResponse,
    ) -> Response:
        response = ok()
        await self._set_tokens_in_response(
            request,
            response,
            IDToken.from_trusted_token(tokens_response.id_token),
            tokens_response,
        )
        return response

    async def _set_tokens_in_response(
        self,
        request: Request,
        response: Response,
        id_token: IDToken,
        token_response: TokenResponse,
    ):
        self.auth_handler.set_cookie(
            id_token.data, response, secure=request.scheme == "https"
        )

        if (
            token_response is not None
            and self.tokens_store
            and token_response.access_token is not None
        ):
            # ability to store access and refresh tokens
            await self.tokens_store.store_tokens(
                request,
                response,
                token_response.access_token,
                token_response.refresh_token,
            )

    async def get_logout_response(
        self, request: Request, post_logout_redirect_path: str
    ) -> Response:
        response = redirect(post_logout_redirect_path)
        self.auth_handler.unset_cookie(response)
        if self.tokens_store is not None:
            await self.tokens_store.unset_tokens(request)
        return response

    async def authenticate(self, context: Request) -> Optional[Identity]:
        await self.auth_handler.authenticate(context)

        if self.tokens_store:
            await self.tokens_store.restore_tokens(context)


class HTMLStorageType(Enum):
    SESSION = "sessionStorage"
    LOCAL = "localStorage"


class JWTOpenIDTokensHandler(OpenIDTokensHandler):
    """
    OpenID Connect authentication handler that uses HTML documents and the HTML5 storage
    API to exchange tokens with the client. This class doesn't use any cookie to
    configure user context, and expects an instance of JWTBearerAuthentication to
    authenticate users using JWT Bearer tokens that the client will include in each web
    request. This class enables more advanced scenarios for authenticating users, with
    the benefit that APIs can be reused more efficiently (as they don't require
    anti-forgery measures anymore) and handle `Authorization: Bearer ...` headers
    instead, but the negative side that automatic redirects are less useful.
    """

    def __init__(
        self,
        auth_handler: JWTBearerAuthentication,
        *,
        id_token_key: str = "ID_TOKEN",
        access_token_key: str = "ACCESS_TOKEN",
        refresh_token_key: str = "REFRESH_TOKEN",
        storage_type: HTMLStorageType = HTMLStorageType.SESSION,
        redirect_timeout: int = 50,
    ) -> None:
        self.auth_handler = auth_handler
        self.id_token_key = id_token_key
        self.access_token_key = access_token_key
        self.refresh_token_key = refresh_token_key
        self.storage_type = storage_type
        self.redirect_timeout = redirect_timeout
        self._serializer = get_serializer(purpose="oidc-tokens-protection")

    async def get_success_response(
        self,
        request: Request,
        id_token: IDToken,
        token_response: Optional[TokenResponse],
        original_path: str,
    ) -> Response:
        """
        Returns a redirect response that includes Set-Cookie headers
        to configure an encrypted id_token and, optionally, also encrypted
        access_token and refresh_token.
        """
        response = html(
            self._get_html(
                original_path,
                id_token.value,
                (
                    token_response.access_token
                    if token_response is not None
                    and token_response.access_token is not None
                    else ""
                ),
                (
                    self.protect_refresh_token(token_response.refresh_token)
                    if token_response is not None
                    and token_response.refresh_token is not None
                    else ""
                ),
            )
        )

        return response

    async def get_refresh_tokens_response(
        self,
        request: Request,
        token_response: TokenResponse,
    ) -> Response:
        refresh_token = token_response.data.get("refresh_token")
        if refresh_token:
            token_response.data["refresh_token"] = self.protect_refresh_token(
                refresh_token
            )
        return json(token_response.data)

    async def get_logout_response(
        self, request: Request, post_logout_redirect_path: str
    ) -> Response:
        return html(self._get_html(post_logout_redirect_path, "", "", ""))

    def _get_storage_code(self) -> str:
        return f"window.{self.storage_type.value}"

    def _get_html(
        self, redirect_path: str, id_token: str, access_token: str, refresh_token: str
    ) -> str:
        storage_code = self._get_storage_code()
        return f"""
<!DOCTYPE html>
<html>
  <head>
    <title>OIDC.</title>
    <meta charset="utf-8" />
    <meta content='text/html; charset=utf-8' http-equiv='Content-Type'>
  </head>
  <body>
    <script>
    (function () {{
        {storage_code}.setItem("{self.id_token_key}", "{id_token}");
        {storage_code}.setItem("{self.access_token_key}", "{access_token}");
        {storage_code}.setItem("{self.refresh_token_key}", "{refresh_token}");
        setTimeout(function () {{
            window.location.replace("{redirect_path}")
        }}, {str(self.redirect_timeout)})
    }})();
    </script>
  </body>
</html>
        """.strip()

    def _get_refresh_token_header_name(self) -> bytes:
        return b"X-" + self.refresh_token_key.replace("_", "-").encode()

    def protect_refresh_token(self, refresh_token: str) -> str:
        return self._serializer.dumps(refresh_token)  # type: ignore

    def restore_refresh_token(self, context: Request) -> None:
        refresh_token_header = context.get_first_header(
            self._get_refresh_token_header_name()
        )

        if refresh_token_header:
            try:
                value = self._serializer.loads(refresh_token_header)
            except BadSignature:
                logger.info(
                    "Discarding refresh token (%s), invalid signature.",
                    self.refresh_token_key,
                )
            else:
                if context.user is None:
                    context.user = Identity({})
                context.user.refresh_token = value

    async def authenticate(self, context: Request) -> Optional[Identity]:
        await self.auth_handler.authenticate(context)

        self.restore_refresh_token(context)


class TokenType(Enum):
    ID_TOKEN = "id_token"
    ACCESS_TOKEN = "access_token"
    REFRESH_TOKEN = "refresh_token"


class CookiesTokensStore(TokensStore):
    """
    A class that can store access and refresh tokens in encrypted form in cookies.

    Beware that cookies size can be problematic when storing all information in cookies.
    If this is the case, consider implementing a type of `BaseTokensStore` that uses
    other ways to store and restore tokens (e.g. Redis Cache, etc.).
    """

    def __init__(
        self,
        scheme_name: str = "OpenIDConnect",
        secret_keys: Optional[Sequence[str]] = None,
        serializer: Optional[Serializer] = None,
        refresh_token_path: str = "/refresh-token",
    ) -> None:
        self._scheme_name: str
        self._access_token_name: str
        self._refresh_token_name: str
        self._refresh_token_path = refresh_token_path
        self.scheme_name = scheme_name

        self.serializer = serializer or get_serializer(
            secret_keys, f"{scheme_name}tokens"
        )

    @property
    def scheme_name(self) -> str:
        return self._scheme_name

    @scheme_name.setter
    def scheme_name(self, value: str) -> None:
        self._scheme_name = value
        self._access_token_cookie_name = f"{self._scheme_name}.at".lower()
        self._refresh_token_cookie_name = f"{self._scheme_name}.rt".lower()

    async def store_tokens(
        self,
        request: Request,
        response: Response,
        access_token: str,
        refresh_token: Optional[str],
    ) -> None:
        secure = request.scheme == "https"
        self.set_cookie(
            response,
            self._access_token_cookie_name,
            access_token,
            secure=secure,
            expires=None,
        )

        len_combined = len(access_token) + len(access_token)
        logger.info(f"COOKIES LEN: {len_combined}")

        if refresh_token:
            self.set_cookie(
                response,
                self._refresh_token_cookie_name,
                refresh_token,
                secure=secure,
                expires=None,
                path=self._refresh_token_path,
            )

    async def restore_tokens(self, request: Request):
        await self._restore_token(
            request, self._access_token_cookie_name, TokenType.ACCESS_TOKEN
        )
        await self._restore_token(
            request, self._refresh_token_cookie_name, TokenType.REFRESH_TOKEN
        )

    def set_cookie(
        self,
        response: Response,
        cookie_name: str,
        data: AnyStr,
        secure: bool,
        expires: Optional[datetime] = None,
        path: str = "/",
    ) -> None:
        value = self.serializer.dumps(data)  # type: ignore
        response.set_cookie(
            Cookie(
                cookie_name,
                ensure_str(value),  # type: ignore
                domain=None,
                path=path,
                http_only=True,
                secure=secure,
                expires=expires,
            )
        )

    async def _restore_token(
        self, request: Request, cookie_name: str, token_type: TokenType
    ) -> None:
        cookie = request.get_cookie(cookie_name)

        if cookie is None:
            pass
        else:
            try:
                value = self.serializer.loads(cookie)
            except BadSignature:
                logger.info(
                    "Discarding token (%s), invalid signature.",
                    cookie_name,
                )
            else:
                if request.user:
                    if token_type == TokenType.ACCESS_TOKEN:
                        request.user.access_token = value
                    elif token_type == TokenType.REFRESH_TOKEN:
                        request.user.refresh_token = value
        return None


class OpenIDConnectHandler:
    def __init__(
        self,
        settings: OpenIDSettings,
        auth_handler: OpenIDTokensHandler,
        parameters_builder: Optional[ParametersBuilder] = None,
    ) -> None:
        self._settings = settings
        self._configuration: Optional[OpenIDConfiguration] = None
        self._http_handler: HTTPHandler = HTTPHandler()
        self.events = OpenIDConnectEvents(self)
        self.parameters_builder = parameters_builder or ParametersBuilder(settings)
        self._jwt_validator: Optional[JWTValidator] = None
        self._auth_handler = auth_handler

    @property
    def auth_handler(self) -> OpenIDTokensHandler:
        return self._auth_handler

    @property
    def settings(self) -> OpenIDSettings:
        return self._settings

    async def get_jwt_validator(self) -> JWTValidator:
        if self._jwt_validator is None:
            configuration = await self.get_openid_configuration()

            self._jwt_validator = JWTValidator(
                require_kid=True,
                keys_url=configuration.jwks_uri,
                valid_issuers=[configuration.issuer],
                valid_audiences=[self._settings.client_id],
            )
        return self._jwt_validator

    def get_well_known_openid_configuration_url(self) -> str:
        if self._settings.discovery_endpoint:
            return self._settings.discovery_endpoint

        if not self._settings.authority:
            raise OpenIDConnectConfigurationError(
                "Missing `authority` or `discovery_endpoint` in OpenIDSettings. "
                "To fix, define one of the two."
            )

        return (
            self._settings.authority.rstrip("/") + "/.well-known/openid-configuration"
        )

    async def fetch_openid_configuration(self) -> OpenIDConfiguration:
        try:
            data = await self._http_handler.fetch_json(
                self.get_well_known_openid_configuration_url()
            )
        except FailedRequestError as request_error:
            logger.error(
                "Failed to fetch OpenID Connect configuration from the remote endpoint."
                "Inspect the exception details for more details on the cause of the "
                "failure.",
                exc_info=request_error,
            )
            raise OpenIDConnectRequestError(request_error)
        else:
            logger.debug(
                "Fetched OpenID Connect configuration from the remote endpoint."
            )
            return OpenIDConfiguration(data)

    async def get_openid_configuration(self) -> OpenIDConfiguration:
        if self._configuration is None:
            self._configuration = await self.fetch_openid_configuration()

        return self._configuration

    async def redirect_to_sign_in(self, request: Request) -> Response:
        redirect_url = await self.get_redirect_uri(request)
        return redirect(redirect_url)

    async def get_redirect_uri(self, request: Request) -> str:
        openid_conf = await self.get_openid_configuration()
        parameters = self.parameters_builder.build_signin_parameters(request)
        authorization_endpoint = openid_conf.authorization_endpoint
        return authorization_endpoint + "?" + urlencode(parameters)

    async def handle_error(self, request: Request, data: Dict[str, Any]) -> Response:
        """
        Handles an error received from the identity provider.
        """
        query = "?" + urlencode({"error": data.get("error", "unknown")})
        if self._settings.error_redirect_path:
            return redirect(self._settings.error_redirect_path + query)
        return redirect("/" + query)

    async def handle_auth_redirect(self, request: Request) -> Response:
        """
        Handles the redirect after the user interacted with the sign-in page of a remote
        authorization server.
        """
        data = await request.form()

        if data is None or not data:
            return accepted()

        error = data.get("error")

        if error:
            logger.error(
                "Received a post request with error message to the OIDC authorization "
                "callback endpoint: %s",
                error,
            )
            await self.events.on_error.fire(data)
            return await self.handle_error(request, data)

        # the following code validates the state and restores the original path
        # the user was trying to access before being redirected to the OIDC sign-in
        state = data.get("state")
        if isinstance(state, str):
            state = self.parameters_builder.read_state(state)
            redirect_path = state.get("orig_path", "/")
        else:
            redirect_path = "/"

        settings = self._settings

        id_token = data.get("id_token")
        token_response = None

        if id_token and not settings.client_secret:
            logger.debug("Successfully obtained an id_token for a user.")
        else:
            code = data.get("code")

            if settings.client_secret and isinstance(code, str):
                # extra call to fetch an access token
                token_response = await self.exchange_token(request, code)

                await self.events.on_tokens_received.fire(token_response)

                if not id_token and token_response.id_token:
                    id_token = token_response.id_token
            else:
                raise BadRequest("Expected either an error, an id_token, or a code.")

        if not isinstance(id_token, str):
            # This can happen legitimately if OIDC settings are configured to retrieve
            # only an access token. For example, when using Auth0 and configuring a
            # single scope that does not include openid or profile. In such cases, it is
            # unclear what should be done, especially since access tokens are not stored
            # by default. The user of the library might still being handling the token
            # response using dedicated event, or using a token_store.
            parsed_id_token = {}
        else:
            parsed_id_token = await self.validate_id_token(id_token)

            if isinstance(state, dict) and state.get("nonce") != parsed_id_token.get(
                "nonce"
            ):
                raise OpenIDConnectError("nonce mismatch error")

            await self.events.on_id_token_validated.fire(parsed_id_token)

        if not isinstance(id_token, str):
            id_token = ""
        return await self._auth_handler.get_success_response(
            request, IDToken(id_token, parsed_id_token), token_response, redirect_path
        )

    async def exchange_token(self, request: Request, code: str) -> TokenResponse:
        configuration = await self.get_openid_configuration()

        code_grant_parameters = self.parameters_builder.build_code_grant_parameters(
            request, code
        )

        try:
            data = await self._http_handler.post_form(
                configuration.token_endpoint, code_grant_parameters
            )
        except FailedRequestError as request_error:
            logger.error(
                "Failed to exchange an authorization code with an access token. "
                "Inspect the exception details for more details on the cause of the "
                "failure.",
                exc_info=request_error,
            )
            raise OpenIDConnectFailedExchangeError(request_error)
        else:
            logger.debug("Exchanged a code with id_token and access_token for a user.")
            return TokenResponse(data)

    async def handle_refresh_token_request(self, request: Request) -> Response:
        if request.user is None:
            return bad_request("Missing user context.")

        refresh_token = request.user.refresh_token

        if not refresh_token:
            return bad_request("Missing refresh_token in request context.")

        token_response = await self.refresh_token(refresh_token)

        await self.events.on_tokens_received.fire(token_response)

        return await self._auth_handler.get_refresh_tokens_response(
            request, token_response
        )

    async def refresh_token(self, refresh_token: str) -> TokenResponse:
        configuration = await self.get_openid_configuration()

        refresh_token_parameters = (
            self.parameters_builder.build_refresh_token_parameters(refresh_token)
        )

        try:
            data = await self._http_handler.post_form(
                configuration.token_endpoint, refresh_token_parameters
            )
        except FailedRequestError as request_error:
            logger.error(
                "Failed to exchange a refresh token with an access token. "
                "Inspect the exception details for more details on the cause of the "
                "failure.",
                exc_info=request_error,
            )
            raise OpenIDConnectFailedExchangeError(request_error)
        else:
            logger.debug(
                "Exchanged a refresh token with a fresh access_token for a user."
            )
            return TokenResponse(data)

    async def validate_id_token(self, raw_id_token: str) -> Any:
        jwt_validator = await self.get_jwt_validator()
        try:
            return await jwt_validator.validate_jwt(raw_id_token)
        except (InvalidAccessToken, InvalidTokenError) as ex:
            logger.error("Invalid id_token: %s", str(ex))
            raise Unauthorized(f"Invalid id_token: {ex}")

    async def handle_logout_redirect(self, request: Request) -> Response:
        # TODO: obtain the logout redirect from OIDC.end_session_endpoint
        # and make what is necessary to logout from the remote identity provider.
        # Note that there are differences among providers:
        # e.g. Okta requires the original id_token

        # Auth0 does not provide end_session_endpoint in the discovery endpoint
        # AAD is the simplest scenario because it's a simple redirect to the
        # end_session_endpoint.
        return await self._auth_handler.get_logout_response(
            request, self._settings.post_logout_redirect_path
        )


class ChallengeMiddleware:
    def __init__(
        self, request_handler: Callable[[Request], Awaitable[Response]]
    ) -> None:
        self.request_handler = request_handler

    async def __call__(self, request: Request, handler):
        try:
            return await handler(request)
        except (Unauthorized, UnauthorizedError):
            if (
                request.user is None
                or not request.user.is_authenticated()
                and request.method in {"GET", "HEAD"}
            ):
                return await self.request_handler(request)
            raise


def use_openid_connect(
    app: Application,
    settings: OpenIDSettings,
    auth_handler: Optional[OpenIDTokensHandler] = None,
    parameters_builder: Optional[ParametersBuilder] = None,
    is_default: bool = True,
) -> OpenIDConnectHandler:
    """
    Configures an application to use OpenID Connect, integrating with an identity
    provider such as Auth0, Okta, Azure Active Directory.

    Parameters
    ----------
    app : Application
        The application to be configured to handle OpenID Connect.
    settings : OpenIDSettings
        Basic OAuth settings, and other settings to handle the OIDC flow.
    auth_handler : Optional[OpenIDTokensHandler]
        Lets specify the object that is responsible of handling responses to communicate
        tokens to the client and restoring user context for web requests.
        If not specified, the default CookiesOpenIDTokensHandler class is used.
        BlackSheep offers two kinds of this class out of the box: one that uses cookies
        and, for more advanced situations, one that uses the HTML5 storage API to set
        tokens on the client side. See [the OIDC
        examples](https://github.com/Neoteroi/BlackSheep-Examples/tree/main/oidc)
        for more information.
    parameters_builder : Optional[ParametersBuilder]
        ParametersBuilder used to build parameters for OAuth requests, by default None
    is_default : bool, optional
        If true, the application is configured to automatically redirect
        not-authenticated users to the sign-in endpoint, by default True

    Returns
    -------
    OpenIDConnectHandler
        Instance of a class that handles the OIDC integration.
    """
    scheme_name = settings.scheme_name or "OpenIDConnect"

    if auth_handler is None:
        auth_handler = CookiesOpenIDTokensHandler(
            CookieAuthentication(
                cookie_name=scheme_name.lower(), auth_scheme=scheme_name
            ),
        )

    app.use_authentication().add(auth_handler)

    handler = OpenIDConnectHandler(
        settings,
        parameters_builder=parameters_builder,
        auth_handler=auth_handler,
    )

    @allow_anonymous()
    @app.router.get(settings.entry_path)
    @cache_control(no_cache=True, no_store=True)
    async def redirect_to_sign_in(request: Request):
        return await handler.redirect_to_sign_in(request)

    @allow_anonymous()
    @app.router.post(settings.callback_path)
    @cache_control(no_cache=True, no_store=True)
    async def handle_auth_redirect(request: Request):
        return await handler.handle_auth_redirect(request)

    @app.router.get(settings.logout_path)
    @cache_control(no_cache=True, no_store=True)
    async def redirect_to_logout(request: Request):
        return await handler.handle_logout_redirect(request)

    @allow_anonymous()
    @app.router.post(settings.refresh_token_path)
    @cache_control(no_cache=True, no_store=True)
    async def refresh_token(request: Request):
        return await handler.handle_refresh_token_request(request)

    if is_default:

        @app.on_middlewares_configuration
        def insert_challenge_middleware(app):
            app.middlewares.insert(0, ChallengeMiddleware(handler.redirect_to_sign_in))

    return handler
