from .options cimport ServerOptions
from .messages cimport Request, Response
from .contents cimport TextContent, HtmlContent
from .exceptions cimport HttpException, HttpNotFound


import html
import traceback


cdef class BaseApplication:

    def __init__(self, ServerOptions options, object router):
        self.options = options
        self.router = router
        self.connections = []

    async def handle(self, Request request):
        cdef object route
        cdef Response response

        route = self.router.get_match(request.method, request.url.path)

        if not route:
            response = await self.handle_not_found(request)
        else:
            request.route_values = route.values

            try:
                response = await route.handler(request)
            except HttpException as http_exception:
                response = await self.handle_http_exception(request, http_exception)
            except Exception as exc:
                response = await self.handle_exception(request, exc)

        if not response:
            response = Response(204)
        response.headers[b'Date'] = self.current_timestamp
        response.headers[b'Server'] = b'BlackSheep'
        return response

    async def handle_not_found(self, Request request):
        return Response(404, content=TextContent('Resource not found'))

    async def handle_http_exception(self, Request request, HttpException http_exception):
        if isinstance(http_exception, HttpNotFound):
            return await self.handle_not_found(request)
        # TODO: improve the design of this feature
        return await self.handle_exception(request, http_exception)

    async def handle_exception(self, request, exc):
        if self.debug or self.options.show_error_details:
            tb = traceback.format_exception(exc.__class__,
                                            exc,
                                            exc.__traceback__)
            info = ''
            for item in tb:
                info += f'<li><pre>{html.escape(item)}</pre></li>'

            content = HtmlContent(self.resources.error_page_html
                                  .format_map({'info': info,
                                               'exctype': exc.__class__.__name__,
                                               'excmessage': str(exc),
                                               'method': request.method.decode(),
                                               'path': request.url.value.decode()}))

            return Response(500, content=content)
        return Response(500, content=TextContent('Internal server error.'))