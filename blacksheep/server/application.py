import os
import ssl
import logging
import asyncio
import uvloop
import warnings
from ssl import SSLContext
from time import time, sleep
from threading import Thread
from typing import Optional, List, Callable, Any
from multiprocessing import Process
from socket import IPPROTO_TCP, TCP_NODELAY, SOL_SOCKET, SO_REUSEPORT, socket, SHUT_RDWR
from email.utils import formatdate
from blacksheep.options import ServerOptions
from blacksheep.server.routing import Router
from blacksheep.server.logs import setup_sync_logging
from blacksheep.server.files.dynamic import serve_files
from blacksheep.server.files.static import serve_static_files
from blacksheep.server.resources import get_resource_file_content
from blacksheep.server.normalization import normalize_handler
from blacksheep.baseapp import BaseApplication
from blacksheep.middlewares import get_middlewares_chain
from blacksheep.utils.reloader import run_with_reloader


server_logger = logging.getLogger('blacksheep.server')

asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())


__all__ = ('Application',)


def get_current_timestamp():
    return formatdate(usegmt=True).encode()


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


class Application(BaseApplication):

    def __init__(self,
                 options: Optional[ServerOptions] = None,
                 router: Optional[Router] = None,
                 middlewares: Optional[List[Callable]] = None,
                 resources: Optional[Resources] = None,
                 services: Any = None,
                 debug: bool = False,
                 auto_reload: bool = True):
        if not options:
            options = ServerOptions('', 8000)
        if router is None:
            router = Router()
        if services is None:
            services = {}
        super().__init__(options, router, services)

        if middlewares is None:
            middlewares = []
        if resources is None:
            resources = Resources(get_resource_file_content('error.html'))
        self.debug = debug
        self.auto_reload = auto_reload
        self.running = False
        self.middlewares = middlewares
        self.current_timestamp = get_current_timestamp()
        self.processes = []
        self.access_logger = None
        self.logger = None
        self._default_headers = None
        self._use_sync_logging = False
        self._middlewares_configured = False
        self.resources = resources
        self._serve_files = None
        self._serve_static_files = None
        self.on_start = ApplicationEvent(self)
        self.on_stop = ApplicationEvent(self)

    def use_server_cert(self, cert_file: str, key_file: str):
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        context.load_cert_chain(certfile=cert_file, keyfile=key_file)
        self.use_ssl(context)

    def use_ssl(self, ssl_context: SSLContext):
        if self.running:
            raise RuntimeError('The application is already running, set the SSL Context '
                               'before starting the application')
        self.options.set_ssl(ssl_context)

    def _validate_static_folders(self):
        if self._serve_static_files and self._serve_files:
            static_files_folder = self._serve_static_files[0]
            files_folder = self._serve_files[0]

            if not isinstance(static_files_folder, str):
                raise RuntimeError('The static files folder must be a string (folder name).')

            if not isinstance(files_folder, str):
                raise RuntimeError('The files folder must be a string (folder name).')

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

        if self._default_headers:
            self.middlewares.append(get_default_headers_middleware(self._default_headers))

        if self._use_sync_logging:
            self._configure_sync_logging()

        if self.middlewares:
            self._apply_middlewares_in_routes()

    def start(self):
        self.running = True
        if self._serve_static_files:
            serve_static_files(self.router, *self._serve_static_files)

        if self._serve_files:
            serve_files(self.router, *self._serve_files)

        if self.debug and self.auto_reload:
            if self.options.processes_count > 1:
                print('[*] The application is in debug mode, but hot reload is disabled when using multiprocessing')
                run_server(self)
            else:
                run_with_reloader(lambda: run_server(self))
        else:
            run_server(self)

    def stop(self):
        if self.connections:
            for connection in self.connections.copy():
                connection.close()
            self.connections.clear()
        if self.running:
            self.loop.stop()
        self.running = False

    def on_connection_lost(self):
        pass


async def tick(app: Application, loop):
    while app.running:
        app.current_timestamp = get_current_timestamp()
        await asyncio.sleep(1, loop=loop)


async def monitor_connections(app: Application, loop):
    while app.running:
        current_time = time()

        for connection in app.connections.copy():
            inactive_for = current_time - connection.time_of_last_activity
            if inactive_for > app.options.limits.keep_alive_timeout:
                server_logger.debug(f'[*] Closing idle connection, inactive for: {inactive_for}.')

                if not connection.closed:
                    connection.close()
                try:
                    app.connections.remove(connection)
                except ValueError:
                    pass

            if connection.closed:
                try:
                    app.connections.remove(connection)
                except ValueError:
                    pass

        await asyncio.sleep(1, loop=loop)


def monitor_processes(app: Application, processes: List[Process]):
    while app.running:
        sleep(5)
        if not app.running:
            return

        dead_processes = [p for p in processes if not p.is_alive()]
        for dead_process in dead_processes:
            server_logger.warning(f'Process {dead_process.pid} died; removing and spawning a new one.')

            try:
                processes.remove(dead_process)
            except ValueError:
                # this means that the process was not anymore inside processes list
                pass
            else:
                p = Process(target=spawn_server, args=(app,))
                p.start()
                processes.append(p)

                server_logger.warning(f'Spawned a new process {p.pid}, to replace dead process {dead_process.pid}.')


def spawn_server(app: Application):
    loop = asyncio.new_event_loop()
    app.loop = loop

    if app.debug:
        loop.set_debug(True)
    asyncio.set_event_loop(loop)

    options = app.options

    if app.debug:
        loop.set_debug(True)

    s = socket()
    s.setsockopt(SOL_SOCKET, SO_REUSEPORT, 1)

    if options.no_delay:
        try:
            s.setsockopt(IPPROTO_TCP, TCP_NODELAY, 1)
        except (OSError, NameError):
            warnings.warn('ServerOptions set for NODELAY, but this option is not supported '
                          '(caused OSError or NameError on this host).', RuntimeWarning)

    s.bind((options.host, options.port))

    from blacksheep.connection import ServerConnection

    server = loop.create_server(lambda: ServerConnection(app=app, loop=loop),
                                sock=s,
                                reuse_port=options.processes_count > 1,
                                backlog=options.backlog,
                                ssl=options.ssl_context)
    loop.create_task(tick(app, loop))
    loop.create_task(monitor_connections(app, loop))

    def on_stop():
        loop.stop()
        app.stop()

    if app.on_start:
        loop.run_until_complete(app.on_start.fire())

    app.normalize_handlers()
    app.configure_middlewares()

    process_id = os.getpid()
    listening_on = ''.join(['https://' if options.ssl_context else 'http://',
                            options.host or 'localhost',
                            ':',
                            str(options.port)])
    print(f'[*] Process {process_id} is listening on {listening_on}')
    loop.run_until_complete(server)

    try:
        loop.run_forever()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        app.running = False
        pending = asyncio.Task.all_tasks()
        try:
            if pending:
                print(f'[*] Process {process_id} is completing pending tasks')
                try:
                    loop.run_until_complete(asyncio.wait_for(asyncio.gather(*pending),
                                            timeout=20,
                                            loop=loop))
                except asyncio.TimeoutError:
                    pass

            if app.on_stop:
                loop.run_until_complete(asyncio.wait_for(app.on_stop.fire(),
                                                         timeout=20,
                                                         loop=loop))
        except KeyboardInterrupt:
            pass

        on_stop()
        s.shutdown(SHUT_RDWR)
        s.close()
        server.close()
        loop.close()


def run_server(app: Application):
    multi_process = app.options.processes_count > 1

    if multi_process:
        print(f'[*] Using multiprocessing ({app.options.processes_count})')
        print(f'[*] Master process id: {os.getpid()}')
        processes = []
        for _ in range(app.options.processes_count):
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
            try:
                monitor_thread.join(30)
            except (KeyboardInterrupt, SystemExit):
                pass
    else:
        print(f'[*] Using single process. To enable multiprocessing, use `processes_count` in ServerOptions')
        try:
            spawn_server(app)
        except (KeyboardInterrupt, SystemExit):
            print('[*] Exit')
