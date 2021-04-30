import logging
import os
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

from blacksheep.baseapp import BaseApplication
from blacksheep.common.files.asyncfs import FilesHandler
from blacksheep.contents import ASGIContent
from blacksheep.messages import Request, Response
from blacksheep.middlewares import get_middlewares_chain
from blacksheep.scribe import send_asgi_response
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
from blacksheep.server.errors import ServerErrorDetailsHandler
from blacksheep.server.files import ServeFilesOptions
from blacksheep.server.files.dynamic import serve_files_dynamic
from blacksheep.server.normalization import normalize_handler, normalize_middleware
from blacksheep.server.routing import RegisteredRoute, Router, RoutesRegistry
from blacksheep.sessions import (
    Encryptor,
    SessionSerializer,
    Signer,
    SessionMiddleware,
)
from blacksheep.utils import ensure_bytes, join_fragments
from guardpost.asynchronous.authentication import AuthenticationStrategy
from guardpost.asynchronous.authorization import AuthorizationStrategy
from guardpost.authorization import Policy, UnauthorizedError
from guardpost.common import AuthenticatedRequirement
from rodi import Container, Services

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
        self.__handlers: List[Callable[..., Any]] = []
        self.context = context

    def __iadd__(self, handler: Callable[..., Any]) -> "ApplicationEvent":
        self.__handlers.append(handler)
        return self

    def __isub__(self, handler: Callable[..., Any]) -> "ApplicationEvent":
        self.__handlers.remove(handler)
        return self

    def __len__(self) -> int:
        return len(self.__handlers)

    async def fire(self, *args: Any, **keywargs: Any) -> None:
        for handler in self.__handlers:
            await handler(self.context, *args, **keywargs)


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


class Application(BaseApplication):
    def __init__(
        self,
        *,
        router: Optional[Router] = None,
        services: Optional[Container] = None,
        debug: bool = False,
        show_error_details: Optional[bool] = None,
    ):
        if router is None:
            router = Router()
        if services is None:
            services = Container()
        if show_error_details is None:
            show_error_details = bool(os.environ.get("APP_SHOW_ERROR_DETAILS", False))
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
        self.started = False
        self.controllers_router: RoutesRegistry = controllers_router
        self.files_handler = FilesHandler()
        self.server_error_details_handler = ServerErrorDetailsHandler()
        self._session_middleware: Optional[SessionMiddleware] = None

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
        async def options_handler(request):
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

        if not strategy:
            strategy = AuthorizationStrategy()

        if strategy.default_policy is None:
            # by default, a default policy is configured with no requirements,
            # meaning that request handlers allow anonymous users by default, unless
            # they are decorated with @auth()
            strategy.default_policy = Policy("default")
            strategy.add(Policy("authenticated").add(AuthenticatedRequirement()))

        self._authorization_strategy = strategy
        self.exceptions_handlers[
            AuthenticateChallenge
        ] = handle_authentication_challenge
        self.exceptions_handlers[UnauthorizedError] = handle_unauthorized
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
        source_folder: str,
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
        configured_handlers.clear()

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

        self._normalize_middlewares()

        if self.middlewares:
            self._apply_middlewares_in_routes()

    def build_services(self):
        self._service_provider = self.services.build_provider()

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

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            return await self._handle_lifespan(receive, send)

        assert scope["type"] == "http"

        request = Request.incoming(
            scope["method"], scope["raw_path"], scope["query_string"], scope["headers"]
        )
        request.scope = scope
        request.content = ASGIContent(receive)

        response = await self.handle(request)
        await send_asgi_response(response, send)

        request.scope = None  # type: ignore
        request.content.dispose()
