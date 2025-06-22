from abc import ABC, abstractmethod
from typing import Any, Dict, Mapping, Optional

from blacksheep.messages import Request, Response


class Session:
    """
    Represents a session for storing and managing user-specific data across requests.

    The Session class provides a dictionary-like interface for storing key-value pairs
    associated with a user's session. It tracks modifications to its contents and
    supports standard dictionary operations such as getting, setting, deleting, and
    updating items. The session data can be converted to a dictionary using `to_dict()`.

    Attributes:
        modified (bool): Indicates whether the session data has been modified.

    Methods:
        get(name, default=None): Retrieves a value by key, returning default if not
            found.
        set(name, value): Sets a value for a given key and marks the session as
            modified.
        update(values): Updates the session with multiple key-value pairs.
        clear(): Removes all items from the session and marks it as modified.
        to_dict(): Returns a shallow copy of the session data as a dictionary.
    """

    def __init__(self, values: Optional[Mapping[str, Any]] = None) -> None:
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
        self._modified = True
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
        self._modified = True
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
    """
    Abstract base class for session serialization and deserialization.

    Implementations of this class provide methods to convert Session objects
    to and from their string representations, enabling storage and retrieval
    of session data in various formats (e.g., JSON, base64, etc.).
    """

    @abstractmethod
    def read(self, value: str) -> Session:
        """Creates an instance of Session from a string representation."""

    @abstractmethod
    def write(self, session: Session) -> str:
        """Creates the string representation of a session."""


class SessionStore(ABC):
    """
    Abstract base class for session storage backends.

    Implementations of this class define how sessions are loaded from and saved to
    a storage medium (such as cookies, databases, or distributed caches) during the
    request-response cycle.
    """

    @abstractmethod
    async def load(self, request: Request) -> Session:
        """Load the session for the given request."""

    @abstractmethod
    async def save(
        self, request: Request, response: Response, session: Session
    ) -> None:
        """Save the session related to the given request-response cycle."""
