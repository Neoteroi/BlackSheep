import ssl
import asyncio
import httptools
from blacksheep import HttpResponse
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

    # __slots__ = ()

    def __init__(self, loop, pool):
        self.loop = loop
        self.pool = pool
        self.transport = None
        self.open = False
        self.in_use = True
        self._connection_lost_exc = None
        self.writing_paused = False
        self.writable = asyncio.Event()
        self.ready = asyncio.Event()

        # per request state
        self.headers = []
        self.response = None
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

    async def send(self, request):
        # TODO: write request bytes
        #   return HttpResponse
        # TODO: instantiate response here or in headers complete?
        response = HttpResponse(-1, None, None)

        # TODO: continue here
        if is_small_request(request):
            self.transport.write(write_small_request(request))
        else:
            async for chunk in write_request(request):
                if self.writing_paused:
                    await self.writable.wait()
                self.transport.write(chunk)

        if not self.parser.should_keep_alive():
            self.close()
        self.reset()

        await response.complete.wait()
        return response

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
        pass

    def on_headers_complete(self):
        # cdef HttpRequest request
        status = self.parser.get_status_code()
        response = HttpResponse(
            status,
            HttpHeaders(self.headers),
            None
        )
        self.response = response
        # self.loop.create_task(self.handle_request(request))

    def on_message_complete(self):
        if self.response:
            self.response.complete.set()

    def on_body(self, bytes value):
        self.response.on_body(value)

        body_len = len(self.response.raw_body)

        if body_len > self.max_body_size:
            self.handle_invalid_response(b'Exceeds maximum body size')