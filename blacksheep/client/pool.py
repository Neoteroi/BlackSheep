import asyncio
import logging
import ssl
from asyncio import Queue, QueueEmpty, QueueFull
from ssl import SSLContext
from typing import Literal

from blacksheep.exceptions import InvalidArgument

from .connection import (
    INSECURE_SSLCONTEXT,
    SECURE_SSLCONTEXT,
    INSECURE_HTTP2_SSLCONTEXT,
    SECURE_HTTP2_SSLCONTEXT,
    HTTPConnection,
    HTTP11Connection,
    HTTP2Connection,
    create_http2_ssl_context,
)

logger = logging.getLogger("blacksheep.client")


def get_ssl_context(
    scheme: bytes, ssl: None | bool | ssl.SSLContext
) -> ssl.SSLContext | None:
    if scheme == b"https":
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

    if ssl:
        raise InvalidArgument("SSL argument specified for non-https scheme.")

    return None


def get_http2_ssl_context(
    scheme: bytes, ssl: None | bool | ssl.SSLContext
) -> ssl.SSLContext | None:
    """Get an SSL context configured for HTTP/2 with ALPN negotiation."""
    if scheme == b"https":
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

    if ssl:
        raise InvalidArgument("SSL argument specified for non-https scheme.")

    return None


class ConnectionPool:
    def __init__(
        self,
        scheme: bytes,
        host: bytes,
        port: int,
        ssl: None | bool | ssl.SSLContext = None,
        max_size: int = 0,
        http2: bool = True,
    ) -> None:
        self.scheme = scheme
        self.host = host if isinstance(host, str) else host.decode()
        self.port = int(port)
        self.ssl = get_ssl_context(scheme, ssl)
        self.http2_ssl = get_http2_ssl_context(scheme, ssl) if http2 else None
        self.max_size = max_size
        self.http2_enabled = http2 and scheme == b"https"
        self._idle_connections: Queue[HTTPConnection] = Queue(maxsize=max_size)
        self._http2_connections: list[HTTP2Connection] = []
        self._protocol_cache: dict[tuple[str, int], str] = {}
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

        key = (self.host, self.port)
        if key in self._protocol_cache:
            return self._protocol_cache[key]

        async with self._protocol_detection_lock:
            # Double-check after acquiring lock
            if key in self._protocol_cache:
                return self._protocol_cache[key]

            try:
                reader, writer = await asyncio.open_connection(
                    self.host,
                    self.port,
                    ssl=self.http2_ssl,
                    server_hostname=self.host,
                )

                ssl_object = writer.get_extra_info("ssl_object")
                protocol = ssl_object.selected_alpn_protocol() or "http/1.1"

                # Cache the protocol BEFORE closing (close can raise SSL errors)
                self._protocol_cache[key] = protocol
                logger.debug(f"Detected protocol {protocol} for {self.host}:{self.port}")

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
                self._protocol_cache[key] = "http/1.1"
                return "http/1.1"

    def _get_connection(self) -> HTTPConnection:
        # if there are no connections, let QueueEmpty exception happen
        # if all connections are closed, remove all of them and let
        # QueueEmpty exception happen
        while True:
            connection: HTTPConnection = self._idle_connections.get_nowait()

            if connection.open:
                logger.debug(
                    f"Reusing connection "
                    f"{id(connection)} to: {self.host}:{self.port}"
                )
                return connection

    def _get_http2_connection(self) -> HTTP2Connection | None:
        """Get an available HTTP/2 connection for multiplexing."""
        for conn in self._http2_connections:
            if conn.is_alive():
                logger.debug(
                    f"Reusing HTTP/2 connection "
                    f"{id(conn)} to: {self.host}:{self.port}"
                )
                return conn
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
        # First, detect protocol if HTTP/2 is enabled
        if self.http2_enabled:
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

    def dispose(self) -> None:
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
                connection.close()

        # Close HTTP/2 connections
        for conn in self._http2_connections:
            logger.debug(
                f"Closing HTTP/2 connection "
                f"{id(conn)} to: {self.host}:{self.port}"
            )
            conn.close()
        self._http2_connections.clear()
        self._protocol_cache.clear()


class ConnectionPools:
    def __init__(self, http2: bool = True) -> None:
        self._pools: dict[tuple[bytes, bytes, int], ConnectionPool] = {}
        self.http2_enabled = http2

    def get_pool(self, scheme, host, port, ssl):
        assert scheme in (b"http", b"https"), "URL schema must be http or https"
        if port is None or port == 0:
            port = 80 if scheme == b"http" else 443

        key = (scheme, host, port)
        try:
            return self._pools[key]
        except KeyError:
            new_pool = ConnectionPool(
                scheme, host, port, ssl, http2=self.http2_enabled
            )
            self._pools[key] = new_pool
            return new_pool

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.dispose()

    def dispose(self):
        for pool in self._pools.values():
            pool.dispose()
        self._pools.clear()
