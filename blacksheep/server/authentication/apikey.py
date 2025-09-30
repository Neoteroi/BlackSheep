"""
This module provides classes to handle API Keys authentication.
"""

from abc import ABC, abstractmethod
from copy import deepcopy
from enum import Enum
from typing import List, Literal, Optional, Sequence, Tuple, Union

from guardpost import AuthenticationHandler, Identity

from blacksheep.messages import Request
from securestr import Secret  # TODO: essentials


class APIKeyLocation(Enum):
    HEADER = "header"
    QUERY = "query"
    COOKIE = "cookie"


APIKeyLocationValue = Literal["header", "query", "cookie"]


class APIKey:
    def __init__(
        self,
        name: str,
        description: str = "",
        secret: Optional[Secret] = None,
        secrets: Optional[Sequence[Secret]] = None,
        scheme: str = "apikey",
        location: Union[APIKeyLocationValue, APIKeyLocation] = "header",
        claims: Optional[dict] = None,
        roles: Optional[List[str]] = None,
    ) -> None:
        """
        Initialize an API Key for authentication.

        Parameters
        ----------
        name : str
            Arbitrary name of the API key (e.g., header name, query parameter name, or
            cookie name).
        secret : Optional[Secret], optional
            A single secret value for the API key. Cannot be used together with 'secrets'.
        secrets : Optional[Sequence[Secret]], optional
            Multiple secret values for the API key. Cannot be used together with 'secret'.
        scheme : str, optional
            The authentication scheme name, by default "apikey".
        location : Union[APIKeyLocationValue, APIKeyLocation], optional
            Where to look for the API key in the request (header, query, or cookie), by default "header".
        claims : Optional[dict], optional
            Additional claims to include in the authenticated identity, by default None.
        roles : Optional[List[str]], optional
            List of roles to assign to the authenticated identity, by default None.

        Raises
        ------
        ValueError
            If both 'secret' and 'secrets' are provided, or if neither is provided.
        """

        self._scheme = scheme
        self._name = name
        self.description = description
        self._location = APIKeyLocation(location)
        self._claims = claims or {}
        self._roles = roles or []

        # Handle secret/secrets parameters
        if secret is not None and secrets is not None:
            raise ValueError("Cannot specify both 'secret' and 'secrets' parameters")
        elif secret is not None:
            self.__secrets = [secret]
        elif secrets is not None:
            self.__secrets = list(secrets)
        else:
            raise ValueError("Either 'secret' or 'secrets' parameter must be provided")

    @property
    def scheme(self) -> str:
        """Returns the name of the Authentication Scheme used by this handler."""
        return self._scheme

    @property
    def name(self) -> str:
        """Returns the name of the API Key."""
        return self._name

    @property
    def location(self) -> APIKeyLocation:
        """Returns the location of the API Key."""
        return self._location

    @property
    def claims(self) -> dict:
        """Returns the claims associated with this API Key."""
        return self._claims

    @property
    def roles(self) -> List[str]:
        """Returns the roles associated with this API Key."""
        return self._roles

    def is_valid_secret(self, provided_secret: str) -> bool:
        """
        Validate if the provided secret matches any of the configured secrets,
        Using constant-time comparison to prevent timing attacks, with
        secrets.compare_digest.
        """
        for secret in self.__secrets:
            # Note: internally the Secret class uses constant-time comparison
            # to prevent timing attacks, with secrets.compare_digest.
            if secret == provided_secret:
                return True
        return False


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
    ...     async def get_keys(self) -> List[APIKey]:
    ...         # Fetch keys from database…
    ...         api_keys = await self.fetch_api_keys_from_db()
    ...         return [APIKey(key.name, Secret(key.secret, direct_value=True))
    ...                 for key in api_keys]
    """

    @abstractmethod
    async def get_keys(self) -> List[APIKey]:
        """
        Retrieve a list of valid API keys.

        This method should return all currently valid API keys that can be used
        for authentication. The method is called by APIKeyAuthentication during
        the authentication process when no static keys are provided.

        Returns
        -------
        List[APIKey]
            A list of APIKey instances representing all valid keys for authentication.
            An empty list indicates no valid keys are available.

        Notes
        -----
        - This method is called for each authentication attempt, so implementations
          should consider caching strategies for performance if fetching keys is expensive.
        - The returned list should only contain currently valid and active API keys.
        """
        ...


class APIKeyAuthentication(AuthenticationHandler):
    """
    AuthenticationHandler that uses API Keys for authentication.
    """

    def __init__(
        self, *keys: APIKey, keys_provider: Optional[APIKeysProvider] = None
    ) -> None:
        """
        Creates a new instance of APIKeyAuthentication.

        Parameters
        ----------
        *keys : Exact keys handled by this instance (APIKeys).
        keys_provider : Optional[APIKeysProvider]
            An optional provider that can be used to retrieve keys dynamically.
            If not provided, the keys passed as parameters will be used.
        """
        super().__init__()
        self._keys = tuple(keys)
        self._keys_provider = keys_provider

        if keys and keys_provider:
            raise ValueError("Cannot specify both static keys and a keys_provider")
        elif not keys and keys_provider is None:
            raise ValueError("Either keys or keys_provider must be provided")

    @property
    def keys(self) -> Tuple[APIKey, ...]:
        return self._keys

    async def authenticate(self, context: Request) -> Optional[Identity]:  # type: ignore
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
            context.user = Identity({})
            return None

        context.user = self._get_identity_for_key(matching_key)
        return context.user

    def _get_identity_for_key(self, key: APIKey) -> Identity:
        """
        Returns an instance of Identity to be used when authentication with a given
        API Key succeeded. Each API Key can be associated with specific roles and
        claims.
        """
        claims = deepcopy(key.claims)
        claims.update({"roles": deepcopy(key.roles)})
        return Identity(claims, authentication_mode=key.scheme)

    def _get_input_secret(self, api_key: APIKey, context: Request) -> Optional[str]:
        value = None
        if api_key.location == APIKeyLocation.HEADER:
            bytes_value = context.get_first_header(api_key.name.encode())
            if bytes_value:
                value = bytes_value.decode()
        elif api_key.location == APIKeyLocation.QUERY:
            list_value = context.query[api_key.name]
            if list_value:
                value = list_value[-1]
        elif api_key.location == APIKeyLocation.COOKIE:
            value = context.cookies[api_key.name]
        else:
            # This should never happen
            raise TypeError("APIKeyLocation not supported.")
        return value

    async def _match_key(self, context: Request) -> Optional[APIKey]:
        """
        Tries to find a matching API Key in the request context.
        Returns the matching API Key if found, otherwise None.
        """
        keys = self._keys

        if not keys and self._keys_provider is not None:
            keys = await self._keys_provider.get_keys()

        for key in keys:
            input_secret = self._get_input_secret(key, context)
            if input_secret and key.is_valid_secret(input_secret):
                return key
        return None
