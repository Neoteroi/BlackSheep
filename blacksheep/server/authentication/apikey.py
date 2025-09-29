"""
This module contains an AuthenticationHandler that uses API Keys for authentication.
"""

from abc import ABC, abstractmethod
from copy import deepcopy
from enum import Enum
from typing import List, Literal, Optional, Sequence, Union

from guardpost import AuthenticationHandler, Identity

from blacksheep.messages import Request


class APIKeyLocation(Enum):
    HEADER = "header"
    QUERY = "query"
    COOKIE = "cookie"


APIKeyLocationValue = Literal["header", "query", "cookie"]


class APIKey:
    def __init__(
        self,
        name: str,
        secret: Optional[str] = None,
        secrets: Optional[Sequence[str]] = None,
        scheme: str = "apikey",
        location: Union[APIKeyLocationValue, APIKeyLocation] = "header",
        claims: Optional[dict] = None,
        roles: Optional[List[str]] = None,
    ) -> None:
        self._scheme = scheme
        self._name = name
        self._secret = secret
        self._location = APIKeyLocation(location)
        self._claims = claims or {}
        self._roles = roles or []

        # Handle secret/secrets parameters
        if secret is not None and secrets is not None:
            raise ValueError("Cannot specify both 'secret' and 'secrets' parameters")
        elif secret is not None:
            self._secrets = {secret}
        elif secrets is not None:
            self._secrets = set(secrets)
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
        """Validate if the provided secret matches any of the configured secrets"""
        return provided_secret in self._secrets


class APIKeysProvider(ABC):
    @abstractmethod
    async def get_keys(self) -> List[APIKey]: ...


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
        *keys : APIKey
            Exact keys handled by this instance.
        keys_provider : Optional[APIKeysProvider]
            An optional provider that can be used to retrieve keys dynamically.
            If not provided, the keys passed as parameters will be used.
        """
        super().__init__()
        self._keys = keys
        self._keys_provider = keys_provider

        if not keys and keys_provider is None:
            raise ValueError("Either keys or keys_provider must be provided")

    def is_valid_api_secret(self, api_key: APIKey, secret_from_client: str) -> bool:
        return api_key.is_valid_secret(secret_from_client)

    async def authenticate(self, context: Request) -> Optional[Identity]:  # type: ignore
        """
        Tries to authenticate the request using API Keys.
        If authentication succeeds, returns an Identity with the authentication mode set
        to the scheme of the matching API Key. If no matching API Key is found, returns
        None.
        """
        matching_key = await self._match_key(context)

        if matching_key is None:
            context.user = Identity({})
            return None

        context.user = self._get_identity_for_key(matching_key)
        return context.user

    def _get_identity_for_key(self, key: APIKey) -> Identity:
        claims = deepcopy(key.claims)
        claims.update({"roles": key.roles})
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
            raise RuntimeError("APIKeyLocation not supported.")
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
            if input_secret and self.is_valid_api_secret(key, input_secret):
                return key
        return None
