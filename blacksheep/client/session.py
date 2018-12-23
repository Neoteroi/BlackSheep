import time
import asyncio
from .pool import HttpConnectionPool, HttpConnectionPools
from blacksheep import HttpRequest, HttpResponse, HttpHeaders, URL


class HttpRequestException(Exception):

    def __init__(self, message, allow_retry):
        super().__init__(message)
        self.can_retry = allow_retry


class HttpClient:

    def __init__(self,
                 loop=None,
                 url=None,
                 ssl=None,
                 pools=None,
                 default_headers=None):
        if loop is None:
            loop = asyncio.get_event_loop()

        if url and not isinstance(url, URL):
            url = URL(url)
        if not pools:
            pools = HttpConnectionPools(loop)
        self.loop = loop
        self.base_url = url
        self.ssl = ssl
        self.default_headers = default_headers
        self.pools = pools
        self.connection_timeout = 3.0
        self.request_timeout = 6660.0  # TODO: put in settings class

    def get_headers(self):
        if not self.default_headers:
            return HttpHeaders()
        return self.default_headers.clone()

    def get_url(self, url):
        if isinstance(url, str):
            url = url.encode()

        if not isinstance(url, URL):
            url = URL(url)

        if url.is_absolute:
            return url.value

        if self.base_url:
            return self.base_url.join(url).value
        return url.value

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # TODO: release all connections that this client is using
        await self.close()

    async def close(self):
        pass

    async def send(self, request: HttpRequest):
        request.headers += self.get_headers()

        # TODO: while True (with timeout?)
        url = request.url
        pool = self.pools.get_pool(url.schema, url.host, url.port, self.ssl)

        connection = await asyncio.wait_for(pool.get_connection(),
                                            self.connection_timeout,
                                            loop=self.loop)
        
        response = await asyncio.wait_for(connection.send(request),
                                          self.request_timeout,
                                          loop=self.loop)

        # TODO: should close the connection? (did the server return Connection: Close?)
        # TODO: follow redirects?
        return response

    async def get(self, url, headers=None):
        return await self.send(HttpRequest(b'GET', self.get_url(url), HttpHeaders(headers), None))

    async def post(self, url, content, headers=None):
        return await self.send(HttpRequest(b'POST', self.get_url(url), HttpHeaders(headers), content))

    async def put(self, url, content, headers=None):
        return await self.send(HttpRequest(b'PUT', self.get_url(url), HttpHeaders(headers), content))

    async def delete(self, url, content=None, headers=None):
        return await self.send(HttpRequest(b'DELETE', self.get_url(url), HttpHeaders(headers), content))

    async def trace(self, url, headers=None):
        return await self.send(HttpRequest(b'TRACE', self.get_url(url), HttpHeaders(headers), None))

    async def head(self, url, headers=None):
        return await self.send(HttpRequest(b'HEAD', self.get_url(url), HttpHeaders(headers), None))

    async def patch(self, url, content, headers=None):
        return await self.send(HttpRequest(b'PATCH', self.get_url(url), HttpHeaders(headers), content))

    async def options(self, url, content, headers=None):
        return await self.send(HttpRequest(b'OPTIONS', self.get_url(url), HttpHeaders(headers), content))
