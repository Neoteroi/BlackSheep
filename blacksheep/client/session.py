import time
import asyncio
from .pool import HttpConnectionPool, HttpConnectionPoolsManager, DEFAULT_POOLS
from blacksheep import HttpRequest, HttpResponse, HttpHeaders, URL


class HttpClient:

    def __init__(self,
                 url=None,
                 ssl=None,
                 connection_pools=None,
                 default_headers=None):
        if url and not isinstance(url, URL):
            url = URL(url)
        if not connection_pools:
            connection_pool = DEFAULT_POOLS
        self.base_url = URL(url)
        self.ssl = ssl
        self.default_headers = default_headers
        self.pools = connection_pool

    def get_headers(self):
        if not self.default_headers:
            return HttpHeaders()
        return self.default_headers.clone()

    def get_url(self, url):
        if not isinstance(url, URL):
            url = URL(url)
        
        if self.base_url:
            return self.base_url.join(url)
        return self.base_url

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # TODO: release all connections that this client is using
        await self.close()

    async def close(self):
        pass

    async def send(self, request: HttpRequest):
        # TODO: get connection by hostname and port,
        #     write request
        #     send with transport, parse response, complete
        #
        request.headers += self.get_headers()
        
        url = request.url
        pool = self.pools.get_pool(url.scheme, url.host, url.port)
        # TODO: add timeout
        connection = await pool.get_connection()
        
        response = await connection.send(request)

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
