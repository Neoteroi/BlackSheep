from .messages cimport Request, Response
from .contents cimport TextContent
from .exceptions cimport HTTPException


import os
import html
import http
import logging
import traceback


async def handle_not_found(app, Request request, HTTPException http_exception):
    return Response(404, content=TextContent('Resource not found'))


async def handle_bad_request(app, Request request, HTTPException http_exception):
    return Response(400, content=TextContent(f'Bad Request: {str(http_exception)}'))


async def common_http_exception_handler(app, Request request, HTTPException http_exception):
    return Response(http_exception.status, content=TextContent(http.HTTPStatus(http_exception.status).phrase))


def get_logger():
    logger = logging.getLogger("blacksheep.server")
    logger.setLevel(logging.INFO)
    return logger


cdef class BaseApplication:

    def __init__(self, bint show_error_details, object router):
        self.router = router
        self.exceptions_handlers = self.init_exceptions_handlers()
        self.show_error_details = show_error_details
        self.logger = get_logger()

    def init_exceptions_handlers(self):
        return {
            404: handle_not_found,
            400: handle_bad_request
        }

    async def log_unhandled_exc(self, request, exc):
        self.logger.error(
            "Unhandled exception - \"%s %s\"",
            request.method,
            request.url.value.decode(),
            exc_info=exc
        )

    async def log_handled_exc(self, request, HTTPException exc):
        self.logger.info(
            "HTTP %s - \"%s %s\". %s",
            exc.status,
            request.method,
            request.url.value.decode(),
            str(exc)
        )

    async def handle(self, Request request):
        cdef object route
        cdef Response response

        route = self.router.get_match(request.method, request._path)

        if route:
            request.route_values = route.values

            try:
                response = await route.handler(request)
            except HTTPException as http_exception:
                await self.log_handled_exc(request, http_exception)
                response = await self.handle_http_exception(request, http_exception)
            except Exception as exc:
                await self.log_unhandled_exc(request, exc)
                response = await self.handle_exception(request, exc)
        else:
            response = await self.exceptions_handlers.get(404)(self, request, None)
            if not response:
                response = Response(404)
        # if the request handler didn't return an object,
        # and since the request was handled successfully, return success status code No Content
        # for example, a user might return "None" from an handler
        # this might be ambiguous, if a programmer thinks to return None for "Not found"
        return response or Response(204)

    cdef object get_http_exception_handler(self, HTTPException http_exception):
        return self.exceptions_handlers.get(http_exception.status, common_http_exception_handler)

    cdef object get_exception_handler(self, Exception exception):
        return self.exceptions_handlers.get(type(exception))

    async def handle_internal_server_error(self, Request request, Exception exc):
        if self.show_error_details:
            return self.server_error_details_handler.produce_response(request, exc)
        return Response(500, content=TextContent("Internal server error."))

    async def _apply_exception_handler(self, Request request, Exception exc, object exception_handler):
        try:
            return await exception_handler(self, request, exc)
        except Exception as server_ex:
            return await self.handle_exception(request, server_ex)

    async def handle_http_exception(self, Request request, HTTPException http_exception):
        exception_handler = self.get_http_exception_handler(http_exception)
        if exception_handler:
            return await self._apply_exception_handler(request, http_exception, exception_handler)

        return await self.handle_exception(request, http_exception)

    async def handle_exception(self, request, exc):
        exception_handler = self.get_exception_handler(exc)
        if exception_handler:
            return await self._apply_exception_handler(request, exc, exception_handler)

        return await self.handle_internal_server_error(request, exc)
