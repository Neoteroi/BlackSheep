from typing import Awaitable, Callable

from blacksheep.messages import Request, Response
from blacksheep.sessions.abc import Session, SessionSerializer, SessionStore

__all__ = [
    "Session",
    "SessionMiddleware",
    "SessionStore",
    "SessionSerializer",
]


class SessionMiddleware:
    """
    Middleware for managing user sessions in a BlackSheep application.

    This middleware loads the session from the provided session store at the beginning
    of the request, attaches it to the request object, and saves the session back to
    the store if it was modified during request processing.

    Args:
        store (SessionStore): The session store used to load and save session data.

    Usage:
        Add this middleware to your application to enable session support.
    """

    def __init__(self, store: SessionStore) -> None:
        self._store = store

    async def __call__(
        self, request: Request, handler: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        session = await self._store.load(request)
        request.session = session
        response = await handler(request)
        if session.modified:
            await self._store.save(request, response, session)
        return response
