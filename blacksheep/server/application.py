import html
import asyncio
import warnings
import traceback
from time import time, sleep
from threading import Thread
from typing import Optional, List, Callable
from multiprocessing import Process
from socket import IPPROTO_TCP, TCP_NODELAY, SO_REUSEADDR, SOL_SOCKET, SO_REUSEPORT, socket, SHUT_RDWR
from .options import ServerOptions
from datetime import datetime
from email.utils import formatdate
from blacksheep import HttpRequest, HttpResponse, TextContent, HtmlContent
from blacksheep.server.routing import Router
from blacksheep.server.logs import setup_sync_logging
from blacksheep.server.files.dynamic import serve_files
from blacksheep.server.files.static import serve_static_files
from blacksheep.exceptions import HttpException, HttpNotFound
from blacksheep.server.resources import get_resource_file_content


try:
    import uvloop
except ImportError:
    pass
else:
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())


__all__ = ('Application',)


def get_current_timestamp():
    return formatdate(timeval=datetime.utcnow().timestamp(),
                      localtime=False,
                      usegmt=True).encode()


def middleware_partial(handler, next_handler):
    async def middleware_wrapper(request):
        return await handler(request, next_handler)
    return middleware_wrapper


def get_middlewares_chain(middlewares, handler):
    fn = handler
    for middleware in reversed(middlewares):
        fn = middleware_partial(middleware, fn)
    return fn


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


class Application:

    def __init__(self,
                 options: Optional[ServerOptions]=None,
                 router: Optional[Router]=None,
                 middlewares: Optional[List[Callable]]=None,
                 resources: Optional[Resources]=None,
                 debug: bool=False):
        if not options:
            options = ServerOptions('', 8000)
        if router is None:
            router = Router()
        if middlewares is None:
            middlewares = []
        if resources is None:
            resources = Resources(get_resource_file_content('error.html'))
        self.debug = debug
        self.running = True
        self.options = options
        self.connections = set()
        self.middlewares = middlewares
        self.current_timestamp = get_current_timestamp()
        self.processes = []
        self.router = router
        self.access_logger = None
        self.logger = None
        self.services = {}
        self._default_headers = None
        self._use_sync_logging = False
        self._middlewares_configured = False
        self.resources = resources
        self._serve_files = None
        self._serve_static_files = None
        self.on_start = ApplicationEvent(self)
        self.on_stop = ApplicationEvent(self)

    def _validate_static_folders(self):
        if self._serve_static_files and self._serve_files:
            static_files_folder = self._serve_static_files[0]
            files_folder = self._serve_files[0]

            if not isinstance(static_files_folder, str):
                raise RuntimeError('The static files folder must be a string (folder name).')

            if not isinstance(files_folder, str):
                raise RuntimeError('The files folder must be a string  (folder name).')

            if static_files_folder.lower() == files_folder.lower():
                raise RuntimeError('Cannot configure the same folder for static files and dynamically read files')

    def route(self, pattern, methods=None):
        if methods is None:
            methods = [b'GET']
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
        self._validate_static_folders()

    def serve_static_files(self, folder_name='static', extensions=None, cache_max_age=10800, frozen=True):
        self._serve_static_files = folder_name, extensions, False, cache_max_age, frozen
        self._validate_static_folders()

    async def handle(self, request: HttpRequest) -> HttpResponse:
        route = self.router.get_match(request.method, request.raw_url.split(b'?')[0])

        if not route:
            return await self.handle_not_found(request)

        request.route_values = route.values

        try:
            return await route.handler(request)
        except HttpException as http_exception:
            return await self.handle_http_exception(request, http_exception)
        except Exception as exc:
            return await self.handle_exception(request, exc)

    async def handle_not_found(self, request: HttpRequest):
        return HttpResponse(404, content=TextContent('Resource not found'))

    async def handle_http_exception(self, request, http_exception):
        if isinstance(http_exception, HttpNotFound):
            return await self.handle_not_found(request)
        # TODO: improve the design of this feature
        return await self.handle_exception(request, http_exception)

    async def handle_exception(self, request, exc):
        if self.debug or self.options.show_error_details:
            tb = traceback.format_exception(exc.__class__,
                                            exc,
                                            exc.__traceback__)
            info = ''
            for item in tb:
                info += f'<li><pre>{html.escape(item)}</pre></li>'

            content = HtmlContent(self.resources.error_page_html
                                  .format_map({'info': info,
                                               'exctype': exc.__class__.__name__,
                                               'excmessage': str(exc),
                                               'method': request.method.decode(),
                                               'path': request.raw_url.decode()}))

            return HttpResponse(500, content=content)
        return HttpResponse(500, content=TextContent('Internal server error.'))

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

    def configure_middlewares(self):
        if self._middlewares_configured:
            return
        self._middlewares_configured = True

        if self._default_headers:
            self.middlewares.append(get_default_headers_middleware(self._default_headers))

        if self._use_sync_logging:
            self._configure_sync_logging()

        if self.middlewares:
            self._apply_middlewares_in_routes()

    def start(self):
        if self._serve_static_files:
            serve_static_files(self.router, *self._serve_static_files)

        if self._serve_files:
            serve_files(self.router, *self._serve_files)

        self.configure_middlewares()
        run_server(self)

    def stop(self):
        if self.running:
            for connection in self.connections:
                connection.close()
            self.connections.clear()
        self.running = False


def monitor_app(app: Application):
    while app.running:
        app.current_timestamp = get_current_timestamp()

        current_time = time()
        to_remove = []
        current_connections = app.connections.copy()

        for connection in current_connections:
            if current_time - connection.time_of_last_activity \
                    > app.options.limits.keep_alive_timeout:
                connection.close()
                to_remove.append(connection)

        for connection in to_remove:
            app.connections.discard(connection)
        sleep(10)


def monitor_processes(app: Application, processes: List[Process]):
    while app.running:
        sleep(10)
        if not app.running:
            return

        dead_processes = [p for p in processes if not p.is_alive()]
        for dead_process in dead_processes:
            processes.remove(dead_process)
            p = Process(target=spawn_server, args=(app,))
            p.start()
            processes.append(p)


def spawn_server(app: Application):
    loop = asyncio.new_event_loop()
    loop.set_debug(app.debug)
    asyncio.set_event_loop(loop)

    options = app.options

    if app.debug:
        loop.set_debug(True)

    s = socket()
    s.setsockopt(SOL_SOCKET, SO_REUSEPORT, 1)
    s.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)

    if options.no_delay:
        try:
            s.setsockopt(IPPROTO_TCP, TCP_NODELAY, 1)
        except (OSError, NameError):
            warnings.warn('ServerOptions set for NODELAY, but this option is not supported '
                          '(caused OSError or NameError on this host).', RuntimeWarning)

    s.bind((options.host, options.port))

    from blacksheep.connection import ConnectionHandler

    server = loop.create_server(lambda: ConnectionHandler(app=app, loop=loop),
                                sock=s,
                                reuse_port=options.processes_count > 1,
                                backlog=options.backlog)

    monitor_thread = None
    #if app.debug:
    #    print('[*] Connections monitoring is disabled when app.debug is True')
    #else:
    #    monitor_thread = Thread(target=monitor_app,
    #                            args=(app, ),
    #                            daemon=True)
    #    monitor_thread.start()

    def on_stop():
        loop.stop()
        app.stop()
        if monitor_thread:
            monitor_thread.join(30)

    if app.on_start:
        loop.run_until_complete(app.on_start.fire())

    print(f'[*] Listening on {options.host or "localhost"}:{options.port}')
    loop.run_until_complete(server)

    try:
        loop.run_forever()
    except (KeyboardInterrupt, SystemExit):
        print('[*] Exit')
    finally:
        pending = asyncio.Task.all_tasks()
        if pending:
            print('[*] completing pending tasks')
            # TODO: add a timeout here
            loop.run_until_complete(asyncio.gather(*pending))

        if app.on_stop:
            loop.run_until_complete(app.on_stop.fire())

        on_stop()
        s.shutdown(SHUT_RDWR)
        s.close()
        server.close()
        loop.close()


def run_server(app: Application):
    multi_process = app.options.processes_count > 1

    if multi_process:
        print(f'[*] Using multiprocessing ({app.options.processes_count})')
        processes = []
        for i in range(app.options.processes_count):
            p = Process(target=spawn_server, args=(app,))
            p.start()
            processes.append(p)

        monitor_thread = None
        if not app.debug:
            monitor_thread = Thread(target=monitor_processes,
                                    args=(app, processes),
                                    daemon=True)
            monitor_thread.start()

        for p in processes:
            try:
                p.join()
            except (KeyboardInterrupt, SystemExit):
                app.running = False

        if monitor_thread:
            monitor_thread.join(30)
    else:
        print(f'[*] Using single process. To enable multiprocessing, use `processes_count` in ServerOptions.')
        try:
            spawn_server(app)
        except (KeyboardInterrupt, SystemExit):
            print('[*] Exit')

