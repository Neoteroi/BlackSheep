import re
from functools import lru_cache
from blacksheep import HttpMethod
from collections import defaultdict
from urllib.parse import unquote
from typing import Callable


__all__ = ['Router', 'Route', 'RouteMatch']


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

    return re.compile(b'^' + pattern + b'$', re.IGNORECASE), param_names


class RouteException(Exception):
    pass


class RouteDuplicate(RouteException):

    def __init__(self, method, pattern, current_handler):
        super().__init__(f'Cannot register route pattern `{pattern}` for `{method}` more than once. '
                         f'This pattern is already registered for handler {current_handler.__name__}.')


class RouteMatch:

    __slots__ = ('values',
                 'handler')

    def __init__(self, route, values):
        self.handler = route.handler
        self.values = {k: unquote(v.decode('utf8')) for k, v in values.items()} if values else {}

    def __repr__(self):
        return f'<RouteMatch {id(self)}>'


class Route:

    __slots__ = ('handler',
                 'pattern',
                 'has_params',
                 'param_names',
                 '_rx')

    def __init__(self, pattern: bytes, handler: Callable):
        if isinstance(pattern, str):
            pattern = pattern.encode('utf8')
        if pattern == b'':
            pattern = b'/'
        pattern = pattern.lower()
        self.handler = handler
        self.pattern = pattern
        self.has_params = b'*' in pattern or b':' in pattern
        rx, param_names = _get_regex_for_pattern(pattern)
        self._rx = rx
        self.param_names = [name.decode('utf8') for name in param_names]

    def match(self, value: bytes):
        if not self.has_params and value.lower() == self.pattern:
            return RouteMatch(self, None)

        match = self._rx.match(value)

        if not match:
            return None

        return RouteMatch(self, match.groupdict() if self.has_params else None)

    def __repr__(self):
        return f'<Route {self.pattern}>'


class Router:

    __slots__ = ('routes',
                 '_map',
                 '_fallback')

    def __init__(self):
        self.routes = defaultdict(list)
        self._map = {}
        self._fallback = None

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

    def _is_route_configured(self, method: bytes, pattern: bytes):
        method_patterns = self._map.get(method)
        if not method_patterns:
            return False
        if method_patterns.get(pattern):
            return True
        return False

    def _set_configured_route(self, method: bytes, pattern: bytes):
        method_patterns = self._map.get(method)
        if not method_patterns:
            self._map[method] = {pattern: True}
        else:
            method_patterns[pattern] = True

    def add(self, method, pattern, handler):
        if isinstance(method, bytes):
            method = method.decode()
        new_route = Route(pattern, handler)
        if self._is_route_configured(method, new_route.pattern):
            current_match = self.get_match(method, pattern)
            raise RouteDuplicate(method, new_route.pattern, current_match.handler)
        else:
            self._set_configured_route(method, pattern)
        self.add_route(method, new_route)

    def add_route(self, method, route):
        self.routes[method].append(route)

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

    def head(self, pattern):
        def decorator(f):
            self.add(HttpMethod.HEAD, pattern, f)
            return f
        return decorator

    def get(self, pattern):
        def decorator(f):
            self.add(HttpMethod.GET, pattern, f)
            return f
        return decorator

    def post(self, pattern):
        def decorator(f):
            self.add(HttpMethod.POST, pattern, f)
            return f
        return decorator

    def put(self, pattern):
        def decorator(f):
            self.add(HttpMethod.PUT, pattern, f)
            return f
        return decorator

    def delete(self, pattern):
        def decorator(f):
            self.add(HttpMethod.DELETE, pattern, f)
            return f
        return decorator

    def trace(self, pattern):
        def decorator(f):
            self.add(HttpMethod.TRACE, pattern, f)
            return f
        return decorator

    def options(self, pattern):
        def decorator(f):
            self.add(HttpMethod.OPTIONS, pattern, f)
            return f
        return decorator

    def connect(self, pattern):
        def decorator(f):
            self.add(HttpMethod.CONNECT, pattern, f)
            return f
        return decorator

    def patch(self, pattern):
        def decorator(f):
            self.add(HttpMethod.PATCH, pattern, f)
            return f
        return decorator

    @lru_cache(maxsize=1200)
    def get_match(self, method, value):
        if isinstance(method, bytes):
            method = method.decode()
        for route in self.routes[method]:
            match = route.match(value)
            if match:
                return match
        return RouteMatch(self._fallback, None) if self.fallback else None

