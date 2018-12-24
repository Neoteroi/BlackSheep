import asyncio
from typing import List, Optional, Union, Type, Any
from .pool import HttpConnectionPools
from blacksheep import (HttpRequest,
                        HttpResponse,
                        HttpContent,
                        HttpHeaders,
                        HttpHeader,
                        URL)


URLType = Union[str, bytes, URL]


class InvalidResponseException(Exception):

    def __init__(self, message, response):
        super().__init__(message)
        self.response = response


class MissingLocationForRedirect(InvalidResponseException):

    def __init__(self, response):
        super().__init__(f'The server returned a redirect status ({response.status}) '
                         f'but didn`t send a "Location" header', response)


class HttpRequestException(Exception):

    def __init__(self, message, allow_retry):
        super().__init__(message)
        self.can_retry = allow_retry


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


class ClientSession:

    def __init__(self,
                 loop=None,
                 url=None,
                 ssl=None,
                 pools=None,
                 default_headers: Optional[List[HttpHeader]] = None,
                 follow_redirects: bool = True,
                 redirects_cache_type: Union[Type[RedirectsCache], Any] = None):
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
        self.connection_timeout = 3.0
        self.request_timeout = 60.0
        self.follow_redirects = follow_redirects
        self._permanent_redirects_urls = redirects_cache_type() if follow_redirects else None
        self.non_standard_handling_of_301_302_redirect_method = True

    def use_standard_redirect(self):
        """Uses specification compliant handling of 301 and 302 redirects"""
        self.non_standard_handling_of_301_302_redirect_method = False

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

    @staticmethod
    def extract_redirect_location(response: HttpResponse):
        location = response.headers[b'Location']
        if not location:
            raise MissingLocationForRedirect(response)
        # if the server returned more than one value, use the last header in order
        return location[-1].value

    @staticmethod
    def get_redirect_url(request: HttpRequest, location: URL):
        if location.is_absolute:
            return location
        return request.url.base_url().join(location)

    def update_request_for_redirect(self, request: HttpRequest, response: HttpResponse):
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
        redirect_url = self.get_redirect_url(request, URL(location))

        if status == 301 or status == 308:
            self._permanent_redirects_urls[request.url.value] = redirect_url

        request.url = redirect_url

    def check_redirected_url(self, request):
        if self.follow_redirects and request.url.value in self._permanent_redirects_urls:
            request.url = self._permanent_redirects_urls[request.url.value]

    async def send(self, request: HttpRequest):
        # TODO: store request context (such as number of redirects, and to which page it redirected)
        #   validate max number of redirects

        request.headers += self.get_headers()
        return await self._send(request)

    async def _send(self, request: HttpRequest):
        self.check_redirected_url(request)

        url = request.url
        pool = self.pools.get_pool(url.schema, url.host, url.port, self.ssl)

        connection = await asyncio.wait_for(pool.get_connection(),
                                            self.connection_timeout,
                                            loop=self.loop)

        # TODO: weak reference to get_connection tasks and connection.send tasks
        # TODO: store connections in use and pending operations, to dispose them when the client is closed
        # TODO: test what happens if the connection is closed at this point, while sending the request

        response = await asyncio.wait_for(connection.send(request),
                                          self.request_timeout,
                                          loop=self.loop)

        # TODO: detect circular redirects, and applies a maximum number of redirects
        if self.follow_redirects and response.is_redirect():
            self.update_request_for_redirect(request, response)
            return await self._send(request)

        return response

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
