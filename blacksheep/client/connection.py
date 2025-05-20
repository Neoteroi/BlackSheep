import asyncio
import ssl
import weakref
from typing import Optional, Protocol

import certifi

from blacksheep import Content, Request, Response
from blacksheep.client.parser import get_default_parser
from blacksheep.scribe import (
    is_small_request,
    request_has_body,
    write_request,
    write_request_body_only,
    write_request_without_body,
    write_small_request,
)

SECURE_SSLCONTEXT = ssl.create_default_context(
    ssl.Purpose.SERVER_AUTH, cafile=certifi.where()
)
SECURE_SSLCONTEXT.check_hostname = True

INSECURE_SSLCONTEXT = ssl.SSLContext(protocol=ssl.PROTOCOL_TLS_CLIENT)
INSECURE_SSLCONTEXT.check_hostname = False
INSECURE_SSLCONTEXT.verify_mode = ssl.CERT_NONE


class HTTPResponseParserProtocol(Protocol):
    """
    Required protocol for classes that can parse HTTP Responses.
    """

    def __init__(self, connection) -> None: ...
    def feed_data(self, data: bytes) -> None: ...
    def get_status_code(self) -> int: ...
    def reset(self) -> None: ...


class IncomingContent(Content):
    def __init__(self, content_type: bytes):
        super().__init__(content_type, b"")
        self._body = bytearray()
        self._chunk = asyncio.Event()
        self.complete = asyncio.Event()
        self._exc: Optional[Exception] = None

    @property
    def exc(self) -> Optional[Exception]:
        """
        Gets an exception that was set on this content.
        """
        return self._exc

    @exc.setter
    def exc(self, value: Optional[Exception]):
        """
        Sets an exception on this content. The exception is used and raised if the
        caller code is handling a response stream.
        """
        self._exc = value

        if value:
            # resume the loop for streaming content
            self._chunk.set()

    def extend_body(self, chunk: bytes):
        self._body.extend(chunk)
        self._chunk.set()

    async def stream(self):
        completed = False
        while not completed:
            await self._chunk.wait()
            self._chunk.clear()

            if not self._body:
                break

            buf = bytes(self._body)  # create a copy of the buffer
            self._body.clear()
            completed = (
                self.complete.is_set()
            )  # we must check for EOD before yielding, or it will race

            yield bytes(buf)  # use the copy

            if completed:
                break

            if self._exc:
                raise self._exc

    async def read(self):
        await self.complete.wait()
        return bytes(self._body)


class ConnectionException(Exception):
    """
    Base class for client connections errors.
    """


class ConnectionClosedError(ConnectionException):
    """
    Exception raised when a connection that should be open is closed. The connection can
    have been closed by the remote server or the client.
    """

    def __init__(self, can_retry: bool):
        super().__init__("The connection was closed by the remote server.")
        self.can_retry = can_retry


class ConnectionLostError(ConnectionException):
    """
    Exception raised when a connection is lost. This can happen for example because of
    instable internet connection on the client. The client should retry repeating a
    request - this does not happen always automatically since the client might be using
    the response stream handling chunks.
    """

    def __init__(self):
        super().__init__("The connection with the remote server was lost.")


class InvalidResponseFromServer(Exception):
    def __init__(self, inner_exception, message=None):
        super().__init__(
            message or "The remote endpoint returned an invalid HTTP response."
        )
        self.inner_exception = inner_exception


class UpgradeResponse(Exception):
    """
    Exception used to communicate an upgrade response (HTTP 101) to the calling code.
    The exception is used to expose the response and transport object, so the caller
    can handle the upgrade response.
    """

    def __init__(self, response, transport):
        self.response = response
        self.transport = transport


class ClientConnection(asyncio.Protocol):
    __slots__ = (
        "loop",
        "pool",
        "transport",
        "open",
        "_connection_lost",
        "writing_paused",
        "writable",
        "ready",
        "response_ready",
        "request_timeout",
        "headers",
        "request",
        "response",
        "parser",
        "expect_100_continue",
        "_pending_task",
        "_can_release",
        "_upgraded",
    )

    def __init__(
        self, loop, pool, parser_impl: Optional[HTTPResponseParserProtocol] = None
    ) -> None:
        self.loop = loop
        self.pool = weakref.ref(pool)
        self.transport = None
        self.open = False
        self.writing_paused = False
        self.writable = asyncio.Event()
        self.ready = asyncio.Event()
        self.response_ready = asyncio.Event()
        self.expect_100_continue = False
        self.request = None
        self.request_timeout = 20
        self.headers = []
        self.response = None
        # Use the provided parser implementation, default to a built-in implementation
        # otherwise
        if parser_impl is not None:
            self.parser = parser_impl
        else:
            self.parser = get_default_parser(self)
        self._connection_lost = False
        self._pending_task = None
        self._can_release = False
        self._upgraded = False

    def reset(self) -> None:
        self.headers = []
        self.request = None
        self.response = None
        self.writing_paused = False
        self.writable.set()
        self.expect_100_continue = False
        # Reset parser implementation if possible, else re-instantiate
        try:
            self.parser.reset()
        except Exception:
            # TODO: raise exception if a different type was provided
            self.parser = get_default_parser(self)
        self._connection_lost = False
        self._pending_task = None
        self._can_release = False
        self._upgraded = False

    def pause_writing(self) -> None:
        super().pause_writing()
        self.writing_paused = True
        self.writable.clear()

    def resume_writing(self) -> None:
        super().resume_writing()
        self.writing_paused = False
        self.writable.set()

    def connection_made(self, transport) -> None:
        self.transport = transport
        self.open = True
        self.ready.set()

    async def _wait_response(self) -> Response:
        await self.response_ready.wait()

        if self._connection_lost:  # pragma: no cover
            raise ConnectionClosedError(True)

        response = self.response
        assert response is not None

        self._pending_task = False
        if self._can_release:
            self.loop.call_soon(self.release)

        if 99 < response.status < 200:
            # Handle 1xx informational
            #  https://tools.ietf.org/html/rfc7231#section-6.2

            if response.status == 101:
                # 101 Upgrade is a final response as it's used to switch
                # protocols with WebSockets handshake.
                # returns the response object with status 101 and access to the
                # transport
                self._upgraded = True
                raise UpgradeResponse(response, self.transport)

            if response.status == 100 and self.expect_100_continue:
                assert self.request is not None
                await self._send_body(self.request)

            # ignore;
            self.response_ready.clear()
            self.headers = []

            # await the final response
            return await self._wait_response()

        self.response_ready.clear()
        return response

    async def _write_chunks(self, request, method) -> Optional[Response]:
        async for chunk in method(request):
            if self._can_release:
                # the server returned a response before
                # we ended sending the request: can happen for a bad request or
                # unauthorized while posting a big enough body
                return await self._wait_response()

            if not self.open:
                raise ConnectionClosedError(False)

            if self.writing_paused:
                await self.writable.wait()
            self.transport.write(chunk)

    async def _send_body(self, request: Request) -> None:
        await self._write_chunks(request, write_request_body_only)

    async def send(self, request: Request) -> Response:
        if not self.open:
            # NB: if the connection is closed here, it is always possible to
            # try again with a new connection
            # instead, if it happens later; we cannot retry because we started
            # sending a request
            raise ConnectionClosedError(True)

        self.request = request
        self._pending_task = True

        if request_has_body(request) and request.expect_100_continue():
            # don't send the body immediately; instead, wait for HTTP 100
            # Continue interim response from server
            self.expect_100_continue = True
            self.transport.write(write_request_without_body(request))

            return await self._wait_response()

        if is_small_request(request):
            self.transport.write(write_small_request(request))
        else:
            response = await self._write_chunks(request, write_request)

            if response is not None:
                # this happens if the server sent a response before we completed
                # sending a body
                return response

        return await self._wait_response()

    def close(self) -> None:
        if self.open:
            self.open = False

            if self.response is not None and isinstance(
                self.response.content, IncomingContent
            ):
                self.response.content.exc = ConnectionClosedError(True)

            if self.transport:
                self.transport.close()

            self.parser = None

    def data_received(self, data: bytes) -> None:
        try:
            self.parser.feed_data(data)
        except Exception as exc:
            self.close()
            raise InvalidResponseFromServer(exc)

    def connection_lost(self, exc) -> None:
        self._connection_lost = True
        self.ready.clear()
        self.open = False

        # if the client was handling a stream, we need to stop the loop
        if self.response is not None and isinstance(
            self.response.content, IncomingContent
        ):
            self.response.content.exc = ConnectionLostError()
            self.response.content.complete.set()

        if self._pending_task:
            self.response_ready.set()

    def on_header(self, name, value):
        self.headers.append((name, value))

    def on_headers_complete(self) -> None:
        status = self.parser.get_status_code()
        self.response = Response(status, self.headers, None)
        # NB: check if headers declare a content-length
        if self._has_content():
            self.response.content = IncomingContent(
                (
                    self.response.get_first_header(b"content-type")
                    or b"application/octet-stream"
                )
            )
        self.response_ready.set()

    def _has_content(self) -> bool:
        assert self.response is not None

        content_type = self.response.get_first_header(b"content-type")
        if content_type:
            return True

        content_length = self.response.get_first_header(b"content-length")

        if content_length:
            try:
                content_length_value = int(content_length)
            except ValueError as value_error:
                # server returned an invalid content-length value
                raise InvalidResponseFromServer(
                    value_error,
                    f"The server returned an invalid value for"
                    f"the Content-Length header; value: {content_length}",
                )
            return content_length_value > 0

        transfer_encoding = self.response.get_first_header(b"transfer-encoding")

        if transfer_encoding and b"chunked" in transfer_encoding:
            return True

        return False

    def on_message_complete(self) -> None:
        if self.response and self.response.content:
            assert isinstance(self.response.content, IncomingContent)
            self.response.content.complete.set()
            self.response.content.extend_body(b"")

        if self._pending_task:
            # the server returned a response before we ended sending the
            # request, the connection can be released now - this can happen
            # for our Bad Requests
            self._can_release = True
            self.response_ready.set()
        else:
            # request-response cycle completed now,
            # the connection can be returned to its pool
            self.loop.call_soon(self.release)

    def should_keep_alive(self) -> bool:
        if self._connection_lost or not self.open:  # pragma: no cover
            return False

        assert self.response is not None
        connection_header = self.response.headers[b"connection"]
        if not connection_header:
            return True
        return connection_header[0].lower() != b"close"

    def release(self) -> None:
        if not self.open or self._upgraded:
            # if the connection was upgraded, its transport is used for
            # web sockets, it cannot return to its pool for other cycles
            return

        if self.should_keep_alive():
            self.reset()
            pool = self.pool()

            if pool:
                pool.try_return_connection(self)
        else:
            self.close()

    def on_body(self, value: bytes) -> None:
        assert self.response is not None and isinstance(
            self.response.content, IncomingContent
        )
        self.response.content.extend_body(value)
