"""
This module provides classes to handle Basic Authentication.
"""

import base64
import secrets
from abc import ABC, abstractmethod
from copy import deepcopy

from essentials.secrets import Secret
from guardpost import AuthenticationHandler, Identity
from guardpost.errors import InvalidCredentialsError

from blacksheep.messages import Request


class BasicCredentials:
    """
    Represents a set of Basic Authentication credentials with username and password.
    """

    def __init__(
        self,
        username: str,
        password: Secret,
        claims: dict | None = None,
        roles: list[str] | None = None,
    ) -> None:
        """
        Initialize Basic Authentication credentials.

        Parameters
        ----------
        username : str
            The username for authentication.
        password : Secret
            The password for authentication, stored securely.
        claims : dict | None, optional
            Additional claims to include in the authenticated identity, by default None.
        roles : list[str] | None, optional
            List of roles to assign to the authenticated identity, by default None.
        """
        self._username = username
        self._password = password
        self._claims = claims or {}
        self._roles = roles or []

    @property
    def username(self) -> str:
        """Returns the username."""
        return self._username

    @property
    def claims(self) -> dict:
        """Returns the claims associated with these credentials."""
        return self._claims

    @property
    def roles(self) -> list[str]:
        """Returns the roles associated with these credentials."""
        return self._roles

    def to_header_value(self) -> str:
        """
        Returns the value to be used in the Authorization header for these credentials.

        Returns
        -------
        str
            The Authorization header value in the format
            "Basic base64(username:password)".
        """
        credentials = f"{self._username}:{self._password.get_value()}"
        encoded_credentials = base64.b64encode(credentials.encode("utf-8")).decode(
            "utf-8"
        )
        return f"Basic {encoded_credentials}"

    def match(self, username: str, password: str) -> bool:
        """
        Returns a value indicating whether the given username and password combination
        matches this credentials object. This method assumes that the username
        configured for this credentials object is a valid unicode string, and ignores
        encoding errors in the username received from the client.
        """
        return (
            secrets.compare_digest(
                self.username.encode("utf8"), username.encode("utf8", errors="ignore")
            )
            and self._password == password
        )


class BasicCredentialsProvider(ABC):
    """
    Abstract base class for providing Basic Authentication credentials dynamically.

    This class defines the interface for credential providers that can be used
    with BasicAuthentication to retrieve credentials at runtime. Implementations
    can fetch credentials from various sources such as databases, LDAP, configuration
    files, or external authentication services.
    """

    @abstractmethod
    async def get_credentials(self) -> list[BasicCredentials]:
        """
        Retrieve a list of valid Basic Authentication credentials.

        This method should return all currently valid credentials that can be used
        for authentication. The method is called by BasicAuthentication during
        the authentication process when no static credentials are provided.

        Returns
        -------
        list[BasicCredentials]
            A list of BasicCredentials instances representing all valid credentials
            for authentication. An empty list indicates no valid credentials are
            available.

        Notes
        -----
        - This method is called for each authentication attempt, so implementations
          should consider caching strategies for performance if fetching credentials is
          expensive.
        - The returned list should only contain currently valid and active credentials.
        - Consider implementing rate limiting and other security measures in your
          provider.
        """


class BasicAuthentication(AuthenticationHandler):
    """
    AuthenticationHandler that uses Basic Authentication for user authentication.

    This handler parses the Authorization header for Basic authentication credentials
    and validates them against configured credentials or a credentials provider.
    """

    def __init__(
        self,
        *credentials: BasicCredentials,
        scheme: str = "Basic",
        credentials_provider: BasicCredentialsProvider | None = None,
        description: str | None = None,
    ) -> None:
        """
        Creates a new instance of BasicAuthentication.

        Parameters
        ----------
        *credentials : BasicCredentials
            Static credentials handled by this instance.
        scheme: arbitrary scheme name of this authentication handler, default "Basic".
        credentials_provider : BasicCredentialsProvider | None, optional
            An optional provider that can be used to retrieve credentials dynamically.
            If not provided, only the static credentials will be used.
        description: optional description.
        Raises
        ------
        ValueError
            If neither credentials nor credentials_provider is provided.
        """
        super().__init__()
        self._scheme = scheme
        self._credentials: tuple[BasicCredentials, ...] = tuple(credentials)
        self._credentials_provider = credentials_provider
        self.description = description

        if not credentials and credentials_provider is None:
            raise ValueError(
                "Either credentials or credentials_provider must be provided"
            )

    @property
    def scheme(self) -> str:
        return self._scheme

    async def authenticate(self, context: Request) -> Identity | None:
        """
        Tries to authenticate the request using Basic Authentication.

        If authentication succeeds, returns an Identity with the authentication mode set
        to the scheme of the matching credentials. If no matching credentials are found,
        returns None.

        Parameters
        ----------
        context : Request
            The HTTP request context.

        Returns
        -------
        Identity | None
            An Identity object if authentication succeeds, None otherwise.
        """
        authorization_value = context.get_first_header(b"Authorization")

        if not authorization_value:
            return None

        if not authorization_value.startswith(b"Basic "):
            return None

        # Decode the base64 encoded credentials
        try:
            encoded_credentials = authorization_value[6:]  # Remove "Basic " prefix
            decoded_credentials = base64.b64decode(encoded_credentials).decode("utf-8")
            username, password = decoded_credentials.split(":", 1)
        except (ValueError, UnicodeDecodeError):
            # Invalid base64 or malformed credentials
            return None

        matching_credentials = await self._match_credentials(username, password)

        if matching_credentials is None:
            # The user provided a username and password combination, but they are
            # invalid. This kind of events must be logged and rate-limited to avoid the
            # risk of attackers trying to guess usernames and passwords.
            raise InvalidCredentialsError(context.original_client_ip)

        return self._get_identity_for_credentials(matching_credentials)

    def _get_identity_for_credentials(self, credentials: BasicCredentials) -> Identity:
        """
        Create an Identity object for the given credentials.

        Parameters
        ----------
        credentials : BasicCredentials
            The credentials to create an identity for.

        Returns
        -------
        Identity
            An Identity object containing the user's claims and roles.
        """
        claims = deepcopy(credentials.claims)
        claims.update(
            {"sub": credentials.username, "roles": [role for role in credentials.roles]}
        )
        return Identity(claims, authentication_mode=self.scheme)

    async def _match_credentials(
        self, username: str, password: str
    ) -> BasicCredentials | None:
        """
        Tries to find matching credentials for the given username and password.

        Parameters
        ----------
        username : str
            The provided username.
        password : str
            The provided password.

        Returns
        -------
        BasicCredentials | None
            The matching credentials if found, None otherwise.
        """
        credentials = self._credentials

        if not credentials and self._credentials_provider is not None:
            credentials = await self._credentials_provider.get_credentials()

        for cred in credentials:
            if cred.match(username, password):
                return cred

        return None
