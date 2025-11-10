"""
This module provides classes to handle JWT Bearer authentication.
"""

import warnings
from typing import Sequence

from essentials.secrets import Secret
from guardpost import AuthenticationHandler, Identity, InvalidCredentialsError
from guardpost.jwks import KeysProvider
from guardpost.jwts import (
    AsymmetricJWTValidator,
    BaseJWTValidator,
    ExpiredAccessToken,
    InvalidAccessToken,
    SymmetricJWTValidator,
)
from jwt.exceptions import InvalidTokenError

from blacksheep.baseapp import get_logger
from blacksheep.messages import Request


class JWTBearerAuthentication(AuthenticationHandler):
    """
    AuthenticationHandler that can parse and verify JWT Bearer access tokens to identify
    users.

    JWTs are validated using either public RSA keys (asymmetric) or a shared secret
    (symmetric), but not both in the same instance. Keys can be fetched automatically
    from OpenID Connect (OIDC) discovery, if an `authority` is provided.

    Use separate instances of this class to support different authentication methods
    or identity providers.
    """

    def __init__(
        self,
        *,
        valid_audiences: Sequence[str],
        valid_issuers: Sequence[str] | None = None,
        authority: str | None = None,
        algorithms: Sequence[str] | None = None,
        require_kid: bool = True,
        keys_provider: KeysProvider | None = None,
        keys_url: str | None = None,
        cache_time: float = 10800,
        auth_mode: str = "JWT Bearer",
        scheme: str = "",
        secret_key: Secret | None = None,
    ):
        """
        Creates a new instance of JWTBearerAuthentication, which tries to
        obtains the identity of the user from the "Authorization" request header,
        handling JWT Bearer tokens. Only standard authorization headers starting
        with the `Bearer ` string are handled.

        Parameters
        ----------
        valid_audiences : Sequence[str]
            Sequence of acceptable audiences (aud).
        valid_issuers : Sequence[str | None]
            Sequence of acceptable issuers (iss). Required if `authority` is not
            provided. If authority is specified and issuers are not, then valid
            issuers are set as [authority].
        authority : str | None, optional
            If provided, keys are obtained from a standard well-known endpoint.
            This parameter is ignored if `keys_provider` is given.
        algorithms : Sequence[str], optional
            Sequence of acceptable algorithms. Defaults to ["RS256"] for asymmetric
            validation or ["HS256"] for symmetric validation.
        require_kid : bool, optional
            According to the specification, a key id is optional in JWK. However,
            this parameter lets control whether access tokens missing `kid` in their
            headers should be handled or rejected. By default True, thus only JWTs
            having `kid` header are accepted. Only applies to asymmetric validation.
        keys_provider : KeysProvider | None, optional
            If provided, the exact `KeysProvider` to be used when fetching JWKS for
            validation. Only applies to asymmetric validation. By default None.
        keys_url : str | None, optional
            If provided, keys are obtained from the given URL through HTTP GET.
            This parameter is ignored if `keys_provider` is given or if `secret_key`
            is provided. Only applies to asymmetric validation.
        cache_time : float, optional
            If >= 0, JWKS are cached in memory and stored for the given amount in
            seconds. By default 10800 (3 hours). Only applies to asymmetric validation.
        scheme: str
            Authentication scheme. When authentication succeeds, the identity is
            authenticated with this scheme.
        auth_mode : str, optional
            Deprecated parameter, use `scheme` instead. When authentication succeeds,
            the declared authentication mode. By default, "JWT Bearer".
        secret_key : Secret | None, optional
            If provided, enables symmetric JWT validation (HS256/HS384/HS512).
            Cannot be used together with asymmetric validation parameters.
        """
        if auth_mode != "JWT Bearer":
            # the user specified an auth_mode different than default.
            warnings.warn(
                "The auth_mode parameter is deprecated and will be removed in a "
                "future version. Use the scheme parameter instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            scheme = auth_mode
        elif scheme:
            # the user used the new parameter - good;
            auth_mode = scheme
        self._validator: BaseJWTValidator
        self.logger = get_logger()

        # Validate mutual exclusivity
        if secret_key and (authority or keys_provider or keys_url):
            raise TypeError(
                "Cannot specify both secret_key (symmetric) and "
                "authority/keys_provider/keys_url (asymmetric) parameters. "
                "Use separate instances for different validation methods."
            )

        # Determine validation mode and set appropriate defaults
        if secret_key:
            # Symmetric validation
            if not algorithms:
                algorithms = ["HS256"]

            if valid_issuers is None:
                raise TypeError("Specify valid issuers.")

            # Validate that only symmetric algorithms are specified
            invalid_algorithms = [
                algo for algo in algorithms if not algo.startswith("HS")
            ]
            if invalid_algorithms:
                raise TypeError(
                    f"When using secret_key, only HS* algorithms are supported. "
                    f"Invalid algorithms: {invalid_algorithms}"
                )

            self._validator = SymmetricJWTValidator(
                valid_issuers=valid_issuers,
                valid_audiences=valid_audiences,
                secret_key=secret_key.get_value(),
                algorithms=algorithms,
            )
        else:
            # Asymmetric validation
            if not algorithms:
                algorithms = ["RS256"]

            if authority and not valid_issuers:
                valid_issuers = [authority]

            if not authority and not valid_issuers:
                raise TypeError("Specify either an authority or valid issuers.")

            assert valid_issuers is not None

            # Validate that only asymmetric algorithms are specified
            invalid_algorithms = [
                algo
                for algo in algorithms
                if not (algo.startswith("RS") or algo.startswith("ES"))
            ]
            if invalid_algorithms:
                raise TypeError(
                    f"When using asymmetric validation, only RS*/ES* algorithms are "
                    f"supported. Invalid algorithms: {invalid_algorithms}."
                )

            self._validator = AsymmetricJWTValidator(
                authority=authority,
                algorithms=algorithms,
                require_kid=require_kid,
                keys_provider=keys_provider,
                keys_url=keys_url,
                valid_issuers=valid_issuers,
                valid_audiences=valid_audiences,
                cache_time=cache_time,
            )

        self.auth_mode = auth_mode
        self._scheme = scheme or auth_mode
        self._validator.logger = self.logger

    async def authenticate(self, context: Request) -> Identity | None:
        authorization_value = context.get_first_header(b"Authorization")

        if not authorization_value:
            return None

        if not authorization_value.startswith(b"Bearer "):
            self.logger.debug(
                "Invalid Authorization header, not starting with 'Bearer ', "
                "the header is ignored."
            )
            return None

        token = authorization_value[7:].decode()

        try:
            decoded = await self._validator.validate_jwt(token)
        except ExpiredAccessToken:
            # Common scenario
            return None
        except (InvalidAccessToken, InvalidTokenError) as exc:
            self.logger.debug(
                "JWT Bearer - access token not valid for this configuration: %s",
                str(exc),
            )
            # Raise a dedicated exception to keep track of the event
            raise InvalidCredentialsError(context.original_client_ip)
        else:
            return Identity(decoded, self.scheme)

    @property
    def scheme(self) -> str:
        return self._scheme.replace(" ", "")
