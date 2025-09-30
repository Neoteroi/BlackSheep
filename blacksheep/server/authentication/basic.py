"""
This module provides classes to handle Basic Authentication.
"""

import base64
import secrets
from abc import ABC, abstractmethod
from copy import deepcopy
from typing import List, Optional, Tuple

from guardpost import AuthenticationHandler, Identity

from blacksheep.messages import Request
from securestr import Secret


class BasicCredentials:
    """
    Represents a set of Basic Authentication credentials with username and password.
    """

    def __init__(
        self,
        username: str,
        password: Secret,
        claims: Optional[dict] = None,
        roles: Optional[List[str]] = None,
    ) -> None:
        """
        Initialize Basic Authentication credentials.

        Parameters
        ----------
        username : str
            The username for authentication.
        password : Secret
            The password for authentication, stored securely.
        claims : Optional[dict], optional
            Additional claims to include in the authenticated identity, by default None.
        roles : Optional[List[str]], optional
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
    def roles(self) -> List[str]:
        """Returns the roles associated with these credentials."""
        return self._roles

    def to_header_value(self) -> str:
        """
        Returns the value to be used in the Authorization header for these credentials.

        Returns
        -------
        str
            The Authorization header value in the format "Basic base64(username:password)".
        """
        credentials = f"{self._username}:{self._password.get_value()}"
        encoded_credentials = base64.b64encode(credentials.encode("utf-8")).decode(
            "utf-8"
        )
        return f"Basic {encoded_credentials}"

    def is_valid_password(self, provided_password: str) -> bool:
        """
        Validate if the provided password matches the stored password.
        Uses constant-time comparison to prevent timing attacks.

        Parameters
        ----------
        provided_password : str
            The password to validate.

        Returns
        -------
        bool
            True if the password is valid, False otherwise.
        """
        # Note: internally the Secret class uses constant-time comparison
        # to prevent timing attacks, with secrets.compare_digest.
        return self._password == provided_password


class BasicCredentialsProvider(ABC):
    """
    Abstract base class for providing Basic Authentication credentials dynamically.

    This class defines the interface for credential providers that can be used
    with BasicAuthentication to retrieve credentials at runtime. Implementations
    can fetch credentials from various sources such as databases, LDAP, configuration
    files, or external authentication services.

    Examples
    --------
    >>> class DatabaseBasicCredentialsProvider(BasicCredentialsProvider):
    ...     async def get_credentials(self) -> List[BasicCredentials]:
    ...         # Fetch credentials from database
    ...         # TODO: handle password hashing and verification as needed!
    ...         users = await self.fetch_users_from_db()
    ...         return [BasicCredentials(user.username, Secret.from_plain_text(user.password_hash))
    ...                 for user in users if user.is_active]
    """

    @abstractmethod
    async def get_credentials(self) -> List[BasicCredentials]:
        """
        Retrieve a list of valid Basic Authentication credentials.

        This method should return all currently valid credentials that can be used
        for authentication. The method is called by BasicAuthentication during
        the authentication process when no static credentials are provided.

        Returns
        -------
        List[BasicCredentials]
            A list of BasicCredentials instances representing all valid credentials
            for authentication. An empty list indicates no valid credentials are available.

        Notes
        -----
        - This method is called for each authentication attempt, so implementations
          should consider caching strategies for performance if fetching credentials is expensive.
        - The returned list should only contain currently valid and active credentials.
        - Consider implementing rate limiting and other security measures in your provider.
        """
        ...


class BasicAuthentication(AuthenticationHandler):
    """
    AuthenticationHandler that uses Basic Authentication for user authentication.

    This handler parses the Authorization header for Basic authentication credentials
    and validates them against configured credentials or a credentials provider.
    """

    def __init__(
        self,
        *credentials: BasicCredentials,
        scheme: str = "basicAuth",
        credentials_provider: Optional[BasicCredentialsProvider] = None,
        description: Optional[str] = None,
    ) -> None:
        """
        Creates a new instance of BasicAuthentication.

        Parameters
        ----------
        *credentials : BasicCredentials
            Static credentials handled by this instance.
        scheme: arbitrary scheme name of this authentication handler, default "basicAuth".
        credentials_provider : Optional[BasicCredentialsProvider], optional
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
        self._credentials = tuple(credentials)
        self._credentials_provider = credentials_provider
        self.description = description

        if not credentials and credentials_provider is None:
            raise ValueError(
                "Either credentials or credentials_provider must be provided"
            )

    @property
    def scheme(self) -> str:
        return self._scheme

    async def authenticate(self, context: Request) -> Optional[Identity]:  # type: ignore
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
        Optional[Identity]
            An Identity object if authentication succeeds, None otherwise.
        """
        authorization_value = context.get_first_header(b"Authorization")

        if not authorization_value:
            context.user = Identity({})
            return None

        if not authorization_value.startswith(b"Basic "):
            context.user = Identity({})
            return None

        # Decode the base64 encoded credentials
        try:
            encoded_credentials = authorization_value[6:]  # Remove "Basic " prefix
            decoded_credentials = base64.b64decode(encoded_credentials).decode("utf-8")
            username, password = decoded_credentials.split(":", 1)
        except (ValueError, UnicodeDecodeError):
            # Invalid base64 or malformed credentials
            context.user = Identity({})
            return None

        matching_credentials = await self._match_credentials(username, password)

        if matching_credentials is None:
            context.user = Identity({})
            return None

        context.user = self._get_identity_for_credentials(matching_credentials)
        return context.user

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
        claims.update({"sub": credentials.username, "roles": credentials.roles})
        return Identity(claims, authentication_mode=self.scheme)

    async def _match_credentials(
        self, username: str, password: str
    ) -> Optional[BasicCredentials]:
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
        Optional[BasicCredentials]
            The matching credentials if found, None otherwise.
        """
        credentials = self._credentials

        if not credentials and self._credentials_provider is not None:
            credentials = await self._credentials_provider.get_credentials()

        for cred in credentials:
            # Use constant-time comparison for username to prevent timing attacks
            if secrets.compare_digest(
                cred.username, username
            ) and cred.is_valid_password(password):
                return cred

        return None
