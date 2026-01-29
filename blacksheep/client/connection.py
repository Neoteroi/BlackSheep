import asyncio
import ssl
import sys
import time
import weakref
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Protocol

import certifi
import h11
from h2.config import H2Configuration
from h2.connection import H2Connection
from h2.events import (
    DataReceived,
    ResponseReceived,
    StreamEnded,
    StreamReset,
    WindowUpdated,
)

from blacksheep import Content, Request, Response, StreamedContent

# Compatibility for asyncio.timeout (added in Python 3.11)
if sys.version_info >= (3, 11):
    from asyncio import timeout as asyncio_timeout
else:
    from async_timeout import timeout as asyncio_timeout

SECURE_SSLCONTEXT = ssl.create_default_context(
    ssl.Purpose.SERVER_AUTH, cafile=certifi.where()
)
SECURE_SSLCONTEXT.check_hostname = True

INSECURE_SSLCONTEXT = ssl.SSLContext(protocol=ssl.PROTOCOL_TLS_CLIENT)
INSECURE_SSLCONTEXT.check_hostname = False
INSECURE_SSLCONTEXT.verify_mode = ssl.CERT_NONE


# HTTP/2 SSL contexts with ALPN
def create_http2_ssl_context(verify: bool = True) -> ssl.SSLContext:
    """Create an SSL context that supports HTTP/2 via ALPN negotiation."""
    if verify:
        context = ssl.create_default_context(
            ssl.Purpose.SERVER_AUTH, cafile=certifi.where()
        )
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED
    else:
        context = ssl.SSLContext(protocol=ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

    # Set ALPN protocols - prefer HTTP/2, fallback to HTTP/1.1
    context.set_alpn_protocols(["h2", "http/1.1"])
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context


SECURE_HTTP2_SSLCONTEXT = create_http2_ssl_context(verify=True)
INSECURE_HTTP2_SSLCONTEXT = create_http2_ssl_context(verify=False)

# Buffer sizes optimized for HTTP/2 and HTTP/1.1
# HTTP/2 default frame size is 16KB, HTTP/1.1 can benefit from larger buffers
DEFAULT_HTTP2_BUFFER_SIZE = 16384  # 16KB
DEFAULT_HTTP11_BUFFER_SIZE = 65535  # 64KB


class HTTPConnection(ABC):
    """Abstract base class for HTTP connections (HTTP/1.1 and HTTP/2)."""

    @abstractmethod
    async def send(self, request: Request) -> Response:
        """Send an HTTP request and return the response."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close the connection."""
        pass

    @abstractmethod
    def is_alive(self) -> bool:
        """Check if connection is still alive and usable."""
        pass

    @property
    @abstractmethod
    def is_open(self) -> bool:
        """Return True if the connection is open."""
        pass


class HTTPResponseParserProtocol(Protocol):
    """
    Required protocol for classes that can parse HTTP Responses.
    """

    def __init__(self, connection) -> None: ...
    def feed_data(self, data: bytes) -> None: ...
    def get_status_code(self) -> int: ...
    def reset(self) -> None: ...


@dataclass(slots=True)
class StreamState:
    """Represents the state of an HTTP/2 stream."""

    headers: list
    content: "IncomingContent | None"
    buffered_data: bytearray
    complete: bool
    headers_received: bool
    status: int
    error: str | None


class IncomingContent(Content):
    def __init__(self, content_type: bytes):
        super().__init__(content_type, b"")
        self._body = bytearray()
        self._chunk = asyncio.Event()
        self._complete = asyncio.Event()
        self._exc: Exception | None = None

    @property
    def complete(self) -> asyncio.Event:
        return self._complete

    @property
    def exc(self) -> Exception | None:
        """
        Gets the exception that was set on this content, if any occurred while handling
        the request.
        """
        return self._exc

    @exc.setter
    def exc(self, value: Exception | None):
        """
        Sets an exception on this content. The exception is used and raised if the
        caller code is handling a response stream.
        """
        self._exc = value

        if value:
            # resume the loop for streaming content
            self._chunk.set()

    def extend_body(self, chunk: bytes | bytearray):
        self._body.extend(chunk)
        self._chunk.set()

    def set_complete(self):
        """
        Sets this incoming content as completed, waking up all requests to
        read() and stream().
        """
        self._complete.set()
        self._chunk.set()  # Wake up any waiting stream()

    async def stream(self):
        completed = False
        while not completed:
            await self._chunk.wait()
            self._chunk.clear()

            # Check if stream is complete even if there is no body data
            # This handles the case where complete.set() was called but no more data
            # arrived
            if self._complete.is_set() and not self._body:
                break

            if not self._body:
                # No data yet but not complete, continue waiting
                continue

            buf = bytes(self._body)  # create a copy of the buffer
            self._body.clear()
            completed = (
                self._complete.is_set()
            )  # we must check for EOD before yielding, or it will race

            yield buf  # use the copy

            if completed:
                break

            if self._exc:
                raise self._exc

    async def read(self):
        await self._complete.wait()
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


class HTTP2Connection(HTTPConnection):
    """
    HTTP/2 connection implementation using the h2 library.

    Supports stream multiplexing, HPACK header compression, flow control,
    and true response streaming.
    """

    __slots__ = (
        "pool",
        "host",
        "port",
        "ssl_context",
        "reader",
        "writer",
        "_connected",
        "_lock",
        "_read_lock",
        "h2_conn",
        "streams",
        "_stream_events",
        "_headers_events",
        "next_stream_id",
        "last_used",
        "request_count",
        "_closing",
        "_active_streams",
        "_reader_task",
        "_cached_scheme",
        "buffer_size",
    )

    def __init__(
        self,
        pool,
        host: str,
        port: int,
        ssl_context: ssl.SSLContext | None = None,
        buffer_size: int = DEFAULT_HTTP2_BUFFER_SIZE,
    ) -> None:
        """
        Initialize HTTP/2 connection.

        Args:
            pool: The connection pool this connection belongs to
            host: Server hostname
            port: Server port
            ssl_context: SSL context for the connection
            buffer_size: Buffer size for reading data (default: 16KB)
        """
        self.pool = weakref.ref(pool)
        self.host = host
        self.port = port
        self.ssl_context = ssl_context or SECURE_HTTP2_SSLCONTEXT
        self.buffer_size = buffer_size

        # Create H2 connection
        config = H2Configuration(client_side=True)
        self.h2_conn = H2Connection(config=config)

        # Async streams
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self._connected = False
        self._lock = asyncio.Lock()
        self._read_lock = asyncio.Lock()

        # Stream management with completion events
        self.streams: dict[int, StreamState] = {}
        self._stream_events: dict[int, asyncio.Event] = {}  # Stream complete events
        self._headers_events: dict[int, asyncio.Event] = {}  # Headers received events
        self.next_stream_id = 1

        # Connection pool tracking
        self.last_used = time.time()
        self.request_count = 0
        self._closing = False
        self._active_streams = 0  # Track streams with pending body reads
        self._reader_task: asyncio.Task | None = None  # Background reader task
        self._cached_scheme = "https" if ssl_context else "http"  # Cached scheme string

    @property
    def is_open(self) -> bool:
        """Return True if the connection is open."""
        return self._connected and not self._closing

    async def connect(self) -> None:
        """Establish SSL/TLS connection and initialize HTTP/2."""
        if self._connected:
            return

        async with self._lock:
            # Double-check inside lock to prevent race condition
            if self._connected:
                return

            self.reader, self.writer = await asyncio.open_connection(
                self.host,
                self.port,
                ssl=self.ssl_context,
                server_hostname=self.host,
            )

            # Verify HTTP/2 negotiation via ALPN
            ssl_object = self.writer.get_extra_info("ssl_object")
            if ssl_object:
                negotiated_protocol = ssl_object.selected_alpn_protocol()
                if negotiated_protocol != "h2":
                    raise ConnectionException(
                        f"HTTP/2 not negotiated, got: {negotiated_protocol}"
                    )

            # Initialize HTTP/2 connection
            self.h2_conn.initiate_connection()
            self.writer.write(self.h2_conn.data_to_send())
            await self.writer.drain()

            self._connected = True

    def _convert_request_to_h2_headers(self, request: Request) -> list[tuple[str, str]]:
        """Convert a BlackSheep Request to HTTP/2 pseudo-headers and headers."""
        # HTTP/2 pseudo-headers
        path = request.url.path or b"/"
        if request.url.query:
            path = path + b"?" + request.url.query

        headers = [
            (":method", request.method),
            (":path", path.decode("utf-8")),
            (":scheme", self._cached_scheme),
            (":authority", self.host),
        ]

        # Add Content-Type header from content if present
        if request.content and request.content.type:
            content_type = request.content.type
            content_type_str = (
                content_type.decode("utf-8")
                if isinstance(content_type, bytes)
                else content_type
            )
            headers.append(("content-type", content_type_str))

        # Add regular headers
        for name, value in request.headers:
            name_str = (
                name.decode("utf-8").lower()
                if isinstance(name, bytes)
                else name.lower()
            )
            value_str = value.decode("utf-8") if isinstance(value, bytes) else value

            # Skip headers that are represented as pseudo-headers in HTTP/2
            if name_str in ("host", "connection", "transfer-encoding"):
                continue

            headers.append((name_str, value_str))

        return headers

    async def send(self, request: Request) -> Response:
        """
        Send an HTTP request over HTTP/2 and return the response.

        Args:
            request: The BlackSheep Request object to send

        Returns:
            Response object
        """
        if not self._connected:
            await self.connect()

        async with self._lock:
            stream_id = self.next_stream_id
            self.next_stream_id += 2  # Client streams are odd numbers

            # Convert request to HTTP/2 headers
            h2_headers = self._convert_request_to_h2_headers(request)

            # Determine if we should stream or materialize the body
            # Only StreamedContent and content with unknown length can be streamed
            use_streaming = (
                request.content
                and isinstance(request.content, StreamedContent)
                and (request.content.length < 0 or request.content.body is None)
            )

            # Get request body if present (only for non-streaming content)
            body: bytes | None = None
            if request.content and not use_streaming:
                if request.content.body is not None:
                    body = request.content.body
                else:
                    body = await request.content.read()

            has_body = body is not None or use_streaming

            # Initialize stream tracking with completion event
            self.streams[stream_id] = StreamState(
                headers=[],
                content=None,
                buffered_data=bytearray(),
                complete=False,
                headers_received=False,
                status=-1,
                error=None,
            )
            self._stream_events[stream_id] = asyncio.Event()
            self._headers_events[stream_id] = asyncio.Event()
            self._active_streams += 1

            # Check for Expect: 100-continue header
            expect_continue = any(
                (h[0] == "expect" and h[1] == "100-continue") for h in h2_headers
            )

            # Send headers (without end_stream if expecting 100-continue with body)
            if expect_continue and has_body:
                # Don't set end_stream, wait for 100 Continue
                self.h2_conn.send_headers(stream_id, h2_headers, end_stream=False)
            else:
                # Normal behavior
                self.h2_conn.send_headers(
                    stream_id, h2_headers, end_stream=not has_body
                )
            self.writer.write(self.h2_conn.data_to_send())
            await self.writer.drain()

            # Handle Expect: 100-continue
            if expect_continue and has_body:
                # Wait for 100 Continue response or error
                should_send_body = await self._wait_for_100_continue_h2(stream_id)
                if not should_send_body:
                    # Got a final response (e.g., 417), don't send body
                    self.request_count += 1
                    self.last_used = time.time()
                    return await self._receive_response(stream_id)

            # Send body
            max_frame_size = self.h2_conn.max_outbound_frame_size
            if use_streaming:
                # Stream the content in chunks
                async for chunk in request.content.get_parts():
                    if chunk:
                        # Send chunk in frame-sized pieces
                        for i in range(0, len(chunk), max_frame_size):
                            frame_chunk = chunk[i : i + max_frame_size]
                            # Don't set end_stream yet, we don't know if this is the last chunk
                            self.h2_conn.send_data(
                                stream_id, frame_chunk, end_stream=False
                            )
                            self.writer.write(self.h2_conn.data_to_send())
                            await self.writer.drain()
                # Send final empty frame with end_stream=True
                self.h2_conn.send_data(stream_id, b"", end_stream=True)
                self.writer.write(self.h2_conn.data_to_send())
                await self.writer.drain()
            elif body:
                # Handle flow control for large bodies
                for i in range(0, len(body), max_frame_size):
                    chunk = body[i : i + max_frame_size]
                    is_last = i + max_frame_size >= len(body)
                    self.h2_conn.send_data(stream_id, chunk, end_stream=is_last)
                    self.writer.write(self.h2_conn.data_to_send())
                    await self.writer.drain()

            self.request_count += 1
            self.last_used = time.time()

        # Receive response
        return await self._receive_response(stream_id)

    async def _wait_for_100_continue_h2(
        self, stream_id: int, timeout: float = 5.0
    ) -> bool:
        """
        Wait for 100 Continue response for HTTP/2.

        Returns:
            True if should send body (got 100 or timeout)
            False if got final response (don't send body)
        """
        stream = self.streams.get(stream_id)
        if not stream:
            return True  # Proceed if stream doesn't exist

        try:
            async with asyncio_timeout(timeout):
                # Keep reading until we get headers
                while not stream.headers_received:
                    async with self._read_lock:
                        if not self.reader:
                            return True

                        data = await self.reader.read(self.buffer_size)
                        if not data:
                            return True  # Connection closed, proceed anyway

                        events = self.h2_conn.receive_data(data)
                        await self._process_events(events)
                        await self._send_pending_data()

                # Check the status we received
                if stream.status == 100:
                    # Got 100 Continue, proceed with body
                    # Reset headers_received so _receive_response can get the real
                    # response
                    stream.headers_received = False
                    stream.headers = []
                    stream.status = None
                    return True
                else:
                    # Got a final response (e.g., 417 Expectation Failed)
                    # Don't send body, let _receive_response handle this response
                    return False

        except asyncio.TimeoutError:
            # Timeout waiting for 100, proceed with body anyway
            return True

    async def _process_events(self, events) -> None:
        """Process H2 events and update streams."""
        for event in events:
            if isinstance(event, ResponseReceived):
                stream = self.streams.get(event.stream_id)
                if stream:
                    stream.headers = list(event.headers)
                    for name, value in event.headers:
                        if name == b":status" or name == ":status":
                            status_value = (
                                value if isinstance(value, str) else value.decode()
                            )
                            stream.status = int(status_value)
                            break
                    stream.headers_received = True
                    # Signal that headers are ready
                    headers_event = self._headers_events.get(event.stream_id)
                    if headers_event:
                        headers_event.set()

            elif isinstance(event, DataReceived):
                stream = self.streams.get(event.stream_id)
                if stream:
                    if stream.content:
                        # Stream data directly to IncomingContent
                        stream.content.extend_body(event.data)
                    else:
                        # Buffer data until IncomingContent is created
                        stream.buffered_data.extend(event.data)
                # Acknowledge received data for flow control
                self.h2_conn.acknowledge_received_data(
                    event.flow_controlled_length, event.stream_id
                )
                await self._send_pending_data()

            elif isinstance(event, StreamEnded):
                stream = self.streams.get(event.stream_id)
                if stream:
                    stream.complete = True
                    # Mark content as complete
                    if stream.content:
                        stream.content.set_complete()
                    stream_event = self._stream_events.get(event.stream_id)
                    if stream_event:
                        stream_event.set()
                    # Decrement active streams and possibly return to pool
                    self._active_streams -= 1
                    if self._active_streams == 0:
                        self._try_return_to_pool()

            elif isinstance(event, WindowUpdated):
                pass  # Flow control window updated

            elif isinstance(event, StreamReset):
                stream = self.streams.get(event.stream_id)
                if stream:
                    stream.complete = True
                    stream.error = f"Stream {event.stream_id} was reset"
                    # Set error on content if it exists
                    if stream.content:
                        stream.content.exc = ConnectionException(stream.error)
                        stream.content
                        stream_event.set()
                    # Also signal headers event in case we're waiting
                    headers_event = self._headers_events.get(event.stream_id)
                    if headers_event:
                        headers_event.set()
                    self._active_streams -= 1
                    if self._active_streams == 0:
                        self._try_return_to_pool()

    async def _send_pending_data(self) -> None:
        """Send any pending H2 data."""
        data_to_send = self.h2_conn.data_to_send()
        if data_to_send and self.writer:
            self.writer.write(data_to_send)
            await self.writer.drain()

    async def _receive_response(
        self, stream_id: int, timeout: float = 60.0
    ) -> Response:
        """
        Receive response for a specific stream with true streaming support.

        Returns the response as soon as headers are received. Body data
        is streamed progressively via IncomingContent.

        Args:
            stream_id: Stream ID to receive response for
            timeout: Timeout in seconds for headers

        Returns:
            BlackSheep Response object with streaming content
        """
        headers_event = self._headers_events[stream_id]

        # Start the background reader to process all incoming data
        self._start_background_reader()

        # Wait for headers to arrive (background reader will signal when ready)
        try:
            await asyncio.wait_for(headers_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            raise ConnectionException(f"Headers timeout for stream {stream_id}")

        # Check if stream still exists (might have been cleaned up on error)
        if stream_id not in self.streams:
            raise ConnectionClosedError(True)

        stream = self.streams[stream_id]
        if stream.error:
            # Check if it's a connection closed error (retryable)
            if "closed" in stream.error.lower():
                raise ConnectionClosedError(True)
            raise ConnectionException(stream.error)

        # Convert to BlackSheep Response
        response_headers = []
        for name, value in stream.headers:
            if isinstance(name, str):
                name = name.encode("utf-8")
            if isinstance(value, str):
                value = value.encode("utf-8")
            # Skip pseudo-headers
            if not name.startswith(b":"):
                response_headers.append((name, value))

        response = Response(stream.status, response_headers, None)

        # Create IncomingContent for streaming and store in stream
        content_type = (
            response.get_first_header(b"content-type") or b"application/octet-stream"
        )
        incoming_content = IncomingContent(content_type)
        stream.content = incoming_content
        response.content = incoming_content

        # Transfer any buffered data received before IncomingContent was created
        if stream.buffered_data:
            incoming_content.extend_body(stream.buffered_data)
            stream.buffered_data.clear()

        # If stream is already complete (no body or already received), mark as done
        if stream.complete:
            incoming_content.set_complete()
            # Clean up
            del self.streams[stream_id]
            del self._stream_events[stream_id]
            del self._headers_events[stream_id]
        else:
            # Start background reader to continue processing body data
            self._start_background_reader()

        return response

    def _start_background_reader(self) -> None:
        """Start a background task to read remaining stream data."""
        if self._reader_task is None or self._reader_task.done():
            self._reader_task = asyncio.create_task(self._background_read())

    async def _background_read(self) -> None:
        """Background task to read data for all active streams."""
        try:
            while self._connected and not self._closing:
                # Check if there are any streams to process
                if not self.streams and self._active_streams == 0:
                    break

                async with self._read_lock:
                    if self.reader is None:
                        break

                    try:
                        data = await asyncio.wait_for(
                            self.reader.read(self.buffer_size), timeout=1.0
                        )
                    except asyncio.TimeoutError:
                        # Check again if we should continue
                        if not self.streams and self._active_streams == 0:
                            break
                        continue

                    if not data:
                        # Connection closed
                        self._handle_connection_closed()
                        break

                    events = self.h2_conn.receive_data(data)
                    await self._process_events(events)
                    await self._send_pending_data()

                # Clean up completed streams that have had their content consumed
                # Only clean up if content.complete is set and body has been read
                completed = [
                    sid
                    for sid, s in self.streams.items()
                    if s.complete and s.content and s.content.complete.is_set()
                ]
                for sid in completed:
                    if sid in self.streams:
                        del self.streams[sid]
                    if sid in self._stream_events:
                        del self._stream_events[sid]
                    if sid in self._headers_events:
                        del self._headers_events[sid]

        except Exception as e:
            # Set error on all active streams and signal headers events
            for stream_id, stream in self.streams.items():
                stream.error = str(e)
                # Signal headers event so waiting requests can see the error
                if stream_id in self._headers_events:
                    self._headers_events[stream_id].set()
                if stream.content and not stream.complete:
                    stream.content.exc = e
                    stream.content

    def _handle_connection_closed(self) -> None:
        """Handle unexpected connection close."""
        for stream_id, stream in self.streams.items():
            if not stream.complete:
                stream.complete = True
                stream.error = "Connection closed"
                # Signal headers event so waiting requests can see the error
                if stream_id in self._headers_events:
                    self._headers_events[stream_id].set()
                if stream.content:
                    stream.content.exc = ConnectionClosedError(True)
                    stream.content.set_complete()

    def _try_return_to_pool(self) -> None:
        """Try to return this connection to its pool."""
        pool = self.pool()
        if pool and self.is_open:
            self.last_used = time.time()
            pool.try_return_connection(self)

    async def close(self) -> None:
        """Close the connection and properly wait for background tasks."""
        if self._connected and not self._closing:
            self._closing = True
            try:
                # Cancel background reader task and wait for it
                if self._reader_task and not self._reader_task.done():
                    self._reader_task.cancel()
                    try:
                        await self._reader_task
                    except asyncio.CancelledError:
                        pass
                    except Exception:
                        pass
                if self.writer:
                    self.writer.close()
                    try:
                        await self.writer.wait_closed()
                    except Exception:
                        pass
            except Exception:
                pass
            finally:
                self._connected = False
                self._reader_task = None

    def is_alive(self) -> bool:
        """Check if connection is still alive."""
        if not self._connected or self._closing:
            return False
        # Check idle timeout from pool
        pool = self.pool()
        idle_timeout = pool.idle_timeout if pool else 300.0
        return (time.time() - self.last_used) < idle_timeout


class HTTP11Connection(HTTPConnection):
    """
    HTTP/1.1 connection implementation using the h11 library.

    Uses async streams for consistent API with HTTP2Connection.
    Supports true response streaming.
    """

    __slots__ = (
        "pool",
        "host",
        "port",
        "ssl_context",
        "use_ssl",
        "reader",
        "writer",
        "_connected",
        "_lock",
        "_h11_conn",
        "last_used",
        "request_count",
        "_closing",
        "_streaming",  # True while streaming response body
        "buffer_size",
    )

    def __init__(
        self,
        pool,
        host: str,
        port: int,
        ssl_context: ssl.SSLContext | None = None,
        use_ssl: bool = True,
        buffer_size: int = DEFAULT_HTTP11_BUFFER_SIZE,
    ) -> None:
        """
        Initialize HTTP/1.1 connection.

        Args:
            pool: The connection pool this connection belongs to
            host: Server hostname
            port: Server port
            ssl_context: SSL context for the connection
            use_ssl: Whether to use SSL/TLS
        """
        self.pool = weakref.ref(pool)
        self.host = host
        self.port = port
        self.use_ssl = use_ssl
        self.ssl_context = ssl_context
        self.buffer_size = buffer_size

        # Async streams
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self._connected = False
        self._lock = asyncio.Lock()

        # h11 connection state machine
        self._h11_conn: h11.Connection | None = None

        # Connection pool tracking
        self.last_used = time.time()
        self.request_count = 0
        self._closing = False
        self._streaming = False  # True while streaming response body

    @property
    def is_open(self) -> bool:
        """Return True if the connection is open."""
        return self._connected and not self._closing

    async def connect(self) -> None:
        """Establish connection."""
        if self._connected:
            return

        async with self._lock:
            if self._connected:
                return

            self.reader, self.writer = await asyncio.open_connection(
                self.host,
                self.port,
                ssl=self.ssl_context if self.use_ssl else None,
                server_hostname=self.host if self.use_ssl else None,
            )

            self._h11_conn = h11.Connection(our_role=h11.CLIENT)
            self._connected = True

    def _convert_request_to_h11(
        self, request: Request
    ) -> tuple[h11.Request, bytes | None]:
        """Convert a BlackSheep Request to h11 request."""
        # Build request target (path + query)
        path = request.url.path or b"/"
        if request.url.query:
            path = path + b"?" + request.url.query

        # Build headers list
        headers = []

        # Add Content-Type header from content if present
        if request.content and request.content.type:
            content_type = request.content.type
            content_type_bytes = (
                content_type
                if isinstance(content_type, bytes)
                else content_type.encode("utf-8")
            )
            headers.append((b"content-type", content_type_bytes))

        # Add Host header if not present
        has_host = False
        for name, value in request.headers:
            name_bytes = name if isinstance(name, bytes) else name.encode("utf-8")
            value_bytes = value if isinstance(value, bytes) else value.encode("utf-8")
            if name_bytes.lower() == b"host":
                has_host = True
            headers.append((name_bytes, value_bytes))

        if not has_host and request.url.host:
            headers.insert(0, (b"host", request.url.host))

        # Get body and handle headers
        body: bytes | None = None
        use_chunked = False
        if request.content:
            # Check if we should use chunked encoding (unknown length)
            if request.content.length < 0:
                # Streaming content with unknown length - use chunked encoding
                use_chunked = True
                # Add transfer-encoding header if not present
                has_transfer_encoding = any(
                    h[0].lower() == b"transfer-encoding" for h in headers
                )
                if not has_transfer_encoding:
                    headers.append((b"transfer-encoding", b"chunked"))
            elif request.content.body is not None:
                # Content with known length and body already available
                body = request.content.body
                # Add content-length if not present
                has_content_length = any(
                    h[0].lower() == b"content-length" for h in headers
                )
                if not has_content_length:
                    headers.append((b"content-length", str(len(body)).encode()))
            else:
                # Content with known length but body not materialized yet
                # Add content-length from content.length if not present
                has_content_length = any(
                    h[0].lower() == b"content-length" for h in headers
                )
                if not has_content_length and request.content.length >= 0:
                    headers.append(
                        (b"content-length", str(request.content.length).encode())
                    )

        # Create h11 Request
        method = (
            request.method.encode()
            if isinstance(request.method, str)
            else request.method
        )
        h11_request = h11.Request(
            method=method,
            target=path,
            headers=headers,
        )

        return h11_request, body

    async def send(self, request: Request) -> Response:
        """
        Send an HTTP request over HTTP/1.1 and return the response.

        Args:
            request: The BlackSheep Request object to send

        Returns:
            Response object
        """
        if not self._connected:
            await self.connect()

        async with self._lock:
            # Reset h11 if needed for connection reuse
            # Both client and server must be DONE to start a new cycle
            if (
                self._h11_conn.our_state == h11.DONE
                and self._h11_conn.their_state == h11.DONE
            ):
                self._h11_conn.start_next_cycle()
            elif self._h11_conn.our_state not in (h11.IDLE, h11.DONE):
                # Connection is in an unusable state, reconnect
                self._h11_conn = h11.Connection(our_role=h11.CLIENT)

            # Determine if we need to stream or if we can send body directly
            # Only StreamedContent can be streamed
            use_streaming = (
                request.content
                and isinstance(request.content, StreamedContent)
                and (request.content.length < 0 or request.content.body is None)
            )

            # For non-streaming content with no body, read it first
            if request.content and request.content.body is None and not use_streaming:
                body_data = await request.content.read()
                # Update content with read body
                request.content = Content(request.content.type, body_data)

            # Convert request to h11 format
            h11_request, body = self._convert_request_to_h11(request)

            # Check for Expect: 100-continue header
            expect_continue = any(
                h[0].lower() == b"expect" and h[1].lower() == b"100-continue"
                for h in h11_request.headers
            )
            has_body = body or use_streaming

            # Send request headers
            data = self._h11_conn.send(h11_request)
            self.writer.write(data)
            await self.writer.drain()

            # Handle Expect: 100-continue
            if expect_continue and has_body:
                # Wait for 100 Continue or error response
                interim_response = await self._wait_for_100_continue()
                if interim_response is not None:
                    # Got a final response (e.g., 417 Expectation Failed), don't send body
                    return interim_response
                # Got 100 Continue or timeout, proceed to send body

            # Send body
            if use_streaming:
                # Stream the content in chunks
                async for chunk in request.content.get_parts():
                    if chunk:
                        data = self._h11_conn.send(h11.Data(data=chunk))
                        self.writer.write(data)
                        await self.writer.drain()
            elif body:
                # Send body directly
                data = self._h11_conn.send(h11.Data(data=body))
                self.writer.write(data)

            # Send end of message
            data = self._h11_conn.send(h11.EndOfMessage())
            self.writer.write(data)
            await self.writer.drain()

            self.request_count += 1
            self.last_used = time.time()

            # Receive response
            return await self._receive_response()

    async def _wait_for_100_continue(self, timeout: float = 5.0) -> Response | None:
        """
        Wait for 100 Continue response or a final response.

        Returns:
            None if 100 Continue received (proceed with body)
            Response if got final response like 417 (don't send body)
        """
        try:
            async with asyncio_timeout(timeout):
                while True:
                    event = self._h11_conn.next_event()

                    if event is h11.NEED_DATA:
                        data = await self.reader.read(self.buffer_size)
                        if not data:
                            # Connection closed, return None to proceed anyway
                            return None
                        self._h11_conn.receive_data(data)
                        continue

                    if isinstance(event, h11.InformationalResponse):
                        # Got 100 Continue or other 1xx
                        if event.status_code == 100:
                            return None  # Proceed with body
                        # Other 1xx responses, keep waiting
                        continue

                    if isinstance(event, h11.Response):
                        # Got a final response (e.g., 417 Expectation Failed)
                        # Build and return it, don't send body
                        status = event.status_code
                        response_headers = [(k, v) for k, v in event.headers]
                        response = Response(status, response_headers, None)

                        # Still need to read any body from this response
                        content_type = (
                            response.get_first_header(b"content-type")
                            or b"application/octet-stream"
                        )
                        incoming_content = IncomingContent(content_type)
                        response.content = incoming_content

                        # Start reading body in background
                        asyncio.create_task(self._read_response_body(incoming_content))
                        return response

        except asyncio.TimeoutError:
            # Timeout waiting for 100, proceed with body anyway
            return None

    async def _read_response_body(self, incoming_content: IncomingContent) -> None:
        """Read response body and stream to IncomingContent."""
        try:
            while True:
                event = self._h11_conn.next_event()

                if event is h11.NEED_DATA:
                    data = await self.reader.read(self.buffer_size)
                    if not data:
                        incoming_content.exc = ConnectionClosedError(False)
                        incoming_content.set_complete()
                        break
                    self._h11_conn.receive_data(data)
                    continue

                if isinstance(event, h11.Data):
                    incoming_content.extend_body(event.data)

                elif isinstance(event, h11.EndOfMessage):
                    incoming_content.set_complete()
                    break

                elif isinstance(event, h11.ConnectionClosed):
                    incoming_content.set_complete()
                    break

        except Exception as e:
            incoming_content.exc = e
            incoming_content.set_complete()

    async def _receive_response(self, timeout: float = 60.0) -> Response:
        """
        Receive and parse HTTP/1.1 response with true streaming support.

        Returns response immediately after headers are received.
        Body data is streamed progressively via IncomingContent.
        """
        status: int | None = None
        response_headers: list[tuple[bytes, bytes]] = []
        incoming_content: IncomingContent | None = None
        response: Response | None = None

        async def read_headers():
            """Read until we have response headers."""
            nonlocal status, response_headers

            while True:
                event = self._h11_conn.next_event()

                if event is h11.NEED_DATA:
                    data = await self.reader.read(self.buffer_size)
                    if not data:
                        raise ConnectionClosedError(True)
                    self._h11_conn.receive_data(data)
                    continue

                if isinstance(event, h11.InformationalResponse):
                    # Skip 1xx informational responses (like 100 Continue)
                    # These should have been handled earlier if Expect: 100-continue was used
                    continue

                if isinstance(event, h11.Response):
                    status = event.status_code
                    response_headers = [
                        (
                            k if isinstance(k, bytes) else k.encode(),
                            v if isinstance(v, bytes) else v.encode(),
                        )
                        for k, v in event.headers
                    ]
                    return  # Headers received, return to caller

                elif isinstance(event, h11.ConnectionClosed):
                    raise ConnectionClosedError(True)

        async def read_body():
            """Read body data and stream to IncomingContent."""
            try:
                while True:
                    event = self._h11_conn.next_event()

                    if event is h11.NEED_DATA:
                        data = await self.reader.read(self.buffer_size)
                        if not data:
                            # Connection closed unexpectedly
                            if incoming_content:
                                incoming_content.exc = ConnectionClosedError(False)
                                incoming_content.set_complete()
                            break
                        self._h11_conn.receive_data(data)
                        continue

                    if isinstance(event, h11.Data):
                        if incoming_content:
                            incoming_content.extend_body(event.data)

                    elif isinstance(event, h11.EndOfMessage):
                        if incoming_content:
                            incoming_content.set_complete()
                        break

                    elif isinstance(event, h11.ConnectionClosed):
                        if incoming_content:
                            incoming_content.set_complete()
                        break

            except Exception as e:
                if incoming_content:
                    incoming_content.exc = e
                    incoming_content.set_complete()
            finally:
                self._streaming = False
                self.last_used = time.time()
                # Handle connection reuse after body is complete
                if response:
                    self._handle_connection_reuse(response)

        # Read headers with timeout
        try:
            await asyncio.wait_for(read_headers(), timeout=timeout)
        except asyncio.TimeoutError:
            raise ConnectionException(f"Headers timeout after {timeout}s")

        # Create response immediately after headers
        response = Response(status, response_headers, None)

        # Create IncomingContent for streaming
        content_type = (
            response.get_first_header(b"content-type") or b"application/octet-stream"
        )
        incoming_content = IncomingContent(content_type)
        response.content = incoming_content

        # Check if there's a body expected
        content_length = response.get_first_header(b"content-length")
        transfer_encoding = response.get_first_header(b"transfer-encoding")
        has_body = (
            (content_length and int(content_length) > 0)
            or (transfer_encoding and b"chunked" in transfer_encoding)
            or response.get_first_header(b"content-type") is not None
        )

        if has_body:
            # Start reading body in background
            self._streaming = True
            asyncio.create_task(read_body())
        else:
            # No body, mark as complete immediately
            incoming_content.set_complete()
            self._handle_connection_reuse(response)

        return response

    def _handle_connection_reuse(self, response: Response) -> None:
        """Handle connection reuse based on response headers."""
        # Don't return to pool while still streaming
        if self._streaming:
            return

        connection_header = response.get_first_header(b"connection")
        should_close = connection_header and connection_header.lower() == b"close"

        # Check if h11 is in a reusable state (both sides must be DONE)
        h11_reusable = (
            self._h11_conn is not None
            and self._h11_conn.our_state == h11.DONE
            and self._h11_conn.their_state == h11.DONE
        )

        if should_close or not h11_reusable:
            self._closing = True
        else:
            # Return connection to pool
            self._try_return_to_pool()

    def _try_return_to_pool(self) -> None:
        """Try to return this connection to its pool."""
        pool = self.pool()
        if pool and self.is_open:
            self.last_used = time.time()
            pool.try_return_connection(self)

    async def close(self) -> None:
        """Close the connection."""
        if self._connected and not self._closing:
            self._closing = True
            try:
                if self.writer:
                    self.writer.close()
                    try:
                        await self.writer.wait_closed()
                    except Exception:
                        pass
            except Exception:
                pass
            finally:
                self._connected = False
                self._h11_conn = None

    def is_alive(self) -> bool:
        """Check if connection is still alive."""
        if not self._connected or self._closing:
            return False
        if self._streaming:
            return False  # Don't reuse while streaming
        if self._h11_conn is None:
            return False
        # Check h11 state - must be reusable (both DONE or both IDLE)
        our_state = self._h11_conn.our_state
        their_state = self._h11_conn.their_state
        if our_state == h11.CLOSED or their_state == h11.CLOSED:
            return False
        if our_state == h11.ERROR or their_state == h11.ERROR:
            return False
        # If client is DONE but server is not, connection is not reusable
        if our_state == h11.DONE and their_state != h11.DONE:
            return False
        # Check idle timeout from pool
        pool = self.pool()
        idle_timeout = pool.idle_timeout if pool else 300.0
        return (time.time() - self.last_used) < idle_timeout
