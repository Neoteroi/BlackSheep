import logging
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

from guardpost.asynchronous.authentication import AuthenticationStrategy
from guardpost.asynchronous.authorization import AuthorizationStrategy
from guardpost.authorization import Policy, UnauthorizedError
from guardpost.common import AuthenticatedRequirement
from rodi import Container, Services

from blacksheep.baseapp import BaseApplication, handle_not_found
from blacksheep.common.files.asyncfs import FilesHandler
from blacksheep.contents import ASGIContent
from blacksheep.exceptions import HTTPException
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
    handle_unauthorized,
)
from blacksheep.server.bindings import ControllerParameter
from blacksheep.server.controllers import router as controllers_router
from blacksheep.server.cors import CORSPolicy, CORSStrategy, get_cors_middleware
from blacksheep.server.env import EnvironmentSettings
from blacksheep.server.errors import ServerErrorDetailsHandler
from blacksheep.server.files import ServeFilesOptions
from blacksheep.server.files.dynamic import serve_files_dynamic
from blacksheep.server.normalization import normalize_handler, normalize_middleware
from blacksheep.server.responses import _ensure_bytes
from blacksheep.server.routing import (
    MountRegistry,
    RegisteredRoute,
    Router,
    RoutesRegistry,
)
from blacksheep.server.websocket import WebSocket
from blacksheep.sessions import Encryptor, SessionMiddleware, SessionSerializer, Signer
from blacksheep.utils import ensure_bytes, join_fragments

__all__ = ("Application",)


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
        self._handlers.append(handler)
        return self

    def __isub__(self, handler: Callable[..., Any]) -> "ApplicationEvent":
        self._handlers.remove(handler)
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

    async def fire(self, *args: Any, **keywargs: Any) -> None:
        for handler in self._handlers:
            await handler(self.context, *args, **keywargs)


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
    ...


class RequiresServiceContainerError(ApplicationStartupError):
    def __init__(self, details: str):
        super().__init__(
            f"The application requires services to be a Container "
            f"at this point of execution. Details: {details}"
        )
        self.details = details


class ApplicationAlreadyStartedCORSError(TypeError):
    def __init__(self) -> None:
        super().__init__(
            "The application is already running, configure CORS rules "
            "before starting the application"
        )


def _extend(obj, cls):
    """Applies a mixin to an instance of a class."""
    base_cls = obj.__class__
    base_cls_name = obj.__class__.__name__
    obj.__class__ = type(base_cls_name, (cls, base_cls), {})


class Application(BaseApplication):
    """
    Server application class.
    """

    def __init__(
        self,
        *,
        router: Optional[Router] = None,
        services: Optional[Container] = None,
        debug: bool = False,
        show_error_details: Optional[bool] = None,
        mount: Optional[MountRegistry] = None,
    ):
        env_settings = EnvironmentSettings()
        if router is None:
            router = Router()
        if services is None:
            services = Container()
        if show_error_details is None:
            show_error_details = env_settings.show_error_details
        if mount is None:
            mount = MountRegistry(env_settings.mount_auto_events)
        super().__init__(show_error_details, router)

        self.services: Container = services
        self._service_provider: Optional[Services] = None
        self.debug = debug
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
        self.controllers_router: RoutesRegistry = controllers_router
        self.files_handler = FilesHandler()
        self.server_error_details_handler = ServerErrorDetailsHandler()
        self._session_middleware: Optional[SessionMiddleware] = None
        self.base_path: str = ""
        self._mount_registry = mount

    @property
    def service_provider(self) -> Services:
        """
        Returns the object that provides services of this application.
        """
        if self._service_provider is None:
            raise TypeError("The service provider is not build for this application.")
        return self._service_provider

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

            APP_MOUNT_AUTO_EVENTS is set to "1" or "true" (case insensitive)

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
        secret_key: str,
        *,
        session_cookie: str = "session",
        serializer: Optional[SessionSerializer] = None,
        signer: Optional[Signer] = None,
        encryptor: Optional[Encryptor] = None,
        session_max_age: Optional[int] = None,
    ) -> None:
        self._session_middleware = SessionMiddleware(
            secret_key=secret_key,
            session_cookie=session_cookie,
            serializer=serializer,
            signer=signer,
            encryptor=encryptor,
            session_max_age=session_max_age,
        )

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
            strategy = AuthenticationStrategy()

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
            strategy = AuthorizationStrategy()

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
            }
        )
        return strategy

    def route(
        self, pattern: str, methods: Optional[Sequence[str]] = None
    ) -> Callable[..., Any]:
        if methods is None:
            methods = ["GET"]

        def decorator(f):
            for method in methods:
                self.router.add(method, pattern, f)
            return f

        return decorator

    def exception_handler(
        self, exception: Union[int, Type[Exception]]
    ) -> Callable[..., Any]:
        """
        Registers an exception handler function in the application exception handler.
        """

        def decorator(f):
            self.exceptions_handlers[exception] = f
            return f

        return decorator

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
            allow_anonymous: Whether to enable anonymous access to static files, true by
            default.
            index_document: The name of the index document to display, if present,
            in folders. Requests for folders that contain a file with matching produce
            a response with this document.
            fallback_document: Optional file name, for a document to serve when a
            response would be otherwise 404 Not Found; e.g. use this to serve SPA that
            use HTML5 History API for client side routing.
        """
        if isinstance(source_folder, ServeFilesOptions):
            # deprecated class, will be removed in the next version
            from typing import cast

            deprecated_arg = cast(ServeFilesOptions, source_folder)
            deprecated_arg.validate()
            serve_files_dynamic(
                self.router,
                self.files_handler,
                str(deprecated_arg.source_folder),
                discovery=deprecated_arg.discovery,
                cache_time=deprecated_arg.cache_time,
                extensions=deprecated_arg.extensions,
                root_path=deprecated_arg.root_path,
                index_document=deprecated_arg.index_document,
                fallback_document=deprecated_arg.fallback_document,
                anonymous_access=deprecated_arg.allow_anonymous,
            )
            return
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
        )

    def _apply_middlewares_in_routes(self):
        for route in self.router:
            route.handler = get_middlewares_chain(self.middlewares, route.handler)

    def _normalize_middlewares(self):
        self.middlewares = [
            normalize_middleware(middleware, self.service_provider)
            for middleware in self.middlewares
        ]

    def use_controllers(self):
        # NB: controller types are collected here, and not with
        # Controller.__subclasses__(),
        # to avoid funny bugs in case several Application objects are defined
        # with different controllers; this is the case for example of tests.

        # This sophisticated approach, using metaclassing, dynamic
        # attributes, and calling handlers dynamically
        # with activated instances of controllers; still supports custom
        # and generic decorators (*args, **kwargs);
        # as long as `functools.wraps` decorator is used in those decorators.
        self.register_controllers(self.prepare_controllers())

    def get_controller_handler_pattern(
        self, controller_type: Type, route: RegisteredRoute
    ) -> bytes:
        """
        Returns the full pattern to be used for a route handler,
        defined as controller method.
        """
        base_route = getattr(controller_type, "route", None)

        if base_route is not None:
            if callable(base_route):
                value = base_route()
            elif isinstance(base_route, (str, bytes)):
                value = base_route
            else:
                raise RuntimeError(
                    f"Invalid controller `route` attribute. "
                    f"Controller `{controller_type.__name__}` "
                    f"has an invalid route attribute: it should "
                    f"be callable, or str, or bytes."
                )

            if value:
                return ensure_bytes(join_fragments(value, route.pattern))
        return ensure_bytes(route.pattern)

    def prepare_controllers(self) -> List[Type]:
        controller_types = []
        for route in self.controllers_router:
            handler = route.handler
            controller_type = getattr(handler, "controller_type")
            controller_types.append(controller_type)
            handler.__annotations__["self"] = ControllerParameter[controller_type]
            self.router.add(
                route.method,
                self.get_controller_handler_pattern(controller_type, route),
                handler,
            )
        return controller_types

    def bind_controller_type(self, controller_type: Type):
        templates_environment = getattr(self, "templates_environment", None)

        if templates_environment:
            setattr(controller_type, "templates", templates_environment)

    def register_controllers(self, controller_types: List[Type]):
        """
        Registers controller types as transient services
        in the application service container.
        """
        if not controller_types:
            return

        if not isinstance(self.services, Container):
            raise RequiresServiceContainerError(
                "When using controllers, the application.services must be "
                "a service `Container` (`rodi.Container`; not a built service "
                "provider)."
            )

        for controller_class in controller_types:
            if controller_class in self.services:
                continue

            self.bind_controller_type(controller_class)

            if getattr(controller_class, "__init__") is object.__init__:
                self.services.add_transient_by_factory(
                    controller_class, controller_class
                )
            else:
                self.services.add_exact_transient(controller_class)

    def normalize_handlers(self):
        configured_handlers = set()

        self.router.sort_routes()

        for route in self.router:
            if route.handler in configured_handlers:
                continue

            route.handler = normalize_handler(route, self.service_provider)
            configured_handlers.add(route.handler)

        self._normalize_fallback_route()
        configured_handlers.clear()

    def _normalize_fallback_route(self):
        fallback = self.router.fallback

        if fallback is not None and self._has_default_not_found_handler():

            async def fallback_handler(app, request, exc) -> Response:
                return await fallback.handler(request)  # type: ignore

            self.exceptions_handlers[404] = fallback_handler  # type: ignore

    def _has_default_not_found_handler(self):
        return self.exceptions_handlers.get(404) is handle_not_found

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

    def build_services(self):
        self._service_provider = self.services.build_provider()

    def extend(self, mixin) -> None:
        """
        Extends the class with additional features, applying the given mixin class.
        """
        _extend(self, mixin)

    async def start(self):
        if self.started:
            return

        self.started = True
        if self.on_start:
            await self.on_start.fire()

        self.use_controllers()
        self.build_services()
        self.normalize_handlers()
        self.configure_middlewares()

        if self.after_start:
            await self.after_start.fire()

    async def stop(self):
        await self.on_stop.fire()
        self.started = False

    async def _handle_lifespan(self, receive, send):
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

    async def _handle_websocket(self, scope, receive, send):
        ws = WebSocket(scope, receive, send)
        route = self.router.get_ws_match(scope["path"])

        if route:
            ws.route_values = route.values
            try:
                return await route.handler(ws)
            except UnauthorizedError:
                await ws.close(401, "Unauthorized")
            except HTTPException as http_exception:
                await ws.close(http_exception.status, str(http_exception))
        await ws.close()

    async def _handle_http(self, scope, receive, send):
        assert scope["type"] == "http"

        request = Request.incoming(
            scope["method"],
            scope["raw_path"],
            scope["query_string"],
            list(scope["headers"]),
        )

        request.scope = scope
        request.content = ASGIContent(receive)

        response = await self.handle(request)
        await send_asgi_response(response, send)

        request.scope = None  # type: ignore
        request.content.dispose()

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            return await self._handle_http(scope, receive, send)

        if scope["type"] == "websocket":
            return await self._handle_websocket(scope, receive, send)

        if scope["type"] == "lifespan":
            return await self._handle_lifespan(receive, send)

        raise TypeError(f"Unsupported scope type: {scope['type']}")


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
            route_match = route.match(scope["raw_path"])
            if route_match:
                raw_path = scope["raw_path"]
                if raw_path == route.pattern.rstrip(b"/*") and scope["type"] == "http":
                    return await self._handle_redirect_to_mount_root(scope, send)
                self.handle_mount_path(scope, route_match)
                return await route.handler(scope, receive, send)

        return await super().__call__(scope, receive, send)  # type: ignore
