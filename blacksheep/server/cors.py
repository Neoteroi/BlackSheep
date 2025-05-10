import re
from functools import lru_cache
from typing import Any, Awaitable, Callable, Dict, FrozenSet, Iterable, Optional, Union

from blacksheep.baseapp import BaseApplication
from blacksheep.messages import Request, Response
from blacksheep.server.routing import Route, Router
from blacksheep.server.websocket import WebSocket

from .responses import not_found, ok, status_code


class CORSPolicy:
    def __init__(
        self,
        *,
        allow_methods: Union[None, str, Iterable[str]] = None,
        allow_headers: Union[None, str, Iterable[str]] = None,
        allow_origins: Union[None, str, Iterable[str]] = None,
        allow_credentials: bool = False,
        max_age: int = 5,
        expose_headers: Union[None, str, Iterable[str]] = None,
    ) -> None:
        if expose_headers is None:
            expose_headers = self.default_expose_headers()
        self._max_age: int = 300
        self._allow_methods: FrozenSet[str]
        self._allow_headers: FrozenSet[str]
        self._allow_origins: FrozenSet[str]
        self._expose_headers: FrozenSet[str]
        self.allow_methods = allow_methods or []
        self.allow_headers = allow_headers or []
        self.allow_origins = allow_origins or []
        self.allow_credentials = bool(allow_credentials)
        self.expose_headers = expose_headers
        self.max_age = max_age

    def default_expose_headers(self) -> FrozenSet[str]:
        return frozenset(
            value.lower()
            for value in {
                "Transfer-Encoding",
                "Content-Encoding",
                "Vary",
                "Request-Context",
                "Set-Cookie",
                "Server",
                "Date",
            }
        )

    def _normalize_set(
        self, value: Union[None, str, Iterable[str]], ci_function: Callable[[str], str]
    ) -> FrozenSet[str]:
        if value is None:
            return frozenset()
        if isinstance(value, str):
            value = re.split(r"\s|,\s?|;\s?", value)
        return frozenset(map(ci_function, value))

    @property
    def allow_methods(self) -> FrozenSet[str]:
        return self._allow_methods

    @allow_methods.setter
    def allow_methods(self, value) -> None:
        self._allow_methods = self._normalize_set(value, str.upper)

    @property
    def allow_headers(self) -> FrozenSet[str]:
        return self._allow_headers

    @allow_headers.setter
    def allow_headers(self, value) -> None:
        self._allow_headers = self._normalize_set(value, str.lower)

    @property
    def allow_origins(self) -> FrozenSet[str]:
        return self._allow_origins

    @allow_origins.setter
    def allow_origins(self, value) -> None:
        self._allow_origins = self._normalize_set(value, str.lower)

    @property
    def max_age(self) -> int:
        return self._max_age

    @max_age.setter
    def max_age(self, value) -> None:
        int_value = int(value)
        if int_value < 0:
            raise ValueError("max_age must be a positive number")
        self._max_age = int_value

    @property
    def expose_headers(self) -> FrozenSet[str]:
        return self._expose_headers

    @expose_headers.setter
    def expose_headers(self, value) -> None:
        self._expose_headers = self._normalize_set(value, str.lower)

    def allow_any_header(self) -> "CORSPolicy":
        self.allow_headers = frozenset("*")
        return self

    def allow_any_method(self) -> "CORSPolicy":
        self.allow_methods = frozenset("*")
        return self

    def allow_any_origin(self) -> "CORSPolicy":
        self.allow_origins = frozenset("*")
        return self


class CORSConfigurationError(Exception):
    pass


class CORSPolicyNotConfiguredError(CORSConfigurationError):
    def __init__(self, name: str) -> None:
        super().__init__(
            f'The policy with name "{name}" is not configured. '
            "Configure this policy before applying it to request handlers."
        )


class NotRequestHandlerError(CORSConfigurationError):
    def __init__(self) -> None:
        super().__init__(
            "The decorated function is not a request handler. "
            "Apply the @cors() decorator after decorators that define routes."
        )


class CORSStrategy:
    def __init__(self, default_policy: CORSPolicy, router: Router) -> None:
        self.default_policy = default_policy
        self._router = router
        self._policies: Dict[str, CORSPolicy] = {}
        self._policies_by_route: Dict[Route, CORSPolicy] = {}

    @property
    def router(self) -> Router:
        return self._router

    @property
    def policies(self) -> Dict[str, CORSPolicy]:
        return self._policies

    def add_policy(self, name: str, policy: CORSPolicy) -> "CORSStrategy":
        """
        Adds a new CORS policy by name to the overall CORS configuration.

        The CORS policy can then be associated to specific request handlers,
        using the instance of `CORSStrategy` as a function decorator:

        @app.cors("example")
        @app.router.route("/")
        async def foo():
            ....
        """
        if not name:
            raise CORSConfigurationError(
                "A name is required to configure additional CORS policies."
            )

        if name in self.policies:
            raise CORSConfigurationError(
                f"A policy with name {name} is already configured. "
                "The name of CORS policies must be unique."
            )

        self.policies[name] = policy
        return self

    def get_policy_by_route(self, route: Route) -> Optional[CORSPolicy]:
        return self._policies_by_route.get(route)

    def get_policy_by_route_or_default(self, route: Route) -> CORSPolicy:
        return self.get_policy_by_route(route) or self.default_policy

    def __call__(self, policy: str):
        """Decorates a request handler to bind it to a specific policy by name."""

        def decorator(fn):
            is_match = False
            policy_object = self.policies.get(policy)
            if not policy_object:
                raise CORSPolicyNotConfiguredError(policy)

            for route in self.router.iter_all():
                if route.handler is fn:
                    self._policies_by_route[route] = policy_object
                    is_match = True

            if not is_match:
                raise NotRequestHandlerError()

            return fn

        return decorator


def _get_cors_error_response(message: str) -> Response:
    response = status_code(400)
    response.add_header(b"CORS-Error", message.encode())
    return response


def _get_invalid_origin_response() -> Response:
    return _get_cors_error_response(
        "The origin of the request is not enabled by CORS rules."
    )


def _get_invalid_method_response() -> Response:
    return _get_cors_error_response(
        "The method of the request is not enabled by CORS rules."
    )


def _get_invalid_header_response(header_name: str) -> Response:
    return _get_cors_error_response(
        f'The "{header_name}" request header is not enabled by CORS rules.'
    )


@lru_cache(maxsize=100)
def _get_encoded_value_for_set(items: FrozenSet[str]) -> bytes:
    if not items:
        return b""
    return ", ".join(items).encode()


@lru_cache(maxsize=20)
def _get_encoded_value_for_max_age(max_age: int) -> bytes:
    return str(max_age).encode()


def _set_cors_origin(response: Response, origin_response: bytes):
    """
    Sets a Access-Control-Allow-Origin to the given value, and a `Vary: Origin` header
    if that value is not "*".
    """
    response.set_header(b"Access-Control-Allow-Origin", origin_response)

    if origin_response != b"*":
        response.add_header(b"Vary", b"Origin")


def get_cors_middleware(
    app: BaseApplication,
    strategy: CORSStrategy,
) -> Callable[[Request, Callable[..., Any]], Awaitable[Response]]:
    async def cors_middleware(request: Request, handler):
        if isinstance(request, WebSocket):
            return await handler(request)

        origin = request.get_first_header(b"Origin")

        if not origin:
            # not a CORS request
            return await handler(request)

        next_request_method = request.get_first_header(b"Access-Control-Request-Method")

        # match policy by route to support route-specific CORS rules,
        # instead of supporting only global CORS rules
        # this approach has the added value that destination routes are validated for
        # OPTIONS requests, instead of assuming a path is handled
        route = strategy.router.get_matching_route(
            next_request_method or request.method, request.url.path
        )

        if route is None:
            return not_found()

        policy = strategy.get_policy_by_route_or_default(route)
        allowed_methods = _get_encoded_value_for_set(policy.allow_methods)
        expose_headers = _get_encoded_value_for_set(policy.expose_headers)
        max_age = _get_encoded_value_for_max_age(policy.max_age)

        if (
            "*" not in policy.allow_origins
            and origin.decode() not in policy.allow_origins
        ):
            return _get_invalid_origin_response()

        # https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Access-Control-Allow-Origin
        origin_response = b"*" if "*" in policy.allow_origins else origin

        if next_request_method:
            # This is a preflight request;
            if (
                "*" not in policy.allow_methods
                and next_request_method.decode() not in policy.allow_methods
            ):
                return _get_invalid_method_response()

            next_request_headers = request.get_first_header(
                b"Access-Control-Request-Headers"
            )

            if next_request_headers and "*" not in policy.allow_headers:
                for value in next_request_headers.split(b","):
                    str_value = value.strip().decode()
                    if str_value.lower() not in policy.allow_headers:
                        return _get_invalid_header_response(str_value)

            response = ok()
            _set_cors_origin(response, origin_response)
            response.set_header(b"Access-Control-Allow-Methods", allowed_methods)

            if next_request_headers:
                response.set_header(
                    b"Access-Control-Allow-Headers", next_request_headers
                )

            if policy.allow_credentials:
                response.set_header(b"Access-Control-Allow-Credentials", b"true")

            response.set_header(b"Access-Control-Max-Age", max_age)
            return response

        # regular CORS request (non-preflight)
        if (
            "*" not in policy.allow_methods
            and request.method not in policy.allow_methods
        ):
            return _get_invalid_method_response()

        # CORS response headers must be set even if exceptions are used to
        # control the flow of the application.
        # For example if a request handler throws a "Conflict" exception to handle
        # unique constraints conflicts in a relational database.
        # If CORS response headers weren't set, error details wouldn't be available
        # to the client code, in such circumstances.
        try:
            response = await handler(request)
        except Exception as exc:
            response = await app.handle_request_handler_exception(request, exc)

        _set_cors_origin(response, origin_response)
        response.set_header(b"Access-Control-Expose-Headers", expose_headers)
        if policy.allow_credentials:
            response.set_header(b"Access-Control-Allow-Credentials", b"true")

        return response

    return cors_middleware
