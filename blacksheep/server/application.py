import os
import logging
import inspect
from typing import Optional, List, Callable, Union, Type
from blacksheep.utils import join_fragments, ensure_bytes
from blacksheep.server.routing import Router, RoutesRegistry, RegisteredRoute
from blacksheep.server.logs import setup_sync_logging
from blacksheep.server.files.dynamic import serve_files
from blacksheep.server.resources import get_resource_file_content
from blacksheep.server.normalization import normalize_handler, normalize_middleware
from blacksheep.server.controllers import router as controllers_router
from blacksheep.baseapp import BaseApplication
from blacksheep.messages import Request, Response
from blacksheep.contents import ASGIContent
from blacksheep.scribe import send_asgi_response
from blacksheep.middlewares import get_middlewares_chain
from blacksheep.server.bindings import ControllerBinder
from blacksheep.server.authentication import (get_authentication_middleware,
                                              AuthenticateChallenge,
                                              handle_authentication_challenge)
from blacksheep.server.authorization import (get_authorization_middleware,
                                             AuthorizationWithoutAuthenticationError,
                                             handle_unauthorized)
from guardpost.authorization import UnauthorizedError, Policy
from guardpost.asynchronous.authentication import AuthenticationStrategy
from guardpost.asynchronous.authorization import AuthorizationStrategy
from rodi import Services, Container

ServicesType = Union[Services, Container]

server_logger = logging.getLogger('blacksheep.server')

__all__ = ('Application',)


def get_default_headers_middleware(headers):
    async def default_headers_middleware(request, handler):
        response = await handler(request)
        for header in headers:
            response.headers.add(header)
        return response

    return default_headers_middleware


class Resources:

    def __init__(self, error_page_html):
        self.error_page_html = error_page_html


class ApplicationEvent:

    def __init__(self, context):
        self.__handlers = []
        self.context = context

    def __iadd__(self, handler):
        self.__handlers.append(handler)
        return self

    def __isub__(self, handler):
        self.__handlers.remove(handler)
        return self

    def __len__(self):
        return len(self.__handlers)

    def append(self, handler):
        self.__handlers.append(handler)

    async def fire(self, *args, **keywargs):
        for handler in self.__handlers:
            await handler(self.context, *args, **keywargs)

    def __repr__(self):
        return f'<ApplicationEvent [{",".join(handler.__name__ for handler in self.__handlers)}]>'


def get_show_error_details(show_error_details):
    if show_error_details:
        return True

    show_error_details = os.environ.get('BLACKSHEEP_SHOW_ERROR_DETAILS')

    if show_error_details and show_error_details not in ('0', 'false'):
        return True
    return False


class ApplicationStartupError(RuntimeError):
    ...


class RequiresServiceContainerError(ApplicationStartupError):

    def __init__(self, details: str):
        super().__init__(f'The application requires services to be a Container at this point of execution. '
                         f'Details: {details}')
        self.details = details


class Application(BaseApplication):

    def __init__(self,
                 router: Optional[Router] = None,
                 middlewares: Optional[List[Callable]] = None,
                 resources: Optional[Resources] = None,
                 services: Optional[ServicesType] = None,
                 debug: bool = False,
                 show_error_details: bool = False):
        if router is None:
            router = Router()
        if services is None:
            services = Container()
        super().__init__(get_show_error_details(debug or show_error_details), router)

        if middlewares is None:
            middlewares = []
        if resources is None:
            resources = Resources(get_resource_file_content('error.html'))
        self.services = services  # type: ServicesType
        self.debug = debug
        self.middlewares = middlewares
        self.access_logger = None
        self.logger = None
        self._default_headers = None
        self._use_sync_logging = False
        self._middlewares_configured = False
        self.resources = resources
        self._serve_files = None
        self._authentication_strategy = None  # type: Optional[AuthenticationStrategy]
        self._authorization_strategy = None  # type: Optional[AuthorizationStrategy]
        self.on_start = ApplicationEvent(self)
        self.on_stop = ApplicationEvent(self)
        self.started = False
        self.controllers_router: RoutesRegistry = controllers_router

    def __repr__(self):
        return f'<BlackSheep Application>'

    @property
    def default_headers(self):
        return self._default_headers

    @default_headers.setter
    def default_headers(self, value):
        self._default_headers = value

    def use_authentication(self, strategy: Optional[AuthenticationStrategy] = None) -> AuthenticationStrategy:
        if self.started:
            raise RuntimeError('The application is already running, configure authentication '
                               'before starting the application')
        if not strategy:
            strategy = AuthenticationStrategy()

        self._authentication_strategy = strategy
        return strategy

    def use_authorization(self, strategy: Optional[AuthorizationStrategy] = None) -> AuthorizationStrategy:
        if self.started:
            raise RuntimeError('The application is already running, configure authorization '
                               'before starting the application')

        if not strategy:
            strategy = AuthorizationStrategy()

        if strategy.default_policy is None:
            # by default, a default policy is configured with no requirements,
            # meaning that request handlers allow anonymous users, unless specified otherwise
            # this can be modified, by adding a requirement to the default policy
            strategy.default_policy = Policy('default')

        self._authorization_strategy = strategy
        self.exceptions_handlers[AuthenticateChallenge] = handle_authentication_challenge
        self.exceptions_handlers[UnauthorizedError] = handle_unauthorized
        return strategy

    def route(self, pattern, methods=None):
        if methods is None:
            methods = ['GET']

        def decorator(f):
            for method in methods:
                self.router.add(method, pattern, f)
            return f

        return decorator

    def set_default_headers(self, headers):
        self._default_headers = headers

    def use_sync_logging(self):
        self._use_sync_logging = True

    def serve_files(self, folder_name: str, extensions=None, discovery=False, cache_max_age=10800):
        self._serve_files = folder_name, extensions, discovery, cache_max_age

    def _configure_sync_logging(self):
        logging_middleware, access_logger, app_logger = setup_sync_logging()
        self.logger = app_logger
        self.access_logger = access_logger,
        self.middlewares.insert(0, logging_middleware)

    def _apply_middlewares_in_routes(self):
        configured_handlers = set()

        for route in self.router:
            if route.handler in configured_handlers:
                continue

            route.handler = get_middlewares_chain(self.middlewares, route.handler)

            configured_handlers.add(route.handler)
        configured_handlers.clear()

    def _normalize_middlewares(self):
        self.middlewares = [normalize_middleware(middleware, self.services) for middleware in self.middlewares]

    def use_controllers(self):
        # NB: controller types are collected here, and not with Controller.__subclasses__(),
        # to avoid funny bugs in case several Application objects are defined with different controllers;
        # this is the case for example of tests.

        # NB: this sophisticated approach, using metaclassing, dynamic attributes, and calling handlers dynamically
        # with activated instances of controllers; still supports custom and generic decorators (*args, **kwargs);
        # as long as `functools.wraps` decorator is used in those decorators.
        self.register_controllers(self.prepare_controllers())

    def get_controller_handler_pattern(self, controller_type: Type, route: RegisteredRoute) -> bytes:
        """Returns the full pattern to be used for a route handler, defined as controller method."""
        base_route = getattr(controller_type, 'route', None)

        if base_route:
            if callable(base_route):
                value = base_route()
            elif isinstance(base_route, (str, bytes)):
                value = base_route
            else:
                raise RuntimeError(f'Invalid controller `route` attribute. Controller `{controller_type.__name__}` '
                                   f'has an invalid route attribute: it should be callable, or str, or bytes.')

            if value:
                return ensure_bytes(join_fragments(value, route.pattern))
        return route.pattern

    def prepare_controllers(self) -> List[Type]:
        controller_types = []
        for route in self.controllers_router:
            handler = route.handler
            controller_type = getattr(handler, 'controller_type')
            controller_types.append(controller_type)
            handler.__annotations__['self'] = ControllerBinder(controller_type)
            self.router.add(route.method, self.get_controller_handler_pattern(controller_type, route), handler)
        return controller_types

    def bind_controller_type(self, controller_type: Type):
        templates_environment = getattr(self, 'templates_environment', None)

        if templates_environment:
            setattr(controller_type, 'templates', templates_environment)

    def register_controllers(self, controller_types: List[Type]):
        """Registers controller types as transient services in the application service container."""
        if not controller_types:
            return

        if not isinstance(self.services, Container):
            raise RequiresServiceContainerError('When using controllers, the application.services must be '
                                                'a service `Container` (`rodi.Container`; not a built service '
                                                'provider).')

        for controller_class in controller_types:
            is_abstract = inspect.isabstract(controller_class)
            if is_abstract:
                continue

            if controller_class in self.services:
                continue

            self.bind_controller_type(controller_class)

            # TODO: maybe rodi should be modified to handle the following internally;
            # if a type does not define an __init__ method, then a fair assumption is that it can be instantiated
            # by calling it;
            # TODO: the following if statement can be removed if rodi is modified as described above.
            if getattr(controller_class, '__init__') is object.__init__:
                self.services.add_transient_by_factory(controller_class, controller_class)
            else:
                self.services.add_exact_transient(controller_class)

    def normalize_handlers(self):
        configured_handlers = set()

        for route in self.router:
            if route.handler in configured_handlers:
                continue

            route.handler = normalize_handler(route, self.services)

            configured_handlers.add(route.handler)
        configured_handlers.clear()

    def configure_middlewares(self):
        if self._middlewares_configured:
            return
        self._middlewares_configured = True

        if self._authorization_strategy:
            if not self._authentication_strategy:
                raise AuthorizationWithoutAuthenticationError()
            self.middlewares.insert(0, get_authorization_middleware(self._authorization_strategy))

        if self._authentication_strategy:
            self.middlewares.insert(0, get_authentication_middleware(self._authentication_strategy))

        if self._use_sync_logging:
            self._configure_sync_logging()

        if self._default_headers:
            self.middlewares.insert(0, get_default_headers_middleware(self._default_headers))

        self._normalize_middlewares()

        if self.middlewares:
            self._apply_middlewares_in_routes()

    def apply_routes(self):
        if self._serve_files:
            serve_files(self.router, *self._serve_files)

    def build_services(self):
        if isinstance(self.services, Container):
            self.services = self.services.build_provider()

    async def start(self):
        if self.started:
            return

        self.started = True
        if self.on_start:
            await self.on_start.fire()

        self.use_controllers()
        self.build_services()
        self.apply_routes()
        self.normalize_handlers()
        self.configure_middlewares()

    async def stop(self):
        await self.on_stop.fire()

    async def _handle_lifespan(self, receive, send):
        message = await receive()
        assert message['type'] == 'lifespan.startup'

        try:
            await self.start()
        except:
            logging.exception('Startup error')
            await send({'type': 'lifespan.startup.failed'})
            return

        await send({'type': 'lifespan.startup.complete'})

        message = await receive()
        assert message['type'] == 'lifespan.shutdown'
        await self.stop()
        await send({'type': 'lifespan.shutdown.complete'})

    async def after_response(self, request: Request, response: Response):
        """After response callback"""

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'lifespan':
            return await self._handle_lifespan(receive, send)

        # assert scope['type'] == 'http'

        request = Request.incoming(
            scope['method'],
            scope['raw_path'],
            scope['query_string'],
            scope['headers']
        )
        request.scope = scope
        request.content = ASGIContent(receive)

        response = await self.handle(request)
        await send_asgi_response(response, send)

        await self.after_response(request, response)

        request.scope = None
        request.content.dispose()
