import asyncio
import ssl
import time
import weakref
from abc import ABC, abstractmethod
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


class HTTPConnection(ABC):
    """Abstract base class for HTTP connections (HTTP/1.1 and HTTP/2)."""

    @abstractmethod
    async def send(self, request: Request) -> Response:
        """Send an HTTP request and return the response."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Close the connection."""
        pass

    @abstractmethod
    def is_alive(self) -> bool:
        """Check if connection is still alive and usable."""
        pass

    @property
    @abstractmethod
    def open(self) -> bool:
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


class IncomingContent(Content):
    def __init__(self, content_type: bytes):
        super().__init__(content_type, b"")
        self._body = bytearray()
        self._chunk = asyncio.Event()
        self.complete = asyncio.Event()
        self._exc: Exception | None = None

    @property
    def exc(self) -> Exception | None:
        """
        Gets an exception that was set on this content.
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


class HTTP2Connection(HTTPConnection):
    """
    HTTP/2 connection implementation using the h2 library.

    Supports stream multiplexing, HPACK header compression, and flow control.
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
        "next_stream_id",
        "last_used",
        "request_count",
        "_closing",
    )

    def __init__(
        self,
        pool,
        host: str,
        port: int,
        ssl_context: ssl.SSLContext | None = None,
    ) -> None:
        """
        Initialize HTTP/2 connection.

        Args:
            pool: The connection pool this connection belongs to
            host: Server hostname
            port: Server port
            ssl_context: SSL context for the connection
        """
        self.pool = weakref.ref(pool)
        self.host = host
        self.port = port
        self.ssl_context = ssl_context or SECURE_HTTP2_SSLCONTEXT

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
        self.streams: dict[int, dict] = {}
        self._stream_events: dict[int, asyncio.Event] = {}
        self.next_stream_id = 1

        # Connection pool tracking
        self.last_used = time.time()
        self.request_count = 0
        self._closing = False

    @property
    def open(self) -> bool:
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

    def _convert_request_to_h2_headers(
        self, request: Request
    ) -> list[tuple[str, str]]:
        """Convert a BlackSheep Request to HTTP/2 pseudo-headers and headers."""
        # HTTP/2 pseudo-headers
        path = request.url.path or b"/"
        if request.url.query:
            path = path + b"?" + request.url.query

        headers = [
            (":method", request.method),
            (":path", path.decode("utf-8")),
            (":scheme", request.url.schema.decode("utf-8")),
            (":authority", self.host),
        ]

        # Add Content-Type header from content if present
        if request.content and request.content.type:
            content_type = request.content.type
            content_type_str = content_type.decode("utf-8") if isinstance(content_type, bytes) else content_type
            headers.append(("content-type", content_type_str))

        # Add regular headers
        for name, value in request.headers:
            name_str = name.decode("utf-8").lower() if isinstance(name, bytes) else name.lower()
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

            # Get request body if present
            body: bytes | None = None
            if request.content:
                body = await request.content.read()

            # Initialize stream tracking with completion event
            self.streams[stream_id] = {
                "headers": [],
                "data": bytearray(),
                "complete": False,
                "status": None,
            }
            self._stream_events[stream_id] = asyncio.Event()

            # Send headers
            self.h2_conn.send_headers(
                stream_id, h2_headers, end_stream=(body is None or len(body) == 0)
            )
            self.writer.write(self.h2_conn.data_to_send())
            await self.writer.drain()

            # Send body if present
            if body:
                # Handle flow control for large bodies
                max_frame_size = self.h2_conn.max_outbound_frame_size
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

    async def _process_events(self, events) -> None:
        """Process H2 events and update streams."""
        for event in events:
            if isinstance(event, ResponseReceived):
                stream = self.streams.get(event.stream_id)
                if stream:
                    stream["headers"] = list(event.headers)
                    for name, value in event.headers:
                        if name == b":status" or name == ":status":
                            status_value = value if isinstance(value, str) else value.decode()
                            stream["status"] = int(status_value)
                            break

            elif isinstance(event, DataReceived):
                stream = self.streams.get(event.stream_id)
                if stream:
                    stream["data"].extend(event.data)
                # Acknowledge received data for flow control
                self.h2_conn.acknowledge_received_data(
                    event.flow_controlled_length, event.stream_id
                )
                await self._send_pending_data()

            elif isinstance(event, StreamEnded):
                stream = self.streams.get(event.stream_id)
                if stream:
                    stream["complete"] = True
                    stream_event = self._stream_events.get(event.stream_id)
                    if stream_event:
                        stream_event.set()

            elif isinstance(event, WindowUpdated):
                pass  # Flow control window updated

            elif isinstance(event, StreamReset):
                stream = self.streams.get(event.stream_id)
                if stream:
                    stream["complete"] = True
                    stream["error"] = f"Stream {event.stream_id} was reset"
                    stream_event = self._stream_events.get(event.stream_id)
                    if stream_event:
                        stream_event.set()

    async def _send_pending_data(self) -> None:
        """Send any pending H2 data."""
        data_to_send = self.h2_conn.data_to_send()
        if data_to_send and self.writer:
            self.writer.write(data_to_send)
            await self.writer.drain()

    async def _receive_response(self, stream_id: int, timeout: float = 60.0) -> Response:
        """
        Receive response for a specific stream.

        Args:
            stream_id: Stream ID to receive response for
            timeout: Timeout in seconds

        Returns:
            BlackSheep Response object
        """
        stream_event = self._stream_events[stream_id]

        async def read_until_complete():
            while not self.streams[stream_id]["complete"]:
                async with self._read_lock:
                    if self.reader is None:
                        raise ConnectionClosedError(False)

                    try:
                        data = await asyncio.wait_for(
                            self.reader.read(65535), timeout=1.0
                        )
                    except asyncio.TimeoutError:
                        # Check if another reader completed our stream
                        if self.streams[stream_id]["complete"]:
                            return
                        continue

                    if not data:
                        raise ConnectionClosedError(False)

                    events = self.h2_conn.receive_data(data)
                    await self._process_events(events)
                    await self._send_pending_data()

        try:
            # Wait for either direct reading or signal from another reader
            read_task = asyncio.create_task(read_until_complete())
            wait_task = asyncio.create_task(stream_event.wait())

            done, pending = await asyncio.wait(
                [read_task, wait_task],
                timeout=timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )

            # Cancel any pending tasks
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            if not done:
                raise ConnectionException(f"Response timeout for stream {stream_id}")

        except asyncio.TimeoutError:
            raise ConnectionException(f"Response timeout for stream {stream_id}")

        stream = self.streams[stream_id]
        if "error" in stream:
            raise ConnectionException(stream["error"])

        # Convert to BlackSheep Response
        response_headers = []
        for name, value in stream["headers"]:
            if isinstance(name, str):
                name = name.encode("utf-8")
            if isinstance(value, str):
                value = value.encode("utf-8")
            # Skip pseudo-headers
            if not name.startswith(b":"):
                response_headers.append((name, value))

        response = Response(stream["status"], response_headers, None)

        # Set response content using IncomingContent to support streaming
        body_data = bytes(stream["data"])
        if body_data:
            content_type = response.get_first_header(b"content-type") or b"application/octet-stream"
            incoming_content = IncomingContent(content_type)
            incoming_content.extend_body(body_data)
            incoming_content.complete.set()
            response.content = incoming_content

        # Clean up stream data
        del self.streams[stream_id]
        del self._stream_events[stream_id]

        # Return connection to pool
        self._try_return_to_pool()

        return response

    def _try_return_to_pool(self) -> None:
        """Try to return this connection to its pool."""
        pool = self.pool()
        if pool and self.open:
            self.last_used = time.time()
            pool.try_return_connection(self)

    def close(self) -> None:
        """Close the connection."""
        if self._connected and not self._closing:
            self._closing = True
            try:
                if self.writer:
                    self.writer.close()
            except Exception:
                pass
            finally:
                self._connected = False

    def is_alive(self) -> bool:
        """Check if connection is still alive."""
        if not self._connected or self._closing:
            return False
        # Consider connection dead if idle for more than 5 minutes
        return (time.time() - self.last_used) < 300


class HTTP11Connection(HTTPConnection):
    """
    HTTP/1.1 connection implementation using the h11 library.

    Uses async streams for consistent API with HTTP2Connection.
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
    )

    def __init__(
        self,
        pool,
        host: str,
        port: int,
        ssl_context: ssl.SSLContext | None = None,
        use_ssl: bool = True,
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

    @property
    def open(self) -> bool:
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
            content_type_bytes = content_type if isinstance(content_type, bytes) else content_type.encode("utf-8")
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

        # Get body
        body: bytes | None = None
        if request.content:
            # For h11, we need to handle content synchronously for now
            # The caller should have already prepared the body
            if request.content.body is not None:
                body = request.content.body
                # Add content-length if not present
                has_content_length = any(
                    h[0].lower() == b"content-length" for h in headers
                )
                if not has_content_length:
                    headers.append((b"content-length", str(len(body)).encode()))

        # Create h11 Request
        method = request.method.encode() if isinstance(request.method, str) else request.method
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
            if self._h11_conn.our_state == h11.DONE:
                self._h11_conn.start_next_cycle()

            # Read body if it's a coroutine/async content
            if request.content and request.content.body is None:
                body_data = await request.content.read()
                # Update content with read body
                request.content = Content(request.content.type, body_data)

            # Convert request to h11 format
            h11_request, body = self._convert_request_to_h11(request)

            # Send request
            data = self._h11_conn.send(h11_request)
            self.writer.write(data)

            # Send body if present
            if body:
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

    async def _receive_response(self, timeout: float = 60.0) -> Response:
        """Receive and parse HTTP/1.1 response."""
        status: int | None = None
        response_headers: list[tuple[bytes, bytes]] = []
        response_data = bytearray()

        async def read_response():
            nonlocal status, response_headers, response_data

            while True:
                event = self._h11_conn.next_event()

                if event is h11.NEED_DATA:
                    data = await self.reader.read(65535)
                    if not data:
                        raise ConnectionClosedError(False)
                    self._h11_conn.receive_data(data)
                    continue

                if isinstance(event, h11.Response):
                    status = event.status_code
                    response_headers = [
                        (
                            k if isinstance(k, bytes) else k.encode(),
                            v if isinstance(v, bytes) else v.encode()
                        )
                        for k, v in event.headers
                    ]

                elif isinstance(event, h11.Data):
                    response_data.extend(event.data)

                elif isinstance(event, h11.EndOfMessage):
                    break

                elif isinstance(event, h11.ConnectionClosed):
                    if status is None:
                        raise ConnectionClosedError(False)
                    break

        try:
            await asyncio.wait_for(read_response(), timeout=timeout)
        except asyncio.TimeoutError:
            raise ConnectionException(f"Response timeout after {timeout}s")

        # Create BlackSheep Response
        response = Response(status, response_headers, None)

        # Set response content using IncomingContent to support streaming
        body_data = bytes(response_data)
        if body_data:
            content_type = response.get_first_header(b"content-type") or b"application/octet-stream"
            incoming_content = IncomingContent(content_type)
            incoming_content.extend_body(body_data)
            incoming_content.complete.set()
            response.content = incoming_content

        # Check if connection should be kept alive
        self._handle_connection_reuse(response)

        return response

    def _handle_connection_reuse(self, response: Response) -> None:
        """Handle connection reuse based on response headers."""
        connection_header = response.get_first_header(b"connection")
        should_close = connection_header and connection_header.lower() == b"close"

        if should_close:
            self._closing = True
        else:
            # Return connection to pool
            self._try_return_to_pool()

    def _try_return_to_pool(self) -> None:
        """Try to return this connection to its pool."""
        pool = self.pool()
        if pool and self.open:
            self.last_used = time.time()
            pool.try_return_connection(self)

    def close(self) -> None:
        """Close the connection."""
        if self._connected and not self._closing:
            self._closing = True
            try:
                if self.writer:
                    self.writer.close()
            except Exception:
                pass
            finally:
                self._connected = False
                self._h11_conn = None

    def is_alive(self) -> bool:
        """Check if connection is still alive."""
        if not self._connected or self._closing:
            return False
        if self._h11_conn and self._h11_conn.our_state == h11.CLOSED:
            return False
        # Consider connection dead if idle for more than 5 minutes
        return (time.time() - self.last_used) < 300
