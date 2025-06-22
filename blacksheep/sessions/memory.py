import secrets
from typing import Any, Dict

from blacksheep.cookies import Cookie
from blacksheep.messages import Request, Response
from blacksheep.sessions.abc import Session, SessionStore


class InMemorySessionStore(SessionStore):
    """
    An in-memory implementation of SessionStore for managing user sessions. The session
    ID is transmitted in Cookies, to restore the same session information across
    request-response cycles.

    This session store keeps session data in a Python dictionary, mapping session IDs
    to session data. It is suitable for development and testing environments, but not
    recommended for production use as session data will be lost when the application
    restarts and is not shared across multiple processes or servers.

    Args:
        cookie_name (str): The name of the cookie used to store the session ID.

    Methods:
        load(request): Loads the session associated with the request, or creates a new
            one.
        save(request, response, session): Saves the session data and sets the session
            cookie.
    """

    def __init__(self, cookie_name: str = "session"):
        self._session_cookie_name = cookie_name
        self._sessions: Dict[str, Any] = {}

    async def load(self, request: Request) -> Session:
        session_id = request.cookies.get(self._session_cookie_name)
        if session_id and session_id in self._sessions:
            return Session(self._sessions[session_id])
        # Create a new session
        session_id = secrets.token_urlsafe(32)
        session = Session({"id": session_id})
        self._sessions[session_id] = session.to_dict()
        return session

    async def save(
        self, request: Request, response: Response, session: Session
    ) -> None:
        # Use existing session_id or the one generated in load()
        session = request.session
        session_id = session["id"]
        if session_id:
            # Update information in-memory
            self._sessions[session_id] = session.to_dict()
            # Set the session_id cookie in the response
            response.set_cookie(
                Cookie(self._session_cookie_name, session_id, http_only=True, path="/")
            )
