import ssl
import asyncio
import httptools
import certifi
import weakref
from blacksheep import Request, Response, Headers, Header
from blacksheep.scribe import is_small_request, write_small_request, write_request
from httptools import HttpParserError, HttpParserCallbackError
SECURE_SSLCONTEXT = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=certifi.where())
SECURE_SSLCONTEXT.check_hostname = True

INSECURE_SSLCONTEXT = ssl.SSLContext()
INSECURE_SSLCONTEXT.check_hostname = False


class ConnectionClosedError(Exception):

    def __init__(self, can_retry: bool):
        super().__init__('The connection was closed by the remote server.')
        self.can_retry = can_retry


class InvalidResponseFromServer(Exception):

    def __init__(self, inner_exception):
        super().__init__('The remote endpoint returned an invalid HTTP response.')
        self.inner_exception = inner_exception


class ClientConnection(asyncio.Protocol):

    __slots__ = (
        'loop',
        'pool',
        'transport',
        'open',
        '_connection_lost',
        'writing_paused',
        'writable',
        'ready',
        'response_ready',
        '_pending_task'
    )

    def __init__(self, loop, pool):
        self.loop = loop
        self.pool = weakref.ref(pool)
        self.transport = None
        self.open = False
        self.writing_paused = False
        self.writable = asyncio.Event()
        self.ready = asyncio.Event()
        self.response_ready = asyncio.Event()

        # per request state
        self.headers = []
        self.response = None
        self.parser = httptools.HttpResponseParser(self)
        self._connection_lost = False
        self._pending_task = None
        self._can_release = False

    def reset(self):
        self.headers.clear()
        self.response = None
        self.writing_paused = False
        self.writable.set()
        self.parser = httptools.HttpResponseParser(self)
        self._connection_lost = False
        self._pending_task = None
        self._can_release = False

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

        self._pending_task = False
        if self._can_release:
            self.loop.call_soon(self.release)

        response = self.response

        if self._connection_lost:  # TODO: should also check if the response is not complete?
            raise ConnectionClosedError(False)

        self.response_ready.clear()
        return response

    async def send(self, request):
        if not self.open:
            # NB: if the connection is closed here, it is always possible to try again with a new connection
            # instead, if it happens later; we cannot retry because we started sending a request
            raise ConnectionClosedError(True)

        self._pending_task = True

        if is_small_request(request):
            self.transport.write(write_small_request(request))
        else:
            async for chunk in write_request(request):
                if self._can_release:
                    # the server returned a response before we ended sending the request
                    return await self._wait_response()

                if not self.open:
                    raise ConnectionClosedError(False)

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
        self._connection_lost = True
        self.ready.clear()
        self.open = False

        if self._pending_task:
            self.response_ready.set()

    def on_header(self, name, value):
        self.headers.append(Header(name, value))

    def on_headers_complete(self):
        status = self.parser.get_status_code()
        self.response = Response(
            status,
            Headers(self.headers),
            None
        )
        self.response_ready.set()

    def on_message_complete(self):
        if self.response:
            self.response.complete.set()

        if self._pending_task:
            # the server returned a response before we ended sending the request,
            # the connection cannot be released now - this can happen for our Bad Requests
            self._can_release = True
            self.response_ready.set()
        else:
            # request-response cycle completed now,
            # the connection can be returned to its pool
            self.loop.call_soon(self.release)

    def release(self):
        if not self.open:
            return

        if self.parser.should_keep_alive():
            self.reset()
            pool = self.pool()

            if pool:
                pool.try_return_connection(self)
        else:
            self.close()

    def on_body(self, value: bytes):
        self.response.extend_body(value)
