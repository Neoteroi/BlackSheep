from blacksheep import Request, Response
from blacksheep.exceptions import HttpException
from blacksheep.server.routing import Router
from typing import Dict, Union, Type, Callable


ExceptionHandlersType = Dict[Union[int, Type[Exception]], Callable]


class BaseApplication:

    def __init__(self, show_error_details: bool, router: Router):
        self.router = router
        self.exceptions_handlers = self.init_exceptions_handlers()
        self.show_error_details = show_error_details

    def init_exceptions_handlers(self) -> ExceptionHandlersType: ...

    async def handle(self, request: Request) -> Response: ...

    async def handle_internal_server_error(self, request: Request, exc: Exception) -> Response: ...

    async def handle_http_exception(self, request: Request, http_exception: HttpException) -> Response: ...

    async def handle_exception(self, request: Request, exc: Exception) -> Response: ...
