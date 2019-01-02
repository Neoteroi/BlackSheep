import logging
from typing import Optional
from ipaddress import ip_address
from datetime import datetime, timedelta
from blacksheep import Request, Cookie, URL


client_logger = logging.getLogger('blacksheep.client')


class InvalidCookie(Exception):

    def __init__(self, message):
        super().__init__(message)


class InvalidCookieDomain(InvalidCookie):

    def __init__(self):
        super().__init__('Invalid domain attribute')


class MissingHostInURL(ValueError):

    def __init__(self):
        super().__init__('An URL with host is required.')


def not_ip_address(value: str):
    try:
        ip_address(value)
    except ValueError:
        return True
    return False


class StoredCookie:

    __slots__ = ('cookie',
                 'persistent',
                 'creation_time',
                 'expiry_time')

    def __init__(self, cookie: Cookie):
        # https://tools.ietf.org/html/rfc6265#section-5.3
        self.cookie = cookie
        self.creation_time = datetime.utcnow()

        expiry = None
        if cookie.max_age:
            # https://tools.ietf.org/html/rfc6265#section-5.2.2
            try:
                max_age = int(cookie.max_age)
            except ValueError:
                pass
            else:
                if max_age <= 0:
                    expiry = datetime.min
                else:
                    expiry = self.creation_time + timedelta(seconds=max_age)
        elif cookie.expires:
            expiry = cookie.expiration

        self.expiry_time = expiry
        self.persistent = True if expiry else False

    @property
    def name(self):
        return self.cookie.name

    def is_expired(self) -> bool:
        expiration = self.expiry_time
        if expiration and expiration < datetime.utcnow():
            return True

        # NB: it's a 'session cookie'; in other words
        # it expires when the session is closed
        return False


class CookieJar:

    def __init__(self):
        self._domain_cookies = {}     # cookies with specific domain
        self._host_only_cookies = {}  # cookies without specific domain

    @staticmethod
    def _get_url_host(request_url: URL):
        if not request_url.host:
            raise MissingHostInURL()

        return request_url.host.lower()

    @staticmethod
    def _get_url_path(request_url: URL):
        if request_url.path:
            return request_url.path.lower()
        return b'/'

    def get_domain(self, request_url: URL, cookie: Cookie) -> bytes:
        # https://tools.ietf.org/html/rfc6265#section-4.1.2.3
        request_domain = self._get_url_host(request_url)

        if not cookie.domain:
            return request_domain

        cookie_domain = cookie.domain.lstrip(b'.').lower()

        if cookie_domain.endswith(b'.'):
            # ignore the domain attribute;
            return request_domain

        if not request_domain.endswith(cookie_domain):
            client_logger.warning(f'A response for {request_url.value} tried to set '
                                  f'a cookie with domain {cookie_domain}; this could '
                                  f'be a malicious action.')
            raise InvalidCookieDomain()

        return cookie_domain

    @staticmethod
    def get_path(request_url: URL, cookie: Cookie):
        if cookie.path:
            return cookie.path.lower()

        return CookieJar.get_cookie_default_path(request_url)

    @staticmethod
    def get_cookie_default_path(request_url: URL) -> bytes:
        # https://tools.ietf.org/html/rfc6265#section-5.1.4
        uri_path = request_url.path

        if not uri_path or not uri_path.startswith(b'/'):
            return b'/'

        if uri_path == b'/':
            return uri_path

        return uri_path[0:uri_path.rfind(b'/')]

    @staticmethod
    def domain_match(domain: bytes, value: bytes):
        lower_domain = domain.lower()
        lower_value = value.lower()

        if lower_domain == lower_value:
            return True

        return lower_value.startswith(lower_domain) \
               and lower_value[len(lower_domain)] == 46 \
               and not_ip_address(lower_value.decode())

    @staticmethod
    def path_match(request_path: bytes, cookie_path: bytes):
        # https://tools.ietf.org/html/rfc6265#section-5.1.4
        lower_request_path = request_path.lower()
        lower_cookie_path = cookie_path.lower()

        if lower_request_path == lower_cookie_path:
            return True

        if lower_request_path.startswith(lower_cookie_path) \
                and lower_cookie_path[-1] == 47:
            return True

        if lower_request_path.startswith(lower_cookie_path) \
                and lower_request_path[len(lower_cookie_path)] == 47:
            return True

        return False

    def get_cookies_for_url(self, url: URL):
        return self.get_cookies(url.schema,
                                self._get_url_host(url),
                                self._get_url_path(url))

    def _get_cookies_by_path(self, schema: bytes, path: bytes, cookies_by_path: dict):
        for cookie_path, cookies in cookies_by_path.items():
            if CookieJar.path_match(path, cookie_path):
                for cookie in self._check_cookies(schema, cookies):
                    yield cookie.clone()

    @staticmethod
    def _check_cookies(schema: bytes, cookies: dict):
        for cookie_name, stored_cookie in cookies.copy().items():

            if stored_cookie.is_expired():
                try:
                    del cookies[cookie_name]
                except KeyError:
                    pass
                continue

            cookie = stored_cookie.cookie
            if cookie.secure and schema != b'https':
                # skip cookie for this request
                continue

            yield cookie

    def get_cookies(self, schema: bytes, domain: bytes, path: bytes):
        for cookies_domain, cookies_by_path in self._host_only_cookies.items():
            if cookies_domain == domain:
                yield from self._get_cookies_by_path(schema, path, cookies_by_path)

        for cookies_domain, cookies_by_path in self._domain_cookies.items():
            if CookieJar.domain_match(cookies_domain, domain):
                yield from self._get_cookies_by_path(schema, path, cookies_by_path)

    @staticmethod
    def _ensure_dict_container(container, key):
        try:
            return container[key]
        except KeyError:
            new_container = {}
            container[key] = new_container
            return new_container

    def _set_ensuring_container(self, root_container, domain, path, stored_cookie: StoredCookie):
        domain_container = self._ensure_dict_container(root_container, domain)
        path_container = self._ensure_dict_container(domain_container, path)
        domain_container[path] = path_container
        path_container[stored_cookie.name.lower()] = stored_cookie

    @staticmethod
    def _get(container: dict, domain: bytes, path: bytes, cookie_name: bytes) -> Optional[StoredCookie]:
        try:
            return container[domain][path][cookie_name]
        except KeyError:
            return None

    @staticmethod
    def _remove(container: dict, domain: bytes, path: bytes, cookie_name: bytes) -> bool:
        try:
            del container[domain][path][cookie_name]
        except KeyError:
            return False
        return True

    def get(self, domain: bytes, path: bytes, cookie_name: bytes) -> Optional[StoredCookie]:
        return self._get(self._host_only_cookies, domain, path, cookie_name) \
               or self._get(self._domain_cookies, domain, path, cookie_name)

    def remove(self, domain: bytes, path: bytes, cookie_name: bytes) -> bool:
        return self._remove(self._host_only_cookies, domain, path, cookie_name) \
               or self._remove(self._domain_cookies, domain, path, cookie_name)

    def add(self, request_url: URL, cookie: Cookie):
        domain = self.get_domain(request_url, cookie)
        path = self.get_path(request_url, cookie)
        cookie_name = cookie.name.lower()

        stored_cookie = StoredCookie(cookie)

        if cookie.domain:
            container = self._domain_cookies
        else:
            container = self._host_only_cookies

        # handle existing cookie
        # https://tools.ietf.org/html/rfc6265#page-23
        existing_cookie = self.get(domain, path, cookie_name)

        if existing_cookie:
            if existing_cookie.cookie.http_only and not cookie.http_only:
                # ignore
                return
            stored_cookie.creation_time = existing_cookie.creation_time

        if stored_cookie.is_expired():
            # remove existing cookie with the same name; if applicable;
            if existing_cookie:
                self.remove(domain, path, cookie_name)
            return

        self._set_ensuring_container(container, domain, path, stored_cookie)


async def cookies_middleware(request, next_handler):
    cookie_jar = request.context.cookies

    for cookie in cookie_jar.get_cookies_for_url(request.url):
        request.set_cookie(cookie.name, cookie.value)

    response = await next_handler(request)

    if b'set-cookie' in response.headers:
        for cookie in response.cookies.values():
            try:
                cookie_jar.add(request.url, cookie)
            except InvalidCookie as invalid_cookie_error:
                client_logger.debug(f'Rejected cookie for {request.url}; the cookie is invalid: '
                                    f'{str(invalid_cookie_error)}')
    return response
