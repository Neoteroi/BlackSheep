import asyncio
from typing import Optional

from blacksheep.contents import Content
from blacksheep.server.application import Application
from blacksheep.server.responses import Response
from blacksheep.testing.simulator import AbstractTestSimulator, TestSimulator
from blacksheep.testing.websocket import TestWebSocket

from .helpers import CookiesType, HeadersType, QueryType


class TestClient:
    # Setting this dunder variable
    # We tell to pytest don't discover this up
    __test__ = False

    def __init__(
        self, app: Application, test_simulator: Optional[AbstractTestSimulator] = None
    ):
        self._test_simulator = test_simulator or TestSimulator(app)

    async def get(
        self,
        path: str,
        headers: HeadersType = None,
        query: QueryType = None,
        cookies: CookiesType = None,
    ) -> Response:
        """Simulates HTTP GET method"""
        return await self._test_simulator.send_request(
            method="GET",
            path=path,
            headers=headers,
            query=query,
            cookies=cookies,
            content=None,
        )

    async def post(
        self,
        path: str,
        headers: HeadersType = None,
        query: QueryType = None,
        content: Optional[Content] = None,
        cookies: CookiesType = None,
    ) -> Response:
        """Simulates HTTP POST method"""
        return await self._test_simulator.send_request(
            method="POST",
            path=path,
            headers=headers,
            query=query,
            cookies=cookies,
            content=content,
        )

    async def patch(
        self,
        path: str,
        headers: HeadersType = None,
        query: QueryType = None,
        content: Optional[Content] = None,
        cookies: CookiesType = None,
    ) -> Response:
        """Simulates HTTP PATCH method"""
        return await self._test_simulator.send_request(
            method="PATCH",
            path=path,
            headers=headers,
            query=query,
            cookies=cookies,
            content=content,
        )

    async def put(
        self,
        path: str,
        headers: HeadersType = None,
        query: QueryType = None,
        content: Optional[Content] = None,
        cookies: CookiesType = None,
    ) -> Response:
        """Simulates HTTP PUT method"""
        return await self._test_simulator.send_request(
            method="PUT",
            path=path,
            headers=headers,
            query=query,
            content=content,
            cookies=cookies,
        )

    async def delete(
        self,
        path: str,
        headers: HeadersType = None,
        query: QueryType = None,
        content: Optional[Content] = None,
        cookies: CookiesType = None,
    ) -> Response:
        """Simulates HTTP DELETE method"""
        return await self._test_simulator.send_request(
            method="DELETE",
            path=path,
            headers=headers,
            query=query,
            content=content,
            cookies=cookies,
        )

    async def options(
        self,
        path: str,
        headers: HeadersType = None,
        query: QueryType = None,
        cookies: CookiesType = None,
    ) -> Response:
        """Simulates HTTP OPTIONS method"""
        return await self._test_simulator.send_request(
            method="OPTIONS",
            path=path,
            headers=headers,
            query=query,
            content=None,
            cookies=cookies,
        )

    async def head(
        self,
        path: str,
        headers: HeadersType = None,
        query: QueryType = None,
        cookies: CookiesType = None,
    ) -> Response:
        """Simulates HTTP HEAD method"""
        return await self._test_simulator.send_request(
            method="HEAD",
            path=path,
            headers=headers,
            query=query,
            content=None,
            cookies=cookies,
        )

    async def trace(
        self,
        path: str,
        headers: HeadersType = None,
        query: QueryType = None,
        cookies: CookiesType = None,
    ) -> Response:
        """Simulates HTTP TRACE method"""
        return await self._test_simulator.send_request(
            method="TRACE",
            path=path,
            headers=headers,
            query=query,
            content=None,
            cookies=cookies,
        )

    def websocket_connect(
        self,
        path: str,
        headers: HeadersType = None,
        query: QueryType = None,
        cookies: CookiesType = None,
    ) -> TestWebSocket:
        return self._test_simulator.websocket_connect(
            path=path,
            headers=headers,
            query=query,
            content=None,
            cookies=cookies,
        )

    async def websocket_all_closed(self):
        await asyncio.gather(*self._test_simulator.websocket_tasks)
        self._test_simulator.websocket_tasks = []
