import os
import logging
from typing import Optional, List, Callable
from blacksheep.server.routing import Router
from blacksheep.server.logs import setup_sync_logging
from blacksheep.server.files.dynamic import serve_files
from blacksheep.server.resources import get_resource_file_content
from blacksheep.server.normalization import normalize_handler, normalize_middleware
from blacksheep.baseapp import BaseApplication
from blacksheep.messages import Request, Response
from blacksheep.contents import ASGIContent
from blacksheep.scribe import send_asgi_response
from blacksheep.middlewares import get_middlewares_chain
from blacksheep.server.authentication import (get_authentication_middleware,
                                              AuthenticateChallenge,
                                              handle_authentication_challenge)
from blacksheep.server.authorization import (get_authorization_middleware,
                                             AuthorizationWithoutAuthenticationError,
                                             handle_unauthorized)
from guardpost.authorization import UnauthorizedError, Policy
from guardpost.asynchronous.authentication import AuthenticationStrategy
from guardpost.asynchronous.authorization import AuthorizationStrategy
from rodi import Services


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


def get_show_error_details(show_error_details):
    if show_error_details:
        return True

    show_error_details = os.environ.get('BLACKSHEEP_SHOW_ERROR_DETAILS')

    if show_error_details and show_error_details not in ('0', 'false'):
        return True
    return False


class Application(BaseApplication):

    def __init__(self,
                 router: Optional[Router] = None,
                 middlewares: Optional[List[Callable]] = None,
                 resources: Optional[Resources] = None,
                 services: Optional[Services] = None,
                 debug: bool = False,
                 show_error_details: bool = False,
                 auto_reload: bool = True):
        if router is None:
            router = Router()
        if services is None:
            services = Services()
        super().__init__(get_show_error_details(debug or show_error_details), router, services)

        if middlewares is None:
            middlewares = []
        if resources is None:
            resources = Resources(get_resource_file_content('error.html'))
        self.debug = debug
        self.auto_reload = auto_reload
        self.running = False
        self.middlewares = middlewares
        self.processes = []
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

    def use_authentication(self, strategy: Optional[AuthenticationStrategy] = None) -> AuthenticationStrategy:
        if self.running:
            raise RuntimeError('The application is already running, configure authentication '
                               'before starting the application')
        if not strategy:
            strategy = AuthenticationStrategy()

        self._authentication_strategy = strategy
        return strategy

    def use_authorization(self, strategy: Optional[AuthorizationStrategy] = None) -> AuthorizationStrategy:
        if self.running:
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

    async def start(self):
        if self.started:
            return

        if self.on_start:
            await self.on_start.fire()
        self.started = True

        self.apply_routes()
        self.normalize_handlers()
        self.configure_middlewares()

    async def stop(self):
        await self.on_stop.fire()

    async def _handle_lifespan(self, receive, send):
        message = await receive()
        assert message['type'] == 'lifespan.startup'
        await self.start()
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
