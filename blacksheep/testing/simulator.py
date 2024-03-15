import abc
import asyncio
from typing import Dict, Optional

from blacksheep.contents import Content
from blacksheep.messages import Request
from blacksheep.server.application import Application
from blacksheep.server.responses import Response
from blacksheep.testing.helpers import get_example_scope
from blacksheep.testing.websocket import TestWebSocket

from .helpers import CookiesType, HeadersType, QueryType


def _create_scope(
    method: str,
    path: str,
    headers: HeadersType = None,
    query: QueryType = None,
    cookies: CookiesType = None,
) -> Dict:
    """Creates a mocked ASGI scope"""
    return get_example_scope(
        method, path, extra_headers=headers, query=query, cookies=cookies
    )


def should_use_chunked_encoding(content: Content) -> bool:
    return content.length < 0


def set_headers_for_response_content(message: Response):
    content = message.content

    if not content:
        message.add_header(b"content-length", b"0")
        return

    message.add_header(b"content-type", content.type or b"application/octet-stream")

    if should_use_chunked_encoding(content):
        message.add_header(b"transfer-encoding", b"chunked")
    else:
        message.add_header(b"content-length", str(content.length).encode())


class AbstractTestSimulator:
    """An abstract class for custom Test simulator clients"""

    @abc.abstractmethod
    async def send_request(
        self,
        method: str,
        path: str,
        headers: HeadersType = None,
        query: QueryType = None,
        content: Optional[Content] = None,
        cookies: CookiesType = None,
    ) -> Response:
        """Entrypoint for all HTTP methods

        The method is main entrypoint for all TestClient methods
            - get
            - post
            - patch
            - put
            - delete
        Then you can define an own TestClient, with the custom logic.
        """

    @abc.abstractmethod
    async def websocket_connect(
        self,
        path,
        headers: HeadersType = None,
        query: QueryType = None,
        content: Optional[Content] = None,
        cookies: CookiesType = None,
    ) -> TestWebSocket:
        """Entrypoint for WebSocket"""


class TestSimulator(AbstractTestSimulator):
    """Base Test simulator class

    The class introduces a fast "tests" for your server-side application,
    it means that all incoming requests are mocked.
    """

    def __init__(self, app: Application):
        self.app = app
        self.websocket_tasks = []
        self._is_started_app()

    async def send_request(
        self,
        method: str,
        path: str,
        headers: HeadersType = None,
        query: QueryType = None,
        content: Optional[Content] = None,
        cookies: CookiesType = None,
    ) -> Response:
        scope = _create_scope(method, path, headers, query, cookies=cookies)
        request = Request.incoming(
            scope["method"],
            scope["raw_path"],
            scope["query_string"],
            scope["headers"],
        )

        request.scope = scope  # type: ignore

        if content is not None:
            if not isinstance(content, Content):
                raise ValueError(
                    "The content argument should be an instance of Content class"
                )

            request.content = content

        response = await self.app.handle(request)
        set_headers_for_response_content(response)

        return response

    def websocket_connect(
        self,
        path: str,
        headers: HeadersType = None,
        query: QueryType = None,
        content: Optional[Content] = None,
        cookies: CookiesType = None,
    ) -> TestWebSocket:
        scope = _create_scope("GET_WS", path, headers, query, cookies=cookies)
        scope["type"] = "websocket"
        test_websocket = TestWebSocket()

        self.websocket_tasks.append(
            asyncio.create_task(
                self.app(
                    scope,
                    test_websocket._receive,
                    test_websocket._send,
                ),
            ),
        )

        return test_websocket

    def _is_started_app(self):
        assert (
            self.app.started
        ), "The BlackSheep application is not started, use Application.start method"
