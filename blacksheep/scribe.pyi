from typing import AsyncIterable, Callable
from blacksheep.messages import Request, Response
from blacksheep.contents import Content


def get_status_line(status: int) -> bytes:
    ...


def is_small_request(request: Request) -> bool:
    ...


def request_has_body(request: Request) -> bool:
    ...


def write_small_request(request: Request) -> bytes:
    ...


def write_request_without_body(request: Request) -> bytes:
    ...


async def write_chunks(content: Content):
    ...


async def send_asgi_response(response: Response, send: Callable):
    ...


async def write_request(request: Request) -> AsyncIterable[bytes]:
    ...


async def write_request_body_only(request: Request) -> AsyncIterable[bytes]:
    ...
