import asyncio
import logging
import ssl
from asyncio import Queue, QueueEmpty, QueueFull
from collections import deque
from ssl import SSLContext
from typing import Literal

from blacksheep.exceptions import InvalidArgument

from .connection import (
    INSECURE_HTTP2_SSLCONTEXT,
    INSECURE_SSLCONTEXT,
    SECURE_HTTP2_SSLCONTEXT,
    SECURE_SSLCONTEXT,
    HTTP2Connection,
    HTTP11Connection,
    HTTPConnection,
)

logger = logging.getLogger("blacksheep.client")


def get_ssl_context(
    scheme: bytes, ssl: None | bool | ssl.SSLContext
) -> ssl.SSLContext | None:
    if scheme != b"https":
        # Note: the SSL context is created for a connection pool, and it is correct
        # to return None if a ClientSession needs to make a request over HTTP
        return None

    if ssl is None or ssl is True:
        return SECURE_SSLCONTEXT
    if ssl is False:
        return INSECURE_SSLCONTEXT
    if isinstance(ssl, SSLContext):
        return ssl
    raise InvalidArgument(
        "Invalid ssl argument, expected one of: "
        "None, False, True, instance of ssl.SSLContext."
    )


def get_http2_ssl_context(
    scheme: bytes, ssl: None | bool | ssl.SSLContext
) -> ssl.SSLContext | None:
    """Get an SSL context configured for HTTP/2 with ALPN negotiation."""
    if scheme != b"https":
        # Note: the SSL context is created for a connection pool, and it is correct
        # to return None if a ClientSession needs to make a request over HTTP
        return None

    if ssl is None or ssl is True:
        return SECURE_HTTP2_SSLCONTEXT
    if ssl is False:
        return INSECURE_HTTP2_SSLCONTEXT
    if isinstance(ssl, SSLContext):
        # User provided custom context - ensure it has ALPN set
        try:
            ssl.set_alpn_protocols(["h2", "http/1.1"])
        except Exception:
            pass  # May already be set or not supported
        return ssl
    raise InvalidArgument(
        "Invalid ssl argument, expected one of: "
        "None, False, True, instance of ssl.SSLContext."
    )


class ConnectionPool:
    def __init__(
        self,
        scheme: bytes,
        host: bytes,
        port: int,
        ssl: None | bool | ssl.SSLContext = None,
        max_size: int = 0,
        http2: bool = True,
        idle_timeout: float = 300.0,
    ) -> None:
        self.scheme = scheme
        self.host = host if isinstance(host, str) else host.decode()
        self.port = int(port)
        self.ssl = get_ssl_context(scheme, ssl)
        self.http2_ssl = get_http2_ssl_context(scheme, ssl) if http2 else None
        self.max_size = max_size
        self.http2_enabled = http2 and scheme == b"https"
        self.idle_timeout = idle_timeout
        self._idle_connections: Queue[HTTPConnection] = Queue(maxsize=max_size)
        self._http2_connections: deque[HTTP2Connection] = deque()
        self._detected_protocol: Literal["h2", "http/1.1"] | None = None
        self._protocol_detection_lock = asyncio.Lock()
        self.disposed = False

    async def _detect_protocol(self) -> Literal["h2", "http/1.1"]:
        """
        Detect which protocol the server supports via ALPN negotiation.

        Returns:
            'h2' for HTTP/2, 'http/1.1' for HTTP/1.1
        """
        if not self.http2_enabled or self.scheme != b"https":
            return "http/1.1"

        # Check if already detected (fast path)
        if self._detected_protocol is not None:
            return self._detected_protocol

        async with self._protocol_detection_lock:
            # Double-check after acquiring lock
            if self._detected_protocol is not None:
                return self._detected_protocol

            try:
                reader, writer = await asyncio.open_connection(
                    self.host,
                    self.port,
                    ssl=self.http2_ssl,
                    server_hostname=self.host,
                )

                ssl_object = writer.get_extra_info("ssl_object")
                protocol = ssl_object.selected_alpn_protocol() or "http/1.1"

                # Store the detected protocol BEFORE closing (close can raise SSL errors)
                self._detected_protocol = protocol
                logger.debug(
                    f"Detected protocol {protocol} for {self.host}:{self.port}"
                )

                # Close the detection connection - ignore SSL errors during close
                try:
                    writer.close()
                    await writer.wait_closed()
                except Exception:
                    pass  # Ignore errors during close (e.g., SSL close notify issues)

                return protocol

            except Exception as e:
                logger.debug(
                    f"Protocol detection failed for {self.host}:{self.port}: {e}"
                )
                self._detected_protocol = "http/1.1"
                return "http/1.1"

    def _get_connection(self) -> HTTPConnection:
        # if there are no connections, let QueueEmpty exception happen
        # if all connections are closed, remove all of them and let
        # QueueEmpty exception happen
        while True:
            connection: HTTPConnection = self._idle_connections.get_nowait()

            if connection.is_open:
                logger.debug(
                    f"Reusing connection "
                    f"{id(connection)} to: {self.host}:{self.port}"
                )
                return connection

    def _get_http2_connection(self) -> HTTP2Connection | None:
        """Get an available HTTP/2 connection for multiplexing."""
        # Check each connection once by rotating through the deque
        for _ in range(len(self._http2_connections)):
            conn = self._http2_connections[0]
            if conn.is_alive():
                logger.debug(
                    f"Reusing HTTP/2 connection "
                    f"{id(conn)} to: {self.host}:{self.port}"
                )
                # Rotate to distribute load across connections
                self._http2_connections.rotate(-1)
                return conn
            # Dead connection, remove it and continue
            self._http2_connections.popleft()
        return None

    def try_return_connection(self, connection: HTTPConnection) -> None:
        if self.disposed:
            return

        # HTTP/2 connections are kept in a separate list for multiplexing
        if isinstance(connection, HTTP2Connection):
            if connection not in self._http2_connections:
                self._http2_connections.append(connection)
            return

        try:
            self._idle_connections.put_nowait(connection)
        except QueueFull:
            pass

    async def get_connection(self) -> HTTPConnection:
        # First, check protocol if HTTP/2 is enabled
        if self.http2_enabled:
            # Fast path: check cached protocol without async call
            if self._detected_protocol == "h2":
                # Try to get existing HTTP/2 connection (multiplexing)
                h2_conn = self._get_http2_connection()
                if h2_conn is not None:
                    return h2_conn
                # Create new HTTP/2 connection
                return await self._create_http2_connection()
            elif self._detected_protocol == "http/1.1":
                # Already detected as HTTP/1.1, skip to fallback
                pass
            else:
                # First request - need to detect protocol
                protocol = await self._detect_protocol()
                if protocol == "h2":
                    # Try to get existing HTTP/2 connection (multiplexing)
                    h2_conn = self._get_http2_connection()
                    if h2_conn is not None:
                        return h2_conn
                    # Create new HTTP/2 connection
                    return await self._create_http2_connection()

        # Fall back to HTTP/1.1
        try:
            return self._get_connection()
        except QueueEmpty:
            return await self.create_connection()

    async def _create_http2_connection(self) -> HTTP2Connection:
        """Create a new HTTP/2 connection."""
        logger.debug(f"Creating HTTP/2 connection to: {self.host}:{self.port}")
        connection = HTTP2Connection(
            pool=self,
            host=self.host,
            port=self.port,
            ssl_context=self.http2_ssl,
        )
        await connection.connect()
        self._http2_connections.append(connection)
        return connection

    async def create_connection(self) -> HTTP11Connection:
        """Create a new HTTP/1.1 connection using h11."""
        logger.debug(f"Creating HTTP/1.1 connection to: {self.host}:{self.port}")
        use_ssl = self.scheme == b"https"
        connection = HTTP11Connection(
            pool=self,
            host=self.host,
            port=self.port,
            ssl_context=self.ssl,
            use_ssl=use_ssl,
        )
        await connection.connect()
        # NB: a newly created connection is going to be used by a
        # request-response cycle;
        # so we don't put it inside the pool (since it's not immediately
        # reusable for other requests)
        return connection

    async def dispose(self) -> None:
        """Dispose of the pool and properly await connection cleanup."""
        self.disposed = True

        # Close HTTP/1.1 connections
        while True:
            try:
                connection = self._idle_connections.get_nowait()
            except QueueEmpty:
                break
            else:
                logger.debug(
                    f"Closing connection "
                    f"{id(connection)} to: {self.host}:{self.port}"
                )
                await connection.close()

        # Close HTTP/2 connections with proper async cleanup
        for conn in self._http2_connections:
            logger.debug(
                f"Closing HTTP/2 connection " f"{id(conn)} to: {self.host}:{self.port}"
            )
            await conn.close()
        self._http2_connections.clear()
        self._detected_protocol = None


class ConnectionPools:
    def __init__(self, http2: bool = True, idle_timeout: float = 300.0) -> None:
        self._pools: dict[tuple[bytes, bytes, int], ConnectionPool] = {}
        self.http2_enabled = http2
        self.idle_timeout = idle_timeout

    def get_pool(
        self, scheme: bytes, host: bytes, port: int, ssl: None | bool | ssl.SSLContext
    ):
        assert scheme in (b"http", b"https"), "URL schema must be http or https"
        if port is None or port == 0:
            port = 80 if scheme == b"http" else 443

        key = (scheme, host, port)
        try:
            return self._pools[key]
        except KeyError:
            new_pool = ConnectionPool(
                scheme,
                host,
                port,
                ssl,
                http2=self.http2_enabled,
                idle_timeout=self.idle_timeout,
            )
            self._pools[key] = new_pool
            return new_pool

    def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.dispose()

    async def dispose(self):
        """Dispose of all pools and properly await cleanup."""
        for pool in self._pools.values():
            await pool.dispose()
        self._pools.clear()
