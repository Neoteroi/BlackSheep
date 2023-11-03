from datetime import datetime

try:
    from datetime import UTC
except ImportError:
    from datetime import timezone

    UTC = timezone.utc
from typing import Any, Optional, Sequence

from guardpost import AuthenticationHandler, Identity
from itsdangerous import Serializer
from itsdangerous.exc import BadSignature

from blacksheep.baseapp import get_logger
from blacksheep.cookies import Cookie
from blacksheep.messages import Request, Response
from blacksheep.server.dataprotection import get_serializer
from blacksheep.utils import ensure_str


class CookieAuthentication(AuthenticationHandler):
    """
    An AuthenticationHandler that tries to restore the user's context from a cookie.
    """

    def __init__(
        self,
        cookie_name: str = "identity",
        secret_keys: Optional[Sequence[str]] = None,
        serializer: Optional[Serializer] = None,
        auth_scheme: Optional[str] = None,
    ) -> None:
        """
        Creates a new instance of CookieAuthentication handler, that tries to obtain
        the user's identity by cookie.

        Parameters
        ----------
        cookie_name : str, optional
            The name of the cookie used to restore user's identity, by default
            "identity"
        secret_key : str, optional
            If specified, the key used by a default serializer (when no serializer is
            specified), by default None
        serializer : Optional[Serializer], optional
            If specified, controls the serializer used to sign and verify the values
            of cookies used for identities, by default None
        auth_scheme : str, optional
            The name of the authentication scheme declared for users' identity, by
            default f"CookieAuth: {cookie_name}"
        """
        super().__init__()
        self.cookie_name = cookie_name
        self.serializer = serializer or get_serializer(
            secret_keys, f"{cookie_name}auth"
        )
        self.auth_scheme = auth_scheme or f"CookieAuth: {cookie_name}"
        self.logger = get_logger()

    def set_cookie(self, data: Any, response: Response, secure: bool = False) -> None:
        """
        Sets the cookie used for authentication. If a cookie is set, it is assumed that
        the user is recognized (authenticated). The passed value is serialized, meaning
        signed and encrypted using the `itsdangerous.Serializer` associated with this
        CookieAuthentication handler. A common scenario is that data is a dictionary
        with claims describing the identity of the user (e.g. id_token claims).

        Parameters
        ----------
        data : Any
            Anything that can be serialized by an `itsdangerous.Serializer`, a
            dictionary in the most common scenario.
        response : Response
            The instance of blacksheep `Response` that will include the cookie for the
            client.
        secure : bool, optional
            Whether the set cookie should have secure flag, by default False
        """
        value = self.serializer.dumps(data)

        response.set_cookie(
            Cookie(
                self.cookie_name,
                ensure_str(value),  # type: ignore
                domain=None,
                path="/",
                http_only=True,
                secure=secure,
                expires=(
                    datetime.fromtimestamp(data["exp"], UTC) if "exp" in data else None
                ),
            )
        )

    def unset_cookie(self, response: Response) -> None:
        """
        Unsets the cookie used for authentication.
        """
        response.unset_cookie(self.cookie_name)

    def set_user_context(self, context: Request, data: Any) -> None:
        """
        Sets the user context, when user's data was parsed and validated from a cookie.
        """
        context.user = Identity(data, self.auth_scheme)

    async def authenticate(self, context: Request) -> Optional[Identity]:
        cookie = context.get_cookie(self.cookie_name)

        if cookie is None:
            context.user = Identity({})
        else:
            try:
                value = self.serializer.loads(cookie)
            except BadSignature:
                self.logger.debug(
                    "Cookie authentication failed (%s), invalid signature.",
                    self.cookie_name,
                )
                context.user = Identity({})
            else:
                self.set_user_context(context, value)
        return None
