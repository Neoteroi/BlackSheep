import asyncio
import ssl
from asyncio import AbstractEventLoop, TimeoutError
from typing import Any, AnyStr, Callable, Type, cast
from urllib.parse import urlencode

from blacksheep import URL, Content, InvalidURL, Request, Response, __version__
from blacksheep.common.types import HeadersType, ParamsType, URLType, normalize_headers
from blacksheep.middlewares import MiddlewareList, get_middlewares_chain
from blacksheep.utils.aio import get_running_loop

from .connection import ConnectionClosedError
from .cookies import CookieJar, cookies_middleware
from .exceptions import (
    CircularRedirectError,
    ConnectionTimeout,
    MaximumRedirectsExceededError,
    MissingLocationForRedirect,
    RequestTimeout,
    UnsupportedRedirect,
)
from .pool import ClientConnection, ConnectionPools


class RedirectsCache:
    """Used to store permanent redirects urls for later reuse"""

    __slots__ = ("_cache",)

    def __init__(self):
        self._cache: dict[bytes, URL] = {}

    def __setitem__(self, key: bytes, value: URL):
        self._cache[key] = value

    def __getitem__(self, item: Any) -> URL | None:
        try:
            return self._cache[item]
        except KeyError:
            return None

    def __contains__(self, item: Any) -> bool:
        return item in self._cache


class ClientRequestContext:
    __slots__ = ("path", "cookies")

    def __init__(self, request, cookies: CookieJar | None = None):
        self.path = [request.url.value.lower()]
        self.cookies = cookies


class ClientSession:
    USER_AGENT = f"python-blacksheep/{__version__}".encode("utf-8")

    def __init__(
        self,
        loop: AbstractEventLoop | None = None,
        base_url: None | bytes | str | URL = None,
        ssl: None | bool | ssl.SSLContext = None,
        pools: ConnectionPools | None = None,
        default_headers: HeadersType | None = None,
        follow_redirects: bool = True,
        connection_timeout: float = 10.0,
        request_timeout: float = 60.0,
        maximum_redirects: int = 20,
        redirects_cache_type: Type[RedirectsCache] | Any = None,
        cookie_jar: None | bool | CookieJar = None,
        middlewares: list[Callable[..., Any]] | None = None,
    ):
        if loop is None:
            loop = get_running_loop()

        if pools:
            self.owns_pools = False
        else:
            pools = ConnectionPools(loop)
            self.owns_pools = True

        if redirects_cache_type is None and follow_redirects:
            redirects_cache_type = RedirectsCache

        if middlewares is None:
            middlewares = []

        if cookie_jar is None or cookie_jar is True:
            cookie_jar = CookieJar()

        if cookie_jar is False:
            cookie_jar = None
        else:
            middlewares.insert(0, cookies_middleware)

        self.loop = loop
        self._base_url: URL | None
        self.base_url = base_url
        self.ssl = ssl
        self._default_headers: list[tuple[bytes, bytes]] | None
        self.default_headers = default_headers
        self.pools = pools
        self.connection_timeout = connection_timeout
        self.request_timeout = request_timeout
        self.follow_redirects = follow_redirects
        self.cookie_jar: CookieJar | None = cast(CookieJar | None, cookie_jar)
        self._permanent_redirects_urls = (
            redirects_cache_type() if follow_redirects else None
        )
        self.non_standard_handling_of_301_302_redirect_method = True
        self.maximum_redirects = maximum_redirects
        self._handler = None
        self._middlewares: MiddlewareList
        self.middlewares = middlewares
        self.delay_before_retry = 0.5

    @property
    def default_headers(self) -> list[tuple[bytes, bytes]] | None:
        return self._default_headers

    @default_headers.setter
    def default_headers(self, value: HeadersType | None):
        self._default_headers = normalize_headers(value)

    @property
    def middlewares(self) -> MiddlewareList:
        return self._middlewares

    @middlewares.setter
    def middlewares(self, value: MiddlewareList | list[Callable[..., Any]]):
        if isinstance(value, MiddlewareList):
            self._middlewares = value
        else:
            self._middlewares = MiddlewareList()

            for fn in value:
                self._middlewares.append(fn)
        self._build_middlewares_chain()

    @property
    def base_url(self) -> URL | None:
        return self._base_url

    @base_url.setter
    def base_url(self, value):
        url = None
        if value and not isinstance(value, URL):
            if isinstance(value, str):
                url = URL(value.encode())
            else:
                url = URL(value)
        self._base_url = url

    def add_middlewares(self, middlewares: list[Callable]):
        for middleware in middlewares:
            self._middlewares.append(middleware)
        self._build_middlewares_chain()

    def _build_middlewares_chain(self):
        if not self.middlewares:
            return

        async def root_handler(request):
            return await self._send_core(request)

        self._handler = get_middlewares_chain(self._middlewares, root_handler)

    def use_standard_redirect(self):
        """Uses specification compliant handling of 301 and 302 redirects"""
        self.non_standard_handling_of_301_302_redirect_method = False

    def get_url(self, url, params: ParamsType | None = None) -> bytes:
        value = self.get_url_value(url)
        if not params:
            return value
        query = urlencode(params).encode("ascii")
        return value + (b"&" if b"?" in value else b"?") + query

    def get_url_value(self, url: AnyStr | URL) -> bytes:
        if isinstance(url, str):
            url = url.encode()

        if not isinstance(url, URL):
            if url == b"":
                url = b"/"
            url = URL(url)

        if url.is_absolute:
            return url.value

        if self.base_url:
            return self.base_url.join(url).value
        return url.value

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def close(self):
        if self.owns_pools:
            self.pools.dispose()

    @staticmethod
    def extract_redirect_location(response: Response) -> URL:
        # if the server returned more than one value, use
        # the first header in order
        location = response.get_first_header(b"Location")
        if not location:
            raise MissingLocationForRedirect(response)

        # if the location cannot be parsed as URL, let exception happen:
        # this might be a redirect to a URN!
        # simply don't follows the redirect, and returns the response to
        # the caller
        try:
            return URL(location)
        except InvalidURL:
            raise UnsupportedRedirect(location)

    @staticmethod
    def get_redirect_url(request: Request, location: URL) -> URL:
        if location.is_absolute:
            return location
        # relative redirect URI
        # https://tools.ietf.org/html/rfc7231#section-7.1.2
        return request.url.base_url().join(location)

    def validate_redirect(
        self, redirect_url: URL, response: Response, context: ClientRequestContext
    ):
        redirect_url_lower = redirect_url.value.lower()
        if redirect_url_lower in context.path:
            context.path.append(redirect_url_lower)
            raise CircularRedirectError(context.path, response)

        context.path.append(redirect_url_lower)

        if len(context.path) > self.maximum_redirects:
            raise MaximumRedirectsExceededError(
                context.path, response, self.maximum_redirects
            )

    def update_request_for_redirect(self, request: Request, response: Response) -> None:
        context: ClientRequestContext = getattr(
            request, "context", ClientRequestContext(request, self.cookie_jar)
        )
        status = response.status

        if status == 301 or status == 302:
            if (
                self.non_standard_handling_of_301_302_redirect_method
                and request.method != "GET"
            ):
                # Change original request method to GET (Browser-like)
                request.method = "GET"

        if status == 303:
            # 303 See Other
            # Change original request method to GET
            request.method = "GET"

        location = self.extract_redirect_location(response)
        redirect_url = self.get_redirect_url(request, location)

        self.validate_redirect(redirect_url, response, context)

        if status == 301 or status == 308:
            self._permanent_redirects_urls[request.url.value] = redirect_url

        request.url = redirect_url

    def merge_default_headers(self, request: Request) -> None:
        if not self.default_headers:
            return

        for header in self.default_headers:
            if header[0] not in request.headers:
                request.headers.add(header[0], header[1])

    def check_permanent_redirects(self, request: Request) -> None:
        if (
            self._permanent_redirects_urls is not None
            and request.url.value in self._permanent_redirects_urls
        ):
            redirect_url = self._permanent_redirects_urls[request.url.value]
            if redirect_url is not None:
                request.url = redirect_url

    async def get_connection(self, url: URL) -> ClientConnection:
        pool = self.pools.get_pool(url.schema, url.host, url.port, self.ssl)

        try:
            return await asyncio.wait_for(
                pool.get_connection(), self.connection_timeout
            )
        except TimeoutError:
            raise ConnectionTimeout(url.base_url(), self.connection_timeout)

    def get_new_context(self, request: Request) -> ClientRequestContext:
        return ClientRequestContext(request, self.cookie_jar)

    def _validate_request_url(self, request: Request):
        if not request.url.is_absolute:
            if self.base_url:
                request.url = URL(self.get_url_value(request.url))
            else:
                raise ValueError(
                    "request.url must be a complete, absolute URL. "
                    "Either provide a base_url "
                    "for the client, or specify a full URL for the request."
                )

    async def send(self, request: Request) -> Response:
        self._validate_request_url(request)

        if not hasattr(request, "context"):
            request.context = self.get_new_context(request)  # type: ignore
            self.merge_default_headers(request)

        if self._handler:
            # using middlewares
            response = await self._handler(request)
        else:
            # without middlewares
            response = await self._send_core(request)

        if self.follow_redirects and response.is_redirect():
            try:
                self.update_request_for_redirect(request, response)
            except UnsupportedRedirect:
                # redirect not to HTTP / HTTPS: for example,
                # it can be a redirect to a URN - this is not followed
                return response
            return await self.send(request)

        return response

    async def _send_core(self, request: Request) -> Response:
        self.check_permanent_redirects(request)

        if not request.has_header(b"user-agent"):
            request.add_header(b"user-agent", self.USER_AGENT)

        return await self._send_using_connection(request)

    async def _send_using_connection(self, request, attempt: int = 1) -> Response:
        connection = await self.get_connection(request.url)

        try:
            return await asyncio.wait_for(
                connection.send(request), self.request_timeout
            )
        except ConnectionClosedError as connection_closed_error:
            if connection_closed_error.can_retry and attempt < 4:
                await asyncio.sleep(self.delay_before_retry)
                return await self._send_using_connection(request, attempt + 1)
            raise
        except TimeoutError:
            raise RequestTimeout(request.url, self.request_timeout)

    async def get(
        self,
        url: URLType,
        headers: HeadersType | None = None,
        params: ParamsType | None = None,
    ) -> Response:
        return await self.send(
            Request("GET", self.get_url(url, params), normalize_headers(headers))
        )

    async def post(
        self,
        url: URLType,
        content: Content | None = None,
        headers: HeadersType | None = None,
        params: ParamsType | None = None,
    ) -> Response:
        request = Request("POST", self.get_url(url, params), normalize_headers(headers))
        return await self.send(
            request.with_content(content) if content is not None else request
        )

    async def put(
        self,
        url: URLType,
        content: Content | None = None,
        headers: HeadersType | None = None,
        params: ParamsType | None = None,
    ) -> Response:
        request = Request("PUT", self.get_url(url, params), normalize_headers(headers))
        return await self.send(
            request.with_content(content) if content is not None else request
        )

    async def delete(
        self,
        url: URLType,
        content: Content | None = None,
        headers: HeadersType | None = None,
        params: ParamsType | None = None,
    ) -> Response:
        request = Request(
            "DELETE", self.get_url(url, params), normalize_headers(headers)
        )
        return await self.send(
            request.with_content(content) if content is not None else request
        )

    async def trace(
        self,
        url: URLType,
        headers: HeadersType | None = None,
        params: ParamsType | None = None,
    ) -> Response:
        return await self.send(
            Request("TRACE", self.get_url(url, params), normalize_headers(headers))
        )

    async def head(
        self,
        url: URLType,
        headers: HeadersType | None = None,
        params: ParamsType | None = None,
    ) -> Response:
        return await self.send(
            Request("HEAD", self.get_url(url, params), normalize_headers(headers))
        )

    async def patch(
        self,
        url: URLType,
        content: Content | None = None,
        headers: HeadersType | None = None,
        params: ParamsType | None = None,
    ) -> Response:
        request = Request(
            "PATCH", self.get_url(url, params), normalize_headers(headers)
        )
        return await self.send(
            request.with_content(content) if content is not None else request
        )

    async def options(
        self,
        url: URLType,
        content: Content | None = None,
        headers: HeadersType | None = None,
        params: ParamsType | None = None,
    ) -> Response:
        request = Request(
            "OPTIONS", self.get_url(url, params), normalize_headers(headers)
        )
        return await self.send(
            request.with_content(content) if content is not None else request
        )
