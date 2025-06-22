import logging
from contextlib import asynccontextmanager
from functools import wraps
from inspect import signature, unwrap
from pathlib import Path
from typing import (
    Any,
    Awaitable,
    Callable,
    Iterable,
    List,
    Optional,
    Sequence,
    Set,
    Tuple,
    Type,
    Union,
)

from guardpost import (
    AuthenticationStrategy,
    AuthorizationStrategy,
    Policy,
    UnauthorizedError,
)
from guardpost.authorization import ForbiddenError
from guardpost.common import AuthenticatedRequirement
from itsdangerous import Serializer
from rodi import ContainerProtocol

from blacksheep.baseapp import BaseApplication, handle_not_found
from blacksheep.common import extend
from blacksheep.common.files.asyncfs import FilesHandler
from blacksheep.contents import ASGIContent
from blacksheep.exceptions import NotFound
from blacksheep.messages import Request, Response
from blacksheep.middlewares import get_middlewares_chain
from blacksheep.scribe import send_asgi_response
from blacksheep.server.asgi import get_request_url_from_scope
from blacksheep.server.authentication import (
    AuthenticateChallenge,
    get_authentication_middleware,
    handle_authentication_challenge,
)
from blacksheep.server.authorization import (
    AuthorizationWithoutAuthenticationError,
    get_authorization_middleware,
    handle_forbidden,
    handle_unauthorized,
)
from blacksheep.server.controllers import ControllersManager
from blacksheep.server.cors import CORSPolicy, CORSStrategy, get_cors_middleware
from blacksheep.server.env import EnvironmentSettings
from blacksheep.server.errors import ServerErrorDetailsHandler
from blacksheep.server.files import DefaultFileOptions
from blacksheep.server.files.dynamic import serve_files_dynamic
from blacksheep.server.normalization import normalize_handler, normalize_middleware
from blacksheep.server.process import use_shutdown_handler
from blacksheep.server.responses import _ensure_bytes
from blacksheep.server.routing import (
    MountRegistry,
    RouteMethod,
    Router,
    RoutesRegistry,
)
from blacksheep.server.routing import router as default_router
from blacksheep.server.routing import (
    validate_default_router,
    validate_router,
)
from blacksheep.server.websocket import WebSocket, format_reason
from blacksheep.sessions import SessionMiddleware, SessionSerializer
from blacksheep.sessions.abc import SessionStore
from blacksheep.settings.di import di_settings
from blacksheep.utils import join_fragments
from blacksheep.utils.meta import get_parent_file, import_child_modules


def get_default_headers_middleware(
    headers: Sequence[Tuple[str, str]],
) -> Callable[..., Awaitable[Response]]:
    raw_headers = tuple((name.encode(), value.encode()) for name, value in headers)

    async def default_headers_middleware(
        request: Request, handler: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await handler(request)
        for name, value in raw_headers:
            response.add_header(name, value)
        return response

    return default_headers_middleware


class ApplicationEvent:
    def __init__(self, context: Any) -> None:
        self._handlers: List[Callable[..., Any]] = []
        self.context = context

    def __iadd__(self, handler: Callable[..., Any]) -> "ApplicationEvent":
        self._handlers.append(self._wrap_discard(handler))
        return self

    def __isub__(self, handler: Callable[..., Any]) -> "ApplicationEvent":
        to_remove = [
            callback
            for callback in self._handlers
            if callback is handler or unwrap(callback) is handler
        ]
        for callback in to_remove:
            self._handlers.remove(callback)
        return self

    def __len__(self) -> int:
        return len(self._handlers)

    def __call__(self, *args) -> Any:
        if args:
            self.__iadd__(args[0])
            return args[0]

        def decorator(fn):
            self.__iadd__(fn)
            return fn

        return decorator

    async def fire(self, *args: Any, **kwargs: Any) -> None:
        for handler in self._handlers:
            await handler(self.context, *args, **kwargs)

    def _wrap_discard(self, function):
        """
        If the given function does not accept any parameter, returns a wrapper with a
        discard parameter; otherwise returns the same function.
        """
        if len(signature(function).parameters) == 0:

            @wraps(function)
            async def wrap_handler(_):
                await function()

            return wrap_handler
        else:
            return function


class ApplicationSyncEvent(ApplicationEvent):
    """
    ApplicationEvent whose subscribers must be synchronous functions.
    """

    def fire_sync(self, *args: Any, **keywargs: Any) -> None:
        for handler in self._handlers:
            handler(self.context, *args, **keywargs)

    async def fire(self, *args: Any, **keywargs: Any) -> None:
        raise TypeError(
            "The event handlers in this ApplicationEvent must be synchronous!"
        )


class ApplicationStartupError(RuntimeError):
    """Base class for errors occurring when an application starts."""


class ApplicationAlreadyStartedCORSError(TypeError):
    def __init__(self) -> None:
        super().__init__(
            "The application is already running, configure CORS rules "
            "before starting the application"
        )


class Application(BaseApplication):
    """
    Server application class.
    """

    def __init__(
        self,
        *,
        router: Optional[Router] = None,
        services: Optional[ContainerProtocol] = None,
        show_error_details: bool = False,
        mount: Optional[MountRegistry] = None,
    ):
        env_settings = EnvironmentSettings()
        if router is None:
            router = default_router if env_settings.use_default_router else Router()
        if services is None:
            services = di_settings.get_default_container()
        if mount is None:
            mount = MountRegistry(env_settings.mount_auto_events)

        super().__init__(show_error_details or env_settings.show_error_details, router)

        assert services is not None
        self._services: ContainerProtocol = services
        self.middlewares: List[Callable[..., Awaitable[Response]]] = []
        self._default_headers: Optional[Tuple[Tuple[str, str], ...]] = None
        self._middlewares_configured = False
        self._cors_strategy: Optional[CORSStrategy] = None
        self._authentication_strategy: Optional[AuthenticationStrategy] = None
        self._authorization_strategy: Optional[AuthorizationStrategy] = None
        self.on_start = ApplicationEvent(self)
        self.after_start = ApplicationEvent(self)
        self.on_stop = ApplicationEvent(self)
        self.on_middlewares_configuration = ApplicationSyncEvent(self)
        self.started = False
        self.files_handler = FilesHandler()
        self.server_error_details_handler = ServerErrorDetailsHandler()
        self._session_middleware: Optional[SessionMiddleware] = None
        self.base_path: str = ""  # TODO: deprecate
        self._mount_registry = mount
        validate_router(self)
        parent_file = get_parent_file()

        if parent_file:
            _auto_import_controllers(parent_file)
            _auto_import_routes(parent_file)

        if env_settings.add_signal_handler:
            use_shutdown_handler(self)

    @property
    def controllers_router(self) -> RoutesRegistry:
        return self.router.controllers_routes

    @controllers_router.setter
    def controllers_router(self, value) -> None:
        self.router.controllers_routes = value

    @property
    def services(self) -> ContainerProtocol:
        """
        Returns the object that provides services of this application.
        """
        return self._services

    @property
    def default_headers(self) -> Optional[Tuple[Tuple[str, str], ...]]:
        return self._default_headers

    @default_headers.setter
    def default_headers(self, value: Optional[Tuple[Tuple[str, str], ...]]) -> None:
        self._default_headers = tuple(value) if value else None

    @property
    def cors(self) -> CORSStrategy:
        if not self._cors_strategy:
            raise TypeError(
                "CORS settings are not initialized for the application. "
                + "Use `app.use_cors()` method before using this property."
            )
        return self._cors_strategy

    @property
    def mount_registry(self) -> MountRegistry:
        return self._mount_registry

    def mount(self, path: str, app: Callable) -> None:
        """
        Mounts an ASGI application at the given path. When a web request has a URL path
        that starts with the mount path, it is handled by the mounted app (the mount
        path is stripped from the final URL path received by the child application).

        If the child application is a BlackSheep application, it requires handling of
        its lifecycle events. This can be automatic, if the environment variable

            APP_MOUNT_AUTO_EVENTS is missing or set to "1" or "true" (case insensitive)

        or explicitly enabled, if the parent app's is configured this way:

            parent_app.mount_registry.auto_events = True
        """
        if app is self:
            raise TypeError("Cannot mount an application into itself")

        self._mount_registry.mount(path, app)

        if isinstance(app, Application):
            app.base_path = (
                join_fragments(self.base_path, path) if self.base_path else path
            )

            if self._mount_registry.auto_events:
                self._bind_child_app_events(app)

        if len(self._mount_registry.mounted_apps) == 1:
            # the first time a mount is configured, extend the application
            # to use mounts when handling web requests
            self.extend(MountMixin)

    def _bind_child_app_events(self, app: "Application") -> None:
        @self.on_start
        async def handle_child_app_start(_):
            await app.start()

        @self.after_start
        async def handle_child_app_after_start(_):
            await app.after_start.fire()

        @self.on_middlewares_configuration
        def handle_child_app_on_middlewares_configuration(_):
            app.on_middlewares_configuration.fire_sync()

        @self.on_stop
        async def handle_child_app_stop(_):
            await app.stop()

    def use_sessions(
        self,
        store: Union[str, SessionStore],
        *,
        session_cookie: str = "session",
        serializer: Optional[SessionSerializer] = None,
        signer: Optional[Serializer] = None,
        session_max_age: Optional[int] = None,
    ) -> None:
        """
        Configures session support for the application.

        This method enables session management by adding a SessionMiddleware to the
        application.
        It can be used with either a secret key (to use cookie-based sessions) or a
        custom SessionStore.

        Args:
            store (Union[str, SessionStore]): A secret key for cookie-based sessions,
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
            from blacksheep.sessions.cookies import CookieSessionStore

            self._session_middleware = SessionMiddleware(
                CookieSessionStore(
                    store,
                    session_cookie=session_cookie,
                    serializer=serializer,
                    signer=signer,
                    session_max_age=session_max_age,
                )
            )
        elif isinstance(store, SessionStore):
            self._session_middleware = SessionMiddleware(store)

    def use_cors(
        self,
        *,
        allow_methods: Union[None, str, Iterable[str]] = None,
        allow_headers: Union[None, str, Iterable[str]] = None,
        allow_origins: Union[None, str, Iterable[str]] = None,
        allow_credentials: bool = False,
        max_age: int = 5,
        expose_headers: Union[None, str, Iterable[str]] = None,
    ) -> CORSStrategy:
        """
        Enables CORS for the application, specifying the default rules to be applied
        for all request handlers.
        """
        if self.started:
            raise ApplicationAlreadyStartedCORSError()
        self._cors_strategy = CORSStrategy(
            CORSPolicy(
                allow_methods=allow_methods,
                allow_headers=allow_headers,
                allow_origins=allow_origins,
                allow_credentials=allow_credentials,
                max_age=max_age,
                expose_headers=expose_headers,
            ),
            self.router,
        )

        # Note: the following is a no-op request handler, necessary to activate handling
        # of OPTIONS preflight requests.
        # However, preflight requests are handled by the CORS middleware. This is to
        # stop the chain of middlewares and prevent extra logic from executing for
        # preflight requests (e.g. authentication logic)
        @self.router.options("*")
        async def options_handler(request: Request) -> Response:
            return Response(404)

        # User defined catch-all OPTIONS request handlers are not supported when the
        # built-in CORS handler is used.
        return self._cors_strategy

    def add_cors_policy(
        self,
        policy_name,
        *,
        allow_methods: Union[None, str, Iterable[str]] = None,
        allow_headers: Union[None, str, Iterable[str]] = None,
        allow_origins: Union[None, str, Iterable[str]] = None,
        allow_credentials: bool = False,
        max_age: int = 5,
        expose_headers: Union[None, str, Iterable[str]] = None,
    ) -> None:
        """
        Configures a set of CORS rules that can later be applied to specific request
        handlers, by name.

        The CORS policy can then be associated to specific request handlers,
        using the instance of `CORSStrategy` as a function decorator:

        @app.cors("example")
        @app.route("/")
        async def foo():
            ....
        """
        if self.started:
            raise ApplicationAlreadyStartedCORSError()

        if not self._cors_strategy:
            self.use_cors()

        assert self._cors_strategy is not None
        self._cors_strategy.add_policy(
            policy_name,
            CORSPolicy(
                allow_methods=allow_methods,
                allow_headers=allow_headers,
                allow_origins=allow_origins,
                allow_credentials=allow_credentials,
                max_age=max_age,
                expose_headers=expose_headers,
            ),
        )

    def use_authentication(
        self, strategy: Optional[AuthenticationStrategy] = None
    ) -> AuthenticationStrategy:
        if self.started:
            raise RuntimeError(
                "The application is already running, configure authentication "
                "before starting the application"
            )

        if self._authentication_strategy:
            return self._authentication_strategy

        if not strategy:
            strategy = AuthenticationStrategy(container=self.services)

        self._authentication_strategy = strategy
        return strategy

    def use_authorization(
        self, strategy: Optional[AuthorizationStrategy] = None
    ) -> AuthorizationStrategy:
        if self.started:
            raise RuntimeError(
                "The application is already running, configure authorization "
                "before starting the application"
            )

        if self._authorization_strategy:
            return self._authorization_strategy

        if not strategy:
            strategy = AuthorizationStrategy(container=self.services)

        if strategy.default_policy is None:
            # by default, a default policy is configured with no requirements,
            # meaning that request handlers allow anonymous users by default, unless
            # they are decorated with @auth()
            strategy.default_policy = Policy("default")
            strategy.add(Policy("authenticated").add(AuthenticatedRequirement()))

        self._authorization_strategy = strategy
        self.exceptions_handlers.update(
            {  # type: ignore
                AuthenticateChallenge: handle_authentication_challenge,
                UnauthorizedError: handle_unauthorized,
                ForbiddenError: handle_forbidden,
            }
        )
        return strategy

    def exception_handler(
        self, exception_type: Union[int, Type[Exception]]
    ) -> Callable[..., Any]:
        """
        Registers an exception handler function in the application exception handler.
        """

        def decorator(f):
            self.exceptions_handlers[exception_type] = f
            return f

        return decorator

    def lifespan(self, callback):
        """
        Registers an async generator, or async context manager, to be entered at
        application start, and exited at application shutdown. This is syntactic sugar
        alternative to handling application start and stop events directly. It can be
        useful to handle objects that need to be initialized and disposed, like HTTP
        clients that use connection pools, or files that needs to be open following the
        lifespan of the application.
        """
        if not hasattr(callback, "__aenter__"):
            callback = asynccontextmanager(callback)

        obj = None

        @self.on_start
        async def register_aenter(_):
            nonlocal obj
            try:
                obj = callback(self)
            except TypeError:
                obj = callback()
            await obj.__aenter__()

        @self.on_stop
        async def register_aexit(_):
            nonlocal obj
            if obj is not None:
                await obj.__aexit__(None, None, None)

        return callback

    def serve_files(
        self,
        source_folder: Union[str, Path],
        *,
        discovery: bool = False,
        cache_time: int = 10800,
        extensions: Optional[Set[str]] = None,
        root_path: str = "",
        index_document: Optional[str] = "index.html",
        fallback_document: Optional[str] = None,
        allow_anonymous: bool = True,
        default_file_options: Optional[DefaultFileOptions] = None,
    ):
        """
        Configures dynamic file serving from a given folder, relative to the server cwd.

        Parameters:
            source_folder (str): Path to the source folder containing static files.
            extensions: The set of files extensions to serve.
            discovery: Whether to enable file discovery, serving HTML pages for folders.
            cache_time: Controls the Cache-Control Max-Age in seconds for static files.
            root_path: Path prefix used for routing requests.
            For example, if set to "public", files are served at "/public/*".
            If the Application router uses a prefix, it is applied automatically.
            allow_anonymous: Whether to enable anonymous access to static files, true by
            default.
            index_document: The name of the index document to display, if present,
            in folders. Requests for folders that contain a file with matching produce
            a response with this document.
            fallback_document: Optional file name, for a document to serve when a
            response would be otherwise 404 Not Found; e.g. use this to serve SPA that
            use HTML5 History API for client side routing.
            default_file_options: Optional options to serve the default file
            (index.html)
        """
        serve_files_dynamic(
            self.router,
            self.files_handler,
            source_folder,
            discovery=discovery,
            cache_time=cache_time,
            extensions=extensions,
            root_path=root_path,
            index_document=index_document,
            fallback_document=fallback_document,
            anonymous_access=allow_anonymous,
            default_file_options=default_file_options,
        )

    def _apply_middlewares_in_routes(self):
        for route in self.router:
            route.handler = get_middlewares_chain(self.middlewares, route.handler)

    def _normalize_middlewares(self):
        self.middlewares = [
            normalize_middleware(middleware, self.services)
            for middleware in self.middlewares
        ]

    def use_controllers(self):
        """
        Configures controllers in the application. This method is called automatically
        when the application starts.
        """
        controllers_manager = ControllersManager()
        self.register_controllers(controllers_manager.prepare_controllers(self.router))

    def register_controllers(self, controller_types: List[Type]):
        """
        Registers controller types as transient services in the application service
        container.
        """
        if not controller_types:
            return

        for controller_class in controller_types:
            if controller_class in self.services:
                continue

            self.services.register(controller_class)

    def normalize_handlers(self):
        configured_handlers = set()

        self.router.sort_routes()

        for method, route in self.router.iter_with_methods():
            if route.handler in configured_handlers:
                continue

            route.handler = normalize_handler(route, self.services, method)
            configured_handlers.add(route.handler)

        self._normalize_fallback_route()
        configured_handlers.clear()

    def _normalize_fallback_route(self):
        fallback = self.router.fallback

        if fallback is not None and self._has_default_not_found_handler():

            async def fallback_handler(app, request, exc) -> Response:
                return await fallback.handler(request)  # type: ignore

            self.exceptions_handlers[NotFound] = fallback_handler  # type: ignore

    def _has_default_not_found_handler(self):
        return self.get_http_exception_handler(NotFound()) is handle_not_found

    def configure_middlewares(self):
        if self._middlewares_configured:
            return
        self._middlewares_configured = True

        if self._authorization_strategy:
            if not self._authentication_strategy:
                raise AuthorizationWithoutAuthenticationError()
            self.middlewares.insert(
                0, get_authorization_middleware(self._authorization_strategy)
            )

        if self._authentication_strategy:
            self.middlewares.insert(
                0, get_authentication_middleware(self._authentication_strategy)
            )

        if self._session_middleware:
            self.middlewares.insert(0, self._session_middleware)

        if self._cors_strategy:
            self.middlewares.insert(0, get_cors_middleware(self, self._cors_strategy))

        if self._default_headers:
            self.middlewares.insert(
                0, get_default_headers_middleware(self._default_headers)
            )

        self.on_middlewares_configuration.fire_sync()

        self._normalize_middlewares()

        if self.middlewares:
            self._apply_middlewares_in_routes()

    def extend(self, mixin) -> None:
        """
        Extends the class with additional features, applying the given mixin class.

        This method should be used for those scenarios where opting-in for a feature
        incurs a performance fee, so that said fee is paid only when necessary.
        """
        extend(self, mixin)

    async def start(self):
        if self.started:
            return

        self.started = True
        self.router.apply_routes()

        if self.on_start:
            await self.on_start.fire()

        validate_default_router()
        self._check_prefix()
        self.use_controllers()
        self.normalize_handlers()
        self.configure_middlewares()

        if self.after_start:
            await self.after_start.fire()

    async def stop(self):
        await self.on_stop.fire()
        self.started = False

    async def _handle_lifespan(self, receive, send) -> None:
        message = await receive()
        assert message["type"] == "lifespan.startup"

        try:
            await self.start()
        except:  # NOQA
            logging.exception("Startup error")
            await send({"type": "lifespan.startup.failed"})
            return

        await send({"type": "lifespan.startup.complete"})

        message = await receive()
        assert message["type"] == "lifespan.shutdown"
        await self.stop()
        await send({"type": "lifespan.shutdown.complete"})

    async def _handle_websocket(self, scope, receive, send) -> None:
        ws = WebSocket(scope, receive, send)
        # TODO: support filters
        route = self.router.get_match_by_method_and_path(
            RouteMethod.GET_WS, scope["path"]
        )

        if route is None:
            await ws.close()
            return

        ws.route_values = route.values

        try:
            # The ASGI protocol does not allow to return any response, not even for the
            # handshake HTTP request
            await route.handler(ws)
        except Exception as exc:
            logging.exception("Exception while handling WebSocket")
            # If WebSocket connection accepted, close
            # the connection using WebSocket Internal error code.
            try:
                if ws.accepted:
                    await ws.close(1011, reason=format_reason(str(exc)))
                else:
                    # Otherwise, just close the connection, the ASGI server
                    # will anyway respond 403 to the client.
                    await ws.close()
            except RuntimeError:
                logging.exception(
                    "RuntimeError while closing WebSocket. "
                    "This can happen when the socket is already closed."
                )

    def instantiate_request(self, scope, receive) -> Request:
        request = Request.incoming(
            scope["method"],
            scope["raw_path"],
            scope["query_string"],
            list(scope["headers"]),
        )

        request.scope = scope
        request.content = ASGIContent(receive)
        return request

    def _check_prefix(self):
        """
        If the application router uses a prefix, modify the class to apply the prefix
        automatically to each instantiated request.base_path. This is used by the
        get_absolute_url_to_path to produce appropriate URLs for redirections to the
        application (e.g. in OIDC integrations).
        """
        if self.router.prefix and not isinstance(self, PathPrefixMixin):
            self.extend(PathPrefixMixin)

    async def _handle_http(self, scope, receive, send) -> None:
        assert scope["type"] == "http"

        request = self.instantiate_request(scope, receive)
        response = await self.handle(request)
        await send_asgi_response(response, send)

        request.scope = None  # type: ignore
        request.content.dispose()  # type: ignore

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            return await self._handle_http(scope, receive, send)

        if scope["type"] == "websocket":
            return await self._handle_websocket(scope, receive, send)

        if scope["type"] == "lifespan":
            return await self._handle_lifespan(receive, send)

        raise TypeError(f"Unsupported scope type: {scope['type']}")


class PathPrefixMixin:
    router: Router

    def instantiate_request(self, scope, receive) -> Request:
        request = super().instantiate_request(scope, receive)  # type: ignore
        request.base_path = self.router.prefix
        return request


class MountMixin:
    _mount: MountRegistry
    base_path: str

    def handle_mount_path(self, scope, route_match):
        assert route_match.values is not None
        tail = route_match.values.get("tail")
        assert tail is not None
        tail = "/" + tail

        scope["path"] = tail
        scope["raw_path"] = tail.encode("utf8")

    async def _handle_redirect_to_mount_root(self, scope, send):
        """
        A request to the path "https://.../{mount_path}" must result in a
        307 Temporary Redirect to the root of the mount: "https://.../{mount_path}/"
        including a trailing slash.
        """
        response = Response(
            307,
            [
                (
                    b"Location",
                    _ensure_bytes(
                        get_request_url_from_scope(
                            scope, trailing_slash=True, base_path=self.base_path
                        )
                    ),
                )
            ],
        )
        await send_asgi_response(response, send)

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            return await super()._handle_lifespan(receive, send)  # type: ignore

        for route in self.mount_registry.mounted_apps:  # type: ignore
            route_match = route.match_by_path(scope["raw_path"])
            if route_match:
                raw_path = scope["raw_path"]
                if raw_path == route.pattern.rstrip(b"/*") and scope["type"] == "http":
                    return await self._handle_redirect_to_mount_root(scope, send)
                self.handle_mount_path(scope, route_match)
                return await route.handler(scope, receive, send)

        return await super().__call__(scope, receive, send)  # type: ignore


def _auto_import(parent_file: str, folder_name):
    parent_folder = Path(parent_file).parent
    controllers_path = parent_folder / folder_name
    if controllers_path.exists():
        import_child_modules(controllers_path)


def _auto_import_controllers(parent_file: str):
    _auto_import(parent_file, "controllers")


def _auto_import_routes(parent_file: str):
    _auto_import(parent_file, "routes")
