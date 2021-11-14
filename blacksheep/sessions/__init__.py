import base64
import logging
import warnings
from abc import ABC, abstractmethod
from typing import Any, Awaitable, Callable, Dict, Mapping, Optional

from itsdangerous import Serializer, Signer, URLSafeTimedSerializer  # noqa
from itsdangerous.exc import BadSignature, SignatureExpired

from blacksheep.cookies import Cookie
from blacksheep.messages import Request, Response
from blacksheep.plugins import json as json_plugin
from blacksheep.utils import ensure_str


def get_logger():
    logger = logging.getLogger("blacksheep.sessions")
    logger.setLevel(logging.INFO)
    return logger


class Session:
    def __init__(self, values: Mapping[str, Any] = None) -> None:
        if values is None:
            values = {}
        self._modified = False
        self._values = dict(values)

    @property
    def modified(self) -> bool:
        return self._modified

    def get(self, name: str, default: Any = None) -> Any:
        return self._values.get(name, default)

    def set(self, name: str, value: Any) -> None:
        self._values[name] = value

    def update(self, values: Mapping[str, Any]) -> None:
        self._modified = True
        self._values.update(values)

    def __getitem__(self, name: str) -> Any:
        return self._values[name]

    def __setitem__(self, name: str, value: Any) -> None:
        self._modified = True
        self._values[name] = value

    def __delitem__(self, name: str) -> None:
        del self._values[name]

    def __contains__(self, name: str) -> bool:
        return name in self._values

    def __len__(self) -> int:
        return len(self._values)

    def __eq__(self, o: object) -> bool:
        if self is o:
            return True
        if isinstance(o, Session):
            return self._values == o._values
        return self._values == o

    def clear(self) -> None:
        self._modified = True
        self._values.clear()

    def to_dict(self) -> Dict[str, Any]:
        return self._values.copy()


class SessionSerializer(ABC):
    @abstractmethod
    def read(self, value: str) -> Session:
        """Creates an instance of Session from a string representation."""

    @abstractmethod
    def write(self, session: Session) -> str:
        """Creates the string representation of a session."""


class Encryptor(ABC):
    @abstractmethod
    def encrypt(self, value: str) -> str:
        pass  # pragma: no cover

    @abstractmethod
    def decrypt(self, value: str) -> str:
        pass  # pragma: no cover


class JSONSerializer(SessionSerializer):
    def read(self, value: str) -> Session:
        return Session(json_plugin.loads(value))

    def write(self, session: Session) -> str:
        return json_plugin.dumps(session.to_dict())


class SessionMiddleware:
    def __init__(
        self,
        secret_key: str,
        *,
        session_cookie: str = "session",
        serializer: Optional[SessionSerializer] = None,
        signer: Optional[Serializer] = None,
        encryptor: Optional[Encryptor] = None,
        session_max_age: Optional[int] = None,
    ) -> None:
        if encryptor is not None:
            warnings.warn(
                "The `encryptor` for sessions is deprecated and will be removed in "
                "version 1.3.x.",
                DeprecationWarning,
            )
        self._signer = signer or URLSafeTimedSerializer(secret_key)
        self._serializer = serializer or JSONSerializer()
        self._session_cookie = session_cookie
        self._encryptor = encryptor
        self._logger = get_logger()
        if session_max_age is not None and session_max_age < 1:
            raise ValueError("session_max_age must be a positive number greater than 0")
        self.session_max_age = session_max_age

    def try_read_session(self, raw_value: str) -> Session:
        if self._encryptor:
            try:
                raw_value = self._encryptor.decrypt(raw_value)
            except Exception as decrypt_error:
                # the client might be sending forged tokens
                self._logger.info(
                    "The session value decryption failed.",
                    exc_info=decrypt_error,
                )
                return Session()

        try:
            if self.session_max_age:
                assert isinstance(self._signer, URLSafeTimedSerializer), (
                    "To use a session_max_age, the configured signer must be of "
                    + " TimestampSigner type"
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
            # the client might be sending forged tokens
            self._logger.info("The session signature verification failed.")
            return Session()

        # in this case, we don't try because if the signature verification worked,
        # we expect the value to be valid - if reading fails here it's a bug in
        # in the serializer class
        return self._serializer.read(base64.b64decode(unsigned_value).decode("utf8"))

    def write_session(self, session: Session) -> str:
        payload = base64.b64encode(
            self._serializer.write(session).encode("utf8")
        ).decode()
        signed = ensure_str(self._signer.dumps(payload))  # type: ignore

        if self._encryptor:
            return self._encryptor.encrypt(signed)

        return signed

    def prepare_cookie(self, value: str) -> Cookie:
        return Cookie(self._session_cookie, value, path="/", http_only=True)

    async def __call__(
        self, request: Request, handler: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        session: Optional[Session] = None
        current_session_value = request.cookies.get(self._session_cookie, None)
        if current_session_value:
            session = self.try_read_session(current_session_value)
        else:
            session = Session()
        request.session = session

        response = await handler(request)

        if session.modified:
            response.set_cookie(self.prepare_cookie(self.write_session(session)))
        return response
