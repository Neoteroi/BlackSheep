import logging
import ssl
from asyncio import AbstractEventLoop, Queue, QueueEmpty, QueueFull
from ssl import SSLContext
from typing import Dict, Optional, Tuple, Union

from blacksheep.exceptions import InvalidArgument

from .connection import INSECURE_SSLCONTEXT, SECURE_SSLCONTEXT, ClientConnection

logger = logging.getLogger("blacksheep.client")


def get_ssl_context(
    scheme: bytes, ssl: Union[None, bool, ssl.SSLContext]
) -> Optional[ssl.SSLContext]:
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


class ClientConnectionPool:
    def __init__(
        self,
        loop: AbstractEventLoop,
        scheme: bytes,
        host: bytes,
        port: int,
        ssl: Union[None, bool, ssl.SSLContext] = None,
        max_size: int = 0,
    ) -> None:
        self.loop = loop
        self.scheme = scheme
        self.host = host if isinstance(host, str) else host.decode()
        self.port = int(port)
        self.ssl = get_ssl_context(scheme, ssl)
        self.max_size = max_size
        self._idle_connections: Queue[ClientConnection] = Queue(maxsize=max_size)
        self.disposed = False

    def _get_connection(self) -> ClientConnection:
        # if there are no connections, let QueueEmpty exception happen
        # if all connections are closed, remove all of them and let
        # QueueEmpty exception happen
        while True:
            connection: ClientConnection = self._idle_connections.get_nowait()

            if connection.open:
                logger.debug(
                    f"Reusing connection "
                    f"{id(connection)} to: {self.host}:{self.port}"
                )
                return connection

    def try_return_connection(self, connection: ClientConnection) -> None:
        if self.disposed:
            return

        try:
            self._idle_connections.put_nowait(connection)
        except QueueFull:
            pass

    async def get_connection(self) -> ClientConnection:
        try:
            return self._get_connection()
        except QueueEmpty:
            return await self.create_connection()

    async def create_connection(self) -> ClientConnection:
        logger.debug(f"Creating connection to: {self.host}:{self.port}")
        transport, connection = await self.loop.create_connection(
            lambda: ClientConnection(self.loop, self),
            self.host,
            self.port,
            ssl=self.ssl,
        )
        assert isinstance(connection, ClientConnection)
        await connection.ready.wait()
        # NB: a newly created connection is going to be used by a
        # request-response cycle;
        # so we don't put it inside the pool (since it's not immediately
        # reusable for other requests)
        return connection

    def dispose(self) -> None:
        self.disposed = True
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


class ClientConnectionPools:
    def __init__(self, loop: AbstractEventLoop) -> None:
        self.loop = loop
        self._pools: Dict[Tuple[bytes, bytes, int], ClientConnectionPool] = {}

    def get_pool(self, scheme, host, port, ssl):
        assert scheme in (b"http", b"https"), "URL schema must be http or https"
        if port is None or port == 0:
            port = 80 if scheme == b"http" else 443

        key = (scheme, host, port)
        try:
            return self._pools[key]
        except KeyError:
            new_pool = ClientConnectionPool(self.loop, scheme, host, port, ssl)
            self._pools[key] = new_pool
            return new_pool

    def dispose(self):
        for _, pool in self._pools.items():
            pool.dispose()
        self._pools.clear()
