from typing import TYPE_CHECKING, Awaitable, Callable

from itsdangerous import Serializer

from blacksheep.messages import Request, Response
from blacksheep.middlewares import MiddlewareCategory
from blacksheep.sessions.abc import Session, SessionSerializer, SessionStore
from blacksheep.sessions.cookies import CookieSessionStore

if TYPE_CHECKING:
    from blacksheep.server.application import Application


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


def use_sessions(
    app: "Application",
    store: str | SessionStore,
    *,
    session_cookie: str = "session",
    serializer: SessionSerializer | None = None,
    signer: Serializer | None = None,
    session_max_age: int | None = None,
) -> None:
    """
    Configures session support for the application.

    This method enables session management by adding a SessionMiddleware to the
    application.
    It can be used with either a secret key (to use cookie-based sessions) or a
    custom SessionStore.

    Args:
        store (str | SessionStore): A secret key for cookie-based sessions,
            or an instance of SessionStore for custom session storage.
        session_cookie (str, optional): Name of the session cookie. Defaults to
            session".
        serializer (SessionSerializer, optional): Serializer for session data.
        signer (Serializer, optional): Serializer used for signing session data.
        session_max_age (int, optional): Maximum age of the session in seconds.

    Usage:
        app.use_sessions("my-secret-key")
        # or
        app.use_sessions(MyCustomSessionStore())
    """
    if isinstance(store, str):
        session_middleware = SessionMiddleware(
            CookieSessionStore(
                store,
                session_cookie=session_cookie,
                serializer=serializer,
                signer=signer,
                session_max_age=session_max_age,
            )
        )
    elif isinstance(store, SessionStore):
        session_middleware = SessionMiddleware(store)

    app.middlewares.append(session_middleware, MiddlewareCategory.SESSION)
