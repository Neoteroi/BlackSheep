import time
import asyncio
from httptools import URL
from blacksheep import HttpRequest, HttpResponse, HttpHeaderCollection


class ClientProtocol(asyncio.Protocol):

    def __init__(self, loop):
        self.loop = loop
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport

    def data_received(self, data):
        print('Data received: {!r}'.format(data.decode()))
        # loop.stop()

    def connection_lost(self, exc):
        print('The server closed the connection')
        # loop.stop()


class HttpClientConnection:

    def __init__(self, loop, host=None, port=None, ssl=None):
        self.loop = loop
        self.host = host
        self.port = port
        self.ssl = ssl

    async def open(
            self, *, family=0, proto=0,
            flags=0, sock=None, local_addr=None,
            server_hostname=None,
            ssl_handshake_timeout=None):
        await self.loop.create_connection(
            lambda: ClientProtocol(loop=self.loop), self.host, self.port,
            self.ssl, family, proto,
            flags, sock, local_addr,
            server_hostname,
            ssl_handshake_timeout
        )


class HttpConnectionPool:

    def __init__(self):
        self.connections = {}

    async def get_connection(self, url):  # TODO: by hostname and port
        host = url.host.lower()
        schema = url.schema.lower()

        assert schema in (b'http', b'https'), 'URL schema must be http or https'

        port = url.port
        if port is None or port == 0:
            port = 443 if schema == b'https' else 80

        key = (schema, host, port)

        try:
            return self.connections[key]
        except KeyError:
            self.connections[key] = ConnectionPool(
                loop=self.loop,
                host=host,
                port=port,
                protocol=protocol,
                keep_alive=self.session.keep_alive
            )
        return self.pools[key]


class HttpClient:  # TODO: rename in ClientSession?

    def __init__(self,
                 url=None,
                 ssl=None,
                 keep_alive=True,
                 connection_pool=None,
                 default_headers=None):
        if not connection_pool:
            connection_pool = HttpConnectionPool()
        self.url = url
        self.ssl = ssl
        self.keep_alive = keep_alive
        self.default_headers = default_headers
        self.pool = connection_pool

    def get_headers(self):
        if not self.default_headers:
            return HttpHeaderCollection()
        return self.default_headers.clone()

    def get_url(self, url: bytes):
        # TODO: concatenate in a smart way
        if self.url:
            return self.url + b'/' + url
        # TODO: make sure that url is a valid url (http:// or https://)
        return url

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def close(self):
        pass

    async def send(self, request: HttpRequest):
        # TODO: get connection by hostname and port,
        #     write request
        #     send with transport, parse response, complete
        #
        request.headers += self.get_headers()
        connection = await self.pool.get_connection(request)
        pass

    async def get(self, url: bytes, headers=None):
        return await self.send(HttpRequest(b'GET', self.get_url(url), HttpHeaderCollection(headers), None))

    async def post(self, url, content, headers=None):
        return await self.send(HttpRequest(b'POST', self.get_url(url), HttpHeaderCollection(headers), content))

    async def put(self, url, content, headers=None):
        return await self.send(HttpRequest(b'PUT', self.get_url(url), HttpHeaderCollection(headers), content))

    async def delete(self, url, content=None, headers=None):
        return await self.send(HttpRequest(b'DELETE', self.get_url(url), HttpHeaderCollection(headers), content))

    async def trace(self, url, headers=None):
        return await self.send(HttpRequest(b'TRACE', self.get_url(url), HttpHeaderCollection(headers), None))

    async def head(self, url, headers=None):
        return await self.send(HttpRequest(b'HEAD', self.get_url(url), HttpHeaderCollection(headers), None))

    async def patch(self, url, content, headers=None):
        return await self.send(HttpRequest(b'PATCH', self.get_url(url), HttpHeaderCollection(headers), content))

    async def options(self, url, content, headers=None):
        return await self.send(HttpRequest(b'OPTIONS', self.get_url(url), HttpHeaderCollection(headers), content))
