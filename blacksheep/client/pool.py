import logging
from asyncio import Queue, QueueEmpty, QueueFull
from ssl import SSLContext
from .connection import ClientConnection, SECURE_SSLCONTEXT, INSECURE_SSLCONTEXT, ConnectionClosedError
from blacksheep.exceptions import InvalidArgument


logger = logging.getLogger('blacksheep.client')


class ClientConnectionPool:

    def __init__(self, loop, scheme, host, port, ssl=None, max_size=0):
        self.loop = loop
        self.scheme = scheme
        self.host = host
        self.port = port
        self.ssl = self._ssl_option(ssl)
        self.max_size = max_size
        self._idle_connections = Queue(maxsize=max_size)
        self.disposed = False

    def _ssl_option(self, ssl):
        if self.scheme == b'https':
            if ssl is None:
                return SECURE_SSLCONTEXT
            if ssl is False:
                return INSECURE_SSLCONTEXT
            if isinstance(ssl, SSLContext):
                return ssl
            raise InvalidArgument('Invalid ssl argument, expected one of: '
                                  '{None, False, True, instance of ssl.SSLContext}')
        if ssl:
            raise InvalidArgument('SSL argument specified for non-https scheme.')
        return None

    def _get_connection(self):
        # if there are no connections, let QueueEmpty exception happen
        # if all connections are closed, remove all of them and let QueueEmpty exception happen
        while True:
            connection = self._idle_connections.get_nowait()  # type: ClientConnection

            if connection.open:
                logger.debug(f'Reusing connection {id(connection)} to: {self.host}:{self.port}')
                return connection

    def try_return_connection(self, connection):
        if self.disposed:
            return

        try:
            self._idle_connections.put_nowait(connection)
        except QueueFull:
            pass

    async def get_connection(self):
        try:
            return self._get_connection()
        except QueueEmpty:
            return await self.create_connection()

    async def create_connection(self):
        logger.debug(f'Creating connection to: {self.host}:{self.port}')
        transport, connection = await self.loop.create_connection(
            lambda: ClientConnection(self.loop, self),
            self.host,
            self.port,
            ssl=self.ssl)
        await connection.ready.wait()
        # NB: a newly created connection is going to be used by a request-response cycle;
        # so we don't put it inside the pool (since it's not immediately reusable for other requests)
        return connection

    def dispose(self):
        self.disposed = True
        while True:
            try:
                connection = self._idle_connections.get_nowait()
            except QueueEmpty:
                break
            else:
                logger.debug(f'Closing connection {id(connection)} to: {self.host}:{self.port}')
                connection.close()


class ClientConnectionPools:

    def __init__(self, loop):
        self.loop = loop
        self._pools = {}

    def get_pool(self, scheme, host, port, ssl):
        assert scheme in (b'http', b'https'), 'URL schema must be http or https'
        if port is None or port == 0:
            port = 80 if scheme == b'http' else 443
        
        key = (scheme, host, port)
        try:
            return self._pools[key]
        except KeyError:
            new_pool = ClientConnectionPool(self.loop, scheme, host, port, ssl)
            self._pools[key] = new_pool
            return new_pool

    def dispose(self):
        for key, pool in self._pools.items():
            pool.dispose()
