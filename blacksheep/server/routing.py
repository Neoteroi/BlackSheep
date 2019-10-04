import re
from abc import abstractmethod
from functools import lru_cache
from blacksheep import HttpMethod
from collections import defaultdict
from urllib.parse import unquote
from typing import Callable, Dict, Optional, List, Any
from blacksheep.utils import ensure_bytes, ensure_str, BytesOrStr

__all__ = ['Router', 'Route', 'RouteMatch', 'RouteDuplicate', 'RegisteredRoute', 'RoutesRegistry']


_route_all_rx = re.compile(b'\\*')
_route_param_rx = re.compile(b'/:([^/]+)')
_named_group_rx = re.compile(b'\\?P<([^>]+)>')
_escaped_chars = {b'.', b'[', b']', b'(', b')'}


def _get_regex_for_pattern(pattern):

    for c in _escaped_chars:
        if c in pattern:
            pattern = pattern.replace(c, b'\\' + c)
    if b'*' in pattern:
        pattern = _route_all_rx.sub(br'(?P<tail>.+)', pattern)
    if b'/:' in pattern:
        pattern = _route_param_rx.sub(br'/(?P<\1>[^\/]+)', pattern)

    # NB: following code is just to throw user friendly errors;
    # regex would fail anyway, but with a more complex message 'sre_constants.error: redefinition of group name'
    # we only return param names as they are useful for other things
    param_names = []
    for p in _named_group_rx.finditer(pattern):
        param_name = p.group(1)
        if param_name in param_names:
            raise ValueError(f'cannot have multiple parameters with name: {param_name}')

        param_names.append(param_name)

    if len(pattern) > 1 and not pattern.endswith(b'*'):
        # NB: the /? at the end, ensures that a route is matched both with a trailing slash or not
        pattern = pattern + b'/?'
    return re.compile(b'^' + pattern + b'$', re.IGNORECASE), param_names


class RouteException(Exception):
    ...


class RouteDuplicate(RouteException):

    def __init__(self, method, pattern, current_handler):
        method = ensure_str(method)
        pattern = ensure_str(pattern)
        super().__init__(f'Cannot register route pattern `{pattern}` for `{method}` more than once. '
                         f'This pattern is already registered for handler {current_handler.__qualname__}.')
        self.method = method
        self.pattern = pattern
        self.current_handler = current_handler


class RouteMatch:

    __slots__ = ('values',
                 'handler')

    def __init__(self, route: 'Route', values: Optional[Dict[str, bytes]]):
        self.handler = route.handler
        self.values = {k: unquote(v.decode('utf8')) for k, v in values.items()} \
            if values else None  # type: Optional[Dict[str, str]]

    def __repr__(self):
        return f'<RouteMatch {id(self)}>'


class Route:

    __slots__ = ('handler',
                 'pattern',
                 'has_params',
                 'param_names',
                 '_rx')

    def __init__(self, pattern: bytes, handler: Any):
        if isinstance(pattern, str):
            pattern = pattern.encode('utf8')
        if pattern == b'':
            pattern = b'/'
        if len(pattern) > 1 and pattern.endswith(b'/'):
            pattern = pattern.rstrip(b'/')
        pattern = pattern.lower()
        self.handler = handler
        self.pattern = pattern
        self.has_params = b'*' in pattern or b':' in pattern
        rx, param_names = _get_regex_for_pattern(pattern)
        self._rx = rx
        self.param_names = [name.decode('utf8') for name in param_names]

    @property
    def full_pattern(self) -> bytes:
        return self._rx.pattern

    def match(self, value: bytes):
        if not self.has_params and value.lower() == self.pattern:
            return RouteMatch(self, None)

        match = self._rx.match(value)

        if not match:
            return None

        return RouteMatch(self, match.groupdict() if self.has_params else None)

    def __repr__(self):
        return f'<Route {self.pattern}>'


class RouterBase:

    def mark_handler(self, handler: Callable):
        setattr(handler, 'route_handler', True)

    @abstractmethod
    def add(self, method: str, pattern: BytesOrStr, handler: Callable):
        ...

    def add_head(self, pattern, handler):
        self.add(HttpMethod.HEAD, pattern, handler)

    def add_get(self, pattern, handler):
        self.add(HttpMethod.GET, pattern, handler)

    def add_post(self, pattern, handler):
        self.add(HttpMethod.POST, pattern, handler)

    def add_put(self, pattern, handler):
        self.add(HttpMethod.PUT, pattern, handler)

    def add_delete(self, pattern, handler):
        self.add(HttpMethod.DELETE, pattern, handler)

    def add_trace(self, pattern, handler):
        self.add(HttpMethod.TRACE, pattern, handler)

    def add_options(self, pattern, handler):
        self.add(HttpMethod.OPTIONS, pattern, handler)

    def add_connect(self, pattern, handler):
        self.add(HttpMethod.CONNECT, pattern, handler)

    def add_patch(self, pattern, handler):
        self.add(HttpMethod.PATCH, pattern, handler)

    def add_any(self, pattern, handler):
        self.add('*', pattern, handler)

    def head(self, pattern='/'):
        def decorator(f):
            self.add(HttpMethod.HEAD, pattern, f)
            return f
        return decorator

    def get(self, pattern='/'):
        def decorator(f):
            self.add(HttpMethod.GET, pattern, f)
            return f
        return decorator

    def post(self, pattern='/'):
        def decorator(f):
            self.add(HttpMethod.POST, pattern, f)
            return f
        return decorator

    def put(self, pattern='/'):
        def decorator(f):
            self.add(HttpMethod.PUT, pattern, f)
            return f
        return decorator

    def delete(self, pattern='/'):
        def decorator(f):
            self.add(HttpMethod.DELETE, pattern, f)
            return f
        return decorator

    def trace(self, pattern='/'):
        def decorator(f):
            self.add(HttpMethod.TRACE, pattern, f)
            return f
        return decorator

    def options(self, pattern='/'):
        def decorator(f):
            self.add(HttpMethod.OPTIONS, pattern, f)
            return f
        return decorator

    def connect(self, pattern='/'):
        def decorator(f):
            self.add(HttpMethod.CONNECT, pattern, f)
            return f
        return decorator

    def patch(self, pattern='/'):
        def decorator(f):
            self.add(HttpMethod.PATCH, pattern, f)
            return f
        return decorator


class Router(RouterBase):

    __slots__ = ('routes',
                 '_map',
                 '_fallback')

    def __init__(self):
        self._map = {}
        self._fallback = None
        self.routes = defaultdict(list)

    @property
    def fallback(self):
        return self._fallback

    @fallback.setter
    def fallback(self, value):
        if not isinstance(value, Route):
            if callable(value):
                self._fallback = Route(b'*', value)
                return
            raise ValueError('fallback must be a Route')
        self._fallback = value

    def __iter__(self):
        for key, routes in self.routes.items():
            for route in routes:
                yield route
        if self._fallback:
            yield self._fallback

    def _is_route_configured(self, method: bytes, route: Route):
        method_patterns = self._map.get(method)
        if not method_patterns:
            return False
        if method_patterns.get(route.full_pattern):
            return True
        return False

    def _set_configured_route(self, method: bytes, route: Route):
        method_patterns = self._map.get(method)
        if not method_patterns:
            self._map[method] = {route.full_pattern: route}
        else:
            method_patterns[route.full_pattern] = route

    def _check_duplicate(self, method: bytes, new_route: Route):
        if self._is_route_configured(method, new_route):
            current_route = self._map.get(method).get(new_route.full_pattern)
            raise RouteDuplicate(method, new_route.pattern, current_route.handler)
        self._set_configured_route(method, new_route)

    def add(self, method: str, pattern: BytesOrStr, handler: Any):
        self.mark_handler(handler)
        method = ensure_bytes(method)
        pattern = ensure_bytes(pattern)
        new_route = Route(pattern, handler)
        self._check_duplicate(method, new_route)
        self.add_route(method, new_route)

    def add_route(self, method: BytesOrStr, route: Route):
        self.routes[ensure_bytes(method)].append(route)

    @lru_cache(maxsize=1200)
    def get_match(self, method, value):
        method = ensure_bytes(method)
        value = ensure_bytes(value)

        for route in self.routes[method]:
            match = route.match(value)
            if match:
                return match
        return RouteMatch(self._fallback, None) if self.fallback else None


class RegisteredRoute:

    __slots__ = ('method', 'pattern', 'handler')

    def __init__(self, method: str, pattern: bytes, handler: Callable):
        self.method = method
        self.pattern = pattern
        self.handler = handler

    def __repr__(self):
        try:
            return f'<{self.__class__.__name__} {self.method} {self.pattern.decode()} {self.handler.__name__}>'
        except AttributeError:
            return f'<{self.__class__.__name__} at {id(self)}>'


class RoutesRegistry(RouterBase):
    """A registry for routes: not a full router able to get matches.
    Unlike a router, a registry does not throw for duplicated routes; because such routes can be modified
    when applied to an actual router.

    This class is meant to enable scenarios like base pattern for controllers.
    """

    def __init__(self):
        self.routes = []  # type: List[RegisteredRoute]

    def __iter__(self):
        yield from self.routes

    def add(self, method: str, pattern: BytesOrStr, handler: Callable):
        self.mark_handler(handler)
        self.routes.append(RegisteredRoute(method, pattern, handler))
