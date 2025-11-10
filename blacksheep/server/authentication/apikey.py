"""
This module provides classes to handle API Keys authentication.
"""

from abc import ABC, abstractmethod
from copy import deepcopy
from enum import Enum
from typing import Literal

from essentials.secrets import Secret
from guardpost import AuthenticationHandler, Identity
from guardpost.errors import InvalidCredentialsError

from blacksheep.messages import Request


class APIKeyLocation(Enum):
    HEADER = "header"
    QUERY = "query"
    COOKIE = "cookie"


APIKeyLocationValue = Literal["header", "query", "cookie"]


class APIKey:
    def __init__(
        self,
        secret: Secret,
        claims: dict | None = None,
        roles: list[str] | None = None,
    ) -> None:
        """
        Creates an instance of API Key for authentication.

        Parameters
        ----------
        secret : Secret
            The secret value of the API key.
        claims : dict | None, optional
            Additional claims to include in the authenticated identity, by default None.
        roles : list[str] | None, optional
            List of roles to assign to the authenticated identity, by default None.

        Raises
        ------
        ValueError
            If both 'secret' and 'secrets' are provided, or if neither is provided.
        """
        self._claims = claims or {}
        self._roles = roles or []
        self._secret = secret

    @property
    def claims(self) -> dict:
        """Returns the claims associated with this API Key."""
        return self._claims

    @property
    def roles(self) -> list[str]:
        """Returns the roles associated with this API Key."""
        return self._roles

    def match(self, secret: Secret | str) -> bool:
        """
        Returns a value indicating if the provided secret matches this API Key secret.
        """
        return self._secret == secret


class APIKeysProvider(ABC):
    """
    Abstract base class for providing API keys dynamically.

    This class defines the interface for API key providers that can be used
    with APIKeyAuthentication to retrieve API keys at runtime. Implementations
    can fetch keys from various sources such as databases, configuration files,
    external services, or in-memory stores.

    Examples
    --------
    >>> class DatabaseAPIKeysProvider(APIKeysProvider):
    ...     async def get_keys(self) -> list[APIKey]:
    ...         # Fetch keys from database…
    ...         api_keys = await self.fetch_api_keys_from_db()
    ...         return [APIKey(key.name, Secret(key.secret, direct_value=True))
    ...                 for key in api_keys]
    """

    @abstractmethod
    async def get_keys(self) -> list[APIKey]:
        """
        Retrieve a list of valid API keys.

        This method should return all currently valid API keys that can be used
        for authentication. The method is called by APIKeyAuthentication during
        the authentication process when no static keys are provided.

        Returns
        -------
        list[APIKey]
            A list of APIKey instances representing all valid keys for authentication.
            An empty list indicates no valid keys are available.

        Notes
        -----
        - This method is called for each authentication attempt, so implementations
          should consider caching strategies for performance if fetching keys is
          expensive.
        - The returned list should only contain currently valid and active API keys.
        """


class APIKeyAuthentication(AuthenticationHandler):
    """
    AuthenticationHandler that uses API Keys for authentication, handling one or more
    API Key secrets. Each secret can be associated to different claims and roles.
    """

    def __init__(
        self,
        *keys: APIKey,
        param_name: str,
        scheme: str = "APIKey",
        location: APIKeyLocationValue | APIKeyLocation = "header",
        keys_provider: APIKeysProvider | None = None,
        description: str | None = None,
    ) -> None:
        """
        Creates a new instance of APIKeyAuthentication.

        Parameters
        ----------
        param_name : str
            Arbitrary name of the API key parameter (e.g., header name, query parameter
            name, or cookie name).
        keys : Optional keys handled by this instance (APIKeys). Use this
            parameter or a keys_provider.
        scheme : str, optional
            The authentication scheme name, by default "APIKey".
        location : APIKeyLocationValue | APIKeyLocation, optional
            Where to look for the API key in the request (header, query, or cookie), by
            default "header".
        keys_provider : APIKeysProvider | None
            An optional provider that can be used to retrieve keys dynamically.
            If not provided, the keys passed as parameters will be used.
        description : str | None
            An optional description for this authentication scheme.
        """
        super().__init__()
        self._scheme = scheme
        self._keys = tuple(keys) if keys else None
        self._keys_provider = keys_provider
        self._param_name = param_name
        self._location = APIKeyLocation(location)
        self.description = description

        if keys and keys_provider:
            raise ValueError("Cannot specify both static keys and a keys_provider")
        elif not keys and keys_provider is None:
            raise ValueError("Either keys or keys_provider must be provided")

    @property
    def scheme(self) -> str:
        """Returns the name of the Authentication Scheme used by this handler."""
        return self._scheme

    @property
    def param_name(self) -> str:
        """Returns the name of the API Key."""
        return self._param_name

    @property
    def location(self) -> APIKeyLocation:
        """Returns the location of the API Key."""
        return self._location

    async def authenticate(self, context: Request) -> Identity | None:
        """
        Tries to authenticate the request using API Keys.
        If authentication succeeds, returns an Identity with the authentication mode set
        to the scheme of the matching API Key. If no matching API Key is found, returns
        None.
        """
        matching_key = await self._match_key(context)

        if matching_key is None:
            # Return None here and do not raise an exception, because the application
            # might be configured with alternative ways to authenticate users.
            return None

        return self._get_identity_for_key(matching_key)

    def _get_identity_for_key(self, key: APIKey) -> Identity:
        """
        Returns an instance of Identity to be used when authentication with a given
        API Key succeeded. Each API Key can be associated with specific roles and
        claims.
        """
        claims = deepcopy(key.claims)
        claims.update({"roles": [role for role in key.roles]})
        return Identity(claims, authentication_mode=self.scheme)

    def _get_input_secret(self, context: Request) -> str | None:
        value = None
        if self.location == APIKeyLocation.HEADER:
            bytes_value = context.get_first_header(self._param_name.encode())
            if bytes_value:
                value = bytes_value.decode()
        elif self.location == APIKeyLocation.QUERY:
            list_value = context.query.get(self._param_name)
            if list_value:
                value = list_value[-1]
        elif self.location == APIKeyLocation.COOKIE:
            value = context.cookies.get(self._param_name)
        else:
            # This should never happen
            raise TypeError("APIKeyLocation not supported.")
        return value

    async def _match_key(self, context: Request) -> APIKey | None:
        """
        Tries to find a matching API Key in the request context.
        Returns the matching API Key if found, otherwise None.

        If the client provides an API Key and it is invalid, an InvalidCredentialsError
        error is raised to keep track of this event and support rate-limiting requests
        from the same client, to prevent brute-forcing.
        """
        keys = self._keys

        if not keys and self._keys_provider is not None:
            keys = await self._keys_provider.get_keys()

        if not keys:
            return None

        input_secret = self._get_input_secret(context)

        if not input_secret:
            return None

        for key in keys:
            if key.match(input_secret):
                return key

        # The client provided an API Key, but it is invalid. This event must be logged,
        # and we must rate-limit this kind of request by client IP.
        raise InvalidCredentialsError(context.original_client_ip)
