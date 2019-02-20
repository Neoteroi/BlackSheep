from .options cimport ServerOptions
from .messages cimport Request, Response
from .contents cimport TextContent, HtmlContent
from .exceptions cimport HttpException, NotFound


import os
import html
import traceback


async def handle_not_found(app, Request request, HttpException http_exception):
    return Response(404, content=TextContent('Resource not found'))


async def handle_bad_request(app, Request request, HttpException http_exception):
    return Response(400, content=TextContent(f'Bad Request: {str(http_exception)}'))


cdef class BaseApplication:

    def __init__(self, ServerOptions options, object router, object services):
        self.options = options
        self.router = router
        self.services = services
        self.connections = []
        self.exceptions_handlers = self.init_exceptions_handlers()

    def init_exceptions_handlers(self):
        return {
            404: handle_not_found,
            400: handle_bad_request
        }

    async def handle(self, Request request):
        cdef object route
        cdef Response response

        route = self.router.get_match(request.method, request.url.path)

        if not route:
            response = await handle_not_found(self, request, None)
        else:
            request.route_values = route.values

            try:
                response = await route.handler(request)
            except HttpException as http_exception:
                response = await self.handle_http_exception(request, http_exception)
            except Exception as exc:
                response = await self.handle_exception(request, exc)
            else:
                # if the request handler didn't return an object,
                # and since the request was handled successfully, return success status code No Content
                # for example, a user might return "None" from an handler
                # this might be ambiguous, if a programmer thinks to return None for "Not found"
                if not response:
                    response = Response(204)
        response.headers[b'Date'] = self.current_timestamp
        response.headers[b'Server'] = b'BlackSheep'
        return response

    cdef object get_http_exception_handler(self, HttpException http_exception):
        return self.exceptions_handlers.get(http_exception.status)

    cdef object get_exception_handler(self, Exception exception):
        return self.exceptions_handlers.get(type(exception))

    async def handle_internal_server_error(self, Request request, Exception exc):
        if self.debug or self.options.show_error_details:
            tb = traceback.format_exception(exc.__class__,
                                            exc,
                                            exc.__traceback__)
            info = ''
            for item in tb:
                info += f'<li><pre>{html.escape(item)}</pre></li>'

            content = HtmlContent(self.resources.error_page_html
                                  .format_map({'process_id': os.getpid(),
                                               'info': info,
                                               'exctype': exc.__class__.__name__,
                                               'excmessage': str(exc),
                                               'method': request.method.decode(),
                                               'path': request.url.value.decode()}))

            return Response(500, content=content)
        return Response(500, content=TextContent('Internal server error.'))

    async def _apply_exception_handler(self, Request request, Exception exc, object exception_handler):
        try:
            return await exception_handler(self, request, exc)
        except Exception as server_ex:
            return await self.handle_exception(request, server_ex)

    async def handle_http_exception(self, Request request, HttpException http_exception):
        exception_handler = self.get_http_exception_handler(http_exception)
        if exception_handler:
            return await self._apply_exception_handler(request, http_exception, exception_handler)

        return await self.handle_exception(request, http_exception)

    async def handle_exception(self, request, exc):
        exception_handler = self.get_exception_handler(exc)
        if exception_handler:
            return await self._apply_exception_handler(request, exc, exception_handler)

        return await self.handle_internal_server_error(request, exc)
