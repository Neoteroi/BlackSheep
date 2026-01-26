import http
import inspect
import logging
import typing
from collections import UserDict

from blacksheep.server.errors import ServerErrorDetailsHandler
from blacksheep.server.routing import Router

from .contents import Content, TextContent
from .exceptions import HTTPException, InternalServerError, InvalidExceptionHandler
from .messages import Response
from .utils import get_class_instance_hierarchy

try:
    from pydantic import ValidationError
except ImportError:
    ValidationError = None


if typing.TYPE_CHECKING:
    from .messages import Request


class ExceptionHandlersDict(UserDict):
    def __setitem__(self, key, item) -> None:
        if not inspect.iscoroutinefunction(item):
            raise InvalidExceptionHandler()
        signature = inspect.Signature.from_callable(item)
        if len(signature.parameters) != 3 and not any(
            param
            for param in signature.parameters
            if signature.parameters[param].kind == 2
        ):
            raise InvalidExceptionHandler()
        return super().__setitem__(key, item)


async def handle_not_found(app, request, http_exception) -> Response:
    return Response(404, content=TextContent("Resource not found"))


async def handle_internal_server_error(app, request, exception) -> Response:
    return Response(500, content=TextContent("Internal Server Error"))


async def handle_bad_request(app, request, http_exception) -> Response:
    if getattr(http_exception, "__context__", None) is not None and callable(
        getattr(http_exception.__context__, "json", None)
    ):
        return Response(
            http_exception.status,
            content=Content(
                b"application/json", http_exception.__context__.json().encode("utf8")
            ),
        )
    return Response(400, content=TextContent(f"Bad Request: {str(http_exception)}"))


async def _default_pydantic_validation_error_handler(app, request, error) -> Response:
    return Response(
        400, content=Content(b"application/json", error.json(indent=4).encode("utf-8"))
    )


async def common_http_exception_handler(app, request, http_exception) -> Response:
    return Response(
        http_exception.status,
        content=TextContent(http.HTTPStatus(http_exception.status).phrase),
    )


def get_logger() -> logging.Logger:
    logger = logging.getLogger("blacksheep.server")
    logger.setLevel(logging.INFO)
    return logger


class BaseApplication:
    router: Router

    def __init__(self, show_error_details, router):
        self.router = router
        self.exceptions_handlers = self.init_exceptions_handlers()
        self.show_error_details = show_error_details
        self.logger = get_logger()
        self.server_error_details_handler: ServerErrorDetailsHandler

    def init_exceptions_handlers(self) -> ExceptionHandlersDict:
        default_handlers = ExceptionHandlersDict(
            {404: handle_not_found, 400: handle_bad_request}
        )
        if ValidationError is not None:
            default_handlers[ValidationError] = (
                _default_pydantic_validation_error_handler
            )
        return default_handlers

    async def log_unhandled_exc(
        self,
        request: "Request",
        exc: Exception,
    ):
        self.logger.error(
            'Unhandled exception - "%s %s"',
            request.method,
            request.url.value.decode(),
            exc_info=exc,
        )

    async def log_handled_exc(
        self,
        request: "Request",
        exc: Exception,
    ):
        if isinstance(exc, HTTPException):
            self.logger.info(
                'HTTP %s - "%s %s". %s',
                exc.status,
                request.method,
                request.url.value.decode(),
                str(exc),
            )
        else:
            self.logger.info(
                'Handled error: "%s %s". %s',
                request.method,
                request.url.value.decode(),
                str(exc),
            )

    async def handle(self, request: "Request") -> Response:
        route = self.router.get_match(request)

        if not route:
            # This is intentional. We should not use user-defined not found exception
            # handlers here because middlewares are not executed. The main router should
            # always have a fallback route configured.
            return Response(404)

        request.route_values = route.values
        try:
            response = await route.handler(request)
        except Exception as exc:
            response = await self.handle_request_handler_exception(request, exc)
        return response or Response(204)

    async def handle_request_handler_exception(
        self,
        request: "Request",
        exc: Exception,
    ) -> Response:
        if isinstance(exc, HTTPException):
            await self.log_handled_exc(request, exc)
            return await self.handle_http_exception(request, exc)
        if self.is_handled_exception(exc):
            await self.log_handled_exc(request, exc)
        else:
            await self.log_unhandled_exc(request, exc)
        return await self.handle_exception(request, exc)

    def get_http_exception_handler(
        self, http_exception: HTTPException
    ) -> typing.Callable[
        ["BaseApplication", "Request", Exception], typing.Awaitable[Response]
    ]:
        handler = self.get_exception_handler(http_exception, stop_at=HTTPException)
        if handler:
            return handler
        return self.exceptions_handlers.get(
            getattr(http_exception, "status", None), common_http_exception_handler
        )

    def is_handled_exception(self, exception) -> bool:
        for class_type in get_class_instance_hierarchy(exception):
            if class_type in self.exceptions_handlers:
                return True
        return False

    def get_exception_handler(
        self,
        exception: Exception,
        stop_at: type | None,
    ) -> (
        typing.Callable[
            ["BaseApplication", "Request", Exception], typing.Awaitable[Response]
        ]
        | None
    ):
        for class_type in get_class_instance_hierarchy(exception):
            if stop_at is not None and stop_at is class_type:
                return None
            if class_type in self.exceptions_handlers:
                return self.exceptions_handlers[class_type]
        return None

    async def handle_internal_server_error(
        self,
        request: "Request",
        exc,
    ) -> Response:
        if self.show_error_details:
            return self.server_error_details_handler.produce_response(request, exc)
        error = InternalServerError(exc)
        internal_server_error_handler = self.get_http_exception_handler(error)
        try:
            return await internal_server_error_handler(self, request, error)
        except Exception:
            self.logger.exception(
                "An exception occurred while trying to apply the configured "
                "Internal Server Error handler!"
            )
        return Response(500, content=TextContent("Internal Server Error"))

    async def _apply_exception_handler(
        self,
        request: "Request",
        exc: Exception,
        exception_handler: typing.Callable[
            ["BaseApplication", "Request", Exception], typing.Awaitable[Response]
        ],
    ):
        try:
            return await exception_handler(self, request, exc)
        except Exception as server_ex:
            # If the exception happens in the user-defined exception handler,
            # we need to fallback to the default handlers.
            self.logger.error(
                "Unhandled exception in exception_handler: %s",
                exception_handler.__name__,
            )
            if self.show_error_details:
                return self.server_error_details_handler.produce_response(request, exc)

            return await handle_internal_server_error(self, request, server_ex)

    async def handle_http_exception(
        self,
        request: "Request",
        http_exception: HTTPException,
    ) -> Response:
        exception_handler = self.get_http_exception_handler(http_exception)
        if exception_handler:
            return await self._apply_exception_handler(
                request, http_exception, exception_handler
            )
        return await self.handle_exception(request, http_exception)

    async def handle_exception(self, request: "Request", exc: Exception) -> Response:
        exception_handler = self.get_exception_handler(exc, None)
        if exception_handler:
            return await self._apply_exception_handler(request, exc, exception_handler)
        return await self.handle_internal_server_error(request, exc)
