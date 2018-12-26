import asyncio
from asyncio import TimeoutError
from typing import List, Optional, Union, Type, Any, Callable
from .pool import HttpConnectionPools
from .exceptions import *
from blacksheep import (HttpRequest,
                        HttpResponse,
                        HttpContent,
                        HttpHeaders,
                        HttpHeader,
                        URL,
                        InvalidURL)
from blacksheep.middlewares import get_middlewares_chain


URLType = Union[str, bytes, URL]


class RedirectsCache:
    """Used to store permanent redirects urls for later reuse"""

    __slots__ = ('_cache',)

    def __init__(self):
        self._cache = {}

    def store_redirect(self, source, destination):
        self._cache[source] = destination

    def __setitem__(self, key, value):
        self._cache[key] = value

    def __getitem__(self, item):
        try:
            return self._cache[item]
        except KeyError:
            return None

    def __contains__(self, item):
        return item in self._cache


class ClientRequestContext:

    __slots__ = ('path',)

    def __init__(self, request):
        self.path = [request.url.value.lower()]


def get_default_headers_middleware(headers):
    async def default_headers_middleware(request, handler):
        for header in headers:
            request.headers.add(header)
        return await handler(request)
    return default_headers_middleware


class ClientSession:

    def __init__(self,
                 loop=None,
                 url=None,
                 ssl=None,
                 pools=None,
                 default_headers: Optional[List[HttpHeader]] = None,
                 follow_redirects: bool = True,
                 connection_timeout: float = 3.0,
                 request_timeout: float = 60.0,
                 maximum_redirects: int = 20,
                 redirects_cache_type: Union[Type[RedirectsCache], Any] = None,
                 middlewares: Optional[List[Callable]] = None):
        if loop is None:
            loop = asyncio.get_event_loop()

        if url and not isinstance(url, URL):
            url = URL(url)

        if not pools:
            pools = HttpConnectionPools(loop)

        if redirects_cache_type is None and follow_redirects:
            redirects_cache_type = RedirectsCache

        self.loop = loop
        self.base_url = url
        self.ssl = ssl
        self.default_headers = HttpHeaders(default_headers)
        self.pools = pools
        self.connection_timeout = connection_timeout
        self.request_timeout = request_timeout
        self.follow_redirects = follow_redirects
        self._permanent_redirects_urls = redirects_cache_type() if follow_redirects else None
        self.non_standard_handling_of_301_302_redirect_method = True
        self.maximum_redirects = maximum_redirects
        self._handler = None
        self._middlewares = middlewares or []
        if middlewares:
            self._build_middlewares_chain()

    def add_middlewares(self, middlewares: List[Callable]):
        self._middlewares += middlewares
        self._build_middlewares_chain()

    def set_middlewares(self, middlewares: List[Callable]):
        self._middlewares = middlewares
        self._build_middlewares_chain()

    def _build_middlewares_chain(self):
        async def root_handler(request):
            return await self._send_core(request)

        self._handler = get_middlewares_chain(self._middlewares, root_handler)

    def use_standard_redirect(self):
        """Uses specification compliant handling of 301 and 302 redirects"""
        self.non_standard_handling_of_301_302_redirect_method = False

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

    def configure(self):
        if self._middlewares and not self._handler:
            self._build_middlewares_chain()
        pass

    def use_sync_logging(self):
        from .logs import client_logging_middleware
        if client_logging_middleware not in self._middlewares:
            self._middlewares.insert(0, client_logging_middleware)
        self._build_middlewares_chain()

    async def __aenter__(self):
        self.configure()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def close(self):
        self.pools.dispose()

    @staticmethod
    def extract_redirect_location(response: HttpResponse):
        location = response.headers[b'Location']
        if not location:
            raise MissingLocationForRedirect(response)
        # if the server returned more than one value, use the last header in order
        # if the location cannot be parsed as URL, let exception happen: this might be a redirect to a URN!!
        # simply don't follows the redirect, and returns the response to the caller
        try:
            return URL(location[-1].value)
        except InvalidURL:
            raise UnsupportedRedirect()

    @staticmethod
    def get_redirect_url(request: HttpRequest, location: URL):
        if location.is_absolute:
            return location
        # relative redirect URI
        # https://tools.ietf.org/html/rfc7231#section-7.1.2
        return request.url.base_url().join(location)

    def validate_redirect(self, redirect_url: URL, response: HttpResponse, context: ClientRequestContext):
        redirect_url_lower = redirect_url.value.lower()
        if redirect_url_lower in context.path:
            context.path.append(redirect_url_lower)

            raise CircularRedirectError(context.path, response)

        context.path.append(redirect_url_lower)

        if len(context.path) > self.maximum_redirects:
            raise MaximumRedirectsExceededError(context.path, response, self.maximum_redirects)

    def update_request_for_redirect(self,
                                    request: HttpRequest,
                                    response: HttpResponse):
        context = request.context  # type: ClientRequestContext
        status = response.status

        if status == 301 or status == 302:
            if self.non_standard_handling_of_301_302_redirect_method:
                # Change original request method to GET (Browser-like)
                request.method = b'GET'

        if status == 303:
            # 303 See Other
            # Change original request method to GET
            request.method = b'GET'

        location = self.extract_redirect_location(response)
        redirect_url = self.get_redirect_url(request, location)

        if redirect_url.schema.lower() not in {b'http', b'https'}:
            raise UnsupportedRedirect()

        self.validate_redirect(redirect_url, response, context)

        if status == 301 or status == 308:
            self._permanent_redirects_urls[request.url.value] = redirect_url

        request.url = redirect_url

    def merge_default_headers(self, request):
        if not self.default_headers:
            return

        for header in self.default_headers:
            if header.name not in request.headers:
                request.headers.add(header)

    def check_permanent_redirects(self, request):
        if self.follow_redirects and request.url.value in self._permanent_redirects_urls:
            request.url = self._permanent_redirects_urls[request.url.value]

    async def get_connection(self, url: URL):
        pool = self.pools.get_pool(url.schema, url.host, url.port, self.ssl)

        try:
            return await asyncio.wait_for(pool.get_connection(),
                                          self.connection_timeout,
                                          loop=self.loop)
        except TimeoutError:
            raise ConnectionTimeout(url.base_url(), self.connection_timeout)

    async def send(self, request: HttpRequest):
        if not hasattr(request, 'context'):
            request.context = ClientRequestContext(request)
            self.merge_default_headers(request)

        if self._handler:
            # using middlewares
            return await self._handler(request)

        # without middlewares
        return await self._send_core(request)

    async def _send_core(self, request: HttpRequest):
        self.check_permanent_redirects(request)

        connection = await self.get_connection(request.url)
        response = await self._send_using_connection(connection, request)

        if self.follow_redirects and response.is_redirect():
            try:
                self.update_request_for_redirect(request, response)
            except UnsupportedRedirect:
                # redirect not to HTTP / HTTPS: for example, it can be a redirect to a URN
                return response
            return await self.send(request)

        return response

    async def _send_using_connection(self, connection, request):
        try:
            return await asyncio.wait_for(connection.send(request),
                                          self.request_timeout,
                                          loop=self.loop)
        except TimeoutError:
            raise RequestTimeout(request.url, self.request_timeout)

    async def get(self,
                  url: URLType,
                  headers: Optional[List[HttpHeader]] = None):
        return await self.send(HttpRequest(b'GET',
                                           self.get_url(url),
                                           HttpHeaders(headers), None))

    async def post(self,
                   url: URLType,
                   content: HttpContent = None,
                   headers: Optional[List[HttpHeader]] = None):
        return await self.send(HttpRequest(b'POST',
                                           self.get_url(url),
                                           HttpHeaders(headers), content))

    async def put(self,
                  url: URLType,
                  content: HttpContent = None,
                  headers: Optional[List[HttpHeader]] = None):
        return await self.send(HttpRequest(b'PUT',
                                           self.get_url(url),
                                           HttpHeaders(headers), content))

    async def delete(self,
                     url: URLType,
                     content: HttpContent = None,
                     headers: Optional[List[HttpHeader]] = None):
        return await self.send(HttpRequest(b'DELETE',
                                           self.get_url(url),
                                           HttpHeaders(headers),
                                           content))

    async def trace(self,
                    url: URLType,
                    headers: Optional[List[HttpHeader]] = None):
        return await self.send(HttpRequest(b'TRACE',
                                           self.get_url(url),
                                           HttpHeaders(headers),
                                           None))

    async def head(self,
                   url: URLType,
                   headers: Optional[List[HttpHeader]] = None):
        return await self.send(HttpRequest(b'HEAD',
                                           self.get_url(url),
                                           HttpHeaders(headers),
                                           None))

    async def patch(self,
                    url: URLType,
                    content: HttpContent = None,
                    headers: Optional[List[HttpHeader]] = None):
        return await self.send(HttpRequest(b'PATCH',
                                           self.get_url(url),
                                           HttpHeaders(headers),
                                           content))

    async def options(self,
                      url: URLType,
                      content: HttpContent = None,
                      headers: Optional[List[HttpHeader]] = None):
        return await self.send(HttpRequest(b'OPTIONS',
                                           self.get_url(url),
                                           HttpHeaders(headers),
                                           content))
