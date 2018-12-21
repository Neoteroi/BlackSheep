from asyncio import PriorityQueue, QueueEmpty, QueueFull
from ssl import SSLContext
from .connection import HttpConnection, SECURE_SSLCONTEXT, INSECURE_SSLCONTEXT, ConnectionClosedError
from blacksheep.exceptions import InvalidArgument


class HttpConnectionPool:

    def __init__(self, loop, scheme, host, port, ssl=None, max_size=0):
        self.loop = loop
        self.scheme = scheme
        self.host = host
        self.port = port
        self.ssl = self._ssl_option(ssl)
        self.max_size = max_size
        self._idle_connections = PriorityQueue(maxsize=max_size)

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
            connection = self._idle_connections.get_nowait()  # type: HttpConnection
            if connection.in_use:
                # we should not get here; since a connection should not reside in the queue
                # when in use
                continue

            if connection.open:
                connection.in_use = True  # in use for a request-response cycle
                return connection

    def try_put_connection(self, connection):
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
        transport, connection = await self.loop.create_connection(
            lambda: HttpConnection(self.loop, self),
            self.host,
            self.port,
            self.ssl,
            loop=self.loop)
        await connection.ready()
        # NB: a newly created connection is going to be used by a request-response cycle;
        # so we don't put it inside the pool (since it's not immediately reusable for other requests)
        return connection


class HttpConnectionPoolsManager:

    # TODO: put _pools in HttpConnectionPool as class property?
    #   and then override __new__ to return existing pools by key?
    def __init__(self, loop):
        self.loop = loop
        self._pools = {}

    def get_pool(self, scheme, host, port):
        assert scheme in (b'http', b'https'), 'URL schema must be http or https'
        if port is None:
            port = 80 if scheme == b'http' else 443
        
        key = (scheme, host, port)
        try:
            return self._pools[key]
        except KeyError:
            new_pool = HttpConnectionPool(self.loop, scheme, host, port)
            self._pools[key] = new_pool
            return new_pool


DEFAULT_POOLS = HttpConnectionPoolsManager()
