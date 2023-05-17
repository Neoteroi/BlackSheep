from typing import Optional, Sequence

from guardpost import AuthenticationHandler, Identity
from guardpost.jwks import KeysProvider
from guardpost.jwts import InvalidAccessToken, JWTValidator
from jwt.exceptions import InvalidTokenError

from blacksheep.baseapp import get_logger
from blacksheep.messages import Request


class JWTBearerAuthentication(AuthenticationHandler):
    """
    AuthenticationHandler that can parse and verify JWT Bearer access tokens to identify
    users.

    JWTs are validated using public RSA keys, and keys can be fetched automatically from
    OpenID Connect (OIDC) discovery, if an `authority` is provided.

    It is possible to use several instances of this class, to support authentication
    through several identity providers (e.g. Azure Active Directory, Auth0, Azure Active
    Directory B2C).
    """

    def __init__(
        self,
        *,
        valid_audiences: Sequence[str],
        valid_issuers: Optional[Sequence[str]] = None,
        authority: Optional[str] = None,
        algorithms: Optional[Sequence[str]] = None,
        require_kid: bool = True,
        keys_provider: Optional[KeysProvider] = None,
        keys_url: Optional[str] = None,
        cache_time: float = 10800,
        auth_mode: str = "JWT Bearer",
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
        valid_issuers : Optional[Sequence[str]]
            Sequence of acceptable issuers (iss). Required if `authority` is not
            provided. If authority is specified and issuers are not, then valid
            issuers are set as [authority].
        authority : Optional[str], optional
            If provided, keys are obtained from a standard well-known endpoint.
            This parameter is ignored if `keys_provider` is given.
        algorithms : Sequence[str], optional
            Sequence of acceptable algorithms, by default ["RS256"].
        require_kid : bool, optional
            According to the specification, a key id is optional in JWK. However,
            this parameter lets control whether access tokens missing `kid` in their
            headers should be handled or rejected. By default True, thus only JWTs
            having `kid` header are accepted.
        keys_provider : Optional[KeysProvider], optional
            If provided, the exact `KeysProvider` to be used when fetching keys.
            By default None
        keys_url : Optional[str], optional
            If provided, keys are obtained from the given URL through HTTP GET.
            This parameter is ignored if `keys_provider` is given.
        cache_time : float, optional
            If >= 0, JWKS are cached in memory and stored for the given amount in
            seconds. By default 10800 (3 hours).
        auth_mode : str, optional
            When authentication succeeds, the declared authentication mode. By default,
            "JWT Bearer".
        """
        self.logger = get_logger()

        if authority and not valid_issuers:
            valid_issuers = [authority]

        if not authority and not valid_issuers:
            raise TypeError("Specify either an authority or valid issuers.")

        assert valid_issuers is not None

        if not algorithms:
            algorithms = ["RS256"]

        self._validator = JWTValidator(
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
        self._validator.logger = self.logger

    async def authenticate(self, context: Request) -> Optional[Identity]:
        authorization_value = context.get_first_header(b"Authorization")

        if not authorization_value:
            context.user = Identity({})
            return None

        if not authorization_value.startswith(b"Bearer "):
            self.logger.debug(
                "Invalid Authorization header, not starting with `Bearer `, "
                "the header is ignored."
            )
            context.user = Identity({})
            return None

        token = authorization_value[7:].decode()

        try:
            decoded = await self._validator.validate_jwt(token)
        except (InvalidAccessToken, InvalidTokenError) as ex:
            # pass, because the application might support more than one
            # authentication method and several JWT Bearer configurations
            self.logger.debug(
                "JWT Bearer - access token not valid for this configuration: %s",
                str(ex),
            )
            pass
        else:
            context.user = Identity(decoded, self.auth_mode)
            return context.user

        context.user = Identity({})
        return None
