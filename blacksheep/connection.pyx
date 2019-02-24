from .headers cimport Header, Headers
from .messages cimport Request, Response
from .contents cimport TextContent
from .options cimport ServerOptions
from .scribe cimport is_small_response, write_small_response
from .baseapp cimport BaseApplication
from .scribe import write_response


include "includes/consts.pxi"


import time
import asyncio
import httptools
from asyncio import Event
from httptools import HttpParserUpgrade
from httptools.parser.errors import HttpParserCallbackError, HttpParserError


cdef class ServerConnection:
    
    def __init__(self, *, BaseApplication app, object loop):
        self.app = app
        self.websockets_handler = None
        self.services = app.services
        self.max_body_size = app.options.limits.max_body_size
        app.connections.append(self)
        self.time_of_last_activity = time.time()
        self.loop = loop
        self.transport = None
        self.reading_paused = False
        self.writing_paused = False
        self.writable = Event()
        self.closed = False

        self.parser = httptools.HttpRequestParser(self)
        self.url = None
        self.method = None
        self.request = None  # type: Request
        self.headers = []
        self.ignore_more_body = False

    cpdef void reset(self):
        self.request = None
        self.parser = httptools.HttpRequestParser(self)
        self.reading_paused = False
        self.writing_paused = False
        self.url = None
        self.method = None
        self.headers = []
        self.ignore_more_body = False

    def pause_reading(self):
        self.reading_paused = True
        self.transport.pause_reading()

    def resume_reading(self):
        self.reading_paused = False
        self.transport.resume_reading()

    cpdef void pause_writing(self):
        self.writing_paused = True

    cpdef void resume_writing(self):
        if self.writing_paused:
            self.time_of_last_activity = time.time()
            self.writing_paused = False
            self.writable.set()

    cpdef void connection_made(self, transport):
        self.time_of_last_activity = time.time()
        self.transport = transport

    cpdef void connection_lost(self, exc):
        self.dispose()

    cpdef void close(self):
        self.dispose()

    cpdef void dispose(self):
        cdef Request request = self.request

        self.closed = True

        if self.transport:
            try:
                self.transport.close()
            except:
                pass

        if request:
            request.active = False

            if not request.complete.is_set():
                # a connection is lost before a request content was complete
                request.aborted = True
                request.complete.set()

        self.app = None
        self.services = None
        self.request = None
        self.parser = None
        self.reading_paused = False
        self.writing_paused = False
        self.url = None
        self.method = None
        self.headers.clear()
        self.ignore_more_body = False

    cpdef void data_received(self, bytes data):
        self.time_of_last_activity = time.time()

        try:
            self.parser.feed_data(data)
        except AttributeError:
            if self.closed:
                pass
            else:
                raise
        except HttpParserCallbackError:
            self.dispose()
            raise
        except HttpParserError:
            # TODO: support logging this event
            self.dispose()
        except HttpParserUpgrade:
            self.handle_upgrade()

    cpdef bytes get_upgrade_value(self):
        cdef Header header
        for header in self.headers:
            if header.name.lower() == b'upgrade':
                return header.value.lower()
        return None

    cpdef void handle_upgrade(self):
        upgrade = self.get_upgrade_value()

        if upgrade != b'websocket':
            self.handle_invalid_request('Unsupported upgrade request.')
            return

        if not self.websockets_handler:
            self.handle_unsupported_request('WebSockets are not supported.')
            return

        self.transport.write(write_small_response(Response(101)))
        protocol = self.websockets_handler(self)
        self.transport.set_protocol(protocol)

    cpdef str get_client_ip(self):
        return self.transport.get_extra_info('peername')[0]

    def handle_invalid_request(self, message):
        self.transport.write(write_small_response(Response(400, Headers(), TextContent(message))))
        self.dispose()

    def handle_unsupported_request(self, message):
        self.transport.write(write_small_response(Response(501, Headers(), TextContent(message))))

    cpdef void on_body(self, bytes value):
        cdef int body_len

        if self.ignore_more_body:
            return

        self.request.on_body(value)

        body_len = len(self.request.raw_body)

        if body_len > self.max_body_size:
            self.ignore_more_body = True
            self.handle_invalid_request('Exceeds maximum body size')

    def on_message_complete(self):
        if self.request:
            self.request.complete.set()

    cpdef void on_headers_complete(self):
        cdef Request request
        request = Request(
            self.method,
            self.url,
            Headers(self.headers),
            None
        )
        request.services = self.services
        self.request = request
        self.loop.create_task(self.handle_request(request))

    async def reset_when_request_complete(self):
        # we need to wait for the client to send the message is sending,
        # before resetting this connection; because otherwise we cannot handle cleanly
        # situations where we send a response before getting the full request
        await self.request.complete.wait()

        if not self.parser.should_keep_alive():
            self.dispose()
        self.reset()

    cpdef void on_url(self, bytes url):
        self.url = url
        self.method = self.parser.get_method()

    cpdef void on_header(self, bytes name, bytes value):
        self.headers.append(Header(name, value))

        if len(self.headers) > MAX_REQUEST_HEADERS_COUNT or len(value) > MAX_REQUEST_HEADER_SIZE:
            self.transport.write(write_small_response(Response(413)))
            self.dispose()

    cpdef void eof_received(self):
        pass

    async def handle_request(self, Request request):
        if self.closed:
            return

        cdef bytes chunk
        cdef Response response

        response = await self.app.handle(request)

        # the request was handled: ignore any more body the client might be sending
        # for example, if the client tried to upload a file to a non-existing endpoint;
        # we return immediately 404 even though the client is still writing the content in the socket
        self.ignore_more_body = True

        # connection might get closed while the application is handling a request
        if self.closed:
            return

        if is_small_response(response):
            self.transport.write(write_small_response(response))
        else:
            async for chunk in write_response(response):

                if self.closed:
                    return

                if self.writing_paused:
                    await self.writable.wait()
                self.transport.write(chunk)

        await self.reset_when_request_complete()
