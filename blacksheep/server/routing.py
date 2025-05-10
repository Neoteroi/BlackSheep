import inspect
import logging
import re
from abc import ABC, abstractmethod
from collections import defaultdict
from functools import lru_cache
from typing import (
    Any,
    AnyStr,
    Callable,
    Dict,
    List,
    Optional,
    Sequence,
    Set,
    Tuple,
    Union,
)
from urllib.parse import unquote

from blacksheep.common import extend
from blacksheep.common.types import (
    HeadersType,
    ParamsType,
    normalize_headers,
    normalize_params,
)
from blacksheep.messages import Request
from blacksheep.server.env import get_global_route_prefix
from blacksheep.utils import ensure_bytes, ensure_str


class RouteMethod:
    GET = "GET"
    GET_WS = "GET_WS"
    HEAD = "HEAD"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    TRACE = "TRACE"
    OPTIONS = "OPTIONS"
    CONNECT = "CONNECT"
    PATCH = "PATCH"


# for backward compatibility
HTTPMethod = RouteMethod


_route_all_rx = re.compile(b"\\*")
_route_param_rx = re.compile(b"/:([^/]+)")
_mustache_route_param_rx = re.compile(b"/{([^}]+)}")
_angle_bracket_route_param_rx = re.compile(b"/<([^>]+)>")
_named_group_rx = re.compile(b"\\?P<([^>]+)>")
_escaped_chars = {b".", b"[", b"]", b"(", b")"}


class RouteException(Exception):
    """Base class for routing exceptions."""


class RouteDuplicate(RouteException):
    def __init__(self, method, pattern, current_handler):
        method = ensure_str(method)
        pattern = ensure_str(pattern)
        super().__init__(
            f"Cannot register the route {method} {pattern} more than once. "
            f"This route is already registered for {current_handler.__qualname__}."
        )
        self.method = method
        self.pattern = pattern
        self.current_handler = current_handler


class InvalidRouterConfigurationError(RouteException):
    """Base class for router configuration errors"""


class OrphanDefaultRouterError(InvalidRouterConfigurationError):
    """
    Error raised when the default router was configured with routes, but it is not
    associated to any application.
    """

    def __init__(self) -> None:
        super().__init__(
            "Invalid router configuration: the default router was used to register "
            "routes, but it is not associated to any application object. To resolve, "
            "ensure that the router bound to your application is used to register "
            "routes. Do not use routing methods imported from the library."
        )


class SharedRouterError(InvalidRouterConfigurationError):
    """
    Error raised when the more than one application is using the same router.
    Each application object should use a different router.
    """

    def __init__(self) -> None:
        super().__init__(
            "Invalid routers configuration: the same router is used in more "
            "than one Application object. When working with multiple applications, "
            "ensure that each application is configured to use different routers. "
            "For more information, refer to: "
            "https://www.neoteroi.dev/blacksheep/routing/"
        )


class InvalidValuePatternName(RouteException):
    def __init__(self, parameter_pattern_name: str, matched_parameter: str) -> None:
        super().__init__(
            f"Invalid value pattern: {parameter_pattern_name} "
            f"for route parameter {matched_parameter}."
            f"Define a value pattern in the `Route.value_patterns` class "
            f"attribute to configure additional patterns for route values."
        )

        self.parameter_pattern_name = parameter_pattern_name
        self.matched_parameter = matched_parameter


class RouteMatch:
    __slots__ = ("_values", "pattern", "handler")

    def __init__(self, route: "Route", values: Optional[Dict[str, bytes]]):
        self.handler = route.handler
        self.pattern = route.pattern
        self._values: Optional[Dict[str, str]] = (
            {k: unquote(v.decode("utf8")) for k, v in values.items()}
            if values
            else None
        )

    @property
    def values(self) -> Optional[Dict[str, str]]:
        return self._values


class RouteFilter(ABC):
    @abstractmethod
    def handle(self, request: Request) -> bool:
        """
        Returns a value indicating whether a request should be handled by a request
        handler.
        For example, to filter requests by headers.
        """


class HeadersFilter(RouteFilter):
    """
    Filters requests by required headers values.
    """

    def __init__(self, required_headers: HeadersType) -> None:
        self.required_headers = normalize_headers(required_headers) or []

    def handle(self, request: Request) -> bool:
        for key, value in self.required_headers:
            if request.get_first_header(key) != value:
                return False
        return True


class ParamsFilter(RouteFilter):
    """
    Filters requests by required query parameters.
    """

    def __init__(self, required_params: ParamsType) -> None:
        self.required_params = normalize_params(required_params) or []

    def handle(self, request: Request) -> bool:
        for key, value in self.required_params:
            query = request.query.get(key)
            if query is not None and len(query) == 1 and query[0] == value:
                continue
            if query != value:
                return False
        return True


class HostFilter(RouteFilter):
    """
    Filters requests by host value. The comparison is always case insensitive.
    By default the port number is ignored, if present in request headers, unless the
    given host value itself includes the character ":".
    """

    def __init__(self, value: str, ignore_port: bool = True) -> None:
        self._host = value.lower()
        self._ignore_port = ignore_port if ":" not in value else False

    @property
    def host(self) -> str:
        return self._host

    def handle(self, request: Request) -> bool:
        req_host = request.host.lower()
        if self._ignore_port and ":" in req_host:
            req_host = req_host[0 : req_host.index(":")]
        return req_host == self._host


def normalize_filters(
    host: Optional[str] = None,
    headers: Optional[HeadersType] = None,
    params: Optional[ParamsType] = None,
    filters: Optional[List[RouteFilter]] = None,
) -> List[RouteFilter]:
    if filters:
        filters = filters.copy()
    else:
        filters = []

    if headers:
        filters.insert(0, HeadersFilter(headers))

    if params:
        filters.insert(0, ParamsFilter(params))

    if host:
        filters.insert(0, HostFilter(host))

    return filters


def _get_parameter_pattern_fragment(
    parameter_name: bytes, value_pattern: bytes = rb"[^\/]+"
) -> bytes:
    return b"/(?P<" + parameter_name + b">" + value_pattern + b")"


class Route:
    __slots__ = (
        "handler",
        "pattern",
        "param_names",
        "_rx",
    )

    pattern: bytes

    value_patterns = {
        "string": r"[^\/]+",
        "str": r"[^\/]+",
        "path": r".*",
        "int": r"\d+",
        "float": r"\d+(?:\.\d+)?",
        "uuid": r"[a-zA-Z0-9]{8}-[a-zA-Z0-9]{4}-[a-zA-Z0-9]"
        + r"{4}-[a-zA-Z0-9]{4}-[a-zA-Z0-9]{12}",
    }

    def __init__(
        self,
        pattern: Union[str, bytes],
        handler: Any,
    ):
        raw_pattern = self.normalize_pattern(pattern)
        self.handler = handler
        self.pattern = raw_pattern
        rx, param_names = self._get_regex_for_pattern(raw_pattern)
        self._rx = rx
        self.param_names = [name.decode("utf8") for name in param_names]

    @property
    def rx(self) -> re.Pattern:
        return self._rx

    @property
    def has_params(self) -> bool:
        return self._rx.groups > 0

    def _get_regex_for_pattern(self, pattern: bytes):
        """
        Converts a raw pattern into a compiled regular expression that can be used
        to match bytes URL paths, extracting route parameters.
        """
        # TODO: should blacksheep support ":" in routes (using escape chars)?
        for c in _escaped_chars:
            if c in pattern:
                pattern = pattern.replace(c, b"\\" + c)

        if b"*" in pattern:
            # throw exception if a star appears more than once
            if pattern.count(b"*") > 1:
                raise RouteException(
                    "A route pattern cannot contain more than one star sign *. "
                    "Multiple star signs are not supported."
                )

            if b"/*" in pattern:
                pattern = _route_all_rx.sub(rb"?(?P<tail>.*)", pattern)
            else:
                pattern = _route_all_rx.sub(rb"(?P<tail>.*)", pattern)

        # support for < > patterns, e.g. /api/cats/<cat_id>
        # but also: /api/cats/<int:cat_id> or /api/cats/<uuid:cat_id> for more
        # granular control on the generated pattern
        if b"<" in pattern:
            pattern = _angle_bracket_route_param_rx.sub(
                self._handle_rich_parameter, pattern
            )

        # support for mustache patterns, e.g. /api/cats/{cat_id}
        # but also: /api/cats/{int:cat_id} or /api/cats/{uuid:cat_id} for more
        # granular control on the generated pattern
        if b"{" in pattern:
            pattern = _mustache_route_param_rx.sub(self._handle_rich_parameter, pattern)

        # route parameters defined using /:name syntax
        if b"/:" in pattern:
            pattern = _route_param_rx.sub(rb"/(?P<\1>[^\/]+)", pattern)

        # NB: following code is just to throw user friendly errors;
        # regex would fail anyway, but with a more complex message
        # 'sre_constants.error: redefinition of group name'
        # we only return param names as they are useful for other things
        param_names = []
        for p in _named_group_rx.finditer(pattern):
            param_name = p.group(1)
            if param_name in param_names:
                raise ValueError(
                    f"cannot have multiple parameters with name: " f"{param_name}"
                )

            param_names.append(param_name)

        if len(pattern) > 1 and not pattern.endswith(b"*"):
            # NB: the /? at the end ensures that a route is matched both with
            # a trailing slash or not
            pattern = pattern + b"/?"
        return re.compile(b"^" + pattern + b"$", re.IGNORECASE), param_names

    def _handle_rich_parameter(self, match: re.Match):
        """
        Handles a route parameter that can include details about the pattern,
        for example:

        /api/cats/<int:cat_id>
        /api/cats/<uuid:cat_id>

        /api/cats/{int:cat_id}
        /api/cats/{uuid:cat_id}
        """
        assert (
            len(match.groups()) == 1
        ), "The regex using this function must handle a single group at a time."

        matched_parameter = next(iter(match.groups()))
        assert isinstance(matched_parameter, bytes)

        if b":" in matched_parameter:
            assert matched_parameter.count(b":") == 1

            raw_pattern_name, parameter_name = matched_parameter.split(b":")
            parameter_pattern_name = raw_pattern_name.decode()
            parameter_pattern = Route.value_patterns.get(parameter_pattern_name)

            if not parameter_pattern:
                raise InvalidValuePatternName(
                    parameter_pattern_name,
                    matched_parameter.decode("utf8"),
                )

            return _get_parameter_pattern_fragment(
                parameter_name, parameter_pattern.encode()
            )
        return _get_parameter_pattern_fragment(matched_parameter)

    def normalize_pattern(self, pattern: Union[str, bytes]) -> bytes:
        if isinstance(pattern, str):
            raw_pattern = pattern.encode("utf8")
        else:
            raw_pattern = pattern

        if raw_pattern == b"":
            raw_pattern = b"/"
        if len(raw_pattern) > 1 and raw_pattern.endswith(b"/"):
            raw_pattern = raw_pattern.rstrip(b"/")

        return raw_pattern

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} \"{self.pattern.decode('utf8')}\">"

    @staticmethod
    def _normalize_rich_parameter(match: re.Match):
        matched_parameter = next(iter(match.groups()))
        parts = matched_parameter.split(b":")
        parameter_name = parts[1] if len(parts) > 1 else matched_parameter
        return b"/{" + parameter_name + b"}"

    @property
    def mustache_pattern(self) -> str:
        pattern = self.pattern
        if b"<" in pattern:
            pattern = _angle_bracket_route_param_rx.sub(
                self._normalize_rich_parameter, pattern
            )
        if b"{" in pattern:
            pattern = _mustache_route_param_rx.sub(
                self._normalize_rich_parameter, pattern
            )
        return _route_param_rx.sub(rb"/{\1}", pattern).decode("utf8")

    @property
    def full_pattern(self) -> bytes:
        return self._rx.pattern

    def match(self, request: Request) -> Optional[RouteMatch]:
        return self.match_by_path(ensure_bytes(request._path))

    def match_by_path(self, path: bytes) -> Optional[RouteMatch]:
        """
        Returns a match by path - this method can be used only when the route does not
        define any filter.
        """
        if not self.has_params and path.lower() == self.pattern:
            return RouteMatch(self, None)

        match = self._rx.match(path)

        if not match:
            return None

        return RouteMatch(self, match.groupdict() if self.has_params else None)


class FilterRoute(Route):
    """
    Route class that supports filters for requests.
    """

    __slots__ = (
        "handler",
        "pattern",
        "filters",
        "param_names",
        "_rx",
    )

    def __init__(
        self,
        pattern: Union[str, bytes],
        handler: Any,
        filters: List[RouteFilter],
    ):
        super().__init__(pattern, handler)
        self.filters = filters

    def match(self, request: Request) -> Optional[RouteMatch]:
        match = super().match(request)

        if not match:
            return None

        if all(action_filter.handle(request) for action_filter in self.filters):
            return match

        return None


class RouterBase(ABC):
    """
    Base abstract class for types that can register HTTP routes and filters.
    """

    def __init__(
        self,
        *,
        host: Optional[str] = None,
        headers: Optional[HeadersType] = None,
        params: Optional[ParamsType] = None,
        filters: Optional[List[RouteFilter]] = None,
    ):
        self._filters = normalize_filters(host, headers, params, filters)

    @abstractmethod
    def add(
        self,
        method: str,
        pattern: str,
        handler: Callable,
    ) -> None:
        """Adds a request handler for the given HTTP method and route pattern."""

    def mark_handler(self, handler: Callable) -> None:
        setattr(handler, "route_handler", True)

    def normalize_default_pattern_name(self, handler_name: str) -> str:
        return handler_name.replace("_", "-")

    def _get_decorator(
        self,
        method: str,
        pattern: Optional[str] = "/",
    ) -> Callable[..., Any]:
        def decorator(fn):
            nonlocal pattern
            if pattern is ... or pattern is None:
                # default to something depending on decorated function's name
                if fn.__name__ in {"index", "default"}:
                    pattern = "/"
                else:
                    pattern = "/" + self.normalize_default_pattern_name(fn.__name__)

                logging.debug(
                    "Defaulting to route pattern '%s' for" "request handler <%s>",
                    pattern,
                    fn.__qualname__,
                )
            self.add(method, pattern, fn)
            return fn

        return decorator

    def add_head(self, pattern: str, handler: Callable[..., Any]) -> None:
        self.add(RouteMethod.HEAD, pattern, handler)

    def add_get(self, pattern: str, handler: Callable[..., Any]) -> None:
        self.add(RouteMethod.GET, pattern, handler)

    def add_post(self, pattern: str, handler: Callable[..., Any]) -> None:
        self.add(RouteMethod.POST, pattern, handler)

    def add_put(self, pattern: str, handler: Callable[..., Any]) -> None:
        self.add(RouteMethod.PUT, pattern, handler)

    def add_delete(self, pattern: str, handler: Callable[..., Any]) -> None:
        self.add(RouteMethod.DELETE, pattern, handler)

    def add_trace(self, pattern: str, handler: Callable[..., Any]) -> None:
        self.add(RouteMethod.TRACE, pattern, handler)

    def add_options(self, pattern: str, handler: Callable[..., Any]) -> None:
        self.add(RouteMethod.OPTIONS, pattern, handler)

    def add_connect(self, pattern: str, handler: Callable[..., Any]) -> None:
        self.add(RouteMethod.CONNECT, pattern, handler)

    def add_patch(self, pattern: str, handler: Callable[..., Any]) -> None:
        self.add(RouteMethod.PATCH, pattern, handler)

    def add_ws(self, pattern: str, handler: Callable[..., Any]) -> None:
        self.add(RouteMethod.GET_WS, pattern, handler)

    def head(self, pattern: Optional[str] = "/") -> Callable[..., Any]:
        return self._get_decorator(RouteMethod.HEAD, pattern)

    def get(self, pattern: Optional[str] = "/") -> Callable[..., Any]:
        return self._get_decorator(RouteMethod.GET, pattern)

    def post(self, pattern: Optional[str] = "/") -> Callable[..., Any]:
        return self._get_decorator(RouteMethod.POST, pattern)

    def put(self, pattern: Optional[str] = "/") -> Callable[..., Any]:
        return self._get_decorator(RouteMethod.PUT, pattern)

    def delete(self, pattern: Optional[str] = "/") -> Callable[..., Any]:
        return self._get_decorator(RouteMethod.DELETE, pattern)

    def trace(self, pattern: Optional[str] = "/") -> Callable[..., Any]:
        return self._get_decorator(RouteMethod.TRACE, pattern)

    def options(self, pattern: Optional[str] = "/") -> Callable[..., Any]:
        return self._get_decorator(RouteMethod.OPTIONS, pattern)

    def connect(self, pattern: Optional[str] = "/") -> Callable[..., Any]:
        return self._get_decorator(RouteMethod.CONNECT, pattern)

    def patch(self, pattern: Optional[str] = "/") -> Callable[..., Any]:
        return self._get_decorator(RouteMethod.PATCH, pattern)

    def ws(self, pattern) -> Callable[..., Any]:
        return self._get_decorator(RouteMethod.GET_WS, pattern)

    def route(
        self, pattern: str, methods: Optional[Sequence[str]] = None
    ) -> Callable[..., Any]:
        if methods is None:
            methods = ["GET"]

        def decorator(f):
            for method in methods:
                self.add(method, pattern, f)
            return f

        return decorator


class MultiRouterMixin:
    """
    This mixin is activate automatically when a Router defines sub-routers.
    """

    _sub_routers: List["Router"]

    def __iter__(self):
        yield from super().__iter__()  # type: ignore

        for router in self._sub_routers:
            yield from router

    def iter_with_methods(self):
        """
        Iters through the routes defined in this Router, yielding each route
        and its HTTP method.
        """
        yield from super().iter_with_methods()  # type: ignore

        for router in self._sub_routers:
            yield from router.iter_with_methods()

    def get_match(self, request: Request) -> Optional[RouteMatch]:
        for router in self._sub_routers:
            match = router.get_match(request)

            if match:
                return match

        return super().get_match(request)  # type: ignore


class RouterFiltersMixin:
    """
    This mixin is activated automatically when any of the routes defined for a web app
    uses filters (RouteFilter). The rationale for using a mixin is that using filters
    incurs a performance fee, and fees should only be paid when using features.
    """

    routes: Dict[bytes, List[Route]]
    _fallback: Any

    def get_match(self, request: Request) -> Optional[RouteMatch]:
        for route in self.routes[ensure_bytes(request.method)]:
            match = route.match(request)

            if match:
                return match

        if self._fallback is None:
            return None

        return RouteMatch(self._fallback, None)


RouteConfig = Union[Dict[str, Any], "Router"]


def _combine_with_global_prefix(prefix: str) -> str:
    """
    Combines a router specific prefix with the global prefix, if one is defined using
    env variables.
    """
    global_prefix = get_global_route_prefix()
    if global_prefix:
        if not prefix:
            return global_prefix

        global_prefix = global_prefix.rstrip("/")
        prefix = prefix.lstrip("/")
        return f"{global_prefix}/{prefix}"
    return prefix


class Router(RouterBase):
    __slots__ = (
        "routes",
        "controllers_routes",
        "_map",
        "_fallback",
        "_sub_routers",
        "_filters",
        "_prefix",
        "_registered_routes",
    )

    def __init__(
        self,
        *,
        host: Optional[str] = None,
        headers: Optional[HeadersType] = None,
        params: Optional[ParamsType] = None,
        filters: Optional[List[RouteFilter]] = None,
        sub_routers: Optional[List["Router"]] = None,
        prefix: str = "",
    ):
        super().__init__(
            host=host,
            headers=headers,
            params=params,
            filters=filters,
        )

        self._map = {}
        self._fallback = None
        self._prefix: bytes = self._normalize_prefix(
            _combine_with_global_prefix(prefix)
        )
        self.routes: Dict[bytes, List[Route]] = defaultdict(list)  # final routes
        self.controllers_routes = RoutesRegistry()  # used during controllers setup
        self._sub_routers = sub_routers
        self._registered_routes = []  # used during setup

        if self._filters:
            extend(self, RouterFiltersMixin)

        if self._sub_routers:
            extend(self, MultiRouterMixin)

    @property
    def registered_routes(self) -> List[Tuple[str, Route]]:
        return self._registered_routes

    def reset(self):
        """Resets this router to its initial state."""
        self._map = {}
        self._fallback = None
        self.routes = defaultdict(list)
        self.controllers_routes.reset()
        if self._sub_routers:
            for sub_router in self._sub_routers:
                sub_router.reset()

    @property
    def prefix(self) -> str:
        return self._prefix.decode("utf8")

    @property
    def fallback(self):
        return self._fallback

    @fallback.setter
    def fallback(self, value):
        if not isinstance(value, Route):
            if callable(value):
                self._fallback = Route(b"*", value)
                return
            raise ValueError("fallback must be a Route or a callable")
        self._fallback = value

    def __iter__(self):
        for _, routes in self.routes.items():
            for route in routes:
                yield route
        if self._fallback:
            yield self._fallback

    def iter_all(self):
        yield from self
        for _, route in self._registered_routes:
            yield route

    def iter_with_methods(self):
        """
        Iters through the routes defined in this Router, yielding each route
        and its HTTP method.
        """
        for method, routes in self.routes.items():
            for route in routes:
                yield method.decode(), route
        if self._fallback:
            yield "*", self._fallback

    def _normalize_prefix(self, prefix: str) -> bytes:
        if not prefix:
            return b""

        if "." in prefix:
            prefix = prefix.replace(".", "")

        while "//" in prefix:
            prefix = prefix.replace("//", "/")

        value = ensure_bytes(prefix)
        if not value.startswith(b"/"):
            value = b"/" + value
        if value.endswith(b"/"):
            value = value[:-1]
        return value

    def _is_route_configured(self, method: bytes, route: Route):
        if isinstance(route, FilterRoute):  # pragma: no cover
            # The route defines action filters, we cannot determine if the user is
            # registering twice the same pattern. However, the user opted-in for an
            # advanced feature and should be aware about conflicting routes.
            return False

        method_patterns = self._map.get(method)
        if not method_patterns:
            return False
        existing_route: Route = method_patterns.get(route.full_pattern)

        if existing_route and not isinstance(existing_route, FilterRoute):
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
            current_route = self._map[method][new_route.full_pattern]
            raise RouteDuplicate(method, new_route.pattern, current_route.handler)
        self._set_configured_route(method, new_route)

    def _get_pattern(self, pattern: AnyStr) -> bytes:
        value = ensure_bytes(pattern)
        if self._prefix:
            return self._prefix + value
        if not value.startswith(b"/"):
            return b"/" + value
        return value

    def add(
        self,
        method: str,
        pattern: AnyStr,
        handler: Any,
        filters: Optional[List[RouteFilter]] = None,
    ):
        new_route = self.create_route(pattern, handler, filters)
        self._registered_routes.append((method, new_route))

    def create_route(
        self,
        pattern: AnyStr,
        handler: Any,
        filters: Optional[List[RouteFilter]] = None,
    ) -> Route:
        if filters and not isinstance(self, RouterFiltersMixin):
            extend(self, RouterFiltersMixin)

        route_filters = filters or self._filters

        self.mark_handler(handler)
        return (
            FilterRoute(self._get_pattern(pattern), handler, route_filters)
            if route_filters
            else Route(self._get_pattern(pattern), handler)
        )

    def apply_routes(self) -> None:
        """
        Apply routes to this router. This is necessary to offer a good user
        experience and support partial routes that are validated at application start.
        """
        method: str
        self._check_controllers_registry()

        while True:
            try:
                method, route = self._registered_routes.pop(0)
            except IndexError:
                break

            handler = route.handler
            controller_type = getattr(handler, "controller_type", None)
            if controller_type:
                self.controllers_routes.add(
                    method, route.pattern.decode("utf8"), handler
                )
            else:
                self.add_route(method.encode(), route)

        if self._sub_routers:
            for sub_router in self._sub_routers:
                sub_router.apply_routes()

    def _check_controllers_registry(self):
        """
        If the user used the controllers_registry to define request handlers that are
        not bound to a controller class, this method corrects the situation to the
        desired internal state.
        """
        function_routes = [
            item
            for item in self.controllers_routes
            if getattr(item.handler, "controller_type", None) is None
        ]
        for route in function_routes:
            self._registered_routes.append(
                (route.method, self.create_route(route.pattern, route.handler))
            )
            self.controllers_routes.remove(route)

    def remove(self, method: AnyStr, route: Route):
        self.routes[ensure_bytes(method)].remove(route)
        del self._map[ensure_bytes(method)][route.full_pattern]

    def add_route(self, method: AnyStr, route: Route):
        method_bytes = ensure_bytes(method)
        if not isinstance(route, FilterRoute):
            self._check_duplicate(method_bytes, route)
        self.routes[method_bytes].append(route)

    def sort_routes(self):
        """
        Sorts the current routes in order of dynamic parameters ascending.
        The catch-all route is always placed to the end.
        """
        current_routes = self.routes.copy()

        for method in current_routes.keys():
            current_routes[method].sort(key=lambda route: -route.pattern.count(b"/"))
            current_routes[method].sort(key=lambda route: len(route.param_names))
            current_routes[method].sort(key=lambda route: b".*" in route.rx.pattern)
            current_routes[method].sort(
                key=lambda route: (
                    -len(route.filters) if isinstance(route, FilterRoute) else 0
                )
            )
            current_routes[method].sort(
                key=lambda route: b"*" == route.pattern or b"/*" == route.pattern
            )

        self.routes = current_routes

        if self._sub_routers:
            for sub_router in self._sub_routers:
                sub_router.sort_routes()

    def get_match(self, request: Request) -> Optional[RouteMatch]:
        """
        Gets a match for the given request, by method and request path.
        """
        return self.get_match_by_method_and_path(request.method, request._path)

    @lru_cache(maxsize=1200)
    def get_match_by_method_and_path(
        self, method: AnyStr, path: AnyStr
    ) -> Optional[RouteMatch]:
        bytes_value = ensure_bytes(path)
        for route in self.routes[ensure_bytes(method)]:
            match = route.match_by_path(bytes_value)
            if match:
                return match
        if self._fallback is None:
            return None

        return RouteMatch(self._fallback, None)

    @lru_cache(maxsize=1200)
    def get_matching_route(self, method: AnyStr, value: AnyStr) -> Optional[Route]:
        for route in self.routes[ensure_bytes(method)]:
            match = route.match_by_path(ensure_bytes(value))
            if match:
                return route
        return None


class RegisteredRoute:
    __slots__ = ("method", "pattern", "handler")

    def __init__(
        self,
        method: str,
        pattern: str,
        handler: Callable,
    ):
        self.method = method
        self.pattern = pattern
        self.handler = handler

    def __repr__(self):
        return f"<{self.__class__.__name__} {self.method} {self.pattern}>"


class RoutesRegistry(RouterBase):
    """
    A registry for routes: not a full router able to get matches.
    Unlike a router, a registry does not throw for duplicated routes;
    because such routes can be modified when applied to an actual router.

    This class is meant to enable scenarios like base pattern for controllers.
    """

    __slots__ = ("routes", "_filters")

    def __init__(
        self,
        *,
        host: Optional[str] = None,
        headers: Optional[HeadersType] = None,
        params: Optional[ParamsType] = None,
        filters: Optional[List[RouteFilter]] = None,
    ):
        super().__init__(host=host, headers=headers, params=params, filters=filters)
        self.routes: List[RegisteredRoute] = []

    def reset(self):
        """Resets this routes registry to its initial state."""
        self.routes = []

    def __iter__(self):
        yield from self.routes

    def add(
        self,
        method: str,
        pattern: str,
        handler: Callable,
    ):
        self.mark_handler(handler)
        self.routes.append(RegisteredRoute(method, pattern, handler))

    def remove(self, route: RegisteredRoute):
        self.routes.remove(route)


class MountRegistry:
    """
    Holds information about mounted applications and how they should be handled.
    """

    __slots__ = ("_mounted_apps", "_mounted_paths", "auto_events", "handle_docs")

    def __init__(self, auto_events: bool = True, handle_docs: bool = False):
        self._mounted_apps = []
        self._mounted_paths = set()
        self.auto_events = auto_events
        self.handle_docs = handle_docs

    @property
    def mounted_apps(self) -> List[Route]:
        return self._mounted_apps

    @property
    def mounted_paths(self) -> Set[str]:
        return self._mounted_paths

    def mount(self, path: str, app: Callable) -> None:
        if not path:
            path = "/"

        if path.lower() in self._mounted_paths:
            raise AssertionError(f"Mount application with path '{path}' already exist")

        self._mounted_paths.add(path.lower())

        if not path.endswith("/*"):
            path = f"{path.rstrip('/*')}/*"

        self._mounted_apps.append(Route(path, app))


# For backward compatibility
Mount = MountRegistry


_apps_by_router_id = {}


def validate_router(app):
    """
    Ensures that the same router is not bound to more than one application object.
    If the same application is being reloaded dynamically, like when using uvicorn
    programmatically, the router is reset.
    """
    app_router: Router = app.router
    router_id = id(app_router)

    # Get information about where the application was instantiated (which filename,
    # which line_number)
    _, filename, line_number, *_ = inspect.stack()[2]

    try:
        existing_app = _apps_by_router_id[router_id]
    except KeyError:
        # Good
        _apps_by_router_id[router_id] = {
            "app": app,
            "filename": filename,
            "line_number": line_number,
        }
    else:
        if (
            existing_app["filename"] == filename
            and existing_app["line_number"] == line_number
        ):
            # This is the same application! This can happen when imported dynamically
            # by uvicorn reload feature, when uvicorn is started programmatically.
            # See https://github.com/Neoteroi/BlackSheep/issues/438
            logging.getLogger("blacksheep.server").warning(
                "The application was reloaded, resetting its router."
            )
            app_router.reset()
            return
        raise SharedRouterError()


def validate_default_router():
    """
    This method ensures that the default router is associated to an application, if it
    defines any route.
    """
    if set(router):
        # The default router has routes defined, ensure that it is bound to an
        # application
        # verify that
        try:
            _apps_by_router_id[id(router)]
        except KeyError:
            # Not good
            raise OrphanDefaultRouterError() from None


# Singleton router used to store initial configuration, before the application starts.
# This is used as *default* router, but it can be overridden.
# This is done for two reasons: to reduce code verbosity when defining routes,
# and because we can expect that in most use cases, web applications use a single
# Application and Router (the same approach can be easily used for more complex use
# cases where more than one router is used).
router = Router()
controllers_routes = router.controllers_routes

head = router.head
get = router.get
post = router.post
put = router.put
patch = router.patch
delete = router.delete
trace = router.trace
options = router.options
connect = router.connect
ws = router.ws
route = router.route
