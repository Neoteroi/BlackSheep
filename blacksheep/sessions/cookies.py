import base64
from typing import Optional

from itsdangerous import (
    BadSignature,
    Serializer,
    SignatureExpired,
    URLSafeTimedSerializer,
)

from blacksheep.cookies import Cookie
from blacksheep.messages import Request, Response
from blacksheep.sessions.abc import Session, SessionSerializer, SessionStore
from blacksheep.sessions.json import JSONSerializer
from blacksheep.sessions.logs import get_logger
from blacksheep.utils import ensure_str


class CookieSessionStore(SessionStore):
    """
    Session store implementation that saves session data in a signed cookie.

    This store serializes session data, signs it using a secret key, and stores it
    in a cookie on the client side. It supports optional session expiration and
    custom serializers and signers.

    Args:
        secret_key (str): Secret key used to sign session cookies.
        session_cookie (str, optional): Name of the session cookie. Defaults to
            "session".
        serializer (SessionSerializer, optional): Serializer for session data. Defaults
            to JSONSerializer.
        signer (Serializer, optional): Serializer used for signing. Defaults to
            URLSafeTimedSerializer.
        session_max_age (int, optional): Maximum age of the session in seconds.

    Raises:
        ValueError: If session_max_age is provided and is less than 1.
    """

    def __init__(
        self,
        secret_key: str,
        *,
        session_cookie: str = "session",
        serializer: Optional[SessionSerializer] = None,
        signer: Optional[Serializer] = None,
        session_max_age: Optional[int] = None,
    ) -> None:
        self._signer = signer or URLSafeTimedSerializer(secret_key)
        self._serializer = serializer or JSONSerializer()
        self._session_cookie = session_cookie
        self._logger = get_logger()
        if session_max_age is not None and session_max_age < 1:
            raise ValueError("session_max_age must be a positive number greater than 0")
        self.session_max_age = session_max_age

    def _try_read_session(self, raw_value: str) -> Session:
        try:
            if self.session_max_age:
                assert isinstance(self._signer, URLSafeTimedSerializer), (
                    "To use a session_max_age, the configured signer must be of "
                    + " URLSafeTimedSerializer type"
                )
                unsigned_value = self._signer.loads(
                    raw_value, max_age=self.session_max_age
                )
            else:
                unsigned_value = self._signer.loads(raw_value)
        except SignatureExpired:
            self._logger.info("The session signature has expired.")
            return Session()
        except BadSignature:
            self._logger.info("The session signature verification failed.")
            return Session()
        return self._serializer.read(base64.b64decode(unsigned_value).decode("utf8"))

    def _write_session(self, session: Session) -> str:
        payload = base64.b64encode(
            self._serializer.write(session).encode("utf8")
        ).decode()
        return ensure_str(self._signer.dumps(payload))  # type: ignore

    def _prepare_cookie(self, value: str) -> Cookie:
        return Cookie(self._session_cookie, value, path="/", http_only=True)

    async def load(self, request: Request) -> Session:
        current_session_value = request.cookies.get(self._session_cookie, None)
        if current_session_value:
            return self._try_read_session(current_session_value)
        return Session()

    async def save(
        self, request: Request, response: Response, session: Session
    ) -> None:
        response.set_cookie(self._prepare_cookie(self._write_session(session)))
