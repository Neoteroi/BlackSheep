from abc import ABC, abstractmethod
from enum import Enum
from typing import Literal, Optional, Union

from guardpost import AuthenticationHandler, Identity

from blacksheep.messages import Request


class APIKeySecretProvider(ABC):
    @abstractmethod
    async def get_secret(self) -> str: ...


class APIKeyLocation(Enum):
    HEADER = "header"
    QUERY = "query"
    COOKIE = "cookie"


APIKeyLocationType = Literal["header", "query", "cookie"]


class APIKey:
    def __init__(
        self,
        scheme: str,
        name: str,
        secret: str,
        location: Union[APIKeyLocationType, APIKeyLocation] = APIKeyLocation.HEADER,
    ) -> None:
        self._scheme = scheme
        self._name = name
        self._secret = secret
        self._location = APIKeyLocation(location)


class APIKeyAuthentication(AuthenticationHandler):
    """
    AuthenticationHandler that uses API Keys for authentication.
    """

    def __init__(
        self,
        scheme: str,
        key_name: str,
        keys_provider: Optional[APIKeySecretProvider] = None,
        location: Union[APIKeyLocationType, APIKeyLocation] = APIKeyLocation.HEADER,
    ) -> None:
        """ """
        super().__init__()
        self._scheme = scheme
        self._key_name = key_name
        self._location = APIKeyLocation(location)
        self._secret_provider = keys_provider

    @property
    def scheme(self) -> str:
        """Returns the name of the Authentication Scheme used by this handler."""
        return self._scheme

    def _get_input_key(self, context: Request) -> Optional[str]:
        value = None
        if self._location == APIKeyLocation.HEADER:
            bytes_value = context.get_single_header(self._key_name.encode())
            if bytes_value:
                value = bytes_value.decode()
        elif self._location == APIKeyLocation.QUERY:
            list_value = context.query[self._key_name]
            if list_value:
                value = list_value[-1]
        elif self._location == APIKeyLocation.COOKIE:
            value = context.cookies[self._key_name]
        else:
            # This should never happen
            raise RuntimeError("APIKeyLocation not supported.")
        return value

    async def _is_valid_input_key(self, value: str) -> bool:
        # TODO: support checking for rotating key
        if self._secret_key is None:
            assert self._secret_provider is not None
            self._secret_key = await self._secret_provider.get_secret()

        return self._secret_key == value

    async def authenticate(self, context: Request) -> Optional[Identity]:
        value = self._get_input_key(context)

        if value is None:
            return None

        if self._is_valid_input_key(value):
            context.user = Identity({}, authentication_mode=self.scheme)
        else:
            # TODO: what to do here? Log the key was wrong? Raise Forbidden?
            ...
