import ssl
import asyncio
import httptools
from blacksheep import HttpRequest, HttpResponse, HttpHeaders, HttpHeader
from blacksheep.scribe import is_small_request, write_small_request, write_request
from httptools import HttpParserError, HttpParserCallbackError
SECURE_SSLCONTEXT = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
SECURE_SSLCONTEXT.check_hostname = True

INSECURE_SSLCONTEXT = ssl.SSLContext()
INSECURE_SSLCONTEXT.check_hostname = False


class ConnectionClosedError(Exception):
    pass


class InvalidResponseFromServer(Exception):

    def __init__(self, inner_exception):
        super().__init__('The remote endpoint returned an invalid HTTP response.')
        self.inner_exception = inner_exception


class HttpConnection(asyncio.Protocol):

    __slots__ = (
        'loop',
        'pool',
        'transport',
        'open',
        '_connection_lost_exc',
        'writing_paused',
        'writable',
        'ready',
        'response_ready'
    )

    def __init__(self, loop, pool):
        self.loop = loop
        self.pool = pool
        self.transport = None
        self.open = False
        self._connection_lost_exc = None
        self.writing_paused = False
        self.writable = asyncio.Event()
        self.ready = asyncio.Event()
        self.response_ready = asyncio.Event()

        # per request state
        self.headers = []
        self.response = None
        self.parser = httptools.HttpResponseParser(self)

    def reset(self):
        self.headers.clear()
        self.response = None
        self.writing_paused = False
        self.writable.set()
        self.parser = httptools.HttpResponseParser(self)

    def pause_writing(self):
        super().pause_writing()
        self.writing_paused = True
        self.writable.clear()

    def resume_writing(self):
        super().resume_writing()
        self.writing_paused = False
        self.writable.set()

    def connection_made(self, transport):
        self.transport = transport
        self.open = True
        self.ready.set()

    async def _wait_response(self):
        await self.response_ready.wait()
        response = self.response
        self.response_ready.clear()
        return response

    async def send(self, request):
        if is_small_request(request):
            self.transport.write(write_small_request(request))
        else:
            async for chunk in write_request(request):
                if self.writing_paused:
                    await self.writable.wait()
                self.transport.write(chunk)

        return await self._wait_response()

    def close(self):
        if self.open:
            self.open = False
            if self.transport:
                self.transport.close()

    def data_received(self, data):
        try:
            self.parser.feed_data(data)
        except HttpParserCallbackError:
            self.close()
            raise
        except HttpParserError as pex:
            raise InvalidResponseFromServer(pex)

    def connection_lost(self, exc):
        self._connection_lost_exc = exc
        self.ready.clear()
        self.open = False

    def on_header(self, name, value):
        self.headers.append(HttpHeader(name, value))

    def on_headers_complete(self):
        status = self.parser.get_status_code()
        response = HttpResponse(
            status,
            HttpHeaders(self.headers),
            None
        )
        self.response = response
        self.response_ready.set()

    def on_message_complete(self):
        if self.response:
            self.response.complete.set()

        # request-response cycle completed now,
        # the connection can be returned to its pool
        self.loop.call_soon(self.release)

    def release(self):
        if not self.open:
            return

        if self.parser.should_keep_alive():
            self.reset()
            self.pool.try_return_connection(self)
        else:
            self.close()

    def on_body(self, value: bytes):
        self.response.extend_body(value)
