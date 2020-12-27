from blacksheep.messages import Request, Response
from blacksheep.exceptions import HTTPException
from blacksheep.server.application import Application
from blacksheep.server.routing import Router
from typing import Awaitable, Dict, Union, Type, Callable, TypeVar

ExcT = TypeVar("ExcT", bound=Exception)

ExceptionHandlersType = Dict[
    Union[int, Type[Exception]],
    Callable[[Application, Request, ExcT], Awaitable[Response]],
]

class BaseApplication:
    def __init__(self, show_error_details: bool, router: Router):
        self.router = router
        self.exceptions_handlers = self.init_exceptions_handlers()
        self.show_error_details = show_error_details
    def init_exceptions_handlers(self) -> ExceptionHandlersType: ...
    async def handle(self, request: Request) -> Response: ...
    async def handle_internal_server_error(
        self, request: Request, exc: Exception
    ) -> Response: ...
    async def handle_http_exception(
        self, request: Request, http_exception: HTTPException
    ) -> Response: ...
    async def handle_exception(self, request: Request, exc: Exception) -> Response: ...
